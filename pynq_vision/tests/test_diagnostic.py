"""No board imports: test artifact rejection and capture/display isolation."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from pynq_vision import app, hardware
from pynq_vision.constants import (ADDRESS_MAP, BIT_SHA256, CAPTURE_IPS,
                                   FCLK_MHZ, HWH_SHA256, XSA_SHA256)
from pynq_vision.prepare_overlay import prepare

XSA = Path(__file__).resolve().parents[2] / "color_test" / "color_test.xsa"


@unittest.skipUnless(XSA.is_file(), "selected local XSA is required for artifact integration checks")
class ArtifactTests(unittest.TestCase):
    def test_bundle_binds_xsa_embedded_pair_clocks_and_source_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            archive_path = Path(directory) / "capture.zip"
            manifest = prepare(XSA, output, archive_path)
            report = hardware.inspect_overlay_files(output / "system_wrapper.bit")
            self.assertEqual(report["source_xsa_sha256"], XSA_SHA256)
            self.assertEqual(report["bit_sha256"], BIT_SHA256)
            self.assertEqual(report["hwh_sha256"], HWH_SHA256)
            self.assertEqual(tuple(report["clocks"]["actual_mhz"]), FCLK_MHZ)
            self.assertEqual(report["clocks"]["requested_mhz"], [100.0, 150.0, 200.0])
            self.assertFalse(manifest["production_pl_qualified"])
            for line in (output / "SHA256SUMS").read_text().splitlines():
                expected, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            with zipfile.ZipFile(str(archive_path)) as archive:
                for path in output.rglob("*"):
                    if path.is_file():
                        member = output.name + "/" + path.relative_to(output).as_posix()
                        self.assertEqual(archive.read(member), path.read_bytes())
            with self.assertRaises(FileExistsError):
                prepare(XSA, output)

    def test_tampered_inputs_fail_before_pynq_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            bad_xsa = directory / "bad.xsa"
            bad_xsa.write_bytes(b"not the selected XSA")
            with self.assertRaisesRegex(RuntimeError, "XSA"):
                prepare(bad_xsa, directory / "never_created")
            self.assertFalse((directory / "never_created").exists())
            output = directory / "capture"
            prepare(XSA, output)
            bit = output / "system_wrapper.bit"
            original = bit.read_bytes()
            for member in ("system_wrapper.bit", "system_wrapper.hwh", "color_test.xsa"):
                path = output / member
                saved = path.read_bytes()
                path.write_bytes(saved + b"tamper")
                with patch.dict(sys.modules, {"pynq": None}):
                    with self.assertRaises(RuntimeError):
                        hardware.load_overlay(bit)
                path.write_bytes(saved)
            self.assertEqual(bit.read_bytes(), original)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["clocks"]["actual_mhz"][1] = 150.0
            manifest_path.write_text(json.dumps(manifest))
            with patch.object(app, "CameraPipeline") as pipeline:
                with self.assertRaisesRegex(RuntimeError, "manifest"):
                    app.main(["--overlay", str(bit), "capture", "--i2c-device",
                              "/dev/not-opened", "--output", str(directory / "no_capture")])
                pipeline.assert_not_called()
            self.assertFalse((directory / "no_capture").exists())

    def test_unknown_hwh_clocks_and_addresses_are_rejected(self):
        with zipfile.ZipFile(str(XSA)) as archive:
            hwh = archive.read("system.hwh")
        # Independent XML checks still reject wrong metadata if hashes were updated later.
        for bad in (hwh.replace(b'NAME="PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ"', b'NAME="UNKNOWN"'),
                    hwh.replace(b'142.857132', b'150.000000')):
            with self.assertRaises(RuntimeError):
                hardware.validate_hwh_contract(bad)
        root = ET.fromstring(hwh)
        for entry in root.iter("MEMRANGE"):
            if entry.get("INSTANCE") == "axi_vdma_1":
                entry.set("BASEVALUE", "0x44000000")
        with self.assertRaisesRegex(RuntimeError, "address"):
            hardware.validate_hwh_contract(ET.tostring(root))


class StartupTests(unittest.TestCase):
    def test_pynq_address_disagreement_never_falls_back_to_download(self):
        overlay = MagicMock(ip_dict={})
        pynq = SimpleNamespace(Overlay=MagicMock(return_value=overlay), Bitstream=MagicMock())
        with patch.dict(sys.modules, {"pynq": pynq}), \
                patch.object(hardware, "inspect_overlay_files", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "omitted"):
                hardware.load_overlay("checked.bit")
        overlay.download.assert_not_called()
        pynq.Bitstream.assert_not_called()

    def test_parser_failure_uses_checked_bitstream_fallback(self):
        pynq = SimpleNamespace(Overlay=MagicMock(side_effect=ValueError("old HWH parser")),
                               Bitstream=MagicMock())
        with patch.dict(sys.modules, {"pynq": pynq}), \
                patch.object(hardware, "inspect_overlay_files", return_value={}):
            _, report = hardware.load_overlay("checked.bit")
        pynq.Bitstream.return_value.download.assert_called_once_with()
        self.assertEqual(report["load_mode"], "Bitstream+explicit-MMIO")

    def test_clock_writes_use_actual_hwh_rates_and_validate_readback(self):
        class Clocks:
            fclk0_mhz, fclk1_mhz, fclk2_mhz = (10.0, 10.0, 10.0)

        clocks = Clocks()
        with patch.dict(sys.modules, {"pynq": SimpleNamespace(Clocks=clocks)}):
            report = hardware.configure_fclks()
        self.assertEqual(report["before_mhz"], (10.0, 10.0, 10.0))
        self.assertEqual(report["readback_mhz"], FCLK_MHZ)
        self.assertAlmostEqual(clocks.fclk1_mhz, 142.857132)

        class WrongClocks:
            def __init__(self, value):
                object.__setattr__(self, "value", value)

            def __getattr__(self, name):
                return self.value

            def __setattr__(self, name, value):
                pass  # Model an unavailable/incorrect hardware clock source.

        for value in (150.0, float("nan"), float("inf"), 0.0):
            with patch.dict(sys.modules, {"pynq": SimpleNamespace(Clocks=WrongClocks(value))}):
                with self.assertRaisesRegex(RuntimeError, "FCLK"):
                    hardware.configure_fclks()

    def test_clock_failure_precedes_dma_gpio_i2c_and_display(self):
        pipeline = hardware.CameraPipeline("checked.bit", "/dev/not-opened")
        with patch.object(hardware, "load_overlay", return_value=(object(), {})), \
                patch.object(hardware, "_require_qualified_dma_backend"), \
                patch.object(hardware, "configure_fclks", side_effect=RuntimeError("FCLK fail")), \
                patch.object(hardware, "_mmio_blocks") as blocks, \
                patch.object(hardware, "_allocate_frames") as allocate, \
                patch.object(hardware, "CameraReset") as gpio, \
                patch.object(hardware, "LinuxI2C") as bus:
            with self.assertRaisesRegex(RuntimeError, "FCLK fail"):
                with pipeline:
                    self.fail("pipeline entered after failed clock check")
        for mock in (blocks, allocate, gpio, bus):
            mock.assert_not_called()

    def test_headless_full_lifecycle_never_touches_display(self):
        blocks = {name: MagicMock(name=name) for name in CAPTURE_IPS}
        buffers = [MagicMock() for _ in range(3)]
        for buffer in buffers:
            buffer.release_checked.return_value = 0
        dma = MagicMock()
        frame = np.ones((720, 1280, 3), dtype=np.uint8)
        dma.capture_copy.return_value = (0, frame, 0.1, 0.2)
        csi = MagicMock()
        csi.validate_window.return_value = {"packet_delta": 720, "crc_delta": 0}
        with contextlib.ExitStack() as stack:
            def stub(name, **kwargs):
                return stack.enter_context(patch.object(hardware, name, **kwargs))
            stub("load_overlay", return_value=(object(), {}))
            stub("_require_qualified_dma_backend")
            stub("configure_fclks", return_value={"readback_mhz": FCLK_MHZ})
            mmio = stub("_mmio_blocks", return_value=blocks)
            allocate = stub("_allocate_frames", return_value=buffers)
            vdma = stub("AxiVdma", return_value=dma)
            stub("CsiReceiver", return_value=csi)
            gpio = stub("CameraReset")
            bus = stub("LinuxI2C")
            sensor = stub("OV5640")
            stub("time", sleep=MagicMock(), perf_counter=MagicMock(return_value=1.0))
            dynclk, vtc, bars = (stub(name, side_effect=AssertionError("HDMI touched"))
                                for name in ("DynamicClock", "VideoTimingController", "draw_color_bars"))
            with hardware.CameraPipeline("checked.bit", "/dev/verified") as pipeline:
                captured, _ = pipeline.capture()
                self.assertIs(captured, frame)
                self.assertFalse(pipeline.overlay_report["display_enabled"])
                self.assertEqual(pipeline.display_buffers, [])
                with self.assertRaisesRegex(RuntimeError, "HDMI is disabled"):
                    pipeline.present(frame)
            mmio.assert_called_once_with(CAPTURE_IPS)
            allocate.assert_called_once_with()
            vdma.assert_called_once_with(blocks["axi_vdma_1"])
            dma.configure.assert_called_once_with(True, buffers, circular=True)
            dma.stop.assert_called_once_with(True)
            dma.reset.assert_not_called()
            for mock in (dynclk, vtc, bars):
                mock.assert_not_called()
            gpio.return_value.pulse.assert_called_once_with()
            gpio.return_value.hold.assert_called_once_with()
            bus.return_value.open.return_value.close.assert_called_once_with()
            sensor.return_value.configure_raw10_720p.assert_called_once_with()
            for buffer in buffers:
                buffer.release_checked.assert_called_once_with()
                buffer.freebuffer.assert_not_called()

    def test_unqualified_backend_blocks_all_device_actions(self):
        with contextlib.ExitStack() as stack:
            actions = [stack.enter_context(patch.object(hardware, name)) for name in
                       ("load_overlay", "configure_fclks", "_mmio_blocks", "CameraReset", "LinuxI2C")]
            with self.assertRaisesRegex(RuntimeError, "No qualified DMA"):
                hardware.CameraPipeline("checked.bit", "/dev/verified").open()
            pipeline = hardware.CameraPipeline("checked.bit", "/dev/verified")
            with self.assertRaisesRegex(RuntimeError, "No qualified DMA"):
                with pipeline:
                    self.fail("unqualified pipeline entered")
            self.assertEqual(pipeline.stage, "dma_backend_qualification")
            with self.assertRaisesRegex(RuntimeError, "No qualified DMA"):
                hardware._allocate_frames()
            for action in actions:
                action.assert_not_called()

    def test_unknown_halt_retains_buffers_and_device_owner(self):
        pipeline = hardware.CameraPipeline("checked.bit", "/dev/verified")
        pipeline.capture_vdma = MagicMock()
        pipeline.capture_vdma.stop.side_effect = RuntimeError("HALTED unknown")
        pipeline.sensor_bus = MagicMock()
        owned = [MagicMock(), MagicMock()]
        pipeline.capture_buffers = list(owned)
        with self.assertRaisesRegex(RuntimeError, "HALTED unknown"):
            pipeline.close()
        self.assertEqual(pipeline.capture_buffers, owned)
        self.assertEqual(pipeline.stage, "retained_unconfirmed_stop")
        pipeline.sensor_bus.close.assert_not_called()
        for buffer in owned:
            buffer.release_checked.assert_not_called()
        pipeline.capture_vdma.stop.side_effect = None
        for buffer in owned:
            buffer.release_checked.return_value = 0
        pipeline.close()
        self.assertEqual(pipeline.capture_buffers, [])

    def test_unknown_release_retains_remaining_and_refuses_automatic_retry(self):
        pipeline = hardware.CameraPipeline("checked.bit", "/dev/verified")
        first, second, third = [MagicMock() for _ in range(3)]
        first.release_checked.return_value = third.release_checked.return_value = 0
        second.release_checked.return_value = None
        pipeline.capture_buffers = [first, second, third]
        with self.assertRaisesRegex(RuntimeError, "release did not confirm"):
            pipeline.close()
        self.assertEqual(pipeline.capture_buffers, [second, third])
        self.assertEqual(pipeline.stage, "retained_unconfirmed_release")
        with self.assertRaisesRegex(RuntimeError, "automatic retry is unsafe"):
            pipeline.close()
        self.assertEqual(pipeline.capture_buffers, [second, third])
        first.release_checked.assert_called_once_with()
        second.release_checked.assert_called_once_with()
        third.release_checked.assert_not_called()

    def test_capture_cli_is_headless_and_logs_failure_without_pc_detector(self):
        for failure in (False, True):
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(app, "inspect_overlay_files", return_value={"checked": True}), \
                    patch.object(app, "CameraPipeline") as factory, \
                    patch.dict(sys.modules, {"pc_vision": None}), \
                    contextlib.redirect_stdout(io.StringIO()):
                pipeline = factory.return_value
                pipeline.__enter__.return_value = pipeline
                pipeline.stage = "single_frame_capture"
                pipeline.overlay_report = {"display_enabled": False}
                if failure:
                    pipeline.capture.side_effect = RuntimeError("no frame")
                else:
                    pipeline.capture.return_value = (np.ones((720, 1280, 3), np.uint8), {})
                args = ["--overlay", "checked.bit", "capture", "--i2c-device", "/dev/verified",
                        "--output", str(Path(directory) / "capture")]
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "no frame"):
                        app.main(args)
                else:
                    app.main(args)
                factory.assert_called_once_with(Path("checked.bit"), "/dev/verified", enable_display=False)
                record = json.loads((Path(directory) / "capture/capture.json").read_text())
                self.assertEqual(record["status"], "FAIL" if failure else "PASS")
                self.assertEqual(record["stage"], "single_frame_capture")
                self.assertEqual((Path(directory) / "capture/frame.png").exists(), not failure)


if __name__ == "__main__":
    unittest.main()
