#ifndef VISION_PERF_H
#define VISION_PERF_H
#include "vision_ps_config.h"
#include <stdint.h>

/* Durations are microseconds, never differences of scene capture_ms. Nested
 * envelopes (loop/process/recovery/sleep) must not be added to leaf stages. */
typedef enum {
    PERF_CAPTURE_WAIT, PERF_INVALIDATE, PERF_PIXEL_CHECK, PERF_COPY,
    PERF_DETECT, PERF_RAY, PERF_OVERLAY, PERF_FLUSH, PERF_DISPLAY_WAIT,
    PERF_PUBLISH, PERF_ENCODE, PERF_UART_SERVICE, PERF_POLL_GAP,
    PERF_QUEUE_AGE, PERF_FIFO_SPAN, PERF_WIRE_IDLE_UPPER,
    PERF_PROCESS, PERF_LOOP, PERF_RECOVERY, PERF_RETRY, PERF_SLEEP,
    PERF_REPORT, PERF_CAPTURE_FAIL, PERF_PROCESS_FAIL, PERF_HOLD, PERF_STAGE_COUNT
} VisionPerfStage;

#if VISION_PERF_ENABLE
#include "scene_protocol.h"
typedef struct { uint32_t n; uint64_t total, maximum; } VisionPerfStat;
/* One cumulative bank + one immutable report snapshot + one <=64-byte line.
 * Single main-loop owner; no allocation, interrupt handler or UART wait. */
extern VisionPerfStat vision_perf_stats[PERF_STAGE_COUNT];
uint64_t vision_perf_now(void); /* Platform clock supplied by main / host test. */
void vision_perf_record(VisionPerfStage stage, uint64_t us);
void vision_perf_end(VisionPerfStage stage, uint64_t start);
void vision_perf_observation(uint32_t frame, uint32_t processing_start_ms);
void vision_perf_packet(uint32_t frame, uint32_t tx, uint64_t queued_us);
void vision_perf_fifo_first(void);
void vision_perf_fifo(unsigned int before, unsigned int after, int done, int full);
void vision_perf_wire_idle(int idle);
void vision_perf_poll(void);
int vision_perf_diag_active(void);
unsigned int vision_perf_diag_poll(const SceneStream *stream, int idle,
    SceneStreamPutByte put, void *context, unsigned int budget);
#define PERF_START(name) uint64_t name = vision_perf_now()
#define PERF_END(stage, name) vision_perf_end(stage, name)
#define PERF_EVENT(stage) vision_perf_record(stage, 0)
#else
#define PERF_START(name) ((void)0)
#define PERF_END(stage, name) ((void)0)
#define PERF_EVENT(stage) ((void)0)
#endif
#endif
