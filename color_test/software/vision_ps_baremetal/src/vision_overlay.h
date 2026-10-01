#ifndef VISION_OVERLAY_H
#define VISION_OVERLAY_H
#include "vision_ps.h"
void vision_overlay(uint8_t *frame, unsigned width, unsigned height,
                    unsigned stride, const VisionDetection *items, int count,
                    unsigned processing_ms);
#endif
