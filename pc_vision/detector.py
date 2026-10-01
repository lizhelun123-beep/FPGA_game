"""Color-first detector. No vertex-count gate, neural network, or tracking."""
from dataclasses import asdict, dataclass, field
import math

import cv2
import numpy as np

from body_refinement import source_outline, wall_contrast


@dataclass
class Detection:
    type: str
    center_x: float
    center_y: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    angle: float
    confidence: float

    def to_dict(self):
        return asdict(self)


@dataclass
class Result:
    detections: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    masks: dict = field(default_factory=dict)
    segmentation_stats: dict = field(default_factory=dict)
    candidate_mask: np.ndarray = None
    marker_mask: np.ndarray = None
    final: np.ndarray = None
    hsv: np.ndarray = None
    status: str = "ok"


def contours(mask, mode=cv2.RETR_EXTERNAL):
    return cv2.findContours(mask, mode, cv2.CHAIN_APPROX_SIMPLE)


def shape_features(contour):
    area = float(cv2.contourArea(contour))
    perimeter = cv2.arcLength(contour, True)
    (cx, cy), (rw, rh), angle = cv2.minAreaRect(contour)
    if rw < rh:
        rw, rh, angle = rh, rw, angle + 90
    angle = (angle + 90) % 180 - 90
    moments = cv2.moments(contour)
    if moments["m00"]:
        cx, cy = moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]
    x, y, w, h = cv2.boundingRect(contour)
    return dict(bbox=[x, y, w, h], center=[float(cx), float(cy)], area=area,
                width=w, height=h, rotated_width=float(rw), rotated_height=float(rh),
                aspect_ratio=float(rw / max(rh, 1)),
                circularity=float(min(1, 4 * math.pi * area / max(perimeter ** 2, 1))),
                fill=float(min(1, area / max(rw * rh, 1))), angle=float(angle))


