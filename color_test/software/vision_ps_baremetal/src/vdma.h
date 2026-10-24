
#ifndef VDMA_H_
#define VDMA_H_

#include "xaxivdma.h"


#define VDMA_CAPTURE_FRAME_COUNT 3U

int vdma_read_init(short DeviceID,short HoriSizeInput,short VertSizeInput,short Stride,unsigned int FrameStoreStartAddr);
int vdma_write_init(short DeviceID, short HoriSizeInput, short VertSizeInput,
	short Stride, const UINTPTR FrameStoreStartAddr[VDMA_CAPTURE_FRAME_COUNT]);
int vdma_write_reset(short DeviceID);
int vdma_capture_ready(unsigned int *FrameIndex);
int vdma_capture_current(unsigned int *FrameIndex);
u32 vdma_version();

#endif /* VDMA_H_ */
