#ifndef VIRTUAL15_LVGL_UI_H
#define VIRTUAL15_LVGL_UI_H

#include "vision_overlay.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Optional presentation-only LVGL layer. The default build uses the small
 * no-op implementation, so the existing virtual15 artifact has no new
 * library or display dependency. When VIRTUAL15_USE_LVGL is defined, the
 * implementation is the LVGL 8.3.x RGB565-to-BGR888 transparent overlay. */
typedef struct {
    VisionCanvas *overlay;
    unsigned updates;
    int enabled;
    int initialized;
    void *implementation;
} Virtual15LvglUi;

int virtual15_lvgl_ui_init(Virtual15LvglUi *ui, VisionCanvas *overlay, int enabled);
int virtual15_lvgl_ui_update(Virtual15LvglUi *ui, unsigned level,
                              unsigned remaining_seconds, int solved);
int virtual15_lvgl_ui_blend(Virtual15LvglUi *ui, VisionCanvas *target);
void virtual15_lvgl_ui_close(Virtual15LvglUi *ui);

#ifdef __cplusplus
}
#endif
#endif
