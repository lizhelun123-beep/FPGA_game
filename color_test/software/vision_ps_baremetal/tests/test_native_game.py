"""Full native game acceptance, reusing game_offline and the canonical detector.

Time/movement fixtures are explicitly simulated. Photographs use unmodified
1280x720 input and the existing C detector. No devices or hardware libraries.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from pc_vision.native import NativeGame, NativeVision
from pc_vision.game_app import read_photo
from pc_vision.scene_protocol import Scene

CONFIG = json.loads((ROOT/"pc_vision/game_config.json").read_text(encoding="utf-8"))
TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")


def fields(line):
    return dict(re.findall(r"(\w+)=([^ ]+)", line))


def fixture(level, unsolved=False, edit=None):
    rows = []
    for original in CONFIG["board_game"]["levels"][level-1]["objects"]:
        obj = dict(original)
        if unsolved and level == 1 and obj["type"] == "SOURCE":
            obj["axis"] = [0, 1]
        if unsolved and level == 2 and obj["type"] == "PORTAL_A":
            obj.update(center=[600, 600], axis=[1, 0])
        if edit:
            edit(obj)
        rows.append(" ".join(map(str, (TYPES.index(obj["type"]), *obj["center"], *obj["axis"],
                                      int(obj["type"] == "SOURCE"), *obj["axis"]))))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    executable, assets = args.executable.resolve(), args.assets.resolve()
    checks = []
    photos, shots, evidence = [], {}, {}
    g = NativeGame(assets, executable)
    native = None
    shot_at = []
    seq = 0

    def image(name, origin):
        data = g.image()
        Image.fromarray(data[:, :, ::-1]).save(out/f"{name}.png")
        shots[name] = sha256(data.tobytes()).hexdigest()
        evidence[name] = dict(origin=origin, snapshot=dict(g.state), sha256_bgr=shots[name])
        shot_at.append((len(g.transcript), name))

    def submit(level, now, unsolved=False, edit=None, generation=None, valid=1, held=0, captured=None):
        nonlocal seq
        seq += 1
        rows = fixture(level, unsolved, edit)
        generation = int(g.state["generation"]) if generation is None else generation
        captured = now if captured is None else captured
        return g.command("\n".join([f"frame {now} {generation} {seq} {captured} {valid} {held} {len(rows)}", *rows]))

    def select(level, now):
        g.command(f"select {now} {level}")

    try:
        g.command("input 0 1\nleft 0 0")
        image("menu", "native C initial menu")
        native = NativeVision()
        for level, name in enumerate(("075.png", "076.png", "077.png"), 1):
            scene = native.detect(read_photo(ROOT/"sample_photo"/name), level)
            assert scene.valid and scene.image_size == (1280, 720)
            assert set(o.type for o in scene.objects) == {o["type"] for o in CONFIG["board_game"]["levels"][level-1]["objects"]}
            select(level, level*100)
            # Host bridge capture_ms is explicitly 0. The following capture
            # stamps belong to this simulated dispatch fixture, not a board.
            stamp = level*100+1
            replayed = Scene.from_record(scene.record())
            g.command(NativeGame.scene_command(replayed, stamp, int(g.state["generation"]), stamp))
            assert g.state["valid"] == "1"
            assert g.state["ready"] == ("1" if level == 3 else "0")
            original = scene.record()
            assert Scene.from_record(original) == scene
            photos.append(dict(source=name, detector_scene=original, dispatch_ms=stamp,
                               generation=int(g.state["generation"]), result=dict(g.state)))
            image(f"photo_{name[:3]}", "actual canonical C detection / simulated dispatch clock")
        native.close()
        native = None
        checks.append("075/076/077 actual C detector -> unchanged adapter/session -> cached C compositor; scene-v1 round trip; 077 remains unsolved")

        # Real menu hit regions and repeat-click handling, no Python hit test.
        g.command("pointer 400 240 114\nleft 400 1")
        gen = g.state["generation"]
        g.command("left 400 1")
        assert g.state["generation"] == gen and g.state["level"] == "3"
        g.command("left 400 0")
        assert int(g.state["generation"]) == int(gen)+1 and g.state["level"] == "1"
        submit(1, 401, True)
        image("level1_prepare", "synthetic SOURCE rotation, shared original fixture")
        g.command("pointer 402 640 700\nleft 402 1\nleft 402 0")
        assert g.state["state"] == "2"
        image("level1_running", "synthetic motion / real native mouse path")
        submit(1, 1402)
        assert g.state["state"] == "3" and g.state["stars"] == "3"
        image("level1_clear", "synthetic motion with original solved template pose")

        select(2, 2000)
        old = int(g.state["generation"])-1
        submit(1, 2001, generation=old)
        assert g.state["valid"] == "0"
        submit(2, 2002, True)
        image("level2_prepare", "synthetic PORTAL_A free pose, all fixed anchors unchanged")
        g.command("start 2003")
        submit(2, 62003)
        assert g.state["state"] == "3" and g.state["stars"] == "2"
        image("level2_clear", "synthetic portal movement / exact 60s two-star boundary")

        select(3, 63000)
        lines = submit(3, 63001)
        assert g.state["ready"] == "1"
        ray = fields(next(s for s in lines if s.startswith("ray ")))
        assert ray["success"] == "0"
        g.command("start 63002")
        image("level3_running", "original unsolved 077 anchors, no template changes")
        lines = g.command("snapshot")
        incoming = fields(next(s for s in lines if s.startswith("segment=1 ")))
        a = tuple(map(float, incoming["start"].split(",")))
        b = tuple(map(float, incoming["end"].split(",")))
        target = next(o for o in CONFIG["board_game"]["levels"][2]["objects"] if o["type"] == "TARGET")["center"]
        dx, dy = b[0]-a[0], b[1]-a[1]
        norm = math.hypot(dx, dy)
        dx, dy = dx/norm, dy/norm
        center = (target[0], a[1]+(target[0]-a[0])*dy/dx)
        vx, vy = target[0]-center[0], target[1]-center[1]
        norm = math.hypot(vx, vy)
        # The existing test_game_session.c MIRROR-only bisector fixture,
        # derived from the PUBLIC canonical ray; never a second solver.
        def mirror(obj):
            if obj["type"] == "MIRROR":
                obj.update(center=center, axis=[dx+vx/norm, dy+vy/norm])
        lines = submit(3, 183002, edit=mirror)
        assert g.state["state"] == "3" and g.state["stars"] == "1"
        image("level3_clear", "synthetic MIRROR-only movement / original 077 unchanged / 120s one-star boundary")
        checks.append("complete mouse select/prepare/explicit start/run/clear/skip; source rotate_only, portal free, mirror free; exact 3/2/1-star native frames")

        # A stale or held nominally solved scene cannot end a running game.
        select(1, 184000)
        submit(1, 184001, True)
        g.command("start 184002")
        submit(1, 184253, captured=184002)
        assert g.state["state"] == "2" and g.state["valid"] == "0"
        image("stale", "synthetic age=251ms rejected, timer continues")
        submit(1, 184254, held=1)
        assert g.state["state"] == "2"
        g.command("input 184255 0")
        image("input_lost", "explicit offline input disconnect, timer continues")
        g.command("tick 364002")
        assert g.state["state"] == "4" and g.state["stars"] == "0"
        image("timeout", "no new observations, exact 180s timeout")
        g.command("input 364003 1")
        submit(1, 364004)
        assert g.state["state"] == "4" and g.state["stars"] == "0"
        checks.append("old generation/251ms stale/held/input loss cannot clear; idle exact 180s timeout and terminal freeze")

        base = 365000
        for elapsed, stars in ((59999, 3), (60000, 2), (119999, 2), (120000, 1), (179999, 1), (180000, 0)):
            select(1, base)
            submit(1, base+1, True)
            g.command(f"start {base+2}")
            submit(1, base+2+elapsed)
            assert int(g.state["stars"]) == stars
            assert g.state["state"] == ("4" if stars == 0 else "3")
            base += elapsed+1000
        checks.append("cached native path: 59999/60000/119999/120000/179999/180000ms star boundaries")
        resources = g.command("resources")
        assert "assets_loaded=1" in resources[0] and "asset_bytes=13956928" in resources[0]
        commands = list(g.transcript)
    finally:
        if native:
            native.close()
        g.close()
    assert g.process.returncode == 0 and g.process.stdin.closed and g.process.stdout.closed
    (out/"events.replay").write_text("\n".join(commands)+"\nrender final.ppm\nquit\n", encoding="ascii")
    (out/"photo_scenes.json").write_text(json.dumps(photos, indent=2)+"\n", encoding="utf-8")
    # Execute identical events through a fresh process. Images are read only at
    # matching publication boundaries; all hashes must match byte for byte.
    repeated = NativeGame(assets, executable)
    try:
        by_index = dict(shot_at)
        for index, command in enumerate(commands[1:], 2):
            repeated.command(command)
            if index in by_index:
                name = by_index[index]
                assert sha256(repeated.image().tobytes()).hexdigest() == shots[name], name
    finally:
        repeated.close()
    checks.append(f"two identical native executions: {len(shots)} representative BGR image hashes; published scene/ray/timer/score remain coherent")

    pack = assets.read_bytes()
    with tempfile.TemporaryDirectory(dir=out) as folder:
        path = Path(folder)/"test.bin"
        for name, data in (("truncated", pack[:-1]), ("extra", pack+b"x"),
                           ("corrupt", pack[:100]+bytes([pack[100]^1])+pack[101:]),
                           ("wrong_geometry", pack[:20]+bytes([pack[20]^1])+pack[21:]),
                           ("header_count", pack[:16]+struct.pack("<I", 1)+pack[20:])):
            path.write_bytes(data)
            result = subprocess.run([str(executable), "--assets", str(path)], input=b"quit\n", capture_output=True, timeout=10)
            assert result.returncode == 2 and b"Asset load rejected" in result.stderr, name
        path.unlink()
        result = subprocess.run([str(executable), "--assets", str(path)], input=b"quit\n", capture_output=True, timeout=10)
        assert result.returncode == 2
        path.write_bytes(pack)
        cached = NativeGame(path, executable)
        try:
            first = cached.image().tobytes()
            path.unlink()
            assert cached.image().tobytes() == first
            assert "assets_loaded=1" in cached.command("resources")[0]
        finally:
            cached.close()
    checks.append("missing/short/extra/corrupt/wrong-geometry/bad-header assets rejected before play; cached rendering after file removal; normal/failed init CPU ownership cleanup")

    # Exercise the real existing desktop entry in file-only headless mode.
    # No automatic level selection/start is introduced for a smoke check.
    viewer_dir = Path(tempfile.mkdtemp(prefix="viewer_check_", dir=out))
    replay_path = viewer_dir/"scenes.jsonl"
    replay_path.write_text("".join(json.dumps(dict(elapsed=i*.02, source=p["source"], scene=p["detector_scene"]))+"\n"
                                   for i, p in enumerate(photos)), encoding="utf-8")
    viewer_checks = []
    for mode, source in (("photo", ["--image", str(ROOT/"sample_photo/077.png")]),
                         ("scene", ["--replay", str(replay_path)])):
        destination = viewer_dir/mode
        run = subprocess.run([sys.executable, "-m", "pc_vision.app", "--native-game", *source,
                              "--assets", str(assets), "--headless", "--max-frames", "20", "--output", str(destination)],
                             cwd=ROOT, capture_output=True, timeout=30)
        (viewer_dir/f"{mode}_stdout.txt").write_bytes(run.stdout)
        (viewer_dir/f"{mode}_stderr.txt").write_bytes(run.stderr)
        assert run.returncode == 0, (mode, run.stderr)
        observations = json.loads((destination/"observations.json").read_text(encoding="utf-8"))
        assert observations and all(o["state"]["state"] == "0" for o in observations)
        if mode == "photo":
            assert all(o["captured_ms"] > 0 for o in observations)
        else:
            assert all(o["captured_ms"] == o["scene"]["capture_ms"] == 0 for o in observations)
        resource = (destination/"resources.txt").read_text(encoding="utf-8")
        assert "assets_loaded=1" in resource and "frames=20" in resource
        viewer_checks.append(dict(mode=mode, observations=len(observations), resources=resource.strip(),
                                  evidence=str(destination.relative_to(ROOT)).replace("\\", "/")))
    checks.append("actual pc_vision.app --native-game photo and scene-v1 headless runs: native canvas, original capture stamps, no auto-start, load once and clean exit")

    # Reviewable collage is a preview of actual C output, no Python redrawing.
    names = ("menu", "photo_075", "photo_076", "photo_077", "level1_clear", "level2_clear", "level3_clear", "timeout")
    collage = Image.new("RGB", (1280, 1600))
    for i, name in enumerate(names):
        with Image.open(out/f"{name}.png") as im:
            collage.paste(im.resize((640, 400)), ((i%2)*640, (i//2)*400))
    collage.save(out/"gallery.png")

    files = [executable, assets, assets.parent/"assets.json", ROOT/"pc_vision/game_config.json",
             out/"events.replay", out/"photo_scenes.json", out/"gallery.png"]
    arm = out/"game_offline.arm.elf"
    if arm.exists():
        files.append(arm)
    # Package this CPU application only. No HDL/XDC/IP/BOOT/board artifacts.
    src = ROOT/"color_test/software/vision_ps_baremetal/src"
    sources = ("game_session", "ray_game", "game_scene_adapter", "game_app", "game_input", "game_evdev",
               "game_loop", "game_pump", "game_render", "game_linux_io", "vision_overlay", "vision_ps", "green_target_detector", "scene_protocol")
    for stem in sources:
        files.extend(src/f"{stem}{suffix}" for suffix in (".c", ".h"))
    files.extend((src/"game_font.h", src/"vision_ps_config.h"))
    tool = ROOT/"color_test/software/vision_ps_baremetal/tools"
    files.extend(tool/name for name in ("game_offline.c", "generate_game_config.py", "prepare_game_assets.py", "test_game_app.ps1"))
    files.extend((src.parent/"tests"/name) for name in (
        "test_game_session.c", "test_game_app.c", "test_game_loop.c", "test_game_pump.c", "test_game_render.c",
        "test_game_linux_io.c", "test_game_offline.py", "test_native_game.py"))
    files.extend((ROOT/"pc_vision").glob("*.py"))
    files.append(ROOT/"pc_vision/host_bridge.c")
    files.append(ROOT/"pc_vision/requirements.txt")
    files.append(src.parent/"README.md")
    files.extend(ROOT/"sample_photo"/f"{i:03d}.png" for i in (75, 76, 77))
    files.extend(ROOT/"output/build/game_app"/name for name in ("game_config.h", "game_config.c"))
    if arm.exists():
        files.extend((out/"arm_elf_check.txt", out/"arm_dynamic_elf_check.txt"))
    # Preserve the existing module dependency graph, including conditional
    # instrumentation headers needed by the canonical C detector bridge.
    files = list(dict.fromkeys(files))
    known = set(files)
    pending = list(files)
    while pending:
        path = pending.pop()
        if path.suffix not in (".c", ".h"):
            continue
        for header in re.findall(r'^#include "([^"]+)"', path.read_text(encoding="utf-8"), re.M):
            candidates = (path.parent/header, src/header, ROOT/"output/build/game_app"/header)
            dependency = next((p for p in candidates if p.is_file()), None)
            assert dependency is not None, (path, header)
            if dependency not in known:
                known.add(dependency)
                files.append(dependency)
                pending.append(dependency)
    arm_text = (out/"arm_elf_check.txt").read_text(encoding="utf-8") if arm.exists() else ""
    if arm.exists():
        assert "hard-float ABI" in arm_text and "Tag_CPU_arch: v7" in arm_text
        assert "interpreter" not in arm_text and "GLIBC_" not in arm_text
    report = dict(scope="offline CPU only", checks=checks, checks_passed=len(checks), images=evidence, viewer_entry=viewer_checks,
                  resources=resources, pack_sha256=sha256(pack).hexdigest(),
                  memory=dict(asset_resident_storage_bytes=13956928, asset_image_bytes=13947648, canvas_bytes=3072000,
                              resident_storage_plus_canvas_bytes=17028928),
                  hardware="NOT_RUN; display backend closed; no board/device/MMIO/PYNQ/HDL/Vivado operation",
                  calibration="uncalibrated_preview, no invented A3 corners; 1280x720 capture independent of 1280x800 display",
                  prior_evidence="game_session 261 / app 519 / loop 692 / pump 271558 / renderer 639725 / linux fake I/O 161; existing offline 102 steps + 13 frame deterministic replay",
                  arm="Cortex-A9 armhf static ELF, no interpreter or dynamic GLIBC requirement; source/link only, target NOT_RUN. Dynamic experiment requires GLIBC_2.35, excluded from package.",
                  fixture_failures=["check_attempt1.log: incorrectly expected activation on button-down",
                                    "check_attempt2.log: fixture omitted required connect/release handshake; fixed without changing C input rules"],
                  packaging_correction="Quoted-header dependency closure added after final archive check found vision_perf.h absent; original sample native_game_offline_missing_header_attempt1.zip retained locally",
                  source_sha256={str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest()
                                 for p in files if p.is_file()})
    (out/"verification.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    run_text = """Offline native C game (CPU only; no hardware access)
