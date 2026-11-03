#ifndef VISION_PORTAL_H
#define VISION_PORTAL_H
#include "vision_ps.h"

/* Optional AprilTag backend of vision_detect_bgr888, not a second detector.
 * Corners use AprilTag's decoded order in measured object millimetres.
 * The result is a local affine camera-pixel projection, not a global plane or
 * lens calibration. +x goes from tag 1 to 2, +y points to the offset tag. */
typedef struct {
    int id, hamming;
    float margin;
    float corners[4][2];
} VisionPortalTag;
typedef struct {
    float corners[3][4][2];
    float center[2], axis[2], length, width;
    float reference_scale, handedness;
} VisionPortalTemplate;

int vision_portal_configure(const VisionPortalTemplate templates[2]);
/* Allocate the shared detector before starting a timed camera frame. */
int vision_portal_initialize(void);
int vision_portal_scan_bgr888(const uint8_t *frame, uint32_t width,
    uint32_t height, uint32_t stride);
int vision_portal_last_tags(VisionPortalTag *tags, int capacity);
/* Diagnostic only, measured on standalone's XTime clock. Sequence identifies
 * whether the Portal backend actually ran on the caller's current frame.
 * quad/decode are nested inside detector_us; do not add them to its total. */
typedef struct {
    uint64_t scan_sequence, grayscale_us, detector_us, quad_us, decode_us, fit_us;
    /* Upstream profiler intervals, all nested inside quad_us. Bits 0..3
     * mark threshold/components/clusters/quad-fit intervals actually seen. */
    uint64_t threshold_us, components_us, clusters_us, fit_quads_us;
    uint32_t quad_stage_mask;
    uint32_t raw_tags, accepted_tags, quads;
    int clock_available;
} VisionPortalTiming;
void vision_portal_last_timing(VisionPortalTiming *timing);
int vision_portal_detect_bgr888(const uint8_t *frame, uint32_t width,
    uint32_t height, uint32_t stride, VisionDetection *output, int capacity);
void vision_portal_shutdown(void);
#endif
