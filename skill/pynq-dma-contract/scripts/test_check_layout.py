"""Behavioral positive/negative layout cases; no project imports or hardware."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from check_layout import check_layout, main


def example():
    return {"version": 1, "channels": [
        {"name": "capture", "width": 16, "height": 4, "bytes_per_pixel": 3,
         "stride": 64, "span": 256, "cache_line": 64,
         "buffers": [{"address": 4096, "owner": "device_write", "cpu_access": "none"},
                     {"address": 4352, "owner": "cpu_read", "cpu_access": "read"}]}]}


class LayoutTests(unittest.TestCase):
    def test_padding_adjacent_ranges_and_scope(self):
        result = check_layout(example())
        self.assertEqual(result["buffers"], 2)
        self.assertEqual(result["channels"][0]["row_bytes"], 48)
        self.assertIn("runtime ownership", result["not_proven"][0])

    def test_active_row_or_full_padded_allocation_too_small(self):
        for key, value in (("stride", 47), ("span", 192)):
            data = example()
            data["channels"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_layout(data)

    def test_overlap_across_channels_and_nested_ranges(self):
        data = example()
        other = copy.deepcopy(data["channels"][0])
        other.update(name="display", width=8, height=2, span=128)
        data["channels"].append(other)
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(data)

    def test_alignment_and_address_overflow(self):
        for field, value in (("address", 4097), ("address", (1 << 64) - 128),
                             ("span", 257), ("cache_line", 48)):
            data = example()
            channel = data["channels"][0]
            (channel["buffers"][0] if field == "address" else channel)[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                check_layout(data)

    def test_device_cpu_conflict_and_unknown_ownership(self):
        for owner, access in (("device_write", "read"), ("device_read", "write"),
                              ("unknown", "none"), ("cpu_read", "none"), ([], "none")):
            data = example()
            data["channels"][0]["buffers"][0].update(owner=owner, cpu_access=access)
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                check_layout(data)

    def test_boolean_missing_fields_and_duplicate_channels(self):
        for field in ("width", "stride", "span"):
            data = example()
            data["channels"][0][field] = True
            with self.assertRaises(ValueError):
                check_layout(data)
        for data in ({}, {"version": True}, {"version": 1, "channels": []},
                     {"version": 1, "channels": [None]}):
            with self.assertRaises(ValueError):
                check_layout(data)
        data = example()
        data["channels"].append(copy.deepcopy(data["channels"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            check_layout(data)

    def test_cli_readonly_accepts_valid_and_rejects_corrupt_json(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "layout.json"
            for content, expected in ((json.dumps(example()), 0), ("{broken", 1)):
                source.write_text(content, encoding="utf-8")
                original = source.read_bytes()
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = main([str(source)])
                self.assertEqual(code, expected)
                self.assertEqual(source.read_bytes(), original)
                if expected == 0:
                    self.assertEqual(json.loads(out.getvalue())["buffers"], 2)
                else:
                    self.assertIn("REJECTED", err.getvalue())

    def test_cli_accepts_utf8_bom_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "layout.json"
            source.write_text(json.dumps(example()), encoding="utf-8-sig")
            original = source.read_bytes()
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(source)])
            self.assertEqual(code, 0, err.getvalue())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(out.getvalue())["status"], "PASS_STATIC_DESCRIPTION")


if __name__ == "__main__":
    unittest.main()
