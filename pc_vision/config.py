"""OpenCV HSV: H=0..179, S/V=0..255. All tunable thresholds live here."""
import copy
import json

DEFAULT = {
    "hsv": {
        "yellow": [[[18, 85, 85], [36, 255, 255]]],
        "blue": [[[60, 85, 45], [130, 255, 255]],
                 [[60, 5, 45], [130, 84, 120]],
                 [[14, 20, 40], [45, 100, 60]]],
        "orange": [[[15, 100, 80], [21, 255, 255]]],
        "green": [[[37, 70, 45], [89, 255, 255]]],
        "magenta": [[[10, 120, 65], [19, 255, 255]]],
        "black": [[[0, 0, 0], [179, 255, 65]]],
        "white": [[[0, 0, 70], [60, 100, 255]]],
    },
    "stages": {name: True for name in (
        "hsv", "segmentation", "open", "close", "candidates", "area_filter",
        "markers", "geometry", "source_outline", "draw")},
    "morphology": {"kernel": 3, "open_iterations": 1, "close_iterations": 1},
    "candidate": {"min_area": 200, "max_frame_fraction": 0.85},
    # WALL dark-gray support is independent from strict black marker thresholds.
    "wall": {"hsv": [[[0, 0, 0], [179, 255, 60]]],
             "surround_fraction": 0.15, "min_surround_pixels": 20,
             "local_window": 129, "local_delta": 10},
    "wall_marker": {
        "s_max": 180, "v_min": 65, "local_window": 31, "local_delta": 8,
        "min_area": 10, "max_area": 900, "aspect": [1.3, 8.0],
        "min_fill": 0.30, "max_major_ratio": 2.0, "max_minor_ratio": 2.5,
        "min_parallel_dot": 0.80, "max_perpendicular_dot": 0.30,
        "spacing_ratio": [1.4, 3.0], "dark_v_max": 120,
        "min_dark_fraction": 0.70, "longitudinal_fraction": 0.32,
        "transverse_fraction": 0.38,
    },
    "black_marker": {"local_window": 15, "local_delta": 20},
    "source_outline": {"padding_fraction": 0.20, "max_area_growth": 1.80,
                       "min_hole_overlap": 0.85},
    "display": {"show_rejected": False},
    "geometry": {
        "MIRROR": {"aspect": [2.2, 6.5], "min_fill": 0.65},
        "PORTAL_A": {"aspect": [1.8, 5.5], "min_fill": 0.60,
                     "min_area": 1800},
        "PORTAL_B": {"aspect": [1.8, 5.5], "min_fill": 0.60,
                     "min_area": 1800},
        "TARGET": {"aspect": [1.0, 1.65], "min_circularity": 0.60},
        "SOURCE": {"aspect": [1.0, 2.5], "min_fill": 0.30,
                   "min_circularity": 0.50},
        "WALL": {"aspect": [2.0, 6.5], "min_fill": 0.70, "min_color_fill": 0.80,
                 "max_colored_overlap": 0.10, "min_surround_contrast": 12,
                 "min_area": 2000, "max_frame_fraction": 0.05},
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
        "endpoint_offset": 0.44, "endpoint_offset_fallbacks": [0.37, 0.30, 0.25],
        "endpoint_radius": 0.30,
        "solid_sample_min": 0.45, "ring_sample_min": 0.08,
        "ring_sample_body_min": 0.30, "ring_sample_annulus_margin": 0.05,
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
    for section, key in (("wall", "local_window"),
                         ("wall_marker", "local_window"),
                         ("black_marker", "local_window")):
        window = config[section][key]
        if not isinstance(window, int) or window < 3 or window % 2 == 0:
            raise ValueError(f"{section}.{key} must be an odd integer >= 3")
    return config
