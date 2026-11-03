#include "virtual15_lvgl_ui.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VIRTUAL15_LVGL_KEY_B 0xFFU
#define VIRTUAL15_LVGL_KEY_G 0x00U
#define VIRTUAL15_LVGL_KEY_R 0xFFU

static int canvas_valid(const VisionCanvas *canvas)
{
    size_t last;
    if (!canvas || !canvas->data || canvas->width < 1 || canvas->height < 1 ||
        canvas->stride < (unsigned)canvas->width * 3U) return 0;
    if (canvas->capacity < (size_t)(canvas->height - 1) * canvas->stride) return 0;
    last = (size_t)(canvas->height - 1) * canvas->stride +
           (size_t)canvas->width * 3U;
    return last <= canvas->capacity;
}

#if defined(VIRTUAL15_USE_LVGL)
#include "lvgl.h"

static void clear_overlay(VisionCanvas *canvas)
{
    int y;
    if (!canvas_valid(canvas)) return;
    for (y = 0; y < canvas->height; ++y) {
        uint8_t *row = canvas->data + (size_t)y * canvas->stride;
        int x;
        for (x = 0; x < canvas->width; ++x) {
            row[x * 3 + 0] = VIRTUAL15_LVGL_KEY_B;
            row[x * 3 + 1] = VIRTUAL15_LVGL_KEY_G;
            row[x * 3 + 2] = VIRTUAL15_LVGL_KEY_R;
        }
    }
}

#define VIRTUAL15_LVGL_WIDTH 1280U
#define VIRTUAL15_LVGL_HEIGHT 720U
#define VIRTUAL15_LVGL_LINES 32U

typedef struct {
    VisionCanvas *overlay;
    lv_disp_draw_buf_t draw_buf;
    lv_color_t *draw_memory;
    lv_disp_drv_t display;
    lv_obj_t *level_label;
    lv_obj_t *status_label;
    lv_obj_t *timer_label;
} Virtual15LvglImplementation;

static Virtual15LvglImplementation *active_implementation;

static uint8_t expand5(unsigned value)
{
    return (uint8_t)((value * 255U + 15U) / 31U);
}

static uint8_t expand6(unsigned value)
{
    return (uint8_t)((value * 255U + 31U) / 63U);
}

static void flush_rgb565(lv_disp_drv_t *driver, const lv_area_t *area,
                         lv_color_t *color)
{
    Virtual15LvglImplementation *implementation = active_implementation;
    int x, y, width;
    if (!implementation || !implementation->overlay || !area || !color ||
        !canvas_valid(implementation->overlay)) {
        lv_disp_flush_ready(driver);
        return;
    }
    width = area->x2 - area->x1 + 1;
    for (y = area->y1; y <= area->y2; ++y) {
        if (y >= 0 && y < implementation->overlay->height) {
            uint8_t *dst = implementation->overlay->data +
                (size_t)y * implementation->overlay->stride;
            for (x = area->x1; x <= area->x2; ++x) {
                if (x >= 0 && x < implementation->overlay->width) {
                    uint16_t pixel = color[(size_t)(y - area->y1) *
                                           (size_t)width + (size_t)(x - area->x1)].full;
                    unsigned red = expand5((pixel >> 11) & 31U);
                    unsigned green = expand6((pixel >> 5) & 63U);
                    unsigned blue = expand5(pixel & 31U);
                    uint8_t *out = dst + (size_t)x * 3U;
                    out[0] = (uint8_t)blue;
                    out[1] = (uint8_t)green;
                    out[2] = (uint8_t)red;
                }
            }
        }
    }
    lv_disp_flush_ready(driver);
}

static void set_label(lv_obj_t *label, const char *text)
{
    if (label && text) lv_label_set_text(label, text);
}

