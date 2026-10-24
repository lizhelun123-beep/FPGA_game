import unittest
from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from green_target_recognition.detector import GreenTargetDetector  # noqa: E402


def green_bgr(h=55, s=90, v=120):
    return tuple(int(value) for value in cv2.cvtColor(
        np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR
    )[0, 0])


class GreenTargetDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = GreenTargetDetector()

    def test_detects_solid_low_contrast_green_circle(self):
        image = np.full((360, 640, 3), (95, 100, 105), np.uint8)
        cv2.circle(image, (470, 105), 32, green_bgr(), -1)
        detections, _ = self.detector.detect(image)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "GREEN_TARGET")
        self.assertLessEqual(abs(detections[0].center[0] - 470), 1)
        self.assertLessEqual(abs(detections[0].center[1] - 105), 1)

    def test_detects_green_ring_without_marker_requirement(self):
        image = np.full((360, 640, 3), (90, 95, 100), np.uint8)
        cv2.circle(image, (160, 250), 38, green_bgr(h=38, s=75, v=90), 10)
        detections, _ = self.detector.detect(image)
        self.assertEqual(len(detections), 1)
        self.assertLessEqual(abs(detections[0].center[0] - 160), 1)
        self.assertLessEqual(abs(detections[0].center[1] - 250), 1)

    def test_rejects_green_rectangle_and_small_noise(self):
        image = np.full((360, 640, 3), (90, 95, 100), np.uint8)
        cv2.rectangle(image, (80, 100), (180, 180), green_bgr(), -1)
        image[20, 20] = green_bgr()
        detections, _ = self.detector.detect(image)
        self.assertEqual(detections, [])

    def test_rejects_gray_background(self):
        image = np.full((360, 640, 3), (95, 100, 105), np.uint8)
        detections, mask = self.detector.detect(image)
        self.assertEqual(detections, [])
        self.assertEqual(cv2.countNonZero(mask), 0)


if __name__ == "__main__":
    unittest.main()

