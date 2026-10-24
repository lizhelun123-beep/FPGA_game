"""Hardware contract extracted from the matched 2023.1 XSA/HWH."""

WIDTH = 1280
HEIGHT = 720
BYTES_PER_PIXEL = 3
ACTIVE_LINE_BYTES = WIDTH * BYTES_PER_PIXEL
STRIDE = 5760
FRAME_BYTES = STRIDE * HEIGHT
FRAME_COUNT = 3

# These addresses were read from color_test/color_test.xsa:system.hwh.
# Hardware startup validates a parsed HWH map against them before MMIO use.
ADDRESS_MAP = {
    "axi_vdma_1": (0x43000000, 0x10000),  # capture S2MM
    "axi_vdma_0": (0x43010000, 0x10000),  # display MM2S
    "axi_dynclk_0": (0x43C00000, 0x10000),
    "vtg": (0x43C10000, 0x10000),
    "MIPI_D_PHY_RX_0": (0x43C20000, 0x10000),
    "MIPI_CSI_2_RX_0": (0x43C30000, 0x10000),
    "AXI_GammaCorrection_0": (0x43C40000, 0x10000),
}

XSA_SHA256 = "03AE58AC8483359101E5286931EFFB0D84544F4B9B6C215572FF88653011E0C8"
BIT_SHA256 = "A5A88800AF559C2E95AD67453DEAB7D4EC5BDFEAA3ECCDDC7279F0F2F64F3E55"
HWH_SHA256 = "DC899D44A94C1C98FFD6B7178E64F78FF6576FF3E4889759B291B659BABA347C"
MANIFEST_VERSION = 2

# PCW_ACT_FPGA*_PERIPHERAL_FREQMHZ, not the requested PCW_FPGA* values.
FCLK_MHZ = (100.0, 142.857132, 200.0)
FCLK_REQUESTED_MHZ = (100.0, 150.0, 200.0)
FCLK_TOLERANCE_MHZ = 0.1  # PS register-derived readback, not a jitter guarantee.

CAPTURE_IPS = ("axi_vdma_1", "MIPI_CSI_2_RX_0", "AXI_GammaCorrection_0")
CAPTURE_CONTRACT = {
    "sensor_mode": "720p RAW10", "lanes": 2, "width": WIDTH, "height": HEIGHT,
    "ddr_format": "BGR888", "active_line_bytes": ACTIVE_LINE_BYTES,
    "stride": STRIDE, "frame_bytes": FRAME_BYTES, "frame_count": FRAME_COUNT,
}


def check_frame_contract():
    if ACTIVE_LINE_BYTES != 3840 or STRIDE != 5760 or FRAME_BYTES != 4147200:
        raise RuntimeError("BGR888 frame contract was changed unexpectedly")
