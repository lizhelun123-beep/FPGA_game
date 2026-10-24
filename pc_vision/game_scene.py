"""Plane mapping, bounded scene stabilization, fixed models and interaction state."""
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .scene_protocol import TYPES


def load_game_config(path=None):
    cfg = json.loads(Path(__file__).with_name("game_config.json").read_text(encoding="utf-8"))
    if path:
        updates = json.loads(Path(path).read_text(encoding="utf-8"))
        if "model_sizes" in updates:
            cfg["model_sizes"].update(updates.pop("model_sizes"))
        cfg.update(updates)
    if cfg["version"] != 1 or set(cfg["model_sizes"]) != set(TYPES):
        raise ValueError("Invalid game configuration version/classes")
    for size in cfg["model_sizes"].values():
        if len(size) != 2 or not all(math.isfinite(v) and v > 0 for v in size):
            raise ValueError("Model dimensions must be finite and positive")
    if cfg["model_sizes"]["TARGET"][0] != cfg["model_sizes"]["TARGET"][1]:
        raise ValueError("TARGET uses one circular diameter")
    for key in ("position_alpha", "direction_alpha"):
        if not 0 < cfg[key] <= 1:
            raise ValueError(f"{key} must be in (0,1]")
    if not (0 <= cfg["dropout_seconds"] < cfg["timeout_seconds"] and
            cfg["timeout_seconds"] > 0 and cfg["match_distance"] > 0 and
            math.isfinite(cfg["physics_scale"]) and 1 <= cfg["physics_scale"] <= 10000 and
            0 <= cfg["minimum_confidence"] <= 100):
        raise ValueError("Invalid game scale, stability or timeout configuration")
    if min(min(size) for size in cfg["model_sizes"].values()) * cfg["physics_scale"] <= 10:
        raise ValueError("Model dimensions must exceed ten C intersection epsilons; increase physics_scale")
    return cfg


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    length = np.linalg.norm(vector)
    if not np.isfinite(length) or length < 1e-8:
        raise ValueError("Invalid direction")
    return tuple(vector / length)


class PlaneMapper:
    def __init__(self, calibration=None, image_size=(1280, 720)):
        self.image_size = tuple(image_size)
        self.calibration = calibration
        if calibration is None:
            self.width, self.height = image_size[0]-1, image_size[1]-1
            self.matrix = np.eye(3)
            self.unit = "preview units"
            return
        if (calibration.get("schema") != "plane-v1" or
                tuple(calibration["image_size"]) != self.image_size or
                calibration.get("unit") != "mm"):
            raise ValueError("Calibration must be plane-v1 in mm with matching unscaled image size")
        points = np.asarray(calibration["image_points"], dtype=float)
        self.width, self.height = calibration["plane_size"]
        if (points.shape != (4, 2) or not np.isfinite(points).all() or
                not all(math.isfinite(v) and v > 0 for v in (self.width, self.height)) or
                np.any(points < 0) or np.any(points > np.asarray(image_size)-1)):
            raise ValueError("Invalid calibration points or plane size")
        edges = np.roll(points, -1, axis=0)-points
        crosses = edges[:, 0]*np.roll(edges[:, 1], -1)-edges[:, 1]*np.roll(edges[:, 0], -1)
        if not np.all(crosses > 0) or cv2.contourArea(points.astype(np.float32)) < 100:
            raise ValueError("Click convex corners in TL, TR, BR, BL order")
        self.matrix = cv2.getPerspectiveTransform(points.astype(np.float32),
            np.array([[0, 0], [self.width, 0], [self.width, self.height], [0, self.height]], np.float32))
        if not np.isfinite(self.matrix).all() or abs(np.linalg.det(self.matrix)) < 1e-12:
            raise ValueError("Degenerate calibration")
        self.unit = "mm"

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def point(self, point):
        mapped = self.matrix @ np.array([*point, 1.0])
        if not np.isfinite(mapped).all() or abs(mapped[2]) < 1e-8:
            raise ValueError("Point maps to projective infinity")
        return tuple(mapped[:2] / mapped[2])

    def direction(self, center, axis, reference_length=32):
        # Transform two actual reference points, not the image angle.
        half = max(1, reference_length / 2)
        axis = np.asarray(unit(axis))
        first = self.point(np.asarray(center)-half*axis)
        second = self.point(np.asarray(center)+half*axis)
        return unit(np.subtract(second, first))

    def save(self, path):
        if self.calibration is None:
            raise ValueError("Preview has no calibration to save")
        Path(path).write_text(json.dumps(self.calibration, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class Model:
    type: str
    center: tuple
    axis: tuple
    size: tuple
    confidence: int
    direction_valid: bool = False
    held: bool = False

    @property
    def direction(self):
        return self.axis if self.type == "SOURCE" else (0.0, 0.0)

    @property
    def source_tip(self):
        # Triangle centroid at center; tip is 2/3 of total length ahead.
        return tuple(np.asarray(self.center) + np.asarray(self.axis)*self.size[0]*2/3)

    def vertices(self):
        axis = np.asarray(self.axis)
        normal = np.array([-axis[1], axis[0]])
        center = np.asarray(self.center)
        length, width = self.size
        if self.type == "SOURCE":
            return np.array([self.source_tip, center-axis*length/3+normal*width/2,
                             center-axis*length/3-normal*width/2])
        return np.array([center+axis*u*length/2+normal*v*width/2
                         for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))])

    def mirror_endpoints(self):
        return np.array([np.asarray(self.center)+np.asarray(self.axis)*self.size[0]*v
                         for v in (-.5, .5)])


