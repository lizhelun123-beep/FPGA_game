#ifndef GAME_PUMP_H
#define GAME_PUMP_H

#include "game_loop.h"
#include "game_evdev.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_PUMP_IO_VERSION 1U
/* Clock failure sentinel. Reject before ticking/consuming input/publishing. */
#define GAME_PUMP_CLOCK_ERROR UINT64_MAX
/* Structural bounds, not gameplay tuning. Each callback must be bounded and
 * nonblocking except wait_until. EINTR consumes an attempt, just like data. */
#define GAME_PUMP_READ_MAX 4U
#define GAME_PUMP_READ_BYTES 192U
#define GAME_PUMP_RESULT_MAX 4U
typedef struct { uint64_t tick_ms; } GamePumpConfig;
typedef enum {
    GAME_READ_DATA = 0, GAME_READ_AGAIN, GAME_READ_INTERRUPTED,
    GAME_READ_EOF, GAME_READ_DISCONNECTED, GAME_READ_ERROR
} GameReadStatus;
typedef struct { GameReadStatus status; size_t count; } GameReadResult;
typedef struct {
    int connected;
    uint64_t epoch; /* change on EVERY new fd/stream, even missed unplug/replug */
} GamePumpConnection;
typedef enum { GAME_WAIT_READY = 0, GAME_WAIT_INTERRUPTED, GAME_WAIT_STOP, GAME_WAIT_ERROR } GameWaitStatus;
typedef enum { GAME_PUMP_CONTINUE = 0, GAME_PUMP_STOP, GAME_PUMP_BAD_CLOCK, GAME_PUMP_IO_ERROR } GamePumpStatus;
typedef struct {
    GameLoopOutput view; /* owned value: models/rays/generation/score together */
    GameReadStatus read_status;
    GameStatus result_status; /* last result rejection survives the final tick */
    size_t reads, bytes, results;
    int idle; /* wait after publication unless stopping or returning an error */
    uint64_t deadline_ms;
} GamePumpOutput;
typedef struct {
    unsigned int version;
    void *context;
    uint64_t (*now_ms)(void *context); /* capture timeline; GAME_PUMP_CLOCK_ERROR on failure */
    GamePumpConnection (*connection)(void *context);
    GameReadResult (*read)(void *context, unsigned char *bytes, size_t capacity);
    /* absolute monotonic deadline; wake on input/result/hotplug/stop OR deadline.
     * Do not return READY repeatedly for a latched EOF/fault or absent device. */
    GameWaitStatus (*wait_until)(void *context, uint64_t deadline_ms);
    /* Optional: called ONLY after discard-through-REPORT at a record boundary.
     * 1=state synchronized, 0=not ready, -1=fault (latches until new connection).
     * Linux implementation must query device state here; no ioctl in this core. */
    int (*resync)(void *context);
    /* Optional completion mailbox, 1=result, 0=empty, -1=platform failure.
     * Original stamp is mandatory. detections is borrowed until the NEXT poll;
     * submit synchronously before that poll. Pump never queues this pointer.
     * Producer must keep it immutable during this call/submit (no threads here). */
    int (*result)(void *context, GameDetectionFrame *frame);
    /* Optional stop and publication callbacks, called once per finished batch.
     * publish borrows output for this call; copy it to retain. Never reenter. */
    int (*stopping)(void *context);
    void (*publish)(void *context, const GamePumpOutput *output);
} GamePumpIO;

typedef struct {
    GameLoop *loop; /* exclusive owner after init; do not mutate alongside pump */
    GamePumpConfig config;
    GamePumpIO io;
    GameEvdevStream stream;
    GamePumpConnection connection;
    int have_connection, read_fault;
    uint64_t now;
    GameLoopOutput latest;
} GamePump;

int game_pump_init(GamePump *pump, GameLoop *loop, const GamePumpConfig *config,
                   GameEvdevLayout layout, const GamePumpIO *io);
/* Synchronous injected menu/capture dispatch/result, between batches, on the
 * owner's thread. Uses external clock and copies snapshot; no publication here.
 * Save dispatch output.stamp with work ONCE. Completion must submit unchanged.
 * Detection array need only survive this call. No internal result queue. */
GameStatus game_pump_event(GamePump *pump, const GameLoopEvent *event, GameLoopOutput *output);
/* Bounded reads -> bounded completions -> final external-time tick -> publish
 * exactly once -> wait if no bytes/results. Fresh clock sampled between calls.
 * Timeout deadline caps tick_ms; continuous traffic/EINTR cannot monopolize a
 * batch. Terminal read failures disconnect and latch until connection changes.
 * wait errors / backwards clocks return to owner, never retry internally. */
GamePumpStatus game_pump_once(GamePump *pump, GamePumpOutput *output);
GamePumpStatus game_pump_run(GamePump *pump, GamePumpOutput *output);

#ifdef __cplusplus
}
#endif
#endif
