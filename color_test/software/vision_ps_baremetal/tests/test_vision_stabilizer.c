#include "vision_stabilizer.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define PI_F 3.14159265358979323846f

static VisionDetection detection(VisionType type, float angle_deg,
                                 int center_x, int center_y)
{
    VisionDetection value;
    float radians = angle_deg*PI_F/180.0f;
    memset(&value, 0, sizeof(value));
    value.type = type;
    value.center_x = center_x;
    value.center_y = center_y;
    value.geometry_center_x = (float)center_x;
    value.geometry_center_y = (float)center_y;
    value.bbox_w = 80;
    value.bbox_h = 30;
    value.axis_x = cosf(radians);
    value.axis_y = sinf(radians);
    value.major_length = 80.0f;
    value.minor_width = 30.0f;
    value.angle_deg = (int)lroundf(angle_deg);
    value.confidence_percent = 90;
    if (type == VISION_SOURCE) {
        value.direction_valid = 1;
        value.source_direction_x = value.axis_x;
        value.source_direction_y = value.axis_y;
        value.source_tip_x = center_x+(int)lroundf(30.0f*value.axis_x);
        value.source_tip_y = center_y+(int)lroundf(30.0f*value.axis_y);
    }
    return value;
}

static const VisionDetection *find_type(const VisionDetection *detections,
                                        int count, VisionType type)
{
    int index;
    for (index = 0; index < count; ++index)
        if (detections[index].type == type) return &detections[index];
    return NULL;
}

static float angle_of(const VisionDetection *value)
{
    float x = value->type == VISION_SOURCE ?
              value->source_direction_x : value->axis_x;
    float y = value->type == VISION_SOURCE ?
              value->source_direction_y : value->axis_y;
    return atan2f(y, x)*180.0f/PI_F;
}

static int update(VisionStabilizer *stabilizer, VisionDetection *detections,
                  int count)
{
    return vision_stabilizer_update(stabilizer, detections, count,
                                    VISION_MAX_DETECTIONS);
}

static int source_persistence_and_move_test(void)
{
    VisionStabilizer stabilizer;
    VisionDetection values[VISION_MAX_DETECTIONS];
    VisionDetection locked;
    const VisionDetection *source;
    int sample;
    int count;
    vision_stabilizer_reset(&stabilizer);
    for (sample = 0; sample < 8; ++sample) {
        if (sample == 3 && update(&stabilizer, values, 0) != 0) return 0;
        values[0] = detection(VISION_SOURCE,
                              sample & 1 ? 0.8f : -0.8f,
                              400+(sample%3)-1, 300);
        count = update(&stabilizer, values, 1);
        if (sample < 7 && count != 0) return 0;
    }
    source = find_type(values, count, VISION_SOURCE);
    if (!source || stabilizer.tracks[VISION_SOURCE].commit_count != 1U ||
        stabilizer.tracks[VISION_SOURCE].valid_samples != 8U)
        return 0;
    locked = *source;

    /* A miss and small pose jitter keep the exact confirmed pose. */
    count = update(&stabilizer, values, 0);
    source = find_type(values, count, VISION_SOURCE);
    if (!source || memcmp(source, &locked, sizeof(locked)) != 0) return 0;
    for (sample = 0; sample < 12; ++sample) {
        values[0] = detection(VISION_SOURCE,
                              sample & 1 ? 3.5f : -3.5f,
                              402+(sample&1), 299);
        count = update(&stabilizer, values, 1);
        source = find_type(values, count, VISION_SOURCE);
        if (!source || memcmp(source, &locked, sizeof(locked)) != 0 ||
            stabilizer.tracks[VISION_SOURCE].commit_count != 1U)
            return 0;
    }

    /* A major move is sampled non-consecutively. Old pose stays visible until
     * all eight stable observations have been aggregated exactly once. */
    for (sample = 0; sample < 8; ++sample) {
        if (sample == 4) {
            count = update(&stabilizer, values, 0);
            source = find_type(values, count, VISION_SOURCE);
            if (!source || memcmp(source, &locked, sizeof(locked)) != 0)
                return 0;
        }
        values[0] = detection(VISION_SOURCE,
                              20.0f+(sample&1 ? 0.5f : -0.5f),
                              500+(sample%3)-1, 330);
        count = update(&stabilizer, values, 1);
        source = find_type(values, count, VISION_SOURCE);
        if (!source) return 0;
        if (sample < 7 && memcmp(source, &locked, sizeof(locked)) != 0)
            return 0;
    }
    if (stabilizer.tracks[VISION_SOURCE].commit_count != 2U ||
        source->center_x < 495 ||
        stabilizer.tracks[VISION_SOURCE].candidate_position_spread > 3.0f ||
        stabilizer.tracks[VISION_SOURCE].candidate_angle_spread_deg > 2.0f)
        return 0;
    printf("SOURCE metrics raw=%u valid=%u commits=%u pos_spread=%.2f "
           "angle_spread=%.2f\n",
           stabilizer.tracks[VISION_SOURCE].raw_observations,
           stabilizer.tracks[VISION_SOURCE].valid_samples,
           stabilizer.tracks[VISION_SOURCE].commit_count,
           stabilizer.tracks[VISION_SOURCE].candidate_position_spread,
           stabilizer.tracks[VISION_SOURCE].candidate_angle_spread_deg);
    return 1;
}

