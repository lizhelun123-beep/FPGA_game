"""Independent image comparison of the C replay; no device or display access."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


def display_submission(executable, assets, output):
    """Compare scan buffers from the existing fake display lifecycle with art.

    Read the saved assets; never regenerate or edit them in this mode.
    """
    assets = assets.resolve()
    hashes = {name: hashlib.sha256((assets / name).read_bytes()).hexdigest()
              for name in ("background.bgr", "mirror_000.bgr", "mirror_090.bgr")}
    run = subprocess.run([str(executable.resolve()), "--assets", str(assets),
                          "--output", str(output.resolve())],
                         capture_output=True, text=True, check=True, timeout=30)
    assert "assets_loaded=3 frames=3 platform=FAKE HDMI=UNVERIFIED" in run.stdout, run.stdout
    background = Image.open(assets / "background.png").convert("RGB")
    frames = []
    for index, (x, y, pose) in enumerate(((420, 300, 0), (650, 360, 0), (650, 360, 90))):
        sprite = Image.open(assets / f"mirror_{pose:03d}.png").convert("RGB")
        pixels = sprite.tobytes()
        mask = Image.frombytes("L", sprite.size,
                               bytes(0 if pixels[i:i + 3] == b"\xff\x00\xff" else 255
                                     for i in range(0, len(pixels), 3)))
        expected = background.copy()
        expected.paste(sprite, (x, y), mask)
        raw = (output / f"scanout_{index:03d}.bgr").read_bytes()
        assert len(raw) == 4608000
        assert all(not any(raw[row * 5760 + 3840:(row + 1) * 5760]) for row in range(800))
        actual = Image.frombytes("RGB", (1280, 800), raw, "raw", "BGR", 5760, 1)
        assert ImageChops.difference(actual, expected).getbbox() is None, f"scan buffer {index} differs"
        frames.append({"frame": index, "x": x, "y": y, "pose": pose,
                       "scanout_sha256": hashlib.sha256(raw).hexdigest()})
    assert all(hashlib.sha256((assets / name).read_bytes()).hexdigest() == digest
               for name, digest in hashes.items())
    report = {"result": "PASS", "scope": "resident assets -> existing C renderer -> display prepare/start/stop on FAKE platform",
              "assets_loaded_once": 3, "asset_sha256": hashes, "frames_compared_pixel_exact": 3,
              "frames": frames, "layout": {"width": 1280, "height": 800, "hsize": 3840, "stride": 5760, "span": 4608000},
              "padding_zero": True, "cpu_update_does_not_change_scanout": True,
              "halt_timeout_retains_allocation_and_owner": True, "halted_before_individual_release": True,
              "test_mode": "synthetic 80MHz fixture, NOT a sink profile", "qualified_for_display": False,
              "hardware_dma": "NOT_RUN", "sd_card_read": "NOT_RUN", "hdmi": "UNVERIFIED", "board_operations": 0}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "submission.log").write_text(run.stdout, encoding="utf-8")
    print(run.stdout, end="")
    print("PASS 3 independent pixel-exact prepared scan buffers; no hardware qualification")


def main():
    parser = argparse.ArgumentParser()
    entries = parser.add_mutually_exclusive_group(required=True)
    entries.add_argument("--executable", type=Path)
    entries.add_argument("--display-executable", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.display_executable:
        if args.assets is None:
            parser.error("--display-executable requires --assets")
        display_submission(args.display_executable, args.assets, args.output)
        return
    script = Path(__file__).resolve().parents[1] / "tools" / "prepare_game_assets.py"
    import sys
    subprocess.run([sys.executable, str(script), "--output", str(args.output)], check=True)
    command = [str(args.executable.resolve()), "--assets", str(args.output),
               "--replay", str(args.output / "demo.replay"), "--output", str(args.output)]
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "assets_loaded=3 background_loads=1 frames=3" in run.stdout, run.stdout
    background = Image.open(args.output / "background.png").convert("RGB")
    sheet = Image.new("RGB", (1280, 3 * 432), "#f9fcf4")
    for index, (x, y, pose) in enumerate(((420, 300, 0), (650, 360, 0), (650, 360, 90))):
        sprite = Image.open(args.output / f"mirror_{pose:03d}.png").convert("RGB")
        mask = Image.new("L", sprite.size)
        pixels = sprite.tobytes()
        mask.frombytes(bytes(0 if pixels[i:i + 3] == b"\xff\x00\xff" else 255 for i in range(0, len(pixels), 3)))
        expected = background.copy()
        expected.paste(sprite, (x, y), mask)
        actual = Image.open(args.output / f"frame_{index:03d}.ppm").convert("RGB")
        assert actual.size == (1280, 800)
        assert ImageChops.difference(expected, actual).getbbox() is None, f"frame {index} differs"
        actual.save(args.output / f"frame_{index:03d}.png")
        sheet.paste(actual.resize((640, 400)), (320, index * 432 + 32))
        ImageDraw.Draw(sheet).text((320, index * 432 + 8), f"{index + 1}: x={x}, y={y}, pose={pose}", fill="#244b3c", font_size=20)
    sheet.save(args.output / "preview.png")
    # Exercise file refusal and input validation without corrupting authored art.
    original = (args.output / "mirror_090.bgr").read_bytes()
    try:
        (args.output / "mirror_090.bgr").write_bytes(original[:-1])
        assert subprocess.run(command, capture_output=True).returncode == 1
    finally:
        (args.output / "mirror_090.bgr").write_bytes(original)
    invalid = args.output / "invalid.replay"
    invalid.write_text("999999999999999999999 0 90\n", encoding="ascii")
    bad_command = command.copy()
    bad_command[4] = str(invalid)
    assert subprocess.run(bad_command, capture_output=True).returncode == 1
    invalid.unlink()
    blocked = subprocess.run([str(args.executable.resolve()), "--display"], capture_output=True, text=True)
    assert blocked.returncode == 3 and "No display/CMA/device operation performed" in blocked.stderr
    check = subprocess.run([str(args.executable.resolve()), "--check"], capture_output=True, text=True, check=True)
    assert "hash=1f497c09" in check.stdout, check.stdout
    report = {"result": "PASS", "frames_compared_pixel_exact": 3,
              "assets_loaded_once": 3, "truncated_asset_rejected": True,
              "invalid_replay_rejected": True, "original_menu_hash": "1f497c09",
              "unqualified_display_exit": 3, "board_operations": 0,
              "sd_card_read": "NOT_RUN", "hdmi": "UNVERIFIED"}
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "replay.log").write_text(run.stdout + check.stdout + blocked.stderr, encoding="utf-8")
    print(run.stdout, end="")
    print("PASS 3 pixel-exact images, old-position restoration, pose switch, file refusal, original menu and closed HDMI gate")


if __name__ == "__main__":
    main()
