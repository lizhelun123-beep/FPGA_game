#ifndef GAME_EVDEV_H
#define GAME_EVDEV_H

#include "game_input.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Explicit target wire layouts, never sizeof(host struct input_event/timeval).
 * LE32: 16 bytes, sec/usec 32-bit at 0/4, type/code/value at 8/10/12.
 * LE64: 24 bytes, sec/usec 64-bit at 0/8, type/code/value at 16/18/20.
 * LE32 models two 32-bit time words (including legacy armhf); LE64 models two
 * 64-bit time words. libc time_t/time64 alone does NOT select the wire layout.
 * The Linux backend MUST verify target UAPI size/offsets. The stream seam below
 * reassembles short reads. Other layouts/endian are unsupported.
 * Device open/read/ioctl and clock conversion live in game_linux_io; this
 * decoder does no syscalls. Automatic device discovery remains absent. */
typedef enum { GAME_EVDEV_LE32 = 16, GAME_EVDEV_LE64 = 24 } GameEvdevLayout;
typedef struct {
    uint64_t seconds, microseconds;
    uint16_t type, code;
    int32_t value;
} GameEvdevEvent;
#define GAME_EVDEV_BATCH_MAX 32
typedef struct {
    GameMouseEvent events[GAME_EVDEV_BATCH_MAX];
    size_t count;
} GameMouseBatch;
typedef struct {
    int width, height, x, y, published_x, published_y, connected;
    int recovering; /* 0=normal, 1=discard through REPORT, 2=await state resync */
    GameMouseBatch pending;
} GameEvdev;

int game_evdev_decode(GameEvdevLayout layout, const unsigned char *bytes,
                      size_t length, GameEvdevEvent *event);
int game_evdev_init(GameEvdev *evdev, int width, int height);
/* Explicit hotplug/loss boundary; discards unfinished reports, keeps pointer.
 * CONNECT never creates a click. Menu input requires release after reconnect. */
void game_evdev_connection(GameEvdev *evdev, int connected, GameMouseBatch *batch);
/* 0=buffered/ignored, 1=batch ready, -1=bad arguments. Relative motion and all
 * left-button edges remain ordered until SYN_REPORT. Key repeats are ignored.
 * SYN_DROPPED or pending overflow emits DISCONNECT and discards the report;
 * ignore through the next SYN_REPORT, then await explicit state resync via
 * game_evdev_connection(1). An early recovery request is ignored. That call
 * asserts the caller has synchronized device state; this seam cannot do ioctl. */
int game_evdev_feed(GameEvdev *evdev, const GameEvdevEvent *event, GameMouseBatch *batch);

/* Byte stream belongs to ONE connection epoch and one explicit target layout.
 * Sink is synchronous; batch storage is borrowed only for the call. */
typedef void (*GameEvdevSink)(void *context, const GameMouseBatch *batch);
typedef struct {
    GameEvdev evdev;
    GameEvdevLayout layout;
    unsigned char partial[24];
    size_t used;
} GameEvdevStream;
int game_evdev_stream_init(GameEvdevStream *stream, GameEvdevLayout layout, int width, int height);
/* Actual detach/new connection, NOT SYN_DROPPED recovery. Clear partial bytes
 * and unfinished report/click on BOTH sides; keep published pointer position. */
void game_evdev_stream_connection(GameEvdevStream *stream, int connected,
                                  GameEvdevSink sink, void *context);
/* Consumes all bytes, including multiple records; ordinary events only at REPORT.
 * Malformed records enter the same discard/resync protocol as SYN_DROPPED.
 * 1=valid arguments/consumed (possibly discarding), 0=bad arguments. */
int game_evdev_stream_feed(GameEvdevStream *stream, const unsigned char *bytes, size_t length,
                           GameEvdevSink sink, void *context);
int game_evdev_stream_can_resync(const GameEvdevStream *stream);
/* Only after REPORT and at a complete record boundary. Caller must have
 * synchronized device state AFTER can_resync; never just clear an error flag. */
int game_evdev_stream_recover(GameEvdevStream *stream, GameEvdevSink sink, void *context);

#ifdef __cplusplus
}
#endif
#endif
