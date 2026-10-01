#include "xil_printf.h"
#include "vdma.h"
#include "sleep.h"
#include "xaxivdma_hw.h"
#include "xparameters.h"
#include "xil_io.h"

/* Video parameter readback is optional; retain the configured height. */
static u32 capture_vsize;

int vdma_capture_next(void)
{
	UINTPTR base = XPAR_AXIVDMA_1_BASEADDR;
	u32 status = Xil_In32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET);
	u32 control;
	if (!capture_vsize || !(status & XAXIVDMA_SR_HALTED_MASK) ||
	    (status & XAXIVDMA_SR_ERR_ALL_MASK)) return XST_FAILURE;
	Xil_Out32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET,
		XAXIVDMA_IXR_FRMCNT_MASK);
	control = Xil_In32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_CR_OFFSET);
	control = (control & ~XAXIVDMA_FRMCNT_MASK) |
		(1U << XAXIVDMA_FRMCNT_SHIFT) | XAXIVDMA_CR_FRMCNT_EN_MASK |
		XAXIVDMA_CR_RUNSTOP_MASK;
	Xil_Out32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_CR_OFFSET, control);
	/* VSIZE write commits/restarts the already configured transfer. */
	Xil_Out32(base + XAXIVDMA_S2MM_ADDR_OFFSET + XAXIVDMA_VSIZE_OFFSET,
		capture_vsize);
	return XST_SUCCESS;
}

/* Reset only capture, leaving the HDMI read channel running. */
int vdma_write_reset(short DeviceID)
{
	XAxiVdma_Config *Config = XAxiVdma_LookupConfig(DeviceID);
	u32 timeout;
	UINTPTR control;
	capture_vsize = 0;
	if (Config == NULL) return XST_FAILURE;
	control = Config->BaseAddress + XAXIVDMA_RX_OFFSET + XAXIVDMA_CR_OFFSET;
	Xil_Out32(control, Xil_In32(control) | XAXIVDMA_CR_RESET_MASK);
	for (timeout = 0; timeout < 1000; ++timeout) {
		if (!(Xil_In32(control) & XAXIVDMA_CR_RESET_MASK)) return XST_SUCCESS;
		usleep(1000);
	}
	xil_printf("Camera VDMA reset timed out: CR=0x%08x\r\n", Xil_In32(control));
	return XST_FAILURE;
}

u32 vdma_version(XAxiVdma *Vdma) {
	return XAxiVdma_GetVersion(Vdma);
}

int vdma_read_start(XAxiVdma *Vdma) {
	int Status;

	// MM2S Startup
	Status = XAxiVdma_DmaStart(Vdma, XAXIVDMA_READ);
	if (Status != XST_SUCCESS)
	{
	   xil_printf("Start read transfer failed %d\n\r", Status);
	   return XST_FAILURE;
	}

	return XST_SUCCESS;
}


int vdma_read_stop(XAxiVdma *Vdma) {
	XAxiVdma_DmaStop(Vdma, XAXIVDMA_READ);
	return XST_SUCCESS;
}


int vdma_read_init(short DeviceID,short HoriSizeInput,short VertSizeInput,short Stride,unsigned int FrameStoreStartAddr)
{
	XAxiVdma Vdma;
	XAxiVdma_Config *Config;
	XAxiVdma_DmaSetup ReadCfg;
	int Status;


	Config = XAxiVdma_LookupConfig(DeviceID);
	if (NULL == Config) {
		xil_printf("XAxiVdma_LookupConfig failure\r\n");
		return XST_FAILURE;
	}

	Status = XAxiVdma_CfgInitialize(&Vdma, Config, Config->BaseAddress);
	if (Status != XST_SUCCESS) {
		xil_printf("XAxiVdma_CfgInitialize failure\r\n");
		return XST_FAILURE;
	}



	ReadCfg.EnableCircularBuf = 1;
	ReadCfg.EnableFrameCounter = 0;
	ReadCfg.FixedFrameStoreAddr = 0;

	ReadCfg.EnableSync = 1;
	ReadCfg.PointNum = 1;

	ReadCfg.FrameDelay = 0;

	ReadCfg.VertSizeInput = VertSizeInput;
	ReadCfg.HoriSizeInput = HoriSizeInput;
	ReadCfg.Stride = Stride;

	Status = XAxiVdma_DmaConfig(&Vdma, XAXIVDMA_READ, &ReadCfg);
	if (Status != XST_SUCCESS) {
			xdbg_printf(XDBG_DEBUG_ERROR,
				"Read channel config failed %d\r\n", Status);

			return XST_FAILURE;
	}


	ReadCfg.FrameStoreStartAddr[0] = FrameStoreStartAddr;

	Status = XAxiVdma_DmaSetBufferAddr(&Vdma, XAXIVDMA_READ, ReadCfg.FrameStoreStartAddr);
	if (Status != XST_SUCCESS) {
			xdbg_printf(XDBG_DEBUG_ERROR,"Read channel set buffer address failed %d\r\n", Status);
			return XST_FAILURE;
	}


	Status = vdma_read_start(&Vdma);
	if (Status != XST_SUCCESS) {
		   xil_printf("error starting VDMA..!");
		   return Status;
	}
	return XST_SUCCESS;

}


