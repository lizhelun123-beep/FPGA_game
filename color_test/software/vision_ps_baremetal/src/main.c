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
#include <stdio.h>
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
#include "vision_ps.h"
#include "vision_overlay.h"
#include "xtime_l.h"
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
XIicPs ps_i2c0;

XGpioPs Gpio;

/*
 * Framebuffers for video data
 */
u8 frameBuf[DISPLAY_NUM_FRAMES][DEMO_MAX_FRAME] __attribute__ ((aligned(64)));
u8 *pFrames[DISPLAY_NUM_FRAMES]; //array of pointers to the frame buffers

/* ------------------------------------------------------------ */
/*				Procedure Definitions							*/
/* ------------------------------------------------------------ */
int PsGpioSetup() ;

#define CAMERA_START_ATTEMPTS 3
#define CAMERA_S2MM_STATUS (XPAR_AXIVDMA_1_BASEADDR + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET)
#define CAMERA_GAMMA_FACTOR_1_8 3U
#define VISION_FRAME_BYTES (DEMO_STRIDE * VERSIZE)
#define VISION_RETRY_FRAME 2
#if HORSIZE != 3840 || VERSIZE != 720 || DEMO_STRIDE != 5760
#error Vision display requires 1280x720 BGR888 with 5760-byte stride
#endif
/* Readable via debugger even when no UART cable is attached. */
volatile unsigned int vision_frames_presented;
volatile unsigned int vision_last_count;
volatile unsigned int vision_last_processing_ms;

static unsigned int NowMs(void)
{
	XTime ticks;
	XTime_GetTime(&ticks);
	return (unsigned int)(ticks / (COUNTS_PER_SECOND / 1000U));
}

/* The observation window begins before arming DMA, including overlapped CPU work. */
static u32 camera_packets_before, camera_crc_before;
static int camera_window;
static const char *vision_failure = "startup";

static void CameraObserve(void)
{
	camera_packets_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x04);
	camera_crc_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x08);
	camera_window = 1;
}

static void VideoRegisters(const char *stage)
{
	unsigned int channel;
	xil_printf("VIDEO stage=%s committed=%u presented=%u BGR888 1280x720 hsize=%u stride=%u\r\n",
		stage, dispCtrl.curFrame, vision_frames_presented, HORSIZE, DEMO_STRIDE);
	for (channel = 0; channel < 2; ++channel) {
		UINTPTR base = channel ? XPAR_AXIVDMA_1_BASEADDR : XPAR_AXIVDMA_0_BASEADDR;
		u32 off = channel ? XAXIVDMA_RX_OFFSET : XAXIVDMA_TX_OFFSET;
		u32 addr = channel ? XAXIVDMA_S2MM_ADDR_OFFSET : XAXIVDMA_MM2S_ADDR_OFFSET;
		xil_printf("%s CR=%08x SR=%08x PARKPTR=%08x ADDR0=%08x VSIZE=%u HSIZE=%u STRIDE=%u\r\n",
			channel ? "S2MM" : "MM2S", Xil_In32(base + off + XAXIVDMA_CR_OFFSET),
			Xil_In32(base + off + XAXIVDMA_SR_OFFSET), Xil_In32(base + XAXIVDMA_PARKPTR_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_VSIZE_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_HSIZE_OFFSET),
			Xil_In32(base + addr + XAXIVDMA_STRD_FRMDLY_OFFSET) & XAXIVDMA_STRIDE_MASK);
	}
	xil_printf("DDR expected frame0=%08x frame1=%08x frame2=%08x; matched XCI enables parameter readback\r\n",
		(unsigned int)pFrames[0], (unsigned int)pFrames[1], (unsigned int)pFrames[2]);
}

/* Both VDMA instances in the matched XCI enable video parameter readback. */
static int VideoLayoutMatches(unsigned int capture)
{
	UINTPTR base = capture ? XPAR_AXIVDMA_1_BASEADDR : XPAR_AXIVDMA_0_BASEADDR;
	u32 addr = capture ? XAXIVDMA_S2MM_ADDR_OFFSET : XAXIVDMA_MM2S_ADDR_OFFSET;
	unsigned int i;
	if (Xil_In32(base + addr + XAXIVDMA_VSIZE_OFFSET) != VERSIZE ||
		Xil_In32(base + addr + XAXIVDMA_HSIZE_OFFSET) != HORSIZE ||
		(Xil_In32(base + addr + XAXIVDMA_STRD_FRMDLY_OFFSET) & XAXIVDMA_STRIDE_MASK) != DEMO_STRIDE)
		return XST_FAILURE;
	for (i = 0; i < DISPLAY_NUM_FRAMES; ++i) {
		UINTPTR expected = (UINTPTR)pFrames[capture ? 0 : i];
		if ((expected & 63U) ||
			Xil_In32(base + addr + XAXIVDMA_START_ADDR_OFFSET + i * XAXIVDMA_START_ADDR_LEN) != (u32)expected)
			return XST_FAILURE;
	}
	return XST_SUCCESS;
}

