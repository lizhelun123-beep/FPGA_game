"""Strict fake-clock/FIFO checks; no serial, board, or ARM build. All runs timed."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from pc_vision.scene_protocol import StreamParser, PERF_STAGES


def function(source, name):
    match = re.search(r"^static (?:int|void) " + name + r"\([^;]*?\)\s*\{", source, re.M)
    assert match, name
    end, depth = match.end(), 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def run(command, timeout):
    completed = subprocess.run(command, capture_output=True, timeout=timeout)
    if completed.returncode:
        print(completed.stderr.decode(errors="replace"), flush=True)
    completed.check_returncode()
    return completed.stdout


def main():
    app = Path(__file__).resolve().parents[1]
    src = app / "src"
    cc = shutil.which("gcc")
    assert cc, "host GCC required"
    flags = [cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", f"-I{src}"]
    with tempfile.TemporaryDirectory(prefix="vision_perf_") as directory:
        tmp = Path(directory)
        source = (src / "main.c").read_text()
        (tmp / "perf_uart.inc").write_text("\n".join(function(source, name) for name in
            ("SceneUartIdle", "SceneUartPut", "SceneUartPoll")))
        exe = tmp / "perf.exe"
        run([*flags, "-DVISION_PERF_ENABLE=1", "-DVISION_SCENE_STREAM_ENABLE=1", f"-I{tmp}",
             str(app / "tests/test_vision_perf.c"), str(src / "vision_perf.c"),
             str(src / "scene_protocol.c"), "-lm", "-o", str(exe)], 60)
        wire = run([str(exe)], 10)
        rows = []
        parser = StreamParser(rows.append)
        packets = []
        for byte in wire:
            packets.extend(parser.feed(bytes([byte])))
        assert [p.frame for p in packets] == [0, 77, 78]
        assert parser.rejected == 0
        assert len(rows) == 2 * (len(PERF_STAGES) + 6), len(rows)
        copies = [r for r in rows if r["stage"] == "copy"]
        assert [(r["n"], r["total"], r["maximum"]) for r in copies] == [(2, 20, 13), (3, 1019, 999)]
        rays = [r for r in rows if r["stage"] == "ray"]
        assert rays[0]["total"] == 0x100000006 and rays[0]["maximum"] == 0x100000001
        assert max(len(line) + 1 for line in wire.split(b"\n") if line.startswith(b"@PF1")) == 61
        # Every split and large discarded text: bounded diagnostic state/resync.
        row = next(line + b"\n" for line in wire.split(b"\n") if line.startswith(b"@PF1"))
        for split in range(len(row) + 1):
            got = []
            p = StreamParser(got.append)
            p.feed(row[:split]); p.feed(row[split:])
            assert len(got) == 1
            p.feed(row[:20]); p.disconnect(); p.feed(row[20:])
            assert len(got) == 1
            p.feed(b"noise" * 20000 + b"\n" + row)
            assert len(got) == 2 and len(p.diagnostic_tail) <= 64
        # Profiler-off transport is byte-identical to profiler-on transport
        # when reports aren't scheduled, including the original rollover test.
        clock = tmp / "clock.c"
        clock.write_text('#include <stdint.h>\nuint64_t vision_perf_now(void) {return 0;}\n')
        outputs = []
        for enabled in (0, 1):
            exe = tmp / f"stream{enabled}.exe"
            run([*flags, f"-DVISION_PERF_ENABLE={enabled}", "-DVISION_SCENE_STREAM_ENABLE=1",
                 str(app / "tests/test_scene_stream.c"), str(src / "scene_protocol.c"),
                 str(src / "vision_perf.c"), str(clock), "-lm", "-o", str(exe)], 60)
            outputs.append(run([str(exe)], 10))
        assert outputs[0] == outputs[1]
        assert len(StreamParser().feed(outputs[0])) == 6
        print("PASS stats/64-bit totals/snapshots/FIFO full/packet boundaries/wire upper bound/all splits/off compatibility")


if __name__ == "__main__":
    main()
