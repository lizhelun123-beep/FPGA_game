#include "beam_pynq_portal.h"

#include <math.h>

/* 只把 Portal 的质量门控放在 PYNQ 适配层，检测器仍由唯一的
 * VISION_PROFILE_RESTORED 入口完成，避免复制一套颜色或几何检测器。 */
unsigned beam_pynq_portal_restrictions(const VisionDetection *detections,
                                       int count)
{
    unsigned restricted = 0U;
    unsigned seen = 0U;
    int i;
    if (!detections || count < 0 || count > VISION_MAX_DETECTIONS)
        return (1U << VISION_PORTAL_A) | (1U << VISION_PORTAL_B);
    for (i = 0; i < count; ++i) {
        const VisionDetection *d = &detections[i];
        unsigned bit;
        if (d->type != VISION_PORTAL_A && d->type != VISION_PORTAL_B)
            continue;
        bit = 1U << (unsigned)d->type;
        if (seen & bit) {
            restricted |= bit;
            continue;
        }
        seen |= bit;
        if (d->confidence_percent < 96 || !d->geometry_is_effective ||
            !isfinite(d->axis_x) || !isfinite(d->axis_y) ||
            hypotf(d->axis_x, d->axis_y) < 0.5f)
            restricted |= bit;
    }
    return restricted;
}
