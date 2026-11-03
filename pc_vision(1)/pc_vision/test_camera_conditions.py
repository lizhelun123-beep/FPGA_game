"""Regressions for camera contrast, dark-wall color noise and rotation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from app import main, pixel_diagnostics, read_image, write_image
from config import load_config
from detector import Detector
from test_vision import BG, COLORS, fixture

PROFILE = Path(__file__).parent / "camera_low_contrast.json"


def camera_fixture(kind, bad=None):
    source = fixture(kind, bad)
    frame = source.copy()
    # Deterministic low-contrast examples, not measurements from the user screenshot.
    replacements = [(BG, (145, 143, 140)), ((245, 245, 245), (165, 165, 165)),
                    ((15, 15, 15), (90, 87, 85)), ((35, 35, 35), (100, 97, 94))]
    if kind == "TARGET":
        green = cv2.cvtColor(np.uint8([[[60, 45, 125]]]), cv2.COLOR_HSV2BGR)[0, 0]
        replacements.append((COLORS[kind], green))
    for original, replacement in replacements:
        frame[np.all(source == original, axis=2)] = replacement
    return frame


class CameraConditionsTests(unittest.TestCase):
    def test_wall_works_by_default_and_target_can_use_profile(self):
        default = Detector(load_config())
        configured = Detector(load_config(PROFILE))
        for kind in ("WALL", "TARGET"):
            with self.subTest(kind=kind):
                frame = camera_fixture(kind)
                if kind == "TARGET":
                    self.assertNotIn(kind, [d.type for d in default.process(frame).detections])
                else:
                    self.assertIn(kind, [d.type for d in default.process(frame).detections])
                self.assertEqual([d.type for d in configured.process(frame).detections], [kind])

    def test_six_classes_rotated_180_and_moved(self):
        detector = Detector(load_config(PROFILE))
        for kind in COLORS:
            for x, y in ((0, 0), (300, 0), (0, 220), (300, 220)):
                with self.subTest(kind=kind, x=x, y=y):
                    frame = np.full((440, 620, 3), (145, 143, 140), np.uint8)
                    frame[y:y+220, x:x+320] = camera_fixture(kind)
                    first = detector.process(frame).detections
                    second = detector.process(cv2.rotate(frame, cv2.ROTATE_180)).detections
                    self.assertEqual([d.type for d in first], [kind])
                    self.assertEqual([d.type for d in second], [kind])
                    self.assertAlmostEqual(first[0].center_x, 619-second[0].center_x, places=3)
                    self.assertAlmostEqual(first[0].center_y, 439-second[0].center_y, places=3)

    def test_wall_tolerates_small_colored_patch(self):
        frame = fixture("WALL")
        cv2.rectangle(frame, (150, 100), (167, 118), COLORS["TARGET"], -1)
        result = Detector(load_config()).process(frame)
        self.assertEqual([d.type for d in result.detections], ["WALL"], result.candidates)
        wall = next(c for c in result.candidates if c["type"] == "WALL")
        # The green patch has no valid target marker, so it no longer occupies space.
        self.assertEqual(wall["colored_overlap"], 0)
        self.assertEqual(wall["bbox"], [40, 83, 241, 55])

    def test_camera_profile_does_not_accept_invalid_markers(self):
        detector = Detector(load_config(PROFILE))
        for kind, bad in (("MIRROR", "missing"), ("PORTAL_A", "two_disks"),
                          ("PORTAL_B", "wrong_center"), ("TARGET", "no_black")):
            with self.subTest(kind=kind, bad=bad):
                result = detector.process(camera_fixture(kind, bad))
                self.assertEqual(result.detections, [])
                self.assertTrue(any(c["rejection_reasons"] for c in result.candidates))
        frame = np.full((220, 320, 3), (145, 143, 140), np.uint8)
        self.assertEqual(detector.process(frame).detections, [])
        cv2.rectangle(frame, (30, 80), (290, 140), (100, 97, 94), 5)
        result = detector.process(frame)
        self.assertEqual(result.detections, [])
        self.assertIn("color_fill", result.candidates[0]["rejection_reasons"])

    def test_debug_export_and_pixel_failure_explanation(self):
        frame = camera_fixture("WALL")
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        info = pixel_diagnostics(frame, hsv, 160, 110, load_config())
        self.assertEqual(info["thresholds"]["black"]["failed_by_range"], [["V>65"]])
        self.assertTrue(pixel_diagnostics(frame, hsv, 160, 110, load_config(PROFILE))
                        ["thresholds"]["black"]["pass_hsv"])
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / "input.png"
            write_image(source, frame)
            main(["--image", str(source), "--config", str(PROFILE), "--headless",
                  "--output", str(root / "run"), "--save-debug", "--width", "640"])
            debug = root / "run" / "debug_000000"
            np.testing.assert_array_equal(read_image(debug / "input.png"), frame)
            self.assertEqual(read_image(debug / "processed.png").shape[:2], (440, 640))
            self.assertTrue((debug / "mask_black.png").exists())
            record = json.loads((debug / "diagnostics.json").read_text())
            self.assertGreater(record["segmentation_stats"]["black"]["mask_pixels"], 0)
            self.assertEqual(record["detections"][0]["type"], "WALL")


if __name__ == "__main__":
    unittest.main()
