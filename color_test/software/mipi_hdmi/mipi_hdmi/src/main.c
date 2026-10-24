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
#define CAMERA_RX_CONTROL_OFFSET 0x00U
#define CAMERA_RX_PACKET_OFFSET 0x04U
#define CAMERA_RX_CRC_OFFSET 0x08U
#define CAMERA_RX_VERSION_OFFSET 0x0cU
#define CAMERA_RX_CONTROL_RESET 0x00000001U
#define CAMERA_RX_CONTROL_ENABLE 0x00000002U
#define CAMERA_CSI_FIFO_OVERFLOW 0x80000000U

static void CameraReceiverStatus(const char *phase)
{
	UINTPTR csi = XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR;
	UINTPTR dphy = XPAR_MIPI_D_PHY_RX_0_S_AXI_LITE_BASEADDR;
	u32 csi_control = Xil_In32(csi + CAMERA_RX_CONTROL_OFFSET);
	u32 dphy_control = Xil_In32(dphy + CAMERA_RX_CONTROL_OFFSET);

	xil_printf("%s CSI_RX control=0x%08x enable=%u reset=%u fifo_overflow=%u version=0x%08x long_packets=%u crc_errors=%u\r\n",
		phase, csi_control,
		(csi_control & CAMERA_RX_CONTROL_ENABLE) != 0,
		(csi_control & CAMERA_RX_CONTROL_RESET) != 0,
		(csi_control & CAMERA_CSI_FIFO_OVERFLOW) != 0,
		Xil_In32(csi + CAMERA_RX_VERSION_OFFSET),
		Xil_In32(csi + CAMERA_RX_PACKET_OFFSET),
		Xil_In32(csi + CAMERA_RX_CRC_OFFSET));
	xil_printf("%s DPHY_RX control=0x%08x enable=%u reset=%u version=0x%08x HS/stop/lane_status=unavailable\r\n",
		phase, dphy_control,
		(dphy_control & CAMERA_RX_CONTROL_ENABLE) != 0,
		(dphy_control & CAMERA_RX_CONTROL_RESET) != 0,
		Xil_In32(dphy + CAMERA_RX_VERSION_OFFSET));
}

/* Both Digilent receiver IPs implement bit 0 reset and bit 1 enable in their
 * real AXI-Lite control register.  Hold both cores reset while the sensor is
 * reset/configured, then release D-PHY before the CSI packet decoder. */
static int CameraReceiverHoldReset(void)
{
	UINTPTR csi = XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR;
	UINTPTR dphy = XPAR_MIPI_D_PHY_RX_0_S_AXI_LITE_BASEADDR;
	u32 asserted = CAMERA_RX_CONTROL_ENABLE | CAMERA_RX_CONTROL_RESET;

	Xil_Out32(csi + CAMERA_RX_CONTROL_OFFSET, asserted);
	Xil_Out32(dphy + CAMERA_RX_CONTROL_OFFSET, asserted);
	usleep(1000);
	if ((Xil_In32(csi + CAMERA_RX_CONTROL_OFFSET) & 0x3U) != asserted ||
		(Xil_In32(dphy + CAMERA_RX_CONTROL_OFFSET) & 0x3U) != asserted) {
		CameraReceiverStatus("RESET_ASSERT_FAILED");
		return XST_FAILURE;
	}
	return XST_SUCCESS;
}

static int CameraReceiverEnable(void)
{
	UINTPTR csi = XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR;
	UINTPTR dphy = XPAR_MIPI_D_PHY_RX_0_S_AXI_LITE_BASEADDR;

	Xil_Out32(dphy + CAMERA_RX_CONTROL_OFFSET, CAMERA_RX_CONTROL_ENABLE);
	usleep(1000); /* also exceeds the D-PHY IDELAYCTRL reset requirement */
	Xil_Out32(csi + CAMERA_RX_CONTROL_OFFSET, CAMERA_RX_CONTROL_ENABLE);
	usleep(1000);
	if ((Xil_In32(csi + CAMERA_RX_CONTROL_OFFSET) & 0x3U) != CAMERA_RX_CONTROL_ENABLE ||
		(Xil_In32(dphy + CAMERA_RX_CONTROL_OFFSET) & 0x3U) != CAMERA_RX_CONTROL_ENABLE) {
		CameraReceiverStatus("RESET_RELEASE_FAILED");
		return XST_FAILURE;
	}
	CameraReceiverStatus("RECEIVER_READY");
	return XST_SUCCESS;
}

