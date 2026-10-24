"""Headless board entry point; default live recognition is TARGET-only."""

import argparse
import json
from pathlib import Path
import time

from .hardware import CameraPipeline, inspect_overlay_files


def process_frame(detector, source, width):
    import cv2
    frame = source
    if width and width != source.shape[1]:
        height = max(1, round(source.shape[0] * width / source.shape[1]))
        frame = cv2.resize(source, (width, height))
    started = time.perf_counter()
    result = detector.process(frame)
    processing_ms = (time.perf_counter() - started) * 1000.0
    rendered = result.final
    if rendered.shape[:2] != source.shape[:2]:
        rendered = cv2.resize(rendered, (source.shape[1], source.shape[0]))
    return result, rendered, processing_ms


def result_record(index, source, processed_width, result, timings):
    processed_height = (source.shape[0] if not processed_width else
                        max(1, round(source.shape[0] * processed_width / source.shape[1])))
    return {
        "frame": index,
        "source_size_hw": list(source.shape[:2]),
        "processed_size_hw": [processed_height,
                              processed_width or source.shape[1]],
        "timings_ms": {name: round(value, 3) for name, value in timings.items()},
        "status": result.status,
        "detections": [d.to_dict() for d in result.detections],
        "candidates": result.candidates,
        "segmentation_stats": result.segmentation_stats,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="AX7Z020B PYNQ MIPI vision")
    parser.add_argument("--overlay", type=Path, required=True,
                        help="Matched system_wrapper.bit (the .hwh must be beside it)")
    # argparse did not support required=True for subparsers on Python 3.6.
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("inspect-overlay", help="Parse and verify BIT/HWH without loading PL")

    capture = sub.add_parser("capture", help="Capture one BGR frame without HDMI initialization")
    capture.add_argument("--i2c-device", required=True, help="Previously verified camera I2C bus")
    capture.add_argument("--output", type=Path, required=True)

    run = sub.add_parser("run", help="TARGET-only capture/detect/HDMI loop")
    run.add_argument("--i2c-device", default="/dev/i2c-0")
    run.add_argument("--config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--frames", type=int, default=0, help="0 runs until Ctrl-C")
    run.add_argument("--width", type=int, default=0,
                     help="0 starts at full 1280 width; later profiling may justify 640/320")
    run.add_argument("--types", nargs="+", default=["TARGET"])
    run.add_argument("--save-every", type=int, default=0,
                     help="Save every Nth annotated frame; 0 disables periodic PNG writes")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("a command is required")

    if args.command == "inspect-overlay":
        print(json.dumps(inspect_overlay_files(args.overlay), indent=2, sort_keys=True))
        return

    import cv2
    if args.command == "capture":
        # File/clock metadata failures must occur before any PYNQ/device action.
        preflight = inspect_overlay_files(args.overlay)
        args.output.mkdir(parents=True, exist_ok=False)
        pipeline = CameraPipeline(args.overlay, args.i2c_device, enable_display=False)
        record = {"status": "FAIL", "display_enabled": False, "overlay": preflight}
        try:
            with pipeline:
                frame, timings = pipeline.capture()
                if not cv2.imwrite(str(args.output / "frame.png"), frame):
                    raise OSError("cannot write captured frame.png")
                record.update(status="PASS", frame_shape=list(frame.shape),
                              nonzero=int(cv2.countNonZero(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))),
                              timings_ms=timings)
        except Exception as exc:
            record["status"] = "FAIL"
            record["error"] = repr(exc)
            raise
        finally:
            record["stage"] = pipeline.stage
            record["overlay"] = pipeline.overlay_report or preflight
            (args.output / "capture.json").write_text(
                json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            print(json.dumps(record, sort_keys=True))
        return

    if args.frames < 0 or args.width < 0 or args.save_every < 0:
        parser.error("frames, width and save-every must be nonnegative")
    # Capture/inspection bundles do not need the PC detector or dataclasses.
    from pc_vision.app import write_image
    from pc_vision.config import load_config
    from pc_vision.detector import Detector
    detector = Detector(load_config(args.config), enabled_types=args.types)
    args.output.mkdir(parents=True, exist_ok=False)
    log_path = args.output / "detections.jsonl"
    with log_path.open("x", encoding="utf-8") as log:
        with CameraPipeline(args.overlay, args.i2c_device, enable_display=True) as pipeline:
            (args.output / "overlay_report.json").write_text(
                json.dumps(pipeline.overlay_report, indent=2, sort_keys=True), encoding="utf-8")
            index = 0
            try:
                while not args.frames or index < args.frames:
                    total_started = time.perf_counter()
                    source, timings = pipeline.capture()
                    result, rendered, processing_ms = process_frame(
                        detector, source, args.width)
                    timings["opencv"] = processing_ms
                    timings["hdmi_overlay"] = pipeline.present(rendered)
                    timings["total"] = (time.perf_counter() - total_started) * 1000.0
                    record = result_record(index, source, args.width, result, timings)
                    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
                    print(line)
                    log.write(line + "\n")
                    log.flush()
                    if args.save_every and index % args.save_every == 0:
                        write_image(args.output / "frame_{:06d}.png".format(index), rendered)
                    index += 1
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
