#ifndef GAME_SCENE_ADAPTER_H
#define GAME_SCENE_ADAPTER_H

#include "game_session.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_MAPPING_VERSION 1U

/* Created at capture/work dispatch on the same external monotonic ms timeline
 * as game_session. Keep this value with the task, including across selection.
 * Never create a replacement stamp when a result is delivered. */
typedef struct {
    uint64_t generation, sequence, captured_ms;
} GameCaptureStamp;

/* Raw canonical detector output, without smoothing or template completion.
 * valid includes upstream capture/detection/orientation reliability; held must
 * be nonzero if ANY pose was retained/predicted. SOURCE additionally requires
 * detection.direction_valid and a finite nonzero source_direction; all other
 * classes require a finite nonzero axis (direction_valid is SOURCE-only).
 * An unreliable but nonzero non-SOURCE axis must set frame.valid=0.
 * count<0 can carry a detector failure; count=0 is a missing scene.
 * Pointers need only remain valid for the synchronous submit call. */
typedef struct {
    GameCaptureStamp stamp;
    int valid, held;
    const VisionDetection *detections;
    int count;
} GameDetectionFrame;

/* Pose mapping seam for a later real calibration. Return 1 on success, 0 on
 * failure; map center AND axes/SOURCE direction into coordinate_space, preserve
 * class identity and direction validity. Do not apply level permissions here.
 * Config anchors/model units must already use that same space before init.
 * Mapping/context are immutable for the app lifetime; a change needs re-init.
 * Only the uncalibrated identity implementation is supplied in this release. */
typedef int (*GameMapPose)(const void *context, const SceneObject *camera,
                           SceneObject *mapped);
typedef struct {
    unsigned int version;
    const char *coordinate_space;
    int calibrated;
    GameMapPose map_pose;
    const void *context;
} GameSceneMapping;

extern const GameSceneMapping game_uncalibrated_identity_mapping;

/* input.objects points into this structure: do not copy it by value. */
typedef struct {
    GameSceneInput input;
    SceneObject objects[VISION_MAX_DETECTIONS];
} GameAdaptedScene;

/* Always preserves a supplied frame's stamp/held flag, even on invalid input.
 * Invalid observations yield input.valid=0, so submit them to the core to
 * invalidate a previous candidate. Missing/duplicate/extra level identities,
 * freshness, sequence and generation are decided by game_session, not here.
 * Never truncates a detection array or synthesizes a missing observation. */
GameStatus game_scene_adapt(const GameSceneMapping *mapping,
                            const GameDetectionFrame *frame,
                            GameAdaptedScene *scene);

#ifdef __cplusplus
}
#endif
#endif
