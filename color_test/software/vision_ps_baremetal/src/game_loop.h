#ifndef GAME_LOOP_H
#define GAME_LOOP_H

#include "game_app.h"
#include "game_input.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GAME_LOOP_MOUSE = 0, GAME_LOOP_MENU, GAME_LOOP_DETECTION, GAME_LOOP_DISPATCH
} GameLoopKind;
typedef struct {
    GameLoopKind kind;
    union {
        GameMouseEvent mouse;
        GameMenuAction menu;
        GameDetectionFrame detection; /* original stamp; borrowed data for this call */
        struct { uint64_t sequence, captured_ms; } dispatch;
    } data;
} GameLoopEvent;
typedef struct {
    GameSnapshot game; /* complete value copy for publication at a render boundary */
    GameMenuView menu; /* derived from game; no second game state */
    GameMenuAction action;
    GameStatus status;
    int has_stamp;
    GameCaptureStamp stamp;
} GameLoopOutput;
typedef struct {
    GameApp app;
    GameMenuInput input;
    const GameMenuLayout *layout;
} GameLoop;

GameStatus game_loop_init(GameLoop *loop, const GameConfig *config,
                          const GameSceneMapping *mapping, const GameMenuLayout *layout);
/* Single owner only; serialize capture/dispatch, menu, results and publication.
 * Always tick first, even with event=NULL or a rejected event. All events in an
 * external batch are stepped in order at the same now_ms; publish the last copy.
 * Never stamps results: dispatch ONCE and retain output.stamp in the task.
 * Bad time does not consume mouse edges. Returns event/tick status and publishes
 * a full snapshot also on rejection (except invalid loop/output arguments).
 * No devices, waits, system clock, worker threads or implicit start. */
GameStatus game_loop_step(GameLoop *loop, uint64_t now_ms,
                          const GameLoopEvent *event, GameLoopOutput *output);

#ifdef __cplusplus
}
#endif
#endif
