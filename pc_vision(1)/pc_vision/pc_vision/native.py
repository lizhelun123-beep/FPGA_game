"""Host C processes avoid a Python/GCC bitness dependency; no Python physics."""
import hashlib
import importlib.util
import json
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


def build_bridge(compiler=None, real_scene=False):
    compiler = compiler or shutil.which("gcc") or shutil.which("gcc.exe")
    if not compiler:
        raise RuntimeError("Game mode requires host GCC on PATH (MinGW on Windows)")
    cross_linux = os.name == "nt" and "linux" in Path(compiler).name.lower()
    inputs = [ROOT / "host_bridge.c", *(SRC / name for name in
        ("vision_ps.c", "green_target_detector.c", "ray_game.c", "scene_protocol.c"))]
    headers = [SRC / name for name in ("vision_ps.h", "vision_ps_config.h", "ray_game.h",
                                      "green_target_detector.h", "scene_protocol.h")]
    vendor_sources = []
    if real_scene:
        vendor = ROOT.parent / "third_party/apriltag"
        vendor_sources = [vendor / name for name in ("apriltag.c", "apriltag_quad_thresh.c", "tag36h11.c")]
        vendor_sources += sorted((vendor / "common").glob("*.c"))
        inputs += [SRC / name for name in ("vision_portal.c", "vision_stabilizer.c",
                   "game_session.c", "game_scene_adapter.c")]
        headers += [*sorted(SRC.glob("*.h")), *sorted(vendor.glob("*.h")),
                    *sorted((vendor / "common").glob("*.h"))]
    digest = hashlib.sha256(str(compiler).encode())
    digest.update(Path(__file__).read_bytes())
    digest.update(str(real_scene).encode())
    for path in inputs + headers + vendor_sources:
        digest.update(path.read_bytes())
    if real_scene:
        config_path = ROOT / "game_config.json"
        generator_path = SRC.parent / "tools/generate_game_config.py"
        digest.update(config_path.read_bytes())
        digest.update(generator_path.read_bytes())
    directory = ROOT / "output/native"
    executable = directory / ("scene_"+digest.hexdigest()[:16]+(".elf" if cross_linux else ".exe" if os.name == "nt" else ""))
    if not executable.exists():
        directory.mkdir(parents=True, exist_ok=True)
        extra = []
        if real_scene:
            spec = importlib.util.spec_from_file_location("canonical_config_generator", generator_path)
            generator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generator)
            generated = directory / ("real_config_" + digest.hexdigest()[:16] + ".c")
            generated.write_text(generator.generate(json.loads(config_path.read_text(encoding="utf-8"))), encoding="utf-8")
            inputs.append(generated)
            objects = directory / ("apriltag_" + digest.hexdigest()[:16])
            objects.mkdir(exist_ok=True)
            platform_flags = ["-D_WIN32_WINNT=0x0601"] if os.name == "nt" and not cross_linux else ["-pthread"]
            subprocess.run([str(compiler), "-std=gnu99", "-O2", "-w", "-ffunction-sections", "-c", *platform_flags,
                            f"-I{vendor}", *(str(p) for p in vendor_sources)],
                           cwd=objects, check=True, timeout=90)
            extra = ["-DVISION_WITH_APRILTAG=1", "-Wl,--gc-sections", *platform_flags, f"-I{vendor}",
                     *(str(p) for p in sorted(objects.glob("*.o")))]
        subprocess.run([str(compiler), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        f"-I{SRC}", *(str(p) for p in inputs), *extra, "-lm", "-o", str(executable)], check=True, timeout=60)
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
    def __init__(self, compiler=None, recognition=True, real_scene=False, physics_process=True):
        self.path = build_bridge(compiler, real_scene)
        self.detector = HostProcess(self.path) if recognition else None
        try:
            self.physics = HostProcess(self.path) if physics_process else None
        except Exception:
            if self.detector:
                self.detector.close()
            raise

    def configure_portals(self, templates):
        rows = []
        for portal in ("PORTAL_A", "PORTAL_B"):
            template = templates[portal]
            if template.get("unit") != "mm" or template["ids"] != ([10,11,12] if portal == "PORTAL_A" else [20,21,22]):
                raise ValueError("Portal templates require measured mm and canonical IDs")
            rows.extend(np.asarray(template["corners"], dtype=float).reshape(24))
            rows.extend(template["center"])
            rows.extend(template["axis"])
            rows.extend(template["effective_size"])
            rows.extend([template["reference_scale_px_per_mm"], template["image_handedness"]])
        data = np.asarray(rows, dtype="<f4")
        if data.shape != (64,) or not np.isfinite(data).all():
            raise ValueError("Invalid joint Portal template")
        self.detector.send(b"P" + data.tobytes())
        if struct.unpack("<i", self.detector.receive(4))[0]:
            raise ValueError("C detector rejected Portal configuration")

    def configure_marker_geometry(self, physical):
        mirror, wall = physical["MIRROR"], physical["WALL"]
        mirror_span = 2*mirror["black_dot_center_offset"]
        wall_span = wall["body_size"][0]-2*(wall["white_mark_end_gap"]+wall["white_mark_width"]/2)
        rows = [mirror["reflective_line_length"]/mirror_span,
                mirror["body_size"][0]/mirror_span, mirror["body_size"][1]/mirror_span,
                wall["body_size"][0]/wall_span,
                wall["body_size"][1]/wall["white_mark_span"]]
        data = np.asarray(rows, dtype="<f4")
        if not np.isfinite(data).all() or np.any(data <= 0):
            raise ValueError("Invalid measured marker geometry")
        self.detector.send(b"M" + data.tobytes())
        if struct.unpack("<i", self.detector.receive(4))[0]:
            raise ValueError("C detector rejected measured marker geometry")

    def portal_tags(self, frame=None):
        if frame is None:
            self.detector.send(b"G")
        else:
            frame = np.ascontiguousarray(frame, dtype=np.uint8)
            if frame.shape != (720, 1280, 3):
                raise ValueError("Portal input must be unscaled 1280x720 BGR")
            self.detector.send(b"A" + frame.tobytes())
        count = struct.unpack("<i", self.detector.receive(4))[0]
        if not 0 <= count <= 6:
            raise RuntimeError("C Portal scan failed")
        rows = np.frombuffer(self.detector.receive(count*11*4), dtype="<f4").reshape(count, 11)
        return [dict(id=int(r[0]), corners=r[1:9].reshape(4, 2).tolist(),
                     margin=float(r[9]), hamming=int(r[10])) for r in rows]

    def close(self):
        if self.detector:
            self.detector.close()
        if self.physics:
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


