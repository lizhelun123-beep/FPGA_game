/******************************************************************************
 *
 * Copyright (C) 2009 - 2014 Xilinx, Inc.  All rights reserved.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * Use of the Software is limited solely to applications:
 * (a) running on a Xilinx device, or
 * (b) that interact with a Xilinx device through a bus or interconnect.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * XILINX  BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF
 * OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 * Except as contained in this notice, the name of the Xilinx shall not be used
 * in advertising or otherwise to promote the sale, use or other dealings in
 * this Software without prior written authorization from Xilinx.
 *
 ******************************************************************************/

/*
 * helloworld.c: simple test application
 *
 * This application configures UART 16550 to baud rate 9600.
 * PS7 UART (Zynq) is not initialized by this application, since
 * bootrom/bsp configures it to baud rate 115200
 *
 * ------------------------------------------------
 * | UART TYPE   BAUD RATE                        |
 * ------------------------------------------------
 *   uartns550   9600
 *   uartlite    Configurable only in HW design
 *   ps7_uart    115200 (configured by bootrom/bsp)
 */

#include "display_demo.h"
#include "display_ctrl/display_ctrl.h"
#include "vision_ps_config.h"
#include <stdio.h>
#include <string.h>
#include "math.h"
#include <ctype.h>
#include <stdlib.h>
#include "xil_types.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xparameters.h"
#include "xiicps.h"
#include "vdma.h"
#include "i2c/PS_i2c.h"
#include "sleep.h"
#include "MIPI_CSI_2_RX.h"
#include "MIPI_D_PHY_RX.h"
#include "ov5640.h"
#include "xgpiops.h"
#include "xaxivdma_hw.h"
#include "green_target_detector.h"
#include "ray_game.h"
#include "vision_ps.h"
#include "vision_overlay.h"
#include "xtime_l.h"
#include "scene_protocol.h"
#include "vision_perf.h"
#include "xuartps_hw.h"
/* The stream owns UART during runtime. Keep main's verbose diagnostics in the
 * compatible default build; never splice them into an in-flight scene packet. */
#if VISION_SCENE_STREAM_ENABLE
#define xil_printf(...) do { if (0) xil_printf(__VA_ARGS__); } while (0)
#endif
/*
 * XPAR redefines
 */
#define DYNCLK_BASEADDR XPAR_AXI_DYNCLK_0_BASEADDR
#define VGA_VDMA_ID XPAR_AXIVDMA_0_DEVICE_ID
#define DISP_VTC_ID XPAR_VTC_0_DEVICE_ID

//#define P1080 1

#ifdef P1080
#define HORSIZE 1920*3
#define VERSIZE 1080
#else
#define HORSIZE 1280*3
#define VERSIZE 720
#endif

/* ------------------------------------------------------------ */
/*				Global Variables								*/
/* ------------------------------------------------------------ */

/*
 * Display Driver structs
 */
DisplayCtrl dispCtrl;
XAxiVdma vdma;
#if !VISION_FIXED_SCENE_DEMO
XIicPs ps_i2c0;

XGpioPs Gpio;
#endif

/*
 * Framebuffers for video data
 */
u8 frameBuf[DISPLAY_NUM_FRAMES][DEMO_MAX_FRAME] __attribute__ ((aligned(64)));
u8 *pFrames[DISPLAY_NUM_FRAMES]; //array of pointers to the frame buffers
#if !VISION_FIXED_SCENE_DEMO
u8 captureAux[VDMA_CAPTURE_FRAME_COUNT - 1U][DEMO_MAX_FRAME]
	__attribute__ ((aligned(64)));
UINTPTR captureFrames[VDMA_CAPTURE_FRAME_COUNT];
#endif

/* ------------------------------------------------------------ */
/*				Procedure Definitions							*/
/* ------------------------------------------------------------ */
#if !VISION_FIXED_SCENE_DEMO
int PsGpioSetup() ;
#endif

#define CAMERA_START_ATTEMPTS 3
#define CAMERA_S2MM_STATUS (XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET)
#define CAMERA_GAMMA_FACTOR_1_8 3U
#define VISION_FRAME_BYTES (DEMO_STRIDE * VERSIZE)
#define VISION_RETRY_FRAME 2
#define VISION_CALIBRATION_FRAMES 20U
#define CSI_CONTROL_OFFSET 0x00U
#define CSI_CONTROL_ENABLE 0x02U
#define CSI_CONTROL_RESET 0x01U
#define CSI_FIFO_OVERFLOW_MASK 0x80000000U
#if HORSIZE != 3840 || VERSIZE != 720 || DEMO_STRIDE != 5760
#error Vision display requires 1280x720 BGR888 with 5760-byte stride
#endif
/* Readable via debugger even when no UART cable is attached. */
volatile unsigned int vision_frames_presented;
#if !VISION_FIXED_SCENE_DEMO
volatile unsigned int vision_last_count;
volatile unsigned int vision_last_processing_ms;
volatile unsigned int vision_last_capture_ms;
volatile unsigned int vision_last_color_ms;
volatile unsigned int vision_minimal_pixels;
volatile int vision_minimal_center_x = -1;
volatile int vision_minimal_center_y = -1;
/* Stable JTAG export: sequence/address, BGR stats, five packed RGB samples,
 * green-mask geometry, and capture/color/total milliseconds. */
volatile unsigned int vision_probe_words[27];
/* frame count, TARGET sample count + 6*(min/max/mean), then BACKGROUND. */
volatile unsigned int vision_calibration_words[39];
#if !VISION_MINIMAL_TEST && !VISION_GREEN_TARGET_ONLY
static RayGameLevel ray_level;
volatile unsigned int vision_active_zero_ray_frames;
#endif

#if VISION_MINIMAL_TEST
typedef struct {
	u8 minimum[VISION_CALIBRATION_CHANNELS];
	u8 maximum[VISION_CALIBRATION_CHANNELS];
	u64 sum[VISION_CALIBRATION_CHANNELS];
	u32 samples;
} VisionCalibrationAccumulator;

static VisionCalibrationAccumulator calibration_target;
static VisionCalibrationAccumulator calibration_background;
static unsigned int calibration_frames;
#endif

static unsigned int NowMs(void)
{
	XTime ticks;
	XTime_GetTime(&ticks);
	return (unsigned int)(ticks / (COUNTS_PER_SECOND / 1000U));
}

#if VISION_PERF_ENABLE
uint64_t vision_perf_now(void)
{
	XTime ticks;
	XTime_GetTime(&ticks);
	/* Keep fractional tick conversion accurate for the matched PS clock. */
	return ticks / COUNTS_PER_SECOND * 1000000U +
		(ticks % COUNTS_PER_SECOND) * 1000000U / COUNTS_PER_SECOND;
}
static int SceneUartIdle(void)
{
	u32 sr = Xil_In32(STDOUT_BASEADDRESS + XUARTPS_SR_OFFSET);
	return (sr & (XUARTPS_SR_TXEMPTY | XUARTPS_SR_TACTIVE)) == XUARTPS_SR_TXEMPTY;
}
#endif

