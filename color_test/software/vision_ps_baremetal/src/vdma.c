#include "xil_printf.h"
#include "vdma.h"
#include "sleep.h"
#include "xaxivdma_hw.h"
#include "xparameters.h"
#include "xil_io.h"

static int vdma_capture_index(unsigned int *FrameIndex)
{
	UINTPTR base = XPAR_AXIVDMA_1_BASEADDR;
	u32 park;
	unsigned int current;
	if (FrameIndex == NULL) return XST_FAILURE;
	park = Xil_In32(base + XAXIVDMA_PARKPTR_OFFSET);
	current = (park & XAXIVDMA_PARKPTR_WRTSTR_MASK) >> XAXIVDMA_WRTSTR_SHIFT;
	if (current >= VDMA_CAPTURE_FRAME_COUNT) return XST_FAILURE;
	*FrameIndex = current;
	return XST_SUCCESS;
}

int vdma_capture_current(unsigned int *FrameIndex)
{
	return vdma_capture_index(FrameIndex);
}

int vdma_capture_ready(unsigned int *FrameIndex)
{
	UINTPTR base = XPAR_AXIVDMA_1_BASEADDR;
	u32 status = Xil_In32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET);
	unsigned int current;
	if ((status & (XAXIVDMA_SR_HALTED_MASK | XAXIVDMA_SR_ERR_ALL_MASK)) ||
	    !(status & XAXIVDMA_IXR_FRMCNT_MASK) ||
	    vdma_capture_index(&current) != XST_SUCCESS) return XST_FAILURE;
	/* The current store is being written. The preceding store is the newest
	 * complete frame and remains untouched for at least one more frame. */
	*FrameIndex = (current + VDMA_CAPTURE_FRAME_COUNT - 1U) %
		VDMA_CAPTURE_FRAME_COUNT;
	Xil_Out32(base + XAXIVDMA_RX_OFFSET + XAXIVDMA_SR_OFFSET,
		XAXIVDMA_IXR_FRMCNT_MASK);
	return XST_SUCCESS;
}

/* Reset only capture, leaving the HDMI read channel running. */
int vdma_write_reset(short DeviceID)
{
	XAxiVdma_Config *Config = XAxiVdma_LookupConfig(DeviceID);
	u32 timeout;
	UINTPTR control;
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


int vdma_write_init(short DeviceID, short HoriSizeInput, short VertSizeInput,
	short Stride, const UINTPTR FrameStoreStartAddr[VDMA_CAPTURE_FRAME_COUNT])
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



	if (FrameStoreStartAddr == NULL) return XST_FAILURE;
	/* The CSI source cannot honor downstream backpressure. Keep S2MM running
	 * continuously and rotate through three capture stores. */
	WriteCfg.EnableCircularBuf = 1;
	WriteCfg.EnableFrameCounter = 0;
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


	{
		unsigned int i;
		for (i = 0; i < VDMA_CAPTURE_FRAME_COUNT; ++i)
			WriteCfg.FrameStoreStartAddr[i] = FrameStoreStartAddr[i];
	}

	Status = XAxiVdma_DmaSetBufferAddr(&Vdma, XAXIVDMA_WRITE, WriteCfg.FrameStoreStartAddr);
	if (Status != XST_SUCCESS) {
			xdbg_printf(XDBG_DEBUG_ERROR,"Write channel set buffer address failed %d\r\n", Status);
			return XST_FAILURE;
	}


	/* Latch a completion indication after every frame without stopping S2MM. */
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
	return XST_SUCCESS;

}
