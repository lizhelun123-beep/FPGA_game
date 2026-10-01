"""OpenCV HSV: H=0..179, S/V=0..255. All tunable thresholds live here."""
import copy
import json

DEFAULT = {
    "hsv": {
        "yellow": [[[20, 90, 70], [36, 255, 255]]],
        "blue": [[[90, 85, 45], [130, 255, 255]]],
        "orange": [[[4, 100, 80], [19, 255, 255]]],
        "green": [[[37, 70, 45], [89, 255, 255]]],
        "magenta": [[[135, 65, 60], [179, 255, 255]], [[0, 65, 60], [3, 255, 255]]],
        "black": [[[0, 0, 0], [179, 255, 65]]],
        "white": [[[0, 0, 175], [179, 65, 255]]],
    },
    "stages": {name: True for name in (
        "hsv", "segmentation", "open", "close", "candidates", "area_filter",
        "markers", "geometry", "source_outline", "draw")},
    "morphology": {"kernel": 3, "open_iterations": 1, "close_iterations": 1},
    "candidate": {"min_area": 200, "max_frame_fraction": 0.85},
    # WALL dark-gray support is independent from strict black marker thresholds.
    "wall": {"hsv": [[[0, 0, 0], [179, 110, 120]]],
             "surround_fraction": 0.15, "min_surround_pixels": 20},
    "source_outline": {"padding_fraction": 0.20, "max_area_growth": 1.80,
                       "min_hole_overlap": 0.85},
    "display": {"show_rejected": False},
    "geometry": {
        "MIRROR": {"aspect": [2.2, 6.5], "min_fill": 0.65},
        "PORTAL_A": {"aspect": [2.0, 5.5], "min_fill": 0.60},
        "PORTAL_B": {"aspect": [2.0, 5.5], "min_fill": 0.60},
        "TARGET": {"aspect": [1.0, 1.65], "min_circularity": 0.60},
        "SOURCE": {"aspect": [1.0, 2.5], "min_fill": 0.30},
        "WALL": {"aspect": [2.2, 6.5], "min_fill": 0.70, "min_color_fill": 0.80,
                 "max_colored_overlap": 0.10, "min_surround_contrast": 12},
    },
    "marker": {
        "min_area": 9, "area_fraction": [0.002, 0.22],
        "min_circularity": 0.50, "max_aspect": 1.65,
        "solid_min_fill": 0.78, "solid_max_hole_fraction": 0.08,
        "ring_hole_fraction": [0.12, 0.72], "ring_min_fill": 0.22,
        "ring_center_tolerance": 0.25, "ring_center_color_fraction": 0.55,
        "end_min_projection": 0.19, "end_max_projection": 0.49,
        "max_transverse": 0.27, "target_center_tolerance": 0.18,
        "target_black_hole_fraction": [0.05, 1.0],
    },
    "confidence": {"base": 0.40, "color_weight": 0.20,
                   "geometry_weight": 0.15, "marker_weight": 0.25,
                   "source_triangle_bonus": 0.05, "unverified_cap": 0.65},
    "calibration": {"percentiles": [1, 5, 50, 95, 99],
                    "low_percentile": 1, "high_percentile": 99,
                    "h_padding": 2, "sv_padding": 10, "max_samples_per_color": 250000,
                    "seed": 7},
}


def load_config(path=None):
    config = copy.deepcopy(DEFAULT)
    if path:
        def merge(dst, src):
            for key, value in src.items():
                if key not in dst:
                    raise ValueError(f"Unknown configuration key: {key}")
                if isinstance(value, dict) and isinstance(dst[key], dict):
                    merge(dst[key], value)
                else:
                    dst[key] = value
        with open(path, encoding="utf-8-sig") as stream:
            merge(config, json.load(stream))
    for color, ranges in {**config["hsv"], "wall": config["wall"]["hsv"]}.items():
        if not ranges:
            raise ValueError(f"Empty HSV ranges: {color}")
        for low, high in ranges:
            if len(low) != 3 or len(high) != 3 or any(
                not 0 <= a <= b <= limit for a, b, limit in zip(low, high, (179, 255, 255))
            ):
                raise ValueError(f"Invalid HSV range: {color}")
    k = config["morphology"]["kernel"]
    if not isinstance(k, int) or k < 1 or k % 2 == 0:
        raise ValueError("morphology.kernel must be a positive odd integer")
    return config
