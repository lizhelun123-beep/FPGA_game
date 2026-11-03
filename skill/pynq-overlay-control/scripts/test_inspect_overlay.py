"""用合成 HWH 验证静态检查，不使用板卡或真实 BIT。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("overlay_inspector", Path(__file__).with_name("inspect_overlay.py"))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

HWH = '''<ROOT><MODULES><MODULE INSTANCE="accel_0" MODTYPE="adder" VLNV="vendor:lib:adder:1.0">
<REGISTERS><REGISTER NAME="CTRL"/><REGISTER NAME="RESULT"/></REGISTERS></MODULE></MODULES>
<MEMRANGES><MEMRANGE INSTANCE="accel_0" MEMTYPE="REGISTER"
BASEVALUE="0x40000000" HIGHVALUE="0x4000ffff"/></MEMRANGES></ROOT>'''


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.bit = Path(self.temporary.name) / "demo.bit"
        self.hwh = self.bit.with_suffix(".hwh")
        self.bit.write_bytes(b"synthetic-bit-fixture")
        self.hwh.write_text(HWH, encoding="utf-8")

    def test_ranges_and_register_names(self):
        result = inspector.inspect(self.bit, ip="accel_0")
        self.assertEqual(result["ip"]["ranges"], [{"base": 0x40000000, "span": 65536}])
        self.assertEqual(result["ip"]["registers"], ["CTRL", "RESULT"])
        self.assertFalse(result["build_pair_proven"])

    def test_bounded_list(self):
        result = inspector.inspect(self.bit, limit=1)
        self.assertEqual(result["ips"], ["accel_0"])
        self.assertEqual(result["omitted"], 0)
        self.assertNotIn("pynq", sys.modules)

    def test_missing_empty_and_malformed_inputs(self):
        self.hwh.unlink()
        with self.assertRaises(OSError): inspector.inspect(self.bit)
        self.hwh.write_text("<broken", encoding="utf-8")
        with self.assertRaises(inspector.ET.ParseError): inspector.inspect(self.bit)
        self.bit.write_bytes(b"")
        with self.assertRaises(ValueError): inspector.inspect(self.bit)

    def test_unknown_or_duplicate_ip(self):
        with self.assertRaises(ValueError): inspector.inspect(self.bit, ip="missing")
        self.hwh.write_text(HWH.replace("</MODULES>", '<MODULE INSTANCE="accel_0"/></MODULES>'), encoding="utf-8")
        with self.assertRaises(ValueError): inspector.inspect(self.bit, ip="accel_0")

    def test_invalid_address_range_and_limit(self):
        self.hwh.write_text(HWH.replace("0x4000ffff", "0x3fffffff"), encoding="utf-8")
        with self.assertRaises(ValueError): inspector.inspect(self.bit, ip="accel_0")
        with self.assertRaises(ValueError): inspector.inspect(self.bit, limit=0)

    def test_fullname_ranges_do_not_mix_hierarchical_instances(self):
        self.hwh.write_text('''<ROOT><MODULES>
<MODULE INSTANCE="accel_0" FULLNAME="/a/accel_0"/>
<MODULE INSTANCE="accel_0" FULLNAME="/b/accel_0"/></MODULES>
<MEMRANGE INSTANCE="/a/accel_0" BASEVALUE="0x40000000" HIGHVALUE="0x4000ffff"/>
<MEMRANGE INSTANCE="/b/accel_0" BASEVALUE="0x50000000" HIGHVALUE="0x5000ffff"/>
</ROOT>''', encoding="utf-8")
        result = inspector.inspect(self.bit, ip="/a/accel_0")
        self.assertEqual(result["ip"]["ranges"], [{"base": 0x40000000, "span": 65536}])
        with self.assertRaises(ValueError): inspector.inspect(self.bit, ip="accel_0")

    def test_fullname_does_not_resolve_ambiguous_short_range_owner(self):
        self.hwh.write_text('''<ROOT><MODULES>
<MODULE INSTANCE="accel_0" FULLNAME="/a/accel_0"/>
<MODULE INSTANCE="accel_0" FULLNAME="/b/accel_0"/></MODULES>
<MEMRANGE INSTANCE="accel_0" BASEVALUE="0x40000000" HIGHVALUE="0x4000ffff"/>
<MEMRANGE INSTANCE="accel_0" BASEVALUE="0x50000000" HIGHVALUE="0x5000ffff"/>
</ROOT>''', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ambiguous register range owner"):
            inspector.inspect(self.bit, ip="/a/accel_0")

    def test_range_without_owner_is_not_assigned_to_selected_module(self):
        self.hwh.write_text(HWH.replace("</ROOT>", '''
<MEMRANGE BASEVALUE="0x50000000" HIGHVALUE="0x5000ffff"/></ROOT>'''), encoding="utf-8")
        result = inspector.inspect(self.bit, ip="accel_0")
        self.assertEqual(result["ip"]["ranges"], [{"base": 0x40000000, "span": 65536}])

    def test_cli_preserves_files(self):
        before = {p.name: p.read_bytes() for p in self.bit.parent.iterdir()}
        result = subprocess.run([sys.executable, "-B", str(Path(inspector.__file__)),
                                 str(self.bit), "--ip", "accel_0"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"], "STATIC_METADATA_ONLY")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bit.parent.iterdir()})


if __name__ == "__main__":
    unittest.main()
