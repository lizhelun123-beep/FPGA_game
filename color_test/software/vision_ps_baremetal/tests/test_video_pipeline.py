"""Offline fault injection of production C functions (no board access).

Requires host GCC/Python and the existing Vitis BSP register header. Temporary
translation units/executables use the OS temporary directory and are removed
on completion; the generated Vitis build directory may be read-only here.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import time

script_started = time.perf_counter()
print('[HOST-TEST] START Python initialization', flush=True)


def stage_start(name):
    print(f'[HOST-TEST] START {name}', flush=True)
    return time.perf_counter()


def stage_done(name, started, detail=''):
    suffix = f' {detail}' if detail else ''
    print(f'[HOST-TEST] DONE  {name} elapsed={time.perf_counter()-started:.3f}s{suffix}',
          flush=True)


def stop_after(name):
    if os.environ.get('HOST_TEST_STOP_AFTER') == name:
        print(f'[HOST-TEST] STOP  requested after {name}', flush=True)
        raise SystemExit(0)


def run_command(name, command, timeout):
    started = stage_start(name)
    print(f'[HOST-TEST] CMD   {subprocess.list2cmdline(command)}', flush=True)
    try:
        completed = subprocess.run(command, check=False, timeout=timeout,
                                   text=True, capture_output=True)
    except subprocess.TimeoutExpired as error:
        stdout = (error.stdout or '')[-2000:]
        stderr = (error.stderr or '')[-2000:]
        print(f'[HOST-TEST] TIMEOUT {name} timeout={timeout}s', flush=True)
        if stdout:
            print(f'[HOST-TEST] stdout tail:\n{stdout}', flush=True)
        if stderr:
            print(f'[HOST-TEST] stderr tail:\n{stderr}', flush=True)
        raise
    stage_done(name, started, f'returncode={completed.returncode}')
    if completed.stdout:
        print(f'[HOST-TEST] stdout tail:\n{completed.stdout[-4000:]}', flush=True)
    if completed.stderr:
        print(f'[HOST-TEST] stderr tail:\n{completed.stderr[-4000:]}', flush=True)
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command,
                                            completed.stdout, completed.stderr)
    return completed


stage_done('Python initialization', script_started)

started = stage_start('locate and read sources')
app = Path(__file__).resolve().parents[1]
project = app.parents[1]
src = app / 'src'
main = (src / 'main.c').read_text()
display = (src / 'display_ctrl/display_ctrl.c').read_text()
dma = (src / 'vdma.c').read_text()
hw = (project / 'build/vision_ps_baremetal/vision_ps_platform/ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/include/xaxivdma_hw.h').read_text()
stage_done('locate and read sources', started,
           f'bytes={len(main)+len(display)+len(dma)+len(hw)}')
stop_after('sources')

started = stage_start('extract VDMA register macros')
macros = '\n'.join(re.findall(r'^#define\s+XAXIVDMA_\w+\s+0x[0-9A-Fa-f]+[^\n]*|^#define\s+XAXIVDMA_\w+\s+[0-9]+[^\n]*', hw, re.M))

macros = '\n'.join(line.split('/*')[0] for line in macros.splitlines())
stage_done('extract VDMA register macros', started,
           f'bytes={len(macros)} lines={len(macros.splitlines())}')
stop_after('macros')

def function(text, name):
    started = stage_start(f'extract C function {name}')
    match = re.search(r'^(?:static )?(?:int|void) ' + name + r'\([^;]*?\)\s*\{', text, re.M)
    assert match, name
    start = match.start()
    pos = match.end()
    depth = 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    result = text[start:pos] + '\n'
    stage_done(f'extract C function {name}', started, f'bytes={len(result)}')
    return result

prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "vision_ps.h"
#include "vision_overlay.h"
#include "vision_perf.h"
/* This fixture verifies the compatible default display path. The actual
 * bounded transport is exercised by test_scene_stream.c through test_game. */
#define ScenePublish(objects, count, valid, capture_ms) ((void)0)
#define SceneUartPoll() ((void)0)
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
#define VDMA_CAPTURE_FRAME_COUNT 3U
#define CSI_CONTROL_OFFSET 0x00U
#define CSI_FIFO_OVERFLOW_MASK 0x80000000U
typedef struct { UINTPTR BaseAddr; } XAxiVdma;
typedef struct { XAxiVdma *vdma; u32 curFrame; int state; } DisplayCtrl;
static XAxiVdma vdma = {0x1000};
static DisplayCtrl dispCtrl = {&vdma, 1, DISPLAY_RUNNING};
static u8 buffers[3][VISION_FRAME_BYTES] __attribute__((aligned(64)));
static u8 *pFrames[3] = {buffers[0], buffers[1], buffers[2]};
static u8 captureAux[2][VISION_FRAME_BYTES] __attribute__((aligned(64)));
static UINTPTR captureFrames[3] = {
    (UINTPTR)buffers[0], (UINTPTR)captureAux[0], (UINTPTR)captureAux[1]
};
static u32 regs[0x4000/4], packets, crc, clock_ms;
static u32 camera_packets_before, camera_crc_before;
static int camera_window;
static const char *vision_failure = "startup";
static unsigned int vision_frames_presented, vision_last_count, vision_last_processing_ms;
static unsigned int vision_last_capture_ms, vision_last_color_ms;
static RayGameLevel ray_level;
static volatile unsigned int vision_active_zero_ray_frames;
static VisionDetection scripted_detections[VISION_MAX_DETECTIONS];
static int scripted_count;
static int park_fail, park_stall, late_switch, detect_fail, flushes, overlays;
static int last_overlay_segments;
static unsigned last_detected_mask, last_hit_mask;
static int advance_on_invalidate;
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
static void Xil_DCacheInvalidateRange(INTPTR p, unsigned n) {
    (void)p; (void)n;
    if (advance_on_invalidate)
        regs[(XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_PARKPTR_OFFSET)/4] = 0;
}
static void VideoRegisters(const char *s) { (void)s; ++logs; }
int vision_detect_bgr888(const uint8_t *p, uint32_t w, uint32_t h, uint32_t s,
                         VisionDetection *d, int n) {
    (void)p; (void)w; (void)h; (void)s;
    if (detect_fail) return -1;
    assert(scripted_count <= n);
    memcpy(d, scripted_detections,
           (size_t)scripted_count*sizeof(scripted_detections[0]));
    return scripted_count;
}
void vision_overlay(uint8_t *p, unsigned w, unsigned h, unsigned s,
                    const RaySegment *segments, int n,
                    unsigned detected_mask, unsigned hit_mask, unsigned ms) {
    (void)w; (void)h; (void)s; (void)segments; (void)n; (void)ms;
    ++overlays; last_overlay_segments = n;
    last_detected_mask = detected_mask; last_hit_mask = hit_mask;
    p[0] = 255; /* A visible status bar, even with zero detections. */
}
const char *vision_type_name(VisionType t) { (void)t; return "test"; }
'''
started = stage_start('generate HOST source fragments')
body = ''.join([
    function(dma, 'vdma_capture_index'),
    function(dma, 'vdma_capture_current'),
    function(dma, 'vdma_capture_ready'),
    function(display, 'DisplayChangeFrame'),
    *(function(main, n) for n in ['CameraObserve', 'VideoLayoutMatches', 'PresentFrame', 'CaptureHasPixels',
                                  'DiagnosticHold', 'VisionLevelLog', 'VisionRunOnce', 'CameraCheck']),
])
stage_done('generate HOST source fragments', started, f'body_bytes={len(body)}')
stop_after('generation')
tests = r'''
static void clear(void) {
    memset(regs, 0, sizeof(regs)); memset(buffers, 0, sizeof(buffers));
    memset(captureAux, 0, sizeof(captureAux));
    memset(buffers[1], 0x55, sizeof(buffers[1]));
    dispCtrl.curFrame = 1; dispCtrl.state = DISPLAY_RUNNING;
    regs[0x1028/4] = 1 << 16;
    regs[CAMERA_S2MM_STATUS/4] = XAXIVDMA_IXR_FRMCNT_MASK;
    regs[(XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_PARKPTR_OFFSET)/4] =
        1U << XAXIVDMA_WRTSTR_SHIFT;
    packets = crc = clock_ms = 0; camera_window = 0;
    park_fail = park_stall = late_switch = detect_fail = flushes = overlays = 0;
    last_overlay_segments = scripted_count = 0;
    last_detected_mask = last_hit_mask = 0U;
    memset(scripted_detections, 0, sizeof(scripted_detections));
    ray_game_level_reset(&ray_level); vision_active_zero_ray_frames = 0;
    advance_on_invalidate = 0;
    holding = hold_ticks = logs = reset_count = restart_count = 0;
    vision_frames_presented = 0;
}
static void unchanged(void) {
    unsigned i;
    assert(dispCtrl.curFrame == 1 && vision_frames_presented == 0);
    for (i = 0; i < sizeof(buffers[1]); ++i) assert(buffers[1][i] == 0x55);
}
int main(void) {
    unsigned capture_index = 99;
    setbuf(stdout, NULL);
    clear(); CameraObserve();
    assert(!(regs[CAMERA_S2MM_STATUS/4] & XAXIVDMA_IXR_FRMCNT_MASK)); /* stale completion cleared */
    assert(CameraCheck(0, &capture_index) == 1 && clock_ms == 2000); /* no fresh frame */
    clear(); CameraObserve(); packets = 100; crc = 1;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK;
    assert(CameraCheck(0, &capture_index) == 1);
    clear(); crc = UINT32_MAX; CameraObserve(); packets = 100; crc = 0;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK;
    assert(CameraCheck(0, &capture_index) == 1); /* CRC wrap is an increment */
    for (u32 bit = 0x10; bit <= 0x800; bit <<= 1) {
        clear(); CameraObserve(); packets = 100; regs[CAMERA_S2MM_STATUS/4] |= bit;
        assert(CameraCheck(0, &capture_index) == 1);
    }
    clear(); CameraObserve(); packets = 1;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_SR_HALTED_MASK | XAXIVDMA_IXR_FRMCNT_MASK;
    assert(CameraCheck(0, &capture_index) == 1); /* continuous S2MM must not halt */
    clear(); CameraObserve(); packets = 1; regs[CAMERA_S2MM_STATUS/4] = 1;
    assert(CameraCheck(0, &capture_index) == 1 && clock_ms == 2000); /* no completion */
    clear(); CameraObserve(); packets = 1;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK;
    regs[0x3000/4] = CSI_FIFO_OVERFLOW_MASK;
    assert(CameraCheck(0, &capture_index) == 1); /* sticky CSI overflow */
    clear(); packets = UINT32_MAX - 10; CameraObserve(); packets = 5;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK;
    assert(CameraCheck(0, &capture_index) == 0 && capture_index == 0);
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK;
    assert(CameraCheck(0, &capture_index) == 1); /* one use */
    clear(); CameraObserve(); packets = 10; clock_ms = 200;
    regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_IXR_FRMCNT_MASK; /* completion before poll */
    assert(CameraCheck(0, &capture_index) == 0 && capture_index == 0);
    puts("checkpoint: camera health");
    clear(); assert(!CaptureHasPixels(buffers[0]));
    buffers[0][HORSIZE] = 255; assert(!CaptureHasPixels(buffers[0])); /* padding */
    assert(VisionRunOnce(0) == VISION_RETRY_FRAME); unchanged(); assert(!flushes && !overlays);
    clear(); buffers[0][(VERSIZE-1)*DEMO_STRIDE + HORSIZE-1] = 1;
    assert(CaptureHasPixels(buffers[0])); /* dim, single active byte */
    assert(VisionRunOnce(0) == 0 && dispCtrl.curFrame == 2 && overlays == 1);
    assert(vision_frames_presented == 1 && buffers[2][0] == 255);
    memset(buffers[0], 0, sizeof(buffers[0]));
    assert(VisionRunOnce(0) == VISION_RETRY_FRAME);
    assert(dispCtrl.curFrame == 2 && vision_frames_presented == 1 && buffers[2][0] == 255);
    /* A later valid dark frame can still replace the retained frame. */
    buffers[0][0] = 1;
    assert(VisionRunOnce(0) == 0 && dispCtrl.curFrame == 1 && vision_frames_presented == 2);
    clear(); buffers[0][0] = 1; detect_fail = 1;
    assert(VisionRunOnce(0) == 0 && overlays == 1 && last_overlay_segments == 0);
    clear(); buffers[0][0] = 1;
    scripted_count = 2;
    scripted_detections[0].type = VISION_SOURCE;
    scripted_detections[0].center_x = 100;
    scripted_detections[0].center_y = 100;
    scripted_detections[0].geometry_center_x = 100.0f;
    scripted_detections[0].geometry_center_y = 100.0f;
    scripted_detections[0].bbox_w = 50;
    scripted_detections[0].bbox_h = 20;
    scripted_detections[0].axis_x = 1.0f;
    scripted_detections[0].major_length = 50.0f;
    scripted_detections[0].minor_width = 20.0f;
    scripted_detections[0].source_tip_x = 100;
    scripted_detections[0].source_tip_y = 100;
    scripted_detections[0].source_direction_x = 1.0f;
    scripted_detections[0].direction_valid = 1;
    scripted_detections[1].type = VISION_WALL;
    scripted_detections[1].center_x = 600;
    scripted_detections[1].center_y = 500;
    scripted_detections[1].geometry_center_x = 600.0f;
    scripted_detections[1].geometry_center_y = 500.0f;
    scripted_detections[1].bbox_w = 20;
    scripted_detections[1].bbox_h = 100;
    scripted_detections[1].axis_y = 1.0f;
    scripted_detections[1].major_length = 100.0f;
    scripted_detections[1].minor_width = 20.0f;
    assert(VisionRunOnce(0) == 0); /* First valid SOURCE frame draws. */
    assert(ray_level.state == RAY_LEVEL_ACTIVE && ray_level.source_locked);
    assert(ray_level.committed_ray_valid && last_overlay_segments > 0);
    assert(last_detected_mask == ((1U << RAY_OBJECT_SOURCE) |
                                  (1U << RAY_OBJECT_WALL)));
    assert(last_hit_mask == 0U);
    detect_fail = 1;
    assert(VisionRunOnce(0) == 0 && ray_level.state == RAY_LEVEL_ACTIVE);
    assert(last_overlay_segments > 0 && vision_active_zero_ray_frames == 0);
    detect_fail = 0;
    scripted_detections[0].source_tip_x = 900;
    scripted_detections[0].source_tip_y = 650;
    scripted_detections[0].source_direction_x = -1.0f;
    assert(VisionRunOnce(0) == 0 && ray_level.state == RAY_LEVEL_ACTIVE);
    assert(ray_level.source_clear_count == 0 && last_overlay_segments > 0);
    assert(ray_level.locked_source.source_tip.x == 900.0f);
    assert(last_overlay_segments > 0 && vision_active_zero_ray_frames == 0);
    scripted_count = 1; /* SOURCE alone remains a complete drawable scene. */
    assert(VisionRunOnce(0) == 0 && last_overlay_segments > 0);
    assert(vision_active_zero_ray_frames == 0);
    clear(); buffers[0][0] = 1;
    regs[(XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_PARKPTR_OFFSET)/4] =
        2U << XAXIVDMA_WRTSTR_SHIFT;
    assert(VisionRunOnce(0) == VISION_RETRY_FRAME); unchanged();
    clear(); buffers[0][0] = 1; advance_on_invalidate = 1;
    assert(VisionRunOnce(0) == VISION_RETRY_FRAME); unchanged();
    clear(); buffers[0][0] = 1; park_stall = 1;
    assert(VisionRunOnce(0) == 1); unchanged(); assert(requested == 1 && clock_ms == 250);
    puts("checkpoint: frame ownership");
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
    puts("checkpoint: diagnostic hold");
    clear();
    for (u32 capture = 0; capture < 2; ++capture) {
        u32 addr = capture ? 0x20a0 : 0x1050;
        regs[addr/4] = 720; regs[(addr+4)/4] = 3840; regs[(addr+8)/4] = 5760;
        for (u32 i = 0; i < 3; ++i)
            regs[(addr+12+4*i)/4] = (u32)(capture ? captureFrames[i] : (UINTPTR)pFrames[i]);
        assert(VideoLayoutMatches(capture) == 0);
        regs[(addr+8)/4] = 3840; assert(VideoLayoutMatches(capture) == 1);
        regs[(addr+8)/4] = 5760; regs[(addr+16)/4] += 64;
        assert(VideoLayoutMatches(capture) == 1);
    }
    clear(); capture_index = 99; assert(vdma_capture_ready(&capture_index) == 0);
    assert(capture_index == 0);
    assert(!(regs[CAMERA_S2MM_STATUS/4] & XAXIVDMA_IXR_FRMCNT_MASK));
    clear(); regs[CAMERA_S2MM_STATUS/4] |= XAXIVDMA_SR_HALTED_MASK;
    assert(vdma_capture_ready(&capture_index) == 1);
    clear(); regs[(XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_PARKPTR_OFFSET)/4] =
        3U << XAXIVDMA_WRTSTR_SHIFT;
    assert(vdma_capture_ready(&capture_index) == 1);
    puts("PASS: continuous capture ring/overflow/ownership/retained-frame fault injection");
    return 0;
}
'''
started = stage_start('static startup assertions')
# Ensure startup consumes CameraStart's validated frame before the next poll.
main_loop = function(main, 'main')
assert 'return ' not in main_loop
assert main_loop.index('VisionRunOnce(capture_index)') < main_loop.index('CameraCheck(0, &capture_index)')
assert main.index('CameraObserve();', main.index('static int CameraStart')) < main.index('status = vdma_write_init', main.index('static int CameraStart'))
assert function(main, 'CameraObserve').index('camera_packets_before') < function(main, 'CameraObserve').index('Xil_Out32(CAMERA_S2MM_STATUS')
assert main_loop.count('Status = CameraStart(&capture_index);') == 2
assert 'CAPTURE_RECOVERY_EXHAUSTED' in main_loop
assert 'Xil_In32(base + 0xA0' not in dma
assert 'EnableCircularBuf = 1' in dma
assert 'EnableFrameCounter = 0' in dma
stage_done('static startup assertions', started)
stop_after('assertions')

started = stage_start('create temporary HOST workspace')
with tempfile.TemporaryDirectory(prefix='vision_fault_') as tmp:
    stage_done('create temporary HOST workspace', started, f'path={tmp}')
    c = Path(tmp) / 'fault.c'
    exe = Path(tmp) / 'fault.exe'
    started = stage_start('write HOST translation unit')
    generated = (prefix.replace('#include "vision_ps.h"',
                                macros + '\n#include "vision_ps.h"') +
                 body + tests)
    c.write_text(generated)
    stage_done('write HOST translation unit', started,
               f'bytes={c.stat().st_size} lines={generated.count(chr(10))+1}')
    stop_after('write')
    run_command('GCC compile and link',
                ['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-Wno-unused-value', '-I'+str(src), str(c),
                 str(src / 'ray_game.c'), '-lm', '-o', str(exe)], 30)
    stop_after('compile')
    run_command('synthetic HOST executable', [str(exe)], 20)

stage_done('complete HOST pipeline test', script_started)
