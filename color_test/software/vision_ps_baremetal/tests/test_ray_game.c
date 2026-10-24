#include "ray_game.h"
#include "vision_overlay.h"

#include <math.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define WIDTH 1280
#define HEIGHT 720
#define STRIDE 5760
#define SQRT_HALF 0.70710678118654752440f

static struct {
    uint8_t before[64];
    uint8_t pixels[HEIGHT * STRIDE];
    uint8_t after[64];
} framebuffer;
#define frame framebuffer.pixels

static int close_to(float value, float expected, float tolerance)
{
    return fabsf(value-expected) <= tolerance;
}

static SceneObject source(float x, float y, float dx, float dy)
{
    SceneObject object;
    memset(&object, 0, sizeof(object));
    object.type = RAY_OBJECT_SOURCE;
    object.center.x = x;
    object.center.y = y;
    object.source_tip = object.center;
    object.source_direction.x = dx;
    object.source_direction.y = dy;
    object.direction_valid = 1;
    return object;
}

static SceneObject line_object(RayObjectType type, float x, float y,
                               float axis_x, float axis_y,
                               float length, float width)
{
    SceneObject object;
    memset(&object, 0, sizeof(object));
    object.type = type;
    object.center.x = x;
    object.center.y = y;
    object.axis.x = axis_x;
    object.axis.y = axis_y;
    object.length = length;
    object.width = width;
    return object;
}

static int trace(const SceneObject *objects, int count, RayGameResult *result)
{
    return ray_game_trace(objects, count, (float)WIDTH, (float)HEIGHT, result);
}

static RayPoint axis_from_degrees(float degrees)
{
    float radians = degrees*3.14159265358979323846f/180.0f;
    RayPoint result = {cosf(radians), sinf(radians)};
    return result;
}

static RayPoint perpendicular(RayPoint axis)
{
    RayPoint result = {-axis.y, axis.x};
    return result;
}

static float point_dot(RayPoint first, RayPoint second)
{
    return first.x*second.x + first.y*second.y;
}

static RayPoint unit_segment_direction(const RaySegment *segment)
{
    RayPoint result = {segment->end.x-segment->start.x,
                       segment->end.y-segment->start.y};
    float magnitude = sqrtf(point_dot(result, result));
    if (magnitude > 0.0f) {
        result.x /= magnitude;
        result.y /= magnitude;
    }
    return result;
}

static int test_no_source_and_boundary(void)
{
    SceneObject objects[2];
    RayGameResult result;
    objects[0] = line_object(RAY_OBJECT_TARGET, 500.0f, 300.0f,
                             1.0f, 0.0f, 40.0f, 40.0f);
    if (trace(objects, 1, &result) || result.segment_count != 0 ||
        result.success || result.termination != RAY_GAME_NO_SOURCE)
        return 0;
    objects[0] = source(100.0f, 100.0f, 1.0f, 0.0f);
    if (trace(objects, 1, &result) || result.segment_count != 1 ||
        result.termination != RAY_GAME_BOUNDARY ||
        !close_to(result.segments[0].start.x, 103.0f, 0.01f) ||
        !close_to(result.segments[0].end.x, 1279.0f, 0.01f))
        return 0;
    return 1;
}

static int test_mirrors(void)
{
    SceneObject objects[2];
    RayGameResult result;
    objects[0] = source(100.0f, 300.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_MIRROR, 300.0f, 300.0f,
                             0.0f, 1.0f, 300.0f, 5.0f);
    if (trace(objects, 2, &result) || result.segment_count != 2 ||
        !close_to(result.segments[0].end.x, 300.0f, 0.02f) ||
        !close_to(result.segments[1].end.x, 0.0f, 0.01f))
        return 0;
    objects[0] = source(300.0f, 100.0f, 0.0f, 1.0f);
    objects[1] = line_object(RAY_OBJECT_MIRROR, 300.0f, 300.0f,
                             1.0f, 0.0f, 300.0f, 5.0f);
    if (trace(objects, 2, &result) || result.segment_count != 2 ||
        !close_to(result.segments[0].end.y, 300.0f, 0.02f) ||
        !close_to(result.segments[1].end.y, 0.0f, 0.01f))
        return 0;
    objects[0] = source(100.0f, 300.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_MIRROR, 300.0f, 300.0f,
                             SQRT_HALF, SQRT_HALF, 300.0f, 5.0f);
    if (trace(objects, 2, &result) || result.segment_count != 2 ||
        !close_to(result.segments[1].end.y, 719.0f, 0.02f) ||
        !close_to(result.segments[0].end.x, 300.0f, 0.03f) ||
        !close_to(result.segments[1].end.x, 300.0f, 0.03f))
        return 0;
    /* A ray parallel to the finite reflecting segment cannot hit an
     * artificial rectangular end-cap. */
    objects[0] = source(100.0f, 300.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_MIRROR, 300.0f, 300.0f,
                             1.0f, 0.0f, 100.0f, 20.0f);
    if (trace(objects, 2, &result) || result.segment_count != 1 ||
        result.termination != RAY_GAME_BOUNDARY ||
        !close_to(result.segments[0].end.x, 1279.0f, 0.02f))
        return 0;
    return 1;
}

