"""Localization under dark-body brightness gradients and printed outlines."""
import unittest

import cv2
import numpy as np

from config import load_config
from detector import Detector
from test_vision import BG, fixture


class BodyLocalizationTests(unittest.TestCase):
    def test_wall_gradient_recovers_full_width_without_relaxing_markers(self):
        frame = np.full((220, 400, 3), BG, np.uint8)
        gradient = np.zeros((70, 300, 3), np.uint8)
        gradient[:, :, 0] = 110
        gradient[:, :, 1] = 30
        gradient[:, :, 2] = np.linspace(40, 95, 300).astype(np.uint8)
        frame[75:145, 50:350] = cv2.cvtColor(gradient, cv2.COLOR_HSV2BGR)
        detector = Detector(load_config())
        result = detector.process(frame)
        walls = [d for d in result.detections if d.type == "WALL"]
        self.assertEqual(len(walls), 1)
        self.assertEqual((walls[0].bbox_x, walls[0].bbox_w), (50, 300))
        self.assertAlmostEqual(walls[0].center_x, 199.5, places=1)
        self.assertEqual(result.masks["black"][110, 330], 0)
        self.assertEqual(result.masks["wall"][110, 330], 255)
        # Reproduce the old strict mask's partial-width failure on the same scene.
        strict = load_config()
        strict["wall"]["hsv"] = strict["hsv"]["black"]
        old = Detector(strict).process(frame)
        self.assertLess(max((c["width"] for c in old.candidates if c["type"] == "WALL"), default=0), 200)

    def test_rejected_blue_cast_must_not_cut_a_wall(self):
        frame = np.full((220, 400, 3), BG, np.uint8)
        cv2.rectangle(frame, (40, 75), (360, 145), (45, 40, 40), -1)
        patch = np.full((71, 171, 3), (110, 90, 90), np.uint8)
        frame[75:146, 190:361] = cv2.cvtColor(patch, cv2.COLOR_HSV2BGR)
        result = Detector(load_config()).process(frame)
        self.assertEqual([d.type for d in result.detections], ["WALL"])
        self.assertEqual(result.detections[0].bbox_w, 321)
        self.assertTrue(any(c["type"] == "PORTAL_A" and not c["accepted"] for c in result.candidates))

    def test_wall_needs_contrast_against_surroundings(self):
        frame = np.full((220, 400, 3), (125, 125, 125), np.uint8)
        cv2.rectangle(frame, (40, 75), (360, 145), (119, 119, 119), -1)
        result = Detector(load_config()).process(frame)
        self.assertEqual(result.detections, [])
        self.assertTrue(any("surround_contrast" in c["rejection_reasons"] for c in result.candidates))

    def test_source_includes_closed_border_and_real_tip(self):
        frame = fixture("SOURCE")
        result = Detector(load_config()).process(frame)
        source = next(d for d in result.detections if d.type == "SOURCE")
        candidate = next(c for c in result.candidates if c["type"] == "SOURCE")
        self.assertTrue(candidate["outline_used"])
        silhouette = np.any(frame != BG, axis=2).astype(np.uint8)
        full, _ = cv2.findContours(silhouette, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        expected = cv2.boundingRect(full[0])
        for actual, wanted in zip((source.bbox_x, source.bbox_y, source.bbox_w, source.bbox_h), expected):
            self.assertLessEqual(abs(actual-wanted), 2)
        self.assertLess(source.bbox_y, candidate["body_bbox"][1])
        # The physical area centroid is not the bbox center nor the triangle tip.
        self.assertGreater(source.center_y, source.bbox_y + source.bbox_h/2)
        off = load_config()
        off["stages"]["source_outline"] = False
        body_only = next(d for d in Detector(off).process(frame).detections if d.type == "SOURCE")
        self.assertGreater(body_only.bbox_y, source.bbox_y)

    def test_broken_source_border_is_not_invented(self):
        frame = fixture("SOURCE")
        cv2.line(frame, (160, 40), (160, 72), BG, 9)
        result = Detector(load_config()).process(frame)
        source = next(c for c in result.candidates if c["type"] == "SOURCE")
        self.assertFalse(source["outline_used"])
        self.assertTrue(source["accepted"])
        self.assertEqual(source["bbox"], source["body_bbox"])

    def test_rejected_candidates_hidden_without_changing_results(self):
        frame = fixture("PORTAL_A", "two_disks")
        normal = Detector(load_config()).process(frame)
        self.assertEqual(normal.detections, [])
        self.assertTrue(normal.candidates)
        np.testing.assert_array_equal(normal.final, frame)
        debug = load_config()
        debug["display"]["show_rejected"] = True
        annotated = Detector(debug).process(frame)
        self.assertEqual(annotated.detections, [])
        self.assertFalse(np.array_equal(annotated.final, frame))


if __name__ == "__main__":
    unittest.main()
