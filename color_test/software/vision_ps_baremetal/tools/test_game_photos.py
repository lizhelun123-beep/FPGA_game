"""Build and check only the reference-photo software path. No board access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from prepare_game_photos import prepare

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "color_test/software/vision_ps_baremetal"
DEFAULT_ARM = "D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--arm-compiler", default=DEFAULT_ARM)
    parser.add_argument("--stage", choices=("all", "arm", "host", "core", "checks"), default="all")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not args.assets.is_file():
        raise ValueError("existing resident asset pack required: "+str(args.assets))
    prepare(out / "photos")
    results = (json.loads((out/"validation.json").read_text()) if (out/"validation.json").exists() else
               {"scope": "offline_photo_geometry_and_core_not_board", "commands": {}, "returncodes": {}})

    def run(name, command):
        if results["returncodes"].get(name, 0):
            previous = out/(name+".log")
            if previous.exists():
                n = 1
                while (out/(name+f".failure{n}.log")).exists():
                    n += 1
                shutil.copyfile(previous, out/(name+f".failure{n}.log"))
        results["commands"][name] = [str(x) for x in command]
        (out / "validation.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
        try:
            r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as e:
            results.setdefault("launch_errors", {})[name] = str(e)
            (out / "validation.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
            raise
        (out / (name+".log")).write_bytes(r.stdout)
        results["returncodes"][name] = r.returncode
        (out / "validation.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
        print(name, r.returncode, flush=True)
        if r.returncode:
            print(r.stdout.decode(errors="replace")[-1600:])
            raise SystemExit(r.returncode)

    if args.stage == "all" or not (out/"game_config.h").exists():
        run("config", [sys.executable, APP/"tools/generate_game_config.py", "--output", out/"game_config.h"])
    core_names = ("game_session", "ray_game", "game_scene_adapter", "game_app", "game_input", "game_evdev",
                  "game_loop", "game_pump", "game_photo_input", "vision_ps", "green_target_detector")
    core = [APP/"src"/(n+".c") for n in core_names]+[out/"game_config.c"]
    display = core+[APP/"src"/(n+".c") for n in ("game_render", "vision_overlay", "game_linux_io", "game_linux_display")]
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I"+str(APP/"src"), "-I"+str(out),
             '-DGAME_PHOTO_DISPLAY_CHECKER=1']
    gcc = shutil.which("gcc.exe")
    if not gcc:
        raise RuntimeError("existing host gcc.exe required")
    entry = APP/"tools/game_linux_static_menu.c"
    if args.stage in ("all", "arm"):
        run("arm_entry", [args.arm_compiler]+flags+["-static", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard"]+
            display+[entry, "-lm", "-o", out/"photo_menu.arm.elf"])
    if args.stage in ("all", "host"):
        run("host_entry", [gcc]+flags+display+[entry, "-lm", "-o", out/"photo_menu.exe"])
    if args.stage in ("all", "host", "core"):
        run("host_core", [gcc]+flags+core+[APP/"tests/test_game_photo_input.c", "-lm", "-o", out/"photo_core.exe"])
    if args.stage in ("arm", "host", "core"):
        return
    run("core_check", [out/"photo_core.exe", out/"photos"])
    run("unchanged_menu", [out/"photo_menu.exe", "--check"])
    if "hash=1f497c09" not in (out/"unchanged_menu.log").read_text():
        raise RuntimeError("default menu changed")
    run("geometry", [out/"photo_menu.exe", "--photo-check", out/"photos", args.assets.resolve(), out])
    sources = core+display[len(core):]+[entry, APP/"src/game_photo_input.h", APP/"src/game_render.h"]
    results["sources"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    results["artifacts"] = {name: hashlib.sha256((out/name).read_bytes()).hexdigest()
                            for name in ("photo_menu.arm.elf", "photo_menu.exe")}
    results["assets_sha256"] = hashlib.sha256(args.assets.read_bytes()).hexdigest()
    (out/"validation.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