int virtual15_lvgl_ui_init(Virtual15LvglUi *ui, VisionCanvas *overlay, int enabled)
{
    Virtual15LvglImplementation *implementation;
    lv_disp_drv_t *driver;
    if (!ui || !canvas_valid(overlay)) return 0;
    memset(ui, 0, sizeof(*ui));
    ui->overlay = overlay;
    if (!enabled) return 1;
    if (overlay->width != (int)VIRTUAL15_LVGL_WIDTH ||
        overlay->height != (int)VIRTUAL15_LVGL_HEIGHT) return 0;
    implementation = (Virtual15LvglImplementation *)calloc(1, sizeof(*implementation));
    if (!implementation) return 0;
    implementation->overlay = overlay;
    implementation->draw_memory = (lv_color_t *)calloc(
        VIRTUAL15_LVGL_WIDTH * VIRTUAL15_LVGL_LINES, sizeof(lv_color_t));
    if (!implementation->draw_memory) {
        free(implementation);
        return 0;
    }
    clear_overlay(overlay);
    lv_init();
    lv_disp_draw_buf_init(&implementation->draw_buf, implementation->draw_memory,
                          NULL, VIRTUAL15_LVGL_WIDTH * VIRTUAL15_LVGL_LINES);
    lv_disp_drv_init(&implementation->display);
    driver = &implementation->display;
    driver->hor_res = (lv_coord_t)VIRTUAL15_LVGL_WIDTH;
    driver->ver_res = (lv_coord_t)VIRTUAL15_LVGL_HEIGHT;
    driver->flush_cb = flush_rgb565;
    driver->draw_buf = &implementation->draw_buf;
    /* Keep LVGL in partial-refresh mode. The overlay is cleared before each
     * publication, so only invalidated widget rectangles are converted. A
     * full-refresh flag would require a full-screen LVGL draw buffer and would
     * defeat the small-line-buffer memory saving. */
    driver->full_refresh = 0;
    lv_disp_drv_register(driver);
    implementation->level_label = lv_label_create(lv_scr_act());
    implementation->status_label = lv_label_create(lv_scr_act());
    implementation->timer_label = lv_label_create(lv_scr_act());
    if (!implementation->level_label || !implementation->status_label ||
        !implementation->timer_label) {
        lv_deinit();
        free(implementation->draw_memory);
        free(implementation);
        return 0;
    }
    lv_obj_set_style_text_color(implementation->level_label,
                                lv_color_white(), LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(implementation->status_label,
                                lv_color_white(), LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(implementation->timer_label,
                                lv_color_white(), LV_STATE_DEFAULT);
    lv_obj_set_pos(implementation->level_label, 78, 34);
    lv_obj_set_pos(implementation->status_label, 78, 64);
    lv_obj_set_pos(implementation->timer_label, 1030, 34);
    active_implementation = implementation;
    ui->implementation = implementation;
    ui->enabled = 1;
    ui->initialized = 1;
    return 1;
}

int virtual15_lvgl_ui_update(Virtual15LvglUi *ui, unsigned level,
                             unsigned remaining_seconds, int solved)
{
    Virtual15LvglImplementation *implementation;
    char level_text[40], status_text[40], timer_text[40];
    if (!ui || !ui->initialized || !ui->implementation) return 1;
    implementation = (Virtual15LvglImplementation *)ui->implementation;
    clear_overlay(ui->overlay);
    (void)snprintf(level_text, sizeof(level_text), "LEVEL %02u / 15", level);
    (void)snprintf(status_text, sizeof(status_text), "%s", solved ? "SOLVED" : "VIRTUAL SCENE");
    (void)snprintf(timer_text, sizeof(timer_text), "%03u s", remaining_seconds);
    set_label(implementation->level_label, level_text);
    set_label(implementation->status_label, status_text);
    set_label(implementation->timer_label, timer_text);
    lv_tick_inc(10);
    (void)lv_timer_handler();
    ++ui->updates;
    return 1;
}

int virtual15_lvgl_ui_blend(Virtual15LvglUi *ui, VisionCanvas *target)
{
    int x, y;
    if (!ui || !ui->initialized || !canvas_valid(ui->overlay) || !canvas_valid(target) ||
        ui->overlay->width != target->width || ui->overlay->height != target->height)
        return 0;
    for (y = 0; y < target->height; ++y) {
        const uint8_t *source = ui->overlay->data + (size_t)y * ui->overlay->stride;
        uint8_t *destination = target->data + (size_t)y * target->stride;
        for (x = 0; x < target->width; ++x) {
            const uint8_t *pixel = source + (size_t)x * 3U;
            if (pixel[0] != VIRTUAL15_LVGL_KEY_B ||
                pixel[1] != VIRTUAL15_LVGL_KEY_G ||
                pixel[2] != VIRTUAL15_LVGL_KEY_R)
                memcpy(destination + (size_t)x * 3U, pixel, 3U);
        }
    }
    return 1;
}

void virtual15_lvgl_ui_close(Virtual15LvglUi *ui)
{
    Virtual15LvglImplementation *implementation;
    if (!ui || !ui->implementation) return;
    implementation = (Virtual15LvglImplementation *)ui->implementation;
    if (active_implementation == implementation) active_implementation = NULL;
    free(implementation->draw_memory);
    free(implementation);
    ui->implementation = NULL;
    ui->initialized = 0;
    ui->enabled = 0;
}

#else

int virtual15_lvgl_ui_init(Virtual15LvglUi *ui, VisionCanvas *overlay, int enabled)
{
    if (!ui || !canvas_valid(overlay)) return 0;
    memset(ui, 0, sizeof(*ui));
    ui->overlay = overlay;
    /* The default build deliberately has no LVGL dependency. */
    ui->enabled = 0;
    (void)enabled;
    return 1;
}

int virtual15_lvgl_ui_update(Virtual15LvglUi *ui, unsigned level,
                             unsigned remaining_seconds, int solved)
{
    (void)ui; (void)level; (void)remaining_seconds; (void)solved;
    return 1;
}

int virtual15_lvgl_ui_blend(Virtual15LvglUi *ui, VisionCanvas *target)
{
    (void)ui; (void)target;
    return 1;
}

void virtual15_lvgl_ui_close(Virtual15LvglUi *ui)
{
    if (!ui) return;
    ui->implementation = NULL;
    ui->initialized = 0;
    ui->enabled = 0;
}

#endif
