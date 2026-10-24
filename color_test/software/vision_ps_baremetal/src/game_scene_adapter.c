#include "game_scene_adapter.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static int identity(const void *context, const SceneObject *camera,
                    SceneObject *mapped)
{
    (void)context;
    *mapped = *camera;
    return 1;
}

const GameSceneMapping game_uncalibrated_identity_mapping = {
    GAME_MAPPING_VERSION, "uncalibrated_preview", 0, identity, NULL
};

static int vector_valid(float x, float y)
{
    float norm = hypotf(x, y);
    return isfinite(x) && isfinite(y) && isfinite(norm) && norm > 1.0e-6f;
}

static int detection_valid(const VisionDetection *d)
{
    /* The legacy converter defaults unknown types to WALL and can synthesize
     * an axis from angle_deg. Do not let those fallbacks validate game input. */
    switch (d->type) {
    case VISION_SOURCE:
        return d->direction_valid &&
               vector_valid(d->source_direction_x, d->source_direction_y);
    case VISION_MIRROR: case VISION_PORTAL_A: case VISION_PORTAL_B:
    case VISION_TARGET: case VISION_WALL:
        return vector_valid(d->axis_x, d->axis_y);
    default:
        return 0;
    }
}

GameStatus game_scene_adapt(const GameSceneMapping *mapping,
                            const GameDetectionFrame *frame,
                            GameAdaptedScene *scene)
{
    int i, count;
    if (!scene) return GAME_BAD_ARGUMENT;
    memset(scene, 0, sizeof(*scene));
    scene->input.version = GAME_SCENE_VERSION;
    scene->input.objects = scene->objects;
    if (!frame) return GAME_BAD_ARGUMENT;
    scene->input.generation = frame->stamp.generation;
    scene->input.sequence = frame->stamp.sequence;
    scene->input.captured_ms = frame->stamp.captured_ms;
    scene->input.held = frame->held;
    if (!mapping || mapping->version != GAME_MAPPING_VERSION ||
        !mapping->coordinate_space || !mapping->map_pose) return GAME_BAD_ARGUMENT;
    if (!frame->valid || frame->count < 0 || frame->count > VISION_MAX_DETECTIONS ||
        (frame->count && !frame->detections)) return GAME_INVALID_SCENE;
    for (i = 0; i < frame->count; ++i)
        if (!detection_valid(&frame->detections[i])) return GAME_INVALID_SCENE;
    count = ray_game_scene_from_detections(frame->detections, frame->count,
                                          scene->objects, VISION_MAX_DETECTIONS);
    if (count != frame->count) return GAME_INVALID_SCENE;
    for (i = 0; i < count; ++i) {
        SceneObject camera = scene->objects[i];
        SceneObject mapped = camera;
        if (!mapping->map_pose(mapping->context, &camera, &mapped) ||
            mapped.type != camera.type ||
            mapped.direction_valid != camera.direction_valid ||
            !isfinite(mapped.center.x) || !isfinite(mapped.center.y))
            return GAME_INVALID_SCENE;
        if (mapped.type == RAY_OBJECT_SOURCE) {
            if (!mapped.direction_valid ||
                !vector_valid(mapped.source_direction.x, mapped.source_direction.y))
                return GAME_INVALID_SCENE;
        } else if (!vector_valid(mapped.axis.x, mapped.axis.y)) {
            return GAME_INVALID_SCENE;
        }
        scene->objects[i] = mapped;
    }
    scene->input.object_count = count;
    scene->input.valid = 1;
    return GAME_OK;
}
