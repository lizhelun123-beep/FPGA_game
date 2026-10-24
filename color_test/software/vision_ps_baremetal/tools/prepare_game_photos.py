"""Lossless PNG -> packed BGR for the explicit, isolated photo-input check.

No detection, calibration, pose edits, templates or device access here.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[4]


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for number in (75, 76, 77):
        source = ROOT / "sample_photo" / f"{number:03}.png"
        image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if image is None or image.shape != (720, 1280, 3) or image.dtype.name != "uint8":
            raise ValueError(f"requires unchanged 1280x720 uint8 BGR: {source}")
        pixels = image.tobytes(order="C")
        target = output / f"{number:03}.bgr"
        if target.exists() and target.read_bytes() != pixels:
            raise ValueError(f"refusing to overwrite different input: {target}")
        target.write_bytes(pixels)
        records.append({"level": number-74, "source": source.relative_to(ROOT).as_posix(),
                        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "file": target.name, "sha256": hashlib.sha256(pixels).hexdigest(),
                        "width": 1280, "height": 720, "stride": 3840, "bytes": len(pixels)})
    manifest = {"input": "photograph_file_not_camera", "conversion": "lossless_BGR888_no_resize",
                "background": False, "files": records}
    (output / "photos.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))
