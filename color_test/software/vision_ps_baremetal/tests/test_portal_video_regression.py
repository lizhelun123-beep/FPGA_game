"""Frame-by-frame regression over the supplied Portal gameplay capture.

The test compiles the production C detector and ray game into a temporary
shared library.  It does not use the yellow overlay already burned into the
recording as ground truth.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import cv2
import numpy as np


APP = Path(__file__).resolve().parents[1]
MAX_DETECTIONS = 16
MAX_SEGMENTS = 17
SOURCE = 4
MIRROR = 0
PORTAL_A = 1
PORTAL_B = 2
LEVEL_ACTIVE = 3
EVENT_SOURCE_LOCKED = 1 << 2
EVENT_RAY_COMMITTED = 1 << 3
EVENT_CANDIDATE_INVALID = 1 << 4
EVENT_TARGET_CONFIRMED = 1 << 6
EVENT_LEVEL_CLEARED = 1 << 7


class Detection(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("center_x", ctypes.c_int), ("center_y", ctypes.c_int),
        ("geometry_center_x", ctypes.c_float),
        ("geometry_center_y", ctypes.c_float),
        ("bbox_x", ctypes.c_int), ("bbox_y", ctypes.c_int),
        ("bbox_w", ctypes.c_int), ("bbox_h", ctypes.c_int),
        ("angle_deg", ctypes.c_int),
        ("confidence_percent", ctypes.c_int),
        ("sampled_area", ctypes.c_uint32),
        ("axis_x", ctypes.c_float), ("axis_y", ctypes.c_float),
        ("major_length", ctypes.c_float),
        ("minor_width", ctypes.c_float),
        ("source_tip_x", ctypes.c_int), ("source_tip_y", ctypes.c_int),
        ("source_direction_x", ctypes.c_float),
        ("source_direction_y", ctypes.c_float),
        ("direction_valid", ctypes.c_int),
    ]


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]


class Segment(ctypes.Structure):
    _fields_ = [("start", Point), ("end", Point)]


class RayResult(ctypes.Structure):
    _fields_ = [
        ("segments", Segment * MAX_SEGMENTS),
        ("segment_count", ctypes.c_int),
        ("interaction_count", ctypes.c_int),
        ("success", ctypes.c_int),
        ("termination", ctypes.c_int),
        ("hit_types", ctypes.c_int * 16),
        ("hit_count", ctypes.c_int),
    ]


def compile_api(destination: Path) -> None:
    started = time.perf_counter()
    print("[VIDEO-TEST] START compile regression API", flush=True)
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if not vswhere.exists():
        raise RuntimeError("Visual Studio vswhere.exe was not found")
    installation = subprocess.check_output([
        str(vswhere), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "-property", "installationPath",
    ], text=True, timeout=10).strip()
    if not installation:
        raise RuntimeError("Visual Studio x64 C tools were not found")
    vcvars = Path(installation) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.exists():
        raise RuntimeError(f"vcvars64.bat was not found below {installation}")
    environment_script = destination.parent / "load_msvc_environment.cmd"
    environment_script.write_text(
        f'@echo off\ncall "{vcvars}" >nul\n'
        'if errorlevel 1 exit /b %errorlevel%\nset\n',
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", str(environment_script)],
        cwd=destination.parent, check=True, capture_output=True, text=True,
        timeout=20,
    )
    environment = {}
    for line in completed.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator and name:
            environment[name] = value
    path_value = next(
        (value for name, value in environment.items()
         if name.casefold() == "path"),
        None,
    )
    compiler_path = shutil.which("cl.exe", path=path_value)
    if compiler_path is None:
        raise RuntimeError("vcvars64.bat did not provide an x64 cl.exe on PATH")
    sources = ["vision_ps.c", "green_target_detector.c", "ray_game.c"]
    compiler = [
        compiler_path, "/nologo", "/LD", "/std:c11", "/O2", "/W4", "/WX",
        "/DVISION_PORTAL_DIAGNOSTICS",
        "/I" + str(APP / "src"),
        *(str(APP / "src" / source) for source in sources),
        str(APP / "tests" / "video_regression_api.c"),
        "/link", "/OUT:" + str(destination),
    ]
    subprocess.run(compiler, cwd=destination.parent, check=True,
                   env=environment, timeout=60)
    print(f"[VIDEO-TEST] DONE  compile regression API "
          f"elapsed={time.perf_counter()-started:.3f}s", flush=True)


def unload_api(library: ctypes.CDLL) -> None:
    """Release the Windows DLL before its temporary directory is removed."""
    if os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    kernel32.FreeLibrary.restype = ctypes.c_int
    if not kernel32.FreeLibrary(ctypes.c_void_p(library._handle)):
        raise ctypes.WinError(ctypes.get_last_error())


def angle_delta(first: Detection, second: Detection) -> float:
    dot = first.source_direction_x * second.source_direction_x + \
          first.source_direction_y * second.source_direction_y
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def marker_supported(frame: np.ndarray, detection: Detection) -> bool:
    """Independent coarse guard: an accepted SOURCE must contain both parts."""
    x0 = max(0, detection.bbox_x - 4)
    y0 = max(0, detection.bbox_y - 4)
    x1 = min(frame.shape[1], detection.bbox_x + detection.bbox_w + 4)
    y1 = min(frame.shape[0], detection.bbox_y + detection.bbox_h + 4)
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 1] <= 80) & (hsv[:, :, 2] >= 110)
    # The physical SOURCE tip is the low-blue, warm red/brown material.  This
    # check is deliberately broader than the production mask.
    b, g, r = cv2.split(roi)
    warm = (r.astype(np.int16) - b.astype(np.int16) >= 25) & \
           (r.astype(np.int16) - g.astype(np.int16) >= 12)
    return int(np.count_nonzero(white)) >= 12 and \
        int(np.count_nonzero(warm)) >= 12


def normalized_axis(detection: Detection) -> tuple[float, float]:
    length = math.hypot(detection.axis_x, detection.axis_y)
    if length <= 0.0:
        return 1.0, 0.0
    return detection.axis_x / length, detection.axis_y / length


def portal_snapshot(detection: Detection) -> dict[str, float]:
    return {
        "center_x": float(detection.geometry_center_x),
        "center_y": float(detection.geometry_center_y),
        "axis_x": float(detection.axis_x),
        "axis_y": float(detection.axis_y),
        "major_length": float(detection.major_length),
        "angle_deg": float(detection.angle_deg),
    }


def portal_endpoints(snapshot: dict[str, float]) -> tuple[tuple[float, float],
                                                           tuple[float, float]]:
    half = snapshot["major_length"] * 0.5
    dx = snapshot["axis_x"] * half
    dy = snapshot["axis_y"] * half
    return ((snapshot["center_x"] - dx, snapshot["center_y"] - dy),
            (snapshot["center_x"] + dx, snapshot["center_y"] + dy))


def local_coordinates(point: Point, detection: Detection) -> tuple[float, float]:
    tx, ty = normalized_axis(detection)
    nx, ny = -ty, tx
    dx = point.x - detection.geometry_center_x
    dy = point.y - detection.geometry_center_y
    return dx * tx + dy * ty, dx * nx + dy * ny


def nearest(point: Point, detections: list[Detection], kinds: tuple[int, ...]):
    choices = []
    for detection in detections:
        if detection.type not in kinds:
            continue
        tangent, normal = local_coordinates(point, detection)
        half_l = max(1.0, detection.major_length * 0.5)
        half_w = max(1.0, detection.minor_width * 0.5)
        residual = min(abs(abs(tangent) - half_l), abs(abs(normal) - half_w))
        choices.append((residual, detection, tangent, normal))
    return min(choices, key=lambda item: item[0]) if choices else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=0,
                        help="debug limit; zero processes the complete video")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, default=0.0,
                        help="exclusive end; zero decodes to EOF")
    parser.add_argument("--warmup-seconds", type=float, default=0.0,
                        help="decode/process this interval before start without collecting metrics")
    parser.add_argument("--frame-step", type=int, default=1,
                        help="process every Nth decoded frame")
    parser.add_argument("--diagnose-flips", type=int, default=0,
                        help="print detailed scores for this many evenly spaced flips")
    args = parser.parse_args()
    if args.start_seconds < 0.0 or args.end_seconds < 0.0 or \
            args.warmup_seconds < 0.0 or args.frame_step < 1 or \
            args.diagnose_flips < 0:
        parser.error("times must be non-negative and --frame-step must be >= 1")
    if args.end_seconds and args.end_seconds <= args.start_seconds:
        parser.error("--end-seconds must be greater than --start-seconds")
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {args.video}")
    expected_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if fps <= 0.0:
        raise RuntimeError("video reports an invalid frame rate")
    start_frame = int(round(args.start_seconds * fps))
    end_frame = (int(round(args.end_seconds * fps)) if args.end_seconds
                 else expected_frames)
    decode_start = max(0, int(round(
        (args.start_seconds-args.warmup_seconds) * fps)))
    end_frame = min(end_frame, expected_frames)
    if not capture.set(cv2.CAP_PROP_POS_FRAMES, decode_start):
        raise RuntimeError(f"cannot seek to frame {decode_start}")
    print(f"[VIDEO-TEST] window={start_frame/fps:.3f}..{end_frame/fps:.3f}s "
          f"warmup_start={decode_start/fps:.3f}s fps={fps:.3f} "
          f"frame_step={args.frame_step}", flush=True)
    source_steps = []
    unsupported_sources = 0
    portal_flips = 0
    portal_steps = 0
    flip_events = []
    portal_position_errors = []
    portal_side_errors = 0
    mirror_boundary_errors = []
    prior_source = None
    prior_portals: dict[int, Detection] = {}
    processed = 0
    measured = 0
    decoded = 0
    active_frames = 0
    active_source_dropout_frames = 0
    active_source_jump_frames = 0
    candidate_invalid_events = 0
    atomic_display_updates = 0
    source_lock_events = 0
    unexpected_source_relocks = 0
    locked_source_changes = 0
    target_confirm_events = 0
    level_clear_events = 0
    illegal_ray_clears = 0
    invalid_without_display = 0
    measurement_started = False
    ever_active = False
    cleared_since_active = False
    locked_reference = None
    previous_display = None
    final_active_zero = 0
    pipeline_metrics = [0] * 8
    source_candidate_spread = [0.0, 0.0]
    regression_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="portal_video_regression_") as tmp:
        library_path = Path(tmp) / "video_regression.dll"
        compile_api(library_path)
        library = ctypes.CDLL(str(library_path))
        library.video_regression_reset.argtypes = []
        library.video_regression_clear_active_zero.argtypes = []
        library.video_regression_metrics.argtypes = [
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_float)]
        library.video_regression_raw_source.argtypes = [ctypes.POINTER(Detection)]
        library.video_regression_raw_source.restype = ctypes.c_int
        library.video_regression_process.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(Detection), ctypes.c_int,
            ctypes.POINTER(RayResult),
            ctypes.POINTER(RayResult), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_float),
        ]
        library.video_regression_process.restype = ctypes.c_int
        library.video_regression_diagnose_portal.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int,
        ]
        library.video_regression_diagnose_portal.restype = ctypes.c_int
        library.video_regression_reset()
        absolute_frame = decode_start
        while True:
            if absolute_frame >= end_frame:
                break
            ok, frame = capture.read()
            if not ok:
                break
            current_frame = absolute_frame
            absolute_frame += 1
            decoded += 1
            if (current_frame-decode_start) % args.frame_step:
                continue
            collect = current_frame >= start_frame
            if collect and not measurement_started:
                library.video_regression_clear_active_zero()
                measurement_started = True
            if not frame.flags.c_contiguous:
                frame = np.ascontiguousarray(frame)
            output = (Detection * MAX_DETECTIONS)()
            ray = RayResult()
            displayed = RayResult()
            level_state = ctypes.c_int()
            level_events = ctypes.c_uint()
            active_zero = ctypes.c_uint()
            locked_source = (ctypes.c_float * 4)()
            count = library.video_regression_process(
                frame.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
                frame.shape[1], frame.shape[0], frame.strides[0],
                output, MAX_DETECTIONS, ctypes.byref(ray),
                ctypes.byref(displayed), ctypes.byref(level_state),
                ctypes.byref(level_events), ctypes.byref(active_zero),
                locked_source)
            if count < 0:
                raise RuntimeError(
                    f"production pipeline returned {count} at frame {processed}")
            detections = [output[index] for index in range(count)]
            sources = [item for item in detections
                       if item.type == SOURCE and item.direction_valid]
            raw_source = Detection()
            raw_source_valid = bool(library.video_regression_raw_source(
                ctypes.byref(raw_source)))
            if collect and len(sources) > 1:
                unsupported_sources += len(sources) - 1
            if collect and raw_source_valid and not marker_supported(
                    frame, raw_source):
                unsupported_sources += 1
            current_source = sources[0] if len(sources) == 1 else None
            if prior_source is not None and current_source is not None:
                movement = math.hypot(
                    current_source.center_x-prior_source.center_x,
                    current_source.center_y-prior_source.center_y)
                if collect and movement <= 2.0:
                    source_steps.append(angle_delta(prior_source,
                                                    current_source))
            prior_source = current_source

            events = level_events.value
            state = level_state.value
            locked = tuple(float(value) for value in locked_source)
            if events & EVENT_SOURCE_LOCKED:
                if collect:
                    source_lock_events += 1
                if ever_active and not cleared_since_active:
                    unexpected_source_relocks += 1
                cleared_since_active = False
                locked_reference = locked
            if events & EVENT_RAY_COMMITTED:
                ever_active = True
                cleared_since_active = False
                locked_reference = locked
            if events & EVENT_TARGET_CONFIRMED:
                if collect:
                    target_confirm_events += 1
            if events & EVENT_LEVEL_CLEARED:
                if collect:
                    level_clear_events += 1
                if not ever_active or cleared_since_active:
                    illegal_ray_clears += 1
                cleared_since_active = True
                locked_reference = None

            if collect:
                measured += 1
                final_active_zero = active_zero.value
                if events & EVENT_CANDIDATE_INVALID:
                    candidate_invalid_events += 1
                    if state == LEVEL_ACTIVE and displayed.segment_count <= 0:
                        invalid_without_display += 1
                if state == LEVEL_ACTIVE:
                    active_frames += 1
                    if displayed.segment_count <= 0:
                        invalid_without_display += 1
                    if current_source is None:
                        active_source_dropout_frames += 1
                    else:
                        dx = current_source.source_tip_x-locked[0]
                        dy = current_source.source_tip_y-locked[1]
                        direction_dot = (current_source.source_direction_x*locked[2] +
                                         current_source.source_direction_y*locked[3])
                        if dx*dx + dy*dy >= 24.0*24.0 or \
                                direction_dot <= 0.956304756:
                            active_source_jump_frames += 1
                    if locked_reference is not None and any(
                            abs(locked[index]-locked_reference[index]) > 1.0e-5
                            for index in range(4)):
                        locked_source_changes += 1
                current_display = tuple(
                    (displayed.segments[index].start.x,
                     displayed.segments[index].start.y,
                     displayed.segments[index].end.x,
                     displayed.segments[index].end.y)
                    for index in range(displayed.segment_count))
                if previous_display and not current_display and not (
                        events & EVENT_LEVEL_CLEARED):
                    illegal_ray_clears += 1
                if previous_display and current_display and \
                        current_display != previous_display:
                    atomic_display_updates += 1
                previous_display = current_display

            current_portals = {item.type: item for item in detections
                               if item.type in (PORTAL_A, PORTAL_B)}
            for kind, portal in current_portals.items():
                previous = prior_portals.get(kind)
                if collect and previous is not None and math.hypot(
                        portal.center_x-previous.center_x,
                        portal.center_y-previous.center_y) <= 20.0:
                    portal_steps += 1
                    if previous.axis_x*portal.axis_x + \
                            previous.axis_y*portal.axis_y < 0.0:
                        portal_flips += 1
                        flip_events.append({
                            "frame": current_frame,
                            "kind": kind,
                            "previous": portal_snapshot(previous),
                            "current": portal_snapshot(portal),
                        })
            prior_portals = current_portals

            for index in range(max(0, ray.segment_count-1)) if collect else ():
                incoming = ray.segments[index]
                outgoing = ray.segments[index+1]
                jump = math.hypot(outgoing.start.x-incoming.end.x,
                                  outgoing.start.y-incoming.end.y)
                if jump > 4.0:
                    entry = nearest(incoming.end, detections,
                                    (PORTAL_A, PORTAL_B))
                    exit_ = nearest(outgoing.start, detections,
                                    (PORTAL_A, PORTAL_B))
                    if entry and exit_ and entry[1].type != exit_[1].type:
                        entry_u = entry[2] / max(
                            1.0, entry[1].major_length*0.5)
                        exit_u = exit_[2] / max(
                            1.0, exit_[1].major_length*0.5)
                        portal_position_errors.append(
                            abs(exit_u-entry_u)*exit_[1].major_length*0.5)
                        if entry[3]*exit_[3] >= 0.0:
                            portal_side_errors += 1
                else:
                    mirror = nearest(incoming.end, detections, (MIRROR,))
                    if mirror:
                        half_l = max(1.0, mirror[1].major_length*0.5)
                        half_w = max(1.0, mirror[1].minor_width*0.5)
                        mirror_boundary_errors.append(min(
                            abs(abs(mirror[2])-half_l),
                            abs(abs(mirror[3])-half_w)))
            processed += 1
            if processed % 25 == 0 and not args.diagnose_flips:
                print(f"[VIDEO-TEST] progress processed={processed} "
                      f"time={current_frame/fps:.3f}s", flush=True)
            if args.max_frames and processed >= args.max_frames:
                break
        metric_values = (ctypes.c_uint * 8)()
        spread_values = (ctypes.c_float * 2)()
        library.video_regression_metrics(metric_values, spread_values)
        pipeline_metrics = [int(value) for value in metric_values]
        source_candidate_spread = [float(value) for value in spread_values]
        if args.diagnose_flips and flip_events:
            sample_count = min(args.diagnose_flips, len(flip_events))
            sample_indices = sorted(set(
                int(round(value)) for value in
                np.linspace(0, len(flip_events)-1, sample_count)))
            diagnostic_capture = cv2.VideoCapture(str(args.video))
            if not diagnostic_capture.isOpened():
                raise RuntimeError(f"cannot reopen {args.video} for diagnostics")
            for sample_number, event_index in enumerate(sample_indices, 1):
                event = flip_events[event_index]
                if not diagnostic_capture.set(cv2.CAP_PROP_POS_FRAMES,
                                              event["frame"]):
                    raise RuntimeError(
                        f"cannot seek to diagnostic frame {event['frame']}")
                ok, diagnostic_frame = diagnostic_capture.read()
                if not ok:
                    raise RuntimeError(
                        f"cannot decode diagnostic frame {event['frame']}")
                if not diagnostic_frame.flags.c_contiguous:
                    diagnostic_frame = np.ascontiguousarray(diagnostic_frame)
                previous_solid, previous_ring = portal_endpoints(event["previous"])
                current_solid, current_ring = portal_endpoints(event["current"])
                portal_name = "PORTAL_A" if event["kind"] == PORTAL_A else "PORTAL_B"
                print(
                    f"FLIP_SAMPLE {sample_number}/{len(sample_indices)} "
                    f"frame={event['frame']} portal={portal_name} "
                    f"axis_before=({event['previous']['axis_x']:.6f},"
                    f"{event['previous']['axis_y']:.6f}) "
                    f"axis_current=({event['current']['axis_x']:.6f},"
                    f"{event['current']['axis_y']:.6f}) "
                    f"before_endpoints_solid=({previous_solid[0]:.2f},"
                    f"{previous_solid[1]:.2f}) ring=({previous_ring[0]:.2f},"
                    f"{previous_ring[1]:.2f}) current_endpoints_solid=("
                    f"{current_solid[0]:.2f},{current_solid[1]:.2f}) ring=("
                    f"{current_ring[0]:.2f},{current_ring[1]:.2f})",
                    flush=True)
                library.video_regression_diagnose_portal(
                    diagnostic_frame.ctypes.data_as(
                        ctypes.POINTER(ctypes.c_uint8)),
                    diagnostic_frame.shape[1], diagnostic_frame.shape[0],
                    diagnostic_frame.strides[0], event["kind"])
            diagnostic_capture.release()
            for kind in (PORTAL_A, PORTAL_B):
                class_events = [event for event in flip_events
                                if event["kind"] == kind]
                if not class_events:
                    continue
                frames = [event["frame"] for event in class_events]
                centers_x = [event["current"]["center_x"]
                             for event in class_events]
                centers_y = [event["current"]["center_y"]
                             for event in class_events]
                angles = [event["current"]["angle_deg"]
                          for event in class_events]
                portal_name = "PORTAL_A" if kind == PORTAL_A else "PORTAL_B"
                print(
                    f"FLIP_DISTRIBUTION portal={portal_name} count={len(class_events)} "
                    f"frame_range={min(frames)}..{max(frames)} "
                    f"center_x_range={min(centers_x):.1f}..{max(centers_x):.1f} "
                    f"center_y_range={min(centers_y):.1f}..{max(centers_y):.1f} "
                    f"angle_range={min(angles):.1f}..{max(angles):.1f}")
        unload_api(library)
    capture.release()
    if not args.max_frames and not args.start_seconds and not args.end_seconds \
            and args.frame_step == 1 and abs(processed-expected_frames) > 1:
        raise AssertionError(f"decoded {processed}/{expected_frames} frames")
    if not source_steps:
        raise AssertionError("no stationary SOURCE run was observed")
    source_p95 = float(np.percentile(source_steps, 95))
    failures = []
    if source_p95 > 3.0:
        failures.append(f"SOURCE direction P95 {source_p95:.2f} > 3 degrees")
    if unsupported_sources:
        failures.append(f"{unsupported_sources} SOURCE detections lacked the marker pair")
    if portal_flips:
        failures.append(f"{portal_flips}/{portal_steps} Portal 180-degree flips")
    if portal_position_errors and max(portal_position_errors) > 6.0:
        failures.append(f"Portal local-position error {max(portal_position_errors):.2f} > 6 px")
    if portal_side_errors:
        failures.append(f"{portal_side_errors} Portal transitions did not switch sides")
    if mirror_boundary_errors and max(mirror_boundary_errors) > 1.5:
        failures.append(f"MIRROR boundary residual {max(mirror_boundary_errors):.2f} > 1.5 px")
    if not active_frames:
        failures.append("window never reached LEVEL_ACTIVE")
    if final_active_zero:
        failures.append(f"active_zero_ray_frames={final_active_zero}")
    if illegal_ray_clears:
        failures.append(f"{illegal_ray_clears} ray clears lacked TARGET confirmation")
    if invalid_without_display:
        failures.append(f"{invalid_without_display} ACTIVE invalid/zero display frames")
    print(f"[VIDEO-TEST] DONE  window regression "
          f"elapsed={time.perf_counter()-regression_started:.3f}s", flush=True)
    print(f"decoded={decoded} processed={processed} measured={measured} "
          f"active_frames={active_frames} active_zero_ray_frames={final_active_zero}")
    print(f"source_dropout_frames={active_source_dropout_frames} "
          f"source_jump_frames={active_source_jump_frames} "
          f"source_lock_events={source_lock_events} "
          f"unexpected_source_relocks={unexpected_source_relocks} "
          f"locked_source_changes={locked_source_changes}")
    print(f"candidate_invalid_events={candidate_invalid_events} "
          f"atomic_display_updates={atomic_display_updates} "
          f"target_confirm_events={target_confirm_events} "
          f"level_clear_events={level_clear_events} "
          f"illegal_ray_clears={illegal_ray_clears}")
    observation_rate = (pipeline_metrics[1]/pipeline_metrics[0]
                        if pipeline_metrics[0] else 0.0)
    print(f"raw_observation_rate={observation_rate:.3f}/frame "
          f"direct_observations={pipeline_metrics[2]} "
          f"pose_commits={pipeline_metrics[3]} "
          f"source_ray_clears={pipeline_metrics[4]} "
          f"committed_ray_updates={pipeline_metrics[5]} "
          f"topology_changes={pipeline_metrics[6]} "
          f"portal_direction_flip_rejections={pipeline_metrics[7]}")
    print(f"frames={processed} source_stationary_steps={len(source_steps)} "
          f"source_p95={source_p95:.2f} unsupported_source={unsupported_sources}")
    print(f"portal_steps={portal_steps} portal_flips={portal_flips} "
          f"portal_transitions={len(portal_position_errors)} "
          f"portal_max_error={max(portal_position_errors, default=0.0):.2f}")
    print(f"mirror_hits={len(mirror_boundary_errors)} "
          f"mirror_max_residual={max(mirror_boundary_errors, default=0.0):.2f}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