static int object_candidate_test(void)
{
    VisionStabilizer stabilizer;
    VisionDetection values[VISION_MAX_DETECTIONS];
    VisionDetection locked;
    const VisionDetection *wall;
    int sample;
    int count = 0;
    vision_stabilizer_reset(&stabilizer);
    for (sample = 0; sample < 4; ++sample) {
        if (sample == 2 && update(&stabilizer, values, 0) != 0) return 0;
        values[0] = detection(VISION_WALL, 45.0f, 600+(sample&1), 300);
        count = update(&stabilizer, values, 1);
    }
    wall = find_type(values, count, VISION_WALL);
    if (!wall) return 0;
    locked = *wall;
    for (sample = 0; sample < 3; ++sample) {
        values[0] = detection(VISION_WALL, 47.0f, 603, 298);
        count = update(&stabilizer, values, 1);
        wall = find_type(values, count, VISION_WALL);
        if (!wall || memcmp(wall, &locked, sizeof(locked)) != 0) return 0;
    }
    for (sample = 0; sample < 4; ++sample) {
        if (sample == 1) {
            count = update(&stabilizer, values, 0);
            wall = find_type(values, count, VISION_WALL);
            if (!wall || memcmp(wall, &locked, sizeof(locked)) != 0)
                return 0;
        }
        values[0] = detection(VISION_WALL, 70.0f, 650+(sample&1), 340);
        count = update(&stabilizer, values, 1);
        wall = find_type(values, count, VISION_WALL);
        if (!wall) return 0;
        if (sample < 3 && memcmp(wall, &locked, sizeof(locked)) != 0)
            return 0;
    }
    return stabilizer.tracks[VISION_WALL].commit_count == 2U &&
           wall->center_x >= 649;
}

static int portal_direction_lock_test(void)
{
    VisionStabilizer stabilizer;
    VisionDetection values[VISION_MAX_DETECTIONS];
    const VisionDetection *portal;
    int sample;
    int count = 0;
    vision_stabilizer_reset(&stabilizer);
    for (sample = 0; sample < 5; ++sample) {
        values[0] = detection(VISION_PORTAL_A, 30.0f+(float)(sample&1),
                              700+(sample&1), 300);
        count = update(&stabilizer, values, 1);
    }
    portal = find_type(values, count, VISION_PORTAL_A);
    if (!portal || fabsf(angle_of(portal)-30.5f) > 1.0f) return 0;
    for (sample = 0; sample < 12; ++sample) {
        values[0] = detection(VISION_PORTAL_A, -149.0f, 700, 300);
        count = update(&stabilizer, values, 1);
        portal = find_type(values, count, VISION_PORTAL_A);
        if (!portal || fabsf(angle_of(portal)-30.5f) > 1.0f) return 0;
    }
    if (stabilizer.tracks[VISION_PORTAL_A].direction_flip_rejections != 12U ||
        stabilizer.tracks[VISION_PORTAL_A].commit_count != 1U)
        return 0;
    printf("PORTAL metrics raw=%u valid=%u commits=%u flip_rejections=%u\n",
           stabilizer.tracks[VISION_PORTAL_A].raw_observations,
           stabilizer.tracks[VISION_PORTAL_A].valid_samples,
           stabilizer.tracks[VISION_PORTAL_A].commit_count,
           stabilizer.tracks[VISION_PORTAL_A].direction_flip_rejections);
    return 1;
}

int main(void)
{
    if (!source_persistence_and_move_test()) {
        fprintf(stderr, "SOURCE persistence/move test failed\n");
        return 1;
    }
    if (!object_candidate_test()) {
        fprintf(stderr, "object candidate/commit test failed\n");
        return 1;
    }
    if (!portal_direction_lock_test()) {
        fprintf(stderr, "Portal direction-lock test failed\n");
        return 1;
    }
    puts("vision stabilizer host tests passed");
    return 0;
}