#if VISION_SCENE_STREAM_ENABLE
static SceneStream scene_stream;
static uint32_t scene_frame;
static int SceneUartPut(void *context, unsigned char byte)
{
	(void)context;
	if (Xil_In32(STDOUT_BASEADDRESS + XUARTPS_SR_OFFSET) & XUARTPS_SR_TXFULL)
		return 0;
	Xil_Out32(STDOUT_BASEADDRESS + XUARTPS_FIFO_OFFSET, byte);
	return 1;
}
static void SceneUartPoll(void)
{
#if VISION_PERF_ENABLE
	unsigned int budget = 64U;
	vision_perf_poll();
	vision_perf_wire_idle(SceneUartIdle());
	if (vision_perf_diag_active()) {
		vision_perf_diag_poll(&scene_stream, 0, SceneUartPut, NULL, 64U);
		return;
	}
	/* Reserve one bounded diagnostic row at a packet boundary so a constantly
	 * pending scene cannot starve all evidence. Share this poll's 64-byte budget;
	 * the scene may use the remaining FIFO bytes immediately, without waiting. */
	if (scene_stream.offset == scene_stream.length) {
		budget -= vision_perf_diag_poll(&scene_stream, SceneUartIdle(), SceneUartPut, NULL, budget);
		if (vision_perf_diag_active()) return;
	}
	scene_stream_poll(&scene_stream, NowMs(), SceneUartPut, NULL, budget);
#else
	scene_stream_poll(&scene_stream, NowMs(), SceneUartPut, NULL, 64U);
#endif
}
static void ScenePublish(const VisionDetection *objects, int count, int valid,
	uint32_t capture_ms)
{
	scene_stream_publish(&scene_stream, objects, count, valid, ++scene_frame, capture_ms);
	SceneUartPoll();
}
/* Service the FIFO during existing waits, without adding a UART busy wait. */
static void SceneStreamSleep(unsigned int microseconds)
{
	PERF_START(sleep_start);
	while (microseconds) {
		unsigned int step = microseconds > 1000U ? 1000U : microseconds;
		SceneUartPoll();
		usleep(step);
		microseconds -= step;
	}
	PERF_END(PERF_SLEEP, sleep_start);
}
#define usleep SceneStreamSleep
#else
#define SceneUartPoll() ((void)0)
#define ScenePublish(objects, count, valid, capture_ms) ((void)0)
#endif

/* The observation window begins before arming DMA, including overlapped CPU work. */
static u32 camera_packets_before, camera_crc_before;
static int camera_window;
static const char *vision_failure = "startup";

static void CameraObserve(void)
{
	camera_packets_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x04);
	camera_crc_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x08);
	/* Discard a completion latched before this observation window. Snapshot the
	 * CSI counters first so a frame racing this W1C write is still counted, then
	 * require CameraCheck to observe a later completion. */
	Xil_Out32(CAMERA_S2MM_STATUS, XAXIVDMA_IXR_FRMCNT_MASK);
	camera_window = 1;
}

static void CameraCsiReset(void)
{
	UINTPTR base = XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR;
	Xil_Out32(base + CSI_CONTROL_OFFSET, CSI_CONTROL_ENABLE | CSI_CONTROL_RESET);
	usleep(1000);
	Xil_Out32(base + CSI_CONTROL_OFFSET, CSI_CONTROL_ENABLE);
	usleep(1000);
}

static int CameraLockControls(void)
{
	u8 manual = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x3503);
	u8 exposure_h = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x3500);
	u8 exposure_m = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x3501);
	u8 exposure_l = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x3502);
	u8 gain_h = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x350a);
	u8 gain_l = (u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x350b);
	if (i2c_reg16_write(&ps_i2c0, 0x3c, 0x3503, (char)(manual | 0x03U)) != XST_SUCCESS ||
		(((u8)i2c_reg16_read(&ps_i2c0, 0x3c, 0x3503)) & 0x03U) != 0x03U)
		return XST_FAILURE;
	xil_printf("CAMERA_LOCK exposure=%02x%02x%02x gain=%02x%02x AEC=manual AGC=manual WB=PL_fixed\r\n",
		exposure_h, exposure_m, exposure_l, gain_h, gain_l);
	return XST_SUCCESS;
}

#if VISION_MINIMAL_TEST
static void CalibrationAccumulate(VisionCalibrationAccumulator *accumulator,
	const VisionColorStats *frame)
{
	unsigned int channel;
	if (!frame->samples) return;
	if (!accumulator->samples)
		for (channel = 0; channel < VISION_CALIBRATION_CHANNELS; ++channel)
			accumulator->minimum[channel] = 255U;
	for (channel = 0; channel < VISION_CALIBRATION_CHANNELS; ++channel) {
		if (frame->minimum[channel] < accumulator->minimum[channel])
			accumulator->minimum[channel] = frame->minimum[channel];
		if (frame->maximum[channel] > accumulator->maximum[channel])
			accumulator->maximum[channel] = frame->maximum[channel];
		accumulator->sum[channel] += frame->sum[channel];
	}
	accumulator->samples += frame->samples;
}

static void CalibrationExport(void)
{
	const VisionCalibrationAccumulator *sets[2] = {
		&calibration_target, &calibration_background
	};
	unsigned int set;
	vision_calibration_words[0] = calibration_frames;
	for (set = 0; set < 2; ++set) {
		const VisionCalibrationAccumulator *accumulator = sets[set];
		unsigned int base = set ? 20U : 1U;
		unsigned int channel;
		vision_calibration_words[base] = accumulator->samples;
		for (channel = 0; channel < VISION_CALIBRATION_CHANNELS; ++channel) {
			unsigned int word = base + 1U + channel * 3U;
			vision_calibration_words[word] = accumulator->minimum[channel];
			vision_calibration_words[word + 1U] = accumulator->maximum[channel];
			vision_calibration_words[word + 2U] = accumulator->samples ?
				(unsigned int)(accumulator->sum[channel] / accumulator->samples) : 0U;
		}
	}
	Xil_DCacheFlushRange((INTPTR)vision_calibration_words,
		sizeof(vision_calibration_words));
}
#endif

#endif /* !VISION_FIXED_SCENE_DEMO: camera state, timing and controls */

static void VideoRegisters(const char *stage)
{
	unsigned int channel;
	xil_printf("VIDEO stage=%s committed=%u presented=%u BGR888 1280x720 hsize=%u stride=%u\r\n",
		stage, dispCtrl.curFrame, vision_frames_presented, HORSIZE, DEMO_STRIDE);
	for (channel = 0; channel < (VISION_FIXED_SCENE_DEMO ? 1U : 2U); ++channel) {
		UINTPTR base = channel ? XPAR_AXIVDMA_1_BASEADDR : XPAR_AXIVDMA_0_BASEADDR;
		u32 off = channel ? XAXIVDMA_RX_OFFSET : XAXIVDMA_TX_OFFSET;
		u32 addr = channel ? XAXIVDMA_S2MM_ADDR_OFFSET : XAXIVDMA_MM2S_ADDR_OFFSET;
		xil_printf("%s CR=%08x SR=%08x PARKPTR=%08x ADDR0=%08x ADDR1=%08x ADDR2=%08x VSIZE=%u HSIZE=%u STRIDE=%u\r\n",
			channel ? "S2MM" : "MM2S", Xil_In32(base + off + XAXIVDMA_CR_OFFSET),
			Xil_In32(base + off + XAXIVDMA_SR_OFFSET), Xil_In32(base + XAXIVDMA_PARKPTR_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET + XAXIVDMA_START_ADDR_LEN),
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET + 2U * XAXIVDMA_START_ADDR_LEN),
			Xil_In32(base + addr + XAXIVDMA_VSIZE_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_HSIZE_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_STRD_FRMDLY_OFFSET) & XAXIVDMA_STRIDE_MASK);
	}