static int test_wall_target_and_nearest(void)
{
    SceneObject objects[3];
    RayGameResult result;
    objects[0] = source(100.0f, 300.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_WALL, 300.0f, 300.0f,
                             0.0f, 1.0f, 200.0f, 20.0f);
    objects[2] = line_object(RAY_OBJECT_TARGET, 500.0f, 300.0f,
                             1.0f, 0.0f, 30.0f, 30.0f);
    if (trace(objects, 3, &result) || result.success ||
        result.termination != RAY_GAME_WALL || result.segment_count != 1 ||
        !close_to(result.segments[0].end.x, 290.0f, 0.02f))
        return 0;
    if (trace(objects, 1, &result)) return 0;
    objects[1] = objects[2];
    if (trace(objects, 2, &result) || !result.success ||
        result.termination != RAY_GAME_TARGET ||
        !close_to(result.segments[0].end.x, 485.0f, 0.02f))
        return 0;
    objects[1] = line_object(RAY_OBJECT_TARGET, 250.0f, 300.0f,
                             1.0f, 0.0f, 40.0f, 40.0f);
    objects[2] = line_object(RAY_OBJECT_MIRROR, 400.0f, 300.0f,
                             0.0f, 1.0f, 200.0f, 5.0f);
    if (trace(objects, 3, &result) || !result.success ||
        result.termination != RAY_GAME_TARGET ||
        !close_to(result.segments[0].end.x, 230.0f, 0.02f))
        return 0;
    return 1;
}

