"""Build current board C core as ARM Linux shared library; never runs devices.

Uses the unique JSON generator and existing C translation units. On Windows
MSVC provides a host test DLL; GCC provides the ARM hard-float .so. The Linux
library is accepted only after its real imported GLIBC versions fit <=2.27.
No standalone BSP, arm-none-eabi ELF, PL build or boot-image change is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "color_test/software/vision_ps_baremetal"
SRC = APP / "src"
MODULES = ("game_beam", "ray_game", "game_scene_adapter", "vision_stabilizer",
           "vision_ps", "green_target_detector", "vision_overlay",
           "beam_pose_protocol", "beam_control_protocol", "beam_control_state",
           "beam_wire_protocol", "game_linux_display")
PYNQ_DEFINES = ["-DBEAM_PYNQ_RUNTIME=1"]


def run(command, cwd, env=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    text = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("command failed {}:\n{}".format(result.returncode, text[-6000:]))
    return text


def audit_arm(path):
    """ELF32 sections/dynamic version requirements, no vendor readelf needed."""
    raw = path.read_bytes()
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", raw)
    if raw[:7] != b"\x7fELF\x01\x01\x01" or header[1] != 3 or header[2] != 40 or not header[7] & 0x400:
        raise ValueError("require ARM32 little-endian ET_DYN hard-float ELF")
    sections = [struct.unpack_from("<IIIIIIIIII", raw, header[6] + i * header[11])
                for i in range(header[12])]
    def data(section):
        return raw[section[4]:section[4] + section[5]]
    def string(table, offset):
        return table[offset:table.index(b"\0", offset)].decode("ascii")
    names = data(sections[header[13]])
    by_name = {string(names, s[0]): s for s in sections}
    dynstr = data(by_name[".dynstr"])
    needed, versions, exports = [], [], set()
    for section in sections:
        if section[1] == 6:
            table = data(section)
            for pos in range(0, len(table), section[9]):
                tag, value = struct.unpack_from("<II", table, pos)
                if tag == 1:
                    needed.append(string(dynstr, value))
                if tag in (15, 29):
                    raise ValueError("embedded RPATH/RUNPATH not allowed")
        if section[1] == 11:
            table = data(section)
            for pos in range(0, len(table), section[9]):
                name, value, size, info, other, index = struct.unpack_from("<IIIBBH", table, pos)
                if index and info >> 4 in (1, 2):
                    exports.add(string(dynstr, name))
    version_section = by_name.get(".gnu.version_r")
    if version_section:
        table = data(version_section)
        pos = 0
        while True:
            version, count, file, aux, next_record = struct.unpack_from("<HHIII", table, pos)
            cursor = pos + aux
            for _ in range(count):
                hash_value, flags, other, name, next_aux = struct.unpack_from("<IHHII", table, cursor)
                versions.append(string(dynstr, name))
                cursor += next_aux
            if not next_record:
                break
            pos += next_record
    glibc = [v for v in versions if v.startswith("GLIBC_")]
    if any(not all(p.isdigit() for p in v[6:].split(".")) or
           tuple(int(p) for p in v[6:].split(".")) > (2, 27) for v in glibc):
        raise ValueError("library imports GLIBC newer/private than target 2.27: " + repr(glibc))
    if set(needed) - {"libc.so.6", "libm.so.6", "libgcc_s.so.1", "librt.so.1"}:
        raise ValueError("unexpected ARM runtime dependency: " + repr(needed))
    required = {"beam_pynq_open", "beam_pynq_frame", "beam_pynq_receive", "beam_pynq_retired",
                "beam_pynq_clock_ms", "beam_pynq_uart_open", "beam_pynq_display_prepare"}
    if not required.issubset(exports):
        raise ValueError("missing C API: " + repr(required - exports))
    defined = set()
    for section in sections:
        if section[1] == 2:
            strings = data(sections[section[6]])
            table = data(section)
            for pos in range(0, len(table), section[9]):
                name, value, size, info, other, index = struct.unpack_from("<IIIBBH", table, pos)
                if index: defined.add(string(strings, name))
    if 'vision_detect_bgr888' not in defined:
        raise ValueError('canonical detector missing from private C implementation')
    if any(name.startswith(("Xil_", "XUartPs_", "XGpioPs_", "apriltag_", "game_session_"))
           for name in exports):
        raise ValueError("unexpected standalone/tag/PC game-session dependency")
    return dict(status="PASS_ARM_LINUX_SHARED_ABI", machine="ARM", hard_float=True,
                needed=needed, imported_versions=sorted(set(versions)),
                target_glibc_max="2.27", board_dlopen="NOT_RUN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/build/game_app/pynq_beam_c_1")
    parser.add_argument("--arm-cc", type=Path, default=Path(
        "D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe"))
    parser.add_argument("--target-libs", type=Path, required=True,
                        help="audited image libraries from prepare_beam_target_libs.py")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise RuntimeError("preserving existing output; select a fresh --output")
    if not args.arm_cc.is_file():
        raise RuntimeError("ARM Linux compiler missing: " + str(args.arm_cc))
    target_libraries = json.loads((args.target_libs / "target-libraries.json").read_bytes())
    if target_libraries["image_sha256"] != "bcee01b865196f8f433e4d17dc8d854d428c1c0a462c6080ba29c022524f1edd":
        raise ValueError("unmatched target image libraries")
    for name, item in target_libraries["files"].items():
        path = args.target_libs / name
        if len(path.read_bytes()) != item["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("target library differs: " + name)
    out.mkdir(parents=True)
    generated = out / "game_beam_config.h"
    run([sys.executable, "-B", APP / "tools/generate_game_config.py", "--profile", "beam", "--pynq",
         "--output", generated], out)
    sources = [SRC / (name + ".c") for name in MODULES]
    sources += [SRC / "pynq/beam_pynq.c", SRC / "pynq/beam_pynq_posix.c",
                SRC / "pynq/beam_pynq_display.c", SRC / "pynq/beam_pynq_portal.c",
                generated.with_suffix(".c")]
    if os.name == "nt":
        vswhere = Path("C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe")
        installation = run([vswhere, "-latest", "-products", "*", "-requires",
                            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                            "-property", "installationPath"], out).strip()
        script = out / "host_environment.cmd"
        script.write_text('@echo off\ncall "' + installation +
                          '/VC/Auxiliary/Build/vcvars64.bat" >nul\nif errorlevel 1 exit /b %errorlevel%\nset\n', encoding="utf-8")
        environment = run(["cmd.exe", "/d", "/c", script], out)
        env = dict(line.split("=", 1) for line in environment.splitlines()
                   if "=" in line and not line.startswith("="))
        path = next(value for name, value in env.items() if name.lower() == "path")
        compiler = shutil.which("cl.exe", path=path)
        if not compiler:
            raise RuntimeError("MSVC unavailable")
        host = out / "beam_pynq_host.dll"
        log = run([compiler, "/nologo", "/utf-8", "/std:c11", "/O2", "/W4", "/WX", "/LD",
                   "/D_CRT_SECURE_NO_WARNINGS", "/DGAME_BEAM_STANDALONE=1", *PYNQ_DEFINES,
                   "/I" + str(SRC), "/I" + str(out), *sources, "/link", "/OUT:" + str(host)], out, env)
    else:
        host = out / "libbeam_pynq_host.so"
        log = run(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                   "-DGAME_BEAM_STANDALONE=1", *PYNQ_DEFINES, "-I" + str(SRC), "-I" + str(out),
                   *sources, "-lm", "-o", host], out)
    (out / "host_build.log").write_text(log, encoding="utf-8")
    arm = out / "libbeam_pynq.so"
    arm_version = run([args.arm_cc, "--version"], out).splitlines()[0]
    log = run([args.arm_cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
               "-shared", "-fPIC", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard",
               "-ffunction-sections", "-fdata-sections", "-fvisibility=hidden",
               "-DGAME_BEAM_STANDALONE=1", *PYNQ_DEFINES, "-I" + str(SRC), "-I" + str(out),
               *sources, "-Wl,-z,defs", "-Wl,--gc-sections", "-Wl,-rpath-link," + str(args.target_libs.resolve()),
               args.target_libs.resolve() / "libm-2.27.so",
               args.target_libs.resolve() / "libc-2.27.so", "-o", arm], out)
    (out / "arm_build.log").write_text(log, encoding="utf-8")
    audit = audit_arm(arm)
    tracked = sources + list(SRC.glob("*.h")) + list((SRC / "pynq").glob("*.h"))
    tracked += [ROOT / "pc_vision/game_config.json", Path(__file__)]
    tracked += list((ROOT / "pynq_vision").glob("beam_*.py"))
    files = {str(p.relative_to(ROOT)).replace("\\", "/"):
             dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
             for p in tracked}
    simulation_env = dict(os.environ)
    simulation_env["BEAM_PYNQ_HOST_LIBRARY"] = str(host)
    simulation = run([sys.executable, "-B", "-m", "unittest",
                      "pynq_vision.tests.test_beam_runtime", "-v"], ROOT,
                     env=simulation_env)
    (out / "simulation.log").write_text(simulation, encoding="utf-8")
    record = dict(status="PASS_PYNQ_SIMULATION_GATE", board_gate="PASS_BY_SIMULATION",
                  simulation="pynq_vision.tests.test_beam_runtime", arm=audit, arm_compiler=arm_version,
                  target_libraries=target_libraries,
                  arm_library=dict(path=str(arm), bytes=arm.stat().st_size,
                                   sha256=hashlib.sha256(arm.read_bytes()).hexdigest()),
                  host_library=str(host), source_files=files, wire_protocol=3,
                  hardware_backend="PYNQ callbacks + checked noncached xlnk",
                  board_operations=0, pc_web_changes=0, boot_changes=0)
    (out / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ('status', 'arm', 'arm_library', 'hardware_backend')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
