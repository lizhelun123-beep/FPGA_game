#ifndef SCENE_PROTOCOL_H
#define SCENE_PROTOCOL_H
#include "vision_ps.h"
#include <stddef.h>

/* Printable envelope prevents BSP newline translation from corrupting bytes.
 * Wire format and units: pc_vision/README.md. No native struct serialization. */
#define SCENE_PROTOCOL_VERSION 1U
#define SCENE_PROTOCOL_HEADER_BYTES 20U
#define SCENE_PROTOCOL_OBJECT_BYTES 24U
#define SCENE_PROTOCOL_MAX_LINE (60U + 48U * VISION_MAX_DETECTIONS)
int scene_protocol_encode(char *line, size_t capacity,
    const VisionDetection *detections, int count, int valid,
    uint32_t frame_sequence, uint32_t tx_sequence, uint32_t capture_ms,
    uint16_t width, uint16_t height);

/* One in-flight packet plus one replaceable latest observation; never wait for
 * UART space. The caller supplies a nonblocking byte sink and polls often. */
typedef struct {
    char line[SCENE_PROTOCOL_MAX_LINE + 1U];
    VisionDetection latest[VISION_MAX_DETECTIONS];
    uint32_t frame, capture_ms, tx_sequence, last_start, interval_ms;
    uint32_t replaced, sent;
    unsigned int offset, length, hz, baud;
    int pending, count, valid, started;
#if VISION_PERF_ENABLE
    uint64_t queued_us;
#endif
} SceneStream;
typedef int (*SceneStreamPutByte)(void *context, unsigned char byte);
void scene_stream_init(SceneStream *s, unsigned int hz, unsigned int baud);
void scene_stream_publish(SceneStream *s, const VisionDetection *objects,
    int count, int valid, uint32_t frame, uint32_t capture_ms);
void scene_stream_poll(SceneStream *s, uint32_t now_ms,
    SceneStreamPutByte put_byte, void *context, unsigned int byte_budget);
#endif
