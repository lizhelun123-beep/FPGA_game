#ifndef VISION_PS_H_
#define VISION_PS_H_

#include <stdint.h>

#include "vision_ps_config.h"

#define VISION_MAX_DETECTIONS 16

enum {
    VISION_MASK_YELLOW  = 1U << 0,
    VISION_MASK_BLUE    = 1U << 1,
    VISION_MASK_ORANGE  = 1U << 2,
    VISION_MASK_GREEN   = 1U << 3,
    VISION_MASK_MAGENTA = 1U << 4,
    VISION_MASK_BLACK   = 1U << 5,
    VISION_MASK_WHITE   = 1U << 6,
    VISION_MASK_WALL    = 1U << 7
};
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

/* Diagnostic primitives used by host parity tests and UART calibration tools. */
void vision_bgr_to_hsv_pixel(uint8_t b, uint8_t g, uint8_t r,
                             uint8_t *h, uint8_t *s, uint8_t *v);
uint8_t vision_classify_hsv_pixel(uint8_t h, uint8_t s, uint8_t v);

const char *vision_type_name(VisionType type);

#endif
