#ifndef GAME_SESSION_H
#define GAME_SESSION_H

#include <stdint.h>
#include "ray_game.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_CONFIG_VERSION 1U
#define GAME_SCENE_VERSION 1U
#define GAME_MAX_LEVELS 3
#define GAME_MAX_MODELS 6

typedef enum { GAME_FIXED = 0, GAME_ROTATE_ONLY, GAME_FREE } GameMotion;
typedef enum {
    GAME_SELECT_LEVEL = 0, GAME_PREPARING, GAME_RUNNING,
    GAME_CLEARED, GAME_TIMED_OUT
} GameState;
typedef enum {
    GAME_OK = 0, GAME_BAD_ARGUMENT, GAME_BAD_CONFIG, GAME_BAD_STATE,
    GAME_BAD_TIME, GAME_UNKNOWN_LEVEL, GAME_OLD_GENERATION,
    GAME_DUPLICATE_FRAME, GAME_INVALID_SCENE, GAME_STALE_SCENE,
    GAME_NEED_UNSOLVED
} GameStatus;

typedef struct {
    SceneObject anchor;
    GameMotion motion;
} GameObjectConfig;

typedef struct {
    unsigned int id;
    const char *reference;
    int object_count;
    GameObjectConfig objects[GAME_MAX_MODELS];
} GameLevelConfig;

/* Immutable for the lifetime of the session. Dimensions/sizes are logical
 * game units, NOT inferred millimetres. Generated from pc_vision/game_config.json.
 * A calibrated integration must map anchors AND observations into the same
 * space before initialization; changing calibration requires a new session. */
typedef struct {
    unsigned int version;
    const char *coordinate_space;
    float width, height, physics_scale;
    int max_models, render_max_ray_segments;
    uint64_t scene_max_age_ms, duration_ms, star_threshold_ms[2];
    RayPoint model_sizes[RAY_OBJECT_TYPE_COUNT]; /* x=length, y=width */
    int level_count;
    GameLevelConfig levels[GAME_MAX_LEVELS];
} GameConfig;

/* Already mapped observations; exactly one of every configured class.
 * axes must be reliable; SOURCE uses source_direction + direction_valid.
 * Do not feed held/predicted objects as observations: held must be set if ANY
 * object was retained. valid includes upstream mapping/orientation validity.
 * Measured bbox sizes and source_tip are deliberately ignored.
 * sequence must strictly increase within generation (no wrap); captured_ms
 * must also strictly increase, on the same monotonic timeline as now_ms.
 * Stamp generation when capture/work is dispatched, never when it completes. */
typedef struct {
    unsigned int version;
    uint64_t generation, sequence, captured_ms;
    int valid, held;
    const SceneObject *objects;
    int object_count;
} GameSceneInput;

/* One coherent model/ray/result version for a future renderer. Mirror endpoints
 * are center +/- axis*length/2. SOURCE tip is regenerated from this same model.
 * Full solver output is retained even when render_budget_exceeded is true.
 * Serialize calls and copy this snapshot at the presentation frame boundary;
 * the core provides no threads, clocks, smoothing, devices or drawing. */
typedef struct {
    GameState state;
    unsigned int level_id;
    uint64_t generation, scene_sequence, captured_ms;
    uint64_t elapsed_ms, remaining_ms;
    unsigned int stars;
    int scene_valid, ready, render_budget_exceeded;
    GameStatus scene_status;
    SceneObject objects[GAME_MAX_MODELS];
    int object_count;
    RayGameResult ray;
} GameSnapshot;

/* Stack-allocatable; treat fields as private except through snapshot(). */
typedef struct {
    const GameConfig *config;
    const GameLevelConfig *level;
    GameSnapshot view;
    uint64_t last_now_ms, selected_ms, started_ms;
    uint64_t last_sequence, last_capture_ms;
    int have_time, have_sequence;
} GameSession;

GameStatus game_session_init(GameSession *session, const GameConfig *config);
/* Any level may be selected, including the current one; selection always
 * increments generation and clears timer, geometry, candidates and score.
 * There is no reset button, progress store or automatic level progression. */
GameStatus game_session_select(GameSession *session, unsigned int level_id,
                               uint64_t now_ms);
/* Start requires a fresh complete UNSOLVED preparation scene; it never scores
 * that scene. A new post-start capture is required for a win. */
GameStatus game_session_start(GameSession *session, uint64_t now_ms);
GameStatus game_session_submit(GameSession *session, const GameSceneInput *input,
                               uint64_t now_ms);
/* Call even without new input. Occlusion does not pause the running timer.
 * At elapsed >= duration, timeout takes precedence over arriving frames.
 * A hit accepted before deadline scores by captured_ms, not rounded UI time.
 * Terminal snapshots and scores are frozen until another level is selected. */
GameStatus game_session_tick(GameSession *session, uint64_t now_ms);
const GameSnapshot *game_session_snapshot(const GameSession *session);

#ifdef __cplusplus
}
#endif
#endif