#if !VISION_FIXED_SCENE_DEMO
	xil_printf("CSI control/status=%08x (overflow=%u)\r\n",
		Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + CSI_CONTROL_OFFSET),
		(Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + CSI_CONTROL_OFFSET) &
		 CSI_FIFO_OVERFLOW_MASK) != 0);
	xil_printf("S2MM expected frame0=%08x frame1=%08x frame2=%08x; matched XCI enables parameter readback\r\n",
		(unsigned int)captureFrames[0], (unsigned int)captureFrames[1],
		(unsigned int)captureFrames[2]);
#endif
}

/* Both VDMA instances in the matched XCI enable video parameter readback. */
static int VideoLayoutMatches(unsigned int capture)
{
	UINTPTR base = capture ? XPAR_AXIVDMA_1_BASEADDR : XPAR_AXIVDMA_0_BASEADDR;
	u32 addr = capture ? XAXIVDMA_S2MM_ADDR_OFFSET : XAXIVDMA_MM2S_ADDR_OFFSET;
	unsigned int i;
#if VISION_FIXED_SCENE_DEMO
	if (capture) return XST_FAILURE;
#endif
	if (Xil_In32(base + addr + XAXIVDMA_VSIZE_OFFSET) != VERSIZE ||
		Xil_In32(base + addr + XAXIVDMA_HSIZE_OFFSET) != HORSIZE ||
		(Xil_In32(base + addr + XAXIVDMA_STRD_FRMDLY_OFFSET) & XAXIVDMA_STRIDE_MASK) != DEMO_STRIDE)
		return XST_FAILURE;
	for (i = 0; i < DISPLAY_NUM_FRAMES; ++i) {
#if VISION_FIXED_SCENE_DEMO
		UINTPTR expected = (UINTPTR)pFrames[i];
#else
		UINTPTR expected = capture ? captureFrames[i] : (UINTPTR)pFrames[i];
#endif
		if ((expected & 63U) ||
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET + i * XAXIVDMA_START_ADDR_LEN) != (u32)expected)
			return XST_FAILURE;
	}
	return XST_SUCCESS;
}

/* Frame 0 belongs only to S2MM; frames 1/2 alternate CPU and HDMI ownership. */
static int PresentFrame(unsigned int index)
{
	int status;
	PERF_START(flush_start);
	if (index == 0 || index >= DISPLAY_NUM_FRAMES || index == dispCtrl.curFrame)
		return XST_FAILURE;
	Xil_DCacheFlushRange((INTPTR)pFrames[index], VISION_FRAME_BYTES);
	PERF_END(PERF_FLUSH, flush_start);
	{
		PERF_START(display_start);
		status = DisplayChangeFrame(&dispCtrl, index);
		PERF_END(PERF_DISPLAY_WAIT, display_start);
	}
	return status;
}

#if !VISION_FIXED_SCENE_DEMO
/* Reject only an entirely zero active image, not low mean brightness. Zero is
 * ambiguous (clipped darkness or missing data); retain the diagnostic image.
 * Scan every active byte so a small dim object is not missed by sparse sampling. */
static int CaptureHasPixels(const u8 *frame)
{
	unsigned int y, x;
	for (y = 0; y < VERSIZE; ++y)
		for (x = 0; x < HORSIZE; ++x)
			if (frame[y * DEMO_STRIDE + x]) return 1;
	return 0;
}
#endif

/* Never exit main or reuse uncertain buffers. Retry the previous park; if the
 * read channel faulted, reset only MM2S and restart that same retained image. */
static void DiagnosticHold(const char *reason)
{
	PERF_EVENT(PERF_HOLD);
#if !VISION_FIXED_SCENE_DEMO
	ScenePublish(NULL, 0, 0, NowMs());
	(void)vdma_write_reset(XPAR_AXIVDMA_1_DEVICE_ID);
#endif
	for (;;) {
		u32 sr = Xil_In32(XPAR_AXIVDMA_0_BASEADDR + XAXIVDMA_TX_OFFSET + XAXIVDMA_SR_OFFSET);
		int restored;
		if (sr & (XAXIVDMA_SR_ERR_ALL_MASK | XAXIVDMA_SR_HALTED_MASK)) {
			unsigned int poll;
			XAxiVdma_Reset(&vdma, XAXIVDMA_READ);
			for (poll = 0; poll < 1000 && XAxiVdma_ResetNotDone(&vdma, XAXIVDMA_READ); ++poll)
				usleep(1000);
			if (poll < 1000) {
				dispCtrl.state = DISPLAY_STOPPED;
				(void)DisplayStart(&dispCtrl);
			}
		}
		restored = DisplayChangeFrame(&dispCtrl, dispCtrl.curFrame);
		xil_printf("DIAGNOSTIC HOLD reason=%s retained=%u confirmed=%u; buffers frozen\r\n",
			reason, dispCtrl.curFrame, restored == XST_SUCCESS);
		VideoRegisters(reason);
		usleep(1000000);
	}
}

#if !VISION_FIXED_SCENE_DEMO
#if !VISION_MINIMAL_TEST && !VISION_GREEN_TARGET_ONLY
static void VisionLevelLog(unsigned int events,
                           RayGameLevelState previous_state)
{
    if (events & RAY_LEVEL_EVENT_SOURCE_SAMPLE)
        xil_printf("[SOURCE] sample %d/%d\r\n",
            ray_level.source_sample_count, RAY_GAME_SOURCE_LOCK_SAMPLES);
    if (events & RAY_LEVEL_EVENT_SOURCE_LOCKED)
        xil_printf("[SOURCE] locked origin=(%d,%d) dir_milli=(%d,%d)\r\n",
            (int)ray_level.locked_source.source_tip.x,
            (int)ray_level.locked_source.source_tip.y,
            (int)(1000.0f*ray_level.locked_source.source_direction.x),
            (int)(1000.0f*ray_level.locked_source.source_direction.y));
    if (events & RAY_LEVEL_EVENT_RAY_COMMITTED)
        xil_printf("[RAY] stable ray committed, segments=%d\r\n",
            ray_level.committed_ray.segment_count);
    if (events & RAY_LEVEL_EVENT_CANDIDATE_INVALID)
        xil_printf("[RAY] candidate invalid, keep committed ray segments=%d\r\n",
            ray_level.committed_ray_valid ?
                ray_level.committed_ray.segment_count : 0);
    if (events & RAY_LEVEL_EVENT_TARGET_HIT)
        xil_printf("[TARGET] hit %d/%d\r\n", ray_level.target_hit_count,
            RAY_GAME_TARGET_CONFIRM_HITS);
    if (events & RAY_LEVEL_EVENT_TARGET_CONFIRMED)
        xil_printf("[TARGET] confirmed\r\n");
    if (events & RAY_LEVEL_EVENT_LEVEL_CLEARED)
        xil_printf("[RAY] committed ray cleared: valid scene has no SOURCE\r\n");
    if (events & RAY_LEVEL_EVENT_STATE_CHANGED)
        xil_printf("[LEVEL] %s -> %s\r\n",
            ray_game_level_state_name(previous_state),
            ray_game_level_state_name(ray_level.state));
}
#endif

