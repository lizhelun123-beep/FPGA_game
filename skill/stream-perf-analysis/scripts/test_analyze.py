"""Portable synthetic cases; no project imports, device access or toolchain."""

import io
import json
import os
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import tempfile
import unittest

from analyze import analyze, main


CONTRACT = {"version": 1, "stages": {"read_audio": "leaf", "filter_audio": "leaf"}}


def snapshot(report, count, total, connection=1):
    return [dict(connection=connection, report=report, stage=stage, n=count,
                 total=total, maximum=min(total, 10000) if count else 0, unit="us")
            for stage in CONTRACT["stages"]]


def run(rows, contract=None):
    return analyze(io.StringIO("\n".join(json.dumps(r) for r in rows)), contract or CONTRACT)


class SnapshotTests(unittest.TestCase):
    def test_another_topic_and_non_additive_kinds(self):
        contract = {"version": 1, "stages": {
            "read_audio": "leaf", "filter_audio": "envelope", "transport": "span"}}
        rows = snapshot(1, 10, 10000) + snapshot(2, 20, 40000)
        for report, n, total in ((1, 2, 10000), (2, 3, 50000)):
            rows.append(dict(connection=1, report=report, stage="transport", n=n,
                             total=total, maximum=total, unit="us"))
        rows.sort(key=lambda r: r["report"])
        result = run(rows, contract)
        stages = result["last_window"]["stages"]
        self.assertEqual(stages["read_audio"]["mean_ms"], 3.0)
        self.assertEqual(stages["filter_audio"]["kind"], "envelope")
        self.assertEqual(stages["transport"]["mean_ms"], 40.0)
        self.assertNotIn("total_latency_ms", result)

    def test_missing_report_never_bridged(self):
        rows = snapshot(1, 10, 10000) + snapshot(2, 20, 20000)[:1]
        rows += snapshot(3, 30, 30000) + snapshot(4, 40, 40000)
        result = run(rows)
        self.assertEqual(result["valid_windows"], 1)
        self.assertEqual(result["last_window"]["from_report"], 3)
        self.assertEqual(result["discarded_reports"][0]["missing"], ["filter_audio"])

    def test_duplicate_report_discarded(self):
        rows = snapshot(1, 10, 10000) + snapshot(2, 20, 20000)
        rows.append(rows[-1].copy())
        result = run(rows)
        self.assertIsNone(result["last_window"])
        self.assertEqual(result["discarded_reports"][0]["duplicates"], ["filter_audio"])

    def test_unexpected_stage_discarded(self):
        rows = snapshot(1, 10, 10000)
        extra = rows[-1].copy()
        extra["stage"] = "unconfigured"
        result = run(rows + [extra] + snapshot(2, 20, 20000))
        self.assertEqual(result["discarded_reports"][0]["extra"], ["unconfigured"])
        self.assertEqual(result["valid_windows"], 0)

    def test_counter_reset_and_recovery(self):
        result = run(snapshot(1, 20, 40000) + snapshot(2, 5, 5000)
                     + snapshot(3, 10, 20000))
        self.assertEqual(result["valid_windows"], 1)
        self.assertTrue(result["boundaries"][0]["reason"].startswith("counter_decreased"))
        self.assertEqual(result["last_window"]["from_report"], 2)

    def test_reconnect_and_report_reset(self):
        for rows, reason in (
            (snapshot(1, 10, 10000) + snapshot(2, 20, 20000, connection=2),
             "connection_changed"),
            (snapshot(2, 10, 10000) + snapshot(1, 20, 20000), "report_not_increasing"),
        ):
            with self.subTest(reason=reason):
                result = run(rows)
                self.assertEqual(result["valid_windows"], 0)
                self.assertEqual(result["boundaries"][0]["reason"], reason)

    def test_marker_reset_despite_increasing_counters(self):
        contract = {"version": 1, "stages": dict(CONTRACT["stages"], boot="meta"),
                    "boot_marker": {"stage": "boot", "field": "n"}}
        rows = snapshot(1, 10, 10000)
        rows.append(dict(connection=1, report=1, stage="boot", n=900, total=0, maximum=0))
        rows += snapshot(2, 20, 20000)
        rows.append(dict(connection=1, report=2, stage="boot", n=100, total=0, maximum=0))
        result = run(rows, contract)
        self.assertEqual(result["boundaries"][0]["reason"], "boot_marker_decreased")

    def test_zero_samples_and_cumulative_maximum(self):
        rows = snapshot(1, 10, 20000) + snapshot(2, 10, 20000)
        stage = run(rows)["last_window"]["stages"]["read_audio"]
        self.assertIsNone(stage["mean_ms"])
        self.assertEqual(stage["cumulative_max_us"], 10000)

    def test_changed_total_without_sample_rejected_as_boundary(self):
        rows = snapshot(1, 10, 10000) + snapshot(2, 10, 20000)
        result = run(rows)
        self.assertEqual(result["valid_windows"], 0)
        self.assertTrue(result["boundaries"][0]["reason"].startswith(
            "duration_changed_without_samples"))

    def test_invalid_units_counts_and_json(self):
        for field, value in (("unit", "ms"), ("n", True), ("total", -1),
                             ("n", 0), ("maximum", 10001), ("maximum", 999)):
            with self.subTest(field=field, value=value):
                rows = snapshot(1, 10, 10000)
                rows[0][field] = value
                with self.assertRaises(ValueError):
                    run(rows)
        with self.assertRaises(ValueError):
            analyze(["{not json}"], CONTRACT)

    def test_events_have_counts_but_no_duration(self):
        contract = {"version": 1, "stages": {"fault": "event"}}
        rows = [dict(connection=1, report=r, stage="fault", n=r,
                     total=0, maximum=0, unit="us") for r in (1, 2)]
        stage = run(rows, contract)["last_window"]["stages"]["fault"]
        self.assertEqual(stage["delta_n"], 1)
        self.assertIsNone(stage["mean_ms"])
        rows[-1].update(total=100, maximum=100)
        with self.assertRaises(ValueError):
            run(rows, contract)

    def test_cli_readonly_and_no_window_exit(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("SKILL_TEST_TMP")) as directory:
            folder = Path(directory)
            source = folder / "input.jsonl"
            contract = folder / "contract.json"
            contract.write_text(json.dumps(CONTRACT), encoding="utf-8")
            for rows, expected in ((snapshot(1, 10, 10000), 2),
                                   (snapshot(1, 10, 10000) + snapshot(2, 20, 40000), 0)):
                source.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
                original = source.read_bytes()
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([str(source), "--contract", str(contract)])
                self.assertEqual(code, expected, stderr.getvalue())
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(json.loads(stdout.getvalue())["valid_windows"], int(expected == 0))

    def test_impossible_window_total_stops_comparison(self):
        rows = snapshot(1, 10, 10000) + snapshot(2, 11, 22000)
        result = run(rows)
        self.assertEqual(result["valid_windows"], 0)
        self.assertTrue(result["boundaries"][0]["reason"].startswith(
            "window_total_exceeds_maximum"))


if __name__ == "__main__":
    unittest.main()
