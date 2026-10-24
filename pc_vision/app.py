"""Image/camera/video input, debug windows and JSONL output."""
import argparse
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

try:
    from .config import DEFAULT, load_config
    from .detector import Detector
except ImportError:  # Keep direct `python pc_vision/app.py` execution working.
    from config import DEFAULT, load_config
    from detector import Detector


def read_image(path):
    frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Cannot decode image: {path}")
    return frame


def write_image(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix, frame)
    if not ok:
        raise OSError(f"Cannot encode {path}")
    encoded.tofile(str(path))


def pixel_diagnostics(frame, hsv, x, y, config):
    """Inspect raw pixels, not annotation colors; include a small noise-resistant patch."""
    patch = hsv[max(0, y-2):y+3, max(0, x-2):x+3].reshape(-1, 3)
    pixel = hsv[y, x]
    checks = {}
    for color, ranges in {**config["hsv"], "wall": config["wall"]["hsv"]}.items():
        alternatives = []
        for lo, hi in ranges:
            alternatives.append([f"{name}<{a}" if v < a else f"{name}>{b}"
                                 for name, v, a, b in zip("HSV", pixel, lo, hi)
                                 if v < a or v > b])
        checks[color] = dict(pass_hsv=any(not failed for failed in alternatives),
                             failed_by_range=alternatives)
    return dict(x=x, y=y, bgr=frame[y, x].tolist(), hsv=pixel.tolist(),
                patch_hsv_min=patch.min(axis=0).tolist(),
                patch_hsv_max=patch.max(axis=0).tolist(),
                patch_hsv_median=np.median(patch, axis=0).tolist(), thresholds=checks)