static int VisionRunOnce(unsigned int capture_index)
{
#if !VISION_MINIMAL_TEST
	VisionDetection detections[VISION_MAX_DETECTIONS];
	SceneObject scene_objects[VISION_MAX_DETECTIONS];
	unsigned int detected_mask = 0U;
	unsigned int hit_mask = 0U;
#if VISION_GREEN_TARGET_ONLY
	RayGameResult ray_result;
#else
	const RayGameResult *display_ray;
	RayGameLevelState previous_level_state;
	unsigned int level_events;
	int candidate_scene_valid = 1;
#endif
#endif
#if VISION_MINIMAL_TEST
	VisionMinimalProbe probe;
#endif
	unsigned int next = dispCtrl.curFrame == 1 ? 2 : 1;
	u8 *frame = pFrames[next];
	unsigned int started = NowMs();
	static unsigned int last_log;
	unsigned int write_index;
	unsigned int expected_write;
	u8 *capture;
	int count;
	int i;
	#if !VISION_MINIMAL_TEST
	int source_direction_invalid = 0;
	#endif
	unsigned int color_started;

	if (capture_index >= VDMA_CAPTURE_FRAME_COUNT) {
		vision_failure = "invalid capture frame index";
		return XST_FAILURE;
	}
	capture = (u8 *)captureFrames[capture_index];
	expected_write = (capture_index + 1U) % VDMA_CAPTURE_FRAME_COUNT;
	CameraObserve();
	if (vdma_capture_current(&write_index) != XST_SUCCESS ||
		write_index != expected_write) {
		vision_failure = "capture ring advanced before copy";
		return VISION_RETRY_FRAME;
	}
	/* S2MM continues in a three-frame ring. The preceding store is stable for
	 * one full frame interval while it is copied into a display-owned buffer. */
	{
	PERF_START(invalidate_start);
	Xil_DCacheInvalidateRange((INTPTR)capture, VISION_FRAME_BYTES);
	PERF_END(PERF_INVALIDATE, invalidate_start);
	}
	{
	PERF_START(check_start);
	int has_pixels = CaptureHasPixels(capture);
	PERF_END(PERF_PIXEL_CHECK, check_start);
	if (!has_pixels) {
		vision_failure = "capture all-zero (dark/invalid); retaining image";
		return VISION_RETRY_FRAME;
	}
	}
	{
	PERF_START(copy_start);
	for (i = 0; i < VERSIZE; ++i)
		memcpy(frame + i * DEMO_STRIDE, capture + i * DEMO_STRIDE, HORSIZE);
	PERF_END(PERF_COPY, copy_start);
	}
	vision_last_capture_ms = NowMs() - started;
	if (vdma_capture_current(&write_index) != XST_SUCCESS) {
		vision_failure = "capture ring readback";
		return XST_FAILURE;
	}
	if (write_index == capture_index) {
		vision_failure = "capture ring overrun during copy";
		return VISION_RETRY_FRAME;
	}
	color_started = NowMs();
	{
	PERF_START(detect_start);
#if VISION_MINIMAL_TEST
	count = vision_minimal_probe_bgr888(frame, 1280, VERSIZE, DEMO_STRIDE, &probe);
#elif VISION_GREEN_TARGET_ONLY
	count = green_target_detect_bgr888(frame, 1280, VERSIZE, DEMO_STRIDE,
		detections, VISION_MAX_DETECTIONS);
#else
	count = vision_detect_bgr888(frame, 1280, VERSIZE, DEMO_STRIDE,
		detections, VISION_MAX_DETECTIONS);
	PERF_END(PERF_DETECT, detect_start);
	/* Raw full detection scene, independent of the HDMI level's retained ray. */
	ScenePublish(detections, count, count >= 0, started);
#endif
	}
	if (count < 0) {
#if !VISION_MINIMAL_TEST && !VISION_GREEN_TARGET_ONLY
		candidate_scene_valid = 0;
		count = 0;
#else
		vision_failure = "vision detect";
		xil_printf("VISION error=%d\r\n", count);
		return XST_FAILURE;
#endif
	}
	vision_last_color_ms = NowMs() - color_started;
#if VISION_MINIMAL_TEST
	vision_minimal_pixels = probe.green_pixels;
	vision_minimal_center_x = probe.green_center_x;
	vision_minimal_center_y = probe.green_center_y;
	vision_last_count = 0;
#else
	vision_last_count = (unsigned int)count;
	{
		PERF_START(ray_start);
		int scene_count = 0;
		for (i = 0; i < count; ++i)
			if ((unsigned int)detections[i].type < RAY_OBJECT_TYPE_COUNT)
				detected_mask |= 1U << (unsigned int)detections[i].type;
#if VISION_GREEN_TARGET_ONLY
		scene_count = ray_game_scene_from_detections(
			detections, count, scene_objects, VISION_MAX_DETECTIONS);
#else
		if (candidate_scene_valid)
			scene_count = ray_game_scene_from_detections(
				detections, count, scene_objects, VISION_MAX_DETECTIONS);
#endif
#if VISION_GREEN_TARGET_ONLY
		if (scene_count < 0 || ray_game_trace(scene_objects, scene_count,
			1280.0f, (float)VERSIZE, &ray_result) != 0) {
			vision_failure = "ray game";
			return XST_FAILURE;
		}
#else
		if (scene_count < 0) {
			candidate_scene_valid = 0;
			scene_count = 0;
		}
		previous_level_state = ray_level.state;
		level_events = ray_game_level_update(&ray_level,
			scene_objects, scene_count, candidate_scene_valid,
			1280.0f, (float)VERSIZE);
		VisionLevelLog(level_events, previous_level_state);
		display_ray = ray_game_level_display_ray(&ray_level);
#endif
		for (i = 0; i < count; ++i)
			if (detections[i].type == VISION_SOURCE &&
				!detections[i].direction_valid)
				source_direction_invalid = 1;
		PERF_END(PERF_RAY, ray_start);
	}
#endif
	vision_last_processing_ms = NowMs() - started;
#if VISION_MINIMAL_TEST
	if (calibration_frames < VISION_CALIBRATION_FRAMES &&
		probe.target_roi.samples && probe.background.samples) {
		CalibrationAccumulate(&calibration_target, &probe.target_roi);
		CalibrationAccumulate(&calibration_background, &probe.background);
		++calibration_frames;
		CalibrationExport();
	}
	vision_probe_words[0] = vision_frames_presented + 1U;
	vision_probe_words[1] = (unsigned int)capture;
	vision_probe_words[2] = probe.minimum[0];
	vision_probe_words[3] = probe.maximum[0];
	vision_probe_words[4] = probe.mean[0];
	vision_probe_words[5] = probe.minimum[1];
	vision_probe_words[6] = probe.maximum[1];
	vision_probe_words[7] = probe.mean[1];
	vision_probe_words[8] = probe.minimum[2];
	vision_probe_words[9] = probe.maximum[2];
	vision_probe_words[10] = probe.mean[2];
	vision_probe_words[11] = probe.nonzero_all;
	for (i = 0; i < VISION_PROBE_SAMPLE_COUNT; ++i)
		vision_probe_words[12 + i] = ((unsigned int)probe.sample_bgr[i][2] << 16) |
			((unsigned int)probe.sample_bgr[i][1] << 8) | probe.sample_bgr[i][0];
	vision_probe_words[17] = probe.green_pixels;
	vision_probe_words[18] = (unsigned int)probe.green_bbox_x;
	vision_probe_words[19] = (unsigned int)probe.green_bbox_y;
	vision_probe_words[20] = (unsigned int)probe.green_bbox_w;
	vision_probe_words[21] = (unsigned int)probe.green_bbox_h;
	vision_probe_words[22] = (unsigned int)probe.green_center_x;
	vision_probe_words[23] = (unsigned int)probe.green_center_y;
	vision_probe_words[24] = vision_last_capture_ms;
	vision_probe_words[25] = vision_last_color_ms;
	vision_probe_words[26] = vision_last_processing_ms;
	Xil_DCacheFlushRange((INTPTR)vision_probe_words, sizeof(vision_probe_words));
#endif
	{
	PERF_START(overlay_start);
	#if !VISION_MINIMAL_TEST && VISION_GREEN_TARGET_ONLY
	for (i = 0; i < ray_result.hit_count; ++i)
		if ((unsigned int)ray_result.hit_types[i] < RAY_OBJECT_TYPE_COUNT)
			hit_mask |= 1U << (unsigned int)ray_result.hit_types[i];
	vision_overlay(frame, 1280, VERSIZE, DEMO_STRIDE, ray_result.segments,
		ray_result.segment_count,
		detected_mask, hit_mask,
		vision_last_processing_ms);
	#elif !VISION_MINIMAL_TEST
	if (ray_level.state == RAY_LEVEL_ACTIVE && !display_ray)
		++vision_active_zero_ray_frames;
	if (display_ray)
		for (i = 0; i < display_ray->hit_count; ++i)
			if ((unsigned int)display_ray->hit_types[i] < RAY_OBJECT_TYPE_COUNT)
				hit_mask |= 1U << (unsigned int)display_ray->hit_types[i];
	vision_overlay(frame, 1280, VERSIZE, DEMO_STRIDE,
		display_ray ? display_ray->segments : NULL,
		display_ray ? display_ray->segment_count : 0,
		detected_mask, hit_mask,
		vision_last_processing_ms);
	#endif
	PERF_END(PERF_OVERLAY, overlay_start);
	}
	if (PresentFrame(next) != XST_SUCCESS) {
		vision_failure = "present frame";
		return XST_FAILURE;
	}
	++vision_frames_presented;
	SceneUartPoll();
	if (vision_frames_presented == 1) VideoRegisters("FIRST_CAMERA_FRAME_COMMITTED");
	/* Retain the legacy log gate; live mode suppresses these verbose prints. */
	if (vision_frames_presented != 1 && NowMs() - last_log < 1000U) return XST_SUCCESS;
	last_log = NowMs();
#if VISION_MINIMAL_TEST
	xil_printf("FRAME_PROBE frame=%u\r\n", vision_frames_presented);
	xil_printf("address=%08x width=1280 height=%u stride=%u active_line_bytes=%u bytes_per_pixel=3 format=BGR888 buffer_size=%u\r\n",
		(unsigned int)capture, VERSIZE, DEMO_STRIDE, HORSIZE, VISION_FRAME_BYTES);
	xil_printf("B min/max/mean=%u/%u/%u G min/max/mean=%u/%u/%u R min/max/mean=%u/%u/%u nonzero=%u\r\n",
		probe.minimum[0], probe.maximum[0], probe.mean[0],
		probe.minimum[1], probe.maximum[1], probe.mean[1],
		probe.minimum[2], probe.maximum[2], probe.mean[2], probe.nonzero_all);
	xil_printf("sample(0,0)=%u,%u,%u sample(320,180)=%u,%u,%u sample(640,360)=%u,%u,%u sample(960,540)=%u,%u,%u sample(1279,719)=%u,%u,%u order=RGB\r\n",
		probe.sample_bgr[0][2], probe.sample_bgr[0][1], probe.sample_bgr[0][0],
		probe.sample_bgr[1][2], probe.sample_bgr[1][1], probe.sample_bgr[1][0],
		probe.sample_bgr[2][2], probe.sample_bgr[2][1], probe.sample_bgr[2][0],
		probe.sample_bgr[3][2], probe.sample_bgr[3][1], probe.sample_bgr[3][0],
		probe.sample_bgr[4][2], probe.sample_bgr[4][1], probe.sample_bgr[4][0]);
#if VISION_MINIMAL_TARGET_CALIBRATED
	xil_printf("VISION_MINIMAL threshold_state=REAL_CAMERA_CALIBRATED candidate=%s pixels=%u bbox=%d,%d,%d,%d center=%d,%d capture_ms=%u color_ms=%u total_ms=%u\r\n",
		probe.green_pixels >= VISION_MINIMAL_TARGET_MIN_PIXELS ? "TARGET" : "NONE",
#else
	xil_printf("VISION_MINIMAL threshold_state=UNVERIFIED_OFFLINE_DEFAULT candidate=CALIBRATION_REQUIRED pixels=%u bbox=%d,%d,%d,%d center=%d,%d capture_ms=%u color_ms=%u total_ms=%u\r\n",
#endif
		probe.green_pixels, probe.green_bbox_x, probe.green_bbox_y,
		probe.green_bbox_w, probe.green_bbox_h, probe.green_center_x,
		probe.green_center_y, vision_last_capture_ms, vision_last_color_ms,
		vision_last_processing_ms);
#else
	xil_printf("VISION detections=%d sample_step=%d\r\n",
		count, VISION_SAMPLE_STEP);
	if (source_direction_invalid)
		xil_printf("RAY SOURCE direction_valid=0 reason=orange_white_marker_missing_or_invalid; valid SOURCE-free scene clears committed ray\r\n");
	for (i = 0; i < count; ++i) {
		const VisionDetection *d = &detections[i];
#if VISION_GREEN_TARGET_ONLY
		xil_printf("TARGET cx=%d cy=%d bbox=%d,%d,%d,%d area=%u confidence=%d processing_ms=%u\r\n",
			d->center_x, d->center_y, d->bbox_x, d->bbox_y,
			d->bbox_w, d->bbox_h, d->sampled_area,
			d->confidence_percent, vision_last_processing_ms);
#else
		xil_printf("OBJECT class=%s cx=%d cy=%d bbox=%d,%d,%d,%d geom=%d,%d axis_milli=%d,%d size=%d,%d area=%u confidence=%d orientation=%d processing_ms=%u\r\n",
			vision_type_name(d->type), d->center_x, d->center_y,
			d->bbox_x, d->bbox_y, d->bbox_w, d->bbox_h,
			(int)d->geometry_center_x, (int)d->geometry_center_y,
			(int)(1000.0f*d->axis_x), (int)(1000.0f*d->axis_y),
			(int)d->major_length, (int)d->minor_width,
			d->sampled_area, d->confidence_percent, d->angle_deg,
			vision_last_processing_ms);
#endif
	}
#if !VISION_GREEN_TARGET_ONLY
	if (display_ray)
		xil_printf("RAY_SUMMARY segments=%d interactions=%d termination=%d hits=%d detected_mask=%u hit_mask=%u\r\n",
			display_ray->segment_count, display_ray->interaction_count,
			(int)display_ray->termination, display_ray->hit_count,
			detected_mask, hit_mask);
	else
		xil_printf("RAY_SUMMARY segments=0 interactions=0 termination=-1 hits=0 detected_mask=%u hit_mask=0\r\n",
			detected_mask);
#endif
#endif
	return XST_SUCCESS;
}

/* Count fresh packets and completed writes, not just a readable sensor ID. */
static int CameraCheck(int verbose, unsigned int *frame_index)
{
	PERF_START(wait_start);
	u32 packets_before, packets_after, crc_before, crc_after, status, csi_status;
	int healthy;
	unsigned int started = NowMs();
	packets_before = camera_packets_before;
	crc_before = camera_crc_before;
	do {
		status = Xil_In32(CAMERA_S2MM_STATUS);
		if (status & XAXIVDMA_SR_ERR_ALL_MASK) break;
		if (status & XAXIVDMA_IXR_FRMCNT_MASK) break;
		usleep(1000);
	} while (NowMs() - started < 2000U);
	packets_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x04);
	crc_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x08);
	csi_status = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CSI_CONTROL_OFFSET);
	status = Xil_In32(CAMERA_S2MM_STATUS);
	/* Unsigned subtraction permits wrap; windows must contain < 2^32 events. */
	healthy = camera_window && (u32)(packets_after - packets_before) != 0 &&
		(u32)(crc_after - crc_before) == 0 &&
		(status & XAXIVDMA_IXR_FRMCNT_MASK) &&
		!(status & (XAXIVDMA_SR_HALTED_MASK | XAXIVDMA_SR_ERR_ALL_MASK)) &&
		!(csi_status & CSI_FIFO_OVERFLOW_MASK);
	if (healthy)
		healthy = vdma_capture_ready(frame_index) == XST_SUCCESS;
	camera_window = 0; /* A completed frame is consumed exactly once. */
	if (verbose || !healthy) {
		xil_printf("CSI long packets: %u -> %u, CRC errors: %u -> %u\r\n",
			packets_before, packets_after, crc_before, crc_after);
		xil_printf("Camera VDMA S2MM status: 0x%08x, frame completed: %u, CSI overflow: %u\r\n",
			status, (status & XAXIVDMA_IXR_FRMCNT_MASK) != 0,
			(csi_status & CSI_FIFO_OVERFLOW_MASK) != 0);
	}
	PERF_END(PERF_CAPTURE_WAIT, wait_start);
	if (!healthy) PERF_EVENT(PERF_CAPTURE_FAIL);
	return healthy ? XST_SUCCESS : XST_FAILURE;
}