class NativeRealScene(NativeVision):
    """One C process owns detection, the pose commit and game_session/ray_game.

    Python supplies file/camera pixels and an external monotonic clock, and
    renders the returned atomic snapshot. No Python intersections or scoring.
    """
    def __init__(self, compiler=None):
        super().__init__(compiler, real_scene=True, physics_process=False)
        try:
            cfg = json.loads((ROOT / "game_config.json").read_text(encoding="utf-8"))
            self.configure_portals(cfg["real_scene"]["portal_templates"])
            self.configure_marker_geometry(cfg["real_scene"]["physical_geometry_mm"])
        except BaseException:
            self.close()
            raise
        self.state = {}

    def _snapshot(self):
        line = self.detector.process.stdout.readline(16384)
        if not line.endswith(b"\n"):
            raise RuntimeError("Incomplete native real-scene snapshot")
        self.state = json.loads(line)
        return self.state

    def select(self, level, now_ms):
        self.detector.send(b"L" + struct.pack("<IQ", level, now_ms))
        return self._snapshot()

    def observe(self, frame, generation, sequence, captured_ms, algorithm="B", now_ms=None):
        frame = np.ascontiguousarray(frame, dtype=np.uint8)
        if frame.shape != (720, 1280, 3):
            raise ValueError("Real-scene input must be unscaled 1280x720 BGR")
        mode = {"A": 0, "B": 1, None: 2}[algorithm]
        dispatch_ms = captured_ms if now_ms is None else now_ms
        self.detector.send(b"E" + struct.pack("<QQQQi", generation, sequence, captured_ms, dispatch_ms, mode) + frame.tobytes())
        return decode(self.detector.process.stdout.readline(829))

    def commit(self, now_ms):
        self.detector.send(b"F" + struct.pack("<Q", now_ms))
        return self._snapshot()

    def tick(self, now_ms):
        self.detector.send(b"K" + struct.pack("<Q", now_ms))
        return self._snapshot()

    def start(self, now_ms):
        self.detector.send(b"T" + struct.pack("<Q", now_ms))
        return self._snapshot()


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
