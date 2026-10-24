#include "ray_game.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define SAMPLE_PHOTO_WIDTH 1280U
#define SAMPLE_PHOTO_HEIGHT 720U
#define SAMPLE_PHOTO_FRAME_BYTES (SAMPLE_PHOTO_WIDTH * SAMPLE_PHOTO_HEIGHT * 3U)

static uint8_t frame[SAMPLE_PHOTO_FRAME_BYTES];

static int number(const char *text)
{
    return (int)strtol(text, NULL, 10);
}

static const char *ray_object_type_name(RayObjectType type)
{
    switch (type) {
    case RAY_OBJECT_MIRROR: return "MIRROR";
    case RAY_OBJECT_PORTAL_A: return "PORTAL_A";
    case RAY_OBJECT_PORTAL_B: return "PORTAL_B";
    case RAY_OBJECT_TARGET: return "TARGET";
    case RAY_OBJECT_SOURCE: return "SOURCE";
    case RAY_OBJECT_WALL: return "WALL";
    default: return "UNKNOWN";
    }
}

static const char *termination_name(RayGameTermination termination)
{
    switch (termination) {
    case RAY_GAME_NO_SOURCE: return "NO_SOURCE";
    case RAY_GAME_BOUNDARY: return "BOUNDARY";
    case RAY_GAME_WALL: return "WALL";
    case RAY_GAME_TARGET: return "TARGET";
    case RAY_GAME_MISSING_PORTAL: return "MISSING_PORTAL";
    case RAY_GAME_MAX_INTERACTIONS_REACHED: return "MAX_INTERACTIONS";
    case RAY_GAME_INVALID_INPUT: return "INVALID_INPUT";
    default: return "UNKNOWN";
    }
}

int main(int argc, char **argv)
{
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    size_t bytes;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    SceneObject objects[VISION_MAX_DETECTIONS];
    RayGameResult result;
    FILE *stream;
    int detection_count;
    int object_count;
    int index;
    if (argc != 5) {
        fprintf(stderr, "usage: sample_photo_probe W H STRIDE RAW\n");
        return 2;
    }
    width = (uint32_t)number(argv[1]);
    height = (uint32_t)number(argv[2]);
    stride = (uint32_t)number(argv[3]);
    bytes = (size_t)height * stride;
    if (width != SAMPLE_PHOTO_WIDTH || height != SAMPLE_PHOTO_HEIGHT ||
        stride != SAMPLE_PHOTO_WIDTH * 3U || bytes > sizeof(frame)) {
        fprintf(stderr, "sample_photo_probe requires packed 1280x720 BGR\n");
        return 2;
    }
    stream = fopen(argv[4], "rb");
    if (!stream || fread(frame, 1, bytes, stream) != bytes) {
        if (stream) fclose(stream);
        return 3;
    }
    fclose(stream);
    detection_count = vision_detect_bgr888(frame, width, height, stride,
                                            detections, VISION_MAX_DETECTIONS);
    if (detection_count < 0) return 4;
    object_count = ray_game_scene_from_detections(detections, detection_count,
                                                  objects, VISION_MAX_DETECTIONS);
    if (object_count < 0 ||
        ray_game_trace(objects, object_count, (float)width, (float)height,
                       &result) != 0)
        return 5;
    for (index = 0; index < detection_count; ++index) {
        const VisionDetection *detection = &detections[index];
        printf("D %s %d %d %d %d %d %d %d %.6f %.6f %d %.6f %.6f %d %d\n",
               vision_type_name(detection->type), detection->center_x,
               detection->center_y, detection->bbox_x, detection->bbox_y,
               detection->bbox_w, detection->bbox_h, detection->angle_deg,
               detection->axis_x, detection->axis_y,
               detection->direction_valid, detection->source_direction_x,
               detection->source_direction_y, detection->source_tip_x,
               detection->source_tip_y);
    }
    printf("R %s %d %d %d", termination_name(result.termination),
           result.success, result.segment_count, result.hit_count);
    for (index = 0; index < result.hit_count; ++index)
        printf(" %s", ray_object_type_name(result.hit_types[index]));
    printf("\n");
    return 0;
}