/* Frame 0 belongs only to S2MM; frames 1/2 alternate CPU and HDMI ownership. */
static int PresentFrame(unsigned int index)
{
	if (index == 0 || index >= DISPLAY_NUM_FRAMES || index == dispCtrl.curFrame)
		return XST_FAILURE;
	Xil_DCacheFlushRange((INTPTR)pFrames[index], VISION_FRAME_BYTES);
	return DisplayChangeFrame(&dispCtrl, index);
}

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

/* Never exit main or reuse uncertain buffers. Retry the previous park; if the
 * read channel faulted, reset only MM2S and restart that same retained image. */
static void DiagnosticHold(const char *reason)
{
	(void)vdma_write_reset(XPAR_AXIVDMA_1_DEVICE_ID);
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

static int VisionRunOnce(void)
{
	VisionDetection detections[VISION_MAX_DETECTIONS];
	unsigned int next = dispCtrl.curFrame == 1 ? 2 : 1;
	u8 *frame = pFrames[next];
	unsigned int started = NowMs();
	static unsigned int last_log;
	int count;
	int i;

	/* Called only after a frame-complete interrupt AND hardware HALTED.
	 * The capture buffer is read-only to CPU, and never displayed. */
	Xil_DCacheInvalidateRange((INTPTR)pFrames[0], VISION_FRAME_BYTES);
	if (!CaptureHasPixels(pFrames[0])) {
		vision_failure = "capture all-zero (dark/invalid); retaining image";
		return VISION_RETRY_FRAME;
	}
	for (i = 0; i < VERSIZE; ++i)
		memcpy(frame + i * DEMO_STRIDE, pFrames[0] + i * DEMO_STRIDE, HORSIZE);
	/* Overlap next capture with CPU analysis; it cannot overwrite frame. */
	CameraObserve();
	if (vdma_capture_next() != XST_SUCCESS) {
		vision_failure = "capture rearm";
		return XST_FAILURE;
	}
	count = vision_detect_bgr888(frame, 1280, VERSIZE, DEMO_STRIDE,
		detections, VISION_MAX_DETECTIONS);
	if (count < 0) {
		vision_failure = "vision detect";
		xil_printf("VISION error=%d\r\n", count);
		return XST_FAILURE;
	}
	vision_last_count = (unsigned int)count;
	vision_last_processing_ms = NowMs() - started;
	vision_overlay(frame, 1280, VERSIZE, DEMO_STRIDE, detections, count,
		vision_last_processing_ms);
	if (PresentFrame(next) != XST_SUCCESS) {
		vision_failure = "present frame";
		return XST_FAILURE;
	}
	++vision_frames_presented;
	if (vision_frames_presented == 1) VideoRegisters("FIRST_CAMERA_FRAME_COMMITTED");
	/* UART is diagnostic, not a per-frame bottleneck. */
	if (NowMs() - last_log < 1000U) return XST_SUCCESS;
	last_log = NowMs();
	xil_printf("VISION detections=%d sample_step=%d\r\n",
		count, VISION_SAMPLE_STEP);
	for (i = 0; i < count; ++i) {
		const VisionDetection *d = &detections[i];
		xil_printf("VISION %s cx=%d cy=%d bbox=%d,%d,%d,%d angle=%d confidence=%d area=%u\r\n",
			vision_type_name(d->type), d->center_x, d->center_y,
			d->bbox_x, d->bbox_y, d->bbox_w, d->bbox_h,
			d->angle_deg, d->confidence_percent, d->sampled_area);
	}
	return XST_SUCCESS;
}

/* Count fresh packets and completed writes, not just a readable sensor ID. */
static int CameraCheck(int verbose)
{
	u32 packets_before, packets_after, crc_before, crc_after, status;
	int healthy;
	unsigned int started = NowMs();
	packets_before = camera_packets_before;
	crc_before = camera_crc_before;
	do {
		status = Xil_In32(CAMERA_S2MM_STATUS);
		if (status & XAXIVDMA_SR_ERR_ALL_MASK) break;
		if ((status & (XAXIVDMA_IXR_FRMCNT_MASK | XAXIVDMA_SR_HALTED_MASK)) ==
			(XAXIVDMA_IXR_FRMCNT_MASK | XAXIVDMA_SR_HALTED_MASK)) break;
		usleep(1000);
	} while (NowMs() - started < 2000U);
	packets_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x04);
	crc_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR + 0x08);
	status = Xil_In32(CAMERA_S2MM_STATUS);
	/* Unsigned subtraction permits wrap; windows must contain < 2^32 events. */
	healthy = camera_window && (u32)(packets_after - packets_before) != 0 &&
		(u32)(crc_after - crc_before) == 0 &&
		(status & XAXIVDMA_IXR_FRMCNT_MASK) &&
		(status & XAXIVDMA_SR_HALTED_MASK) &&
		!(status & XAXIVDMA_SR_ERR_ALL_MASK);
	camera_window = 0; /* A completed frame is consumed exactly once. */
	if (verbose || !healthy) {
		xil_printf("CSI long packets: %u -> %u, CRC errors: %u -> %u\r\n",
			packets_before, packets_after, crc_before, crc_after);
		xil_printf("Camera VDMA S2MM status: 0x%08x, frame completed: %u\r\n",
			status, (status & XAXIVDMA_IXR_FRMCNT_MASK) != 0);
	}
	return healthy ? XST_SUCCESS : XST_FAILURE;
}

