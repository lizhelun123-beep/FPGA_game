"""Export original photo observations through the canonical C game for a static viewer.

Run from the repository root: python -m pc_vision.export_web_scenes --cc PATH_TO_GCC
The replay clock below is synthetic offline time, never photo exposure/live freshness.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

from .native import NativeGame, NativeVision, SRC, TERMINATIONS
from .scene_protocol import TYPES

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pc_vision/game_config.json"
BUILD = ROOT / "output/build/web_preview"
SOURCE_NAMES = (
    "game_session.c", "ray_game.c", "game_scene_adapter.c", "game_app.c",
    "game_input.c", "game_evdev.c", "game_loop.c", "game_pump.c",
    "game_render.c", "vision_overlay.c",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_game(compiler):
    tools = SRC.parent / "tools"
    BUILD.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(tools / "generate_game_config.py"),
                    "--config", str(CONFIG), "--output", str(BUILD / "game_config.h")],
                   check=True, cwd=ROOT, timeout=30)
    executable = BUILD / ("game_offline.exe" if os.name == "nt" else "game_offline")
    sources = [*(SRC / name for name in SOURCE_NAMES), BUILD / "game_config.c",
               tools / "game_offline.c"]
    # Older MinGW defaults PRIu64 to Microsoft's I64 format, rejected by -pedantic.
    # Select its standard stdio implementation without weakening format checks.
    stdio = ["-D__USE_MINGW_ANSI_STDIO=1"] if os.name == "nt" else []
    subprocess.run([compiler, *stdio, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", f"-I{SRC}", f"-I{BUILD}", *(str(p) for p in sources),
                    "-lm", "-o", str(executable)], check=True, cwd=ROOT, timeout=120)
    return executable


def fields(line):
    return dict(item.split("=", 1) for item in line.split() if "=" in item)


def point(value):
    values = [float(v) for v in value.split(",")]
    if len(values) != 2 or not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid C snapshot point")
    return values


def enum_name(names, value):
    index = int(value)
    if not 0 <= index < len(names):
        raise ValueError("Unknown C snapshot enum")
    return names[index]


def parse_snapshot(lines):
    """Parse exactly one complete game_app_write_view response; reject truncation."""
    headers = [fields(line) for line in lines if line.startswith("mapping=")]
    rays = [fields(line) for line in lines if line.startswith("ray ")]
    if len(headers) != 1 or len(rays) != 1:
        raise ValueError("Expected one complete C snapshot")
    header, ray = headers[0], rays[0]
    objects, hits, segments = [], [], []
    for line in lines:
        row = fields(line)
        if line.startswith("model="):
            if int(row["model"]) != len(objects):
                raise ValueError("Missing or reordered C model")
            objects.append(dict(type=enum_name(TYPES, row["type"]),
                                **{key: point(row[key]) for key in
                                   ("center", "axis", "size", "tip", "direction")},
                                directionValid=bool(int(row["valid"]))))
        elif line.startswith("hit="):
            if int(row["hit"]) != len(hits):
                raise ValueError("Missing or reordered C hit")
            hits.append(enum_name(TYPES, row["type"]))
        elif line.startswith("segment="):
            if int(row["segment"]) != len(segments):
                raise ValueError("Missing or reordered C ray segment")
            segments.append(dict(start=point(row["start"]), end=point(row["end"])))
    if len(hits) != int(ray["hits"]) or len(segments) != int(ray["segments"]):
        raise ValueError("Incomplete C ray result")
    return dict(generation=int(header["generation"]), sequence=int(header["sequence"]),
                capturedMs=int(header["captured_ms"]), valid=bool(int(header["valid"])),
                sceneStatus=int(header["scene_status"]),
                budgetExceeded=bool(int(header["budget_exceeded"])),
                state=int(header["state"]), ready=bool(int(header["ready"])),
                elapsedMs=int(header["elapsed_ms"]), remainingMs=int(header["remaining_ms"]),
                stars=int(header["stars"]), objects=objects,
                ray=dict(success=bool(int(ray["success"])),
                         termination=enum_name(TERMINATIONS, ray["termination"]),
                         interactions=int(ray["interactions"]), hits=hits, segments=segments))


def export(compiler, destination):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))["board_game"]
    executable = build_game(compiler)
    levels, photo_records = [], []
    native = core = None
    try:
        native = NativeVision(compiler)
        core = NativeGame(executable=executable)
        for sequence, level in enumerate(config["levels"], 1):
            photo = ROOT / level["reference"]
            pixels = cv2.imdecode(np.fromfile(str(photo), dtype=np.uint8), cv2.IMREAD_COLOR)
            if pixels is None:
                raise ValueError(f"Cannot decode {photo}")
            started = time.monotonic()
            scene = native.detect(pixels, sequence)
            detection_ms = (time.monotonic() - started) * 1000
            expected = {obj["type"] for obj in level["objects"]}
            if not scene.valid or {obj.type for obj in scene.objects} != expected:
                raise ValueError(f"Photo {photo.name} did not produce the configured classes")
            # Frozen photo demonstration: submit on an explicit offline replay clock.
            # No START command, periodic timestamp refresh, TTL change, or live claim.
            replay_ms = sequence * 1000
            core.command(f"select {replay_ms} {level['id']}")
            generation = int(core.state["generation"])
            frame = core.scene_command(scene, replay_ms, generation, captured_ms=replay_ms)
            response = core.command(frame)
            if any(line.startswith("status=") and line != "status=0" for line in response):
                raise ValueError(f"C core rejected photo {photo.name}: {response[0]}")
            lines = core.command("snapshot")
            raw = "\n".join(lines) + "\n"
            (BUILD / f"level_{level['id']}.snapshot.txt").write_text(raw, encoding="utf-8")
            snapshot = parse_snapshot(lines)
            if (not snapshot["valid"] or snapshot["state"] != 1 or
                    snapshot["generation"] != generation or
                    len(snapshot["objects"]) != len(expected) or
                    {obj["type"] for obj in snapshot["objects"]} != expected):
                raise ValueError(f"C snapshot invalid or not preparing for {photo.name}")
            levels.append(dict(id=level["id"], reference=level["reference"],
                               motion=[dict(type=obj["type"], motion=obj["motion"])
                                       for obj in level["objects"]], snapshot=snapshot))
            photo_records.append(dict(reference=level["reference"], sha256=digest(photo),
                                      detectionMs=round(detection_ms, 3),
                                      detectorCaptureMs=scene.capture_ms,
                                      replayCapturedMs=replay_ms,
                                      snapshotSha256=hashlib.sha256(raw.encode()).hexdigest()))
    finally:
        if core is not None:
            core.close()
        if native is not None:
            native.close()
    data = dict(schemaVersion=1, coordinateSpace=config["coordinate_space"],
                width=config["width"], height=config["height"],
                maxVisibleSegments=config["render_max_ray_segments"], levels=levels,
                provenance=dict(mode="offline-photo-preview", configSha256=digest(CONFIG),
                                timeBasis="synthetic offline replay; not exposure or live freshness",
                                nativeCoreSha256=digest(executable),
                                detectorSha256=digest(native.path), photos=photo_records))
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    restored = json.loads(encoded)
    for level in restored["levels"]:
        raw = (BUILD / f"level_{level['id']}.snapshot.txt").read_text(encoding="utf-8")
        if level["snapshot"] != parse_snapshot(raw.splitlines()):
            raise ValueError("JSON roundtrip differs from original C snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(encoded, encoding="utf-8")
    review = dict(status="PASS_OFFLINE_PHOTO_EXPORT", output=str(destination.relative_to(ROOT)),
                  outputSha256=digest(destination), compiler=compiler,
                  scope="host C detector + adapter + solver, no board operations",
                  snapshotRoundtrip="all fields equal to retained C text",
                  levels=[dict(id=level["id"], models=len(level["snapshot"]["objects"]),
                               segments=len(level["snapshot"]["ray"]["segments"]),
                               success=level["snapshot"]["ray"]["success"],
                               termination=level["snapshot"]["ray"]["termination"])
                          for level in levels])
    (BUILD / "review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=shutil.which("gcc"), help="Existing host GCC executable")
    parser.add_argument("--output", type=Path, default=ROOT / "pc_vision/web/data/scenes.json")
    args = parser.parse_args()
    if not args.cc:
        parser.error("Specify --cc with an existing host GCC executable")
    # Compiler scratch and final artifacts stay within the project on E:.
    scratch = BUILD / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(scratch)
    print(json.dumps(export(args.cc, args.output.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