def map_models(scene, mapper, cfg):
    if tuple(scene.image_size) != mapper.image_size:
        raise ValueError("Scene image size differs from calibration")
    objects = []
    for o in scene.objects:
        if o.confidence < cfg["minimum_confidence"]:
            continue
        center = mapper.point(o.center)
        if not 0 <= center[0] <= mapper.width or not 0 <= center[1] <= mapper.height:
            continue  # Four-point plane is the playfield ROI.
        if o.type == "TARGET":
            axis = (1.0, 0.0)
        elif o.type == "SOURCE":
            if not o.direction_valid:
                axis = (1.0, 0.0)
            else:
                # Transmitted source tip/direction defines a ray reference line.
                axis = mapper.direction(o.source_tip, o.source_direction, o.reference_size[0])
        else:
            if not o.axis_valid:
                raise ValueError(f"{o.type} has no reliable orientation")
            axis = mapper.direction(o.center, o.axis, o.reference_size[0])
        model = Model(o.type, center, axis, tuple(cfg["model_sizes"][o.type]),
                      o.confidence, o.type == "SOURCE" and o.direction_valid)
        if model.direction_valid and not (0 <= model.source_tip[0] <= mapper.width and
                                          0 <= model.source_tip[1] <= mapper.height):
            model = replace(model, direction_valid=False)
        objects.append(model)
    return tuple(objects)


class Stabilizer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks = []

    def clear(self):
        self.tracks.clear()

    def update(self, models, now):
        remaining = list(self.tracks)
        updated = []
        for model in models:
            choices = [(np.linalg.norm(np.subtract(model.center, old.center)), i)
                       for i, (old, _) in enumerate(remaining) if old.type == model.type]
            match = min(choices, default=(math.inf, -1))
            if match[0] <= self.cfg["match_distance"]:
                old, _ = remaining.pop(match[1])
                a = self.cfg["position_alpha"]
                center = tuple((1-a)*np.asarray(old.center)+a*np.asarray(model.center))
                direction = np.asarray(model.axis)
                if model.type in ("MIRROR", "WALL") and np.dot(direction, old.axis) < 0:
                    direction = -direction  # Unoriented axes have a 180-degree equivalence.
                d = self.cfg["direction_alpha"]
                # A genuine directed 180-degree turn must not average to zero.
                axis = unit(direction if np.dot(direction, old.axis) < -.5 else
                            (1-d)*np.asarray(old.axis)+d*direction)
                model = replace(model, center=center, axis=axis)
            updated.append((model, now))
        for old, last in remaining:
            if old.type != "SOURCE" and now-last < self.cfg["dropout_seconds"]:
                updated.append((replace(old, held=True), last))
        self.tracks = updated
        return tuple(model for model, _ in updated)

    def expire(self, now):
        self.tracks = [(model, last) for model, last in self.tracks
                       if not model.held or
                       now-last < self.cfg["dropout_seconds"]]
        return tuple(model for model, _ in self.tracks)


