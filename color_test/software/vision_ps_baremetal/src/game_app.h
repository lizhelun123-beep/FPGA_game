#ifndef GAME_APP_H
#define GAME_APP_H

#include "game_scene_adapter.h"
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Serialized offline application boundary. No devices, detector ownership,
 * threads, system clock, automatic scene generation or automatic start.
 * Caller owns immutable config and mapping context for the app lifetime. */
typedef struct {
    GameSession session;
    GameSceneMapping mapping;
} GameApp;

GameStatus game_app_init(GameApp *app, const GameConfig *config,
                         const GameSceneMapping *mapping);
GameStatus game_app_select(GameApp *app, unsigned int level_id, uint64_t now_ms);
/* Capture/dispatch only: save the returned stamp WITH that work. sequence and
 * captured_ms come from the producer, never from receipt/completion time. */
GameStatus game_app_capture_stamp(const GameApp *app, uint64_t sequence,
                                  uint64_t captured_ms, GameCaptureStamp *stamp);
GameStatus game_app_submit(GameApp *app, const GameDetectionFrame *frame,
                           uint64_t now_ms);
GameStatus game_app_start(GameApp *app, uint64_t now_ms);
GameStatus game_app_tick(GameApp *app, uint64_t now_ms);
/* Copy all models/rays/generation/score at once. Caller serializes this with
 * updates and publishes this single copy at a future display frame boundary. */
GameStatus game_app_snapshot(const GameApp *app, GameSnapshot *snapshot);
/* Text-only diagnostic output of one snapshot copy; 0=success, -1=bad I/O/args. */
int game_app_write_snapshot(const GameApp *app, FILE *output);
/* Same serializer for an already published loop copy, without re-reading state. */
int game_app_write_view(const GameApp *app, const GameSnapshot *snapshot, FILE *output);

#ifdef __cplusplus
}
#endif
#endif
