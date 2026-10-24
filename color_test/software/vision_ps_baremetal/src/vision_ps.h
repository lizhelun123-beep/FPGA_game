#ifndef VISION_PS_H_
#define VISION_PS_H_

#include <stdint.h>

#include "vision_ps_config.h"

#define VISION_MAX_DETECTIONS 16
#define VISION_PROBE_SAMPLE_COUNT 5
#define VISION_CALIBRATION_CHANNELS 6

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

#ifdef VISION_PORTAL_DIAGNOSTICS
/* Host-only diagnostic switch used by the video regression. */
void vision_portal_diagnostics_set_type(int type);
#endif

#ifdef VISION_SOURCE_REFINEMENT_DIAGNOSTICS
typedef struct {
    uint32_t coarse_color_triggers;
    uint32_t roi_calls;
    uint32_t roi_pixels;
    uint32_t max_roi_pixels;
    uint32_t refined_color_found;
    uint32_t refined_white_found;
    uint32_t refined_pair_found;
    uint32_t reject_no_color;
    uint32_t reject_no_white;
    uint32_t reject_geometry;
    uint32_t accepted;
    uint32_t best_color_pixels;
    uint32_t best_white_pixels;
    int best_roi_x;
    int best_roi_y;
    int best_roi_w;
    int best_roi_h;
    int best_pair_x;
    int best_pair_y;
    int best_pair_w;
    int best_pair_h;
    float best_nearest_distance;
    float best_center_ratio;
    float best_relative_area;
    float best_pair_fill;
    float best_pair_aspect;
    float best_white_eigen_ratio;
    float best_white_normal;
    float best_attachment;
    float best_taper_ratio;
} VisionSourceRefinementStats;

/* Host-only controls for the 16 sampling-phase Architecture-B regression. */
void vision_source_refinement_set_sampling_phase(uint32_t phase_x,
                                                 uint32_t phase_y);
void vision_source_refinement_get_stats(VisionSourceRefinementStats *stats);
#endif

typedef struct {
    uint8_t minimum[VISION_CALIBRATION_CHANNELS];
    uint8_t maximum[VISION_CALIBRATION_CHANNELS];
    uint32_t sum[VISION_CALIBRATION_CHANNELS];
    uint32_t samples;
} VisionColorStats;

typedef struct {
    VisionType type;
    int center_x;
    int center_y;
    float geometry_center_x;
    float geometry_center_y;
    int bbox_x;
    int bbox_y;
    int bbox_w;
    int bbox_h;
    int angle_deg;
    int confidence_percent;
    uint32_t sampled_area;
    float axis_x;
    float axis_y;
    float major_length;
    float minor_width;
    int source_tip_x;
    int source_tip_y;
    float source_direction_x;
    float source_direction_y;
    int direction_valid;
} VisionDetection;

typedef struct {
    uint8_t minimum[3];
    uint8_t maximum[3];
    uint32_t mean[3];
    uint32_t nonzero[3];
    uint8_t sample_bgr[VISION_PROBE_SAMPLE_COUNT][3];
    uint8_t minimum_all;
    uint8_t maximum_all;
    uint32_t mean_all;
    uint32_t nonzero_all;
    uint32_t green_pixels;
    int green_bbox_x;
    int green_bbox_y;
    int green_bbox_w;
    int green_bbox_h;
    int green_center_x;
    int green_center_y;
    VisionColorStats target_roi;
    VisionColorStats background;
} VisionMinimalProbe;

/*
 * Process a BGR888 VDMA frame. The function owns static scratch buffers and
 * is intentionally non-reentrant. A negative return value is an input error.
 */
int vision_detect_bgr888(const uint8_t *frame, uint32_t width, uint32_t height,
                         uint32_t stride, VisionDetection *output,
                         int output_capacity);

/* Detect the five non-TARGET classes with one shared sampled HSV mask pass. */
int vision_detect_objects_bgr888(const uint8_t *frame, uint32_t width,
                                 uint32_t height, uint32_t stride,
                                 VisionDetection *output,
                                 int output_capacity);

/* Low-interference Stage-1 probe. It scans active BGR888 pixels only, ignores
 * stride padding, and reports the current (not necessarily calibrated) green
 * mask without applying morphology or six-class geometry. */
int vision_minimal_probe_bgr888(const uint8_t *frame, uint32_t width,
                                uint32_t height, uint32_t stride,
                                VisionMinimalProbe *probe);

/* Diagnostic primitives used by host parity tests and UART calibration tools. */
void vision_bgr_to_hsv_pixel(uint8_t b, uint8_t g, uint8_t r,
                             uint8_t *h, uint8_t *s, uint8_t *v);
uint8_t vision_classify_hsv_pixel(uint8_t h, uint8_t s, uint8_t v);

const char *vision_type_name(VisionType type);

#endif
