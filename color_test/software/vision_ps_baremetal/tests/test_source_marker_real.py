"""Validate marked-SOURCE detection and directed emission axis on real captures."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import tempfile

from test_six_class_real import compile_probe, detect_c, read_image


SAMPLE_GROUPS = (
    (0, ("222743", "222735", "222724", "222715", "222709")),
    (-45, ("222656", "222649", "222639", "222632", "222623")),
    (-90, ("222613", "222602", "222546", "222539", "222527")),
    (-165, ("222517", "222511", "222504", "222452", "222440")),
    (-180, ("222302", "222251", "222236", "222223", "222156")),
    (45, ("225144",)),
    (90, ("225156",)),
    (135, ("225210",)),
    (0, ("225232",)),
    (180, ("225244",)),
)

# These edge-clipped or very small captures do not provide enough independent
# colour/white support for a safe directed SOURCE.  The production rule is
# deliberately fail-closed: rejecting them is preferable to a 180-degree ray.
AMBIGUOUS_REJECTIONS = {
    "222735", "222656", "222649", "222632", "222602",
    "222539", "222517", "222236", "222223", "225144",
}


def angular_error(direction: tuple[float, float], user_angle: float) -> float:
    """User angles use mathematical +Y; image/C coordinates use downward +Y."""
    radians = math.radians(user_angle)
    expected = (math.cos(radians), -math.sin(radians))
    dot = max(-1.0, min(1.0, direction[0] * expected[0] +
                        direction[1] * expected[1]))
    return math.degrees(math.acos(dot))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--max-error", type=float, default=38.0)
    parser.add_argument("--stamp", action="append")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    failures = []
    errors = []
    rejected = 0
    with tempfile.TemporaryDirectory(prefix="source_marker_real_") as temporary:
        build = Path(temporary)
        probe = build / "vision_probe.exe"
        compile_probe(probe, args.trace)
        for expected_angle, stamps in SAMPLE_GROUPS:
            for stamp in stamps:
                if args.stamp and stamp not in args.stamp:
                    continue
                matches = list(args.samples_dir.glob(
                    f"*2026-10-05 {stamp}.png"))
                if len(matches) != 1:
                    failures.append(
                        f"{stamp}: expected one PNG, found {len(matches)}")
                    continue
                image = read_image(matches[0])
                detections = detect_c(probe, image, build / f"{stamp}.raw")
                sources = [item for item in detections
                           if item["type"] == "SOURCE" and
                           item["direction_valid"]]
                if stamp in AMBIGUOUS_REJECTIONS:
                    if sources:
                        failures.append(
                            f"{stamp}: ambiguous capture produced {sources}")
                    else:
                        rejected += 1
                        print(f"{stamp} expected=reject reported=reject")
                    continue
                if len(sources) != 1:
                    failures.append(
                        f"{stamp}: expected one directed SOURCE, got {sources}")
                    continue
                error = angular_error(sources[0]["direction"], expected_angle)
                errors.append(error)
                print(f"{stamp} expected={expected_angle:>6g} "
                      f"reported={sources[0]['angle']:>4d} error={error:5.1f} "
                      f"center={sources[0]['center']} bbox={sources[0]['bbox']}")
                if error > args.max_error:
                    failures.append(
                        f"{stamp}: direction error {error:.1f} > {args.max_error:.1f}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"{len(errors)} directed captures passed and {rejected} ambiguous "
          f"captures were rejected; mean error={sum(errors)/len(errors):.1f}, "
          f"max={max(errors):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
