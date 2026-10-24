"""Pure file check for the existing RAYART1 native game pack. Python 3.6+.

No PYNQ, image library, device, display or DMA access. Also shipped on SD.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
POSES = (36, 72, 72, 1, 72, 36)
PAYLOAD_BYTES = 3072000 + 289 * 37632 + 290 * 32


def require(value, message):
    if not value:
        raise ValueError(message)


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def inspect_pack(path):
    path = Path(path)
    require(path.stat().st_size == PAYLOAD_BYTES + 24, "wrong pack size")
    data = path.read_bytes()
    require(data[:8] == b"RAYART1\0", "wrong pack format")
    size, checksum, count, signature = struct.unpack_from("<4I", data, 8)
    require(size == PAYLOAD_BYTES and count == 290, "wrong header")
    require(fnv(data[24:]) == checksum, "payload checksum mismatch")
    entries, seen, offset = [], set(), 24
    for i in range(count):
        require(offset + 32 <= len(data), "short entry")
        kind, pose, width, height, ax, ay, size, reserved = struct.unpack_from("<8I", data, offset)
        offset += 32
        require(reserved == 0 and size == width * height * 3 and offset + size <= len(data), "entry bounds")
        if kind == 6:
            require(i == 0 and (pose, width, height, ax, ay) == (0, 1280, 800, 0, 0), "background layout")
        else:
            require(kind < 6 and pose < POSES[kind] and (width, height, ax, ay) == (112, 112, 56, 56), "sprite layout")
        require((kind, pose) not in seen, "duplicate pose")
        seen.add((kind, pose))
        entries.append(dict(type="BACKGROUND" if kind == 6 else TYPES[kind], pose=pose,
                            angle_deg=pose * 5, width=width, height=height, anchor=[ax, ay],
                            bytes=size, offset=offset))
        offset += size
    require(offset == len(data) and len(seen) == 290, "incomplete pack")
    for kind, poses in enumerate(POSES):
        require(all((kind, p) in seen for p in range(poses)), "missing class/pose")
    summary = dict(format="RAYART1", bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                   geometry_signature=signature, images=290, model_poses=sum(POSES),
                   pose_counts=dict(zip(TYPES, POSES)), background=[1280, 800], key_rgb="FF00FF")
    return data, summary, entries


def check_bundle(directory):
    directory = Path(directory)
    _, summary, _ = inspect_pack(directory / "game_assets.bin")
    assets = json.loads((directory / "assets.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "sd_manifest.json").read_text(encoding="utf-8"))
    require(summary["sha256"] == assets["sha256"] == manifest["pack_sha256"], "pack SHA256 mismatch")
    require(summary["geometry_signature"] == assets["geometry_signature"] == manifest["geometry_signature"], "geometry mismatch")
    require(assets["pose_counts"] == list(POSES), "metadata pose count mismatch")
    for name, record in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "unsafe manifest path")
        path = directory / relative
        require(path.is_file() and path.stat().st_size == record["bytes"], "file size: " + name)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], "file SHA256: " + name)
    summary.update(status="PASS_FILES_ONLY", files_checked=len(manifest["files"]),
                   board_or_display_access=False, full_game_acceptance=False)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(check_bundle(args.directory), indent=2))