int vdma_write_start(XAxiVdma *Vdma) {
	int Status;

	// MM2S Startup
	Status = XAxiVdma_DmaStart(Vdma, XAXIVDMA_WRITE);
	if (Status != XST_SUCCESS)
	{
	   xil_printf("Start write transfer failed %d\n\r", Status);
	   return XST_FAILURE;
	}

	return XST_SUCCESS;
}


int vdma_write_stop(XAxiVdma *Vdma) {
	XAxiVdma_DmaStop(Vdma, XAXIVDMA_WRITE);
	return XST_SUCCESS;
}


int vdma_write_init(short DeviceID,short HoriSizeInput,short VertSizeInput,short Stride,unsigned int FrameStoreStartAddr)
{
	XAxiVdma Vdma;
	XAxiVdma_Config *Config;
	XAxiVdma_DmaSetup WriteCfg = {0};
	int Status;


	Config = XAxiVdma_LookupConfig(DeviceID);
	if (NULL == Config) {
		xil_printf("XAxiVdma_LookupConfig failure\r\n");
		return XST_FAILURE;
	}

	Status = XAxiVdma_CfgInitialize(&Vdma, Config, Config->BaseAddress);
	if (Status != XST_SUCCESS) {
		xil_printf("XAxiVdma_CfgInitialize failure\r\n");
		return XST_FAILURE;
	}



	WriteCfg.EnableCircularBuf = 0;
	/* Stop in hardware after one whole frame, before CPU access. */
	WriteCfg.EnableFrameCounter = 1;
	WriteCfg.FixedFrameStoreAddr = 0;

	WriteCfg.EnableSync = 0;
	WriteCfg.PointNum = 1;

	WriteCfg.FrameDelay = 0;

	WriteCfg.VertSizeInput = VertSizeInput;
	WriteCfg.HoriSizeInput = HoriSizeInput;
	WriteCfg.Stride = Stride;

	Status = XAxiVdma_DmaConfig(&Vdma, XAXIVDMA_WRITE, &WriteCfg);
	if (Status != XST_SUCCESS) {
			xdbg_printf(XDBG_DEBUG_ERROR,
				"Read channel config failed %d\r\n", Status);

			return XST_FAILURE;
	}


	/* The driver reads every hardware frame-store entry, even in park mode. */
	{
		unsigned int i;
		for (i = 0; i < sizeof(WriteCfg.FrameStoreStartAddr) /
			sizeof(WriteCfg.FrameStoreStartAddr[0]); ++i)
			WriteCfg.FrameStoreStartAddr[i] = FrameStoreStartAddr;
	}

	Status = XAxiVdma_DmaSetBufferAddr(&Vdma, XAXIVDMA_WRITE, WriteCfg.FrameStoreStartAddr);
	if (Status != XST_SUCCESS) {
			xdbg_printf(XDBG_DEBUG_ERROR,"Write channel set buffer address failed %d\r\n", Status);
			return XST_FAILURE;
	}


	/* Poll frame-completion status with a threshold of one frame. */
	{
		UINTPTR control = Config->BaseAddress + XAXIVDMA_RX_OFFSET + XAXIVDMA_CR_OFFSET;
		u32 value = Xil_In32(control);
		value = (value & ~XAXIVDMA_FRMCNT_MASK) | (1U << XAXIVDMA_FRMCNT_SHIFT);
		Xil_Out32(control, value);
	}
	Status = vdma_write_start(&Vdma);
	if (Status != XST_SUCCESS) {
		   xil_printf("error starting VDMA..!");
		   return Status;
	}
	capture_vsize = (u32)VertSizeInput;
	return XST_SUCCESS;

}
