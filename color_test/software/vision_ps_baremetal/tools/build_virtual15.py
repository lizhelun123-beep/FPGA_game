"""Build the camera-free PYNQ virtual15 presentation artifact.

This script creates a fresh output directory, generates the current fifteen
level C table, renders every configured scene through the canonical C ray
solver/renderer, and produces a separate ARM32 hard-float ELF.  It never
loads an overlay, opens UART/JTAG/SD, imports PYNQ, or touches a board.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "color_test/software/vision_ps_baremetal"
TOOLS = APP / "tools"
SRC = APP / "src"
DEFAULT_ARM = Path("D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin")
MODULES = ("game_virtual15", "game_render", "vision_overlay", "game_input",
           "ray_game", "game_linux_display", "virtual15_lvgl_ui")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None, timeout=180):
    result = subprocess.run([str(item) for item in command], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=timeout)
    if result.returncode:
        output = result.stdout.decode("utf-8", errors="replace")
        raise RuntimeError("command failed ({}):\n{}".format(result.returncode, output[-5000:]))
    return result.stdout.decode("utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/build/game_app/virtual15_1")
    parser.add_argument("--cc", type=Path,
                        default=Path("C:/Users/11967/Downloads/mingw/bin/gcc.exe"))
    parser.add_argument("--arm-bin", type=Path, default=DEFAULT_ARM)
    parser.add_argument("--assets", type=Path,
                        default=ROOT / "output/sd_card/ray_game_assets/game_assets.bin")
    parser.add_argument("--lvgl-root", type=Path,
                        help="optional LVGL 8.3.x source root; enables --lvgl-ui")
    parser.add_argument("--lvgl-conf", type=Path,
                        help="optional lv_conf.h; defaults to <lvgl-root>/lv_conf.h")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise RuntimeError("refusing to overwrite existing virtual15 output: {}".format(out))
    if not args.cc.is_file():
        raise RuntimeError("host compiler not found: {}".format(args.cc))
    arm_cc = args.arm_bin / "arm-linux-gnueabihf-gcc.exe"
    arm_readelf = args.arm_bin / "arm-linux-gnueabihf-readelf.exe"
    if not arm_cc.is_file() or not arm_readelf.is_file():
        raise RuntimeError("ARM compiler/readelf not found under {}".format(args.arm_bin))
    if not args.assets.is_file():
        raise RuntimeError("resident asset pack not found: {}".format(args.assets))

    out.mkdir(parents=True)
    frames = out / "frames"
    frames.mkdir()
    run([sys.executable, TOOLS / "generate_game_config.py",
         "--output", out / "game_config.h"])
    sources = [TOOLS / "game_virtual15.c"] + [SRC / (name + ".c")
                                               for name in MODULES[1:]]
    sources += [out / "game_config.c"]
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-I" + str(SRC), "-I" + str(out)]
    lvgl_sources = []
    lvgl_conf = None
    if args.lvgl_root:
        lvgl_root = args.lvgl_root.resolve()
        lvgl_source_root = lvgl_root / "src"
        if not lvgl_source_root.is_dir():
            raise RuntimeError("LVGL source root must contain src/: {}".format(lvgl_root))
        lvgl_conf = (args.lvgl_conf.resolve() if args.lvgl_conf else
                     lvgl_root / "lv_conf.h")
        if not lvgl_conf.is_file():
            raise RuntimeError("LVGL 8.x build requires lv_conf.h at {}".format(lvgl_conf))
        lvgl_sources = sorted(lvgl_source_root.rglob("*.c"))
        flags += ["-DVIRTUAL15_USE_LVGL", "-DLV_CONF_INCLUDE_SIMPLE",
                  "-I" + str(lvgl_conf.parent), "-I" + str(lvgl_root),
                  "-I" + str(lvgl_source_root), "-Wno-unused-parameter"]

    host = out / "game_virtual15_host.exe"
    host_command = [args.cc, *flags, *sources, *lvgl_sources, "-lm", "-o", host]
    host_log = run(host_command)
    (out / "host_build.log").write_text(host_log, encoding="utf-8")
    check_log = run([host, "--check", args.assets, frames], cwd=out)
    (out / "host_check.log").write_text(check_log, encoding="utf-8")
    manifest = frames / "virtual15_manifest.txt"
    if not manifest.is_file():
        raise RuntimeError("host check did not produce {}".format(manifest))
    lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 15 or any(not line.startswith("level=") for line in lines):
        raise RuntimeError("host check did not render all fifteen levels")

    arm = out / "game_virtual15.elf"
    arm_flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                 "-static", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard",
                 "-I" + str(SRC), "-I" + str(out)]
    if args.lvgl_root:
        lvgl_conf = (args.lvgl_conf.resolve() if args.lvgl_conf else
                     args.lvgl_root.resolve() / "lv_conf.h")
        arm_flags += ["-DVIRTUAL15_USE_LVGL", "-DLV_CONF_INCLUDE_SIMPLE",
                      "-I" + str(lvgl_conf.parent),
                      "-I" + str(args.lvgl_root.resolve()),
                      "-I" + str((args.lvgl_root.resolve() / "src")),
                      "-Wno-unused-parameter"]
    arm_log = run([arm_cc, *arm_flags, *sources, *lvgl_sources, "-lm", "-o", arm])
    (out / "arm_build.log").write_text(arm_log, encoding="utf-8")
    elf_audit = run([arm_readelf, "-h", "-l", "-A", "-d", arm])
    (out / "arm_readelf.txt").write_text(elf_audit, encoding="utf-8")
    if "ARM" not in elf_audit or "hard-float" not in elf_audit or "INTERP" in elf_audit or "NEEDED" in elf_audit:
        raise RuntimeError("ARM ELF audit failed")

    bundle = out / "virtual15_bundle"
    bundle.mkdir()
    shutil.copy2(arm, bundle / arm.name)
    shutil.copy2(args.assets, bundle / "game_assets.bin")
    shutil.copy2(out / "game_config.c", bundle / "game_config.c")
    shutil.copy2(out / "game_config.h", bundle / "game_config.h")
    shutil.copy2(TOOLS / "game_virtual15.c", bundle / "game_virtual15.c")
    shutil.copy2(SRC / "virtual15_lvgl_ui.c", bundle / "virtual15_lvgl_ui.c")
    shutil.copy2(SRC / "virtual15_lvgl_ui.h", bundle / "virtual15_lvgl_ui.h")
    if args.lvgl_root:
        shutil.copy2(lvgl_conf, bundle / "lv_conf.h")
    (bundle / "运行说明.txt").write_text(
        "本包为独立 virtual15 PYNQ/Linux 展示制品。\n"
        "运行 game_virtual15.elf --virtual15 --assets /path/game_assets.bin --seconds 30。\n"
        "若按 LVGL 8.3.x 构建，可追加 --lvgl-ui 启用关卡/状态/计时透明叠加。\n"
        "它只使用当前 15 关 JSON 生成的固定场景和现有 MM2S/HDMI；\n"
        "不初始化摄像头、CSI、S2MM、检测器或串口。\n"
        "复制到板卡或做 HDMI 实测前，须按仓库硬件准入流程单独授权。\n",
        encoding="utf-8")

    files = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(bundle)).replace("\\", "/")] = {
                "bytes": path.stat().st_size, "sha256": sha(path)}
    evidence = {
        "status": "VIRTUAL15_OFFLINE_HOST_AND_ARM_READY_NOT_BOARD_VERIFIED",
        "lvgl": {
            "enabled": bool(args.lvgl_root),
            "version": "8.3.x" if args.lvgl_root else None,
            "config_sha256": sha(lvgl_conf) if lvgl_conf else None,
            "color_depth": 16 if args.lvgl_root else None,
            "mem_size_bytes": 10 * 1024 * 1024 if args.lvgl_root else None
        },
        "camera": False, "csi": False, "s2mm": False, "detector": False,
        "levels": 15, "logical_canvas": [1280, 800], "output_canvas": [1280, 720],
        "host_rendered_frames": len(lines),
        "source_config": str((ROOT / "pc_vision/game_config.json").relative_to(ROOT)),
        "asset_pack": {"path": str(args.assets), "sha256": sha(args.assets)},
        "arm_elf": {"path": str(arm), "sha256": sha(arm)},
        "bundle_files": files,
        "board_operations": 0,
        "boot_or_sd_changes": 0,
        "notes": [
            "All scenes use the generated level anchors and ray_game.c.",
            "No camera timestamps or detector output are synthesized.",
            "LVGL is an optional UI overlay; the ray scene remains the canonical C renderer.",
            "HDMI/MM2S hardware acceptance remains a separate authorized step."
        ]
    }
    (out / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n",
                                             encoding="utf-8")
    archive = out / "virtual15_bundle.zip"
    shutil.make_archive(str(archive.with_suffix("")), "zip", bundle)
    print(json.dumps({"status": evidence["status"], "output": str(out),
                      "bundle": str(archive), "levels": 15,
                      "arm_sha256": sha(arm)}, indent=2))


if __name__ == "__main__":
    main()
