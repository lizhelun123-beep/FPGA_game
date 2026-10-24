"""Color-first detector. No vertex-count gate, neural network, or tracking."""
from dataclasses import asdict, dataclass, field
import math

import cv2
import numpy as np

try:
    from .body_refinement import source_marker_geometry, source_outline, wall_contrast
except ImportError:  # Keep direct `python pc_vision/app.py` execution working.
    from body_refinement import source_marker_geometry, source_outline, wall_contrast


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
    found = cv2.findContours(mask, mode, cv2.CHAIN_APPROX_SIMPLE)
    # OpenCV 3 returns image, contours, hierarchy; OpenCV 4 returns two values.
    return found[-2], found[-1]


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


def bbox_iou(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    overlap_w = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    overlap_h = max(0, min(ay + ah, by + bh) - max(ay, by))
    intersection = overlap_w * overlap_h
    return intersection / max(aw * ah + bw * bh - intersection, 1)


class Detector:
    TYPES = {"yellow": "MIRROR", "blue": "PORTAL_A", "orange": "PORTAL_B",
             "green": "TARGET", "magenta": "SOURCE", "wall": "WALL"}

    def __init__(self, config, enabled_types=None):
        self.cfg = config
        known = set(self.TYPES.values())
        self.enabled_types = known if enabled_types is None else set(enabled_types)
        unknown = self.enabled_types - known
        if unknown:
            raise ValueError("Unknown detection types: " + ", ".join(sorted(unknown)))

    def segment(self, hsv):
        masks = {}
        k = self.cfg["morphology"]["kernel"]
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        ranges_by_color = {**self.cfg["hsv"], "wall": self.cfg["wall"]["hsv"]}
        for color, ranges in ranges_by_color.items():
            mask = np.zeros(hsv.shape[:2], np.uint8)
            for lo, hi in ranges:
                mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            if color == "wall":
                cfg = self.cfg["wall"]
                local_mean = cv2.boxFilter(
                    hsv[:, :, 2], cv2.CV_32F,
                    (cfg["local_window"], cfg["local_window"]), normalize=True
                )
                adaptive = hsv[:, :, 2].astype(np.float32) + cfg["local_delta"] <= local_mean
                mask &= adaptive.astype(np.uint8) * 255
            elif color == "black":
                cfg = self.cfg["black_marker"]
                local_mean = cv2.boxFilter(
                    hsv[:, :, 2], cv2.CV_32F,
                    (cfg["local_window"], cfg["local_window"]), normalize=True
                )
                adaptive = hsv[:, :, 2].astype(np.float32) + cfg["local_delta"] <= local_mean
                mask |= adaptive.astype(np.uint8) * 255
            raw_marker = mask.copy() if color in ("black", "white") else None
            for name, op in (("open", cv2.MORPH_OPEN), ("close", cv2.MORPH_CLOSE)):
                if self.cfg["stages"][name]:
                    mask = cv2.morphologyEx(mask, op, kernel,
                                           iterations=self.cfg["morphology"][name + "_iterations"])
            if raw_marker is not None:
                mask = raw_marker
            masks[color] = mask
        marker_cfg = self.cfg["wall_marker"]
        local_mean = cv2.boxFilter(
            hsv[:, :, 2], cv2.CV_32F,
            (marker_cfg["local_window"], marker_cfg["local_window"]), normalize=True
        )
        wall_marker = ((hsv[:, :, 1] <= marker_cfg["s_max"]) &
                       (hsv[:, :, 2] >= marker_cfg["v_min"]) &
                       (hsv[:, :, 2].astype(np.float32) >=
                        local_mean + marker_cfg["local_delta"])).astype(np.uint8) * 255
        if self.cfg["stages"]["open"]:
            wall_marker = cv2.morphologyEx(wall_marker, cv2.MORPH_OPEN, kernel)
        if self.cfg["stages"]["close"]:
            wall_marker = cv2.morphologyEx(wall_marker, cv2.MORPH_CLOSE, kernel)
        masks["wall_marker"] = wall_marker
        return masks

    def wall_marker_pairs(self, hsv, marker_mask):
        """Pair transverse white bars and validate the dark corridor between them."""
        cfg = self.cfg["wall_marker"]
        count, labels, stats, centers = cv2.connectedComponentsWithStats(
            (marker_mask != 0).astype(np.uint8), 8
        )
        markers = []
        for index in range(1, count):
            area = int(stats[index, cv2.CC_STAT_AREA])
            if not cfg["min_area"] <= area <= cfg["max_area"]:
                continue
            yy, xx = np.where(labels == index)
            centered = np.vstack((xx - xx.mean(), yy - yy.mean()))
            eigenvalues, eigenvectors = np.linalg.eigh(np.cov(centered, bias=True))
            if eigenvalues[0] < 0.05:
                continue
            major = math.sqrt(12 * eigenvalues[1]) + 1
            minor = math.sqrt(12 * eigenvalues[0]) + 1
            aspect = major / minor
            fill = area / max(major * minor, 1)
            if not cfg["aspect"][0] <= aspect <= cfg["aspect"][1] or fill < cfg["min_fill"]:
                continue
            markers.append(dict(center=np.array(centers[index], dtype=float),
                                major=major, minor=minor,
                                axis=eigenvectors[:, 1], area=area, label=index))

        yy, xx = np.indices(marker_mask.shape)
        proposals = []
        for first_index, first in enumerate(markers):
            for second in markers[first_index + 1:]:
                if (max(first["major"], second["major"]) /
                        min(first["major"], second["major"]) > cfg["max_major_ratio"] or
                        max(first["minor"], second["minor"]) /
                        min(first["minor"], second["minor"]) > cfg["max_minor_ratio"]):
                    continue
                delta = second["center"] - first["center"]
                distance = float(np.linalg.norm(delta))
                if distance <= 0:
                    continue
                axis = delta / distance
                average_major = (first["major"] + second["major"]) * 0.5
                average_minor = (first["minor"] + second["minor"]) * 0.5
                spacing = distance / max(average_major, 1)
                if not cfg["spacing_ratio"][0] <= spacing <= cfg["spacing_ratio"][1]:
                    continue
                if abs(float(first["axis"] @ second["axis"])) < cfg["min_parallel_dot"]:
                    continue
                if (abs(float(first["axis"] @ axis)) > cfg["max_perpendicular_dot"] or
                        abs(float(second["axis"] @ axis)) > cfg["max_perpendicular_dot"]):
                    continue
                center = (first["center"] + second["center"]) * 0.5
                longitudinal = (xx - center[0]) * axis[0] + (yy - center[1]) * axis[1]
                transverse = abs(-(xx - center[0]) * axis[1] +
                                 (yy - center[1]) * axis[0])
                corridor = ((abs(longitudinal) <= distance * cfg["longitudinal_fraction"]) &
                            (transverse <= average_major * cfg["transverse_fraction"]))
                corridor_values = hsv[:, :, 2][corridor]
                if corridor_values.size < cfg["min_area"]:
                    continue
                dark_fraction = float(np.mean(corridor_values <= cfg["dark_v_max"]))
                if dark_fraction < cfg["min_dark_fraction"]:
                    continue
                normal = np.array([-axis[1], axis[0]])
                half_long = distance * 0.5 + average_minor * 0.75
                half_short = average_major * 0.5 + average_minor * 0.5
                corners = np.array([
                    center + sx * axis * half_long + sy * normal * half_short
                    for sx in (-1, 1) for sy in (-1, 1)
                ])
                x0 = max(0, int(math.floor(corners[:, 0].min())))
                y0 = max(0, int(math.floor(corners[:, 1].min())))
                x1 = min(marker_mask.shape[1], int(math.ceil(corners[:, 0].max())) + 1)
                y1 = min(marker_mask.shape[0], int(math.ceil(corners[:, 1].max())) + 1)
                width, height = x1 - x0, y1 - y0
                area = 4 * half_long * half_short
                wall_geometry = self.cfg["geometry"]["WALL"]
                if (area < wall_geometry["min_area"] or
                        area > marker_mask.size * wall_geometry["max_frame_fraction"]):
                    continue
                angle = math.degrees(math.atan2(axis[1], axis[0]))
                if angle >= 90:
                    angle -= 180
                if angle < -90:
                    angle += 180
                proposals.append(dict(
                    type="WALL", center=center, bbox=[x0, y0, width, height],
                    area=area, width=width, height=height,
                    rotated_width=2 * half_long, rotated_height=2 * half_short,
                    aspect_ratio=half_long / max(half_short, 1), circularity=0.0,
                    fill=dark_fraction, angle=angle, color_fill=dark_fraction,
                    body_bbox=[x0, y0, width, height], outline_used=False,
                    surround_contrast=None, colored_overlap=0.0,
                    rejection_reasons=[], marker_ok=True,
                    marker_result="two_white_transverse_bars+dark_center",
                    geometry_ok=True, accepted=True, markers=(first, second),
                ))
        proposals.sort(key=lambda item: item["area"], reverse=True)
        kept = []
        for proposal in proposals:
            x, y, w, h = proposal["bbox"]
            if any((max(0, min(x+w, k["bbox"][0]+k["bbox"][2]) - max(x, k["bbox"][0])) *
                    max(0, min(y+h, k["bbox"][1]+k["bbox"][3]) - max(y, k["bbox"][1]))) /
                   max(w*h + k["bbox"][2]*k["bbox"][3], 1) > 0.35 for k in kept):
                continue
            kept.append(proposal)
        return kept

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

    def sampled_portal_markers(self, type_name, features, masks):
        """Fallback for thin/incomplete rings using the same endpoint ratios as PS."""
        cfg = self.cfg["marker"]
        angle = math.radians(features["angle"])
        axis = np.array([math.cos(angle), math.sin(angle)])
        center = np.array(features["center"], dtype=float)
        radius = max(2.0, features["rotated_height"] * cfg["endpoint_radius"])
        body_color = "blue" if type_name == "PORTAL_A" else "orange"
        yy, xx = np.ogrid[:masks["white"].shape[0], :masks["white"].shape[1]]

        def marker(kind, point):
            contour = cv2.ellipse2Poly(
                tuple(np.rint(point).astype(int)),
                (max(2, round(radius)), max(2, round(radius))), 0, 0, 360, 30
            ).reshape(-1, 1, 2)
            marker_features = shape_features(contour)
            marker_features["center"] = point.tolist()
            return dict(kind=kind, features=marker_features, contour=contour,
                        hole=np.zeros_like(masks["white"]))

        pairings = []
        offsets = [cfg["endpoint_offset"], *cfg["endpoint_offset_fallbacks"]]
        for offset_fraction in offsets:
            offset = features["rotated_width"] * offset_fraction
            samples = []
            for sign in (-1, 1):
                point = center + sign * axis * offset
                distance_sq = (xx - point[0]) ** 2 + (yy - point[1]) ** 2
                inner = distance_sq <= radius * radius * 0.16
                annulus = ((distance_sq >= radius * radius * 0.36) &
                           (distance_sq <= radius * radius))
                inner_total = max(int(np.count_nonzero(inner)), 1)
                annulus_total = max(int(np.count_nonzero(annulus)), 1)
                white_inner = np.count_nonzero((masks["white"] != 0) & inner) / inner_total
                white_annulus = np.count_nonzero((masks["white"] != 0) & annulus) / annulus_total
                body_inner = np.count_nonzero((masks[body_color] != 0) & inner) / inner_total
                samples.append(dict(point=point, solid=white_inner,
                                    ring_white=white_annulus, ring_body=body_inner))
            for solid_index, ring_index in ((0, 1), (1, 0)):
                solid = samples[solid_index]
                ring = samples[ring_index]
                if (solid["solid"] >= cfg["solid_sample_min"] and
                        ring["ring_white"] >= cfg["ring_sample_min"] and
                        ring["ring_white"] >= (ring["solid"] +
                                               cfg["ring_sample_annulus_margin"]) and
                        ring["ring_body"] >= cfg["ring_sample_body_min"]):
                    score = (2 * solid["solid"] + ring["ring_white"] +
                             ring["ring_body"] - solid["ring_body"] - ring["solid"])
                    pairings.append((score, solid_index, ring_index, samples))
        if not pairings:
            return False, [], "sampled_endpoint_pair_failed"
        _, solid_index, ring_index, samples = max(pairings, key=lambda item: item[0])
        return True, [marker("solid", samples[solid_index]["point"]),
                      marker("ring", samples[ring_index]["point"])], \
            "sampled_white_disk+body_color_ring"

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
        if type_name.startswith("PORTAL"):
            sampled_ok, sampled_markers, sampled_note = self.sampled_portal_markers(
                type_name, features, masks
            )
            if sampled_ok:
                return True, sampled_markers, sampled_note
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
        marker_walls = []
        if ("WALL" in self.enabled_types and stages["markers"] and
                stages["geometry"]):
            marker_walls = self.wall_marker_pairs(
                result.hsv, result.masks["wall_marker"]
            )
        for color, type_name in self.TYPES.items():
            if type_name not in self.enabled_types:
                continue
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
                marker_geometry = None
                if type_name == "SOURCE":
                    marker_geometry = source_marker_geometry(
                        contour, result.masks["white"], result.masks["black"],
                        self.cfg["source_outline"]
                    )
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
                if f["area"] < g.get("min_area", 0):
                    geometry_failures.append("class_min_area")
                if f["area"] > bgr.shape[0] * bgr.shape[1] * g.get(
                        "max_frame_fraction", 1):
                    geometry_failures.append("class_max_area")
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
                if any(bbox_iou(f["bbox"], wall["bbox"]) >= 0.50
                       for wall in marker_walls):
                    reasons.append("suppressed_by_wall_marker")
                if not marker_ok:
                    reasons.append(note)
                if stages["geometry"]:
                    reasons.extend(geometry_failures)
                accepted = not reasons
                if accepted and color != "wall":
                    occupied[y:y+h, x:x+w] |= interior
                candidate = dict(type=type_name, **f, color_fill=color_fill,
                                 body_bbox=body_bbox, outline_used=outline_used,
                                 marker_geometry=marker_geometry,
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
                if marker_geometry is not None:
                    cx, cy = marker_geometry["center"]
                    detection_bbox = marker_geometry["bbox"]
                else:
                    cx, cy = f["center"]
                    detection_bbox = (x, y, w, h)
                angle = f["angle"]
                if type_name.startswith("PORTAL") and len(markers) == 2:
                    disk = next(m for m in markers if m["kind"] == "solid")
                    ring = next(m for m in markers if m["kind"] == "ring")
                    dx, dy = np.array(ring["features"]["center"]) - disk["features"]["center"]
                    angle = math.degrees(math.atan2(dy, dx))
                elif type_name == "TARGET":
                    angle = 0.0
                detection = Detection(type_name, cx, cy, *detection_bbox,
                                      angle, round(min(score, 1), 3))
                result.detections.append(detection)
                if stages["draw"]:
                    cv2.circle(result.final, (round(cx), round(cy)), 3, (0, 0, 255), -1)
                    cv2.putText(result.final, f"{type_name} {detection.confidence:.2f}", (x, max(14, y-5)), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
        for wall in marker_walls:
            x, y, w, h = wall["bbox"]
            first, second = wall.pop("markers")
            for marker in (first, second):
                center = marker["center"]
                extent = marker["axis"] * marker["major"] * 0.5
                cv2.line(result.marker_mask,
                         tuple(np.rint(center - extent).astype(int)),
                         tuple(np.rint(center + extent).astype(int)), 255,
                         max(1, round(marker["minor"])))
            result.candidate_mask[y:y+h, x:x+w] = 255
            wall["center"] = wall["center"].tolist()
            result.candidates.append(wall)
            cx, cy = wall["center"]
            detection = Detection(
                "WALL", float(cx), float(cy), x, y, w, h,
                float(wall["angle"]), 1.0,
            )
            result.detections.append(detection)
            if stages["draw"]:
                cv2.rectangle(result.final, (x, y), (x+w-1, y+h-1),
                              (0, 200, 0), 1)
                cv2.circle(result.final, (round(cx), round(cy)), 3,
                           (0, 0, 255), -1)
                cv2.putText(result.final, "WALL 1.00", (x, max(14, y-5)),
                            cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
        return result