static int CameraStart(unsigned int *frame_index)
{
	int attempt, status;
	for (attempt = 1; attempt <= CAMERA_START_ATTEMPTS; ++attempt) {
		xil_printf("Camera start attempt %d/%d\r\n", attempt, CAMERA_START_ATTEMPTS);
		/* Quiesce DDR writes before stopping the sensor or redrawing bars. */
		if (vdma_write_reset(XPAR_AXIVDMA_1_DEVICE_ID) != XST_SUCCESS) {
			xil_printf("Capture reset failed; check capture clocks/reset\r\n");
			return XST_FAILURE;
		}
		XGpioPs_WritePin(&Gpio, 54, 0);
		usleep(1000000);
		XGpioPs_WritePin(&Gpio, 54, 1);
		usleep(1000000);
		status = i2c_init(&ps_i2c0, XPAR_XIICPS_0_DEVICE_ID, 100000);
		if (status != XST_SUCCESS) {
			xil_printf("Camera I2C reinitialization failed: %d\r\n", status);
			continue;
		}
		status = sensor_configure(&ps_i2c0);
		if (status != XST_SUCCESS) {
			xil_printf("Camera configuration failed: %d\r\n", status);
			continue;
		}
		CameraCsiReset();
		CameraObserve();
		status = vdma_write_init(XPAR_AXIVDMA_1_DEVICE_ID, HORSIZE, VERSIZE,
			DEMO_STRIDE, captureFrames);
		if (status != XST_SUCCESS) {
			xil_printf("Camera VDMA initialization failed: %d\r\n", status);
			continue;
		}
		if (VideoLayoutMatches(1) != XST_SUCCESS) {
			VideoRegisters("S2MM_LAYOUT_MISMATCH");
			continue;
		}
		status = sensor_start(&ps_i2c0);
		if (status != XST_SUCCESS) {
			xil_printf("Camera stream start failed: %d\r\n", status);
			continue;
		}
		/* Let AEC/AGC settle under the final scene, then retain the resulting
		 * exposure/gain. RAW-mode sensor AWB/CCM is disabled and PL WB is fixed. */
		usleep(1000000);
		if (CameraLockControls() != XST_SUCCESS) {
			xil_printf("Camera exposure/gain lock failed\r\n");
			continue;
		}
		CameraObserve();
		if (CameraCheck(1, frame_index) == XST_SUCCESS) {
			xil_printf("Camera capture ready on attempt %d\r\n", attempt);
			return XST_SUCCESS;
		}
		xil_printf("Camera capture unhealthy; retrying initialization\r\n");
	}
	/* Leave a diagnostic pattern only after capture can no longer overwrite it. */
	if (vdma_write_reset(XPAR_AXIVDMA_1_DEVICE_ID) == XST_SUCCESS) {
		XGpioPs_WritePin(&Gpio, 54, 0);
	}
	xil_printf("Camera failed after %d attempts; inspect MIPI clocks/reset and cable\r\n",
		CAMERA_START_ATTEMPTS);
	return XST_FAILURE;
}

