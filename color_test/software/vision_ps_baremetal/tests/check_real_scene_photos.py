"""Opt-in photo check for the real camera profile; no hardware is accessed.

Usage: python check_real_scene_photos.py --photos PATH --probe EXE
The probe uses an empty Portal callback: only the non-Portal detector is checked.
"""
import argparse
from collections import Counter
from pathlib import Path
import subprocess

import cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.photos.glob("*.png"))
    process = subprocess.Popen([str(args.probe.resolve()), "--pipe"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    distribution = Counter()
    try:
        for path in paths:
            frame = cv2.imread(str(path))
            if frame is None or frame.shape != (720, 1280, 3):
                raise ValueError(f"Expected native 1280x720 BGR photo: {path}")
            process.stdin.write(frame.tobytes())
            process.stdin.flush()
            result = process.stdout.readline().decode("ascii").strip()
            if not result:
                raise RuntimeError(f"Probe stopped at {path}")
            types = tuple(sorted(row.split(",")[0] for row in result.split()[1:]))
            distribution[types] += 1
            print(path.name, result, flush=True)
    finally:
        process.stdin.close()
        process.wait(timeout=5)
    print("Distribution:", dict(distribution))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
