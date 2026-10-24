"""Command-line image/video/camera runner for green target recognition."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from .detector import GreenTargetDetector, load_config
except ImportError:  # Direct execution: python green_target_recognition/app.py
    from detector import GreenTargetDetector, load_config


ROOT = Path(__file__).resolve().parent


def read_image(path: Path) -> np.ndarray:
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError as error:
        raise RuntimeError(f"cannot read image: {path}: {error}") from error
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"unsupported or damaged image: {path}")
    return image


def write_image(path: Path, image: np.ndarray, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"output exists (use --overwrite): {path}")
    extension = path.suffix.lower()
    if extension not in (".png", ".jpg", ".jpeg", ".bmp"):
        raise RuntimeError("image output extension must be PNG/JPG/JPEG/BMP")
    success, encoded = cv2.imencode(extension, image)
    if not success:
        raise RuntimeError(f"cannot encode output image: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoded.tofile(path)
    except OSError as error:
        raise RuntimeError(f"cannot write image: {path}: {error}") from error


def result_record(
    frame_number: int,
    source: str,
    detections,
    processing_ms: float,
) -> dict:
    return {
        "frame": frame_number,
        "source": source,
        "processing_ms": round(processing_ms, 3),
        "count": len(detections),
        "detections": [detection.to_dict() for detection in detections],
    }


def process_image(args, detector: GreenTargetDetector) -> int:
    image_path = Path(args.image)
    image = read_image(image_path)
    started = time.perf_counter()
    detections, mask = detector.detect(image)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    annotated = detector.draw(image, detections)
    print(json.dumps(result_record(0, str(image_path), detections, elapsed_ms)))

    if args.output:
        write_image(Path(args.output), annotated, args.overwrite)
    if args.mask_output:
        write_image(Path(args.mask_output), mask, args.overwrite)
    if args.show:
        cv2.imshow("green target", annotated)
        cv2.imshow("green mask", mask)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return 0 if detections else 1


def process_stream(args, detector: GreenTargetDetector) -> int:
    source = int(args.camera) if args.camera is not None else args.video
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video source: {source}")

    writer = None
    output_path = Path(args.output) if args.output else None
    if output_path and output_path.exists() and not args.overwrite:
        capture.release()
        raise RuntimeError(f"output exists (use --overwrite): {output_path}")

    found_any = False
    frame_number = 0
    try:
        while args.max_frames is None or frame_number < args.max_frames:
            ok, image = capture.read()
            if not ok:
                break
            started = time.perf_counter()
            detections, mask = detector.detect(image)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            annotated = detector.draw(image, detections)
            found_any = found_any or bool(detections)
            print(
                json.dumps(
                    result_record(frame_number, str(source), detections, elapsed_ms)
                ),
                flush=True,
            )

            if output_path:
                if writer is None:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    fps = capture.get(cv2.CAP_PROP_FPS)
                    if not fps or fps <= 0.0:
                        fps = 25.0
                    writer = cv2.VideoWriter(
                        str(output_path),
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        fps,
                        (image.shape[1], image.shape[0]),
                    )
                    if not writer.isOpened():
                        raise RuntimeError(f"cannot open video output: {output_path}")
                writer.write(annotated)

            if args.show:
                cv2.imshow("green target", annotated)
                cv2.imshow("green mask", mask)
                if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                    break
            frame_number += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()
    return 0 if found_any else 1


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Detect the pure-green circular target"
    )
    source = argument_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="input image path")
    source.add_argument("--video", help="input video path")
    source.add_argument("--camera", type=int, help="OpenCV camera index")
    argument_parser.add_argument(
        "--config", default=str(ROOT / "config.json"), help="JSON configuration"
    )
    argument_parser.add_argument("--output", help="annotated image or MP4 output")
    argument_parser.add_argument(
        "--mask-output", help="mask image output; image mode only"
    )
    argument_parser.add_argument("--show", action="store_true", help="show GUI windows")
    argument_parser.add_argument(
        "--overwrite", action="store_true", help="replace an existing output"
    )
    argument_parser.add_argument(
        "--max-frames", type=int, help="limit video/camera frames"
    )
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    if args.mask_output and not args.image:
        print("error: --mask-output is available only with --image", file=sys.stderr)
        return 2
    if args.max_frames is not None and args.max_frames <= 0:
        print("error: --max-frames must be positive", file=sys.stderr)
        return 2
    try:
        detector = GreenTargetDetector(load_config(args.config))
        if args.image:
            return process_image(args, detector)
        return process_stream(args, detector)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

