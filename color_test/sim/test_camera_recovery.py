"""Host fault-injection tests for the actual CameraCheck/CameraStart C functions.

Run with Python and a host GCC on PATH. This tests software control flow only;
MIPI timing and real VDMA status still require board validation.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "software/mipi_hdmi/mipi_hdmi/src/main.c").read_text()
sensor_source = (root / "software/mipi_hdmi/mipi_hdmi/src/ov5640.c").read_text()
bayer_source = (root / "repo/ip/AXI_BayerToRGB/hdl/AXI_BayerToRGB.vhd").read_text()

# RAW must stay RAW(DPC) until the matching PL demosaic.  The active sensor
# flip/binning configuration makes the phase observed at the PL input RGGB.
# Enabling the sensor CIP/AWB path here produces a double/intermixed pipeline.
assert "{0x4300, 0x00}" in sensor_source
assert "{0x501f, 0x03}" in sensor_source
assert "{0x5000, 0x06}" in sensor_source
assert "sensor_write_array(IicInstance,cfg_advanced_awb)" not in sensor_source
assert "phase observed by the PL RGGB" in bayer_source
# AXI_GammaCorrection accepts the selector through writes, but its AXI-Lite
# read data is permanently zero; a readback comparison must not block startup.
assert "Xil_Out32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR, CAMERA_GAMMA_FACTOR_1_8);" in source
assert "Xil_In32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR)" not in source
functions = source[source.index("#define CAMERA_START_ATTEMPTS"):source.index("int main()")]
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define XST_SUCCESS 0
#define XST_FAILURE 1
#define XPAR_AXIVDMA_1_BASEADDR 0x1000
#define XPAR_AXIVDMA_1_DEVICE_ID 1
#define XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR 0x2000
#define XPAR_XIICPS_0_DEVICE_ID 0
#define XAXIVDMA_RX_OFFSET 0x30
#define XAXIVDMA_SR_OFFSET 4
#define XAXIVDMA_IXR_FRMCNT_MASK 0x1000
#define XAXIVDMA_SR_HALTED_MASK 1
#define XAXIVDMA_SR_ERR_ALL_MASK 0xff0
#define HORSIZE 3840
#define VERSIZE 720
#define DEMO_STRIDE 5760
static int Gpio, ps_i2c0;
static struct { unsigned char *framePtr[1]; int curFrame;
    struct { int width, height; } vMode; } dispCtrl;
static int attempts, stage, fail_attempts, reset_fail, config_fail, start_fail;
static int dma_fail, i2c_fail, fault, resets;
static u32 packets, crc;
static int elapsed;
#define xil_printf(...) ((void)0)
static void Xil_Out32(u32 addr, u32 value) {
    assert(addr == 0x1034 && value == 0x1000);
    elapsed = 0;
}
static u32 Xil_In32(u32 addr) {
    if (addr == 0x2004) return packets;
    if (addr == 0x2008) return crc;
    assert(addr == 0x1034);
    if (fault == 3) return 0;
    if (fault == 4) return 0x1001;
    if (fault == 5) return 0x1020;
    return elapsed ? 0x1000 : 0;
}
static void usleep(unsigned int delay) {
    if (delay == 2000000) {
        elapsed = 1;
        if (fault != 1 && attempts > fail_attempts) packets += 100;
        if (fault == 2) ++crc;
    }
}
static int vdma_write_reset(int id) {
    assert(id == 1); ++resets; stage = 0;
    return reset_fail;
}
static void DemoPrintTest(unsigned char *p, int w, int h, int s, int pattern) {
    assert(stage == 0); /* Never redraw while DMA is writing. */
}
static void XGpioPs_WritePin(int *gpio, int pin, int value) {
    assert(pin == 54);
}
static int i2c_init(int *iic, int id, int rate) { return i2c_fail; }
static int sensor_configure(int *iic) {
    assert(stage == 0); stage = 1; ++attempts; return config_fail;
}
static int vdma_write_init(int id, int h, int v, int stride, unsigned int address) {
    assert(stage == 1); stage = 2; return dma_fail;
}
static int sensor_start(int *iic) {
    assert(stage == 2); stage = 3; return start_fail;
}
static void clear(void) {
    attempts = stage = fail_attempts = reset_fail = config_fail = start_fail = 0;
    dma_fail = i2c_fail = fault = resets = elapsed = 0;
    packets = crc = 0;
}
'''
tests = r'''
int main(void) {
    clear(); assert(CameraStart() == 0 && attempts == 1);
    clear(); fail_attempts = 1; assert(CameraStart() == 0 && attempts == 2);
    clear(); fail_attempts = 3; assert(CameraStart() == 1 && attempts == 3 && resets == 4);
    clear(); reset_fail = 1; assert(CameraStart() == 1 && attempts == 0 && resets == 1);
    clear(); config_fail = 1; assert(CameraStart() == 1 && attempts == 3);
    clear(); dma_fail = 1; assert(CameraStart() == 1 && attempts == 3);
    clear(); start_fail = 1; assert(CameraStart() == 1 && attempts == 3);
    clear(); i2c_fail = 1; assert(CameraStart() == 1 && attempts == 0 && resets == 4);
    for (int i = 1; i <= 5; ++i) {
        clear(); attempts = 1; fault = i; assert(CameraCheck(0) == 1);
    }
    clear(); attempts = 1; packets = UINT32_MAX - 50;
    assert(CameraCheck(0) == 0); /* Counter wrap is still progress. */
    assert(CameraCheck(0) == 0); /* Requires fresh completion each window. */
    puts("PASS: 15 camera startup/health fault-injection checks");
    return 0;
}
'''
build = root / "build"
build.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="camera_test_", dir=build) as tmp:
    cfile = Path(tmp) / "test.c"
    exe = Path(tmp) / "test.exe"
    cfile.write_text(prefix + functions + tests)
    subprocess.run(["gcc", "-std=c99", "-Werror=implicit-function-declaration",
                    "-Wno-pointer-to-int-cast", str(cfile), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
