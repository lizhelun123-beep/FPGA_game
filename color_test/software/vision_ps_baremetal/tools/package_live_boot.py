"""Offline package/byte-verify the live camera ELF with the proven Zynq inputs.

No Vivado, platform generation, serial, JTAG, or SD operations. Refuses to
overwrite a BOOT image. --verify-only rechecks an existing independent image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUILD = ROOT / "color_test/build/vision_ps_baremetal"
OUTPUT = BUILD / "output/live"
PLATFORM = BUILD / "vision_ps_platform"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data), sha256=sha(data))


def check_inputs():
    baseline = json.loads((BUILD / "output/fixed_scene_validation.json").read_text())
    for entry in baseline["inputs"]:
        assert fingerprint(ROOT / entry["path"]) == entry, f"Baseline mismatch: {entry['path']}"
    with zipfile.ZipFile(ROOT / "color_test/color_test.xsa") as archive:
        bit, = [n for n in archive.namelist() if n.endswith(".bit")]
        assert archive.read(bit) == (PLATFORM / "hw/color_test.bit").read_bytes(), "XSA/BIT mismatch"
    return baseline["inputs"]


def elf_info(path):
    data = path.read_bytes()
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    assert data[:7] == b"\x7fELF\x01\x01\x01" and header[2] == 40, "Require little-endian ELF32 ARM"
    assert header[7] & 0xff000600 == 0x05000400, "Require EABI5 hard-float"
    segments = [struct.unpack_from("<8I", data, header[5]+i*header[9]) for i in range(header[10])]
    loads = [p for p in segments if p[0] == 1 and p[4]]
    assert len(loads) == 1, "Review multi-load ELF packaging before use"
    p, = loads
    sections = [struct.unpack_from("<10I", data, header[6]+i*header[11]) for i in range(header[12])]
    symbols = set()
    for section in sections:
        if section[1] != 2:
            continue
        names_section = sections[section[6]]
        names = data[names_section[4]:names_section[4]+names_section[5]]
        for at in range(section[4], section[4]+section[5], section[9]):
            name, value, size, info, other, shndx = struct.unpack_from("<IIIBBH", data, at)
            if shndx:
                symbols.add(names[name:names.find(b"\0", name)].decode())
    return data[p[1]:p[1]+p[4]], dict(entry=header[4], load_address=p[3],
        file_bytes=p[4], memory_bytes=p[5], flags=hex(header[7])), symbols


def bit_payload(path):
    data = path.read_bytes()
    preamble = struct.unpack_from(">H", data)[0]
    pos = 2+preamble
    assert data[pos:pos+2] == b"\0\x01"
    pos += 2
    for tag in b"abcd":
        assert data[pos] == tag
        length = struct.unpack_from(">H", data, pos+1)[0]
        pos += 3+length
    assert data[pos:pos+1] == b"e"
    length = struct.unpack_from(">I", data, pos+1)[0]
    raw = data[pos+5:]
    assert len(raw) == length and length % 4 == 0
    # Bootgen's Zynq configuration partition uses little-endian 32-bit words.
    return b"".join(raw[i:i+4][::-1] for i in range(0, len(raw), 4))


def verify_boot(boot, fsbl, bit, app):
    data = boot.read_bytes()

    def word(offset):
        return struct.unpack_from("<I", data, offset)[0]

    assert word(0x20) == 0xaa995566 and word(0x24) == 0x584c4e58
    assert sum(struct.unpack_from("<11I", data, 0x20)) & 0xffffffff == 0xffffffff
    table = word(0x98)
    version, count, partition_words = struct.unpack_from("<3I", data, table)
    assert version == 0x01020000 and count == 3
    partitions = partition_words*4
    assert partitions == word(0x9c)
    fsbl_bytes, fsbl_info, _ = elf_info(fsbl)
    app_bytes, app_info, symbols = elf_info(app)
    for name in ("scene_stream_poll", "scene_stream_publish", "vision_detect_bgr888", "ray_game_trace"):
        assert name in symbols, f"Missing linked live/camera symbol: {name}"
    expected = [(fsbl, fsbl_bytes, fsbl_info, 0x10),
                (bit, bit_payload(bit), dict(entry=0, load_address=0), 0x20),
                (app, app_bytes, app_info, 0x10)]
    result = []
    previous_end = partitions+4*64
    for i, (path, payload, info, attributes) in enumerate(expected):
        fields = struct.unpack_from("<16I", data, partitions+i*64)
        assert sum(fields) & 0xffffffff == 0xffffffff, "Partition header checksum"
        assert fields[0] == fields[1] == fields[2] and fields[2]*4 == len(payload)
        assert fields[3] == info["entry"] and fields[4] == info["load_address"]
        assert fields[6] == attributes and fields[7] == 1 and fields[8] == 0
        start, end = fields[5]*4, fields[5]*4+fields[2]*4
        assert previous_end <= start < end <= len(data), "Partition range/overlap"
        assert data[start:end] == payload, f"Partition bytes differ from {path}"
        previous_end = end
        result.append(dict(input=path.relative_to(ROOT).as_posix(), offset=start,
                           bytes=len(payload), sha256=sha(payload), payload_equal=True, **info))
    sentinel = struct.unpack_from("<16I", data, partitions+3*64)
    assert sentinel[:15] == (0,)*15 and sentinel[15] == 0xffffffff
    assert word(0x30) == result[0]["offset"] and word(0x34) == result[0]["bytes"]
    return result, app_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootgen", type=Path, default=Path("D:/Xilinx/Vitis/2023.1/bin/bootgen.bat"))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--mode", choices=("live", "perf"), default="live")
    parser.add_argument("--output-tag", help="Distinct output directory for a perf build")
    args = parser.parse_args()
    tag = args.output_tag or args.mode
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", tag) or (args.mode == "perf" and tag in ("live", "camera", "fixed", "default")):
        parser.error("Require a distinct simple perf output tag")
    if args.mode == "live" and tag != "live":
        parser.error("--output-tag is for independent perf delivery")
    output = BUILD / "output" / tag
    inputs = check_inputs()
    fsbl, bit, app = PLATFORM/"zynq_fsbl/fsbl.elf", PLATFORM/"hw/color_test.bit", output/"vision_ps_baremetal.elf"
    assert app.is_file() and (output/"vision_ps_baremetal.map").is_file()
    build_log = (output/"arm_build.log").read_text(encoding="utf-8-sig")
    assert f"Strict ARM build mode={args.mode}:" in build_log and "Built " in build_log
    if args.mode == "perf":
        assert "-DVISION_PERF_ENABLE=1" in build_log and "-DVISION_SCENE_STREAM_ENABLE=1" in build_log
        assert "vision_perf_diag_poll" in elf_info(app)[2], "Missing linked profiler"
    bif, boot = output/"boot.bif", output/"BOOT.bin"
    if not args.verify_only:
        if boot.exists() or bif.exists():
            raise FileExistsError("Preserving existing live image/BIF; use --verify-only to recheck")
        bif.write_text('the_ROM_image:\n{\n  [bootloader] "'+fsbl.as_posix()+'"\n  "'+
                       bit.as_posix()+'"\n  "'+app.as_posix()+'"\n}\n', encoding="ascii")
        command = [str(args.bootgen), "-arch", "zynq", "-image", str(bif), "-o", str(boot), "-w", "on"]
        run = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output/"bootgen.log").write_text(run.stdout+run.stderr, encoding="utf-8")
        print(run.stdout+run.stderr)
        run.check_returncode()
    partitions, app_info = verify_boot(boot, fsbl, bit, app)
    override = re.search(r"-DVISION_SCENE_STREAM_HZ=(\d+)", build_log)
    config = (ROOT/"color_test/software/vision_ps_baremetal/src/vision_ps_config.h").read_text()
    target_hz = int(override[1] if override else re.search(r"#define VISION_SCENE_STREAM_HZ (\d+)", config)[1])
    source = ROOT/"color_test/software/vision_ps_baremetal/src"
    sources = sorted([*source.glob("*.c"), *source.glob("*.h"), source/"lscript.ld", source/"Xilinx.spec",
        *source.glob("i2c/*.[ch]"), *source.glob("dynclk/*.[ch]"), *source.glob("display_ctrl/*.[ch]")])
    pc = ROOT/"pc_vision"
    pc_sources = [pc/name for name in ("app.py", "scene_protocol.py", "game_app.py", "game_scene.py",
        "game_view.py", "native.py", "host_bridge.c", "game_config.json", "requirements.txt", "test_game.py")]
    proof = dict(scope=f"Strict {args.mode} camera ARM application and offline boot payload verification; no hardware",
                 mode=dict(VISION_FIXED_SCENE_DEMO=0, VISION_MINIMAL_TEST=0, VISION_GREEN_TARGET_ONLY=0,
                           VISION_SCENE_STREAM_ENABLE=1, VISION_PERF_ENABLE=int(args.mode == "perf"),
                           target_hz=target_hz, baud=115200),
                 matched_inputs=inputs, xsa_embedded_bit_equal=True,
                 sources=[fingerprint(p) for p in sources],
                 pc_sources=[fingerprint(p) for p in pc_sources],
                 outputs=[fingerprint(p) for p in (app, output/"vision_ps_baremetal.map", bif, boot)],
                 elf=app_info, partitions=partitions, hardware_operated=False)
    if args.mode == "perf":
        override = re.search(r"-DVISION_PERF_REPORT_MS=(\d+)", build_log)
        proof["mode"]["VISION_PERF_REPORT_MS"] = int(override[1] if override else
            re.search(r"#define VISION_PERF_REPORT_MS (\d+)", config)[1])
    (output/"validation.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(dict(boot=fingerprint(boot), partitions_equal=True, elf=app_info), indent=2))


if __name__ == "__main__":
    main()
