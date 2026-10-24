/* Host-only bounded UART scheduler and C/Python wire fixture. */
#include "scene_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

typedef struct { unsigned int space, calls; } Sink;
static int put(void *context, unsigned char byte)
{
    Sink *sink = context;
    ++sink->calls;
    if (!sink->space) return 0;
    --sink->space;
    putchar(byte);
    return 1;
}
int main(void)
{
    VisionDetection objects[VISION_MAX_DETECTIONS];
    SceneStream stream;
    Sink sink = {10000U, 0U};
    char line[SCENE_PROTOCOL_MAX_LINE + 1U];
    int i, n;
#ifdef _WIN32
    _setmode(1, _O_BINARY);
#endif
    memset(objects, 0, sizeof objects);
    for (i = 0; i < VISION_MAX_DETECTIONS; ++i) {
        objects[i].type = (VisionType)(i % 6);
        objects[i].geometry_center_x = 100.25f + i;
        objects[i].geometry_center_y = 200.5f;
        objects[i].axis_x = 0.6f; objects[i].axis_y = 0.8f;
        objects[i].major_length = 60.0f; objects[i].minor_width = 30.0f;
        objects[i].confidence_percent = 95;
        if (objects[i].type == VISION_SOURCE) {
            objects[i].source_tip_x = 120; objects[i].source_tip_y = 230;
            objects[i].source_direction_x = -0.8f;
            objects[i].source_direction_y = 0.6f;
            objects[i].direction_valid = 1;
        }
    }
    n = scene_protocol_encode(line, sizeof line, objects, 6, 1, 123, 45, 6789, 1280, 720);
    assert(n == 348); fwrite(line, 1, (size_t)n, stdout);
    scene_stream_init(&stream, 10, 115200);
    while (stream.offset < stream.length) {
        unsigned int before = sink.calls;
        scene_stream_poll(&stream, 0, put, &sink, 7);
        assert(sink.calls - before <= 7);
    }
    sink.space = 0;
    for (i = 1; i <= 10000; ++i)
        scene_stream_publish(&stream, objects, 16, 1, (uint32_t)i, 500);
    scene_stream_poll(&stream, 10, put, &sink, 64);
    assert(stream.pending == 0 && stream.offset == 0 && stream.replaced == 9999);
    assert(stream.length == 828 && stream.interval_ms == 111);
    /* Active packet is immutable; newer observations replace only the mailbox. */
    scene_stream_publish(&stream, NULL, 0, 0, 10001, 510);
    scene_stream_publish(&stream, NULL, 0, 1, 10002, 520);
    sink.space = 10000;
    while (stream.offset < stream.length) scene_stream_poll(&stream, 20, put, &sink, 64);
    scene_stream_poll(&stream, 120, put, &sink, 64);
    assert(stream.pending && stream.sent == 2);
    scene_stream_poll(&stream, 121, put, &sink, 64);
    assert(!stream.pending && stream.sent == 3 && stream.length == 60);
    scene_stream_publish(&stream, NULL, -1, 1, 10003, 530);
    scene_stream_poll(&stream, 221, put, &sink, 64);
    assert(stream.sent == 4);
    /* Unsigned scheduling across the 32-bit timer rollover. */
    stream.last_start = 0xfffffff0U;
    scene_stream_publish(&stream, NULL, 0, 1, 10004, 540);
    scene_stream_poll(&stream, 85, put, &sink, 64);
    assert(stream.sent == 5);
    return 0;
}