class GameController:
    def __init__(self, native, mapper, cfg):
        self.native, self.mapper, self.cfg = native, mapper, cfg
        self.stabilizer = Stabilizer(cfg)
        self.reset()

    def reset(self):
        self.stabilizer.clear()
        self.live = self.display = ()
        self.ray = self.empty_ray()
        self.frame = self.display_frame = None
        self.last_received = None
        self.valid = False
        self.persistent = False
        self.paused = self.locked = False
        self.reason = "Waiting for scene"

    @staticmethod
    def empty_ray():
        return dict(segments=[], interactions=0, success=False, termination="NO_SOURCE", hits=[])

    def adopt(self):
        self.display, self.display_frame = self.live, self.frame
        sources = [o for o in self.live if o.type == "SOURCE" and o.direction_valid]
        self.ray = (self.native.trace(self.display, self.mapper.width, self.mapper.height,
                                     self.cfg["physics_scale"])
                    if self.valid and len(sources) == 1 else self.empty_ray())

    def accept(self, scene, now, persistent=False, independent=False):
        self.frame, self.last_received, self.persistent = scene.frame, now, persistent
        try:
            if not scene.valid:
                raise ValueError("Invalid recognition frame")
            models = map_models(scene, self.mapper, self.cfg)
            if independent:
                self.stabilizer.clear()
            self.live = self.stabilizer.update(models, now)
            self.valid = True
            sources = [o for o in self.live if o.type == "SOURCE" and o.direction_valid]
            self.reason = "Scene ready" if len(sources) == 1 else "Need exactly one valid SOURCE"
        except ValueError as error:
            self.stabilizer.clear()
            self.live, self.valid, self.reason = (), False, str(error)
        if not self.locked and not self.paused:
            self.adopt()

    def tick(self, now):
        if self.last_received is None or self.persistent:
            return
        age = now-self.last_received
        if age >= self.cfg["timeout_seconds"]:
            self.stabilizer.clear()
            self.live, self.valid, self.reason = (), False, "Scene timed out"
        else:
            # Silence between complete scenes is not an observed dropout.
            # Only explicitly missing, held tracks use the short dropout TTL.
            expired = self.stabilizer.expire(now)
            if self.valid and age >= self.cfg["dropout_seconds"]:
                self.reason = "Showing last scene (stale)"
            if expired == self.live:
                return
            self.live = expired
        if not self.paused and not self.locked:
            self.adopt()

    def pause(self):
        self.paused = not self.paused
        if not self.paused and not self.locked:
            self.adopt()

    def lock(self, now):
        self.tick(now)
        sources = [o for o in self.live if o.type == "SOURCE" and o.direction_valid]
        fresh = self.persistent or (self.last_received is not None and
                                   now-self.last_received < self.cfg["dropout_seconds"])
        if self.valid and fresh and len(sources) == 1 and not any(o.held for o in self.live):
            # Lock the latest complete scene, even if the display was paused.
            self.adopt()
            self.locked = True
            return True
        return False

    def unlock(self, now):
        self.locked = False
        self.tick(now)
        if not self.paused:
            self.adopt()
