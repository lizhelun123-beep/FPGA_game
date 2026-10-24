"""Exercise the ONE text entry via stdin. Standard library, simulated time only."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[4]
CONFIG = json.loads((ROOT / "pc_vision/game_config.json").read_text(encoding="utf-8"))
MENU = CONFIG["board_game"]["menu"]
TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")


def detection_rows():
    # Original unsolved 077 fixture; the executable never creates missing poses.
    level = CONFIG["board_game"]["levels"][2]
    return [" ".join(map(str, (TYPES.index(o["type"]), *o["center"], *o["axis"],
                              int(o["type"] == "SOURCE"), *o["axis"])))
            for o in level["objects"]]


def center(rect):
    return rect[0] + rect[2] // 2, rect[1] + rect[3] // 2


def fields(line):
    return dict(re.findall(r"(\w+)=([^ ]+)", line))


def replay(executable, output, name, steps):
    commands = "\n".join(text for text, _ in steps) + "\nquit\n"
    run = subprocess.run([str(executable)], input=commands, text=True, capture_output=True,
                         timeout=15, check=True)
    (output / f"{name}.txt").write_text(run.stdout, encoding="utf-8")
    blocks = re.split(r"(?m)^status=", run.stdout)[1:]
    assert len(blocks) == len(steps), (name, len(blocks), len(steps))
    for block, (_, expected) in zip(blocks, steps):
        lines = block.splitlines()
        state_line = next(line for line in lines if line.startswith("mapping="))
        state = fields(state_line)
        menu = fields(next(line for line in lines if line.startswith("menu ")))
        assert int(lines[0]) == expected.pop("status", 0), (name, lines[0], expected)
        for key, value in expected.items():
            data = menu if key.startswith("menu.") else state
            key = key.removeprefix("menu.")
            assert data[key] == str(value), (name, key, data[key], value)
        models = [line for line in lines if line.startswith("model=")]
        ray = fields(next(line for line in lines if line.startswith("ray ")))
        segments = [line for line in lines if line.startswith("segment=")]
        assert len(segments) == int(ray["segments"])
        if state["valid"] == "0":
            assert not models and not segments
    print(f"PASS {name}: {len(steps)} stdin steps / complete snapshots")
    return blocks


def test_mouse(executable, output):
    b = 2**32
    x1, y1 = center(MENU["level_rects"][0])
    x3, y3 = center(MENU["level_rects"][2])
    sx, sy = center(MENU["start_rect"])
    rows = detection_rows()
    steps = [
        (f"pointer {b} {x1} {y1}", {"state": 0}),
        (f"left {b} 1", {"generation": 0}),
        (f"left {b} 1", {"generation": 0}),
        (f"left {b} 0", {"state": 1, "level": 1, "generation": 1}),
        (f"dispatch {b+1} {b+99} {b+1}", {"generation": 1}),
        (f"pointer {b+2} {x3} {y3}", {"generation": 1}),
        (f"left {b+2} 1", {"generation": 1}),
        (f"left {b+2} 0", {"state": 1, "level": 3, "generation": 2}),
        (f"start {b+2}", {"status": 8, "state": 1}),
        (f"frame {b+3} 2 {b+1} {b+3} 1 0 {len(rows)}\n" + "\n".join(rows),
         {"state": 1, "valid": 1, "ready": 1, "sequence": b+1, "captured_ms": b+3}),
        (f"frame {b+4} 1 {b+99} {b+1} 1 0 {len(rows)}\n" + "\n".join(rows),
         {"status": 6, "state": 1, "generation": 2, "sequence": b+1, "captured_ms": b+3}),
        (f"pointer {b+5} {sx} {sy}", {"state": 1}),
        (f"left {b+5} 1", {"state": 1}),
        (f"left {b+5} 1", {"state": 1}),
        (f"left {b+5} 0", {"state": 2, "elapsed_ms": 0}),
        (f"input {b+1005} 0", {"state": 2, "elapsed_ms": 1000, "menu.connected": 0}),
        (f"tick {b+2005}", {"state": 2, "elapsed_ms": 2000}),
        (f"input {b+3005} 1", {"state": 2, "elapsed_ms": 3000, "menu.connected": 1}),
        (f"pointer {b+3005} {x1} {y1}", {"state": 2}),
        (f"left {b+3005} 1", {"state": 2, "generation": 2}),
        (f"left {b+3005} 0", {"state": 2, "generation": 2, "elapsed_ms": 3000}),
        (f"tick {b+180005}", {"state": 4, "remaining_ms": 0, "stars": 0}),
    ]
    blocks = replay(executable, output, "offline_input", steps)
    assert f"dispatch generation=1 sequence={b+99} captured_ms={b+1}" in blocks[4]
    # The rejected task cannot replace geometry/rays or current capture metadata.
    assert blocks[9].split("mapping=", 1)[1] == blocks[10].split("mapping=", 1)[1]


def test_evdev(executable, output, layout):
    x, y = center(MENU["level_rects"][2])
    sx, sy = center(MENU["start_rect"])
    rows = detection_rows()
    def raw(now, kind, code, value):
        # Explicit little endian standard sizes, never native host alignment.
        fmt = "<iiHHi" if layout == "LE32" else "<qqHHi"
        return f"evdev {now} {layout} " + struct.pack(fmt, 123, 456, kind, code, value).hex()
    steps = [
        (raw(0, 2, 0, x), {"menu.x": 0, "generation": 0}),
        (raw(0, 2, 1, y), {"menu.y": 0, "generation": 0}),
        (raw(0, 1, 272, 1), {"generation": 0}),
        (raw(0, 1, 272, 2), {"generation": 0}),
        (raw(0, 1, 272, 0), {"generation": 0}),
        (raw(0, 0, 0, 0), {"state": 1, "level": 3, "generation": 1, "menu.x": x, "menu.y": y}),
        (f"frame 1 1 1 1 1 0 {len(rows)}\n" + "\n".join(rows), {"state": 1, "ready": 1}),
        (raw(2, 2, 0, sx-x), {"state": 1, "menu.x": x}),
        (raw(2, 2, 1, sy-y), {"state": 1, "menu.y": y}),
        (raw(2, 1, 272, 1), {"state": 1}),
        (raw(2, 0, 0, 0), {"state": 1, "menu.left": 1, "menu.x": sx, "menu.y": sy}),
        (raw(3, 1, 272, 2), {"state": 1}),
        (raw(3, 0, 0, 0), {"state": 1, "menu.left": 1}),
        (raw(4, 1, 272, 0), {"state": 1}),
        (raw(4, 0, 0, 0), {"state": 2, "elapsed_ms": 0}),
        (raw(1004, 2, 0, -10), {"state": 2, "elapsed_ms": 1000}), # no SYN still ticks
        (raw(1005, 0, 3, 0), {"state": 2, "elapsed_ms": 1001, "menu.connected": 0}),
        ("input 1005 1", {"state": 2, "menu.connected": 0}), # cannot skip drain boundary
        (raw(1006, 0, 0, 0), {"state": 2, "menu.connected": 0}),
        ("input 2004 1", {"state": 2, "elapsed_ms": 2000, "menu.connected": 1}),
        ("tick 180004", {"state": 4, "remaining_ms": 0, "stars": 0}),
    ]
    replay(executable, output, f"offline_evdev_{layout}", steps)
    malformed = raw(0, 0, 0, 0)[:-2] + "\n" # exact record width required
    run = subprocess.run([str(executable)], input=malformed, text=True, capture_output=True,
                         timeout=15)
    assert run.returncode == 2 and "Malformed" in run.stderr


def test_pump(executable, output, layout):
    fmt = "<iiHHi" if layout == "LE32" else "<qqHHi"
    def raw(kind, code, value):
        return struct.pack(fmt, 123, 456, kind, code, value)
    x, y = center(MENU["level_rects"][2])
    rows = detection_rows()
    # Initial connection needs a release; then one report selects level 3.
    stream = b"".join((raw(1, 272, 0), raw(2, 0, x), raw(2, 1, y),
                       raw(1, 272, 1), raw(1, 272, 0), raw(0, 0, 0)))
    steps = [
        (f"pump_begin 0 {layout}", {"generation": 0}),
        (f"pump_bytes {stream[:7].hex()}", {"generation": 0}),
        ("pump_run 10", {"generation": 0}),
        ("pump_io interrupt", {"generation": 0}),
        ("pump_run 20", {"generation": 0}),
        (f"pump_bytes {stream[7:].hex()}", {"generation": 0}),
        ("pump_run 20", {"state": 1, "level": 3, "generation": 1}),
        ("dispatch 21 4294967297 21", {"generation": 1}),
        (f"pump_frame 22 1 4294967297 21 1 0 {len(rows)}\n" + "\n".join(rows), {"ready": 0}),
        ("pump_run 22", {"ready": 1, "sequence": 4294967297, "captured_ms": 21}),
        ("start 23", {"state": 2}),
        ("pump_io eof", {"state": 2}),
        ("pump_run 1000", {"state": 2, "elapsed_ms": 977, "menu.connected": 0}),
        ("pump_link 1 2", {"state": 2}),
        ("pump_run 1000", {"state": 2, "menu.connected": 1}),
        ("pump_run 180023", {"state": 4, "elapsed_ms": 180000, "remaining_ms": 0, "stars": 0}),
        ("select 180024 1", {"state": 1, "generation": 2}),
        (f"pump_frame 180025 1 4294967298 24 1 0 {len(rows)}\n" + "\n".join(rows),
         {"state": 1, "generation": 2}),
        ("pump_run 180025", {"state": 1, "generation": 2, "valid": 0}),
    ]
    blocks = replay(executable, output, f"offline_pump_{layout}", steps)
    assert "dispatch generation=1 sequence=4294967297 captured_ms=21" in blocks[7]
    # pump summary precedes status; inspect the transcript for old-generation reject.
    transcript = (output / f"offline_pump_{layout}.txt").read_text(encoding="utf-8")
    summaries = [fields(line) for line in transcript.splitlines() if line.startswith("pump now=")]
    assert summaries[-1]["result_status"] == "6"
    assert int(summaries[-1]["waits"]) >= 18000


def test_render(executable, output):
    """Pump publication -> renderer -> PPM, including queued-vs-published isolation.

    Original generated 075/077 detector pose fixtures only. PNG conversion is
    optional and uses Pillow only if already present; the replay requires none.
    """
    from hashlib import sha256
    steps=[]
    images=[]
    def command(text):
        steps.append(text)
    def image(name):
        path=(output / (name+".ppm")).resolve()
        # Current text protocol paths contain no whitespace.
        assert not any(c.isspace() for c in str(path))
        command(f"render {path}")
        images.append(path)
    def frame(now, generation, seq, level, unsolved=False):
        rows=[]
        for obj in CONFIG["board_game"]["levels"][level-1]["objects"]:
            axis=obj["axis"]
            if unsolved and level==1 and obj["type"]=="SOURCE":
                axis=[0,1]  # Same unsolved SOURCE fixture as test_game_loop.c.
            rows.append(" ".join(map(str,(TYPES.index(obj["type"]),*obj["center"],*axis,
                                         int(obj["type"]=="SOURCE"),*axis))))
        command(f"dispatch {now} {seq} {now}")
        command(f"pump_frame {now} {generation} {seq} {now} 1 0 {len(rows)}\n"+"\n".join(rows))
    command("pump_begin 0 LE64")
    command("pump_run 0")
    image("render_select")
    command("select 1 1")
    image("render_before_publish")  # Event alone is not a pump publication.
    command("pump_run 1")
    image("render_selected")
    frame(2,1,1,1,True)
    image("render_queued")          # Pending completion is not a scene.
    command("pump_run 2")
    image("render_preparing")
    command("start 3")
    command("pump_run 3")
    image("render_running")
    frame(4,1,2,1)
    command("pump_run 4")
    image("render_cleared")
    command("select 5 3")
    command("pump_run 5")
    image("render_switch")
    # Old level's solved result must not resurrect models/ray/score.
    frame(6,1,3,1)
    command("pump_run 6")
    image("render_old_rejected")
    frame(7,2,4,3)
    command("pump_run 7")
    image("render_portals")
    command("start 8")
    command("pump_io eof")
    command("pump_run 8")
    image("render_disconnected")
    command("pump_run 300")
    image("render_stale")
    command("pump_run 180008")
    image("render_timeout")
    command("snapshot")
    script="\n".join(steps)+"\nquit\n"
    (output/"offline_render_input.txt").write_text(script,encoding="utf-8")
    def run():
        result=subprocess.run([str(executable.resolve())],input=script,text=True,capture_output=True,
                              timeout=30,check=True)
        return result.stdout,{p.stem:p.read_bytes() for p in images}
    transcript,first=run()
    repeat,second=run()
    assert transcript==repeat and first==second, "Non-deterministic text/image replay"
    for name,data in first.items():
        assert data.startswith(b"P6\n1280 800\n255\n"),name
        assert len(data)==len(b"P6\n1280 800\n255\n")+1280*800*3,name
    assert first["render_select"]==first["render_before_publish"]
    assert first["render_selected"]==first["render_queued"]
    assert first["render_switch"]==first["render_old_rejected"]
    assert len({data for name,data in first.items() if name not in
                ("render_before_publish","render_queued","render_old_rejected")})==10
    assert "state=3 level=1 generation=1 sequence=2 captured_ms=4" in transcript
    assert "stars=3" in transcript and "state=4 level=3 generation=2" in transcript
    assert "result_status=6" in transcript
    (output/"offline_render.txt").write_text(transcript,encoding="utf-8")
    (output/"render_hashes.json").write_text(json.dumps({name:sha256(data).hexdigest()
                                                       for name,data in first.items()},indent=2)+"\n")
    try:
        from PIL import Image
    except ImportError:
        pass
    else:
        for path in images:
            with Image.open(path) as picture:
                picture.save(path.with_suffix(".png"))
    print(f"PASS render stdin pump replay: {len(images)} PPM images, two byte-identical runs / publication isolation / optional PNG")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    test_mouse(args.executable, args.output)
    test_evdev(args.executable, args.output, "LE32")
    test_evdev(args.executable, args.output, "LE64")
    test_pump(args.executable, args.output, "LE32")
    test_pump(args.executable, args.output, "LE64")
    test_render(args.executable, args.output)
    print("PASS offline text input/evdev replay (host only; no Linux runtime/board claim)")


if __name__ == "__main__":
    main()
