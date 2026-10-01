#ifndef VISION_PS_H_
#define VISION_PS_H_

#include <stdint.h>

#include "vision_ps_config.h"

#define VISION_MAX_DETECTIONS 16
typedef enum {
    VISION_MIRROR = 0,
    VISION_PORTAL_A,
    VISION_PORTAL_B,
    VISION_TARGET,
    VISION_SOURCE,
    VISION_WALL
} VisionType;

typedef struct {
    VisionType type;
    int center_x;
    int center_y;
    int bbox_x;
    int bbox_y;
    int bbox_w;
    int bbox_h;
    int angle_deg;
    int confidence_percent;
    uint32_t sampled_area;
} VisionDetection;

/*
 * Process a BGR888 VDMA frame. The function owns static scratch buffers and
 * is intentionally non-reentrant. A negative return value is an input error.
 */
int vision_detect_bgr888(const uint8_t *frame, uint32_t width, uint32_t height,
                         uint32_t stride, VisionDetection *output,
                         int output_capacity);

const char *vision_type_name(VisionType type);

#endif