class Detector:
    TYPES = {"yellow": "MIRROR", "blue": "PORTAL_A", "orange": "PORTAL_B",
             "green": "TARGET", "magenta": "SOURCE", "wall": "WALL"}

    def __init__(self, config):
        self.cfg = config

    def segment(self, hsv):
        masks = {}
        k = self.cfg["morphology"]["kernel"]
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        ranges_by_color = {**self.cfg["hsv"], "wall": self.cfg["wall"]["hsv"]}
        for color, ranges in ranges_by_color.items():
            mask = np.zeros(hsv.shape[:2], np.uint8)
            for lo, hi in ranges:
                mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            for name, op in (("open", cv2.MORPH_OPEN), ("close", cv2.MORPH_CLOSE)):
                if self.cfg["stages"][name]:
                    mask = cv2.morphologyEx(mask, op, kernel,
                                           iterations=self.cfg["morphology"][name + "_iterations"])
            masks[color] = mask
        return masks

    def marker_regions(self, mask, object_area):
        """RETR_CCOMP preserves ring holes; evaluate all enclosed components."""
        found, hierarchy = contours(mask, cv2.RETR_CCOMP)
        if hierarchy is None:
            return []
        cfg = self.cfg["marker"]
        markers = []
        for i, contour in enumerate(found):
            if hierarchy[0, i, 3] != -1:
                continue
            f = shape_features(contour)
            fraction = f["area"] / max(object_area, 1)
            if f["area"] < cfg["min_area"] or not cfg["area_fraction"][0] <= fraction <= cfg["area_fraction"][1]:
                continue
            if f["circularity"] < cfg["min_circularity"] or f["aspect_ratio"] > cfg["max_aspect"]:
                continue
            outer = np.zeros_like(mask)
            cv2.drawContours(outer, [contour], -1, 255, -1)
            fill = cv2.countNonZero(mask & outer) / max(cv2.countNonZero(outer), 1)
            holes = []
            child = hierarchy[0, i, 2]
            while child != -1:
                holes.append(found[child])
                child = hierarchy[0, child, 0]
            holes.sort(key=cv2.contourArea, reverse=True)
            hole_fraction = sum(cv2.contourArea(h) for h in holes) / max(f["area"], 1)
            kind = "unknown"
            hole_mask = np.zeros_like(mask)
            if hole_fraction <= cfg["solid_max_hole_fraction"] and fill >= cfg["solid_min_fill"]:
                kind = "solid"
            elif holes and cfg["ring_hole_fraction"][0] <= hole_fraction <= cfg["ring_hole_fraction"][1] and fill >= cfg["ring_min_fill"]:
                hf = shape_features(holes[0])
                distance = np.linalg.norm(np.array(hf["center"]) - f["center"])
                if hf["circularity"] >= cfg["min_circularity"] and distance <= cfg["ring_center_tolerance"] * f["rotated_height"]:
                    kind = "ring"
                    cv2.drawContours(hole_mask, [holes[0]], -1, 255, -1)
                    # Remove the foreground boundary included by OpenCV hole contours.
                    hole_mask[mask != 0] = 0
            if kind != "unknown":
                markers.append(dict(kind=kind, features=f, contour=contour, hole=hole_mask))
        return markers

    def verify_markers(self, type_name, features, interior, masks):
        if type_name in ("SOURCE", "WALL"):
            return True, [], "not_required"
        cfg = self.cfg["marker"]
        color = "black" if type_name == "MIRROR" else "white"
        regions = self.marker_regions(masks[color] & interior, features["area"])
        center = np.array(features["center"])
        angle = math.radians(features["angle"])
        axis = np.array([math.cos(angle), math.sin(angle)])
        normal = np.array([-axis[1], axis[0]])
        if type_name == "TARGET":
            for ring in regions:
                if ring["kind"] != "ring":
                    continue
                rc = np.array(ring["features"]["center"])
                if np.linalg.norm(rc - center) > cfg["target_center_tolerance"] * features["rotated_height"]:
                    continue
                blacks = self.marker_regions(masks["black"] & ring["hole"], features["area"])
                for black in blacks:
                    bc = np.array(black["features"]["center"])
                    ratio = black["features"]["area"] / max(cv2.countNonZero(ring["hole"]), 1)
                    if black["kind"] == "solid" and cfg["target_black_hole_fraction"][0] <= ratio <= cfg["target_black_hole_fraction"][1] and np.linalg.norm(bc - rc) <= cfg["ring_center_tolerance"] * ring["features"]["rotated_height"]:
                        return True, [ring, black], "white_ring+black_center"
            if not any(m["kind"] == "ring" for m in regions):
                return False, regions, "no_white_ring"
            return False, regions, "ring_center_or_black_failed"
        ends = {-1: [], 1: []}
        for marker in regions:
            offset = np.array(marker["features"]["center"]) - center
            longitudinal = float(offset @ axis) / max(features["rotated_width"], 1)
            transverse = abs(float(offset @ normal)) / max(features["rotated_height"], 1)
            if cfg["end_min_projection"] <= abs(longitudinal) <= cfg["end_max_projection"] and transverse <= cfg["max_transverse"]:
                ends[-1 if longitudinal < 0 else 1].append(marker)
        ring_color_failed = False
        for left in ends[-1]:
            for right in ends[1]:
                if type_name == "MIRROR" and left["kind"] == right["kind"] == "solid":
                    return True, [left, right], "two_black_end_disks"
                if type_name.startswith("PORTAL") and {left["kind"], right["kind"]} == {"solid", "ring"}:
                    ring = left if left["kind"] == "ring" else right
                    body_color = "blue" if type_name == "PORTAL_A" else "orange"
                    ratio = cv2.countNonZero(masks[body_color] & ring["hole"]) / max(cv2.countNonZero(ring["hole"]), 1)
                    if ratio >= cfg["ring_center_color_fraction"]:
                        return True, [left, right], "white_disk+body_color_ring"
                    ring_color_failed = True
        if ring_color_failed:
            return False, regions, "ring_inner_color_failed"
        if not regions:
            return False, regions, f"no_{color}_round_markers"
        if not ends[-1] or not ends[1]:
            return False, regions, "marker_end_position_failed"
        return False, regions, "marker_disk_ring_pair_failed"

    def process(self, bgr):
        if bgr is None or bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("Expected a nonempty BGR image")
        result = Result(final=bgr.copy(), candidate_mask=np.zeros(bgr.shape[:2], np.uint8),
                        marker_mask=np.zeros(bgr.shape[:2], np.uint8))
        stages = self.cfg["stages"]
        # Disabled prerequisite stops dependent stages explicitly, never bypasses HSV with RGB.
        if not stages["hsv"]:
            result.status = "hsv disabled; dependent stages skipped"
            return result
        result.hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        if not stages["segmentation"]:
            result.status = "segmentation disabled; dependent stages skipped"
            return result
        result.masks = self.segment(result.hsv)
        result.segmentation_stats = {
            color: dict(mask_pixels=cv2.countNonZero(mask), contours=0,
                        zero_area=0, too_small=0, too_large=0, evaluated=0)
            for color, mask in result.masks.items()
        }
        if not stages["candidates"]:
            result.status = "candidates disabled; dependent stages skipped"
            return result
        # Confirmed colored objects suppress duplicate WALL classifications.
        # Rejected color candidates must never punch holes into a wall mask.
        occupied = np.zeros(bgr.shape[:2], np.uint8)
        for color, type_name in self.TYPES.items():
            source_mask = result.masks[color].copy()
            found, _ = contours(source_mask)
            stats = result.segmentation_stats[color]
            stats["contours"] = len(found)
            for contour in found:
                f = shape_features(contour)
                if f["area"] <= 0:
                    stats["zero_area"] += 1
                    continue
                body_bbox = f["bbox"]
                outline_used = False
                if type_name == "SOURCE" and stages["source_outline"] and f["area"] >= self.cfg["candidate"]["min_area"]:
                    contour, outline_used = source_outline(contour, result.masks["wall"], self.cfg["source_outline"])
                    if outline_used:
                        f = shape_features(contour)
                if stages["area_filter"]:
                    if f["area"] < self.cfg["candidate"]["min_area"]:
                        stats["too_small"] += 1
                        continue
                    if f["area"] > bgr.shape[0] * bgr.shape[1] * self.cfg["candidate"]["max_frame_fraction"]:
                        stats["too_large"] += 1
                        continue
                stats["evaluated"] += 1
                x, y, w, h = f["bbox"]
                # Process markers only inside the silhouette, not the rectangular ROI background.
                local_contour = contour - np.array([[[x, y]]], dtype=np.int32)
                interior = np.zeros((h, w), np.uint8)
                cv2.drawContours(interior, [local_contour], -1, 255, -1)
                colored_overlap = (cv2.countNonZero(occupied[y:y+h, x:x+w] & interior)
                                   / max(cv2.countNonZero(interior), 1)) if color == "wall" else 0.0
                result.candidate_mask[y:y+h, x:x+w] |= interior
                local_masks = {name: mask[y:y+h, x:x+w] for name, mask in result.masks.items()}
                lf = dict(f, center=[f["center"][0] - x, f["center"][1] - y])
                if stages["markers"]:
                    if type_name not in ("SOURCE", "WALL"):
                        marker_colors = local_masks["black"] if type_name == "MIRROR" else local_masks["white"]
                        if type_name == "TARGET":
                            marker_colors = marker_colors | local_masks["black"]
                        result.marker_mask[y:y+h, x:x+w] |= marker_colors & interior
                    marker_ok, markers, note = self.verify_markers(type_name, lf, interior, local_masks)
                else:
                    marker_ok, markers, note = True, [], "disabled/unverified"
                g = self.cfg["geometry"][type_name]
                color_fill = cv2.countNonZero(local_masks[color] & interior) / max(cv2.countNonZero(interior), 1)
                geometry_failures = []
                if not g["aspect"][0] <= f["aspect_ratio"] <= g["aspect"][1]:
                    geometry_failures.append("aspect_ratio")
                for name, value, minimum in (("fill", f["fill"], g.get("min_fill", 0)),
                                             ("circularity", f["circularity"], g.get("min_circularity", 0)),
                                             ("color_fill", color_fill, g.get("min_color_fill", 0))):
                    if value < minimum:
                        geometry_failures.append(name)
                geometry_ok = not geometry_failures
                surround_contrast = None
                if type_name == "WALL" and geometry_ok:
                    surround_contrast = wall_contrast(result.hsv, contour, self.cfg["wall"])
                    if surround_contrast is None or surround_contrast < g["min_surround_contrast"]:
                        geometry_failures.append("surround_contrast")
                        geometry_ok = False
                reasons = []
                if colored_overlap > g.get("max_colored_overlap", 1):
                    reasons.append("colored_overlap")
                if not marker_ok:
                    reasons.append(note)
                if stages["geometry"]:
                    reasons.extend(geometry_failures)
                accepted = not reasons
                if accepted and color != "wall":
                    occupied[y:y+h, x:x+w] |= interior
                candidate = dict(type=type_name, **f, color_fill=color_fill,
                                 body_bbox=body_bbox, outline_used=outline_used,
                                 surround_contrast=surround_contrast,
                                 colored_overlap=colored_overlap, rejection_reasons=reasons,
                                 markers=[dict(kind=m["kind"],
                                               center=[m["features"]["center"][0]+x,
                                                       m["features"]["center"][1]+y],
                                               area=m["features"]["area"],
                                               circularity=m["features"]["circularity"])
                                          for m in markers],
                                 marker_ok=marker_ok if stages["markers"] else None,
                                 marker_result=note, geometry_ok=geometry_ok, accepted=accepted)
                result.candidates.append(candidate)
                draw_candidate = stages["draw"] and (accepted or self.cfg["display"]["show_rejected"])
                for marker in markers:
                    global_contour = marker["contour"] + np.array([[[x, y]]], np.int32)
                    cv2.drawContours(result.marker_mask, [global_contour], -1, 255, 1)
                    if draw_candidate:
                        cv2.drawContours(result.final, [global_contour], -1, (255, 255, 0), 1)
                        mx, my = marker["features"]["center"]
                        cv2.putText(result.final, marker["kind"], (int(mx+x), int(my+y)), cv2.FONT_HERSHEY_SIMPLEX, .35, (255, 255, 0), 1)
                if draw_candidate:
                    cv2.rectangle(result.final, (x, y), (x+w-1, y+h-1), (0, 200, 0) if accepted else (0, 0, 200), 1)
                    detail = note if accepted else type_name + ":" + ",".join(reasons)
                    cv2.putText(result.final, detail, (x, min(bgr.shape[0]-5, y+h+12)), cv2.FONT_HERSHEY_SIMPLEX, .32, (255, 255, 255), 1)
                if not accepted:
                    continue
                weights = self.cfg["confidence"]
                score = weights["base"] + weights["color_weight"] * color_fill
                score += weights["geometry_weight"] * float(geometry_ok and stages["geometry"])
                score += weights["marker_weight"] * float(marker_ok and stages["markers"] and type_name not in ("SOURCE", "WALL"))
                # Triangle area filling is a soft cue, never an exact-three-vertices gate.
                if type_name == "SOURCE":
                    triangle_area, _ = cv2.minEnclosingTriangle(contour)
                    score += weights["source_triangle_bonus"] * min(1, f["area"] / max(triangle_area, 1))
                if not stages["markers"] or not stages["geometry"]:
                    score = min(score, weights["unverified_cap"])
                cx, cy = f["center"]
                angle = f["angle"]
                if type_name.startswith("PORTAL") and len(markers) == 2:
                    disk = next(m for m in markers if m["kind"] == "solid")
                    ring = next(m for m in markers if m["kind"] == "ring")
                    dx, dy = np.array(ring["features"]["center"]) - disk["features"]["center"]
                    angle = math.degrees(math.atan2(dy, dx))
                elif type_name == "TARGET":
                    angle = 0.0
                detection = Detection(type_name, cx, cy, x, y, w, h, angle, round(min(score, 1), 3))
                result.detections.append(detection)
                if stages["draw"]:
                    cv2.circle(result.final, (round(cx), round(cy)), 3, (0, 0, 255), -1)
                    cv2.putText(result.final, f"{type_name} {detection.confidence:.2f}", (x, max(14, y-5)), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
        return result