#endif /* !VISION_FIXED_SCENE_DEMO: recognition and camera startup */

#if VISION_FIXED_SCENE_DEMO
/* Logical pixels, equal 1:1 display scale. Sizes match PC game_config.json;
 * MIRROR length is already the effective surface, not a detected carrier.
 * PC scenes supply observed centers, so this demo supplies a fixed layout. */
static int FixedScenePresent(void)
{
	SceneObject objects[] = {
		{RAY_OBJECT_SOURCE, {160.0f, 540.0f}, {1.0f, 0.0f},
		 54.0f, 40.0f, {0.0f, 0.0f}, {1.0f, 0.0f}, 1},
		{RAY_OBJECT_MIRROR, {420.0f, 540.0f}, {0.70710678f, -0.70710678f},
		 140.0f, 12.0f, {0.0f, 0.0f}, {0.0f, 0.0f}, 0},
		{RAY_OBJECT_WALL, {660.0f, 550.0f}, {1.0f, 0.0f},
		 160.0f, 30.0f, {0.0f, 0.0f}, {0.0f, 0.0f}, 0},
		{RAY_OBJECT_TARGET, {1100.0f, 300.0f}, {1.0f, 0.0f},
		 64.0f, 64.0f, {0.0f, 0.0f}, {0.0f, 0.0f}, 0},
		{RAY_OBJECT_PORTAL_A, {420.0f, 300.0f}, {1.0f, 0.0f},
		 164.0f, 56.0f, {0.0f, 0.0f}, {0.0f, 0.0f}, 0},
		{RAY_OBJECT_PORTAL_B, {860.0f, 300.0f}, {0.0f, 1.0f},
		 164.0f, 56.0f, {0.0f, 0.0f}, {0.0f, 0.0f}, 0}
	};
	RayGameResult ray;
	SceneObject *source = &objects[0];
	const int count = (int)(sizeof objects / sizeof objects[0]);
	unsigned int next = dispCtrl.curFrame == 1U ? 2U : 1U;
	/* Same triangle centroid/tip convention as PC Model.source_tip. The trace
	 * starts 3 logical pixels ahead of this visible tip; epsilon is 1 pixel. */
	source->source_tip.x = source->center.x + source->axis.x * source->length * (2.0f / 3.0f);
	source->source_tip.y = source->center.y + source->axis.y * source->length * (2.0f / 3.0f);
	/* Startup has confirmed park on frame 1. Never draw into an active buffer
	 * or frame 0, which remains reserved for capture in the camera build. */
	if (dispCtrl.state != DISPLAY_RUNNING || dispCtrl.curFrame != 1U)
		return XST_FAILURE;
	if (ray_game_trace(objects, count, VISION_FIXED_SCENE_WIDTH,
		VISION_FIXED_SCENE_HEIGHT, &ray) != 0)
		return XST_FAILURE;
	vision_overlay_scene(pFrames[next], VISION_FIXED_SCENE_WIDTH,
		VISION_FIXED_SCENE_HEIGHT, DEMO_STRIDE, objects, count, &ray);
	/* Flush the full strided 720-line span, then wait for MM2S acknowledgement.
	 * On failure both display buffers stay frozen in DiagnosticHold. */
	if (PresentFrame(next) != XST_SUCCESS) return XST_FAILURE;
	vision_frames_presented++;
	xil_printf("FIXED_SCENE committed=%u segments=%d interactions=%d target=%d termination=%d\r\n",
		dispCtrl.curFrame, ray.segment_count, ray.interaction_count,
		ray.success, (int)ray.termination);
	return XST_SUCCESS;
}
#endif