static int portal_transfer_case(float angle_a, float angle_b,
                                RayObjectType entry_type, float local_u,
                                int entry_side)
{
    SceneObject objects[3];
    SceneObject *entry;
    SceneObject *exit;
    RayGameResult result;
    RayPoint u_in = axis_from_degrees(entry_type == RAY_OBJECT_PORTAL_A ?
                                      angle_a : angle_b);
    RayPoint u_out = axis_from_degrees(entry_type == RAY_OBJECT_PORTAL_A ?
                                       angle_b : angle_a);
    RayPoint v_in = perpendicular(u_in);
    RayPoint v_out = perpendicular(u_out);
    const float along = 0.25f;
    const float across = -(float)entry_side*0.9682458365518543f;
    RayPoint incoming = {along*u_in.x+across*v_in.x,
                         along*u_in.y+across*v_in.y};
    RayPoint expected_direction = {along*u_out.x+across*v_out.x,
                                   along*u_out.y+across*v_out.y};
    RayPoint hit;
    RayPoint expected_surface;
    RayPoint expected_start;
    RayPoint output_direction;
    RayPoint recovered_surface;
    float recovered_u;
    int exit_side = -entry_side;

    objects[1] = line_object(RAY_OBJECT_PORTAL_A, 350.0f, 360.0f,
                             cosf(angle_a*3.14159265358979323846f/180.0f),
                             sinf(angle_a*3.14159265358979323846f/180.0f),
                             180.0f, 20.0f);
    objects[2] = line_object(RAY_OBJECT_PORTAL_B, 900.0f, 360.0f,
                             cosf(angle_b*3.14159265358979323846f/180.0f),
                             sinf(angle_b*3.14159265358979323846f/180.0f),
                             140.0f, 24.0f);
    entry = entry_type == RAY_OBJECT_PORTAL_A ? &objects[1] : &objects[2];
    exit = entry_type == RAY_OBJECT_PORTAL_A ? &objects[2] : &objects[1];
    hit.x = entry->center.x + local_u*0.5f*entry->length*u_in.x +
            (float)entry_side*0.5f*entry->width*v_in.x;
    hit.y = entry->center.y + local_u*0.5f*entry->length*u_in.y +
            (float)entry_side*0.5f*entry->width*v_in.y;
    objects[0] = source(hit.x-123.0f*incoming.x,
                        hit.y-123.0f*incoming.y,
                        incoming.x, incoming.y);
    expected_surface.x = exit->center.x + local_u*0.5f*exit->length*u_out.x +
                         (float)exit_side*0.5f*exit->width*v_out.x;
    expected_surface.y = exit->center.y + local_u*0.5f*exit->length*u_out.y +
                         (float)exit_side*0.5f*exit->width*v_out.y;
    expected_start.x = expected_surface.x + expected_direction.x;
    expected_start.y = expected_surface.y + expected_direction.y;

    if (trace(objects, 3, &result) || result.segment_count != 2 ||
        result.interaction_count != 1 || result.hit_count != 1 ||
        result.hit_types[0] != entry_type ||
        result.termination != RAY_GAME_BOUNDARY ||
        !close_to(result.segments[0].end.x, hit.x, 0.04f) ||
        !close_to(result.segments[0].end.y, hit.y, 0.04f) ||
        !close_to(result.segments[1].start.x, expected_start.x, 0.04f) ||
        !close_to(result.segments[1].start.y, expected_start.y, 0.04f)) {
        fprintf(stderr, "portal geometry failed angles=%.1f/%.1f entry=%d "
                "u=%.2f side=%d term=%d segments=%d hits=%d\n",
                angle_a, angle_b, entry_type, local_u, entry_side,
                result.termination, result.segment_count, result.hit_count);
        return 0;
    }
    output_direction = unit_segment_direction(&result.segments[1]);
    if (point_dot(output_direction, expected_direction) < 0.9999f ||
        point_dot(output_direction, v_out)*(float)exit_side <= 0.0f) {
        fprintf(stderr, "portal direction/outward failed angles=%.1f/%.1f "
                "entry=%d got=(%.4f,%.4f) expected=(%.4f,%.4f)\n",
                angle_a, angle_b, entry_type, output_direction.x,
                output_direction.y, expected_direction.x,
                expected_direction.y);
        return 0;
    }
    recovered_surface.x = result.segments[1].start.x-output_direction.x;
    recovered_surface.y = result.segments[1].start.y-output_direction.y;
    recovered_u = point_dot((RayPoint){recovered_surface.x-exit->center.x,
                                       recovered_surface.y-exit->center.y},
                            u_out)/(0.5f*exit->length);
    if (!close_to(recovered_u, local_u, 0.001f)) {
        fprintf(stderr, "portal signed solid/ring coordinate failed "
                "entry=%d expected=%.4f got=%.4f\n",
                entry_type, local_u, recovered_u);
        return 0;
    }
    return 1;
}

