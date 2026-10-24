import tempfile
import contextlib
import io
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from pynq_vision.constants import (ACTIVE_LINE_BYTES, ADDRESS_MAP, FRAME_BYTES,
                                   HEIGHT, STRIDE, WIDTH)
from pynq_vision.hardware import CsiReceiver, inspect_display_hwh, parse_hwh_addresses
from pynq_vision.prepare_overlay import inspect_display_handoff, main as prepare_main, prepare
from pynq_vision.ov5640 import MODE_720P_RAW10, RAW10_EXPECTED, SENSOR_INIT
from pynq_vision.vdma import (AxiVdma, FRAME_COUNTER_ONE, FRAME_COUNT_ENABLE, FRAME_IRQ_ENABLE,
                              FRAME_COMPLETE, HALTED, RUNSTOP, S2MM_CONTROL,
                              S2MM_STATUS, S2MM_VSIZE, stride_view,
                              sync_for_cpu, sync_for_device)
from pynq_vision.video import DynamicClock, VideoTimingController


class FakeMMIO:
    def __init__(self, vdma=False):
        self.values = {}
        self.writes = []
        self.vdma = vdma

    def read(self, offset):
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.writes.append((offset, value))
        # Model the self-clearing reset only for VDMA channel controls.
        is_vdma_control = self.vdma and offset in (0x00, 0x30)
        self.values[offset] = value & ~0x4 if is_vdma_control and value & 0x4 else value


class FakeBuffer(np.ndarray):
    def __new__(cls, address):
        obj = np.zeros(FRAME_BYTES, np.uint8).view(cls)
        obj.device_address = address
        obj.syncs = []
        return obj

    def sync_for_cpu_checked(self):
        self.syncs.append("cpu")
        return 0

    def sync_for_device_checked(self):
        self.syncs.append("device")
        return 0


