#ifndef GAME_LINUX_CAPTURE_H
#define GAME_LINUX_CAPTURE_H
#include <stdint.h>
#include "game_linux_display.h"
#include "game_scene_adapter.h"
#define GAME_CAPTURE_FRAME_SPAN (5760U * 720U)
#ifdef __cplusplus
extern "C" {
#endif
/* Capture-only adapter for the EXISTING native noncached xlnk allocator.
 * One allocation, three disjoint 1280x720 stores, existing capture S2MM.
 * No constructor, DMA programming, sensor, clock/reset or display start here.
 * Stopped-frame APIs require hardware halt. The live parked-frame API requires
 * a two-fresh-start retirement fence from the single Python coordinator and
 * verifies that DMA stays on a different store during the copy. No automatic free.
 * prepare:0=owned,-1=clean rejection,-2=resources retained. release/sync
 * inspect actual S2MM RS/HALTED/errors; caller assertions cannot grant access.
 * Keep this owner/library/process alive if release cannot confirm ownership. */
int game_capture_owner_prepare(uint64_t *virtual_address,uint64_t *physical_address);
/* Same owner/copy contract, using a role platform from a shared live session.
 * The caller must keep the session alive until this owner is released. */
int game_capture_owner_prepare_with_platform(const GameDisplayPlatform *platform,
                                             uint64_t *virtual_address,
                                             uint64_t *physical_address);
int game_capture_owner_sync(unsigned slot);
int game_capture_owner_release(void);
int game_capture_owner_can_exit(void);
/* ABI adapter only: the canonical C detector and scene encoder own semantics.
 * Input is a CPU-owned, tightly packed BGR888 copy of a stopped full frame. */
int game_capture_detect_bgr(const uint8_t *bgr,uint32_t sequence,uint32_t capture_ms,
                            char *line,unsigned capacity);
int game_capture_detect_owned(uint32_t sequence,uint32_t capture_ms,char *line,
                              unsigned capacity,uint32_t *copy_ms,uint32_t *detect_ms);
typedef int (*GameCaptureFrameCallback)(void *context, GameDetectionFrame *frame);
/* Borrowed, read-only BGR888 pixels from the independent CPU copy, NEVER the
 * capture allocation. The view and detections share exactly one original stamp.
 * Both pointers expire when the synchronous callback returns: copy or render
 * there, do not retain/reenter the owner. No DMA access is granted by this type. */
typedef struct {
    const uint8_t *data;
    unsigned width, height;
    size_t stride, capacity;
    GameCaptureStamp stamp;
} GameCaptureImageView;
typedef int (*GameCaptureImageCallback)(void *context,
    const GameDetectionFrame *frame, const GameCaptureImageView *image);
/* CPU-to-CPU snapshot copy. Destination must be separately CPU-owned; it may
 * have row padding, which is left untouched. Reject overlap/truncated spans.
 * This does not establish DMA ownership or freshness; preserve image.stamp
 * alongside the copied pixels and match it to the accepted game snapshot. */
int game_capture_image_copy(const GameCaptureImageView *image,
                            VisionCanvas *destination);
/* Copy one already-stopped full frame, run the canonical detector, and invoke
 * the callback synchronously while detections and the original stamp remain
 * valid. The callback must submit before returning; no result is queued. */
int game_capture_owner_dispatch(uint64_t generation,uint64_t sequence,
                                uint64_t captured_ms,GameCaptureFrameCallback callback,
                                void *context,uint32_t *copy_ms,uint32_t *detect_ms);
typedef struct {
    uint32_t control,status,park,vsize,hsize,stride,addresses[3];
} GameCaptureDmaState;
/* Actual register snapshot validation, also usable by host fault regressions.
 * This is an exclusion check, not a substitute for the retirement fence. */
int game_capture_parked_slot_valid(const GameCaptureDmaState *state,uint64_t physical,
                                   unsigned slot,unsigned writer);
/* Worker pins slot after requested/current writer agree and TWO fresh START
 * events. It must not change writer until FRAME_DONE. Recheck actual control,
 * errors, park and full layout before AND after copying this excluded store.
 * Detector/callback then use only the independent CPU copy. Release still
 * requires the entire S2MM channel to be HALTED, never this park proof. */
int game_capture_owner_dispatch_parked(unsigned slot,unsigned writer,
                                      uint64_t generation,uint64_t sequence,
                                      uint64_t captured_ms,GameCaptureFrameCallback callback,
                                      void *context,uint32_t *copy_ms,uint32_t *detect_ms);
/* Same parked-store checks and single detector invocation as the legacy API.
 * The image callback is synchronous and receives the 1280x720, stride3840,
 * capacity2764800 CPU copy only AFTER both DMA exclusion/layout checks pass.
 * Caller sends FRAME_DONE only after success, as for the existing dispatch.
 * No extra allocation, device owner, timestamp update or DMA write is added. */
int game_capture_owner_dispatch_image_parked(unsigned slot,unsigned writer,
                                      uint64_t generation,uint64_t sequence,
                                      uint64_t captured_ms,GameCaptureImageCallback callback,
                                      void *context,uint32_t *copy_ms,uint32_t *detect_ms);
#ifdef __cplusplus
}
#endif
#endif