static int test_portals(void)
{
    static const float orientations[][2] = {
        {0.0f, 0.0f},
        {0.0f, 180.0f},
        {0.0f, 90.0f},
        {30.0f, -55.0f}
    };
    SceneObject objects[4];
    RayGameResult result;
    unsigned int index;
    for (index = 0; index < sizeof(orientations)/sizeof(orientations[0]);
         ++index) {
        if (!portal_transfer_case(orientations[index][0],
                                  orientations[index][1],
                                  RAY_OBJECT_PORTAL_A, 0.35f, 1) ||
            !portal_transfer_case(orientations[index][0],
                                  orientations[index][1],
                                  RAY_OBJECT_PORTAL_B, 0.35f, -1))
            return 0;
    }
    if (!portal_transfer_case(30.0f, -55.0f,
                              RAY_OBJECT_PORTAL_A, -0.75f, 1) ||
        !portal_transfer_case(30.0f, -55.0f,
                              RAY_OBJECT_PORTAL_B, 0.75f, -1))
        return 0;

    objects[0] = source(500.0f, 250.0f, -1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_PORTAL_A, 300.0f, 300.0f,
                             0.0f, 1.0f, 200.0f, 10.0f);
    if (trace(objects, 2, &result) ||
        result.termination != RAY_GAME_MISSING_PORTAL ||
        result.segment_count != 1)
        return 0;
    objects[2] = line_object(RAY_OBJECT_PORTAL_B, 700.0f, 550.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    objects[3] = line_object(RAY_OBJECT_PORTAL_B, 900.0f, 400.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    if (trace(objects, 4, &result) ||
        result.termination != RAY_GAME_MISSING_PORTAL ||
        result.segment_count != 1)
        return 0;
    objects[2] = line_object(RAY_OBJECT_PORTAL_B, 700.0f, 550.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    objects[3] = line_object(RAY_OBJECT_PORTAL_A, 900.0f, 400.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    if (trace(objects, 4, &result) ||
        result.termination != RAY_GAME_MISSING_PORTAL ||
        result.segment_count != 1)
        return 0;
    return 1;
}

static int test_interaction_limit(void)
{
    SceneObject objects[3];
    RayGameResult result;
    objects[0] = source(400.0f, 300.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_MIRROR, 300.0f, 300.0f,
                             0.0f, 1.0f, 500.0f, 5.0f);
    objects[2] = line_object(RAY_OBJECT_MIRROR, 500.0f, 300.0f,
                             0.0f, 1.0f, 500.0f, 5.0f);
    if (trace(objects, 3, &result) ||
        result.termination != RAY_GAME_MAX_INTERACTIONS_REACHED ||
        result.interaction_count != RAY_GAME_MAX_INTERACTIONS ||
        result.segment_count != RAY_GAME_MAX_INTERACTIONS)
        return 0;
    return 1;
}

static int test_scene_fallback(void)
{
    VisionDetection detection;
    SceneObject object;
    memset(&detection, 0, sizeof(detection));
    detection.type = VISION_WALL;
    detection.center_x = 50;
    detection.center_y = 60;
    detection.bbox_w = 20;
    detection.bbox_h = 80;
    detection.angle_deg = 90;
    if (ray_game_scene_from_detections(&detection, 1, &object, 1) != 1 ||
        object.type != RAY_OBJECT_WALL ||
        !close_to(object.axis.x, 0.0f, 0.001f) ||
        !close_to(object.axis.y, 1.0f, 0.001f) ||
        !close_to(object.length, 80.0f, 0.001f) ||
        !close_to(object.width, 20.0f, 0.001f))
        return 0;
    return 1;
}

static int start_level(RayGameLevel *level, SceneObject *objects, int count)
{
    unsigned int events;
    ray_game_level_reset(level);
    events = ray_game_level_update(level, objects, count, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_STATE_CHANGED) ||
        !(events & RAY_LEVEL_EVENT_SOURCE_LOCKED) ||
        !(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        level->state != RAY_LEVEL_ACTIVE || !level->source_locked ||
        !level->committed_ray_valid || !ray_game_level_display_ray(level))
        return 0;
    return 1;
}

static int test_level_immediate_updates(void)
{
    RayGameLevel level;
    SceneObject objects[2];
    RayGameResult original;
    unsigned int events;
    objects[0] = source(100.0f, 100.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_WALL, 600.0f, 500.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    if (!start_level(&level, objects, 2)) return 0;
    original = level.committed_ray;

    /* A failed detector/candidate does not clear or mutate the display ray. */
    events = ray_game_level_update(&level, NULL, 0, 0,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_CANDIDATE_INVALID) ||
        level.state != RAY_LEVEL_ACTIVE || !level.committed_ray_valid ||
        memcmp(&original, &level.committed_ray, sizeof(original)) != 0)
        return 0;

    /* A valid empty/background scene clears the old ray instead of making a
     * white playfield edge appear to emit it. */
    events = ray_game_level_update(&level, NULL, 0, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        !(events & RAY_LEVEL_EVENT_STATE_CHANGED) ||
        (events & RAY_LEVEL_EVENT_CANDIDATE_INVALID) ||
        level.state != RAY_LEVEL_ACQUIRE_SOURCE || level.source_locked ||
        level.committed_ray_valid || ray_game_level_display_ray(&level) ||
        level.source_clear_count != 1U)
        return 0;

    /* A later SOURCE reacquires and draws in the same frame. */
    objects[0] = source(106.0f, 100.0f, 1.0f, 0.0f);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        !(events & RAY_LEVEL_EVENT_SOURCE_LOCKED) ||
        (events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        level.state != RAY_LEVEL_ACTIVE || !level.committed_ray_valid ||
        !close_to(level.locked_source.source_tip.x, 106.0f, 0.01f) ||
        !close_to(level.committed_ray.segments[0].start.x, 109.0f, 0.01f))
        return 0;

    /* A valid orange Portal-only scene also clears the ray, so its white ring
     * cannot inherit a previous SOURCE's segment. */
    objects[1] = line_object(RAY_OBJECT_PORTAL_B, 600.0f, 500.0f,
                             1.0f, 0.0f, 100.0f, 20.0f);
    events = ray_game_level_update(&level, &objects[1], 1, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        !(events & RAY_LEVEL_EVENT_STATE_CHANGED) ||
        level.state != RAY_LEVEL_ACQUIRE_SOURCE || level.source_locked ||
        level.committed_ray_valid || ray_game_level_display_ray(&level) ||
        level.source_clear_count != 2U)
        return 0;

    objects[1] = line_object(RAY_OBJECT_WALL, 600.0f, 500.0f,
                             0.0f, 1.0f, 100.0f, 20.0f);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        !(events & RAY_LEVEL_EVENT_SOURCE_LOCKED) ||
        level.state != RAY_LEVEL_ACTIVE || !level.committed_ray_valid)
        return 0;

    /* No persistent inventory: SOURCE alone immediately draws to the boundary. */
    events = ray_game_level_update(&level, objects, 1, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if ((events & RAY_LEVEL_EVENT_CANDIDATE_INVALID) ||
        level.committed_ray.termination != RAY_GAME_BOUNDARY ||
        level.committed_ray.segment_count != 1 ||
        !close_to(level.committed_ray.segments[0].end.x, 1279.0f, 0.02f))
        return 0;

    /* A changed object also replaces the ray immediately. */
    objects[1] = line_object(RAY_OBJECT_WALL, 400.0f, 100.0f,
                             0.0f, 1.0f, 200.0f, 20.0f);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        level.state != RAY_LEVEL_ACTIVE || !level.committed_ray_valid ||
        level.committed_ray.segment_count != 1 ||
        !close_to(level.committed_ray.segments[0].end.x, 390.0f, 0.02f))
        return 0;

    /* A major SOURCE move is not a permission gate for recomputation. */
    objects[0] = source(140.0f, 100.0f, 1.0f, 0.0f);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        (events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        level.source_clear_count != 2U || level.state != RAY_LEVEL_ACTIVE ||
        !close_to(level.locked_source.source_tip.x, 140.0f, 0.01f))
        return 0;

    /* An unpaired Portal still displays the complete segment up to its hit. */
    objects[0] = source(500.0f, 250.0f, -1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_PORTAL_A, 300.0f, 300.0f,
                             0.0f, 1.0f, 200.0f, 10.0f);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        level.committed_ray.termination != RAY_GAME_MISSING_PORTAL ||
        level.committed_ray.segment_count != 1 ||
        !ray_game_level_display_ray(&level))
        return 0;
    return 1;
}

static int test_level_target_confirmation(void)
{
    RayGameLevel level;
    SceneObject objects[2];
    RayGameResult target_ray;
    unsigned int events;
    objects[0] = source(100.0f, 100.0f, 1.0f, 0.0f);
    objects[1] = line_object(RAY_OBJECT_TARGET, 500.0f, 100.0f,
                             1.0f, 0.0f, 40.0f, 40.0f);
    ray_game_level_reset(&level);
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_TARGET_HIT) ||
        !(events & RAY_LEVEL_EVENT_TARGET_CONFIRMED) ||
        !(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        level.target_hit_count != RAY_GAME_TARGET_CONFIRM_HITS ||
        !level.target_reached || level.state != RAY_LEVEL_ACTIVE ||
        !ray_game_level_display_ray(&level) ||
        level.committed_ray.segment_count != 1 ||
        level.committed_ray.termination != RAY_GAME_TARGET ||
        !close_to(level.committed_ray.segments[0].end.x, 480.0f, 0.02f))
        return 0;
    target_ray = level.committed_ray;

    /* Repeating the same hit never clears or flashes the displayed ray. */
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if ((events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        level.state != RAY_LEVEL_ACTIVE || !level.committed_ray_valid ||
        memcmp(&target_ray, &level.committed_ray, sizeof(target_ray)) != 0)
        return 0;

    /* TARGET is only a latch: other objects keep updating without moving the
     * SOURCE or waiting for another confirmation sequence. */
    objects[1].center.y = 500.0f;
    events = ray_game_level_update(&level, objects, 2, 1,
                                   (float)WIDTH, (float)HEIGHT);
    if (!(events & RAY_LEVEL_EVENT_RAY_COMMITTED) ||
        (events & RAY_LEVEL_EVENT_LEVEL_CLEARED) ||
        level.state != RAY_LEVEL_ACTIVE || !level.target_reached ||
        level.committed_ray.success ||
        level.committed_ray.termination != RAY_GAME_BOUNDARY)
        return 0;
    return 1;
}

static int test_overlay(void)
{
    RaySegment segment = {{-20.0f, 360.0f}, {1300.0f, 360.0f}};
    unsigned y;
    unsigned x;
    memset(frame, 0x5A, sizeof(frame));
    vision_overlay(frame, WIDTH, HEIGHT, STRIDE, NULL, 0, 0U, 0U, 17);
    /* The default overlay API has no detection annotations: an old bbox/cross
     * location away from the small status bar must remain untouched. */
    if (frame[100U*STRIDE+100U*3U] != 0x5A ||
        frame[95U*STRIDE+100U*3U+2U] != 0x5A)
        return 0;
    vision_overlay(frame, WIDTH, HEIGHT, STRIDE, &segment, 1,
                   (1U << RAY_OBJECT_SOURCE) | (1U << RAY_OBJECT_MIRROR),
                   1U << RAY_OBJECT_MIRROR, 17);
    if (frame[360U*STRIDE+1U] != 255U ||
        frame[360U*STRIDE+2U] != 255U ||
        frame[360U*STRIDE+(WIDTH-1U)*3U+1U] != 255U ||
        frame[360U*STRIDE+(WIDTH-1U)*3U+2U] != 255U)
        return 0;
    for (y = 0; y < HEIGHT; ++y)
        for (x = WIDTH*3U; x < STRIDE; ++x)
            if (frame[y*STRIDE+x] != 0x5A) return 0;
    return 1;
}

#if VISION_FIXED_SCENE_DEMO
/* The runner extracts the actual function from main.c into this include.
 * Only display ownership/commit is stubbed; geometry, trace and drawing run
 * unchanged. The overlay spy records the exact objects passed by production. */
#define DISPLAY_RUNNING 1
#define XST_SUCCESS 0
#define XST_FAILURE 1
#define DEMO_STRIDE STRIDE
#define xil_printf printf
static struct { unsigned curFrame; int state; } dispCtrl;
static uint8_t *pFrames[3];
static unsigned vision_frames_presented, present_calls, draw_calls;
static int present_status;
static SceneObject fixed_objects[RAY_OBJECT_TYPE_COUNT];
static int fixed_count;
static RayGameResult fixed_ray;

static int PresentFrame(unsigned next)
{
    assert(next == 2U && dispCtrl.curFrame == 1U);
    ++present_calls;
    if (present_status == XST_SUCCESS) dispCtrl.curFrame = next;
    return present_status;
}

static void capture_scene(uint8_t *f, unsigned w, unsigned h, unsigned stride,
                          const SceneObject *objects, int count,
                          const RayGameResult *ray)
{
    assert(f == frame && w == WIDTH && h == HEIGHT && stride == STRIDE);
    assert(count == RAY_OBJECT_TYPE_COUNT);
    ++draw_calls;
    fixed_count = count;
    memcpy(fixed_objects, objects, sizeof fixed_objects);
    fixed_ray = *ray;
    vision_overlay_scene(f, w, h, stride, objects, count, ray);
}
#define vision_overlay_scene capture_scene
#include "fixed_scene_present.inc"
#undef vision_overlay_scene

static void check_guards(void)
{
    unsigned x, y;
    for (x = 0; x < sizeof framebuffer.before; ++x) {
        assert(framebuffer.before[x] == 0x5A);
        assert(framebuffer.after[x] == 0x5A);
    }
    for (y = 0; y < HEIGHT; ++y)
        for (x = WIDTH*3U; x < STRIDE; ++x)
            assert(frame[y*STRIDE+x] == 0x5A);
}

static unsigned rgb_at(RayPoint p)
{
    unsigned x = (unsigned)lroundf(p.x), y = (unsigned)lroundf(p.y);
    const uint8_t *pixel;
    assert(x < WIDTH && y < HEIGHT);
    pixel = frame + y*STRIDE + x*3U;
    return pixel[0] | ((unsigned)pixel[1] << 8) | ((unsigned)pixel[2] << 16);
}

static RayPoint model_point(const SceneObject *o, float along, float across)
{
    RayPoint p = {o->center.x + along*o->axis.x - across*o->axis.y,
                  o->center.y + along*o->axis.y + across*o->axis.x};
    return p;
}

static void test_fixed_scene(const char *raw_path)
{
    static const RayPoint starts[] = {{199,540},{420,539},{889,300}};
    static const RayPoint ends[] = {{420,540},{420,328},{1068,300}};
    static const RayPoint directions[] = {{1,0},{0,-1},{1,0}};
    static const RayObjectType hits[] = {
        RAY_OBJECT_MIRROR, RAY_OBJECT_PORTAL_A, RAY_OBJECT_TARGET
    };
    SceneObject moved[RAY_OBJECT_TYPE_COUNT];
    RayGameResult no_ray = {0};
    int i, corner;
    FILE *raw;
    memset(&framebuffer, 0x5A, sizeof framebuffer);
    pFrames[2] = frame;
    dispCtrl.state = DISPLAY_RUNNING;
    dispCtrl.curFrame = 1U;
    assert(FixedScenePresent() == XST_SUCCESS);
    assert(present_calls == 1 && draw_calls == 1 && vision_frames_presented == 1);
    assert(dispCtrl.curFrame == 2U);
    printf("fixed ray: segments=%d interactions=%d success=%d termination=%d hits=%d\n",
           fixed_ray.segment_count, fixed_ray.interaction_count,
           fixed_ray.success, fixed_ray.termination, fixed_ray.hit_count);
    for (i = 0; i < fixed_ray.segment_count; ++i) {
        RayPoint dir = unit_segment_direction(&fixed_ray.segments[i]);
        printf("segment %d: (%.6f,%.6f) -> (%.6f,%.6f) dir=(%.6f,%.6f) hit=%d\n",
               i, fixed_ray.segments[i].start.x, fixed_ray.segments[i].start.y,
               fixed_ray.segments[i].end.x, fixed_ray.segments[i].end.y,
               dir.x, dir.y, (int)fixed_ray.hit_types[i]);
    }
    fflush(stdout); /* Preserve actual intersections if an assertion fails. */
    assert(fixed_ray.segment_count == 3 && fixed_ray.interaction_count == 2);
    assert(fixed_ray.success == 1 && fixed_ray.termination == RAY_GAME_TARGET);
    assert(fixed_ray.hit_count == 3);
    for (i = 0; i < 3; ++i) {
        RayPoint dir = unit_segment_direction(&fixed_ray.segments[i]);
        assert(fixed_ray.hit_types[i] == hits[i]);
        assert(close_to(fixed_ray.segments[i].start.x, starts[i].x, 0.02f));
        assert(close_to(fixed_ray.segments[i].start.y, starts[i].y, 0.02f));
        assert(close_to(fixed_ray.segments[i].end.x, ends[i].x, 0.02f));
        assert(close_to(fixed_ray.segments[i].end.y, ends[i].y, 0.02f));
        assert(close_to(dir.x, directions[i].x, 0.0001f));
        assert(close_to(dir.y, directions[i].y, 0.0001f));
    }
    assert(close_to(fixed_objects[0].source_tip.x, 196.0f, 0.01f));
    assert(close_to(fixed_objects[0].source_tip.y, 540.0f, 0.01f));
    assert(close_to(fixed_ray.segments[2].start.x-directions[2].x, 888.0f, 0.02f));
    assert(close_to(fixed_ray.segments[2].start.y-directions[2].y, 300.0f, 0.02f));
    check_guards();
    /* Actual BGR bytes: yellow ray, green target and model/boundary positions. */
    assert(rgb_at((RayPoint){300,540}) == 0xFFFF00U);
    assert(rgb_at((RayPoint){1100,300}) == 0x5DE688U);
    assert(rgb_at((RayPoint){1279,719}) == 0x576A64U);
    assert(rgb_at((RayPoint){600,400}) != 0xFFFF00U); /* no portal connector */
    if (raw_path) {
        raw = fopen(raw_path, "wb");
        assert(raw && fwrite(frame, 1, sizeof frame, raw) == sizeof frame);
        assert(fclose(raw) == 0);
    }

    /* Without rays obscuring the models: finite mirror endpoints, source tip,
     * solid->ring portal orientation, all derived from captured geometry. */
    vision_overlay_scene(frame, WIDTH, HEIGHT, STRIDE, fixed_objects, fixed_count, &no_ray);
    for (i = 0; i < fixed_count; ++i) {
        const SceneObject *o = &fixed_objects[i];
        if (o->type == RAY_OBJECT_MIRROR) {
            assert(rgb_at(model_point(o, -o->length/2, 0)) == 0xFAFBFAU);
            assert(rgb_at(model_point(o, o->length/2, 0)) == 0xFAFBFAU);
            assert(rgb_at(model_point(o, o->length/2+5, 0)) != 0xFAFBFAU);
        } else if (o->type == RAY_OBJECT_SOURCE) {
            assert(rgb_at(o->source_tip) == 0xFF70BBU);
        } else if (o->type == RAY_OBJECT_PORTAL_A || o->type == RAY_OBJECT_PORTAL_B) {
            unsigned color = o->type == RAY_OBJECT_PORTAL_A ? 0x51B8F9U : 0xFFA147U;
            assert(rgb_at(model_point(o, -o->length*0.35f, 0)) == color);
            assert(rgb_at(model_point(o, o->length*0.35f, 0)) != color);
            assert(rgb_at(model_point(o, o->length*0.35f, 6)) == color);
        }
    }
    check_guards();
    /* Move the same models across each corner; cross-edge rays exercise line
     * clipping and brush clipping. No second scene layout or physics is added. */
    no_ray.segment_count = 2;
    no_ray.segments[0] = (RaySegment){{-20,360},{1300,360}};
    no_ray.segments[1] = (RaySegment){{640,-20},{640,740}};
    for (corner = 0; corner < 4; ++corner) {
        for (i = 0; i < fixed_count; ++i) {
            float dx, dy;
            moved[i] = fixed_objects[i];
            dx = ((corner & 1) ? WIDTH-1.0f : 0.0f)-moved[i].center.x;
            dy = ((corner & 2) ? HEIGHT-1.0f : 0.0f)-moved[i].center.y;
            moved[i].center.x += dx; moved[i].center.y += dy;
            moved[i].source_tip.x += dx; moved[i].source_tip.y += dy;
        }
        vision_overlay_scene(frame, WIDTH, HEIGHT, STRIDE, moved, fixed_count, &no_ray);
        check_guards();
        assert(rgb_at((RayPoint){1,360}) == 0xFFFF00U);
        assert(rgb_at((RayPoint){1278,360}) == 0xFFFF00U);
        assert(rgb_at((RayPoint){640,1}) == 0xFFFF00U);
        assert(rgb_at((RayPoint){640,718}) == 0xFFFF00U);
    }
    /* Invalid dimensions/stride are rejected before any pixel write. */
    memset(frame, 0x5A, sizeof frame);
    vision_overlay_scene(frame, WIDTH-1, HEIGHT, STRIDE, fixed_objects, fixed_count, &fixed_ray);
    vision_overlay_scene(frame, WIDTH, HEIGHT-1, STRIDE, fixed_objects, fixed_count, &fixed_ray);
    vision_overlay_scene(frame, WIDTH, HEIGHT, WIDTH*3-1, fixed_objects, fixed_count, &fixed_ray);
    for (i = 0; i < (int)sizeof frame; ++i) assert(frame[i] == 0x5A);
    /* Active/wrong-state buffers cannot draw/commit, including a failed commit. */
    assert(FixedScenePresent() == XST_FAILURE);
    dispCtrl.curFrame = 1U; dispCtrl.state = 0;
    assert(FixedScenePresent() == XST_FAILURE);
    assert(present_calls == 1 && draw_calls == 1);
    dispCtrl.state = DISPLAY_RUNNING; present_status = XST_FAILURE;
    assert(FixedScenePresent() == XST_FAILURE);
    assert(dispCtrl.curFrame == 1U && vision_frames_presented == 1);
    check_guards();
    printf("fixed scene assertions passed: geometry/BGR888/5760 stride/guards/clipping/software commit\n");
}
#endif

int main(int argc, char **argv)
{
#if VISION_FIXED_SCENE_DEMO
    test_fixed_scene(argc == 2 ? argv[1] : NULL);
#else
    (void)argc; (void)argv;
#endif
    if (!test_no_source_and_boundary()) {
        fprintf(stderr, "no-source/boundary test failed\n"); return 1;
    }
    if (!test_mirrors()) {
        fprintf(stderr, "mirror test failed\n"); return 1;
    }
    if (!test_wall_target_and_nearest()) {
        fprintf(stderr, "wall/target/nearest test failed\n"); return 1;
    }
    if (!test_portals()) {
        fprintf(stderr, "portal test failed\n"); return 1;
    }
    if (!test_interaction_limit()) {
        fprintf(stderr, "interaction-limit test failed\n"); return 1;
    }
    if (!test_scene_fallback()) {
        fprintf(stderr, "scene fallback test failed\n"); return 1;
    }
    if (!test_level_immediate_updates()) {
        fprintf(stderr, "level immediate-update test failed\n"); return 1;
    }
    if (!test_level_target_confirmation()) {
        fprintf(stderr, "level target-confirmation test failed\n"); return 1;
    }
    if (!test_overlay()) {
        fprintf(stderr, "overlay clipping/default annotation test failed\n");
        return 1;
    }
    printf("ray_game host tests passed\n");
    return 0;
}
