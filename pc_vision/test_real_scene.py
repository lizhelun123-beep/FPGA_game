"""Offline C integration tests. Synthetic tags are not camera acceptance."""
import json
import math
import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from .native import NativeRealScene
from .real_scene import OverlayRetention, render_overlay

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "pc_vision/game_config.json").read_text(encoding="utf-8"))


def fixture(number, stamp):
    path = ROOT / f"sample_photo(1)/{number:03d}.png"
    if not path.exists() and os.environ.get("REAL_SCENE_PHOTO_DIR"):
        path = Path(os.environ["REAL_SCENE_PHOTO_DIR"]) / f"Screenshot 2026-10-27 {stamp}.png"
    if not path.exists():
        raise unittest.SkipTest(f"New real-photo fixture {number:03d} is not available")
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def tag_scene(visible=(3, 3), angles=(0, 0), bad=False, duplicate=False):
    frame = np.full((720, 1280, 3), 65, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    for p, kind in enumerate(("PORTAL_A", "PORTAL_B")):
        model = CONFIG["real_scene"]["portal_templates"][kind]
        angle = math.radians(angles[p])
        rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        for i in range(visible[p]):
            corners = np.asarray(model["corners"][i], dtype=float)
            # Production templates are measured mm; the synthetic camera view
            # uses the recorded local pixel scale and image handedness.
            corners[:, 1] *= model["image_handedness"]
            corners *= model["reference_scale_px_per_mm"]
            corners = corners @ rotation.T + [300+p*600, 400]
            if bad and p == 0 and i == 2:
                corners += [18, -12]
            center = corners.mean(axis=0)
            cv2.fillConvexPoly(frame, np.rint((corners-center)*1.35+center).astype(np.int32), (240, 240, 240))
            marker = cv2.aruco.generateImageMarker(dictionary, model["ids"][i], 96)
            matrix = cv2.getPerspectiveTransform(np.float32([[96, 0], [0, 0], [0, 96], [96, 96]]), corners.astype(np.float32))
            image = cv2.warpPerspective(marker, matrix, (1280, 720), flags=cv2.INTER_NEAREST)
            mask = cv2.warpPerspective(np.full((96, 96), 255, np.uint8), matrix, (1280, 720), flags=cv2.INTER_NEAREST)
            frame[mask > 0] = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)[mask > 0]
    if duplicate:
        marker = cv2.aruco.generateImageMarker(dictionary, 10, 64)
        frame[72:152, 72:152] = 240
        frame[80:144, 80:144] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return frame


class NativeOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NativeRealScene()
        cls.clock = 10000

    @classmethod
    def tearDownClass(cls):
        cls.native.close()

    def detect(self, frame):
        return self.native.detect(frame, 1)

    def next_time(self):
        type(self).clock += 1000
        return type(self).clock

    def test_old_generation_and_sequence_cannot_support_stability(self):
        image = fixture(132, "14-13-18")
        now = self.next_time()
        selected = self.native.select(3, now)
        generation = selected["generation"]
        rejected = self.native.observe(image, generation-1, 1, now+10, "B")
        self.assertFalse(rejected.valid)
        self.native.commit(now+11)
        first = self.native.observe(image, generation, 1, now+120, "B")
        self.assertEqual(first.objects, ())
        self.native.commit(now+121)
        # A higher timestamp cannot make an old sequence support B's candidate.
        rejected = self.native.observe(image, generation, 1, now+170, "B")
        self.assertFalse(rejected.valid)
        self.native.commit(now+171)
        second = self.native.observe(image, generation, 2, now+200, "B")
        self.assertEqual(second.objects, ())  # still <100ms reliable support
        self.native.commit(now+201)
        final = self.native.observe(image, generation, 3, now+230, "B")
        self.assertEqual(len(final.objects), 4)
        self.assertTrue(self.native.commit(now+231)["valid"])
        old = self.native.observe(image, generation, 4, now+240, "B", now_ms=now+500)
        self.assertFalse(old.valid)
        self.assertFalse(self.native.commit(now+501)["valid"])

    def test_joint_corners_follow_rotation_without_translation(self):
        for angle in (0, 45, 90, 179, -179):
            scene = self.detect(tag_scene(angles=(angle, -angle)))
            objects = {o.type: o for o in scene.objects}
            for p, kind in enumerate(("PORTAL_A", "PORTAL_B")):
                self.assertIn(kind, objects)
                obj = objects[kind]
                self.assertLess(np.linalg.norm(np.subtract(obj.center, [300+p*600, 400])), 2)
                reference = np.array([1.0, 0.0])
                radians = math.radians(angle if p == 0 else -angle)
                expected = np.array([[math.cos(radians), -math.sin(radians)], [math.sin(radians), math.cos(radians)]]) @ reference
                self.assertGreater(np.dot(obj.axis, expected), .999)
            self.assertNotIn("SOURCE", objects)

    def test_one_tag_is_diagnostic_only_two_tags_can_fit(self):
        one = self.detect(tag_scene(visible=(1, 3)))
        self.assertNotIn("PORTAL_A", [o.type for o in one.objects])
        self.assertEqual(sum(t["id"] < 20 for t in self.native.portal_tags()), 1)
        two = self.detect(tag_scene(visible=(2, 3)))
        self.assertIn("PORTAL_A", [o.type for o in two.objects])

    def test_inconsistent_or_duplicate_ids_reject_portal(self):
        for kwargs in (dict(bad=True), dict(duplicate=True)):
            scene = self.detect(tag_scene(**kwargs))
            self.assertNotIn("PORTAL_A", [o.type for o in scene.objects])
            self.assertIn("PORTAL_B", [o.type for o in scene.objects])

    def test_real_photos_complete_or_fail_closed_and_freshness(self):
        for level, number, stamp in ((1, 125, "14-09-42"), (2, 130, "14-12-43"), (3, 132, "14-13-18")):
            image = fixture(number, stamp)
            now = self.next_time()
            selected = self.native.select(level, now)
            observed = self.native.observe(image, selected["generation"], 1, now+1, None)
            snapshot = self.native.commit(now+2)
            self.assertNotIn("SOURCE", [o.type for o in observed.objects])
            if number == 130 and "PORTAL_A" not in [o.type for o in observed.objects]:
                # This real photo has insufficient A support. It must remain
                # incomplete, rather than filling A from its template.
                self.assertFalse(snapshot["valid"])
                self.assertEqual(snapshot["segments"], [])
                continue
            self.assertEqual(snapshot["valid"], 1, (number, observed))
            emitter = CONFIG["board_game"]["levels"][level-1]["emitter"]
            self.assertTrue(np.allclose(snapshot["segments"][0][:2], emitter["point"], atol=.001))
            self.assertEqual(sum(int(o[0]) == 4 for o in snapshot["objects"]), 1)
            self.assertEqual(snapshot["captured_ms"], now+1)
            self.assertEqual(snapshot["stars"], 0)
            self.assertEqual(snapshot["state"], 1)
            stale = self.native.tick(now+252)
            self.assertFalse(stale["valid"])
            self.assertEqual(stale["segments"], [])

    def test_overlay_uses_complete_returned_segments(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        snapshot = dict(level=1, state=1, sequence=1, valid=1, objects=[],
                        segments=[[100, 200, 200, 200], [400, 200, 500, 200]])
        out = render_overlay(image, snapshot, [], CONFIG)
        self.assertGreater(int(out[200, 150].sum()), 100)
        self.assertEqual(int(out[200, 300].sum()), 0)  # Portal gap
        self.assertEqual(int(out[200, 530].sum()), 0)  # terminal endpoint
        self.assertEqual(out.shape, (720, 1280, 3))


class RetentionTests(unittest.TestCase):
    def test_stale_display_does_not_refresh_capture_or_game(self):
        hold = OverlayRetention(CONFIG)
        good = dict(level=1, state=1, valid=1, captured_ms=1000, objects=[[0]], segments=[[1]])
        hold.update(good)
        shown, stale = hold.display(dict(good, valid=0), 1300)
        self.assertTrue(stale)
        self.assertEqual(shown["captured_ms"], 1000)
        shown, _ = hold.display(dict(good, valid=0), 7001)
        self.assertEqual(shown["segments"], [])
        hold.update(dict(good, valid=0))
        shown, _ = hold.display(dict(good, valid=0), 1251)
        self.assertEqual(shown["segments"], [])


if __name__ == "__main__":
    unittest.main()
