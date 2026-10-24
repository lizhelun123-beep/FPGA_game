#include "green_target_detector.h"
#include "ray_game.h"
#include "vision_ps.h"

#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(_WIN32)
#define VIDEO_API __declspec(dllexport)
#else
#define VIDEO_API
#endif

static RayGameLevel level;
static unsigned int active_zero_ray_frames;
static unsigned int processed_frames;
static unsigned int raw_observations;
static VisionDetection last_raw_source;
static int last_raw_source_valid;

VIDEO_API void video_regression_reset(void)
{
    ray_game_level_reset(&level);
    active_zero_ray_frames = 0U;
    processed_frames = 0U;
    raw_observations = 0U;
    last_raw_source_valid = 0;
}

VIDEO_API void video_regression_clear_active_zero(void)
{
    active_zero_ray_frames = 0U;
}

VIDEO_API void video_regression_metrics(unsigned int *metrics, float *spread)
{
    if (!metrics || !spread) return;
    metrics[0] = processed_frames;
    metrics[1] = raw_observations;
    metrics[2] = raw_observations;
    metrics[3] = 0U;
    metrics[4] = level.source_clear_count;
    metrics[5] = level.committed_ray_update_count;
    metrics[6] = level.topology_change_count;
    metrics[7] = 0U;
    spread[0] = 0.0f;
    spread[1] = 0.0f;
}

VIDEO_API int video_regression_raw_source(VisionDetection *source)
{
    if (!source || !last_raw_source_valid) return 0;
    *source = last_raw_source;
    return 1;
}

#ifdef VISION_PORTAL_DIAGNOSTICS
VIDEO_API int video_regression_diagnose_portal(const uint8_t *frame,
                                                uint32_t width,
                                                uint32_t height,
                                                uint32_t stride,
                                                int portal_type)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count;
    vision_portal_diagnostics_set_type(portal_type);
    count = vision_detect_bgr888(frame, width, height, stride, detections,
                                 VISION_MAX_DETECTIONS);
    vision_portal_diagnostics_set_type(-1);
    return count;
}
#endif

VIDEO_API int video_regression_process(const uint8_t *frame, uint32_t width,
                                        uint32_t height, uint32_t stride,
                                        VisionDetection *detections,
                                        int detection_capacity,
                                        RayGameResult *candidate_result,
                                        RayGameResult *display_result,
                                        int *level_state,
                                        unsigned int *level_events,
                                        unsigned int *active_zero_frames,
                                        float *locked_source)
{
    SceneObject objects[VISION_MAX_DETECTIONS];
    const RayGameResult *display_ray;
    unsigned int events;
    int count = vision_detect_bgr888(frame, width, height, stride, detections,
                                     detection_capacity);
    int object_count = 0;
    int index;
    int scene_valid = count >= 0;
    if (!candidate_result || !display_result || !level_state ||
        !level_events || !active_zero_frames || !locked_source)
        return -3;
    memset(candidate_result, 0, sizeof(*candidate_result));
    memset(display_result, 0, sizeof(*display_result));
    processed_frames++;
    if (count > 0) raw_observations += (unsigned int)count;
    last_raw_source_valid = 0;
    if (scene_valid) {
        for (index = 0; index < count; ++index)
            if (detections[index].type == VISION_SOURCE &&
                detections[index].direction_valid) {
                last_raw_source = detections[index];
                last_raw_source_valid = 1;
                break;
            }
    }
    if (!scene_valid) count = 0;
    if (scene_valid) {
        object_count = ray_game_scene_from_detections(
            detections, count, objects, VISION_MAX_DETECTIONS);
        scene_valid = object_count >= 0;
    }
    if (scene_valid &&
        ray_game_trace(objects, object_count, (float)width, (float)height,
                       candidate_result) != 0)
        scene_valid = 0;
    events = ray_game_level_update(&level, objects,
        scene_valid ? object_count : 0, scene_valid,
        (float)width, (float)height);
    display_ray = ray_game_level_display_ray(&level);
    if (display_ray) *display_result = *display_ray;
    if (level.state == RAY_LEVEL_ACTIVE && !display_ray)
        active_zero_ray_frames++;
    *level_state = (int)level.state;
    *level_events = events;
    *active_zero_frames = active_zero_ray_frames;
    if (level.source_locked) {
        locked_source[0] = level.locked_source.source_tip.x;
        locked_source[1] = level.locked_source.source_tip.y;
        locked_source[2] = level.locked_source.source_direction.x;
        locked_source[3] = level.locked_source.source_direction.y;
    } else {
        memset(locked_source, 0, 4U*sizeof(*locked_source));
    }
    return count;
}

#ifdef VIDEO_REGRESSION_EXE
static int read_frame(uint8_t *frame, size_t bytes)
{
    size_t offset = 0U;
    while (offset < bytes) {
        size_t received = fread(frame+offset, 1U, bytes-offset, stdin);
        if (received == 0U) return 0;
        offset += received;
    }
    return 1;
}

int main(int argc, char **argv)
{
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    size_t bytes;
    uint8_t *frame;
    int command;
    if (argc != 4) return 2;
    width = (uint32_t)strtoul(argv[1], NULL, 10);
    height = (uint32_t)strtoul(argv[2], NULL, 10);
    stride = (uint32_t)strtoul(argv[3], NULL, 10);
    if (!width || !height || stride < width*3U) return 2;
    bytes = (size_t)height*stride;
    frame = (uint8_t *)malloc(bytes);
    if (!frame) return 2;
    video_regression_reset();
    while ((command = fgetc(stdin)) != EOF) {
        if (command == 'Q') break;
        if (command == 'R') {
            video_regression_reset();
            puts("RESET");
            fflush(stdout);
            continue;
        }
        if (command == 'F') {
            VisionDetection detections[VISION_MAX_DETECTIONS];
            RayGameResult candidate;
            RayGameResult displayed;
            float locked_source[4];
            unsigned int events;
            unsigned int active_zero;
            int state;
            int count;
            int index;
            if (!read_frame(frame, bytes)) break;
            count = video_regression_process(frame, width, height, stride,
                                             detections,
                                             VISION_MAX_DETECTIONS,
                                             &candidate, &displayed, &state,
                                             &events, &active_zero,
                                             locked_source);
            printf("%d", count);
            if (count >= 0) {
                for (index = 0; index < count; ++index) {
                    const VisionDetection *d = &detections[index];
                    printf(" %d %d %d %.6f %.6f %d %d %d %d"
                           " %.6f %.6f %.6f %.6f %.6f %.6f %d",
                           (int)d->type, d->center_x, d->center_y,
                           d->geometry_center_x, d->geometry_center_y,
                           d->bbox_x, d->bbox_y, d->bbox_w, d->bbox_h,
                           d->axis_x, d->axis_y, d->major_length,
                           d->minor_width, d->source_direction_x,
                           d->source_direction_y, d->direction_valid);
                }
                printf(" %d", candidate.segment_count);
                for (index = 0; index < candidate.segment_count; ++index)
                    printf(" %.6f %.6f %.6f %.6f",
                           candidate.segments[index].start.x,
                           candidate.segments[index].start.y,
                           candidate.segments[index].end.x,
                           candidate.segments[index].end.y);
            }
            putchar('\n');
            fflush(stdout);
        }
    }
    free(frame);
    return 0;
}
#endif