def save_debug(directory, source_frame, frame, result, record):
    directory.mkdir(parents=True, exist_ok=False)
    write_image(directory / "input.png", source_frame)
    write_image(directory / "processed.png", frame)
    write_image(directory / "final.png", result.final)
    write_image(directory / "candidate_mask.png", result.candidate_mask)
    write_image(directory / "marker_mask.png", result.marker_mask)
    for color, mask in result.masks.items():
        write_image(directory / f"mask_{color}.png", mask)
    (directory / "diagnostics.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


class DebugWindows:
    def __init__(self, config):
        self.config = config
        self.frame = self.hsv = None
        self.label = "Click original/final: BGR and HSV"
        for name in ("original", "HSV masks", "candidate mask", "marker mask", "final result"):
            cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
        for name in ("original", "final result"):
            cv2.setMouseCallback(name, self.click)

    def click(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and self.frame is not None and 0 <= y < self.frame.shape[0] and 0 <= x < self.frame.shape[1]:
            bgr = self.frame[y, x].tolist()
            hsv = self.hsv[y, x].tolist() if self.hsv is not None else "disabled"
            self.label = f"({x},{y}) BGR={bgr} HSV={hsv}"
            print(self.label, file=sys.stderr)
            if self.hsv is not None:
                print(json.dumps(pixel_diagnostics(self.frame, self.hsv, x, y, self.config)), file=sys.stderr)

    def show(self, frame, result):
        self.frame, self.hsv = frame, result.hsv
        original = frame.copy()
        cv2.putText(original, self.label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
        cv2.imshow("original", original)
        cv2.imshow("final result", result.final)
        cv2.imshow("candidate mask", result.candidate_mask)
        cv2.imshow("marker mask", result.marker_mask)
        tiles = []
        for color in [*DEFAULT["hsv"], "wall"]:
            mask = result.masks.get(color, np.zeros(frame.shape[:2], np.uint8))
            tile = cv2.cvtColor(cv2.resize(mask, (240, 160), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
            cv2.putText(tile, color, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 255), 1)
            tiles.append(tile)
        cv2.imshow("HSV masks", np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:])]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Color and marker based PC vision prototype")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--video", type=Path)
    source.add_argument("--camera", type=int)
    source.add_argument("--photos", type=Path, help="Photo directory for offline game browsing")
    source.add_argument("--replay", type=Path, help="scene-v1 JSONL recording for game mode")
    source.add_argument("--serial", help="Explicit UART port for board scenes (e.g. COM5); never auto-detected")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud, 8N1; firmware default 115200")
    parser.add_argument("--game", action="store_true", help="Independent virtual game using production C recognition/physics")
    parser.add_argument("--native-game", action="store_true", help="Offline three-level C game; Python only transports files/mouse/native pixels")
    parser.add_argument("--assets", type=Path, default=Path("output/build/game_app/offline_native_20261021/assets/game_assets.bin"))
    parser.add_argument("--start-photo", default="077.png")
    parser.add_argument("--game-config", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--calibration-out", type=Path)
    parser.add_argument("--plane-size", type=float, nargs=2, metavar=("WIDTH_MM", "HEIGHT_MM"))
    parser.add_argument("--scene-timeout", type=float)
    parser.add_argument("--input-hz", type=float, default=8, help="Offline video processing cadence")
    parser.add_argument("--replay-speed", type=float, default=1)
    parser.add_argument("--cc", help="Host GCC path; default is gcc on PATH")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--disable", nargs="+", choices=list(DEFAULT["stages"]), default=[])
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--output", type=Path, help="New directory for JSONL and optional rendered frames")
    parser.add_argument("--save-frames", action="store_true")
    parser.add_argument("--save-debug", action="store_true", help="Save raw images, masks and reasons each frame")
    parser.add_argument("--show-rejected", action="store_true", help="Draw rejected candidates for diagnosis")
    parser.add_argument("--max-frames", type=int, default=0, help="0 means until EOF/quit")
    parser.add_argument("--width", type=int, default=0, help="Processing width; 0 keeps original")
    parser.add_argument("--types", nargs="+", choices=sorted(Detector.TYPES.values()),
                        help="Only evaluate these classes; omitted means all classes")
    args = parser.parse_args(argv)
    if args.width < 0 or args.max_frames < 0:
        parser.error("width and max-frames must be nonnegative")
    if (args.save_frames or args.save_debug) and args.output is None:
        parser.error("--save-frames/--save-debug requires --output")
    if args.native_game:
        if args.camera is not None or args.serial or args.calibration or args.game_config or args.plane_size:
            parser.error("Native offline preview accepts files only and the generated canonical uncalibrated configuration")
        if args.width or args.config or args.disable or args.types or args.save_debug or args.show_rejected or args.scene_timeout is not None or args.calibration_out:
            parser.error("Native mode uses unchanged C detection and canonical timing; detector/calibration override flags are unavailable")
        if not np.isfinite(args.input_hz) or args.input_hz <= 0 or args.replay_speed != 1:
            parser.error("Native input-hz must be positive and replay-speed must be 1 to preserve capture timestamps")
        if __package__:
            from .game_app import run_native_game
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from pc_vision.game_app import run_native_game
        return run_native_game(args)
    if args.game:
        if args.baud <= 0:
            parser.error("baud must be positive")
        if args.camera is not None:
            parser.error("Game mode uses --serial for board scenes, or --image/--photos/--video/--replay for files")
        if args.width or args.config or args.disable or args.types or args.save_debug or args.show_rejected:
            parser.error("Game mode uses unchanged C detection; detector debug flags belong to the original mode")
        if not np.isfinite([args.input_hz, args.replay_speed]).all() or min(args.input_hz, args.replay_speed) <= 0:
            parser.error("input-hz and replay-speed must be finite and positive")
        if args.plane_size and (not np.isfinite(args.plane_size).all() or min(args.plane_size) <= 0):
            parser.error("plane-size must be finite positive measured dimensions in mm")
        if args.scene_timeout is not None and (not np.isfinite(args.scene_timeout) or args.scene_timeout <= 0):
            parser.error("scene-timeout must be finite and positive")
        if __package__:
            from .game_app import run_game
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from pc_vision.game_app import run_game
        return run_game(args)
    if args.photos or args.replay or args.serial:
        parser.error("--photos/--replay/--serial requires --game")
    config = load_config(args.config)
    if args.show_rejected:
        config["display"]["show_rejected"] = True
    for name in args.disable:
        config["stages"][name] = False
    detector = Detector(config, enabled_types=args.types)
    capture = log = None
    count = 0
    try:
        if args.image:
            still = read_image(args.image)
        else:
            capture = cv2.VideoCapture(args.camera if args.camera is not None else str(args.video))
            if not capture.isOpened():
                raise RuntimeError("Cannot open video/camera")
        if args.output:
            args.output.mkdir(parents=True, exist_ok=False)
            log = (args.output / "detections.jsonl").open("x", encoding="utf-8")
            (args.output / "effective_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        ui = None if args.headless else DebugWindows(config)
        while True:
            if capture is None:
                frame = still
            else:
                ok, frame = capture.read()
                if not ok:
                    if args.camera is not None or count == 0:
                        raise RuntimeError("Camera read failed or video contained no decodable frames")
                    break
            source_frame = frame
            source_shape = list(frame.shape[:2])
            if args.width and frame.shape[1] != args.width:
                height = max(1, round(frame.shape[0] * args.width / frame.shape[1]))
                frame = cv2.resize(frame, (args.width, height))
            start = time.perf_counter()
            result = detector.process(frame)
            elapsed = (time.perf_counter() - start) * 1000
            record = dict(frame=count, source_size_hw=source_shape, processed_size_hw=list(frame.shape[:2]),
                          processing_ms=round(elapsed, 3), status=result.status,
                          segmentation_stats=result.segmentation_stats,
                          detections=[d.to_dict() for d in result.detections], candidates=result.candidates)
            line = json.dumps(record, ensure_ascii=False, allow_nan=False)
            print(line)
            if log:
                log.write(line + "\n")
                log.flush()
                if args.save_frames:
                    write_image(args.output / f"frame_{count:06d}.png", result.final)
                if args.save_debug:
                    save_debug(args.output / f"debug_{count:06d}", source_frame, frame, result, record)
            count += 1
            if ui:
                while True:
                    ui.show(frame, result)
                    key = cv2.waitKey(30 if capture is None else 1) & 0xFF
                    if key == ord("s"):
                        if args.output is None:
                            print("Snapshot needs --output NEW_DIRECTORY", file=sys.stderr)
                        else:
                            snapshot = args.output / f"snapshot_{count-1:06d}"
                            if not snapshot.exists():
                                save_debug(snapshot, source_frame, frame, result, record)
                                print(f"Saved raw image and diagnostics: {snapshot}", file=sys.stderr)
                    if key in (27, ord("q")) or cv2.getWindowProperty("original", cv2.WND_PROP_VISIBLE) < 1:
                        return
                    if capture is not None or key in (13, 32):
                        break
            if capture is None or (args.max_frames and count >= args.max_frames):
                break
    finally:
        if capture is not None:
            capture.release()
        if log:
            log.close()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
