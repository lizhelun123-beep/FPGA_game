#ifndef VISION_OVERLAY_H
#define VISION_OVERLAY_H
#include "ray_game.h"
#include <stddef.h>

/* Portable BGR888 raster surface. Valid dimensions are 1..16384; only active
 * pixels are written, including on the last row. capacity is the actual
 * accessible span from data, not stride*height inferred by the renderer. */
typedef struct {
    uint8_t *data;
    int width, height;
    size_t stride, capacity;
} VisionCanvas;
typedef struct { double x, y; } VisionPoint;
int vision_canvas_valid(const VisionCanvas *canvas);
void vision_canvas_rect(const VisionCanvas *c, int x, int y, int w, int h, unsigned rgb);
void vision_canvas_line(const VisionCanvas *c, VisionPoint a, VisionPoint b, int radius, unsigned rgb);
void vision_canvas_polygon(const VisionCanvas *c, const VisionPoint *p, int count, unsigned fill, unsigned edge);
void vision_canvas_circle(const VisionCanvas *c, VisionPoint center, double radius, double thickness, unsigned rgb);
/* Transparent 5x7 ASCII from the existing font; unknown bytes are blank. */
void vision_canvas_text(const VisionCanvas *c, int x, int y, const char *s, int scale, unsigned rgb);
unsigned vision_object_color(RayObjectType type);
/* Exact published model geometry, mapped uniformly; no solver or pose update.
 * All shapes are clipped to c, allowing a scene-only subcanvas. */
void vision_canvas_object(const VisionCanvas *c, const SceneObject *o, double scale, double ox, double oy);
void vision_overlay(uint8_t *frame, unsigned width, unsigned height,
                    unsigned stride, const RaySegment *segments, int count,
                    unsigned detected_mask, unsigned hit_mask,
                    unsigned processing_ms);
#if VISION_FIXED_SCENE_DEMO
/* Complete 1280x720 logical-pixel scene; draw only into an idle BGR888 buffer.
 * Objects must be the exact geometry supplied to ray_game_trace. No physics,
 * coordinate mapping, cache operations or VDMA ownership changes occur here. */
void vision_overlay_scene(uint8_t *frame, unsigned width, unsigned height,
                          unsigned stride, const SceneObject *objects, int count,
                          const RayGameResult *ray);
#endif
#endif
