#ifndef RAY_GAME_H
#define RAY_GAME_H

#include "vision_ps.h"

#define RAY_GAME_MAX_INTERACTIONS 16
#define RAY_GAME_MAX_SEGMENTS (RAY_GAME_MAX_INTERACTIONS + 1)

typedef enum {
    RAY_OBJECT_MIRROR = 0,
    RAY_OBJECT_PORTAL_A,
    RAY_OBJECT_PORTAL_B,
    RAY_OBJECT_TARGET,
    RAY_OBJECT_SOURCE,
    RAY_OBJECT_WALL,
    RAY_OBJECT_TYPE_COUNT
} RayObjectType;

typedef struct {
    float x;
    float y;
} RayPoint;

typedef struct {
    RayObjectType type;
    RayPoint center;
    RayPoint axis;
    float length;
    float width;
    RayPoint source_tip;
    RayPoint source_direction;
    int direction_valid;
} SceneObject;

typedef struct {
    RayPoint start;
    RayPoint end;
} RaySegment;

typedef enum {
    RAY_GAME_NO_SOURCE = 0,
    RAY_GAME_BOUNDARY,
    RAY_GAME_WALL,
    RAY_GAME_TARGET,
    RAY_GAME_MISSING_PORTAL,
    RAY_GAME_MAX_INTERACTIONS_REACHED,
    RAY_GAME_INVALID_INPUT
} RayGameTermination;

typedef struct {
    RaySegment segments[RAY_GAME_MAX_SEGMENTS];
    int segment_count;
    int interaction_count;
    int success;
    RayGameTermination termination;
    RayObjectType hit_types[RAY_GAME_MAX_INTERACTIONS];
    int hit_count;
} RayGameResult;

#define RAY_GAME_SOURCE_LOCK_SAMPLES 1
#define RAY_GAME_RAY_CONFIRM_SAMPLES 1
#define RAY_GAME_TARGET_CONFIRM_HITS 1

typedef enum {
    RAY_LEVEL_INIT = 0,
    RAY_LEVEL_ACQUIRE_SOURCE,
    RAY_LEVEL_SOURCE_LOCKED,
    RAY_LEVEL_ACTIVE,
    RAY_LEVEL_TARGET_CONFIRM,
    RAY_LEVEL_TRANSITION
} RayGameLevelState;

enum {
    RAY_LEVEL_EVENT_STATE_CHANGED = 1U << 0,
    RAY_LEVEL_EVENT_SOURCE_SAMPLE = 1U << 1,
    RAY_LEVEL_EVENT_SOURCE_LOCKED = 1U << 2,
    RAY_LEVEL_EVENT_RAY_COMMITTED = 1U << 3,
    RAY_LEVEL_EVENT_CANDIDATE_INVALID = 1U << 4,
    RAY_LEVEL_EVENT_TARGET_HIT = 1U << 5,
    RAY_LEVEL_EVENT_TARGET_CONFIRMED = 1U << 6,
    RAY_LEVEL_EVENT_LEVEL_CLEARED = 1U << 7,
    RAY_LEVEL_EVENT_RESET_STABILIZER = 1U << 8
};

/* The latest valid scene replaces the displayed ray immediately.  A complete
 * valid scene without SOURCE clears it; only a detector/scene-conversion
 * failure preserves the committed copy.  This is not a multi-frame candidate
 * confirmation mechanism. */
typedef struct {
    RayGameLevelState state;
    SceneObject source_samples[RAY_GAME_SOURCE_LOCK_SAMPLES];
    int source_sample_count;
    SceneObject locked_source;
    int source_locked;
    int required_object_counts[RAY_OBJECT_TYPE_COUNT];
    RayGameResult candidate_ray;
    RayGameResult committed_ray;
    int committed_ray_valid;
    int candidate_ray_stable_count;
    int target_hit_count;
    int target_reached;
    int candidate_invalid;
    unsigned int source_clear_count;
    unsigned int committed_ray_update_count;
    unsigned int topology_change_count;
} RayGameLevel;

/* Copy initialized recognition geometry into framebuffer-independent objects. */
int ray_game_scene_from_detections(const VisionDetection *detections, int count,
                                   SceneObject *objects, int capacity);

/* Trace one valid SOURCE through the nearest object intersections. */
int ray_game_trace(const SceneObject *objects, int count,
                   float frame_width, float frame_height,
                   RayGameResult *result);

/* Reset a level to INIT. The first update advances it to ACQUIRE_SOURCE. */
void ray_game_level_reset(RayGameLevel *level);

/* Consume one complete candidate scene. A valid SOURCE-free scene clears the
 * displayed ray, while scene_valid=0 preserves it across detector or scene
 * conversion failures. The return value is a bitmask of RAY_LEVEL_EVENT_*.
 * scene_valid must be zero when detection or scene conversion failed. */
unsigned int ray_game_level_update(RayGameLevel *level,
                                   const SceneObject *objects, int count,
                                   int scene_valid,
                                   float frame_width, float frame_height);

/* Return the persistent display ray, or NULL before first commit/after clear. */
const RayGameResult *ray_game_level_display_ray(const RayGameLevel *level);

const char *ray_game_level_state_name(RayGameLevelState state);

#endif