static int CameraStart(void)
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
		CameraObserve();
		status = vdma_write_init(XPAR_AXIVDMA_1_DEVICE_ID, HORSIZE, VERSIZE,
			DEMO_STRIDE, (unsigned int)pFrames[0]);
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
		if (CameraCheck(1) == XST_SUCCESS) {
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

int main()
{



	int Status;
	XAxiVdma_Config *vdmaConfig;
	int i;

	xil_printf("color_test camera diagnostic start\r\n");
	xil_printf("Camera recovery: RAW10 single-frame capture\r\n");
	xil_printf("Vision PS v2: complete frames, HDMI overlay, frame-driven processing\r\n");
	xil_printf("ISP: effective RGGB, gamma 1/1.8, WB 1.5/1/1.5, highlight disabled in matched PL\r\n");
	xil_printf("Focus: mechanically adjust the lens if this is a fixed-focus module\r\n");

	/*
	 * Initialize an array of pointers to the 3 frame buffers
	 */
	for (i = 0; i < DISPLAY_NUM_FRAMES; i++)
	{
		pFrames[i] = frameBuf[i];
		memset(pFrames[i], 0, DEMO_MAX_FRAME);
		Xil_DCacheFlushRange((INTPTR) pFrames[i], DEMO_MAX_FRAME) ;
	}

	Xil_Out32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR, CAMERA_GAMMA_FACTOR_1_8);
	/* AXI_GammaCorrection's AXI-Lite read data is hard-wired to zero. */
	xil_printf("Gamma configured: 1/1.8 (write-only AXI-Lite selector)\r\n");
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
	VideoRegisters("BARS_ACTIVE");
	for (i = 0; i < 5; ++i) {
		xil_printf("VIDEO BARS_ONLY second=%d; camera not started\r\n", i + 1);
		usleep(1000000);
	}
	if (PsGpioSetup() != XST_SUCCESS) DiagnosticHold("camera GPIO init");
	Status = CameraStart();
	/* CameraStart already validated its first frame; do not consume it twice. */
	for (;;) {
		if (Xil_In32(XPAR_AXIVDMA_0_BASEADDR + XAXIVDMA_SR_OFFSET) &
			(XAXIVDMA_SR_ERR_ALL_MASK | XAXIVDMA_SR_HALTED_MASK))
			DiagnosticHold("MM2S runtime error");
		if (Status != XST_SUCCESS) {
			VideoRegisters("CAPTURE_FAILED_RETAINING_IMAGE");
			usleep(1000000);
			Status = CameraStart();
			continue;
		}
		Status = VisionRunOnce();
		if (Status == VISION_RETRY_FRAME) {
			xil_printf("VIDEO %s; retrying capture\r\n", vision_failure);
			usleep(1000000);
			CameraObserve();
			if (vdma_capture_next() != XST_SUCCESS) DiagnosticHold("capture rearm after zero frame");
		} else if (Status != XST_SUCCESS) {
			DiagnosticHold(vision_failure);
		}
		Status = CameraCheck(0);
	}
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
