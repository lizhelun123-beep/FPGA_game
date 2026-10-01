"""Offline fault injection of production C functions (no board access).

Requires host GCC/Python and the existing Vitis BSP register header. Temporary
translation units/executables live under build and are removed on completion.
"""
from pathlib import Path
import re
import subprocess
import tempfile

app = Path(__file__).resolve().parents[1]
project = app.parents[1]
src = app / 'src'
main = (src / 'main.c').read_text()
display = (src / 'display_ctrl/display_ctrl.c').read_text()
dma = (src / 'vdma.c').read_text()
hw = (project / 'build/vision_ps_baremetal/vision_ps_platform/ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/include/xaxivdma_hw.h').read_text()
macros = '\n'.join(re.findall(r'^#define\s+XAXIVDMA_\w+\s+0x[0-9A-Fa-f]+[^\n]*|^#define\s+XAXIVDMA_\w+\s+[0-9]+[^\n]*', hw, re.M))

macros = '\n'.join(line.split('/*')[0] for line in macros.splitlines())

def function(text, name):
    match = re.search(r'^(?:static )?(?:int|void) ' + name + r'\([^;]*?\)\s*\{', text, re.M)
    assert match, name
    start = match.start()
    pos = match.end()
    depth = 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[start:pos] + '\n'

prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "vision_ps.h"
#include "vision_overlay.h"
typedef uint32_t u32;
typedef uint8_t u8;
typedef uintptr_t UINTPTR;
typedef uintptr_t INTPTR;
#define XST_SUCCESS 0
#define XST_FAILURE 1
#define DISPLAY_NUM_FRAMES 3
#define DISPLAY_RUNNING 1
#define DISPLAY_STOPPED 0
#define XAXIVDMA_READ 1
#define XPAR_AXIVDMA_0_BASEADDR 0x1000
#define XPAR_AXIVDMA_1_BASEADDR 0x2000
#define XPAR_AXIVDMA_1_DEVICE_ID 1
#define XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR 0x3000
#define CAMERA_S2MM_STATUS (0x2000 + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET)
#define HORSIZE 3840
#define VERSIZE 720
#define DEMO_STRIDE 5760
#define VISION_RETRY_FRAME 2
#define VISION_FRAME_BYTES (DEMO_STRIDE * VERSIZE)
typedef struct { UINTPTR BaseAddr; } XAxiVdma;
typedef struct { XAxiVdma *vdma; u32 curFrame; int state; } DisplayCtrl;
static XAxiVdma vdma = {0x1000};
static DisplayCtrl dispCtrl = {&vdma, 1, DISPLAY_RUNNING};
static u8 buffers[3][VISION_FRAME_BYTES] __attribute__((aligned(64)));
static u8 *pFrames[3] = {buffers[0], buffers[1], buffers[2]};
static u32 regs[0x4000/4], packets, crc, clock_ms, capture_vsize = 720;
static u32 camera_packets_before, camera_crc_before;
static int camera_window;
static const char *vision_failure = "startup";
static unsigned int vision_frames_presented, vision_last_count, vision_last_processing_ms;
static int park_fail, park_stall, late_switch, detect_fail, flushes, overlays;
static int holding, hold_ticks, logs, reset_count, restart_count;
static jmp_buf held;
static u32 requested;
static unsigned int NowMs(void) { return clock_ms; }
static void xil_printf(const char *format, ...) { (void)format; ++logs; }
static u32 Xil_In32(UINTPTR addr) {
    if (addr == 0x3004) return packets;
    if (addr == 0x3008) return crc;
    assert(addr < sizeof(regs));
    return regs[addr/4];
}
static void Xil_Out32(UINTPTR addr, u32 value) {
    assert(addr < sizeof(regs));
    if (addr == CAMERA_S2MM_STATUS) regs[addr/4] &= ~value;
    else regs[addr/4] = value;
}
static void usleep(unsigned int delay) {
    clock_ms += delay / 1000;
    if (holding && delay == 1000000 && ++hold_ticks == 2) longjmp(held, 1);
}
static int XAxiVdma_StartParking(XAxiVdma *v, u32 frame, int direction) {
    (void)v; (void)direction;
    requested = frame;
    if (park_fail) return 1;
    /* A timeout may race a switch just before cancellation. */
    if (late_switch && frame == 1) regs[0x1028/4] = 2 << 16;
    if (!park_stall) regs[0x1028/4] = frame << 16;
    return 0;
}
static void XAxiVdma_Reset(XAxiVdma *v, int dir) {
    (void)v; (void)dir; ++reset_count; regs[0x1004/4] = 1;
}
static int XAxiVdma_ResetNotDone(XAxiVdma *v, int dir) { (void)v; (void)dir; return 0; }
static int DisplayStart(DisplayCtrl *d) {
    ++restart_count; d->state = DISPLAY_RUNNING; regs[0x1004/4] = 0; return 0;
}
static int vdma_write_reset(short id) { (void)id; return 0; }
static void Xil_DCacheFlushRange(INTPTR p, unsigned n) { (void)p; (void)n; ++flushes; }
static void Xil_DCacheInvalidateRange(INTPTR p, unsigned n) { (void)p; (void)n; }
static void VideoRegisters(const char *s) { (void)s; ++logs; }
int vision_detect_bgr888(const uint8_t *p, uint32_t w, uint32_t h, uint32_t s,
                         VisionDetection *d, int n) {
    (void)p; (void)w; (void)h; (void)s; (void)d; (void)n;
    return detect_fail ? -1 : 0;
}
void vision_overlay(uint8_t *p, unsigned w, unsigned h, unsigned s,
                    const VisionDetection *d, int n, unsigned ms) {
    (void)w; (void)h; (void)s; (void)d; (void)n; (void)ms;
    ++overlays; p[0] = 255; /* A visible status bar, even with zero detections. */
}
const char *vision_type_name(VisionType t) { (void)t; return "test"; }
'''
body = ''.join([
    function(dma, 'vdma_capture_next'),
    function(display, 'DisplayChangeFrame'),
    *(function(main, n) for n in ['CameraObserve', 'VideoLayoutMatches', 'PresentFrame', 'CaptureHasPixels',
                                  'DiagnosticHold', 'VisionRunOnce', 'CameraCheck']),
])
tests = r'''
static void clear(void) {
    memset(regs, 0, sizeof(regs)); memset(buffers, 0, sizeof(buffers));
    memset(buffers[1], 0x55, sizeof(buffers[1]));
    dispCtrl.curFrame = 1; dispCtrl.state = DISPLAY_RUNNING;
    regs[0x1028/4] = 1 << 16;
    regs[CAMERA_S2MM_STATUS/4] = XAXIVDMA_IXR_FRMCNT_MASK | XAXIVDMA_SR_HALTED_MASK;
    packets = crc = clock_ms = 0; camera_window = 0; capture_vsize = 720;
    park_fail = park_stall = late_switch = detect_fail = flushes = overlays = 0;
    holding = hold_ticks = logs = reset_count = restart_count = 0;
    vision_frames_presented = 0;
}
static void unchanged(void) {
    unsigned i;
    assert(dispCtrl.curFrame == 1 && vision_frames_presented == 0);
    for (i = 0; i < sizeof(buffers[1]); ++i) assert(buffers[1][i] == 0x55);
}
int main(void) {
    clear(); CameraObserve(); assert(CameraCheck(0) == 1); /* no packets */
    clear(); CameraObserve(); packets = 100; crc = 1; assert(CameraCheck(0) == 1);
    clear(); crc = UINT32_MAX; CameraObserve(); packets = 100; crc = 0;
    assert(CameraCheck(0) == 1); /* CRC wrap is an increment */
    for (u32 bit = 0x10; bit <= 0x800; bit <<= 1) {
        clear(); CameraObserve(); packets = 100; regs[CAMERA_S2MM_STATUS/4] |= bit;
        assert(CameraCheck(0) == 1);
    }
    clear(); CameraObserve(); packets = 1; regs[CAMERA_S2MM_STATUS/4] = 0x1000;
    assert(CameraCheck(0) == 1 && clock_ms == 2000); /* not halted */
    clear(); CameraObserve(); packets = 1; regs[CAMERA_S2MM_STATUS/4] = 1;
    assert(CameraCheck(0) == 1); /* no completion */
    clear(); packets = UINT32_MAX - 10; CameraObserve(); packets = 5;
    assert(CameraCheck(0) == 0); assert(CameraCheck(0) == 1); /* one use */
    clear(); CameraObserve(); packets = 10; clock_ms = 200; /* completion before poll */
    assert(CameraCheck(0) == 0);
    clear(); assert(!CaptureHasPixels(buffers[0]));
    buffers[0][HORSIZE] = 255; assert(!CaptureHasPixels(buffers[0])); /* padding */
    assert(VisionRunOnce() == VISION_RETRY_FRAME); unchanged(); assert(!flushes && !overlays);
    clear(); buffers[0][(VERSIZE-1)*DEMO_STRIDE + HORSIZE-1] = 1;
    assert(CaptureHasPixels(buffers[0])); /* dim, single active byte */
    assert(VisionRunOnce() == 0 && dispCtrl.curFrame == 2 && overlays == 1);
    assert(vision_frames_presented == 1 && buffers[2][0] == 255);
    memset(buffers[0], 0, sizeof(buffers[0]));
    assert(VisionRunOnce() == VISION_RETRY_FRAME);
    assert(dispCtrl.curFrame == 2 && vision_frames_presented == 1 && buffers[2][0] == 255);
    /* A later valid dark frame can still replace the retained frame. */
    buffers[0][0] = 1;
    regs[CAMERA_S2MM_STATUS/4] = XAXIVDMA_IXR_FRMCNT_MASK | XAXIVDMA_SR_HALTED_MASK;
    assert(VisionRunOnce() == 0 && dispCtrl.curFrame == 1 && vision_frames_presented == 2);
    clear(); buffers[0][0] = 1; detect_fail = 1;
    assert(VisionRunOnce() == 1); unchanged(); assert(!flushes && !overlays);
    clear(); buffers[0][0] = 1; regs[CAMERA_S2MM_STATUS/4] |= 0x20;
    assert(VisionRunOnce() == 1); unchanged();
    clear(); buffers[0][0] = 1; park_stall = 1;
    assert(VisionRunOnce() == 1); unchanged(); assert(requested == 1 && clock_ms == 250);
    clear(); park_fail = 1; assert(PresentFrame(2) == 1); unchanged();
    clear(); regs[0x1004/4] = 0x20; assert(PresentFrame(2) == 1); unchanged();
    clear(); assert(PresentFrame(0) == 1 && PresentFrame(3) == 1 && PresentFrame(1) == 1);
    clear(); park_stall = late_switch = 1; assert(PresentFrame(2) == 1); unchanged();
    assert((regs[0x1028/4] >> 16) == 2); /* delayed hardware change */
    park_stall = late_switch = 0; holding = 1;
    if (!setjmp(held)) DiagnosticHold("switch timeout");
    unchanged(); assert((regs[0x1028/4] >> 16) == 1 && logs >= 4);
    clear(); regs[0x1004/4] = 0x20; holding = 1;
    if (!setjmp(held)) DiagnosticHold("read error");
    unchanged(); assert(reset_count == 1 && restart_count == 1 && hold_ticks == 2);
    clear();
    for (u32 capture = 0; capture < 2; ++capture) {
        u32 addr = capture ? 0x20a0 : 0x1050;
        regs[addr/4] = 720; regs[(addr+4)/4] = 3840; regs[(addr+8)/4] = 5760;
        for (u32 i = 0; i < 3; ++i) regs[(addr+12+4*i)/4] = (u32)(UINTPTR)pFrames[capture ? 0 : i];
        assert(VideoLayoutMatches(capture) == 0);
        regs[(addr+8)/4] = 3840; assert(VideoLayoutMatches(capture) == 1);
        regs[(addr+8)/4] = 5760; regs[(addr+16)/4] += 64;
        assert(VideoLayoutMatches(capture) == 1);
    }
    clear(); assert(vdma_capture_next() == 0);
    assert(regs[(0x2000 + XAXIVDMA_S2MM_ADDR_OFFSET + XAXIVDMA_VSIZE_OFFSET)/4] == 720);
    assert(!(regs[CAMERA_S2MM_STATUS/4] & XAXIVDMA_IXR_FRMCNT_MASK));
    clear(); capture_vsize = 0; assert(vdma_capture_next() == 1);
    puts("PASS: production capture/black-frame/ownership/timeout/retained-frame fault injection");
    return 0;
}
'''
# Ensure startup consumes CameraStart's validated frame before the next poll.
main_loop = function(main, 'main')
assert 'return ' not in main_loop
assert main_loop.index('VisionRunOnce()') < main_loop.index('CameraCheck(0)')
assert main.index('CameraObserve();', main.index('static int CameraStart')) < main.index('status = vdma_write_init', main.index('static int CameraStart'))
assert 'Xil_In32(base + 0xA0' not in dma
with tempfile.TemporaryDirectory(prefix='vision_fault_', dir=project / 'build') as tmp:
    c = Path(tmp) / 'fault.c'
    exe = Path(tmp) / 'fault.exe'
    c.write_text(prefix.replace('#include "vision_ps.h"', macros + '\n#include "vision_ps.h"') + body + tests)
    subprocess.run(['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-value', '-I'+str(src), str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
