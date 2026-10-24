#ifndef GAME_LINUX_CAPTURE_H
#define GAME_LINUX_CAPTURE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Capture-only adapter for the EXISTING native noncached xlnk allocator.
 * One allocation, three disjoint 1280x720 stores, existing capture S2MM.
 * No constructor, DMA programming, sensor, clock/reset or display start here.
 * The Python VDMA owner must use hardware one-shot mode. No automatic free.
 * prepare:0=owned,-1=clean rejection,-2=resources retained. release/sync
 * inspect actual S2MM RS/HALTED/errors; caller assertions cannot grant access.
 * Keep this owner/library/process alive if release cannot confirm ownership. */
int game_capture_owner_prepare(uint64_t *virtual_address,uint64_t *physical_address);
int game_capture_owner_sync(unsigned slot);
int game_capture_owner_release(void);
int game_capture_owner_can_exit(void);
/* ABI adapter only: the canonical C detector and scene encoder own semantics.
 * Input is a CPU-owned, tightly packed BGR888 copy of a stopped full frame. */
int game_capture_detect_bgr(const uint8_t *bgr,uint32_t sequence,uint32_t capture_ms,
                            char *line,unsigned capacity);
int game_capture_detect_owned(uint32_t sequence,uint32_t capture_ms,char *line,
                              unsigned capacity,uint32_t *copy_ms,uint32_t *detect_ms);
#ifdef __cplusplus
}
#endif
#endif
