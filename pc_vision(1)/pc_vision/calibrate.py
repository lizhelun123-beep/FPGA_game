"""HSV calibration from independent labeled image samples, not seed thresholds."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from app import read_image
from config import load_config


def circular_hue_origin(hues):
    values = np.unique(hues).astype(int)
    gaps = np.diff(np.r_[values, values[0] + 180])
    return int(values[(int(np.argmax(gaps)) + 1) % len(values)])


def sample_pixels(entry, base):
    frame = read_image(base / entry["image"])
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    selection = np.zeros(frame.shape[:2], np.uint8)
    if "roi" in entry:
        x, y, w, h = entry["roi"]
        if any(not isinstance(v, int) for v in (x, y, w, h)) or x < 0 or y < 0 or w < 1 or h < 1 or x+w > frame.shape[1] or y+h > frame.shape[0]:
            raise ValueError(f"Invalid ROI: {entry}")
        selection[y:y+h, x:x+w] = 255
    elif "mask" not in entry:
        raise ValueError("Each sample needs an ROI or a binary mask")
    if "mask" in entry:
        label = cv2.cvtColor(read_image(base / entry["mask"]), cv2.COLOR_BGR2GRAY)
        if label.shape != selection.shape:
            raise ValueError("Label mask must match the full source image size")
        selection = ((label > 0) & ((selection > 0) if "roi" in entry else True)).astype(np.uint8)
    pixels = hsv[selection != 0]
    if not len(pixels):
        raise ValueError(f"Empty calibration sample: {entry}")
    return pixels


def calibrate(manifest, config):
    manifest = Path(manifest)
    entries = json.loads(manifest.read_text(encoding="utf-8-sig"))["samples"]
    cfg = config["calibration"]
    rng = np.random.default_rng(cfg["seed"])
    pools, priorities, totals, extrema = {}, {}, {}, {}
    for entry in entries:
        color = entry["color"]
        if color not in config["hsv"]:
            raise ValueError(f"Unknown color: {color}")
        pixels = sample_pixels(entry, manifest.parent)
        totals[color] = totals.get(color, 0) + len(pixels)
        lo, hi = pixels.min(axis=0), pixels.max(axis=0)
        if color in extrema:
            lo = np.minimum(lo, extrema[color][0])
            hi = np.maximum(hi, extrema[color][1])
        extrema[color] = (lo, hi)
        scores = rng.random(len(pixels))
        if color in pools:
            pixels = np.vstack([pools[color], pixels])
            scores = np.r_[priorities[color], scores]
        limit = cfg["max_samples_per_color"]
        if limit < 1:
            raise ValueError("max_samples_per_color must be positive")
        if len(pixels) > limit:
            indices = np.argpartition(scores, limit - 1)[:limit]
            pixels, scores = pixels[indices], scores[indices]
        pools[color], priorities[color] = pixels, scores
    if not pools:
        raise ValueError("No labeled samples")
    report, thresholds = {}, {}
    for color, pixels in pools.items():
        values = pixels.astype(float)
        origin = circular_hue_origin(pixels[:, 0])
        unwrapped = (values[:, 0] - origin) % 180
        pcts = {str(p): np.percentile(values, p, axis=0).tolist() for p in cfg["percentiles"]}
        low = np.floor(np.percentile(values, cfg["low_percentile"], axis=0)).astype(int)
        high = np.ceil(np.percentile(values, cfg["high_percentile"], axis=0)).astype(int)
        low[1:] = np.maximum(0, low[1:] - cfg["sv_padding"])
        high[1:] = np.minimum(255, high[1:] + cfg["sv_padding"])
        hue_lo = int(np.floor(np.percentile(unwrapped, cfg["low_percentile"]))) - cfg["h_padding"]
        hue_hi = int(np.ceil(np.percentile(unwrapped, cfg["high_percentile"]))) + cfg["h_padding"]
        if color in ("black", "white") or hue_hi - hue_lo >= 179:
            hue_ranges = [(0, 179)]
        else:
            h0, h1 = (hue_lo + origin) % 180, (hue_hi + origin) % 180
            hue_ranges = [(h0, h1)] if h0 <= h1 else [(h0, 179), (0, h1)]
        thresholds[color] = [[[int(a), int(low[1]), int(low[2])],
                              [int(b), int(high[1]), int(high[2])]] for a, b in hue_ranges]
        if color == "black":
            thresholds[color][0][0][1] = 0
            thresholds[color][0][1][1] = 255
        radians = values[:, 0] * (2 * np.pi / 180)
        vector = np.mean(np.exp(1j * radians))
        report[color] = dict(total_pixels=totals[color], sampled_pixels=len(pixels),
                             min=extrema[color][0].tolist(), max=extrema[color][1].tolist(),
                             mean=values.mean(axis=0).tolist(), percentile=pcts,
                             circular_hue_mean=float((np.angle(vector) * 180 / (2*np.pi)) % 180),
                             hue_concentration=float(abs(vector)), hue_unwrap_origin=origin,
                             unwrapped_hue_percentile={str(p): float(np.percentile(unwrapped, p)) for p in cfg["percentiles"]},
                             proposed_ranges=thresholds[color])
    return dict(colors=report, missing_colors=sorted(set(config["hsv"]) - set(pools)),
                note="min/max exact; mean/percentiles use bounded uniform samples; H is circular"), {"hsv": thresholds}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calibrate HSV using labeled ROIs/masks")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    report, thresholds = calibrate(args.manifest, load_config(args.config))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "statistics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output / "hsv_config.json").write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    print(f"Wrote calibration to {args.output}; missing colors: {report['missing_colors']}")


if __name__ == "__main__":
    main()
