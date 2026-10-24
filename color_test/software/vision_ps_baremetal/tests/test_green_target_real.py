"""Compare the embedded C detector with the Python reference on real captures."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
sys.path.insert(0, str(ROOT))

from green_target_recognition.detector import GreenTargetDetector, load_config  # noqa: E402


STAMPS = ("213127", "213118", "213106", "213056", "213023")


def log(message: str) -> None:
    print(message, flush=True)


def run_command(label: str, command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    log(f"[{label}] START: {subprocess.list2cmdline(command)}")
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        elapsed = time.perf_counter() - started
        if error.stdout:
            log(f"[{label}] stdout:\n{error.stdout}")
        if error.stderr:
            log(f"[{label}] stderr:\n{error.stderr}")
        raise RuntimeError(f"{label} timed out after {elapsed:.2f}s") from error
    elapsed = time.perf_counter() - started
    if result.stdout:
        log(f"[{label}] stdout:\n{result.stdout.rstrip()}")
    if result.stderr:
        log(f"[{label}] stderr:\n{result.stderr.rstrip()}")
    if result.returncode:
        raise RuntimeError(f"{label} failed rc={result.returncode} after {elapsed:.2f}s")
    log(f"[{label}] PASS {elapsed:.2f}s")
    return result


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot read {path}")
    return image


def compile_probe(destination: Path) -> None:
    source = APP / "src"
    tests = APP / "tests"
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc was not found on PATH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    common = [compiler, "-std=c99", "-O0", "-Wall", "-Wextra", "-Werror",
              "-I" + str(source)]
    objects = [
        ("compile:vision_ps.c", source / "vision_ps.c", destination.with_name("vision_ps.o")),
        ("compile:green_target_detector.c", source / "green_target_detector.c",
         destination.with_name("green_target_detector.o")),
        ("compile:green_target_probe.c", tests / "green_target_probe.c",
         destination.with_name("green_target_probe.o")),
    ]
    log(f"[environment] python={sys.executable}")
    log(f"[environment] gcc={compiler}")
    run_command("python->gcc", [compiler, "--version"], 10)
    for label, input_path, output_path in objects:
        output_path.unlink(missing_ok=True)
        run_command(label, common + ["-c", str(input_path), "-o", str(output_path)], 60)
    destination.unlink(missing_ok=True)
    run_command(
        "link:green_target_probe",
        [compiler, *(str(item[2]) for item in objects), "-lm", "-o", str(destination)],
        30,
    )
    if not destination.is_file():
        raise RuntimeError(f"probe was not created: {destination}")
    log(f"[compile] probe={destination} bytes={destination.stat().st_size}")


def run_c(probe: Path, image: np.ndarray, raw_path: Path):
    height, width = image.shape[:2]
    stride = width * 3 + 17
    packed = np.full((height, stride), 0xA5, np.uint8)
    packed[:, :width * 3] = image.reshape(height, width * 3)
    packed.tofile(raw_path)
    result = run_command(
        f"probe:{raw_path.stem}",
        [str(probe), str(width), str(height), str(stride), str(raw_path)],
        15,
    )
    lines = result.stdout.splitlines()
    if not lines:
        raise AssertionError("C probe produced no output")
    count = int(lines[0])
    detections = []
    for line in lines[1:]:
        values = list(map(int, line.split()))
        detections.append({
            "center": tuple(values[0:2]), "bbox": tuple(values[2:6]),
            "area": values[6], "confidence": values[7],
        })
    if count != len(detections):
        raise AssertionError(f"C count mismatch: {count} vs {len(detections)}")
    return detections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path,
                        default=ROOT / "color_test" / "build" / "green_target_diag")
    parser.add_argument("--probe", type=Path,
                        help="reuse an existing probe instead of compiling")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--stamp", action="append", choices=STAMPS,
                        help="run only selected timestamp(s)")
    args = parser.parse_args()
    reference = GreenTargetDetector(load_config(ROOT / "green_target_recognition" / "config.json"))
    temp = args.build_dir.resolve()
    temp.mkdir(parents=True, exist_ok=True)
    probe = args.probe.resolve() if args.probe else temp / "green_target_probe.exe"
    if args.probe:
        if not probe.is_file():
            raise RuntimeError(f"probe does not exist: {probe}")
        log(f"[compile] reusing probe={probe}")
    else:
        compile_probe(probe)
    if args.compile_only:
        log("[result] compile-only PASS")
        return 0

    stamps = tuple(args.stamp) if args.stamp else STAMPS
    for stamp in stamps:
        log(f"[image:{stamp}] START")
        matches = list(args.samples_dir.glob(f"*{stamp}.png"))
        if len(matches) != 1:
            raise AssertionError(f"expected one screenshot for {stamp}, got {len(matches)}")
        started = time.perf_counter()
        image = read_image(matches[0])
        log(f"[image:{stamp}] read PASS {time.perf_counter() - started:.2f}s "
            f"shape={image.shape}")
        started = time.perf_counter()
        python_detections, _ = reference.detect(image)
        log(f"[image:{stamp}] python PASS {time.perf_counter() - started:.2f}s "
            f"count={len(python_detections)}")
        raw_path = temp / f"{stamp}.raw"
        c_detections = run_c(probe, image, raw_path)
        if len(python_detections) != 1 or len(c_detections) != 1:
            raise AssertionError(
                f"{stamp}: Python/C counts {len(python_detections)}/{len(c_detections)}"
            )
        python_detection = python_detections[0]
        c_detection = c_detections[0]
        if any(abs(a - b) > 12 for a, b in zip(
                python_detection.center, c_detection["center"])):
            raise AssertionError(
                f"{stamp}: center {python_detection.center} vs {c_detection['center']}"
            )
        if any(abs(a - b) > 16 for a, b in zip(
                python_detection.bbox, c_detection["bbox"])):
            raise AssertionError(
                f"{stamp}: bbox {python_detection.bbox} vs {c_detection['bbox']}"
            )
        raw_path.unlink(missing_ok=True)
        log(
            f"[image:{stamp}] PASS center={c_detection['center']} "
            f"bbox={c_detection['bbox']} area={c_detection['area']} "
            f"confidence={c_detection['confidence']}"
        )
    log(f"[result] {len(stamps)} real-image comparison(s) PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
