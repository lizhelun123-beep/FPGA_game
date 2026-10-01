"""Host comparison of the PS C core against the pc_vision OpenCV reference."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[2]
PC = ROOT / "pc_vision"
sys.path.insert(0, str(PC))

from config import load_config  # noqa: E402
from detector import Detector  # noqa: E402
from test_vision import COLORS, fixture  # noqa: E402


BITS = {"yellow": 1 << 0, "blue": 1 << 1, "orange": 1 << 2,
        "green": 1 << 3, "magenta": 1 << 4, "black": 1 << 5,
        "white": 1 << 6, "wall": 1 << 7}


def reference_mask(h, s, v, config):
    result = 0
    ranges = {**config["hsv"], "wall": config["wall"]["hsv"]}
    for name, entries in ranges.items():
        if any(lo[0] <= h <= hi[0] and lo[1] <= s <= hi[1] and
               lo[2] <= v <= hi[2] for lo, hi in entries):
            result |= BITS[name]
    return result


class PcParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = ROOT / "color_test" / "build"
        build.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="vision_parity_", dir=build)
        cls.probe = Path(cls.temp.name) / "vision_probe.exe"
        subprocess.run([
            "gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I" + str(APP / "src"), str(APP / "src" / "vision_ps.c"),
            str(APP / "tests" / "vision_probe.c"), "-lm", "-o", str(cls.probe)
        ], check=True)
        cls.config = load_config()
        cls.detector = Detector(cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def probe_values(self, mode, *values):
        output = subprocess.check_output([str(self.probe), mode, *map(str, values)], text=True)
        return tuple(map(int, output.split()))

    def detect_c(self, frame, padding=17):
        height, width = frame.shape[:2]
        stride = width * 3 + padding
        packed = np.full((height, stride), 0xA5, np.uint8)
        packed[:, :width * 3] = frame.reshape(height, width * 3)
        path = Path(self.temp.name) / "frame.raw"
        packed.tofile(path)
        output = subprocess.check_output([
            str(self.probe), "detect", str(width), str(height), str(stride), str(path)
        ], text=True).splitlines()
        self.assertEqual(int(output[0]), len(output) - 1)
        detections = []
        for line in output[1:]:
            fields = line.split()
            detections.append(dict(type=fields[0], center=(int(fields[1]), int(fields[2])),
                                   bbox=tuple(map(int, fields[3:7])), angle=int(fields[7]),
                                   sampled_area=int(fields[8])))
        return detections

    def test_bgr_channel_order_and_opencv_hsv(self):
        colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0),
                  (127, 127, 127), (255, 255, 255), (0, 0, 0)]
        for hue in (0, 1, 3, 4, 20, 36, 90, 130, 134, 135, 179):
            colors.append(tuple(int(x) for x in cv2.cvtColor(
                np.uint8([[[hue, 211, 203]]]), cv2.COLOR_HSV2BGR)[0, 0]))
        for bgr in colors:
            with self.subTest(bgr=bgr):
                expected = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0]
                actual = self.probe_values("pixel", *bgr)
                self.assertLessEqual(abs(actual[0] - int(expected[0])), 1)
                self.assertLessEqual(abs(actual[1] - int(expected[1])), 1)
                self.assertEqual(actual[2], int(expected[2]))

    def test_threshold_inclusive_edges_and_hue_wrap(self):
        cases = {(0, 0, 0), (179, 255, 255), (134, 100, 100),
                 (135, 100, 100), (3, 100, 100), (4, 100, 100)}
        ranges = {**self.config["hsv"], "wall": self.config["wall"]["hsv"]}
        for entries in ranges.values():
            for low, high in entries:
                center = [(low[i] + high[i]) // 2 for i in range(3)]
                for axis in range(3):
                    for value in (low[axis] - 1, low[axis], high[axis], high[axis] + 1):
                        if 0 <= value <= (179 if axis == 0 else 255):
                            point = center.copy()
                            point[axis] = value
                            cases.add(tuple(point))
        for hsv in cases:
            with self.subTest(hsv=hsv):
                actual = self.probe_values("hsv", *hsv)[0]
                self.assertEqual(actual, reference_mask(*hsv, self.config))

    def test_synthetic_classes_bbox_center_and_stride(self):
        for kind in COLORS:
            with self.subTest(kind=kind):
                frame = fixture(kind)
                pc = self.detector.process(frame).detections
                ps = self.detect_c(frame)
                self.assertEqual([d.type for d in pc], [kind])
                self.assertEqual([d["type"] for d in ps], [kind])
                self.assertLessEqual(abs(ps[0]["center"][0] - pc[0].center_x), 5)
                self.assertLessEqual(abs(ps[0]["center"][1] - pc[0].center_y), 5)
                # PC adopts the closed SOURCE outline while PS deliberately
                # reports the sampled magenta seed. The sloped edge plus black
                # stroke reaches a 19 px width difference in this fixture.
                tolerance = 20 if kind == "SOURCE" else 5
                for actual, expected in zip(ps[0]["bbox"],
                                            (pc[0].bbox_x, pc[0].bbox_y,
                                             pc[0].bbox_w, pc[0].bbox_h)):
                    self.assertLessEqual(abs(actual - expected), tolerance)

    def test_combined_priority_and_frame_edge(self):
        canvas = np.full((440, 960, 3), (156, 151, 146), np.uint8)
        for index, kind in enumerate(COLORS):
            y, x = (index // 3) * 220, (index % 3) * 320
            canvas[y:y + 220, x:x + 320] = fixture(kind)
        self.assertEqual(sorted(d.type for d in self.detector.process(canvas).detections), sorted(COLORS))
        self.assertEqual(sorted(d["type"] for d in self.detect_c(canvas)), sorted(COLORS))
        edge = fixture("SOURCE")[:, 100:]
        self.assertEqual([d.type for d in self.detector.process(edge).detections], ["SOURCE"])
        self.assertEqual([d["type"] for d in self.detect_c(edge)], ["SOURCE"])

    def test_min_area_plus_minus_one_and_sample_quantization(self):
        polygons = {
            199: [(20, 20), (29, 20), (30, 21), (31, 20),
                  (40, 20), (40, 30), (20, 30)],
            200: [(20, 20), (40, 20), (40, 30), (20, 30)],
            201: [(20, 20), (29, 20), (30, 19), (31, 20),
                  (40, 20), (40, 30), (20, 30)],
        }
        config = load_config()
        config["stages"]["open"] = False
        config["stages"]["close"] = False
        detector = Detector(config)
        for area, points in polygons.items():
            with self.subTest(area=area):
                contour = np.array(points, np.int32)
                self.assertEqual(cv2.contourArea(contour), area)
                frame = np.full((80, 80, 3), (156, 151, 146), np.uint8)
                cv2.fillPoly(frame, [contour], COLORS["SOURCE"])
                pc_types = [d.type for d in detector.process(frame).detections]
                self.assertEqual(pc_types, [] if area == 199 else ["SOURCE"])
                # PS area is sampled-cell count, so a 199 px contour can round
                # above its 13-cell (~208 px) gate; this is a recorded tolerance.
                self.assertEqual([d["type"] for d in self.detect_c(frame)], ["SOURCE"])


if __name__ == "__main__":
    unittest.main()
