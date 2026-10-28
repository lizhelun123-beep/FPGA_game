#ifndef GAME_BEAM_H
#define GAME_BEAM_H

#include "game_scene_adapter.h"
#include "vision_stabilizer.h"
#include "vision_overlay.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_BEAM_CONFIG_VERSION 2U
#define GAME_BEAM_MAX_OBJECTS 5
#define GAME_BEAM_PHYSICAL_MASK ((1U<<VISION_MIRROR)|(1U<<VISION_PORTAL_A)| \
                                (1U<<VISION_PORTAL_B)|(1U<<VISION_TARGET)|(1U<<VISION_WALL))

typedef enum {
    GAME_BEAM_OK = 0, GAME_BEAM_BAD_ARGUMENT, GAME_BEAM_BAD_CONFIG,
    GAME_BEAM_BAD_TIME, GAME_BEAM_OLD_GENERATION, GAME_BEAM_DUPLICATE_FRAME,
    GAME_BEAM_STALE, GAME_BEAM_UNAVAILABLE, GAME_BEAM_INVALID_GEOMETRY,
    GAME_BEAM_RESTRICTED, GAME_BEAM_PENDING, GAME_BEAM_NO_FRAME
} GameBeamStatus;

/* Camera-image pixel coordinates, not millimetres. width/height are extents
 * (1280/720), so the right/bottom inclusive edges are 1279/719. Immutable copy
 * owned by GameBeam; measured object-to-image geometry comes from detections.
 * max_age_ms is 250 for age rejection, or 0 for the untimed beam test.
 * Disabling age rejection does not change timestamps or frame identity checks. */
typedef struct {
    unsigned version, width, height;
    RayPoint emitter_point, emitter_direction;
    uint64_t max_age_ms;
    int stability_algorithm; /* VISION_STABILITY_A or VISION_STABILITY_B */
    int detector_profile;
    uint64_t display_timeout_ms, display_dropout_ms; /* display only, 0=disabled */
    int portal_b_exit_side; /* 0=paired, +1/-1=fixed local normal */
} GameBeamConfig;

typedef struct {
    uint64_t generation, sequence, captured_ms;
    unsigned width, height;
    RayPoint emitter_point, emitter_direction;
    SceneObject objects[GAME_BEAM_MAX_OBJECTS];
    int object_count;
    RayGameResult ray;
    int valid, display_stale;
    GameBeamStatus status;
    unsigned raw_mask, supported_mask, pending_mask, missing_mask, restricted_mask;
} GameBeamSnapshot;

/* One serial owner. No detector, devices, level rules, timer or scoring here.
 * The sole stabilizer is committed only after generation/sequence/time admission.
 * Treat storage as private except through game_beam_snapshot(). */
typedef struct {
    GameBeamConfig config;
    VisionTimedStabilizer stabilizer;
    GameBeamSnapshot view;
    GameBeamSnapshot display_view;
    uint64_t reset_ms, last_now_ms, last_sequence, last_capture_ms;
    uint64_t absence_since_ms;
    int initialized, have_sequence, have_display, have_absence;
} GameBeam;

GameBeamStatus game_beam_init(GameBeam *beam, const GameBeamConfig *config,
                              uint64_t generation, uint64_t now_ms);
/* A reset uses a strictly newer generation and clears pending pose history. */
GameBeamStatus game_beam_reset(GameBeam *beam, uint64_t generation,
                               uint64_t now_ms);
/* Accepts the current unique subset of the five physical classes, including
 * zero. SOURCE, held poses and non-effective/invalid geometry are rejected.
 * restricted_mask denotes observed identity without a reliable fitted pose;
 * any restriction or B candidate invalidates the whole current beam. */
GameBeamStatus game_beam_submit(GameBeam *beam, const GameDetectionFrame *frame,
                                unsigned restricted_mask, uint64_t now_ms);
GameBeamStatus game_beam_tick(GameBeam *beam, uint64_t now_ms);
const GameBeamSnapshot *game_beam_snapshot(const GameBeam *beam);
/* Copy the current or bounded last committed display version. A retained
 * version has valid=0/display_stale=1/success=0 and keeps ORIGINAL frame stamps.
 * Caller must pair it with the saved camera pixels of that same sequence. */
int game_beam_display_snapshot(const GameBeam *beam, uint64_t now_ms,
                                GameBeamSnapshot *snapshot);
const char *game_beam_status_name(GameBeamStatus status);
/* Draw only into an already-owned CPU canvas/background. No clearing, MMIO,
 * solving, scaling, device acquisition or game state mutation. The snapshot
 * may be a dim display-only copy returned by game_beam_display_snapshot. */
int game_beam_render(const GameBeamSnapshot *snapshot, const VisionCanvas *canvas);

#ifdef __cplusplus
}
#endif
#endif
