"""Execute production FixedScenePresent with host display stubs and C physics.

Extends test_ray_game.c, using the existing guarded strided buffer and overlay.
Exports the actual BGR buffer as a software preview, never a HDMI capture.
"""
from pathlib import Path
from math import prod
import re
import shutil
import subprocess
import tempfile

from PIL import Image


def run(command, timeout):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", flush=True)
    result.check_returncode()
    return result.stdout


def main():
    app = Path(__file__).resolve().parents[1]
    src = app / "src"
    output = app.parents[1] / "build/vision_ps_baremetal/output"
    output.mkdir(parents=True, exist_ok=True)
    source = (src / "main.c").read_text()
    match = re.search(r"^static int FixedScenePresent\(void\)\s*\{", source, re.M)
    assert match, "production FixedScenePresent not found"
    end, depth = match.end(), 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    compiler = shutil.which("gcc")
    assert compiler, "host GCC is required"
    with tempfile.TemporaryDirectory(prefix="fixed_scene_") as directory:
        temporary = Path(directory)
        (temporary / "fixed_scene_present.inc").write_text(source[match.start():end])
        executable, raw = temporary / "test_ray_game.exe", temporary / "scene.bgr"
        print("Strict host compile: -std=c99 -O2 -Wall -Wextra -Werror", flush=True)
        run([compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
             "-DVISION_FIXED_SCENE_DEMO=1", f"-I{src}", f"-I{temporary}",
             str(src / "ray_game.c"), str(src / "vision_overlay.c"),
             str(app / "tests/test_ray_game.c"), "-lm", "-o", str(executable)], 60)
        log = run([str(executable), str(raw)], 20)
        config = (src / "vision_ps_config.h").read_text()
        width = int(re.search(r"#define VISION_FIXED_SCENE_WIDTH (\d+)", config)[1])
        height = int(re.search(r"#define VISION_FIXED_SCENE_HEIGHT (\d+)", config)[1])
        expression = re.search(r"#define DEMO_STRIDE\s+\(([\d\s*]+)\)",
                               (src / "display_demo.h").read_text())[1]
        stride = prod(int(part.strip()) for part in expression.split("*"))
        assert (width, height, stride) == (1280, 720, 5760)
        image = Image.frombytes("RGB", (width, height), raw.read_bytes(),
                                "raw", "BGR", stride, 1)
        preview = output / "fixed_scene.png"
        image.save(preview)
        (output / "fixed_scene_host.log").write_text(log + "Software preview; no hardware access.\n")
        print(f"Software-generated preview (not HDMI): {preview}")


if __name__ == "__main__":
    main()
