"""Real-image regression for the fixed 1280x720 Portal marker set.

Python only loads the PNG files and drives the host probe.  Recognition,
scene conversion, and ray tracing all execute in the production C sources.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import cv2


TEST_ROOT = Path(__file__).resolve().parent
APP_ROOT = TEST_ROOT.parent
SOURCE_ROOT = APP_ROOT / "src"
PHOTO_ROOT = APP_ROOT.parent.parent.parent / "sample_photo"

WIDTH = 1280
HEIGHT = 720
TYPE_ORDER = {"SOURCE": 0, "PORTAL_A": 1, "PORTAL_B": 2,
              "MIRROR": 3, "TARGET": 4, "WALL": 5}


def expected_types() -> dict[int, set[str]]:
    expected: dict[int, set[str]] = {}
    for number in range(1, 5):
        expected[number] = set()
    for number in range(5, 17):
        expected[number] = {"SOURCE"}
    for number in range(17, 29):
        expected[number] = {"PORTAL_A"}
    for number in range(29, 41):
        expected[number] = {"PORTAL_B"}
    for number in range(41, 49):
        expected[number] = {"MIRROR"}
    for number in range(49, 54):
        expected[number] = {"TARGET"}
    for number in range(54, 63):
        expected[number] = {"SOURCE", "MIRROR"}
    for number in range(63, 73):
        expected[number] = {"SOURCE", "PORTAL_A", "PORTAL_B"}
    expected[73] = {"SOURCE", "TARGET"}
    expected[74] = {"SOURCE", "TARGET"}
    expected[75] = {"SOURCE", "MIRROR", "TARGET"}
    expected[76] = {"SOURCE", "PORTAL_A", "PORTAL_B", "TARGET"}
    expected[77] = {"SOURCE", "PORTAL_A", "PORTAL_B", "MIRROR", "TARGET"}
    return expected


def expected_ray(number: int) -> tuple[str, int, int, list[str]]:
    if number <= 4 or 17 <= number <= 53:
        return "NO_SOURCE", 0, 0, []
    if 5 <= number <= 16:
        return "BOUNDARY", 0, 1, []
    if number in {54, 55, 56, 59, 60, 61, 62}:
        return "BOUNDARY", 0, 2, ["MIRROR"]
    if number in {57, 58}:
        return "BOUNDARY", 0, 1, []
    if number in {63, 64, 65, 68, 69, 70, 72}:
        return "BOUNDARY", 0, 2, ["PORTAL_A"]
    if number in {66, 67}:
        return "BOUNDARY", 0, 1, []
    if number == 71:
        return "BOUNDARY", 0, 2, ["PORTAL_B"]
    if number == 73:
        return "TARGET", 1, 1, ["TARGET"]
    if number == 74:
        return "BOUNDARY", 0, 1, []
    if number == 75:
        return "TARGET", 1, 2, ["MIRROR", "TARGET"]
    if number == 76:
        return "TARGET", 1, 2, ["PORTAL_A", "TARGET"]
    if number == 77:
        return "TARGET", 1, 3, ["PORTAL_A", "MIRROR", "TARGET"]
    raise AssertionError(f"missing ray expectation for {number:03d}")


SOURCE_DIRECTIONS = {
    5: 0.0, 6: 45.0, 7: 90.0, 8: 135.0,
    9: 180.0, 10: -135.0, 11: -90.0, 12: -45.0,
    13: 0.0, 14: 0.0, 15: 0.0, 16: 0.0,
}

PORTAL_DIRECTIONS = {
    17: 0.0, 18: 30.0, 19: 90.0, 20: 135.0,
    21: 180.0, 22: -135.0, 23: -90.0, 24: -45.0,
    25: 0.0, 26: 0.0, 27: 0.0, 28: 0.0,
    29: 0.0, 30: 30.0, 31: 90.0, 32: 135.0,
    33: 180.0, 34: -135.0, 35: -90.0, 36: -45.0,
    37: 0.0, 38: 0.0, 39: 0.0, 40: 0.0,
}


def build_probe(output: Path) -> None:
    compiler = shutil.which("gcc.exe")
    if not compiler:
        raise RuntimeError("gcc.exe is required for the sample-photo regression")
    command = [
        compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
        f"-I{SOURCE_ROOT}",
        str(SOURCE_ROOT / "vision_ps.c"),
        str(SOURCE_ROOT / "green_target_detector.c"),
        str(SOURCE_ROOT / "ray_game.c"),
        str(TEST_ROOT / "sample_photo_probe.c"),
        "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)


def parse_probe(output: str) -> tuple[list[dict[str, object]], tuple[str, int, int, list[str]]]:
    detections: list[dict[str, object]] = []
    ray: tuple[str, int, int, list[str]] | None = None
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "D" and len(fields) == 16:
            detections.append({
                "type": fields[1], "center_x": int(fields[2]),
                "center_y": int(fields[3]), "bbox_x": int(fields[4]),
                "bbox_y": int(fields[5]), "bbox_w": int(fields[6]),
                "bbox_h": int(fields[7]), "angle": float(fields[8]),
                "axis_x": float(fields[9]), "axis_y": float(fields[10]),
                "direction_valid": int(fields[11]),
                "direction_x": float(fields[12]),
                "direction_y": float(fields[13]), "tip_x": int(fields[14]),
                "tip_y": int(fields[15]),
            })
        elif fields[0] == "R" and len(fields) >= 5:
            ray = (fields[1], int(fields[2]), int(fields[3]), fields[5:])
    if ray is None:
        raise AssertionError(f"probe did not return a ray result:\n{output}")
    return detections, ray


def angle_matches(actual: float, expected: float, minimum_dot: float = 0.80) -> bool:
    delta = math.radians(actual - expected)
    return math.cos(delta) >= minimum_dot


def validate_detection(number: int, detections: list[dict[str, object]],
                       expected: set[str]) -> list[str]:
    failures: list[str] = []
    actual = {str(detection["type"]) for detection in detections}
    if actual != expected:
        failures.append(f"types expected={sorted(expected, key=TYPE_ORDER.get)} "
                        f"got={sorted(actual, key=TYPE_ORDER.get)}")
    for detection in detections:
        center_x = int(detection["center_x"])
        center_y = int(detection["center_y"])
        if not (200 <= center_x <= 1080 and 0 <= center_y <= 590):
            failures.append(f"{detection['type']} outside fixed playfield "
                            f"at ({center_x},{center_y})")
    source = next((detection for detection in detections
                   if detection["type"] == "SOURCE"), None)
    if source:
        tip_x = int(source["tip_x"])
        tip_y = int(source["tip_y"])
        left = int(source["bbox_x"]) - 4
        top = int(source["bbox_y"]) - 4
        right = int(source["bbox_x"]) + int(source["bbox_w"]) + 4
        bottom = int(source["bbox_y"]) + int(source["bbox_h"]) + 4
        if not int(source["direction_valid"]) or not (left <= tip_x <= right and
                                                        top <= tip_y <= bottom):
            failures.append("SOURCE has no valid in-marker apex origin")
    if number in SOURCE_DIRECTIONS:
        if source is None:
            failures.append("SOURCE direction missing")
        else:
            actual_angle = math.degrees(math.atan2(float(source["direction_y"]),
                                                    float(source["direction_x"])))
            if not angle_matches(actual_angle, SOURCE_DIRECTIONS[number]):
                failures.append(f"SOURCE direction={actual_angle:.1f} expected "
                                f"{SOURCE_DIRECTIONS[number]:.1f}")
    if number in PORTAL_DIRECTIONS:
        portal = next((detection for detection in detections
                       if str(detection["type"]).startswith("PORTAL_")), None)
        if portal is None or not angle_matches(float(portal["angle"]),
                                                PORTAL_DIRECTIONS[number]):
            actual_angle = "missing" if portal is None else f"{portal['angle']:.1f}"
            failures.append(f"Portal solid-to-ring angle={actual_angle} expected "
                            f"{PORTAL_DIRECTIONS[number]:.1f}")
    return failures


def run() -> int:
    expected = expected_types()
    if not PHOTO_ROOT.is_dir():
        raise RuntimeError(f"sample photo directory not found: {PHOTO_ROOT}")
    failures: list[tuple[int, list[str]]] = []
    with tempfile.TemporaryDirectory(prefix="sample-photo-regression-") as temporary:
        temporary_path = Path(temporary)
        probe = temporary_path / "sample_photo_probe.exe"
        raw = temporary_path / "frame.bgr"
        build_probe(probe)
        for number in range(1, 78):
            image_path = PHOTO_ROOT / f"{number:03d}.png"
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None or image.shape[:2] != (HEIGHT, WIDTH):
                failures.append((number, [f"cannot load 1280x720 {image_path.name}"]))
                continue
            image.tofile(raw)
            completed = subprocess.run(
                [str(probe), str(WIDTH), str(HEIGHT), str(image.strides[0]), str(raw)],
                check=False, capture_output=True, text=True,
            )
            sample_failures: list[str] = []
            if completed.returncode:
                sample_failures.append(f"probe exit={completed.returncode}: "
                                       f"{completed.stderr.strip()}")
            else:
                detections, ray = parse_probe(completed.stdout)
                sample_failures.extend(validate_detection(number, detections,
                                                          expected[number]))
                if ray != expected_ray(number):
                    sample_failures.append(f"ray expected={expected_ray(number)} got={ray}")
            status = "PASS" if not sample_failures else "FAIL " + "; ".join(sample_failures)
            print(f"{number:03d}: {status}")
            if sample_failures:
                failures.append((number, sample_failures))
    if failures:
        print(f"sample-photo regression: {77-len(failures)}/77 passed", file=sys.stderr)
        return 1
    print("sample-photo regression: 77/77 passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
