"""Read only the audited AX7Z020B image's ARM runtime libraries for linking.

No mount/image modification, kernel build, install, network or board access.
The optional dissect dependencies are host build tools, not board packages.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reader-deps", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("preserve existing target libraries; select a fresh output")
    if args.reader_deps:
        sys.path.insert(0, str(args.reader_deps.resolve()))
    sys.path.insert(0, str(ROOT))
    from dissect.extfs.extfs import ExtFS
    from dissect.util.stream import RangeStream
    from pynq_vision.prepare_kernel_sdk import IMAGE_SHA256, root_partition
    aliases = {
        "libm-2.27.so": ("libm.so.6", "/lib/arm-linux-gnueabihf/libm-2.27.so"),
        "libc-2.27.so": ("libc.so.6", "/lib/arm-linux-gnueabihf/libc-2.27.so"),
        "ld-2.27.so": ("ld-linux-armhf.so.3", "/lib/arm-linux-gnueabihf/ld-2.27.so"),
    }
    with args.image.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != IMAGE_SHA256:
            raise ValueError("image differs from the frozen audited AX7Z020B image")
        offset, span = root_partition(stream, args.image.stat().st_size)
        fs = ExtFS(RangeStream(stream, offset, span))
        files, data = {}, {}
        for name, (alias, source) in aliases.items():
            raw = fs.get(source).open().read()
            if raw[:6] != b"\x7fELF\x01\x01" or int.from_bytes(raw[18:20], "little") != 40:
                raise ValueError("not an ARM ELF32 runtime: " + source)
            for target in (name, alias):
                data[target] = raw
                files[target] = dict(image_path=source, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    args.output.mkdir(parents=True)
    for name, raw in data.items():
        (args.output / name).write_bytes(raw)
    record = dict(scope="HOST_LINK_INPUTS_ONLY_NOT_DEPLOYMENT", image=str(args.image.resolve()),
                  image_sha256=IMAGE_SHA256, target_glibc="2.27", files=files,
                  image_writes=0, board_operations=0)
    (args.output / "target-libraries.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
