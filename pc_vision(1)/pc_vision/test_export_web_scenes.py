"""Targeted checks for transporting native snapshots to the web preview."""
import unittest

from .export_web_scenes import parse_snapshot


# Captured from the canonical C game_offline output for original photo 076.
SNAPSHOT = """mapping=uncalibrated_preview calibrated=0 state=1 level=2 generation=2 sequence=2 captured_ms=2000 elapsed_ms=0 remaining_ms=180000 stars=0 valid=1 ready=0 scene_status=10 budget_exceeded=0
model=0 type=4 center=998.312,323 axis=-0.995647,0.0932044 size=54,40 tip=962.469,326.355 direction=-0.995647,0.0932044 valid=1
model=1 type=3 center=281,125 axis=1,0 size=64,64 tip=0,0 direction=0,0 valid=0
model=2 type=1 center=859.5,323.625 axis=0.0348997,-0.999391 size=164,56 tip=0,0 direction=0,0 valid=0
model=3 type=2 center=427.125,121.75 axis=0.0348997,-0.999391 size=164,56 tip=0,0 direction=0,0 valid=0
ray success=1 termination=3 interactions=1 hits=2 segments=2
hit=0 type=1
hit=1 type=3
segment=0 start=962.439,326.358 end=887.176,333.404
segment=1 start=398.825,129.575 end=310.301,137.862"""


class SnapshotTests(unittest.TestCase):
    def test_original_complete_snapshot(self):
        view = parse_snapshot(SNAPSHOT.splitlines())
        self.assertEqual(view["generation"], 2)
        self.assertEqual(view["objects"][2]["type"], "PORTAL_A")
        self.assertEqual(view["objects"][2]["size"], [164, 56])
        self.assertEqual(view["ray"]["hits"], ["PORTAL_A", "TARGET"])
        self.assertEqual(view["ray"]["segments"][1]["start"], [398.825, 129.575])
        self.assertEqual(view["stars"], 0)  # A hit is not a scored game result.

    def test_incomplete_or_reordered_response_rejected(self):
        variants = [SNAPSHOT.splitlines()[:-1],
                    SNAPSHOT.replace("segment=1", "segment=2").splitlines(),
                    SNAPSHOT.replace("hit=1", "hit=2").splitlines(),
                    SNAPSHOT.replace("ray success=", "missing success=").splitlines(),
                    SNAPSHOT.splitlines() * 2]
        for lines in variants:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                parse_snapshot(lines)

    def test_nonfinite_geometry_and_unknown_types_rejected(self):
        for text in (SNAPSHOT.replace("998.312", "nan"),
                     SNAPSHOT.replace("type=4", "type=-1"),
                     SNAPSHOT.replace("termination=3", "termination=9")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_snapshot(text.splitlines())


if __name__ == "__main__":
    unittest.main()
