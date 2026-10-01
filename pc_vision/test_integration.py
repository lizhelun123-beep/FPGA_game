"""End-to-end inputs, output contract and shape corner cases."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from app import main, write_image
from calibrate import main as calibration_main
from config import load_config
from detector import Detector
from test_vision import BG, COLORS, fixture


class IntegrationTests(unittest.TestCase):
    def test_target_black_fills_ring_hole(self):
        frame = fixture("TARGET", "no_black")
        cv2.circle(frame, (160, 110), 16, (15, 15, 15), -1)
        found = Detector(load_config()).process(frame).detections
        self.assertEqual([d.type for d in found], ["TARGET"])

    def test_hollow_black_rectangle_is_not_wall(self):
        frame = np.full((220, 320, 3), BG, np.uint8)
        cv2.rectangle(frame, (30, 80), (290, 140), (20, 20, 20), 5)
        self.assertEqual(Detector(load_config()).process(frame).detections, [])

    def test_multiple_entities_and_input_unchanged(self):
        frame = np.hstack([fixture(kind) for kind in COLORS])
        original = frame.copy()
        found = Detector(load_config()).process(frame).detections
        self.assertCountEqual([d.type for d in found], list(COLORS))
        np.testing.assert_array_equal(frame, original)
        expected = {"type", "center_x", "center_y", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "angle", "confidence"}
        for detection in found:
            self.assertEqual(set(detection.to_dict()), expected)

    def test_image_video_and_calibration_cli(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            image = root / "input.png"
            write_image(image, fixture("PORTAL_A"))
            before = image.read_bytes()
            output = root / "image_result"
            main(["--image", str(image), "--headless", "--output", str(output), "--save-frames"])
            record = json.loads((output / "detections.jsonl").read_text())
            self.assertEqual(record["detections"][0]["type"], "PORTAL_A")
            self.assertTrue((output / "frame_000000.png").exists())
            with self.assertRaises(FileExistsError):
                main(["--image", str(image), "--headless", "--output", str(output)])
            self.assertEqual(image.read_bytes(), before)
            video = root / "input.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 220))
            self.assertTrue(writer.isOpened(), "MJPG video codec is unavailable")
            for _ in range(3):
                writer.write(fixture("PORTAL_B"))
            writer.release()
            video_out = root / "video_result"
            main(["--video", str(video), "--headless", "--output", str(video_out)])
            records = [json.loads(line) for line in (video_out / "detections.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(r["detections"][0]["type"] == "PORTAL_B" for r in records))
            manifest = root / "samples.json"
            manifest.write_text(json.dumps({"samples": [{"image": image.name, "color": "blue", "roi": [140, 95, 30, 30]}]}))
            calibration_main(["--manifest", str(manifest), "--output", str(root / "calibration")])
            cfg = load_config(root / "calibration" / "hsv_config.json")
            self.assertIn("blue", cfg["hsv"])


if __name__ == "__main__":
    unittest.main()