/* Count fresh packets and completed writes, not just a readable sensor ID. */
static int CameraCheck(int verbose)
{
	u32 packets_before, packets_after, crc_before, crc_after, status, csi_control;
	u32 packet_delta, crc_delta;
	int healthy;
	Xil_Out32(CAMERA_S2MM_STATUS, XAXIVDMA_IXR_FRMCNT_MASK);
	packets_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CAMERA_RX_PACKET_OFFSET);
	crc_before = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CAMERA_RX_CRC_OFFSET);
	xil_printf("STAGE 4: WAITING FOR CSI PACKETS\r\n");
	usleep(2000000);
	packets_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CAMERA_RX_PACKET_OFFSET);
	crc_after = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CAMERA_RX_CRC_OFFSET);
	csi_control = Xil_In32(XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR +
		CAMERA_RX_CONTROL_OFFSET);
	status = Xil_In32(CAMERA_S2MM_STATUS);
	packet_delta = packets_after - packets_before;
	crc_delta = crc_after - crc_before;
	healthy = packet_delta != 0 && crc_delta == 0 &&
		(status & XAXIVDMA_IXR_FRMCNT_MASK) &&
		!(status & (XAXIVDMA_SR_HALTED_MASK | XAXIVDMA_SR_ERR_ALL_MASK)) &&
		!(csi_control & CAMERA_CSI_FIFO_OVERFLOW);
	if (verbose || !healthy) {
		xil_printf("CSI long packets: %u -> %u, CRC errors: %u -> %u\r\n",
			packets_before, packets_after, crc_before, crc_after);
		xil_printf("Camera VDMA S2MM status: 0x%08x, frame completed: %u, CSI overflow: %u\r\n",
			status, (status & XAXIVDMA_IXR_FRMCNT_MASK) != 0,
			(csi_control & CAMERA_CSI_FIFO_OVERFLOW) != 0);
		CameraReceiverStatus("HEALTH");
		if (packet_delta == 0)
			xil_printf("HEALTH BOUNDARY: no CSI long packets; OV5640 MIPI TX / physical link / D-PHY HS / CSI decode remain indistinguishable because this D-PHY IP exposes no HS status register\r\n");
		else if (crc_delta != 0)
			xil_printf("HEALTH BOUNDARY: CSI packets arrived with CRC errors; inspect MIPI signal integrity and lane decode\r\n");
		else if (!(status & XAXIVDMA_IXR_FRMCNT_MASK))
			xil_printf("HEALTH BOUNDARY: CSI packets arrived but VDMA completed no frame; inspect AXI video framing and S2MM\r\n");
		else if (csi_control & CAMERA_CSI_FIFO_OVERFLOW)
			xil_printf("HEALTH BOUNDARY: CSI receive FIFO overflow; inspect AXI backpressure and downstream readiness\r\n");
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
		if (CameraReceiverHoldReset() != XST_SUCCESS) {
			xil_printf("Receiver reset assertion failed\r\n");
			continue;
		}
		DemoPrintTest(dispCtrl.framePtr[dispCtrl.curFrame], dispCtrl.vMode.width,
			dispCtrl.vMode.height, DEMO_STRIDE, 0);
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
		xil_printf("STAGE 2: OV5640 STREAM CONFIG OK\r\n");
		status = CameraReceiverEnable();
		if (status != XST_SUCCESS) {
			xil_printf("Receiver reset release/enable failed\r\n");
			continue;
		}
		xil_printf("STAGE 3: D-PHY/CSI RX RESET OK\r\n");
		status = vdma_write_init(XPAR_AXIVDMA_1_DEVICE_ID, HORSIZE, VERSIZE,
			DEMO_STRIDE, (unsigned int)dispCtrl.framePtr[dispCtrl.curFrame]);
		if (status != XST_SUCCESS) {
			xil_printf("Camera VDMA initialization failed: %d\r\n", status);
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
	status = vdma_write_reset(XPAR_AXIVDMA_1_DEVICE_ID);
	if (status == XST_SUCCESS) {
		(void)CameraReceiverHoldReset();
		XGpioPs_WritePin(&Gpio, 54, 0);
		DemoPrintTest(dispCtrl.framePtr[dispCtrl.curFrame], dispCtrl.vMode.width,
			dispCtrl.vMode.height, DEMO_STRIDE, 0);
		xil_printf("FALLBACK COLOR BARS buffer=0x%08x active=%ux%u stride=%u MM2S_status=0x%08x\r\n",
			(u32)dispCtrl.framePtr[dispCtrl.curFrame], dispCtrl.vMode.width,
			dispCtrl.vMode.height, DEMO_STRIDE,
			Xil_In32(XPAR_AXIVDMA_0_BASEADDR + XAXIVDMA_TX_OFFSET +
				XAXIVDMA_SR_OFFSET));
	} else {
		xil_printf("FALLBACK COLOR BARS NOT DRAWN: capture VDMA reset failed: %d\r\n",
			status);
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
	xil_printf("Camera recovery v2: matched BGGR RAW ISP and artifact checks\r\n");
	xil_printf("ISP: BGGR demosaic, gamma 1/1.8, RGB white balance R/G/B=1.5/1.0/1.5\r\n");
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

	Status = PsGpioSetup();
	if (Status != XST_SUCCESS) {
		xil_printf("Camera GPIO initialization failed\r\n");
		return Status;
	}
	Xil_Out32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR, CAMERA_GAMMA_FACTOR_1_8);
	/* AXI_GammaCorrection's AXI-Lite read data is hard-wired to zero. */
	xil_printf("Gamma configured: 1/1.8 (write-only AXI-Lite selector)\r\n");
	/*
	 * Initialize VDMA driver
	 */
	vdmaConfig = XAxiVdma_LookupConfig(VGA_VDMA_ID);
	if (!vdmaConfig)
	{
		xil_printf("No video DMA found for ID %d\r\n", VGA_VDMA_ID);
		return XST_FAILURE;

	}
	Status = XAxiVdma_CfgInitialize(&vdma, vdmaConfig, vdmaConfig->BaseAddress);
	if (Status != XST_SUCCESS)
	{
		xil_printf("VDMA Configuration Initialization failed %d\r\n", Status);
		return XST_FAILURE;

	}

	/*
	 * Initialize the Display controller and start it
	 */
	Status = DisplayInitialize(&dispCtrl, &vdma, DISP_VTC_ID, DYNCLK_BASEADDR,pFrames, DEMO_STRIDE);
	if (Status != XST_SUCCESS)
	{
		xil_printf("Display Ctrl initialization failed during demo initialization%d\r\n", Status);
		return XST_FAILURE;

	}
	DemoPrintTest(dispCtrl.framePtr[dispCtrl.curFrame], dispCtrl.vMode.width,
		dispCtrl.vMode.height, DEMO_STRIDE, 0);
	Status = DisplayStart(&dispCtrl);
	if (Status != XST_SUCCESS)
	{
		xil_printf("Couldn't start display during demo initialization%d\r\n", Status);
		return XST_FAILURE;

	}
	xil_printf("HDMI color bars for 5 seconds\r\n");
	usleep(5000000);


	Status = CameraStart();
	if (Status != XST_SUCCESS) return Status;
	/* Monitor continuously; each recovery has at most three start attempts. */
	while (1) {
		if (CameraCheck(0) != XST_SUCCESS) {
			xil_printf("Camera stream stalled or errored; restarting capture\r\n");
			Status = CameraStart();
			if (Status != XST_SUCCESS) return Status;
		}
	}

	return 0;
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
