"""Host C processes avoid a Python/GCC bitness dependency; no Python physics."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np

from .scene_protocol import decode, TYPES

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "color_test/software/vision_ps_baremetal/src"
TERMINATIONS = ("NO_SOURCE", "BOUNDARY", "WALL", "TARGET", "MISSING_PORTAL",
                "MAX_INTERACTIONS", "INVALID_INPUT")


def build_bridge(compiler=None):
    compiler = compiler or shutil.which("gcc") or shutil.which("gcc.exe")
    if not compiler:
        raise RuntimeError("Game mode requires host GCC on PATH (MinGW on Windows)")
    inputs = [ROOT / "host_bridge.c", *(SRC / name for name in
        ("vision_ps.c", "green_target_detector.c", "ray_game.c", "scene_protocol.c"))]
    headers = [SRC / name for name in ("vision_ps.h", "vision_ps_config.h", "ray_game.h",
                                      "green_target_detector.h", "scene_protocol.h")]
    digest = hashlib.sha256(str(compiler).encode())
    for path in inputs + headers:
        digest.update(path.read_bytes())
    directory = ROOT / "output/native"
    executable = directory / ("scene_"+digest.hexdigest()[:16]+(".exe" if os.name == "nt" else ""))
    if not executable.exists():
        directory.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(compiler), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        f"-I{SRC}", *(str(p) for p in inputs), "-lm", "-o", str(executable)], check=True, timeout=60)
    return executable


class HostProcess:
    def __init__(self, executable):
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, bufsize=0,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if self.process.stdout.readline() != b"SCENE_HOST_V1\n":
            self.close()
            raise RuntimeError("Host bridge handshake failed")

    def send(self, data):
        offset = 0
        while offset < len(data):
            n = self.process.stdin.write(data[offset:])
            if not n:
                raise RuntimeError("Host bridge pipe closed")
            offset += n

    def receive(self, count):
        data = bytearray()
        while len(data) < count:
            part = self.process.stdout.read(count-len(data))
            if not part:
                raise RuntimeError("Host bridge stopped before complete response")
            data.extend(part)
        return data

    def close(self):
        if self.process.poll() is None:
            try:
                self.send(b"Q")
                self.process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()


class NativeVision:
    def __init__(self, compiler=None, recognition=True):
        self.path = build_bridge(compiler)
        self.detector = HostProcess(self.path) if recognition else None
        try:
            self.physics = HostProcess(self.path)
        except Exception:
            if self.detector:
                self.detector.close()
            raise

    def close(self):
        if self.detector:
            self.detector.close()
        self.physics.close()

    def detect(self, frame, sequence):
        frame = np.ascontiguousarray(frame, dtype=np.uint8)
        if frame.shape != (720, 1280, 3):
            raise ValueError("Photo game requires unscaled 1280x720 BGR input; calibration uses these pixels")
        self.detector.send(b"D"+struct.pack("<I", sequence)+frame.tobytes())
        line = self.detector.process.stdout.readline(829)
        return decode(line)

    def trace(self, objects, width, height, scale=100):
        rows = np.asarray([[TYPES.index(o.type), *o.center, *o.axis, *o.size,
                            *o.source_tip, *o.direction, int(o.direction_valid)]
                           for o in objects], dtype="<f4").reshape(-1, 12)
        self.physics.send(b"R"+struct.pack("<ifff", len(objects), width, height, scale)+rows.tobytes())
        reply = self.physics.receive(4+17*4*4+21*4)
        if struct.unpack_from("<i", reply)[0]:
            raise ValueError("C ray trace rejected model geometry")
        segments = np.frombuffer(reply, dtype="<f4", count=68, offset=4).reshape(17, 4)
        info = np.frombuffer(reply, dtype="<i4", count=21, offset=4+68*4)
        return dict(segments=segments[:info[0]].tolist(), interactions=int(info[1]),
                    success=bool(info[2]), termination=TERMINATIONS[info[3]],
                    hits=[TYPES[i] for i in info[5:5+info[4]]])


class NativeGame:
    """Transport only. ONE game_offline process owns rules, input and rendering.

    No Python geometry, hit testing, score, timer or drawing. The same commands
    can be saved as a plain text replay and run without this viewer.
    """
    def __init__(self, assets, executable=None):
        executable = executable or ROOT.parent / "output/build/game_app/game_offline.exe"
        if not Path(executable).is_file():
            raise RuntimeError("Build first: ./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -OfflinePackage")
        self.process = subprocess.Popen([str(executable), "--assets", str(assets)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.state = {}
        self.transcript = []
        try:
            self.command("snapshot")
        except BaseException:
            self.close()
            raise

    send = HostProcess.send
    receive = HostProcess.receive

    def command(self, commands):
        import re
        self.send((commands+"\nsync\n").encode("ascii"))
        lines = []
        for _ in range(2048):
            line = self.process.stdout.readline(4096)
            if not line:
                raise RuntimeError("Native game exited before command completion")
            if line == b"READY\n":
                break
            lines.append(line.decode("utf-8").rstrip())
        else:
            raise RuntimeError("Native game response exceeded bound")
        for line in lines:
            if line.startswith("mapping="):
                self.state = dict(re.findall(r"(\w+)=([^ ]+)", line))
        self.transcript.append(commands)
        return lines

    @staticmethod
    def scene_command(scene, now_ms, generation, captured_ms=None):
        # Old scene-v1 files without a trustworthy capture clock stay old. Never
        # turn receipt time into capture time to bypass the 250ms freshness gate.
        captured_ms = scene.capture_ms if captured_ms is None else captured_ms
        valid = scene.valid and all(o.axis_valid for o in scene.objects)
        rows = [" ".join(map(str, (TYPES.index(o.type), *o.center, *o.axis,
                                  int(o.direction_valid), *o.source_direction))) for o in scene.objects]
        return "\n".join([f"frame {now_ms} {generation} {scene.frame} {captured_ms} {int(valid)} 0 {len(rows)}", *rows])

    def image(self):
        self.send(b"present\n")
        header = self.process.stdout.readline(128).decode("ascii").split()
        if header != ["BGR", "1280", "800", "3072000"]:
            raise RuntimeError(f"Invalid native canvas header: {header!r}")
        return np.frombuffer(self.receive(3072000), dtype=np.uint8).reshape(800, 1280, 3).copy()

    def close(self):
        if self.process.poll() is None:
            try:
                self.send(b"quit\n")
                self.process.wait(timeout=2)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