int main()
{



	int Status;
	XAxiVdma_Config *vdmaConfig;
	int i;
#if VISION_SCENE_STREAM_ENABLE
	scene_stream_init(&scene_stream, VISION_SCENE_STREAM_HZ, VISION_SCENE_STREAM_BAUD);
#endif
#if !VISION_FIXED_SCENE_DEMO
#if !VISION_MINIMAL_TEST && !VISION_GREEN_TARGET_ONLY
	ray_game_level_reset(&ray_level);
	vision_active_zero_ray_frames = 0;
#endif

	xil_printf("color_test camera diagnostic start\r\n");
	xil_printf("Camera recovery: RAW10 continuous three-frame S2MM ring\r\n");
	xil_printf("Vision PS v3: %s, frame-driven processing\r\n",
		VISION_MINIMAL_TEST ? "minimal TARGET input/color probe" :
		(VISION_GREEN_TARGET_ONLY ? "pure-green circular TARGET HDMI overlay" :
		 "six-class Portal ray MVP"));
	xil_printf("Vision firmware build=%s\r\n", VISION_FIRMWARE_BUILD_ID);
	xil_printf("ISP: effective BGGR (Xilinx phase 3), gamma 1/1.8, WB 1/1/1, highlight disabled in matched PL\r\n");
	xil_printf("Focus: mechanically adjust the lens if this is a fixed-focus module\r\n");
#else
	xil_printf("FIXED_SCENE HDMI demo: 1280x720 logical pixels, camera bypassed\r\n");
#endif

	/*
	 * Initialize an array of pointers to the 3 frame buffers
	 */
	for (i = 0; i < DISPLAY_NUM_FRAMES; i++)
	{
		pFrames[i] = frameBuf[i];
		memset(pFrames[i], 0, DEMO_MAX_FRAME);
		Xil_DCacheFlushRange((INTPTR) pFrames[i], DEMO_MAX_FRAME) ;
	}
#if !VISION_FIXED_SCENE_DEMO
	captureFrames[0] = (UINTPTR)pFrames[0];
	for (i = 1; (unsigned int)i < VDMA_CAPTURE_FRAME_COUNT; ++i) {
		captureFrames[i] = (UINTPTR)captureAux[i - 1];
		memset((void *)captureFrames[i], 0, DEMO_MAX_FRAME);
		Xil_DCacheFlushRange((INTPTR)captureFrames[i], DEMO_MAX_FRAME);
	}

	Xil_Out32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR, CAMERA_GAMMA_FACTOR_1_8);
	/* AXI_GammaCorrection's AXI-Lite read data is hard-wired to zero. */
	xil_printf("Gamma configured: 1/1.8 (write-only AXI-Lite selector)\r\n");
#endif
	/*
	 * Initialize VDMA driver
	 */
	/* Bring up diagnostic output before any camera initialization. */
	for (;;) {
		xil_printf("VIDEO stage=DISPLAY_INIT_BEGIN\r\n");
		vdmaConfig = XAxiVdma_LookupConfig(VGA_VDMA_ID);
		Status = vdmaConfig ? XAxiVdma_CfgInitialize(&vdma, vdmaConfig, vdmaConfig->BaseAddress) : XST_FAILURE;
		if (Status == XST_SUCCESS)
			Status = DisplayInitialize(&dispCtrl, &vdma, DISP_VTC_ID, DYNCLK_BASEADDR, pFrames, DEMO_STRIDE);
		if (Status == XST_SUCCESS) break;
		xil_printf("VIDEO stage=DISPLAY_INIT_FAILED status=%d; retrying\r\n", Status);
		VideoRegisters("DISPLAY_INIT_FAILED");
		usleep(1000000);
	}
	dispCtrl.curFrame = 1;
	DemoPrintTest(pFrames[1], 1280, VERSIZE, DEMO_STRIDE, 0);
	/* Circular startup must never briefly fetch the black capture buffer. */
	dispCtrl.vdmaConfig.EnableCircularBuf = 0;
	for (;;) {
		xil_printf("VIDEO stage=DISPLAY_START_BEGIN\r\n");
		Status = DisplayStart(&dispCtrl);
		if (Status == XST_SUCCESS &&
			DisplayChangeFrame(&dispCtrl, 1) == XST_SUCCESS) break;
		VideoRegisters("DISPLAY_START_FAILED");
		XAxiVdma_Reset(&vdma, XAXIVDMA_READ);
		for (i = 0; i < 1000 && XAxiVdma_ResetNotDone(&vdma, XAXIVDMA_READ); ++i)
			usleep(1000);
		dispCtrl.state = DISPLAY_STOPPED;
		usleep(1000000);
	}
	if (VideoLayoutMatches(0) != XST_SUCCESS) DiagnosticHold("MM2S layout mismatch");