class OfflineTests(unittest.TestCase):
    def test_stride_view_excludes_padding(self):
        buffer = np.zeros(FRAME_BYTES, np.uint8)
        view = stride_view(buffer)
        self.assertEqual(view.shape, (HEIGHT, WIDTH, 3))
        self.assertEqual(view.strides, (STRIDE, 3, 1))
        view[1, 0] = (1, 2, 3)
        np.testing.assert_array_equal(buffer[STRIDE:STRIDE + 3], (1, 2, 3))
        self.assertFalse(np.any(buffer[ACTIVE_LINE_BYTES:STRIDE]))

    def test_capture_vdma_programming_contract(self):
        io = FakeMMIO(vdma=True)
        buffers = [FakeBuffer(0x10000000 + i * 0x00400000) for i in range(3)]
        vdma = AxiVdma(io)
        vdma.configure(True, buffers, circular=True)
        self.assertEqual(io.values[S2MM_CONTROL], RUNSTOP | 0x2 | FRAME_COUNTER_ONE)
        self.assertEqual(io.values[S2MM_VSIZE], HEIGHT)
        self.assertEqual(vdma.validate_layout(True, buffers)["stride"], STRIDE)

    def test_one_shot_requires_complete_halt_and_copies_owned_slot(self):
        io = FakeMMIO(vdma=True)
        buffers = [FakeBuffer(0x10000000 + i * 0x00400000) for i in range(3)]
        vdma = AxiVdma(io)
        vdma.configure(True, buffers, circular=False, one_shot=True)
        self.assertEqual(io.values[S2MM_CONTROL], RUNSTOP | FRAME_COUNTER_ONE | FRAME_COUNT_ENABLE | FRAME_IRQ_ENABLE)
        self.assertEqual(io.writes[-1], (S2MM_VSIZE, HEIGHT))
        buffers[0][:] = 7
        io.values[S2MM_CONTROL] &= ~RUNSTOP
        io.values[S2MM_STATUS] = FRAME_COMPLETE | HALTED
        index, frame, _, _ = vdma.capture_copy(buffers)
        self.assertEqual(index, 0)
        self.assertTrue(np.all(frame == 7))
        self.assertEqual(buffers[0].syncs, ["cpu"])
        self.assertEqual(buffers[1].syncs, [])
        with patch.object(vdma, "status", side_effect=[FRAME_COMPLETE | HALTED,
                                                     FRAME_COMPLETE | HALTED | (1 << 15)]):
            with self.assertRaisesRegex(RuntimeError, "faulted"):
                vdma.capture_copy(buffers)

    def test_live_ring_copy_and_late_line_error_are_rejected(self):
        io = FakeMMIO(vdma=True)
        buffers = [FakeBuffer(0x10000000 + i * 0x00400000) for i in range(3)]
        vdma = AxiVdma(io)
        with self.assertRaisesRegex(RuntimeError, "active-ring"):
            vdma.capture_copy(buffers)
        vdma.configure(True, buffers, circular=False, one_shot=True)
        io.values[S2MM_CONTROL] &= ~RUNSTOP
        io.values[S2MM_STATUS] = FRAME_COMPLETE | HALTED | (1 << 15)
        with self.assertRaisesRegex(RuntimeError, "S2MM failed"):
            vdma.capture_copy(buffers)
        self.assertEqual(buffers[0].syncs, [])

    def test_frame_start_irq_is_not_completion_and_time_is_conservative(self):
        io = FakeMMIO(vdma=True)
        buffers = [FakeBuffer(0x10000000 + i * 0x00400000) for i in range(3)]
        dma = AxiVdma(io)
        dma.configure(True, buffers, circular=False, one_shot=True)
        dma.frame_start_lower_bound = 10.0
        io.values[S2MM_CONTROL] &= ~RUNSTOP
        original = io.read
        statuses = iter((0, FRAME_COMPLETE, FRAME_COMPLETE | HALTED))
        current = [0]
        def read(offset):
            if offset == S2MM_STATUS:
                current[0] = next(statuses, FRAME_COMPLETE | HALTED)
                return current[0]
            return original(offset)
        io.read = read
        quiesced = []
        def quiesce():
            self.assertEqual(current[0], FRAME_COMPLETE | HALTED)
            self.assertEqual(buffers[0].syncs, [])
            quiesced.append(True)
        with patch('pynq_vision.vdma.time.monotonic', side_effect=(11,12,12.1,13,13.1,14)), \
             patch('pynq_vision.vdma.time.sleep'):
            dma.capture_copy(buffers, timeout=10, after_halt=quiesce)
        self.assertEqual(quiesced, [True])
        self.assertEqual(dma.frame_start_lower_bound, 12)
        self.assertEqual(buffers[0].syncs, ['cpu'])

    def test_csi12_joint_snapshot_and_legacy_interface_rejection(self):
        class SnapshotIO(FakeMMIO):
            def write(self, offset, value):
                super().write(offset, value)
                if offset == 0x10:
                    self.values.update({0x10: 8, 4: 720, 8: 3})
        io = SnapshotIO()
        io.values.update({12: 0x00010002, 16: 7, 20: 0, 4: 1, 8: 0})
        result = CsiReceiver(io).snapshot()
        self.assertEqual((result['long_packets'], result['crc_errors'], result['snapshot_sequence']), (720,3,8))
        for version, busy in ((0x00010001,0),(0x00010002,1)):
            io = FakeMMIO()
            io.values.update({12: version, 20: busy})
            with self.assertRaisesRegex(RuntimeError, 'CSI1.2'):
                CsiReceiver(io).snapshot()
            self.assertEqual(io.writes, [])

    def test_csi_snapshot_timeout_never_returns_partial_counters(self):
        class BusyIO(FakeMMIO):
            def write(self, offset, value):
                super().write(offset, value)
                self.values[20] = 1
        io = BusyIO()
        io.values.update({12: 0x00010002, 20: 0, 16: 5})
        with patch('pynq_vision.hardware.time.monotonic', side_effect=(0,1)):
            with self.assertRaisesRegex(RuntimeError, 'handshake'):
                CsiReceiver(io).snapshot()

    def test_stop_timeout_does_not_pretend_halted(self):
        io = FakeMMIO(vdma=True)
        io.values[S2MM_CONTROL] = RUNSTOP
        with self.assertRaises(RuntimeError):
            AxiVdma(io).stop(True, timeout=0)
        self.assertEqual(io.values[S2MM_CONTROL] & RUNSTOP, 0)

    def test_missing_void_or_failed_sync_never_counts_as_success(self):
        for operation in (sync_for_cpu, sync_for_device):
            for status in (None, -5, False):
                class Buffer:
                    def sync_for_cpu_checked(self): return status
                    def sync_for_device_checked(self): return status
                with self.assertRaises(RuntimeError):
                    operation(Buffer())
            with self.assertRaises(RuntimeError):
                operation(object())

    def test_invalid_or_overlapping_spans_rejected_before_mmio(self):
        for addresses in [(0xFFFFC000, 0x10000000, 0x20000000),
                          (0x10000000, 0x10000040, 0x20000000)]:
            io = FakeMMIO(vdma=True)
            with self.assertRaises(ValueError):
                AxiVdma(io).configure(True, [FakeBuffer(x) for x in addresses], circular=False)
            self.assertEqual(io.writes, [])
        io = FakeMMIO(vdma=True)
        buffers = [FakeBuffer(0x10000000 + i * 0x00400000) for i in range(3)]
        buffers[0] = buffers[0][:64]
        with self.assertRaisesRegex(ValueError, "complete frame allocation"):
            AxiVdma(io).configure(True, buffers, circular=False, one_shot=True)
        self.assertEqual(io.writes, [])

    def test_fixed_clock_and_vtc_sequences(self):
        clock_io = FakeMMIO()
        # DynamicClock.start_720p expects the status bit to follow control.
        def clock_write(offset, value):
            clock_io.writes.append((offset, value))
            clock_io.values[offset] = value
            if offset == 0:
                clock_io.values[4] = value & 1
        clock_io.write = clock_write
        DynamicClock(clock_io).start_720p()
        self.assertEqual(clock_io.values[0x18], 0xCFAFA401)
        vtc_io = FakeMMIO()
        VideoTimingController(vtc_io).configure_720p()
        self.assertEqual(vtc_io.values[0x060], (720 << 16) | 1280)
        self.assertEqual(vtc_io.values[0x078], (1430 << 16) | 1390)
        self.assertEqual(vtc_io.values[0x000], 0x03FDEF06)

    def test_hwh_address_parser(self):
        elements = "".join(
            '<MEMRANGE INSTANCE="{}" MEMTYPE="REGISTER" BASEVALUE="0x{:08X}" '
            'HIGHVALUE="0x{:08X}"/>'.format(name, base, base + span - 1)
            for name, (base, span) in ADDRESS_MAP.items())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "system_wrapper.hwh"
            path.write_text("<ROOT>{}</ROOT>".format(elements), encoding="utf-8")
            self.assertEqual(parse_hwh_addresses(path), ADDRESS_MAP)

    def test_sensor_contract_never_selects_rgb565(self):
        final = dict(SENSOR_INIT + MODE_720P_RAW10)
        self.assertEqual({reg: final[reg] for reg in RAW10_EXPECTED}, RAW10_EXPECTED)
        self.assertNotIn((0x4300, 0x60), SENSOR_INIT + MODE_720P_RAW10)
        self.assertNotIn((0x501F, 0x01), SENSOR_INIT + MODE_720P_RAW10)


class DisplayHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xsa = Path(__file__).resolve().parents[2] / "color_test/color_test.xsa"
        if not cls.xsa.is_file():
            raise unittest.SkipTest("selected local XSA required; no hardware substitute")
        with zipfile.ZipFile(cls.xsa) as archive:
            cls.hwh = archive.read("system.hwh")

    def modified(self, instance, parameter, value):
        root = ET.fromstring(self.hwh)
        module = next(m for m in root.iter("MODULE") if m.get("INSTANCE") == instance)
        next(p for p in module.iter("PARAMETER") if p.get("NAME") == parameter).set("VALUE", value)
        return ET.tostring(root)

    def test_actual_pair_and_display_contract_without_hardware_import(self):
        before = {n for n in sys.modules if n == "pynq" or n.startswith("pynq.")}
        result = inspect_display_handoff(self.xsa)
        self.assertEqual(before, {n for n in sys.modules if n == "pynq" or n.startswith("pynq.")})
        self.assertEqual(result["resources"]["axi_vdma_0"]["base"], 0x43010000)
        self.assertEqual(result["mm2s_parameters"]["C_INCLUDE_MM2S_DRE"], "1")
        self.assertEqual(result["vtc_power_on_active"], [1280, 720])
        self.assertEqual(result["native_target"]["span"], 4608000)
        self.assertEqual(result["memory_path"]["ps_port"], "S_AXI_HP0")
        self.assertFalse(result["memory_path"]["runtime_ownership_verified"])
        self.assertEqual(result["generation"]["part"], "xc7z020clg400-2")
        self.assertEqual(result["current_loaded_identity"], "UNKNOWN")
        self.assertFalse(result["qualified_for_display"] or result["qualified_for_loading"])

    def test_direction_width_address_and_dre_mismatch_refused(self):
        for key, value in (("C_INCLUDE_MM2S", "0"), ("C_INCLUDE_S2MM", "1"),
                           ("C_M_AXI_MM2S_ADDR_WIDTH", "64"),
                           ("C_M_AXIS_MM2S_TDATA_WIDTH", "32"),
                           ("C_INCLUDE_MM2S_DRE", "0"), ("C_NUM_FSTORES", "2")):
            with self.subTest(parameter=key), self.assertRaisesRegex(RuntimeError, "MM2S"):
                inspect_display_hwh(self.modified("axi_vdma_0", key, value))

    def test_disconnected_axis_and_clock_refused(self):
        for tag, attr, name, value in (("BUSINTERFACE", "BUSNAME", "video_in", "foreign_axis"),
                                       ("PORT", "SIGNAME", "aclk", "foreign_clock")):
            with self.subTest(tag=tag):
                root = ET.fromstring(self.hwh)
                module = next(m for m in root.iter("MODULE") if m.get("INSTANCE") == "v_axi4s_vid_out_0")
                next(p for p in module.iter(tag) if p.get("NAME") == name).set(attr, value)
                with self.assertRaises(RuntimeError):
                    inspect_display_hwh(ET.tostring(root))

    def test_vtc_without_programming_interface_refused(self):
        with self.assertRaisesRegex(RuntimeError, "AXI-programmable"):
            inspect_display_hwh(self.modified("vtg", "C_HAS_AXI4_LITE", "0"))

    def test_disconnected_hp_memory_path_refused(self):
        root = ET.fromstring(self.hwh)
        module = next(m for m in root.iter("MODULE") if m.get("INSTANCE") == "processing_system7_0")
        next(b for b in module.iter("BUSINTERFACE") if b.get("NAME") == "S_AXI_HP0").set("BUSNAME", "foreign_hp")
        with self.assertRaisesRegex(RuntimeError, "HP0"):
            inspect_display_hwh(ET.tostring(root))

    def test_missing_or_duplicate_display_module_refused(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                root = ET.fromstring(self.hwh)
                module = next(m for m in root.iter("MODULE") if m.get("INSTANCE") == "rgb2dvi_0")
                parent = next(m for m in root.iter() if module in list(m))
                if duplicate:
                    parent.append(ET.fromstring(ET.tostring(module)))
                else:
                    parent.remove(module)
                with self.assertRaisesRegex(RuntimeError, "module/version"):
                    inspect_display_hwh(ET.tostring(root))

    def test_cli_report_creates_only_json_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display.json"
            args = ["--xsa", str(self.xsa), "--display-report", str(path)]
            with contextlib.redirect_stdout(io.StringIO()):
                prepare_main(args)
                original = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    prepare_main(args)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["display.json"])
            self.assertFalse(json.loads(original)["current_mode_verified"])

    def test_bad_xsa_refused_before_any_bundle_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "bad.xsa"
            bad.write_bytes(b"not the selected handoff")
            target = root / "bundle"
            with self.assertRaisesRegex(RuntimeError, "selected"):
                prepare(bad, target)
            self.assertFalse(target.exists())

    def test_existing_bundle_and_conflicting_modes_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileExistsError):
                prepare(self.xsa, root)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                prepare_main(["--xsa", str(self.xsa), "--display-report", str(root / "d.json"),
                              "--archive", str(root / "archive.zip")])
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