From this directory on Windows cmd:
  game_offline.exe --assets assets/game_assets.bin < events.replay
The last native image is final.ppm. Events use simulated time and explicit
synthetic movements; real 075/076/077 detections are separately identified in
photo_scenes.json. Original 077 stays unsolved. No auto-start in the interactive UI.

In the canonical repository, build/check/package:
  ./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -OfflinePackage
Interactive file/mouse viewer (existing OpenCV; all game pixels/rules are C):
  python -m pc_vision.app --native-game --photos sample_photo
Click any level; mouse selects menus only. A/D browses photos; Q exits.
An already solved or expired photo cannot start. Fresh photo processing retains
capture-before-detection time; slow results can remain stale by design.
For simulated complete play use events.replay, not model dragging.

Source and focused build/check entries retain their canonical repository paths
inside this archive. The packaged desktop viewer can be used after the focused
build command above creates output/build/game_app/game_offline.exe and assets.
Only software sources and three reference photos are included; no PL/BOOT files.

ARM ELF is statically cross-linked for Cortex-A9 hard-float, with no dynamic
loader/glibc requirement. The dynamic experiment needs GLIBC_2.35 and is excluded.
No target runtime/HDMI/DMA/capture/input acceptance.
Assets: 13,956,928 resident bytes, plus 3,072,000 packed canvas bytes and metadata.
The assets are ordinary CPU memory, not DMA buffers. Load once, free on exit.
"""
    (out/"RUN.txt").write_text(run_text, encoding="utf-8")
    with zipfile.ZipFile(out/"native_game_offline.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if not path.is_file():
                continue
            if path == assets or path == assets.parent/"assets.json":
                name = "assets/"+path.name
            elif str(path.relative_to(ROOT)).replace("\\", "/").startswith(("color_test/", "pc_vision/", "sample_photo/", "output/build/game_app/game_config.")):
                name = str(path.relative_to(ROOT)).replace("\\", "/")
            else:
                name = path.name
            archive.write(path, name)
        archive.write(out/"RUN.txt", "RUN.txt")
        archive.write(out/"verification.json", "verification.json")
        for name in shots:
            archive.write(out/f"{name}.png", f"frames/{name}.png")
    with zipfile.ZipFile(out/"native_game_offline.zip") as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert not any(n.endswith((".bit", ".hwh", ".xsa", ".xdc", ".v", ".vhd", ".dynamic.elf")) for n in names)
        from pathlib import PurePosixPath
        for name in names:
            if not name.endswith((".c", ".h")):
                continue
            for header in re.findall(r'^#include "([^"]+)"', archive.read(name).decode("utf-8"), re.M):
                roots = (str(PurePosixPath(name).parent), "color_test/software/vision_ps_baremetal/src", "output/build/game_app")
                assert any(str(PurePosixPath(root)/header) in names for root in roots), (name, header)
    for check in checks:
        print("PASS", check)
    print(f"PASS native offline package: {out/'native_game_offline.zip'}")


if __name__ == "__main__":
    main()
