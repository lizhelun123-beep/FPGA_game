"""Synthetic regression fixtures; not a substitute for camera validation."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from app import read_image, write_image
from calibrate import calibrate
from config import load_config
from detector import Detector

BG = (156, 151, 146)
COLORS = {"MIRROR": (0, 230, 240), "PORTAL_A": (230, 90, 20),
          "PORTAL_B": (0, 135, 255), "TARGET": (45, 190, 40),
          "SOURCE": (40, 74, 118), "WALL": (35, 35, 35)}


def fixture(kind, bad=None):
    image = np.full((220, 320, 3), BG, np.uint8)
    color = COLORS[kind]
    if kind == "MIRROR":
        cv2.rectangle(image, (35, 78), (285, 142), (15, 15, 15), -1)
        cv2.rectangle(image, (40, 83), (280, 137), color, -1)
        if bad != "missing":
            for center in ((75, 110), (245, 110)):
                cv2.circle(image, center, 10, (15, 15, 15), -1)
    elif kind == "WALL":
        # Match the supplied 50 cm captures: the wall occupies about 2-5% of
        # the frame, not the former oversized 18.4% synthetic rectangle.
        cv2.rectangle(image, (110, 94), (210, 126), color, -1)
        cv2.rectangle(image, (120, 98), (128, 122), (245, 245, 245), -1)
        cv2.rectangle(image, (190, 98), (198, 122), (245, 245, 245), -1)
    elif kind.startswith("PORTAL"):
        cv2.rectangle(image, (90, 80), (230, 140), color, -1)
        for center in ((90, 110), (230, 110)):
            cv2.circle(image, center, 30, color, -1)
        if bad != "missing":
            cv2.circle(image, (90, 110), 12, (245, 245, 245), -1)
            cv2.circle(image, (230, 110), 14, (245, 245, 245), -1)
            if bad != "two_disks":
                cv2.circle(image, (230, 110), 8, color if bad != "wrong_center" else (15, 15, 15), -1)
    elif kind == "TARGET":
        cv2.circle(image, (160, 110), 55, color, -1)
        if bad != "missing":
            cv2.circle(image, (160, 110), 24, (245, 245, 245), -1)
            cv2.circle(image, (160, 110), 16, color, -1)
            if bad != "no_black":
                cv2.circle(image, (160, 110), 10, (15, 15, 15), -1)
    else:
        outer = np.array([[160, 23], [88, 187], [232, 187]], np.int32)
        points = np.array([[160, 35], [100, 175], [220, 175]], np.int32)
        cv2.fillPoly(image, [outer], (15, 15, 15))
        cv2.fillPoly(image, [points], color)
        # SOURCE is valid only as the two-part physical marker: the white band
        # covers the non-emitting base and the remaining coloured tip emits.
        band = np.array([[100, 175], [220, 175], [202, 133], [118, 133]],
                        np.int32)
        cv2.fillPoly(image, [band], (245, 245, 245))
    return image


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.detector = Detector(load_config())

    def test_all_six_and_rotation(self):
        for kind in COLORS:
            for angle in (0, 35, 90, 155):
                with self.subTest(kind=kind, angle=angle):
                    # Pad to avoid clipping long objects during rotation.
                    image = cv2.copyMakeBorder(fixture(kind), 90, 90, 40, 40, cv2.BORDER_CONSTANT, value=BG)
                    matrix = cv2.getRotationMatrix2D((200, 200), angle, 1)
                    image = cv2.warpAffine(image, matrix, (400, 400), borderValue=BG)
                    result = self.detector.process(image)
                    self.assertEqual([d.type for d in result.detections], [kind], result.candidates)

    def test_missing_and_invalid_markers(self):
        for kind, bad in (("MIRROR", "missing"), ("PORTAL_A", "missing"),
                          ("PORTAL_A", "two_disks"), ("PORTAL_B", "wrong_center"),
                          ("TARGET", "no_black"), ("TARGET", "missing")):
            with self.subTest(kind=kind, bad=bad):
                result = self.detector.process(fixture(kind, bad))
                self.assertEqual(result.detections, [])

    def test_portal_minimum_area_rejects_small_marker_complete_pattern(self):
        image = cv2.resize(fixture("PORTAL_B"), None, fx=.40, fy=.40,
                           interpolation=cv2.INTER_NEAREST)
        result = self.detector.process(image)
        candidates = [item for item in result.candidates
                      if item["type"] == "PORTAL_B"]
        self.assertEqual(result.detections, [])
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["marker_ok"])
        self.assertEqual(candidates[0]["rejection_reasons"], ["class_min_area"])

    def test_background_noise_and_no_mutation(self):
        image = np.full((300, 400, 3), BG, np.uint8)
        rng = np.random.default_rng(123)
        for _ in range(50):
            x, y = rng.integers([0, 0], [400, 300])
            image[y, x] = (0, 220, 220)
        before = image.copy()
        self.assertEqual(self.detector.process(image).detections, [])
        np.testing.assert_array_equal(image, before)

    def test_stage_switches(self):
        for stage in load_config()["stages"]:
            cfg = load_config()
            cfg["stages"][stage] = False
            result = Detector(cfg).process(fixture("PORTAL_A"))
            if stage in ("hsv", "segmentation", "candidates"):
                self.assertEqual(result.detections, [])
            if stage == "draw":
                np.testing.assert_array_equal(result.final, fixture("PORTAL_A"))

    def test_target_only_keeps_marker_semantics(self):
        detector = Detector(load_config(), enabled_types=("TARGET",))
        self.assertEqual([d.type for d in detector.process(fixture("TARGET")).detections],
                         ["TARGET"])
        self.assertEqual(detector.process(fixture("MIRROR")).detections, [])
        rejected = detector.process(fixture("TARGET", "no_black"))
        self.assertEqual(rejected.detections, [])
        self.assertIn("ring_center_or_black_failed",
                      rejected.candidates[0]["rejection_reasons"])

    def test_unknown_enabled_type_is_rejected(self):
        with self.assertRaises(ValueError):
            Detector(load_config(), enabled_types=("NOT_A_CLASS",))

    def test_calibration_hue_wrap_and_unicode_io(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            hsv = np.full((20, 20, 3), (178, 220, 200), np.uint8)
            hsv[:, 10:, 0] = 1
            path = base / "标定.png"
            write_image(path, cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
            self.assertEqual(read_image(path).shape, hsv.shape)
            manifest = base / "samples.json"
            manifest.write_text(json.dumps({"samples": [{"image": path.name, "color": "magenta", "roi": [0, 0, 20, 20]}]}), encoding="utf-8")
            report, proposed = calibrate(manifest, load_config())
            ranges = proposed["hsv"]["magenta"]
            self.assertEqual(len(ranges), 2)
            self.assertLess(sum(hi[0]-lo[0]+1 for lo, hi in ranges), 15)
            self.assertEqual(report["colors"]["magenta"]["total_pixels"], 400)


def create_demo():
    canvas = np.full((440, 960, 3), BG, np.uint8)
    for i, kind in enumerate(COLORS):
        y, x = (i // 3) * 220, (i % 3) * 320
        canvas[y:y+220, x:x+320] = fixture(kind)
    write_image(Path(__file__).parent / "output" / "demo.png", canvas)


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        create_demo()
    else:
        unittest.main()