#if VISION_FIXED_SCENE_DEMO
	if (FixedScenePresent() != XST_SUCCESS) DiagnosticHold("fixed scene trace/present failed");
	/* MM2S continuously reads the committed frame; no repaint, copy, trace,
	 * capture, camera checks or framebuffer writes in the steady state. */
	for (;;) usleep(1000000);
#else
	VideoRegisters("BARS_ACTIVE");
	for (i = 0; i < 5; ++i) {
		xil_printf("VIDEO BARS_ONLY second=%d; camera not started\r\n", i + 1);
		usleep(1000000);
	}
	if (PsGpioSetup() != XST_SUCCESS) DiagnosticHold("camera GPIO init");
	{
		unsigned int capture_index = 0;
		PERF_START(startup_start);
		Status = CameraStart(&capture_index);
		PERF_END(PERF_RECOVERY, startup_start);
		if (Status != XST_SUCCESS) {
			VideoRegisters("CAPTURE_FAILED_RETAINING_IMAGE");
			DiagnosticHold("camera startup failed after bounded retries");
		}
		/* CameraStart already validated its first frame; do not consume it twice. */
		for (;;) {
			PERF_START(loop_start);
			if (Xil_In32(XPAR_AXIVDMA_0_BASEADDR + XAXIVDMA_SR_OFFSET) &
				(XAXIVDMA_SR_ERR_ALL_MASK | XAXIVDMA_SR_HALTED_MASK))
				DiagnosticHold("MM2S runtime error");
			if (Status != XST_SUCCESS) {
				PERF_START(recovery_start);
				ScenePublish(NULL, 0, 0, NowMs());
				/* Permit one bounded runtime recovery. CameraStart already owns
				 * its three attempts; do not wrap it in another infinite loop. */
				VideoRegisters("CAPTURE_FAILED_RETAINING_IMAGE");
				usleep(1000000);
				Status = CameraStart(&capture_index);
				PERF_END(PERF_RECOVERY, recovery_start);
				if (Status != XST_SUCCESS) {
					VideoRegisters("CAPTURE_RECOVERY_EXHAUSTED");
					DiagnosticHold("camera recovery failed after bounded retries");
				}
				PERF_END(PERF_LOOP, loop_start);
				continue;
			}
			{
			PERF_START(process_start);
			Status = VisionRunOnce(capture_index);
			PERF_END(PERF_PROCESS, process_start);
			}
			if (Status == VISION_RETRY_FRAME) {
				PERF_EVENT(PERF_RETRY);
				ScenePublish(NULL, 0, 0, NowMs());
				xil_printf("VIDEO %s; retrying capture\r\n", vision_failure);
			} else if (Status != XST_SUCCESS) {
				PERF_EVENT(PERF_PROCESS_FAIL);
				DiagnosticHold(vision_failure);
			}
			Status = CameraCheck(0, &capture_index);
			PERF_END(PERF_LOOP, loop_start);
		}
	}
#endif
}


void DemoPrintTest(u8 *frame, u32 width, u32 height, u32 stride, int pattern)
{
	u32 xcoi, ycoi;
	u32 iPixelAddr = 0;
	u8 wRed, wBlue, wGreen;
	u32 xInt;
	(void)pattern;

	xInt = width*BYTES_PIXEL / 8; //each with width/8 pixels

	for(ycoi = 0; ycoi < height; ycoi++)
	{

		/*
		 * Just draw white in the last partial interval (when width is not divisible by 7)
		 */

		for(xcoi = 0; xcoi < (width*BYTES_PIXEL); xcoi+=BYTES_PIXEL)
		{

			if (xcoi < xInt) {                                   //White color
				wRed = 255;
				wGreen = 255;
				wBlue = 255;
			}

			else if ((xcoi >= xInt) && (xcoi < xInt*2)){         //YELLOW color
				wRed = 255;
				wGreen = 255;
				wBlue = 0;
			}
			else if ((xcoi >= xInt*2) && (xcoi < xInt*3)){        //CYAN color
				wRed = 0;
				wGreen = 255;
				wBlue = 255;
			}
			else if ((xcoi >= xInt*3) && (xcoi < xInt*4)){        //GREEN color
				wRed = 0;
				wGreen = 255;
				wBlue = 0;
			}
			else if ((xcoi >= xInt*4) && (xcoi < xInt*5)){        //MAGENTA color
				wRed = 255;
				wGreen = 0;
				wBlue = 255;
			}
			else if ((xcoi >= xInt*5) && (xcoi < xInt*6)){        //RED color
				wRed = 255;
				wGreen = 0;
				wBlue = 0;
			}
			else if ((xcoi >= xInt*6) && (xcoi < xInt*7)){        //BLUE color
				wRed = 0;
				wGreen = 0;
				wBlue = 255;
			}
			else {                                                //BLACK color
				wRed = 0;
				wGreen = 0;
				wBlue = 0;
			}

			frame[xcoi+iPixelAddr + 0] = wBlue;
			frame[xcoi+iPixelAddr + 1] = wGreen;
			frame[xcoi+iPixelAddr + 2] = wRed;
			/*
			 * This pattern is printed one vertical line at a time, so the address must be incremented
			 * by the stride instead of just 1.
			 */
		}
		iPixelAddr += stride;

	}

	/*
	 * Flush the framebuffer memory range to ensure changes are written to the
	 * actual memory, and therefore accessible by the VDMA.
	 */
	Xil_DCacheFlushRange((unsigned int) frame, DEMO_MAX_FRAME);
}


#if !VISION_FIXED_SCENE_DEMO
int PsGpioSetup()
{
	XGpioPs_Config *GPIO_CONFIG ;
	int Status ;

	GPIO_CONFIG = XGpioPs_LookupConfig(XPAR_XGPIOPS_0_DEVICE_ID) ;
	if (GPIO_CONFIG == NULL) return XST_FAILURE;

	Status = XGpioPs_CfgInitialize(&Gpio, GPIO_CONFIG, GPIO_CONFIG->BaseAddr) ;
	if (Status != XST_SUCCESS)
	{
		return XST_FAILURE ;
	}
	/* set MIO 54 as output */
	XGpioPs_SetDirectionPin(&Gpio, 54, 1) ;

	XGpioPs_SetOutputEnablePin(&Gpio, 54, 1);


	return XST_SUCCESS ;
}
#endif
