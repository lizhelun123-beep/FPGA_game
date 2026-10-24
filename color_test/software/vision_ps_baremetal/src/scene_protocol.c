#include "scene_protocol.h"
#include "vision_perf.h"
#include <math.h>
#include <string.h>

static void put16(uint8_t *p, unsigned int v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}
static void put32(uint8_t *p, uint32_t v)
{
    put16(p, v); put16(p + 2, v >> 16);
}
static unsigned int quantize(float value, float scale, int low, int high)
{
    float scaled = value * scale;
    int result;
    if (scaled < (float)low) scaled = (float)low;
    if (scaled > (float)high) scaled = (float)high;
    result = (int)lroundf(scaled);
    return (unsigned int)result & 0xffffU;
}
static int finite_detection(const VisionDetection *d)
{
    return isfinite(d->geometry_center_x) && isfinite(d->geometry_center_y) &&
        isfinite(d->axis_x) && isfinite(d->axis_y) &&
        isfinite(d->major_length) && isfinite(d->minor_width) &&
        isfinite(d->source_direction_x) && isfinite(d->source_direction_y) &&
        (unsigned int)d->type <= VISION_WALL;
}
int scene_protocol_encode(char *line, size_t capacity,
    const VisionDetection *detections, int count, int valid,
    uint32_t frame_sequence, uint32_t tx_sequence, uint32_t capture_ms,
    uint16_t width, uint16_t height)
{
    uint8_t payload[SCENE_PROTOCOL_HEADER_BYTES +
                    SCENE_PROTOCOL_OBJECT_BYTES * VISION_MAX_DETECTIONS + 4];
    static const char hex[] = "0123456789ABCDEF";
    size_t bytes, i;
    int n;
    uint32_t crc = 0xffffffffU;
    if (!line || width < 2 || height < 2 || width > 2048 || height > 2048)
        return -1;
    if (count < 0 || count > VISION_MAX_DETECTIONS || (count && !detections))
        valid = 0;
    if (valid)
        for (n = 0; n < count; ++n)
            if (!finite_detection(&detections[n])) valid = 0;
    if (!valid) count = 0;
    bytes = SCENE_PROTOCOL_HEADER_BYTES + (size_t)count * SCENE_PROTOCOL_OBJECT_BYTES;
    if (capacity < 2U * (bytes + 4U) + 13U) return -1;
    memset(payload, 0, sizeof(payload));
    payload[0] = SCENE_PROTOCOL_VERSION;
    payload[1] = valid ? 1U : 0U;
    payload[2] = (uint8_t)count;
    put32(payload + 4, frame_sequence);
    put32(payload + 8, tx_sequence);
    put32(payload + 12, capture_ms);
    put16(payload + 16, width); put16(payload + 18, height);
    for (n = 0; n < count; ++n) {
        const VisionDetection *d = &detections[n];
        uint8_t *p = payload + SCENE_PROTOCOL_HEADER_BYTES + n * SCENE_PROTOCOL_OBJECT_BYTES;
        float cx = d->geometry_center_x != 0.0f || d->center_x == 0 ?
                   d->geometry_center_x : (float)d->center_x;
        float cy = d->geometry_center_y != 0.0f || d->center_y == 0 ?
                   d->geometry_center_y : (float)d->center_y;
        float length = d->major_length > 0.0f ? d->major_length :
                       (float)(d->bbox_w > d->bbox_h ? d->bbox_w : d->bbox_h);
        float width_ref = d->minor_width > 0.0f ? d->minor_width :
                          (float)(d->bbox_w < d->bbox_h ? d->bbox_w : d->bbox_h);
        p[0] = (uint8_t)d->type;
        p[1] = (d->axis_x*d->axis_x + d->axis_y*d->axis_y > 0.01f ? 1U : 0U) |
               (d->direction_valid ? 2U : 0U);
        p[2] = (uint8_t)(d->confidence_percent < 0 ? 0 :
                        (d->confidence_percent > 100 ? 100 : d->confidence_percent));
        put16(p + 4, quantize(cx, 16, -32768, 32767));
        put16(p + 6, quantize(cy, 16, -32768, 32767));
        put16(p + 8, quantize(d->axis_x, 10000, -10000, 10000));
        put16(p + 10, quantize(d->axis_y, 10000, -10000, 10000));
        put16(p + 12, quantize(length, 16, 0, 65535));
        put16(p + 14, quantize(width_ref, 16, 0, 65535));
        put16(p + 16, quantize((float)d->source_tip_x, 16, -32768, 32767));
        put16(p + 18, quantize((float)d->source_tip_y, 16, -32768, 32767));
        put16(p + 20, quantize(d->source_direction_x, 10000, -10000, 10000));
        put16(p + 22, quantize(d->source_direction_y, 10000, -10000, 10000));
    }
    for (i = 0; i < bytes; ++i) {
        unsigned int bit;
        crc ^= payload[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    put32(payload + bytes, crc ^ 0xffffffffU);
    bytes += 4;
    memcpy(line, "@SCN1:", 6);
    for (i = 0; i < bytes; ++i) {
        line[6 + 2*i] = hex[payload[i] >> 4];
        line[7 + 2*i] = hex[payload[i] & 15];
    }
    memcpy(line + 6 + 2*bytes, ":END\r\n", 6);
    line[12 + 2*bytes] = '\0';
    return (int)(12 + 2*bytes);
}

void scene_stream_init(SceneStream *s, unsigned int hz, unsigned int baud)
{
    memset(s, 0, sizeof(*s));
    s->hz = hz ? hz : 8U;
    s->baud = baud ? baud : 115200U;
    /* A scene-v1 invalid all-zero header explicitly announces a boot epoch.
     * It is not a valid empty observation; ordinary packets start at tx=1. */
    s->length = (unsigned int)scene_protocol_encode(s->line, sizeof s->line,
        NULL, 0, 0, 0, 0, 0, 1280, 720);
}

void scene_stream_publish(SceneStream *s, const VisionDetection *objects,
    int count, int valid, uint32_t frame, uint32_t capture_ms)
{
    PERF_START(start);
    if (s->pending) ++s->replaced;
    s->valid = valid && count >= 0 && count <= VISION_MAX_DETECTIONS &&
        (count == 0 || objects != NULL);
    s->count = s->valid ? count : 0;
    if (s->count) memcpy(s->latest, objects, (size_t)s->count * sizeof(*objects));
    s->frame = frame;
    s->capture_ms = capture_ms;
    s->pending = 1;
#if VISION_PERF_ENABLE
    s->queued_us = vision_perf_now();
    vision_perf_observation(frame, capture_ms);
#endif
    PERF_END(PERF_PUBLISH, start);
}

void scene_stream_poll(SceneStream *s, uint32_t now_ms,
    SceneStreamPutByte put_byte, void *context, unsigned int byte_budget)
{
    if (!put_byte) return;
    if (s->offset == s->length && s->pending &&
        (!s->started || (uint32_t)(now_ms - s->last_start) >= s->interval_ms)) {
        unsigned int wire_ms, period = (1000U + s->hz - 1U) / s->hz;
#if VISION_PERF_ENABLE
        vision_perf_packet(s->frame, s->tx_sequence + 1U, s->queued_us);
#endif
        PERF_START(encode_start);
        int length = scene_protocol_encode(s->line, sizeof s->line,
            s->latest, s->count, s->valid, s->frame, ++s->tx_sequence,
            s->capture_ms, 1280, 720);
        PERF_END(PERF_ENCODE, encode_start);
        s->pending = 0;
        if (length < 0) return;
        s->offset = 0;
        s->length = (unsigned int)length;
        /* 8N1 = ten wire bits/byte; cap scene traffic to 65% of baud. */
        wire_ms = (s->length * 1000000U + s->baud * 65U - 1U) / (s->baud * 65U);
        s->interval_ms = wire_ms > period ? wire_ms : period;
        s->last_start = now_ms;
        s->started = 1;
    }
    {
    PERF_START(service_start);
#if VISION_PERF_ENABLE
    unsigned int before = s->offset;
    int full = 0;
#endif
    while (byte_budget && s->offset < s->length) {
        if (!put_byte(context, (unsigned char)s->line[s->offset])) {
#if VISION_PERF_ENABLE
            full = 1;
#endif
            break;
        }
#if VISION_PERF_ENABLE
        if (s->offset == 0) vision_perf_fifo_first();
#endif
        --byte_budget;
        if (++s->offset == s->length) ++s->sent;
    }
#if VISION_PERF_ENABLE
    vision_perf_fifo(before, s->offset, s->offset == s->length, full);
#endif
    PERF_END(PERF_UART_SERVICE, service_start);
    }
}
