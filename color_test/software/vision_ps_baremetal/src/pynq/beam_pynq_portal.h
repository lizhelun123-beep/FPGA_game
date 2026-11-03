#ifndef BEAM_PYNQ_PORTAL_H
#define BEAM_PYNQ_PORTAL_H

#include "vision_ps.h"

/* PYNQ 对径向环候选使用统一的置信度下限：严格实心环路径为100，
 * 径向三扇区以上路径为96；低于下限的观测只标记为受限，不终止采集。 */
unsigned beam_pynq_portal_restrictions(const VisionDetection *detections,
                                       int count);

#endif
