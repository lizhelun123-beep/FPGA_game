#include "game_evdev.h"

#include <limits.h>
#include <string.h>

static uint64_t little(const unsigned char *p, size_t n)
{
    uint64_t value = 0;
    size_t i;
    for (i = 0; i < n; ++i) value |= (uint64_t)p[i] << (8*i);
    return value;
}

int game_evdev_decode(GameEvdevLayout layout, const unsigned char *bytes,
                      size_t length, GameEvdevEvent *event)
{
    size_t word, offset;
    uint64_t value;
    GameEvdevEvent decoded;
    if (!bytes || !event || (layout != GAME_EVDEV_LE32 && layout != GAME_EVDEV_LE64) ||
        length != (size_t)layout) return 0;
    word = layout == GAME_EVDEV_LE32 ? 4U : 8U;
    offset = 2*word;
    decoded.seconds = little(bytes, word);
    decoded.microseconds = little(bytes+word, word);
    if (decoded.seconds > (word == 4 ? INT32_MAX : INT64_MAX) ||
        decoded.microseconds >= 1000000U) return 0;
    decoded.type = (uint16_t)little(bytes+offset, 2);
    decoded.code = (uint16_t)little(bytes+offset+2, 2);
    value = little(bytes+offset+4, 4);
    decoded.value = value <= INT32_MAX ? (int32_t)value :
                    (int32_t)(-1-(int64_t)(UINT32_MAX-value));
    *event = decoded;
    return 1;
}

int game_evdev_init(GameEvdev *evdev, int width, int height)
{
    if (!evdev || width <= 0 || height <= 0) return 0;
    memset(evdev, 0, sizeof(*evdev));
    evdev->width = width; evdev->height = height; evdev->connected = 1;
    return 1;
}

void game_evdev_connection(GameEvdev *evdev, int connected, GameMouseBatch *batch)
{
    batch->count = 0;
    if (connected && evdev->recovering == 1) return;
    evdev->recovering = 0;
    evdev->pending.count = 0;
    evdev->x = evdev->published_x; evdev->y = evdev->published_y;
    evdev->connected = !!connected;
    batch->count = 1;
    batch->events[0] = (GameMouseEvent){connected ? GAME_MOUSE_CONNECT : GAME_MOUSE_DISCONNECT, 0, 0};
}

static void lost(GameEvdev *evdev, GameMouseBatch *batch)
{
    game_evdev_connection(evdev, 0, batch);
    evdev->recovering = 1;
}

static int enqueue(GameEvdev *evdev, GameMouseEvent mouse, GameMouseBatch *batch)
{
    GameMouseBatch *p = &evdev->pending;
    if (mouse.kind == GAME_MOUSE_MOVE && p->count &&
        p->events[p->count-1].kind == GAME_MOUSE_MOVE) {
        p->events[p->count-1] = mouse;
        return 0;
    }
    if (p->count == GAME_EVDEV_BATCH_MAX) {
        lost(evdev, batch);
        return 1;
    }
    p->events[p->count++] = mouse;
    return 0;
}

int game_evdev_feed(GameEvdev *evdev, const GameEvdevEvent *event, GameMouseBatch *batch)
{
    if (!evdev || !event || !batch || evdev->width <= 0 || evdev->height <= 0) return -1;
    batch->count = 0;
    if (!evdev->connected) {
        if (evdev->recovering && event->type == 0) {
            if (event->code == 3) evdev->recovering = 1;
            else if (event->code == 0) evdev->recovering = 2;
        }
        return 0;
    }
    if (event->type == 0 && event->code == 3) { /* EV_SYN / SYN_DROPPED */
        lost(evdev, batch);
        return 1;
    }
    if (event->type == 0 && event->code == 0) { /* EV_SYN / SYN_REPORT */
        *batch = evdev->pending;
        evdev->published_x = evdev->x; evdev->published_y = evdev->y;
        evdev->pending.count = 0;
        return 1;
    }
    if (event->type == 2 && (event->code == 0 || event->code == 1)) { /* EV_REL X/Y */
        int *coordinate = event->code == 0 ? &evdev->x : &evdev->y;
        int bound = event->code == 0 ? evdev->width : evdev->height;
        int64_t next = (int64_t)*coordinate+event->value;
        *coordinate = next < 0 ? 0 : next >= bound ? bound-1 : (int)next;
        return enqueue(evdev, (GameMouseEvent){GAME_MOUSE_MOVE, evdev->x, evdev->y}, batch);
    }
    if (event->type == 1 && event->code == 272 && /* EV_KEY / BTN_LEFT */
        (event->value == 0 || event->value == 1))
        return enqueue(evdev, (GameMouseEvent){event->value ? GAME_MOUSE_LEFT_DOWN :
                                             GAME_MOUSE_LEFT_UP, 0, 0}, batch);
    return 0;
}

int game_evdev_stream_init(GameEvdevStream *stream, GameEvdevLayout layout, int width, int height)
{
    if (!stream || (layout != GAME_EVDEV_LE32 && layout != GAME_EVDEV_LE64)) return 0;
    memset(stream, 0, sizeof(*stream));
    stream->layout = layout;
    if (!game_evdev_init(&stream->evdev, width, height)) return 0;
    stream->evdev.connected = 0;
    return 1;
}

void game_evdev_stream_connection(GameEvdevStream *stream, int connected,
                                  GameEvdevSink sink, void *context)
{
    GameMouseBatch batch;
    stream->used = 0;
    stream->evdev.recovering = 0; /* new epoch; no bytes from the old device */
    game_evdev_connection(&stream->evdev, connected, &batch);
    sink(context, &batch);
}

int game_evdev_stream_feed(GameEvdevStream *stream, const unsigned char *bytes, size_t length,
                           GameEvdevSink sink, void *context)
{
    size_t i;
    if (!stream || (!bytes && length) || !sink ||
        (stream->layout != GAME_EVDEV_LE32 && stream->layout != GAME_EVDEV_LE64)) return 0;
    if (!stream->evdev.connected && !stream->evdev.recovering) return 1;
    for (i = 0; i < length; ++i) {
        GameEvdevEvent event;
        GameMouseBatch batch;
        stream->partial[stream->used++] = bytes[i];
        if (stream->used != (size_t)stream->layout) continue;
        stream->used = 0;
        if (!game_evdev_decode(stream->layout, stream->partial, (size_t)stream->layout, &event)) {
            if (stream->evdev.connected) { lost(&stream->evdev, &batch); sink(context, &batch); }
            else if (stream->evdev.recovering) stream->evdev.recovering = 1;
            continue;
        }
        game_evdev_feed(&stream->evdev, &event, &batch);
        if (batch.count) sink(context, &batch);
    }
    return 1;
}

int game_evdev_stream_can_resync(const GameEvdevStream *stream)
{
    return stream && stream->evdev.recovering == 2 && stream->used == 0;
}

int game_evdev_stream_recover(GameEvdevStream *stream, GameEvdevSink sink, void *context)
{
    GameMouseBatch batch;
    if (!sink || !game_evdev_stream_can_resync(stream)) return 0;
    game_evdev_connection(&stream->evdev, 1, &batch);
    sink(context, &batch);
    return 1;
}
