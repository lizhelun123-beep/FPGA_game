"""HSV and circular-geometry detector for the pure-green target."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


DEFAULT_CONFIG: dict[str, Any] = {
    "hsv": {"lower": [34, 50, 50], "upper": [70, 255, 255]},
    "morphology": {
        "kernel": 3,
        "open_iterations": 1,
        "close_iterations": 1,
    },
    "geometry": {
        "min_area_pixels": 150.0,
        "min_area_fraction": 0.0004,
        "max_area_fraction": 0.08,
        "max_aspect_ratio": 1.35,
        "min_circularity": 0.55,
        "min_enclosing_circle_fill": 0.70,
    },
}


def _merge(destination: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _merge(destination[key], value)
        else:
            destination[key] = value


def _validate_config(config: dict[str, Any]) -> None:
    lower = config["hsv"]["lower"]
    upper = config["hsv"]["upper"]
    if len(lower) != 3 or len(upper) != 3:
        raise ValueError("hsv.lower and hsv.upper must contain H, S, V")
    limits = (179, 255, 255)
    for name, values in (("lower", lower), ("upper", upper)):
        if any(not isinstance(value, int) for value in values):
            raise ValueError(f"hsv.{name} values must be integers")
        if any(value < 0 or value > limit for value, limit in zip(values, limits)):
            raise ValueError(f"hsv.{name} is outside OpenCV HSV limits")
    if any(lo > hi for lo, hi in zip(lower, upper)):
        raise ValueError("hsv.lower must not exceed hsv.upper")

    morphology = config["morphology"]
    kernel = morphology["kernel"]
    if not isinstance(kernel, int) or kernel < 1 or kernel % 2 == 0:
        raise ValueError("morphology.kernel must be a positive odd integer")
    for key in ("open_iterations", "close_iterations"):
        if not isinstance(morphology[key], int) or morphology[key] < 0:
            raise ValueError(f"morphology.{key} must be a non-negative integer")

    geometry = config["geometry"]
    fractions = ("min_area_fraction", "max_area_fraction")
    if any(not 0.0 <= float(geometry[key]) <= 1.0 for key in fractions):
        raise ValueError("area fractions must be in [0, 1]")
    if geometry["min_area_fraction"] >= geometry["max_area_fraction"]:
        raise ValueError("min_area_fraction must be below max_area_fraction")
    if float(geometry["min_area_pixels"]) < 0.0:
        raise ValueError("min_area_pixels must be non-negative")
    if float(geometry["max_aspect_ratio"]) < 1.0:
        raise ValueError("max_aspect_ratio must be at least 1")
    for key in ("min_circularity", "min_enclosing_circle_fill"):
        if not 0.0 <= float(geometry[key]) <= 1.0:
            raise ValueError(f"geometry.{key} must be in [0, 1]")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load defaults and optionally merge a JSON override."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if path is not None:
        with Path(path).open("r", encoding="utf-8") as stream:
            override = json.load(stream)
        if not isinstance(override, dict):
            raise ValueError("configuration root must be a JSON object")
        _merge(config, override)
    _validate_config(config)
    return config


@dataclass(frozen=True)
class Detection:
    label: str
    center: tuple[int, int]
    bbox: tuple[int, int, int, int]
    area: float
    aspect_ratio: float
    circularity: float
    enclosing_circle_fill: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GreenTargetDetector:
    """Detect solid or annular green circular targets in BGR images."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = copy.deepcopy(config if config is not None else DEFAULT_CONFIG)
        _validate_config(self.config)

    def segment(self, bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8:
            raise ValueError("image must be a uint8 NumPy array")
        if bgr.ndim != 3 or bgr.shape[2] != 3 or not bgr.size:
            raise ValueError("image must have non-zero HxWx3 BGR shape")

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        lower = np.asarray(self.config["hsv"]["lower"], dtype=np.uint8)
        upper = np.asarray(self.config["hsv"]["upper"], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        morphology = self.config["morphology"]
        kernel_size = morphology["kernel"]
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
        )
        if morphology["open_iterations"]:
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_OPEN,
                kernel,
                iterations=morphology["open_iterations"],
            )
        if morphology["close_iterations"]:
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_CLOSE,
                kernel,
                iterations=morphology["close_iterations"],
            )
        return hsv, mask

    def detect(self, bgr: np.ndarray) -> tuple[list[Detection], np.ndarray]:
        _, mask = self.segment(bgr)
        contours_result = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = contours_result[-2]
        frame_area = float(bgr.shape[0] * bgr.shape[1])
        geometry = self.config["geometry"]
        minimum_area = max(
            float(geometry["min_area_pixels"]),
            frame_area * float(geometry["min_area_fraction"]),
        )
        maximum_area = frame_area * float(geometry["max_area_fraction"])
        detections: list[Detection] = []

        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < minimum_area or area > maximum_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            if width <= 0 or height <= 0:
                continue
            aspect_ratio = max(width, height) / min(width, height)
            if aspect_ratio > float(geometry["max_aspect_ratio"]):
                continue

            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0.0:
                continue
            circularity = 4.0 * math.pi * area / (perimeter * perimeter)
            if circularity < float(geometry["min_circularity"]):
                continue

            (circle_x, circle_y), radius = cv2.minEnclosingCircle(contour)
            if radius <= 0.0:
                continue
            circle_fill = area / (math.pi * radius * radius)
            if circle_fill < float(geometry["min_enclosing_circle_fill"]):
                continue

            aspect_score = max(
                0.0,
                1.0
                - (aspect_ratio - 1.0)
                / max(float(geometry["max_aspect_ratio"]) - 1.0, 1e-6),
            )
            circularity_score = min(1.0, circularity)
            circle_fill_score = min(1.0, circle_fill / (math.pi / 4.0))
            confidence = 100.0 * (
                0.35 * aspect_score
                + 0.35 * circularity_score
                + 0.30 * circle_fill_score
            )
            detections.append(
                Detection(
                    label="GREEN_TARGET",
                    center=(int(round(circle_x)), int(round(circle_y))),
                    bbox=(x, y, width, height),
                    area=round(area, 1),
                    aspect_ratio=round(aspect_ratio, 3),
                    circularity=round(circularity, 3),
                    enclosing_circle_fill=round(circle_fill, 3),
                    confidence=round(confidence, 1),
                )
            )

        detections.sort(key=lambda detection: detection.area, reverse=True)
        return detections, mask

    @staticmethod
    def draw(bgr: np.ndarray, detections: list[Detection]) -> np.ndarray:
        annotated = bgr.copy()
        for detection in detections:
            x, y, width, height = detection.bbox
            center_x, center_y = detection.center
            cv2.rectangle(
                annotated, (x, y), (x + width - 1, y + height - 1), (0, 0, 255), 2
            )
            cv2.drawMarker(
                annotated,
                (center_x, center_y),
                (0, 0, 255),
                cv2.MARKER_CROSS,
                16,
                2,
            )
            label = f"GREEN_TARGET {detection.confidence:.0f}%"
            text_y = max(18, y - 7)
            cv2.putText(
                annotated,
                label,
                (x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
        return annotated

