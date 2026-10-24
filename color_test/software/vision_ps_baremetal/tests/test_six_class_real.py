"""Run the five non-TARGET detectors against the supplied 50 cm captures."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

import cv2
import numpy as np


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
sys.path.insert(0, str(ROOT / "pc_vision"))

from config import load_config  # noqa: E402
from detector import Detector  # noqa: E402


SAMPLES = {
    "SOURCE": ("102258", "102343", "102330", "102316", "102358"),
    "WALL": ("121951", "122033", "122022", "122014", "122040"),
    "PORTAL_A": ("103731", "103754", "103747", "103739", "103801"),
    "PORTAL_B": ("103926", "103948", "103942", "103934", "103956"),
    "MIRROR": ("105348", "105418", "105409", "105401", "105426"),
}
POSITIONS = ("center", "upper_left", "upper_right", "lower_right", "lower_left")


def position_ok(position: str, center: tuple[float, float], width: int, height: int) -> bool:
    x = center[0] / width
    y = center[1] / height
    if position == "center":
        return 0.25 <= x <= 0.75 and 0.25 <= y <= 0.75
    horizontal = x < 0.45 if position.endswith("left") else x > 0.55
    vertical = y < 0.45 if position.startswith("upper") else y > 0.55
    return horizontal and vertical


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot read {path}")
    return image


def compile_probe(destination: Path, trace: bool = False) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc was not found on PATH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
        *(["-DVISION_TRACE"] if trace else []),
        "-I" + str(APP / "src"), str(APP / "src" / "vision_ps.c"),
        str(APP / "src" / "green_target_detector.c"),
        str(APP / "tests" / "vision_probe.c"), "-lm", "-o", str(destination),
    ]
    subprocess.run(command, check=True)


def detect_c(probe: Path, image: np.ndarray, raw_path: Path) -> list[dict]:
    height, width = image.shape[:2]
    stride = width * 3 + 17
    packed = np.full((height, stride), 0xA5, np.uint8)
    packed[:, :width * 3] = image.reshape(height, width * 3)
    packed.tofile(raw_path)
    try:
        output = subprocess.check_output([
            str(probe), "detect", str(width), str(height), str(stride), str(raw_path)
        ], text=True).splitlines()
    finally:
        raw_path.unlink(missing_ok=True)
    detections = []
    for line in output[1:]:
        fields = line.split()
        detections.append({
            "type": fields[0], "center": tuple(map(int, fields[1:3])),
            "bbox": tuple(map(int, fields[3:7])), "angle": int(fields[7]),
            "area": int(fields[8]),
            "direction_valid": int(fields[9]) if len(fields) >= 14 else 0,
            "direction": tuple(map(float, fields[10:12])) if len(fields) >= 14 else (0.0, 0.0),
            "source_tip": tuple(map(int, fields[12:14])) if len(fields) >= 14 else (0, 0),
        })
    if not output or int(output[0]) != len(detections):
        raise AssertionError("C probe detection count mismatch")
    return detections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path,
                        default=ROOT / "color_test" / "build" / "six_class_real")
    parser.add_argument("--stamp", action="append",
                        help="run only selected screenshot timestamp(s)")
    parser.add_argument("--trace", action="store_true",
                        help="enable C candidate/marker diagnostics")
    parser.add_argument("--diagnostic", action="store_true",
                        help="report mismatches without failing")
    args = parser.parse_args()

    probe = args.build_dir.resolve() / "vision_probe.exe"
    compile_probe(probe, args.trace)
    detector = Detector(load_config(), enabled_types=set(SAMPLES))
    failures = []
    checked = 0
    for expected, stamps in SAMPLES.items():
        for sample_index, stamp in enumerate(stamps):
            if args.stamp and stamp not in args.stamp:
                continue
            matches = list(args.samples_dir.glob(f"*{stamp}.png"))
            if len(matches) != 1:
                failures.append(f"{expected}/{stamp}: expected one PNG, got {len(matches)}")
                continue
            image = read_image(matches[0])
            pc = detector.process(image).detections
            c = detect_c(probe, image, args.build_dir / f"{stamp}.raw")
            pc_types = [item.type for item in pc]
            c_types = [item["type"] for item in c]
            print(f"{expected:8s} {stamp} shape={image.shape[1]}x{image.shape[0]} "
                  f"PC={pc_types} C={c_types}", flush=True)
            if args.diagnostic:
                print(f"  C details={c}", flush=True)
            checked += 1
            if pc_types != [expected] or c_types != [expected]:
                failures.append(
                    f"{expected}/{stamp}: expected [{expected}], PC={pc_types}, C={c_types}"
                )
            else:
                position = POSITIONS[sample_index]
                pc_center = (pc[0].center_x, pc[0].center_y)
                if not position_ok(position, pc_center, image.shape[1], image.shape[0]):
                    failures.append(f"{expected}/{stamp}: PC center {pc_center} is not {position}")
                if not position_ok(position, c[0]["center"], image.shape[1], image.shape[0]):
                    failures.append(
                        f"{expected}/{stamp}: C center {c[0]['center']} is not {position}"
                    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 0 if args.diagnostic else 1
    print(f"{checked} real-image PC/C checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
