"""Board-only orchestration with all PYNQ imports kept lazy."""

import hashlib
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import numpy as np

from .constants import (ADDRESS_MAP, BIT_SHA256, CAPTURE_CONTRACT, CAPTURE_IPS,
                        FCLK_MHZ, FCLK_REQUESTED_MHZ, FCLK_TOLERANCE_MHZ,
                        FRAME_BYTES, FRAME_COUNT, HWH_SHA256, MANIFEST_VERSION,
                        XSA_SHA256)
from .ov5640 import LinuxI2C, OV5640
from .vdma import AxiVdma, stride_view, sync_for_device
from .video import DynamicClock, VideoTimingController


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def _hwh_root(source):
    return ET.fromstring(source) if isinstance(source, bytes) else ET.parse(str(source)).getroot()


def parse_hwh_addresses(path):
    root = _hwh_root(path)
    addresses = {}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "MEMRANGE":
            continue
        attrs = element.attrib
        if attrs.get("MEMTYPE") != "REGISTER":
            continue
        base = int(attrs["BASEVALUE"], 0)
        high = int(attrs["HIGHVALUE"], 0)
        addresses[attrs["INSTANCE"]] = (base, high - base + 1)
    return addresses


def parse_hwh_clocks(path):
    root = _hwh_root(path)
    ps = [m for m in root.iter("MODULE") if m.get("MODTYPE") == "processing_system7"]
    if len(ps) != 1:
        raise RuntimeError("exactly one PS7 clock source is required")
    params = {p.get("NAME"): p.get("VALUE") for p in ps[0].iter("PARAMETER")}
    try:
        requested = [float(params["PCW_FPGA{}_PERIPHERAL_FREQMHZ".format(i)]) for i in range(3)]
        actual = [float(params["PCW_ACT_FPGA{}_PERIPHERAL_FREQMHZ".format(i)]) for i in range(3)]
        ports = {p.get("NAME"): p for p in ps[0].iter("PORT")}
        port_mhz = [float(ports["FCLK_CLK{}".format(i)].get("CLKFREQUENCY")) / 1e6
                    for i in range(3)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("HWH actual/requested PS clocks or output-port rates missing") from exc
    if (tuple(requested) != FCLK_REQUESTED_MHZ or tuple(actual) != FCLK_MHZ or
            any(not math.isfinite(v) or abs(v - expected) > 1e-6
                for v, expected in zip(port_mhz, FCLK_MHZ))):
        raise RuntimeError("HWH PS clock contract mismatch")
    return {"requested_mhz": requested, "actual_mhz": actual,
            "output_port_mhz": port_mhz, "readback_tolerance_mhz": FCLK_TOLERANCE_MHZ}


def validate_hwh_contract(source):
    addresses = parse_hwh_addresses(source)
    mismatched = {name: (addresses.get(name), expected)
                  for name, expected in ADDRESS_MAP.items() if addresses.get(name) != expected}
    if mismatched:
        raise RuntimeError("HWH address contract mismatch: {!r}".format(mismatched))
    return addresses, parse_hwh_clocks(source)


def inspect_display_hwh(source):
    """Offline display binding facts from the selected handoff, never approval.

    Validate the real direction/width/clock wiring before treating its address
    map as a usable native binding contract. Output clock attributes and VTC
    defaults are declarations, not the currently programmed physical mode.
    """
    addresses, clocks = validate_hwh_contract(source)
    root = _hwh_root(source)
    modules = {}
    expected = {"axi_vdma_0": "xilinx.com:ip:axi_vdma:6.3",
                "axi_dynclk_0": "digilentinc.com:ip:axi_dynclk:1.0",
                "vtg": "xilinx.com:ip:v_tc:6.2",
                "v_axi4s_vid_out_0": "xilinx.com:ip:v_axi4s_vid_out:4.0",
                "rgb2dvi_0": "digilentinc.com:ip:rgb2dvi:1.3"}
    for name, vlnv in expected.items():
        found = [m for m in root.iter("MODULE") if m.get("INSTANCE") == name]
        if len(found) != 1 or found[0].get("VLNV") != vlnv:
            raise RuntimeError("display module/version mismatch: " + name)
        modules[name] = found[0]
    params = {p.get("NAME"): p.get("VALUE") for p in modules["axi_vdma_0"].iter("PARAMETER")}
    required = {"C_INCLUDE_MM2S": "1", "C_INCLUDE_S2MM": "0", "C_INCLUDE_SG": "0",
                "C_NUM_FSTORES": "3", "C_M_AXI_MM2S_ADDR_WIDTH": "32",
                "C_M_AXI_MM2S_DATA_WIDTH": "64", "C_M_AXIS_MM2S_TDATA_WIDTH": "24",
                "C_INCLUDE_MM2S_DRE": "1", "C_MM2S_GENLOCK_MODE": "0"}
    if any(params.get(k) != v for k, v in required.items()):
        raise RuntimeError("display MM2S direction/width/store contract mismatch")
    vp = {p.get("NAME"): p.get("VALUE") for p in modules["vtg"].iter("PARAMETER")}
    if vp.get("C_HAS_AXI4_LITE") != "1":
        raise RuntimeError("VTC generator is not AXI-programmable")
    wiring = {}
    ports = {name: {p.get("NAME"): p for p in module.iter("PORT")}
             for name, module in modules.items()}
    required_clocks = (("axi_vdma_0", "s_axi_lite_aclk", "processing_system7_0_FCLK_CLK0"),
                       ("axi_vdma_0", "m_axi_mm2s_aclk", "processing_system7_0_FCLK_CLK1"),
                       ("axi_vdma_0", "m_axis_mm2s_aclk", "processing_system7_0_FCLK_CLK1"),
                       ("axi_dynclk_0", "REF_CLK_I", "processing_system7_0_FCLK_CLK0"),
                       ("vtg", "clk", "axi_dynclk_0_PXL_CLK_O"),
                       ("v_axi4s_vid_out_0", "aclk", "processing_system7_0_FCLK_CLK1"),
                       ("v_axi4s_vid_out_0", "vid_io_out_clk", "axi_dynclk_0_PXL_CLK_O"),
                       ("rgb2dvi_0", "PixelClk", "axi_dynclk_0_PXL_CLK_O"),
                       ("rgb2dvi_0", "SerialClk", "axi_dynclk_0_PXL_CLK_5X_O"))
    for name, port, signal in required_clocks:
        info = ports[name].get(port)
        if info is None or info.get("SIGNAME") != signal:
            raise RuntimeError("display clock connection mismatch: " + name + "/" + port)
        wiring[name + "/" + port] = {"signal": signal, "hwh_hz": info.get("CLKFREQUENCY")}
    buses = {name: {b.get("NAME"): b.get("BUSNAME") for b in module.iter("BUSINTERFACE")}
             for name, module in modules.items()}
    stream = buses["axi_vdma_0"].get("M_AXIS_MM2S")
    timing = buses["vtg"].get("vtiming_out")
    if (not stream or stream != buses["v_axi4s_vid_out_0"].get("video_in") or
            not timing or timing != buses["v_axi4s_vid_out_0"].get("vtiming_in")):
        raise RuntimeError("VDMA/video-out/VTC stream connection mismatch")
    memory_nodes = {}
    for name in ("axi_mem_intercon", "processing_system7_0"):
        found = [m for m in root.iter("MODULE") if m.get("INSTANCE") == name]
        if len(found) != 1:
            raise RuntimeError("display memory path module mismatch: " + name)
        memory_nodes[name] = {b.get("NAME"): b.get("BUSNAME")
                              for b in found[0].iter("BUSINTERFACE")}
    memory_bus = buses["axi_vdma_0"].get("M_AXI_MM2S")
    hp_bus = memory_nodes["axi_mem_intercon"].get("M00_AXI")
    if (not memory_bus or not hp_bus or
            memory_bus != memory_nodes["axi_mem_intercon"].get("S00_AXI") or
            hp_bus != memory_nodes["processing_system7_0"].get("S_AXI_HP0")):
        raise RuntimeError("display MM2S/interconnect/HP0 connection mismatch")
    return {"scope": "offline selected-handoff display contract only",
            "resources": {n: {"base": addresses[n][0], "span": addresses[n][1], "vlnv": expected[n]}
                          for n in ("axi_vdma_0", "axi_dynclk_0", "vtg")},
            "mm2s_parameters": {k: params[k] for k in required}, "declared_fclks": clocks,
            "clock_wiring": wiring, "stream_bus": stream, "timing_bus": timing,
            "memory_path": {"vdma_bus": memory_bus, "hp_bus": hp_bus,
                            "ps_port": "S_AXI_HP0", "runtime_ownership_verified": False},
            "vtc_power_on_active": [int(vp["C_GEN_HACTIVE_SIZE"]), int(vp["C_GEN_VACTIVE_SIZE"])],
            "native_target": {"width": 1280, "height": 800, "hsize": 3840,
                              "stride": 5760, "span": 4608000},
            "current_loaded_identity": "UNKNOWN", "current_mode_verified": False,
            "qualified_for_loading": False, "qualified_for_display": False}


def inspect_overlay_files(bit_path):
    bit_path = Path(bit_path)
    hwh_path = bit_path.with_suffix(".hwh")
    if not bit_path.is_file() or not hwh_path.is_file():
        raise FileNotFoundError("matching .bit and .hwh files are required")
    bit_hash = sha256(bit_path)
    hwh_hash = sha256(hwh_path)
    if bit_hash != BIT_SHA256 or hwh_hash != HWH_SHA256:
        raise RuntimeError("overlay hashes do not match the inspected 2023.1 XSA")
    addresses, clocks = validate_hwh_contract(hwh_path)
    manifest_path = bit_path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {"schema_version": MANIFEST_VERSION, "source_xsa": "color_test.xsa",
                "source_xsa_sha256": XSA_SHA256, "bit_sha256": bit_hash,
                "hwh_sha256": hwh_hash, "clocks": clocks,
                "capture_contract": CAPTURE_CONTRACT,
                "addresses": {name: list(value) for name, value in addresses.items()}}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise RuntimeError("manifest/XSA/clock contract mismatch; prepare a coherent bundle")
    xsa_path = bit_path.parent / "color_test.xsa"
    if sha256(xsa_path) != XSA_SHA256:
        raise RuntimeError("source XSA hash mismatch")
    return {
        "bit": str(bit_path),
        "hwh": str(hwh_path),
        "bit_sha256": bit_hash,
        "hwh_sha256": hwh_hash,
        "addresses": addresses,
        "source_xsa": str(xsa_path),
        "source_xsa_sha256": XSA_SHA256,
        "clocks": clocks,
        "capture_contract": CAPTURE_CONTRACT,
        "production_pl_qualified": False,
    }


def _validate_pynq_ip_dict(ip_dict):
    for name, (base, span) in ADDRESS_MAP.items():
        info = ip_dict.get(name)
        if info is None:
            raise RuntimeError("PYNQ HWH parser omitted {!r}".format(name))
        if int(info["phys_addr"]) != base or int(info["addr_range"]) != span:
            raise RuntimeError("PYNQ address mismatch for {!r}: {!r}".format(name, info))


def load_overlay(bit_path):
    """Load PL after local pair/address checks; tolerate only HWH parser failure."""
    report = inspect_overlay_files(bit_path)
    try:
        from pynq import Overlay
        overlay = Overlay(str(bit_path), download=False)
    except Exception as exc:
        # PYNQ 2.6 may reject a Vivado 2023.1 HWH. The checked address map is
        # then used explicitly, while Bitstream performs only PL programming.
        from pynq import Bitstream
        bitstream = Bitstream(str(bit_path))
        bitstream.download()
        report["load_mode"] = "Bitstream+explicit-MMIO"
        report["hwh_parser_error"] = repr(exc)
        return bitstream, report
    # An address disagreement is not a parser compatibility exception and must
    # never trigger a fallback download.
    _validate_pynq_ip_dict(overlay.ip_dict)
    overlay.download()
    report["load_mode"] = "Overlay"
    return overlay, report


def configure_fclks():
    try:
        from pynq import Clocks
    except ImportError:
        from pynq.ps import Clocks
    before = tuple(float(getattr(Clocks, "fclk{}_mhz".format(index)))
                   for index in range(len(FCLK_MHZ)))
    for index, mhz in enumerate(FCLK_MHZ):
        setattr(Clocks, "fclk{}_mhz".format(index), mhz)
    actual = tuple(float(getattr(Clocks, "fclk{}_mhz".format(index)))
                   for index in range(len(FCLK_MHZ)))
    if any(not math.isfinite(value) or abs(value - expected) > FCLK_TOLERANCE_MHZ
           for value, expected in zip(actual, FCLK_MHZ)):
        raise RuntimeError("unexpected FCLK frequencies: {!r}".format(actual))
    return {"before_mhz": before, "readback_mhz": actual, "expected_mhz": FCLK_MHZ,
            "tolerance_mhz": FCLK_TOLERANCE_MHZ,
            "measurement": "PYNQ PS PLL/divider register-derived; not oscilloscope or MIPI jitter"}


def _mmio_blocks(names):
    from pynq import MMIO
    return {name: MMIO(*ADDRESS_MAP[name]) for name in names}


def _require_qualified_dma_backend():
    """Closed until this image has a reviewed allocator/sync/release backend.

    No force switch: the legacy libcma interface and the observed zocl CMA
    release path do not currently satisfy the lifecycle contract.
    """
    raise RuntimeError("No qualified DMA allocator/sync/release backend for this image")


def _allocate_frames():
    _require_qualified_dma_backend()
    raise RuntimeError("qualified allocator implementation is not installed")


def _release(buffer):
    method = getattr(buffer, "release_checked", None)
    if method is None:
        raise RuntimeError("qualified status-returning buffer release is required")
    status = method()
    if type(status) is not int or status != 0:
        raise RuntimeError("buffer release did not confirm success: {!r}".format(status))


def draw_color_bars(buffer):
    frame = stride_view(buffer)
    colors = np.array(((255, 255, 255), (0, 255, 255), (255, 255, 0),
                       (0, 255, 0), (255, 0, 255), (0, 0, 255),
                       (255, 0, 0), (0, 0, 0)), dtype=np.uint8)
    edges = np.linspace(0, frame.shape[1], len(colors) + 1, dtype=np.int32)
    for index, color in enumerate(colors):
        frame[:, edges[index]:edges[index + 1], :] = color
    sync_for_device(buffer)


class CameraReset:
    def __init__(self):
        from pynq import GPIO
        self.gpio = GPIO(GPIO.get_gpio_pin(0), "out")  # PS GPIO 54 / EMIO[0]

    def pulse(self):
        self.gpio.write(0)
        time.sleep(1.0)
        self.gpio.write(1)
        time.sleep(1.0)

    def hold(self):
        self.gpio.write(0)


class CsiReceiver:
    ENABLE = 0x02
    RESET = 0x01
    OVERFLOW = 0x80000000

    def __init__(self, io):
        from .registers import RegisterBlock
        self.regs = RegisterBlock(io)

    def reset_enable(self):
        self.regs.write(0x00, self.ENABLE | self.RESET)
        time.sleep(0.001)
        self.regs.write(0x00, self.ENABLE)
        time.sleep(0.001)

    def snapshot(self):
        # Production1.2 snapshots both counters in their actual video domain.
        # Sequence identifies a snapshot, never a camera frame or exposure.
        version = self.regs.read(0x0C)
        if version != 0x00010002 or self.regs.read(0x14) & 1:
            raise RuntimeError("CSI1.2 idle snapshot interface is required")
        sequence = self.regs.read(0x10)
        expected = (sequence + 1) & 0xFFFFFFFF
        self.regs.write(0x10, 1)
        deadline = time.monotonic() + 0.1
        while self.regs.read(0x14) & 1 or self.regs.read(0x10) != expected:
            if time.monotonic() >= deadline:
                raise RuntimeError("CSI snapshot handshake did not complete")
            time.sleep(0.0001)
        result = {"control": self.regs.read(0x00),
                  "long_packets": self.regs.read(0x04),
                  "crc_errors": self.regs.read(0x08),
                  "version": version, "snapshot_sequence": expected}
        if self.regs.read(0x10) != expected or self.regs.read(0x14) & 1:
            raise RuntimeError("CSI snapshot changed during read")
        return result

    def validate_window(self, before, after):
        packet_delta = (after["long_packets"] - before["long_packets"]) & 0xFFFFFFFF
        crc_delta = (after["crc_errors"] - before["crc_errors"]) & 0xFFFFFFFF
        if not packet_delta or crc_delta or after["control"] & self.OVERFLOW:
            raise RuntimeError("unhealthy CSI window: before={!r}, after={!r}".format(
                before, after))
        return {"packet_delta": packet_delta, "crc_delta": crc_delta}


class CameraPipeline:
    """Capture only by default; legacy HDMI requires explicit enable_display."""

    def __init__(self, bit_path, i2c_device, enable_display=False):
        self.bit_path = Path(bit_path)
        self.i2c_device = i2c_device
        self.enable_display = enable_display
        self.stage = "not_started"
        self.overlay = None
        self.overlay_report = None
        self.blocks = None
        self.capture_buffers = []
        self.display_buffers = []
        self.capture_vdma = None
        self.display_vdma = None
        self.csi = None
        self.sensor_bus = None
        self.sensor = None
        self.reset_gpio = None
        self.display_index = 0

    def open(self):
        self.stage = "dma_backend_qualification"
        _require_qualified_dma_backend()
        self.stage = "artifact_preflight_and_pl_load"
        self.overlay, self.overlay_report = load_overlay(self.bit_path)
        self.stage = "fclk_configure_and_readback"
        self.overlay_report["fclk"] = configure_fclks()
        self.overlay_report["display_enabled"] = self.enable_display
        self.stage = "capture_mmio_and_buffers"
        self.blocks = _mmio_blocks(ADDRESS_MAP if self.enable_display else CAPTURE_IPS)
        self.capture_vdma = AxiVdma(self.blocks["axi_vdma_1"])
        self.csi = CsiReceiver(self.blocks["MIPI_CSI_2_RX_0"])
        self.capture_buffers = _allocate_frames()

        # Gamma selector is write-only in this custom IP: 3 means 1/1.8.
        self.blocks["AXI_GammaCorrection_0"].write(0, 3)
        if self.enable_display:
            self.stage = "legacy_hdmi_start"
            self.display_vdma = AxiVdma(self.blocks["axi_vdma_0"])
            self.display_buffers = _allocate_frames()
            DynamicClock(self.blocks["axi_dynclk_0"]).start_720p()
            VideoTimingController(self.blocks["vtg"]).configure_720p()
            draw_color_bars(self.display_buffers[0])
            self.display_vdma.configure(False, self.display_buffers, circular=False)
            self.display_vdma.park_read(0)
            self.display_vdma.validate_layout(False, self.display_buffers)

        self.stage = "camera_reset_and_raw10_configure"
        self.reset_gpio = CameraReset()
        self.reset_gpio.pulse()
        self.sensor_bus = LinuxI2C(self.i2c_device).open()
        self.sensor = OV5640(self.sensor_bus)
        self.sensor.configure_raw10_720p()
        self.csi.reset_enable()
        self.capture_vdma.configure(True, self.capture_buffers, circular=True)
        self.capture_vdma.validate_layout(True, self.capture_buffers)
        before = self.csi.snapshot()
        self.capture_vdma.clear_frame_complete(True)
        self.stage = "sensor_start_and_first_frame"
        self.sensor.start()
        time.sleep(1.0)
        controls = self.sensor.lock_exposure_gain()
        self.capture_vdma.wait_frame(2.0)
        after = self.csi.snapshot()
        self.overlay_report["first_csi_window"] = self.csi.validate_window(before, after)
        self.overlay_report["locked_controls"] = controls
        # The next capture() must wait for a new complete frame and measure a
        # matching CSI counter window, not consume this startup indication.
        self.capture_vdma.clear_frame_complete(True)
        self.stage = "ready"
        return self

    def capture(self):
        self.stage = "single_frame_capture"
        before = self.csi.snapshot()
        started = time.perf_counter()
        index, frame, cache_sync_ms, copy_ms = self.capture_vdma.capture_copy(
            self.capture_buffers)
        acquire_ms = (time.perf_counter() - started) * 1000.0
        after = self.csi.snapshot()
        health = self.csi.validate_window(before, after)
        if not np.any(frame):
            raise RuntimeError("captured active image is all zero")
        return frame, {"capture_index": index, "acquire_ms": acquire_ms,
                       "cache_sync_ms": cache_sync_ms,
                       "stride_copy_ms": copy_ms, **health}

    def present(self, bgr):
        if not self.enable_display:
            raise RuntimeError("HDMI is disabled in capture-only mode")
        if bgr.shape != (720, 1280, 3) or bgr.dtype != np.uint8:
            raise ValueError("display frame must be uint8 BGR 720x1280x3")
        current = self.display_vdma.current_read_index()
        if current >= FRAME_COUNT:
            raise RuntimeError("invalid MM2S read frame index {}".format(current))
        next_index = (current + 1) % FRAME_COUNT
        started = time.perf_counter()
        stride_view(self.display_buffers[next_index])[:] = bgr
        sync_for_device(self.display_buffers[next_index])
        self.display_vdma.park_read(next_index)
        self.display_index = next_index
        return (time.perf_counter() - started) * 1000.0

    def close(self):
        # Retain every owned buffer if either channel's stop is unconfirmed.
        # This method must not be used as an atexit/free-on-GC fallback.
        if self.stage == "retained_unconfirmed_release":
            raise RuntimeError("buffer release outcome is unknown; automatic retry is unsafe")
        self.stage = "stop_and_release"
        try:
            if self.capture_vdma is not None:
                self.capture_vdma.stop(True)
            if self.display_vdma is not None:
                self.display_vdma.stop(False)
            if self.reset_gpio is not None:
                self.reset_gpio.hold()
        except BaseException:
            self.stage = "retained_unconfirmed_stop"
            raise
        try:
            if self.sensor_bus is not None:
                self.sensor_bus.close()
                self.sensor_bus = None
            for buffers in (self.capture_buffers, self.display_buffers):
                while buffers:
                    _release(buffers[0])
                    del buffers[0]
        except BaseException:
            self.stage = "retained_unconfirmed_release"
            raise
        self.stage = "closed"

    def __enter__(self):
        try:
            return self.open()
        except Exception:
            failed_stage = self.stage
            self.close()
            self.stage = failed_stage
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
