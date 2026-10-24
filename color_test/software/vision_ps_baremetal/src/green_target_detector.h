#ifndef GREEN_TARGET_DETECTOR_H_
#define GREEN_TARGET_DETECTOR_H_

#include <stdint.h>

#include "vision_ps.h"

/*
 * Detect pure-green solid circles or annuli in a stride-aware BGR888 frame.
 * Output is sorted by estimated full-resolution green area, largest first.
 * A negative result is an input/configuration error; otherwise it is the
 * number of detections written to output.
 */
int green_target_detect_bgr888(const uint8_t *frame, uint32_t width,
                               uint32_t height, uint32_t stride,
                               VisionDetection *output, int output_capacity);

#endif

