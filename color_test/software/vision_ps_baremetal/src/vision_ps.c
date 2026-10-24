#include "vision_ps.h"

#include "green_target_detector.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#if defined(VISION_TRACE) || defined(VISION_PORTAL_DIAGNOSTICS)
#include <stdio.h>
#endif

#ifdef VISION_TRACE
#define TRACE(...) fprintf(stderr, __VA_ARGS__)
#else
#define TRACE(...) do { } while (0)
#endif

#ifdef VISION_PORTAL_DIAGNOSTICS
static int portal_diagnostic_type = -1;

void vision_portal_diagnostics_set_type(int type)
{
    portal_diagnostic_type = type;
}
#endif

#define GRID_MAX_W 320
#define GRID_MAX_H 180
#define GRID_MAX_PIXELS (GRID_MAX_W * GRID_MAX_H)

#define BIT_YELLOW  VISION_MASK_YELLOW
#define BIT_BLUE    VISION_MASK_BLUE
#define BIT_ORANGE  VISION_MASK_ORANGE
#define BIT_GREEN   VISION_MASK_GREEN
#define BIT_MAGENTA VISION_MASK_MAGENTA
#define BIT_BLACK   VISION_MASK_BLACK
#define BIT_WHITE   VISION_MASK_WHITE
#define BIT_WALL    VISION_MASK_WALL

#define SOURCE_MARKER_COLOR 0x01U
#define SOURCE_MARKER_WHITE 0x02U

#ifndef VISION_SOURCE_ARCHITECTURE_B_EXPERIMENTAL
#define VISION_SOURCE_ARCHITECTURE_B_EXPERIMENTAL 1
#endif

#if VISION_SOURCE_ARCHITECTURE_B_EXPERIMENTAL
/* Derived from the real-S0/scale Architecture-B ROI sweep.  The optional
 * coarse-white extension improves coverage but is never an entry condition. */
#define SOURCE_REFINE_MARGIN_NUMERATOR 3U
#define SOURCE_REFINE_MARGIN_DENOMINATOR 8U
#define SOURCE_REFINE_MARGIN_MIN 12U
#define SOURCE_REFINE_MARGIN_MAX 24U
#define SOURCE_REFINE_WHITE_PADDING 8U
#define SOURCE_REFINE_WHITE_GAP_CELLS 2.0f
#define SOURCE_REFINE_RETRY_SPAN 240U

/* Deliberately broad full-resolution sanity bounds.  The real-S0 sweep passes
 * all 480 phases; PCA, white-normal, attachment, and taper are diagnostics. */
#define SOURCE_REFINE_NEAREST_MAX 4.0f
#define SOURCE_REFINE_AREA_RATIO_MIN 0.05f
#define SOURCE_REFINE_AREA_RATIO_MAX 8.0f
#define SOURCE_REFINE_CENTER_RATIO_MIN 0.05f
#define SOURCE_REFINE_CENTER_RATIO_MAX 0.90f
#define SOURCE_REFINE_PAIR_ASPECT_MAX 3.0f
#define SOURCE_REFINE_PAIR_FILL_MIN 0.10f
#define SOURCE_REFINE_AXIS_DISTANCE_MAX 6U
#define SOURCE_REFINE_AXIS_MIN_PIXELS 32U
#define SOURCE_REFINE_COMPANION_DISTANCE_MAX 24U
#define SOURCE_REFINE_COMPANION_MIN_PIXELS 100U
#define SOURCE_REFINE_CLEAN_WHITE_EIGEN_MIN 5.0f
#define SOURCE_REFINE_CLEAN_WHITE_ATTACHMENT_MIN 1.0f
#define SOURCE_REFINE_CLEAN_WHITE_AREA_MAX 1.10f
#endif

#define PI_F 3.14159265358979323846f

typedef struct {
    uint32_t count;
    uint32_t min_x;
    uint32_t min_y;
    uint32_t max_x;
    uint32_t max_y;
    uint64_t sum_x;
    uint64_t sum_y;
    uint64_t sum_xx;
    uint64_t sum_yy;
    uint64_t sum_xy;
    uint64_t sum_v;
    uint32_t perimeter;
    uint32_t v_histogram[256];
} Component;

typedef struct {
    float cx;
    float cy;
    float major;
    float minor;
    float ux;
    float uy;
    float aspect;
    float fill;
    float circularity;
    int angle_deg;
} Shape;

typedef struct {
    uint32_t seed;
    uint32_t count;
    uint32_t min_x;
    uint32_t min_y;
    uint32_t max_x;
    uint32_t max_y;
    float cx;
    float cy;
    float ux;
    float uy;
    float aspect;
} SourceMarkerPart;

typedef struct {
    uint32_t total_parts;
    uint32_t kept_parts;
    uint32_t overflow_parts;
    uint8_t region_counts[VISION_SOURCE_MARKER_REGION_COLS *
                          VISION_SOURCE_MARKER_REGION_ROWS];
} SourceMarkerPartStats;

#if VISION_SOURCE_ARCHITECTURE_B_EXPERIMENTAL
typedef struct {
    uint32_t x0;
    uint32_t y0;
    uint32_t x1;
    uint32_t y1;
} SourceRefineRoi;

typedef struct {
    int valid;
    int color_found;
    int white_found;
    int pair_found;
    uint8_t touches_roi;
    uint8_t color_touches_roi;
    uint8_t white_touches_roi;
    SourceRefineRoi roi;
    Component color;
    Component white;
    Shape color_shape;
    Shape white_shape;
    Shape white_axis_shape;
    Shape combined_shape;
    uint32_t color_support;
    uint32_t contact_pixels;
    float white_eigen_ratio;
    float white_normal;
    float nearest_distance;
    float attachment;
    float center_ratio;
    float relative_area;
    float pair_fill;
    float pair_aspect;
    float taper_ratio;
    float direction_x;
    float direction_y;
    float direction_center_x;
    float direction_center_y;
    float robust_tip_projection;
    float selection_score;
} SourceRefinedPair;
#endif

typedef struct {
    uint32_t inner_total;
    uint32_t annulus_total;
    uint32_t annulus_sector_total[4];
    uint32_t annulus_outward_total;
    uint32_t annulus_inward_total;
    uint32_t white_inner;
    uint32_t white_annulus;
    uint32_t white_annulus_sector[4];
    uint32_t white_annulus_outward;
    uint32_t white_annulus_inward;
    uint32_t black_inner;
    uint32_t body_inner;
    uint32_t inner_v_sum;
    uint32_t annulus_v_sum;
} MarkerSample;

typedef struct {
    uint32_t count;
    uint32_t bbox_area;
    float fill;
    float cx;
    float cy;
    float longitudinal;
    float transverse;
    float major;
    float aspect;
    float axis_alignment;
    float center_white;
    float center_body;
    int valid;
} PortalMarkerComponent;

typedef struct {
    PortalMarkerComponent solid;
    PortalMarkerComponent line;
    PortalMarkerComponent ring;
    float score;
    float runner_up_score;
    uint8_t white_v_min;
    int component_count;
    int valid;
} PortalMarkerLayout;

typedef struct {
    Shape shape;
    uint32_t count;
} WallMarker;

static uint8_t pixel_masks[GRID_MAX_PIXELS];
static uint8_t pixel_s[GRID_MAX_PIXELS];
static uint8_t pixel_v[GRID_MAX_PIXELS];
static uint8_t visited[GRID_MAX_PIXELS];
static uint8_t raw_marker_masks[GRID_MAX_PIXELS];
static uint8_t source_marker_masks[GRID_MAX_PIXELS];
static uint8_t wall_marker_mask[GRID_MAX_PIXELS];
static uint8_t morphology_scratch[GRID_MAX_PIXELS];
static uint32_t queue_storage[GRID_MAX_PIXELS];
static uint32_t v_integral[(GRID_MAX_W + 1) * (GRID_MAX_H + 1)];

#ifdef VISION_SOURCE_REFINEMENT_DIAGNOSTICS
static uint32_t source_sample_phase_x = 1U;
static uint32_t source_sample_phase_y = 1U;
static VisionSourceRefinementStats source_refinement_stats;

void vision_source_refinement_set_sampling_phase(uint32_t phase_x,
                                                 uint32_t phase_y)
{
    source_sample_phase_x = phase_x < VISION_SAMPLE_STEP ? phase_x : 1U;
    source_sample_phase_y = phase_y < VISION_SAMPLE_STEP ? phase_y : 1U;
}

void vision_source_refinement_get_stats(VisionSourceRefinementStats *stats)
{
    if (stats) *stats = source_refinement_stats;
}
#else
#define source_sample_phase_x 1U
#define source_sample_phase_y 1U
#endif

static int in_range(int value, int low, int high)
{
    return value >= low && value <= high;
}

static int divide_round_nearest(int numerator, int denominator)
{
    if (numerator >= 0) return (numerator + denominator / 2) / denominator;
    return -((-numerator + denominator / 2) / denominator);
}

void vision_bgr_to_hsv_pixel(uint8_t b, uint8_t g, uint8_t r,
                             uint8_t *h_out, uint8_t *s_out, uint8_t *v_out)
{
    int maximum = r;
    int minimum = r;
    int difference;
    int hue;
    int saturation;

    if (g > maximum) maximum = g;
    if (b > maximum) maximum = b;
    if (g < minimum) minimum = g;
    if (b < minimum) minimum = b;
    difference = maximum - minimum;
    saturation = maximum ? divide_round_nearest(difference * 255, maximum) : 0;
    if (difference == 0) {
        hue = 0;
    } else if (maximum == r) {
        hue = divide_round_nearest(30 * ((int)g - (int)b), difference);
        if (hue < 0) hue += 180;
    } else if (maximum == g) {
        hue = 60 + divide_round_nearest(30 * ((int)b - (int)r), difference);
    } else {
        hue = 120 + divide_round_nearest(30 * ((int)r - (int)g), difference);
    }
    if (hue < 0) hue += 180;
    if (hue > 179) hue -= 180;
    *h_out = (uint8_t)hue;
    *s_out = (uint8_t)saturation;
    *v_out = (uint8_t)maximum;
}

uint8_t vision_classify_hsv_pixel(uint8_t h, uint8_t s, uint8_t v)
{
    uint8_t mask = 0;
    if (in_range(h, VISION_YELLOW_H_MIN, VISION_YELLOW_H_MAX) &&
        s >= VISION_YELLOW_S_MIN && v >= VISION_YELLOW_V_MIN) mask |= BIT_YELLOW;
    if ((in_range(h, VISION_BLUE_H_MIN, VISION_BLUE_H_MAX) &&
         ((s >= VISION_BLUE_S_MIN && v >= VISION_BLUE_V_MIN) ||
          (in_range(s, VISION_BLUE_WASHED_S_MIN,
                       VISION_BLUE_WASHED_S_MAX) &&
           in_range(v, VISION_BLUE_V_MIN, VISION_BLUE_WASHED_V_MAX)))) ||
        (in_range(h, VISION_BLUE_SHADOW_H_MIN, VISION_BLUE_SHADOW_H_MAX) &&
         in_range(s, VISION_BLUE_SHADOW_S_MIN, VISION_BLUE_SHADOW_S_MAX) &&
         in_range(v, VISION_BLUE_SHADOW_V_MIN, VISION_BLUE_SHADOW_V_MAX)))
        mask |= BIT_BLUE;
    if (in_range(h, VISION_ORANGE_H_MIN, VISION_ORANGE_H_MAX) &&
        s >= VISION_ORANGE_S_MIN && v >= VISION_ORANGE_V_MIN) mask |= BIT_ORANGE;
    if (in_range(h, VISION_GREEN_H_MIN, VISION_GREEN_H_MAX) &&
        s >= VISION_GREEN_S_MIN && v >= VISION_GREEN_V_MIN) mask |= BIT_GREEN;
    if (in_range(h, VISION_MAGENTA_H_MIN, VISION_MAGENTA_H_MAX) &&
        s >= VISION_MAGENTA_S_MIN && v >= VISION_MAGENTA_V_MIN) mask |= BIT_MAGENTA;
    if (v <= VISION_BLACK_V_MAX) mask |= BIT_BLACK;
    if (h <= VISION_WHITE_H_MAX && s <= VISION_WHITE_S_MAX &&
        v >= VISION_WHITE_V_MIN) mask |= BIT_WHITE;
    if (v <= VISION_WALL_V_MAX) mask |= BIT_WALL;
    return mask;
}

int vision_minimal_probe_bgr888(const uint8_t *frame, uint32_t width,
                                uint32_t height, uint32_t stride,
                                VisionMinimalProbe *probe)
{
    static const uint8_t sample_x_num[VISION_PROBE_SAMPLE_COUNT] = {0, 1, 1, 3, 1};
    static const uint8_t sample_x_den[VISION_PROBE_SAMPLE_COUNT] = {1, 4, 2, 4, 1};
    static const uint8_t sample_y_num[VISION_PROBE_SAMPLE_COUNT] = {0, 1, 1, 3, 1};
    static const uint8_t sample_y_den[VISION_PROBE_SAMPLE_COUNT] = {1, 4, 2, 4, 1};
    uint32_t sum[3] = {0, 0, 0};
    uint32_t sum_all = 0;
    uint32_t sum_x = 0;
    uint32_t sum_y = 0;
    uint32_t pixels;
    uint32_t x;
    uint32_t y;
    unsigned channel;
    unsigned sample;

    if (!frame || !probe || !width || !height || stride < width * 3U) return -1;
    memset(probe, 0, sizeof(*probe));
    probe->minimum[0] = probe->minimum[1] = probe->minimum[2] = 255U;
    probe->minimum_all = 255U;
    for (channel = 0; channel < VISION_CALIBRATION_CHANNELS; ++channel) {
        probe->target_roi.minimum[channel] = 255U;
        probe->background.minimum[channel] = 255U;
    }
    probe->green_bbox_x = probe->green_bbox_y = -1;
    probe->green_center_x = probe->green_center_y = -1;
    pixels = width * height;

    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            const uint8_t *pixel = frame + y * stride + x * 3U;
            uint8_t h;
            uint8_t s;
            uint8_t v;
            for (channel = 0; channel < 3; ++channel) {
                uint8_t value = pixel[channel];
                if (value < probe->minimum[channel]) probe->minimum[channel] = value;
                if (value > probe->maximum[channel]) probe->maximum[channel] = value;
                if (value < probe->minimum_all) probe->minimum_all = value;
                if (value > probe->maximum_all) probe->maximum_all = value;
                sum[channel] += value;
                sum_all += value;
                if (value) {
                    ++probe->nonzero[channel];
                    ++probe->nonzero_all;
                }
            }
            vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
            {
                VisionColorStats *stats = NULL;
                uint8_t values[VISION_CALIBRATION_CHANNELS] = {
                    pixel[0], pixel[1], pixel[2], h, s, v
                };
                int target_roi = x >= width / 4U && x < 3U * width / 4U &&
                    y >= height / 4U && y < 3U * height / 4U;
                /* This relation only selects samples for calibration; it is
                 * not the final camera threshold. Black/white marker pixels
                 * and gray background are intentionally excluded. */
                if (target_roi && pixel[1] > pixel[0] && pixel[1] > pixel[2])
                    stats = &probe->target_roi;
                else if (!target_roi)
                    stats = &probe->background;
                if (stats) {
                    for (channel = 0; channel < VISION_CALIBRATION_CHANNELS; ++channel) {
                        if (values[channel] < stats->minimum[channel])
                            stats->minimum[channel] = values[channel];
                        if (values[channel] > stats->maximum[channel])
                            stats->maximum[channel] = values[channel];
                        stats->sum[channel] += values[channel];
                    }
                    ++stats->samples;
                }
            }
            if (vision_classify_hsv_pixel(h, s, v) & VISION_MASK_GREEN) {
                if (!probe->green_pixels) {
                    probe->green_bbox_x = (int)x;
                    probe->green_bbox_y = (int)y;
                    probe->green_bbox_w = 1;
                    probe->green_bbox_h = 1;
                } else {
                    int x1 = probe->green_bbox_x + probe->green_bbox_w - 1;
                    int y1 = probe->green_bbox_y + probe->green_bbox_h - 1;
                    if ((int)x < probe->green_bbox_x) probe->green_bbox_x = (int)x;
                    if ((int)y < probe->green_bbox_y) probe->green_bbox_y = (int)y;
                    if ((int)x > x1) x1 = (int)x;
                    if ((int)y > y1) y1 = (int)y;
                    probe->green_bbox_w = x1 - probe->green_bbox_x + 1;
                    probe->green_bbox_h = y1 - probe->green_bbox_y + 1;
                }
                ++probe->green_pixels;
                sum_x += x;
                sum_y += y;
            }
        }
    }
    for (channel = 0; channel < 3; ++channel) probe->mean[channel] = sum[channel] / pixels;
    probe->mean_all = sum_all / (pixels * 3U);
    if (probe->green_pixels) {
        probe->green_center_x = (int)(sum_x / probe->green_pixels);
        probe->green_center_y = (int)(sum_y / probe->green_pixels);
    }
    for (sample = 0; sample < VISION_PROBE_SAMPLE_COUNT; ++sample) {
        uint32_t sx = sample_x_num[sample] == sample_x_den[sample] ?
            width - 1U : width * sample_x_num[sample] / sample_x_den[sample];
        uint32_t sy = sample_y_num[sample] == sample_y_den[sample] ?
            height - 1U : height * sample_y_num[sample] / sample_y_den[sample];
        const uint8_t *pixel = frame + sy * stride + sx * 3U;
        probe->sample_bgr[sample][0] = pixel[0];
        probe->sample_bgr[sample][1] = pixel[1];
        probe->sample_bgr[sample][2] = pixel[2];
    }
    return 0;
}

/* OpenCV's 3x3 MORPH_ELLIPSE is a cross. Its default border is true for
 * erosion and false for dilation, represented here by skipping out-of-frame
 * neighbors for erosion and considering only in-frame neighbors for dilation. */
static void erode_cross(const uint8_t *source, uint8_t *destination,
                        uint32_t grid_w, uint32_t grid_h)
{
    uint32_t y;
    for (y = 0; y < grid_h; ++y) {
        uint32_t x;
        for (x = 0; x < grid_w; ++x) {
            uint32_t index = y * grid_w + x;
            uint8_t value = source[index];
            if (x) value &= source[index - 1U];
            if (x + 1U < grid_w) value &= source[index + 1U];
            if (y) value &= source[index - grid_w];
            if (y + 1U < grid_h) value &= source[index + grid_w];
            destination[index] = value;
        }
    }
}

static void dilate_cross(const uint8_t *source, uint8_t *destination,
                         uint32_t grid_w, uint32_t grid_h)
{
    uint32_t y;
    for (y = 0; y < grid_h; ++y) {
        uint32_t x;
        for (x = 0; x < grid_w; ++x) {
            uint32_t index = y * grid_w + x;
            uint8_t value = source[index];
            if (x) value |= source[index - 1U];
            if (x + 1U < grid_w) value |= source[index + 1U];
            if (y) value |= source[index - grid_w];
            if (y + 1U < grid_h) value |= source[index + grid_w];
            destination[index] = value;
        }
    }
}

static void morphology_open_close(uint8_t *masks, uint8_t *scratch,
                                  uint32_t width, uint32_t height)
{
#if VISION_MORPHOLOGY_ENABLE
    erode_cross(masks, scratch, width, height);
    dilate_cross(scratch, masks, width, height);
    dilate_cross(masks, scratch, width, height);
    erode_cross(scratch, masks, width, height);
#else
    (void)masks;
    (void)scratch;
    (void)width;
    (void)height;
#endif
}

static void refine_wall_mask(uint32_t grid_w, uint32_t grid_h)
{
    uint32_t pitch = grid_w + 1U;
    uint32_t y;
    memset(v_integral, 0, (size_t)(grid_h + 1U) * pitch * sizeof(v_integral[0]));
    for (y = 0; y < grid_h; ++y) {
        uint32_t row_sum = 0;
        uint32_t x;
        for (x = 0; x < grid_w; ++x) {
            row_sum += pixel_v[y * grid_w + x];
            v_integral[(y + 1U) * pitch + x + 1U] =
                v_integral[y * pitch + x + 1U] + row_sum;
        }
    }
    for (y = 0; y < grid_h; ++y) {
        uint32_t x;
        uint32_t y0 = y > VISION_WALL_LOCAL_RADIUS ?
            y - VISION_WALL_LOCAL_RADIUS : 0U;
        uint32_t y1 = y + VISION_WALL_LOCAL_RADIUS + 1U;
        uint32_t marker_y0 = y > VISION_WALL_MARKER_LOCAL_RADIUS ?
            y - VISION_WALL_MARKER_LOCAL_RADIUS : 0U;
        uint32_t marker_y1 = y + VISION_WALL_MARKER_LOCAL_RADIUS + 1U;
        if (y1 > grid_h) y1 = grid_h;
        if (marker_y1 > grid_h) marker_y1 = grid_h;
        for (x = 0; x < grid_w; ++x) {
            uint32_t x0 = x > VISION_WALL_LOCAL_RADIUS ?
                x - VISION_WALL_LOCAL_RADIUS : 0U;
            uint32_t x1 = x + VISION_WALL_LOCAL_RADIUS + 1U;
            uint32_t marker_x0 = x > VISION_WALL_MARKER_LOCAL_RADIUS ?
                x - VISION_WALL_MARKER_LOCAL_RADIUS : 0U;
            uint32_t marker_x1 = x + VISION_WALL_MARKER_LOCAL_RADIUS + 1U;
            uint32_t count;
            uint32_t sum;
            uint32_t marker_count;
            uint32_t marker_sum;
            uint32_t index = y * grid_w + x;
            if (x1 > grid_w) x1 = grid_w;
            if (marker_x1 > grid_w) marker_x1 = grid_w;
            count = (x1 - x0) * (y1 - y0);
            sum = v_integral[y1 * pitch + x1] - v_integral[y0 * pitch + x1] -
                  v_integral[y1 * pitch + x0] + v_integral[y0 * pitch + x0];
            marker_count = (marker_x1-marker_x0) * (marker_y1-marker_y0);
            marker_sum = v_integral[marker_y1*pitch+marker_x1] -
                         v_integral[marker_y0*pitch+marker_x1] -
                         v_integral[marker_y1*pitch+marker_x0] +
                         v_integral[marker_y0*pitch+marker_x0];
            pixel_masks[index] &= (uint8_t)~BIT_WALL;
            if (pixel_v[index] <= VISION_WALL_V_MAX &&
                sum >= ((uint32_t)pixel_v[index] + VISION_WALL_LOCAL_DELTA) * count)
                pixel_masks[index] |= BIT_WALL;
            wall_marker_mask[index] =
                pixel_s[index] <= VISION_WALL_MARKER_S_MAX &&
                pixel_v[index] >= VISION_WALL_MARKER_V_MIN &&
                (uint32_t)pixel_v[index] * marker_count >=
                    marker_sum + VISION_WALL_MARKER_LOCAL_DELTA * marker_count;
        }
    }
}

static void create_masks(const uint8_t *frame, uint32_t stride,
                         uint32_t grid_w, uint32_t grid_h)
{
    uint32_t y;
    for (y = 0; y < grid_h; ++y) {
        uint32_t x;
        uint32_t source_y = y * VISION_SAMPLE_STEP + source_sample_phase_y;
        for (x = 0; x < grid_w; ++x) {
            uint32_t source_x = x * VISION_SAMPLE_STEP + source_sample_phase_x;
            const uint8_t *pixel = frame + source_y * stride + source_x * 3U;
            uint8_t b = pixel[0];
            uint8_t g = pixel[1];
            uint8_t r = pixel[2];
            uint8_t h;
            uint8_t s;
            uint8_t v;
            uint32_t index = y * grid_w + x;
            vision_bgr_to_hsv_pixel(b, g, r, &h, &s, &v);
            pixel_masks[index] = vision_classify_hsv_pixel(h, s, v);
            raw_marker_masks[index] = pixel_masks[index] & (BIT_BLACK | BIT_WHITE);
            source_marker_masks[index] = 0U;
            if (pixel_masks[index] & BIT_MAGENTA)
                source_marker_masks[index] |= SOURCE_MARKER_COLOR;
            if (s <= VISION_SOURCE_MARKER_WHITE_S_MAX &&
                v >= VISION_SOURCE_MARKER_WHITE_V_MIN)
                source_marker_masks[index] |= SOURCE_MARKER_WHITE;
            pixel_s[index] = s;
            pixel_v[index] = v;
        }
    }
    refine_wall_mask(grid_w, grid_h);
    /* Body masks benefit from denoising, but a sampled Portal ring may only be
     * one cell thick and must not be destroyed by the erosion stage. */
    morphology_open_close(pixel_masks, morphology_scratch, grid_w, grid_h);
    for (y = 0; y < grid_h * grid_w; ++y)
        pixel_masks[y] = (pixel_masks[y] & (uint8_t)~(BIT_BLACK | BIT_WHITE)) |
                         raw_marker_masks[y];
}

static void component_reset(Component *component, uint32_t x, uint32_t y)
{
    memset(component, 0, sizeof(*component));
    component->min_x = component->max_x = x;
    component->min_y = component->max_y = y;
}

static void component_add(Component *component, uint32_t x, uint32_t y,
                          uint8_t value)
{
    component->count++;
    if (x < component->min_x) component->min_x = x;
    if (x > component->max_x) component->max_x = x;
    if (y < component->min_y) component->min_y = y;
    if (y > component->max_y) component->max_y = y;
    component->sum_x += x;
    component->sum_y += y;
    component->sum_xx += (uint64_t)x * x;
    component->sum_yy += (uint64_t)y * y;
    component->sum_xy += (uint64_t)x * y;
    component->sum_v += value;
    component->v_histogram[value]++;
}

static void collect_component(uint32_t seed, uint8_t bit, uint32_t grid_w,
                              uint32_t grid_h, Component *component)
{
    static const int8_t nx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    static const int8_t ny[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t seed_x = seed % grid_w;
    uint32_t seed_y = seed / grid_w;
    component_reset(component, seed_x, seed_y);
    visited[seed] = 1;
    queue_storage[tail++] = seed;
    while (head < tail) {
        uint32_t index = queue_storage[head++];
        uint32_t x = index % grid_w;
        uint32_t y = index / grid_w;
        int direction;
        component_add(component, x, y, pixel_v[index]);
        if (x == 0 || !(pixel_masks[index-1] & bit)) component->perimeter++;
        if (x+1 == grid_w || !(pixel_masks[index+1] & bit)) component->perimeter++;
        if (y == 0 || !(pixel_masks[index-grid_w] & bit)) component->perimeter++;
        if (y+1 == grid_h || !(pixel_masks[index+grid_w] & bit)) component->perimeter++;
        for (direction = 0; direction < 8; ++direction) {
            int xx = (int)x + nx[direction];
            int yy = (int)y + ny[direction];
            uint32_t neighbor;
            if (xx < 0 || yy < 0 || xx >= (int)grid_w || yy >= (int)grid_h) continue;
            neighbor = (uint32_t)yy * grid_w + (uint32_t)xx;
            if (!visited[neighbor] && (pixel_masks[neighbor] & bit)) {
                visited[neighbor] = 1;
                queue_storage[tail++] = neighbor;
            }
        }
    }
}

static void collect_wall_marker_component(uint32_t seed, uint32_t grid_w,
                                          uint32_t grid_h,
                                          Component *component)
{
    static const int8_t nx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    static const int8_t ny[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t seed_x = seed % grid_w;
    uint32_t seed_y = seed / grid_w;
    component_reset(component, seed_x, seed_y);
    visited[seed] = 1;
    queue_storage[tail++] = seed;
    while (head < tail) {
        uint32_t index = queue_storage[head++];
        uint32_t x = index % grid_w;
        uint32_t y = index / grid_w;
        int direction;
        component_add(component, x, y, pixel_v[index]);
        if (x == 0 || !wall_marker_mask[index-1]) component->perimeter++;
        if (x+1 == grid_w || !wall_marker_mask[index+1]) component->perimeter++;
        if (y == 0 || !wall_marker_mask[index-grid_w]) component->perimeter++;
        if (y+1 == grid_h || !wall_marker_mask[index+grid_w]) component->perimeter++;
        for (direction = 0; direction < 8; ++direction) {
            int xx = (int)x + nx[direction];
            int yy = (int)y + ny[direction];
            uint32_t neighbor;
            if (xx < 0 || yy < 0 || xx >= (int)grid_w || yy >= (int)grid_h)
                continue;
            neighbor = (uint32_t)yy * grid_w + (uint32_t)xx;
            if (!visited[neighbor] && wall_marker_mask[neighbor]) {
                visited[neighbor] = 1;
                queue_storage[tail++] = neighbor;
            }
        }
    }
}

static void collect_source_marker_component(uint32_t seed, uint8_t marker_bit,
                                            uint32_t grid_w, uint32_t grid_h,
                                            Component *component)
{
    static const int8_t nx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    static const int8_t ny[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t seed_x = seed % grid_w;
    uint32_t seed_y = seed / grid_w;
    component_reset(component, seed_x, seed_y);
    visited[seed] = 1;
    queue_storage[tail++] = seed;
    while (head < tail) {
        uint32_t index = queue_storage[head++];
        uint32_t x = index % grid_w;
        uint32_t y = index / grid_w;
        int direction;
        component_add(component, x, y, pixel_v[index]);
        if (x == 0 || !(source_marker_masks[index-1] & marker_bit))
            component->perimeter++;
        if (x+1 == grid_w || !(source_marker_masks[index+1] & marker_bit))
            component->perimeter++;
        if (y == 0 || !(source_marker_masks[index-grid_w] & marker_bit))
            component->perimeter++;
        if (y+1 == grid_h || !(source_marker_masks[index+grid_w] & marker_bit))
            component->perimeter++;
        for (direction = 0; direction < 8; ++direction) {
            int xx = (int)x + nx[direction];
            int yy = (int)y + ny[direction];
            uint32_t neighbor;
            if (xx < 0 || yy < 0 || xx >= (int)grid_w || yy >= (int)grid_h)
                continue;
            neighbor = (uint32_t)yy * grid_w + (uint32_t)xx;
            if (!visited[neighbor] &&
                (source_marker_masks[neighbor] & marker_bit)) {
                visited[neighbor] = 1;
                queue_storage[tail++] = neighbor;
            }
        }
    }
}

static int describe_component(const Component *component, Shape *shape)
{
    float count = (float)component->count;
    float cov_xx;
    float cov_yy;
    float cov_xy;
    float root;
    float lambda_max;
    float lambda_min;
    float angle;
    if (component->count < 2) return 0;
    shape->cx = (float)component->sum_x / count;
    shape->cy = (float)component->sum_y / count;
    cov_xx = (float)component->sum_xx / count - shape->cx * shape->cx;
    cov_yy = (float)component->sum_yy / count - shape->cy * shape->cy;
    cov_xy = (float)component->sum_xy / count - shape->cx * shape->cy;
    root = sqrtf((cov_xx-cov_yy)*(cov_xx-cov_yy) + 4.0f*cov_xy*cov_xy);
    lambda_max = 0.5f * (cov_xx + cov_yy + root);
    lambda_min = 0.5f * (cov_xx + cov_yy - root);
    if (lambda_min < 0.05f || lambda_max <= 0.0f) return 0;
    shape->major = sqrtf(12.0f * lambda_max) + 1.0f;
    shape->minor = sqrtf(12.0f * lambda_min) + 1.0f;
    shape->aspect = shape->major / shape->minor;
    angle = 0.5f * atan2f(2.0f * cov_xy, cov_xx-cov_yy);
    shape->ux = cosf(angle);
    shape->uy = sinf(angle);
    shape->angle_deg = (int)lroundf(angle * 180.0f / PI_F);
    if (shape->angle_deg >= 90) shape->angle_deg -= 180;
    if (shape->angle_deg < -90) shape->angle_deg += 180;
    shape->fill = count / (shape->major * shape->minor);
    if (shape->fill > 1.0f) shape->fill = 1.0f;
    shape->circularity = component->perimeter ?
        (4.0f * PI_F * count) / ((float)component->perimeter * component->perimeter) : 0.0f;
    return 1;
}

static float fraction(uint32_t numerator, uint32_t denominator)
{
    return denominator ? (float)numerator / (float)denominator : 0.0f;
}

static void sample_marker(const uint8_t *frame, uint32_t width, uint32_t height,
                          uint32_t stride, float grid_cx, float grid_cy,
                          float grid_radius, uint8_t body_bit,
                          float outward_x, float outward_y,
                          MarkerSample *sample)
{
    float cx = grid_cx * VISION_SAMPLE_STEP + 1.0f;
    float cy = grid_cy * VISION_SAMPLE_STEP + 1.0f;
    float radius = grid_radius * VISION_SAMPLE_STEP;
    int x0 = (int)floorf(cx-radius);
    int x1 = (int)ceilf(cx+radius);
    int y0 = (int)floorf(cy-radius);
    int y1 = (int)ceilf(cy+radius);
    float inner_sq = radius * radius * 0.16f;
    float outer_sq = radius * radius;
    int y;
    memset(sample, 0, sizeof(*sample));
    for (y = y0; y <= y1; ++y) {
        int x;
        if (y < 0 || y >= (int)height) continue;
        for (x = x0; x <= x1; ++x) {
            float dx;
            float dy;
            float distance_sq;
            uint8_t h;
            uint8_t s;
            uint8_t v;
            uint8_t bits;
            const uint8_t *pixel;
            if (x < 0 || x >= (int)width) continue;
            dx = (float)x - cx;
            dy = (float)y - cy;
            distance_sq = dx*dx + dy*dy;
            if (distance_sq > outer_sq) continue;
            pixel = frame + (uint32_t)y * stride + (uint32_t)x * 3U;
            vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
            bits = vision_classify_hsv_pixel(h, s, v);
            if (distance_sq <= inner_sq) {
                sample->inner_total++;
                sample->inner_v_sum += v;
                if (bits & BIT_WHITE) sample->white_inner++;
                if (bits & BIT_BLACK) sample->black_inner++;
                if (bits & body_bit) sample->body_inner++;
            } else if (distance_sq >= outer_sq * 0.36f) {
                unsigned int sector;
                int outward = dx*outward_x + dy*outward_y >= 0.0f;
                if (dy < 0.0f)
                    sector = dx >= 0.0f ? 0U : 1U;
                else
                    sector = dx < 0.0f ? 2U : 3U;
                sample->annulus_total++;
                sample->annulus_sector_total[sector]++;
                if (outward)
                    sample->annulus_outward_total++;
                else
                    sample->annulus_inward_total++;
                sample->annulus_v_sum += v;
                if (bits & BIT_WHITE) {
                    sample->white_annulus++;
                    sample->white_annulus_sector[sector]++;
                    if (outward)
                        sample->white_annulus_outward++;
                    else
                        sample->white_annulus_inward++;
                }
            }
        }
    }
}

static void endpoint_samples(const uint8_t *frame, uint32_t width,
                             uint32_t height, uint32_t stride,
                             const Shape *shape, uint8_t body_bit,
                             float offset_fraction, float transverse_fraction,
                             MarkerSample *first, MarkerSample *second)
{
    float offset = shape->major * offset_fraction;
    float transverse = shape->minor * transverse_fraction;
    float radius = shape->minor * VISION_MARKER_RADIUS;
    if (radius < 2.0f) radius = 2.0f;
    sample_marker(frame, width, height, stride,
                  shape->cx-shape->ux*offset-shape->uy*transverse,
                  shape->cy-shape->uy*offset+shape->ux*transverse,
                  radius, body_bit, -shape->ux, -shape->uy, first);
    sample_marker(frame, width, height, stride,
                  shape->cx+shape->ux*offset-shape->uy*transverse,
                  shape->cy+shape->uy*offset+shape->ux*transverse,
                  radius, body_bit, shape->ux, shape->uy, second);
}

static int portal_line_component_ok(const PortalMarkerComponent *component)
{
    return component->valid && fabsf(component->longitudinal) <= 0.30f &&
           fabsf(component->transverse) <= 0.65f &&
           component->aspect >= 2.50f &&
           component->axis_alignment >= 0.90f;
}

static int portal_solid_component_ok(const PortalMarkerComponent *component)
{
    return component->valid && component->aspect <= 1.85f &&
           component->fill >= 0.50f &&
           component->center_white >= 0.55f;
}

static int portal_ring_component_ok(const PortalMarkerComponent *component)
{
    return component->valid && component->aspect <= 2.00f &&
           component->fill >= 0.15f &&
           component->fill <= 0.75f && component->center_white <= 0.30f &&
           component->center_body >= 0.20f;
}

static int verify_portal_marker_layout(
    VisionType type, uint8_t body_bit, const Shape *shape,
    const uint8_t *frame, uint32_t width, uint32_t height, uint32_t stride,
    int *angle_deg)
{
    enum { PORTAL_COMPONENT_MAX = 16 };
    static const int neighbor_x[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    static const int neighbor_y[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    PortalMarkerComponent components[PORTAL_COMPONENT_MAX];
    PortalMarkerLayout layout;
    uint32_t body_v_histogram[256];
    float shape_center_x = shape->cx*VISION_SAMPLE_STEP+1.0f;
    float shape_center_y = shape->cy*VISION_SAMPLE_STEP+1.0f;
    float major = shape->major*VISION_SAMPLE_STEP;
    float minor = shape->minor*VISION_SAMPLE_STEP;
    float half_x = fabsf(shape->ux)*major*0.70f+
                   fabsf(shape->uy)*minor*0.78f;
    float half_y = fabsf(shape->uy)*major*0.70f+
                   fabsf(shape->ux)*minor*0.78f;
    int x0 = (int)floorf(shape_center_x-half_x);
    int y0 = (int)floorf(shape_center_y-half_y);
    int x1 = (int)ceilf(shape_center_x+half_x);
    int y1 = (int)ceilf(shape_center_y+half_y);
    uint32_t roi_width;
    uint32_t roi_height;
    uint32_t roi_pixels;
    uint32_t body_pixels = 0U;
    uint32_t body_median_target;
    uint32_t body_median_sum = 0U;
    unsigned int body_median = 0U;
    uint32_t seed;
    int component_count = 0;
    int line_index;
    int best_solid_index = -1;
    int best_line_index = -1;
    int best_ring_index = -1;
    float best_score = -1000.0f;
    float runner_up_score = -1000.0f;
    (void)type;
    memset(&layout, 0, sizeof(layout));
    memset(components, 0, sizeof(components));
    memset(body_v_histogram, 0, sizeof(body_v_histogram));
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= (int)width) x1 = (int)width-1;
    if (y1 >= (int)height) y1 = (int)height-1;
    if (x1 < x0 || y1 < y0) return 0;
    roi_width = (uint32_t)(x1-x0+1);
    roi_height = (uint32_t)(y1-y0+1);
    roi_pixels = roi_width*roi_height;
    if (roi_pixels > GRID_MAX_PIXELS) return 0;

    for (seed = 0U; seed < roi_pixels; ++seed) {
        uint32_t local_x = seed%roi_width;
        uint32_t local_y = seed/roi_width;
        int x = x0+(int)local_x;
        int y = y0+(int)local_y;
        float dx = (float)x-shape_center_x;
        float dy = (float)y-shape_center_y;
        float longitudinal = (dx*shape->ux+dy*shape->uy)/major;
        float transverse = (-dx*shape->uy+dy*shape->ux)/minor;
        const uint8_t *pixel;
        uint8_t h;
        uint8_t s;
        uint8_t v;
        uint8_t bits;
        if (fabsf(longitudinal) > 0.70f || fabsf(transverse) > 0.78f)
            continue;
        pixel = frame+(uint32_t)y*stride+(uint32_t)x*3U;
        vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
        bits = vision_classify_hsv_pixel(h, s, v);
        if (bits & body_bit) {
            body_v_histogram[v]++;
            body_pixels++;
        }
    }
    if (!body_pixels) return 0;
    body_median_target = body_pixels/2U;
    for (body_median = 0U; body_median < 256U; ++body_median) {
        body_median_sum += body_v_histogram[body_median];
        if (body_median_sum > body_median_target) break;
    }
    if (body_median >= 256U) body_median = 255U;
    layout.white_v_min = (uint8_t)(body_median+(255U-body_median+4U)/5U);
    if (layout.white_v_min < VISION_WHITE_V_MIN)
        layout.white_v_min = VISION_WHITE_V_MIN;

    memset(morphology_scratch, 0, roi_pixels);
    for (seed = 0U; seed < roi_pixels; ++seed) {
        uint32_t local_x = seed%roi_width;
        uint32_t local_y = seed/roi_width;
        int x = x0+(int)local_x;
        int y = y0+(int)local_y;
        float dx = (float)x-shape_center_x;
        float dy = (float)y-shape_center_y;
        float longitudinal = (dx*shape->ux+dy*shape->uy)/major;
        float transverse = (-dx*shape->uy+dy*shape->ux)/minor;
        const uint8_t *pixel;
        uint8_t h;
        uint8_t s;
        uint8_t v;
        if (fabsf(longitudinal) > 0.70f || fabsf(transverse) > 0.78f)
            continue;
        pixel = frame+(uint32_t)y*stride+(uint32_t)x*3U;
        vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
        if (v >= layout.white_v_min &&
            (vision_classify_hsv_pixel(h, s, v) & BIT_WHITE))
            morphology_scratch[seed] = 1U;
    }

    for (seed = 0U; seed < roi_pixels; ++seed) {
        uint32_t head = 0U;
        uint32_t tail = 0U;
        uint32_t count = 0U;
        uint32_t min_x = 0U;
        uint32_t min_y = 0U;
        uint32_t max_x = 0U;
        uint32_t max_y = 0U;
        uint64_t sum_x = 0U;
        uint64_t sum_y = 0U;
        uint64_t sum_xx = 0U;
        uint64_t sum_yy = 0U;
        uint64_t sum_xy = 0U;
        PortalMarkerComponent component;
        if (morphology_scratch[seed] != 1U) continue;
        morphology_scratch[seed] = 2U;
        v_integral[tail++] = seed;
        while (head < tail) {
            uint32_t current = v_integral[head++];
            uint32_t local_x = current%roi_width;
            uint32_t local_y = current/roi_width;
            unsigned int neighbor;
            if (!count || local_x < min_x) min_x = local_x;
            if (!count || local_x > max_x) max_x = local_x;
            if (!count || local_y < min_y) min_y = local_y;
            if (!count || local_y > max_y) max_y = local_y;
            count++;
            sum_x += local_x;
            sum_y += local_y;
            sum_xx += (uint64_t)local_x*local_x;
            sum_yy += (uint64_t)local_y*local_y;
            sum_xy += (uint64_t)local_x*local_y;
            for (neighbor = 0U; neighbor < 8U; ++neighbor) {
                int xx = (int)local_x+neighbor_x[neighbor];
                int yy = (int)local_y+neighbor_y[neighbor];
                uint32_t next;
                if (xx < 0 || yy < 0 || xx >= (int)roi_width ||
                    yy >= (int)roi_height)
                    continue;
                next = (uint32_t)yy*roi_width+(uint32_t)xx;
                if (morphology_scratch[next] != 1U) continue;
                morphology_scratch[next] = 2U;
                v_integral[tail++] = next;
            }
        }
        if (count < VISION_PORTAL_MARKER_COMPONENT_MIN_PIXELS ||
            component_count >= PORTAL_COMPONENT_MAX)
            continue;
        memset(&component, 0, sizeof(component));
        component.count = count;
        component.bbox_area = (max_x-min_x+1U)*(max_y-min_y+1U);
        component.fill = fraction(count, component.bbox_area);
        component.cx = (float)x0+(float)sum_x/(float)count;
        component.cy = (float)y0+(float)sum_y/(float)count;
        {
            float local_cx = (float)sum_x/(float)count;
            float local_cy = (float)sum_y/(float)count;
            float cov_xx = (float)sum_xx/(float)count-local_cx*local_cx;
            float cov_yy = (float)sum_yy/(float)count-local_cy*local_cy;
            float cov_xy = (float)sum_xy/(float)count-local_cx*local_cy;
            float root = sqrtf((cov_xx-cov_yy)*(cov_xx-cov_yy)+
                               4.0f*cov_xy*cov_xy);
            float lambda_max = 0.5f*(cov_xx+cov_yy+root);
            float lambda_min = 0.5f*(cov_xx+cov_yy-root);
            float component_angle = 0.5f*atan2f(2.0f*cov_xy,
                                                cov_xx-cov_yy);
            float component_ux = cosf(component_angle);
            float component_uy = sinf(component_angle);
            if (lambda_min < 0.05f) lambda_min = 0.05f;
            component.major = sqrtf(12.0f*lambda_max)+1.0f;
            component.aspect = component.major/
                (sqrtf(12.0f*lambda_min)+1.0f);
            component.axis_alignment = fabsf(component_ux*shape->ux+
                                              component_uy*shape->uy);
        }
        {
            float dx = component.cx-shape_center_x;
            float dy = component.cy-shape_center_y;
            component.longitudinal =
                (dx*shape->ux+dy*shape->uy)/major;
            component.transverse =
                (-dx*shape->uy+dy*shape->ux)/minor;
        }
        {
            float center_radius = 0.18f*sqrtf((float)component.bbox_area);
            float center_radius_sq;
            int center_x0;
            int center_y0;
            int center_x1;
            int center_y1;
            uint32_t center_total = 0U;
            uint32_t center_white = 0U;
            uint32_t center_body = 0U;
            int y;
            if (center_radius < 2.0f) center_radius = 2.0f;
            center_radius_sq = center_radius*center_radius;
            center_x0 = (int)floorf(component.cx-center_radius);
            center_y0 = (int)floorf(component.cy-center_radius);
            center_x1 = (int)ceilf(component.cx+center_radius);
            center_y1 = (int)ceilf(component.cy+center_radius);
            for (y = center_y0; y <= center_y1; ++y) {
                int x;
                if (y < 0 || y >= (int)height) continue;
                for (x = center_x0; x <= center_x1; ++x) {
                    float dx;
                    float dy;
                    const uint8_t *pixel;
                    uint8_t h;
                    uint8_t s;
                    uint8_t v;
                    uint8_t bits;
                    if (x < 0 || x >= (int)width) continue;
                    dx = (float)x-component.cx;
                    dy = (float)y-component.cy;
                    if (dx*dx+dy*dy > center_radius_sq) continue;
                    pixel = frame+(uint32_t)y*stride+(uint32_t)x*3U;
                    vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2],
                                            &h, &s, &v);
                    bits = vision_classify_hsv_pixel(h, s, v);
                    center_total++;
                    if (v >= layout.white_v_min && (bits & BIT_WHITE))
                        center_white++;
                    if (bits & body_bit) center_body++;
                }
            }
            component.center_white = fraction(center_white, center_total);
            component.center_body = fraction(center_body, center_total);
        }
        component.valid = 1;
        components[component_count++] = component;
    }

    for (line_index = 0; line_index < component_count; ++line_index) {
        int solid_index;
        if (!portal_line_component_ok(&components[line_index])) continue;
        for (solid_index = 0; solid_index < component_count; ++solid_index) {
            int ring_index;
            float solid_offset;
            if (solid_index == line_index ||
                !portal_solid_component_ok(&components[solid_index]))
                continue;
            solid_offset = components[solid_index].longitudinal-
                           components[line_index].longitudinal;
            if (fabsf(solid_offset) < 0.16f || fabsf(solid_offset) > 0.70f ||
                fabsf(components[solid_index].transverse-
                      components[line_index].transverse) > 0.25f)
                continue;
            for (ring_index = 0; ring_index < component_count; ++ring_index) {
                float ring_offset;
                float dx;
                float dy;
                float distance;
                float direction_alignment;
                float score;
                if (ring_index == line_index || ring_index == solid_index ||
                    !portal_ring_component_ok(&components[ring_index]))
                    continue;
                ring_offset = components[ring_index].longitudinal-
                              components[line_index].longitudinal;
                if (fabsf(ring_offset) < 0.16f || fabsf(ring_offset) > 0.70f ||
                    solid_offset*ring_offset >= 0.0f ||
                    fabsf(components[ring_index].transverse-
                          components[line_index].transverse) > 0.25f ||
                    fabsf(components[ring_index].longitudinal-
                          components[solid_index].longitudinal) < 0.48f ||
                    (float)components[ring_index].bbox_area <
                        (float)components[solid_index].bbox_area*1.30f ||
                    components[ring_index].major <
                        components[solid_index].major*1.15f ||
                    components[line_index].major <
                        components[ring_index].major*1.20f)
                    continue;
                dx = components[ring_index].cx-components[solid_index].cx;
                dy = components[ring_index].cy-components[solid_index].cy;
                distance = sqrtf(dx*dx+dy*dy);
                if (distance <= 0.0f) continue;
                direction_alignment = fabsf((dx*shape->ux+dy*shape->uy)/
                                             distance);
                if (direction_alignment < 0.92f) continue;
                score = components[solid_index].center_white+
                        components[solid_index].fill+
                        (1.0f-components[ring_index].center_white)+
                        components[ring_index].center_body+
                        components[line_index].axis_alignment+
                        (components[line_index].aspect > 6.0f ? 1.0f :
                         components[line_index].aspect/6.0f)+
                        direction_alignment-
                        fabsf(components[line_index].longitudinal)-
                        0.5f*fabsf(components[line_index].transverse);
                if (score > best_score) {
                    runner_up_score = best_score;
                    best_score = score;
                    best_solid_index = solid_index;
                    best_line_index = line_index;
                    best_ring_index = ring_index;
                } else if (score > runner_up_score) {
                    runner_up_score = score;
                }
            }
        }
    }
    layout.component_count = component_count;
    layout.score = best_score;
    layout.runner_up_score = runner_up_score;
    if (best_solid_index >= 0 && best_line_index >= 0 && best_ring_index >= 0 &&
        (runner_up_score <= -999.0f || best_score-runner_up_score >= 0.15f)) {
        float dx;
        float dy;
        layout.solid = components[best_solid_index];
        layout.line = components[best_line_index];
        layout.ring = components[best_ring_index];
        layout.valid = 1;
        dx = layout.ring.cx-layout.solid.cx;
        dy = layout.ring.cy-layout.solid.cy;
        *angle_deg = (int)lroundf(atan2f(dy, dx)*180.0f/PI_F);
    }
#ifdef VISION_PORTAL_DIAGNOSTICS
    if (portal_diagnostic_type == (int)type) {
        int index;
        fprintf(stderr,
                "PORTAL_DIAG layout body_v_median=%u white_v_min=%u "
                "components=%d best=%.6f runner_up=%.6f valid=%d\n",
                body_median, layout.white_v_min, component_count,
                best_score, runner_up_score, layout.valid);
        for (index = 0; index < component_count; ++index) {
            const PortalMarkerComponent *component = &components[index];
            fprintf(stderr,
                    "PORTAL_DIAG layout_component index=%d count=%u bbox=%u "
                    "fill=%.6f center=(%.2f,%.2f) longitudinal=%.6f "
                    "transverse=%.6f major=%.2f aspect=%.6f align=%.6f "
                    "center_white=%.6f center_body=%.6f roles=%c%c%c\n",
                    index, component->count, component->bbox_area,
                    component->fill, component->cx, component->cy,
                    component->longitudinal, component->transverse,
                    component->major, component->aspect,
                    component->axis_alignment, component->center_white,
                    component->center_body,
                    portal_solid_component_ok(component) ? 'S' : '-',
                    portal_line_component_ok(component) ? 'L' : '-',
                    portal_ring_component_ok(component) ? 'R' : '-');
        }
        if (layout.valid)
            fprintf(stderr,
                    "PORTAL_DIAG layout_selected solid=(%.2f,%.2f) "
                    "line=(%.2f,%.2f) ring=(%.2f,%.2f) angle=%d\n",
                    layout.solid.cx, layout.solid.cy,
                    layout.line.cx, layout.line.cy,
                    layout.ring.cx, layout.ring.cy, *angle_deg);
    }
#endif
    return layout.valid;
}

static int is_black_disk(const MarkerSample *sample)
{
    float inner_mean;
    float annulus_mean;
    if (fraction(sample->black_inner, sample->inner_total) >= VISION_BLACK_DISK_MIN)
        return 1;
    if (!sample->inner_total || !sample->annulus_total) return 0;
    inner_mean = (float)sample->inner_v_sum / sample->inner_total;
    annulus_mean = (float)sample->annulus_v_sum / sample->annulus_total;
    return annulus_mean - inner_mean >= VISION_BLACK_DISK_CONTRAST_MIN;
}

static int verify_markers(VisionType type, uint8_t body_bit, const Shape *shape,
                          const uint8_t *frame, uint32_t width,
                          uint32_t height, uint32_t stride,
                          int allow_refined_portal, int *angle_deg)
{
    enum {
        END_OFFSET_COUNT = 4,
        END_TRANSVERSE_COUNT = 3,
        END_SIDE_COUNT = 2
    };
    static const float offsets[END_OFFSET_COUNT] = {
        VISION_ENDPOINT_OFFSET, VISION_ENDPOINT_OFFSET_FALLBACK,
        VISION_ENDPOINT_OFFSET_INNER, VISION_ENDPOINT_OFFSET_INNERMOST
    };
    static const float transverse_offsets[END_TRANSVERSE_COUNT] = {
        -0.15f, 0.0f, 0.15f
    };
    MarkerSample first;
    MarkerSample second;
    uint8_t mirror_disk[END_OFFSET_COUNT][END_TRANSVERSE_COUNT][END_SIDE_COUNT];
    unsigned int offset_index;
    (void)allow_refined_portal;
    if (type == VISION_PORTAL_A || type == VISION_PORTAL_B)
        return verify_portal_marker_layout(type, body_bit, shape, frame,
                                           width, height, stride, angle_deg);
    if (type == VISION_SOURCE || type == VISION_WALL) return 1;
    if (type == VISION_TARGET) {
        float radius = shape->minor * VISION_MARKER_RADIUS;
        if (radius < 2.0f) radius = 2.0f;
        sample_marker(frame, width, height, stride, shape->cx, shape->cy,
                      radius, body_bit, 1.0f, 0.0f, &first);
        TRACE("target marker white_annulus=%.2f black_inner=%.2f\n",
              fraction(first.white_annulus, first.annulus_total),
              fraction(first.black_inner, first.inner_total));
        return fraction(first.white_annulus, first.annulus_total) >=
                   VISION_TARGET_WHITE_RING_MIN &&
               fraction(first.black_inner, first.inner_total) >=
                   VISION_TARGET_BLACK_CENTER_MIN;
    }
    if (type != VISION_MIRROR) return 0;
    for (offset_index = 0; offset_index < END_OFFSET_COUNT; ++offset_index) {
        unsigned int transverse_index;
        for (transverse_index = 0;
             transverse_index < END_TRANSVERSE_COUNT; ++transverse_index) {
            endpoint_samples(frame, width, height, stride, shape, body_bit,
                             offsets[offset_index],
                             transverse_offsets[transverse_index],
                             &first, &second);
            TRACE("%s offset=%.2f transverse=%.2f black=%.2f/%.2f "
                  "dark_contrast=%.1f/%.1f\n",
                  vision_type_name(type), offsets[offset_index],
                  transverse_offsets[transverse_index],
                  fraction(first.black_inner, first.inner_total),
                  fraction(second.black_inner, second.inner_total),
                  first.inner_total && first.annulus_total ?
                      (float)first.annulus_v_sum / first.annulus_total -
                      (float)first.inner_v_sum / first.inner_total : 0.0f,
                  second.inner_total && second.annulus_total ?
                      (float)second.annulus_v_sum / second.annulus_total -
                      (float)second.inner_v_sum / second.inner_total : 0.0f);
            mirror_disk[offset_index][transverse_index][0] =
                (uint8_t)is_black_disk(&first);
            mirror_disk[offset_index][transverse_index][1] =
                (uint8_t)is_black_disk(&second);
        }
    }
    {
        unsigned int first_offset;
        for (first_offset = 0; first_offset < END_OFFSET_COUNT;
             ++first_offset) {
            unsigned int second_offset;
            for (second_offset = 0; second_offset < END_OFFSET_COUNT;
                 ++second_offset) {
                unsigned int offset_distance = first_offset > second_offset ?
                    first_offset-second_offset : second_offset-first_offset;
                unsigned int first_transverse;
                if (offset_distance > 1U) continue;
                for (first_transverse = 0;
                     first_transverse < END_TRANSVERSE_COUNT;
                     ++first_transverse) {
                    unsigned int second_transverse;
                    for (second_transverse = 0;
                         second_transverse < END_TRANSVERSE_COUNT;
                         ++second_transverse) {
                        unsigned int transverse_distance =
                            first_transverse > second_transverse ?
                            first_transverse-second_transverse :
                            second_transverse-first_transverse;
                        if (transverse_distance <= 1U &&
                            mirror_disk[first_offset][first_transverse][0] &&
                            mirror_disk[second_offset][second_transverse][1])
                            return 1;
                    }
                }
            }
        }
    }
    return 0;
}

static int geometry_ok(VisionType type, const Shape *shape)
{
    switch (type) {
    case VISION_MIRROR:
        return shape->aspect >= VISION_MIRROR_ASPECT_MIN &&
               shape->aspect <= VISION_MIRROR_ASPECT_MAX &&
               shape->fill >= VISION_MIRROR_FILL_MIN;
    case VISION_PORTAL_A:
    case VISION_PORTAL_B:
        return shape->aspect >= VISION_PORTAL_ASPECT_MIN &&
               shape->aspect <= VISION_PORTAL_ASPECT_MAX &&
               shape->fill >= VISION_PORTAL_FILL_MIN;
    case VISION_TARGET:
        return shape->aspect <= VISION_TARGET_ASPECT_MAX &&
               shape->circularity >= VISION_TARGET_CIRCULARITY_MIN;
    case VISION_SOURCE:
        return shape->aspect <= VISION_SOURCE_ASPECT_MAX &&
               shape->fill >= VISION_SOURCE_FILL_MIN &&
               shape->circularity >= VISION_SOURCE_CIRCULARITY_MIN;
    case VISION_WALL:
        return shape->aspect >= VISION_WALL_ASPECT_MIN &&
               shape->aspect <= VISION_WALL_ASPECT_MAX &&
               shape->fill >= VISION_WALL_FILL_MIN;
    default:
        return 0;
    }
}

static uint8_t histogram_median(const uint32_t histogram[256], uint32_t count)
{
    uint32_t cumulative = 0;
    uint32_t target = count / 2U;
    unsigned int value;
    for (value = 0; value < 256U; ++value) {
        cumulative += histogram[value];
        if (cumulative > target) return (uint8_t)value;
    }
    return 255U;
}

static int wall_has_contrast(const Component *component, const Shape *shape,
                             uint32_t grid_w, uint32_t grid_h)
{
    int padding = (int)lroundf(shape->minor * 0.15f);
    int x0;
    int x1;
    int y0;
    int y1;
    uint32_t outside_histogram[256] = {0};
    uint32_t outside_count = 0;
    int y;
    if (padding < 2) padding = 2;
    x0 = (int)component->min_x - padding;
    x1 = (int)component->max_x + padding;
    y0 = (int)component->min_y - padding;
    y1 = (int)component->max_y + padding;
    for (y = y0; y <= y1; ++y) {
        int x;
        if (y < 0 || y >= (int)grid_h) continue;
        for (x = x0; x <= x1; ++x) {
            if (x < 0 || x >= (int)grid_w) continue;
            if (x >= (int)component->min_x && x <= (int)component->max_x &&
                y >= (int)component->min_y && y <= (int)component->max_y) continue;
            outside_histogram[pixel_v[(uint32_t)y*grid_w+(uint32_t)x]]++;
            outside_count++;
        }
    }
    return outside_count >= 20U &&
           (float)histogram_median(outside_histogram, outside_count) -
           (float)histogram_median(component->v_histogram, component->count) >=
           VISION_WALL_CONTRAST_MIN;
}

static uint32_t source_marker_part_bbox_area(const SourceMarkerPart *part)
{
    return (part->max_x-part->min_x+1U) *
           (part->max_y-part->min_y+1U);
}

static uint32_t source_marker_part_tiebreak(uint32_t seed)
{
    /* A fixed integer mix gives equal-size/equal-fill parts a deterministic
     * tie break without preferring earlier rows or columns. */
    seed ^= seed >> 16;
    seed *= 0x7feb352dU;
    seed ^= seed >> 15;
    seed *= 0x846ca68bU;
    return seed ^ (seed >> 16);
}

static int source_marker_part_better(const SourceMarkerPart *first,
                                     const SourceMarkerPart *second)
{
    uint32_t first_area;
    uint32_t second_area;
    if (first->count != second->count)
        return first->count > second->count;
    first_area = source_marker_part_bbox_area(first);
    second_area = source_marker_part_bbox_area(second);
    if (first_area != second_area)
        return first_area < second_area;
    return source_marker_part_tiebreak(first->seed) >
           source_marker_part_tiebreak(second->seed);
}

static int collect_source_marker_parts(uint8_t marker_bit, uint32_t grid_w,
                                       uint32_t grid_h,
                                       SourceMarkerPart *parts,
                                       SourceMarkerPartStats *stats)
{
    enum {
        region_count = VISION_SOURCE_MARKER_REGION_COLS *
                       VISION_SOURCE_MARKER_REGION_ROWS,
        parts_per_region = VISION_SOURCE_MARKER_PARTS_PER_REGION
    };
    uint32_t pixels = grid_w * grid_h;
    uint32_t min_samples = marker_bit == SOURCE_MARKER_COLOR ?
        VISION_SOURCE_MARKER_COLOR_MIN_SAMPLES :
        VISION_SOURCE_MARKER_WHITE_MIN_SAMPLES;
    uint32_t max_samples = marker_bit == SOURCE_MARKER_COLOR ?
        VISION_SOURCE_MARKER_COLOR_MAX_SAMPLES :
        VISION_SOURCE_MARKER_WHITE_MAX_SAMPLES;
    uint32_t seed;
    int part_count;
    int region;
    memset(stats, 0, sizeof(*stats));
    memset(visited, 0, pixels);
    for (seed = 0; seed < pixels; ++seed) {
        Component component;
        Shape shape;
        SourceMarkerPart candidate;
        SourceMarkerPart *part;
        uint32_t span_x;
        uint32_t span_y;
        uint32_t region_x;
        uint32_t region_y;
        int region_index;
        int region_size;
        int slot;
        if (visited[seed] || !(source_marker_masks[seed] & marker_bit)) continue;
        collect_source_marker_component(seed, marker_bit, grid_w, grid_h,
                                        &component);
        span_x = component.max_x-component.min_x+1U;
        span_y = component.max_y-component.min_y+1U;
        if (component.count < min_samples || component.count > max_samples ||
            span_x > VISION_SOURCE_MARKER_MAX_SPAN_CELLS ||
            span_y > VISION_SOURCE_MARKER_MAX_SPAN_CELLS)
            continue;
        stats->total_parts++;
        part = &candidate;
        part->seed = seed;
        part->count = component.count;
        part->min_x = component.min_x;
        part->min_y = component.min_y;
        part->max_x = component.max_x;
        part->max_y = component.max_y;
        part->cx = (float)component.sum_x/(float)component.count;
        part->cy = (float)component.sum_y/(float)component.count;
        if (describe_component(&component, &shape)) {
            part->ux = shape.ux;
            part->uy = shape.uy;
            part->aspect = shape.aspect;
        } else {
            part->ux = 1.0f;
            part->uy = 0.0f;
            part->aspect = 1.0f;
        }
        region_x = (uint32_t)(component.sum_x *
            VISION_SOURCE_MARKER_REGION_COLS /
            ((uint64_t)component.count * grid_w));
        region_y = (uint32_t)(component.sum_y *
            VISION_SOURCE_MARKER_REGION_ROWS /
            ((uint64_t)component.count * grid_h));
        if (region_x >= VISION_SOURCE_MARKER_REGION_COLS)
            region_x = VISION_SOURCE_MARKER_REGION_COLS-1U;
        if (region_y >= VISION_SOURCE_MARKER_REGION_ROWS)
            region_y = VISION_SOURCE_MARKER_REGION_ROWS-1U;
        region_index = (int)(region_y*VISION_SOURCE_MARKER_REGION_COLS +
                             region_x);
        region_size = stats->region_counts[region_index];
        slot = region_index*parts_per_region;
        if (region_size < parts_per_region) {
            parts[slot+region_size] = candidate;
            stats->region_counts[region_index]++;
        } else {
            int index;
            int worst = 0;
            for (index = 1; index < parts_per_region; ++index) {
                if (source_marker_part_better(&parts[slot+worst],
                                              &parts[slot+index]))
                    worst = index;
            }
            if (source_marker_part_better(&candidate, &parts[slot+worst]))
                parts[slot+worst] = candidate;
        }
    }
    part_count = 0;
    for (region = 0; region < region_count; ++region) {
        int index;
        int source = region*parts_per_region;
        for (index = 0; index < stats->region_counts[region]; ++index)
            parts[part_count++] = parts[source+index];
    }
    stats->kept_parts = (uint32_t)part_count;
    stats->overflow_parts = stats->total_parts-stats->kept_parts;
    return part_count;
}

static void merge_source_components(const Component *color,
                                    const Component *white,
                                    Component *combined)
{
    memset(combined, 0, sizeof(*combined));
    combined->count = color->count + white->count;
    combined->min_x = color->min_x < white->min_x ? color->min_x : white->min_x;
    combined->min_y = color->min_y < white->min_y ? color->min_y : white->min_y;
    combined->max_x = color->max_x > white->max_x ? color->max_x : white->max_x;
    combined->max_y = color->max_y > white->max_y ? color->max_y : white->max_y;
    combined->sum_x = color->sum_x + white->sum_x;
    combined->sum_y = color->sum_y + white->sum_y;
    combined->sum_xx = color->sum_xx + white->sum_xx;
    combined->sum_yy = color->sum_yy + white->sum_yy;
    combined->sum_xy = color->sum_xy + white->sum_xy;
    combined->perimeter = color->perimeter + white->perimeter;
}

#if VISION_SOURCE_ARCHITECTURE_B_EXPERIMENTAL
static uint32_t source_refine_roi_area(const SourceRefineRoi *roi)
{
    return (roi->x1-roi->x0)*(roi->y1-roi->y0);
}

static int source_refine_roi_equal(const SourceRefineRoi *first,
                                   const SourceRefineRoi *second)
{
    return first->x0 == second->x0 && first->y0 == second->y0 &&
           first->x1 == second->x1 && first->y1 == second->y1;
}

static void source_part_pixel_bbox(const SourceMarkerPart *part,
                                   uint32_t width, uint32_t height,
                                   SourceRefineRoi *bbox)
{
    bbox->x0 = part->min_x*VISION_SAMPLE_STEP;
    bbox->y0 = part->min_y*VISION_SAMPLE_STEP;
    bbox->x1 = (part->max_x+1U)*VISION_SAMPLE_STEP;
    bbox->y1 = (part->max_y+1U)*VISION_SAMPLE_STEP;
    if (bbox->x1 > width) bbox->x1 = width;
    if (bbox->y1 > height) bbox->y1 = height;
}

static float source_roi_bbox_gap(const SourceRefineRoi *first,
                                 const SourceRefineRoi *second)
{
    float dx = 0.0f;
    float dy = 0.0f;
    if (first->x1 < second->x0) dx = (float)(second->x0-first->x1);
    else if (second->x1 < first->x0) dx = (float)(first->x0-second->x1);
    if (first->y1 < second->y0) dy = (float)(second->y0-first->y1);
    else if (second->y1 < first->y0) dy = (float)(first->y0-second->y1);
    return sqrtf(dx*dx+dy*dy);
}

static float source_roi_center_distance(const SourceRefineRoi *first,
                                        const SourceRefineRoi *second)
{
    float dx = 0.5f*((float)first->x0+(float)first->x1-
                     (float)second->x0-(float)second->x1);
    float dy = 0.5f*((float)first->y0+(float)first->y1-
                     (float)second->y0-(float)second->y1);
    return sqrtf(dx*dx+dy*dy);
}

static SourceRefineRoi source_build_refine_roi(
    const SourceMarkerPart *color, const SourceMarkerPart *whites,
    int white_count, uint32_t width, uint32_t height)
{
    SourceRefineRoi color_bbox;
    SourceRefineRoi roi;
    uint32_t color_w;
    uint32_t color_h;
    uint32_t span;
    uint32_t margin;
    int best_white = -1;
    float best_gap = 0.0f;
    float best_center_distance = 0.0f;
    int white_index;
    source_part_pixel_bbox(color, width, height, &color_bbox);
    color_w = color_bbox.x1-color_bbox.x0;
    color_h = color_bbox.y1-color_bbox.y0;
    span = color_w > color_h ? color_w : color_h;
    margin = (span*SOURCE_REFINE_MARGIN_NUMERATOR+
              SOURCE_REFINE_MARGIN_DENOMINATOR-1U) /
             SOURCE_REFINE_MARGIN_DENOMINATOR;
    if (margin < SOURCE_REFINE_MARGIN_MIN) margin = SOURCE_REFINE_MARGIN_MIN;
    if (margin > SOURCE_REFINE_MARGIN_MAX) margin = SOURCE_REFINE_MARGIN_MAX;
    roi.x0 = color_bbox.x0 > margin ? color_bbox.x0-margin : 0U;
    roi.y0 = color_bbox.y0 > margin ? color_bbox.y0-margin : 0U;
    roi.x1 = color_bbox.x1+margin < width ? color_bbox.x1+margin : width;
    roi.y1 = color_bbox.y1+margin < height ? color_bbox.y1+margin : height;
    for (white_index = 0; white_index < white_count; ++white_index) {
        SourceRefineRoi white_bbox;
        float gap;
        float center_distance;
        source_part_pixel_bbox(&whites[white_index], width, height,
                               &white_bbox);
        gap = source_roi_bbox_gap(&color_bbox, &white_bbox);
        if (gap > SOURCE_REFINE_WHITE_GAP_CELLS*VISION_SAMPLE_STEP)
            continue;
        center_distance = source_roi_center_distance(&color_bbox, &white_bbox);
        if (best_white < 0 || gap < best_gap ||
            (gap == best_gap && center_distance < best_center_distance) ||
            (gap == best_gap && center_distance == best_center_distance &&
             whites[white_index].count > whites[best_white].count)) {
            best_white = white_index;
            best_gap = gap;
            best_center_distance = center_distance;
        }
    }
    if (best_white >= 0) {
        SourceRefineRoi white_bbox;
        SourceRefineRoi candidate;
        uint32_t padding = SOURCE_REFINE_WHITE_PADDING;
        source_part_pixel_bbox(&whites[best_white], width, height,
                               &white_bbox);
        candidate.x0 = roi.x0 < white_bbox.x0 ? roi.x0 : white_bbox.x0;
        candidate.y0 = roi.y0 < white_bbox.y0 ? roi.y0 : white_bbox.y0;
        candidate.x1 = roi.x1 > white_bbox.x1 ? roi.x1 : white_bbox.x1;
        candidate.y1 = roi.y1 > white_bbox.y1 ? roi.y1 : white_bbox.y1;
        candidate.x0 = candidate.x0 > padding ? candidate.x0-padding : 0U;
        candidate.y0 = candidate.y0 > padding ? candidate.y0-padding : 0U;
        candidate.x1 = candidate.x1+padding < width ?
                       candidate.x1+padding : width;
        candidate.y1 = candidate.y1+padding < height ?
                       candidate.y1+padding : height;
        if (source_refine_roi_area(&candidate) <= GRID_MAX_PIXELS)
            roi = candidate;
    }
    return roi;
}

static SourceRefineRoi source_build_retry_roi(const SourceRefineRoi *base,
                                              uint8_t touches,
                                              uint32_t width,
                                              uint32_t height)
{
    SourceRefineRoi retry;
    uint32_t base_w = base->x1-base->x0;
    uint32_t base_h = base->y1-base->y0;
    uint32_t target_w = width < SOURCE_REFINE_RETRY_SPAN ?
                        width : SOURCE_REFINE_RETRY_SPAN;
    uint32_t target_h = height < SOURCE_REFINE_RETRY_SPAN ?
                        height : SOURCE_REFINE_RETRY_SPAN;
    int x0;
    int y0;
    if (target_w < base_w) target_w = base_w;
    if (target_h < base_h) target_h = base_h;
    if (target_w*target_h > GRID_MAX_PIXELS) {
        if ((touches & (2U|8U)) && !(touches & (1U|4U)))
            target_w = GRID_MAX_PIXELS/target_h;
        else
            target_h = GRID_MAX_PIXELS/target_w;
    }
    if ((touches & 1U) && !(touches & 4U))
        x0 = (int)base->x1-(int)target_w;
    else if ((touches & 4U) && !(touches & 1U))
        x0 = (int)base->x0;
    else
        x0 = ((int)base->x0+(int)base->x1-(int)target_w)/2;
    if ((touches & 2U) && !(touches & 8U))
        y0 = (int)base->y1-(int)target_h;
    else if ((touches & 8U) && !(touches & 2U))
        y0 = (int)base->y0;
    else
        y0 = ((int)base->y0+(int)base->y1-(int)target_h)/2;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if ((uint32_t)x0+target_w > width) x0 = (int)(width-target_w);
    if ((uint32_t)y0+target_h > height) y0 = (int)(height-target_h);
    retry.x0 = (uint32_t)x0;
    retry.y0 = (uint32_t)y0;
    retry.x1 = retry.x0+target_w;
    retry.y1 = retry.y0+target_h;
    return retry;
}

static void source_label_coarse_colors(const SourceMarkerPart *colors,
                                       int color_count, uint32_t grid_w,
                                       uint32_t grid_h)
{
    int color_index;
    memset(morphology_scratch, 0, grid_w*grid_h);
    for (color_index = 0; color_index < color_count; ++color_index) {
        Component component;
        uint32_t index;
        memset(visited, 0, grid_w*grid_h);
        collect_source_marker_component(colors[color_index].seed,
                                        SOURCE_MARKER_COLOR, grid_w, grid_h,
                                        &component);
        for (index = 0; index < component.count; ++index)
            morphology_scratch[queue_storage[index]] =
                (uint8_t)(color_index+1);
    }
}

static void source_build_full_resolution_masks(const uint8_t *frame,
                                               uint32_t stride,
                                               const SourceRefineRoi *roi)
{
    uint32_t roi_w = roi->x1-roi->x0;
    uint32_t y;
    for (y = roi->y0; y < roi->y1; ++y) {
        uint32_t x;
        for (x = roi->x0; x < roi->x1; ++x) {
            const uint8_t *pixel = frame+y*stride+x*3U;
            uint8_t h;
            uint8_t s;
            uint8_t v;
            uint8_t mask = 0U;
            uint32_t index = (y-roi->y0)*roi_w+(x-roi->x0);
            vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
            if (vision_classify_hsv_pixel(h, s, v) & BIT_MAGENTA)
                mask |= SOURCE_MARKER_COLOR;
            if (s <= VISION_SOURCE_MARKER_WHITE_S_MAX &&
                v >= VISION_SOURCE_MARKER_WHITE_V_MIN)
                mask |= SOURCE_MARKER_WHITE;
            source_marker_masks[index] = mask;
        }
    }
}

static int describe_source_component(const Component *component, Shape *shape,
                                     float *eigen_max, float *eigen_min)
{
    float count;
    float cov_xx;
    float cov_yy;
    float cov_xy;
    float root;
    float lambda_max;
    float lambda_min;
    float angle;
    float bbox_area;
    if (!component->count) return 0;
    count = (float)component->count;
    shape->cx = (float)component->sum_x/count;
    shape->cy = (float)component->sum_y/count;
    cov_xx = (float)component->sum_xx/count-shape->cx*shape->cx;
    cov_yy = (float)component->sum_yy/count-shape->cy*shape->cy;
    cov_xy = (float)component->sum_xy/count-shape->cx*shape->cy;
    root = sqrtf((cov_xx-cov_yy)*(cov_xx-cov_yy)+4.0f*cov_xy*cov_xy);
    lambda_max = 0.5f*(cov_xx+cov_yy+root);
    lambda_min = 0.5f*(cov_xx+cov_yy-root);
    if (lambda_max < 0.0f) lambda_max = 0.0f;
    if (lambda_min < 0.0f) lambda_min = 0.0f;
    angle = 0.5f*atan2f(2.0f*cov_xy, cov_xx-cov_yy);
    shape->ux = cosf(angle);
    shape->uy = sinf(angle);
    shape->major = sqrtf(12.0f*lambda_max)+1.0f;
    shape->minor = sqrtf(12.0f*lambda_min)+1.0f;
    shape->aspect = shape->major/shape->minor;
    shape->angle_deg = (int)lroundf(angle*180.0f/PI_F);
    bbox_area = (float)((component->max_x-component->min_x+1U)*
                        (component->max_y-component->min_y+1U));
    shape->fill = count/bbox_area;
    shape->circularity = component->perimeter ?
        4.0f*PI_F*count/((float)component->perimeter*component->perimeter) :
        0.0f;
    if (eigen_max) *eigen_max = lambda_max;
    if (eigen_min) *eigen_min = lambda_min;
    return 1;
}

static int source_describe_attached_white_axis(uint32_t roi_w,
                                               uint32_t roi_h,
                                               Shape *shape)
{
    Component attached;
    uint32_t pixels = roi_w*roi_h;
    uint32_t cell;
    int have_attached = 0;
    memset(&attached, 0, sizeof(attached));
    for (cell = 0U; cell < pixels; ++cell) {
        uint32_t x;
        uint32_t y;
        if (!(source_marker_masks[cell] & SOURCE_MARKER_WHITE) ||
            wall_marker_mask[cell] ||
            v_integral[cell] > SOURCE_REFINE_AXIS_DISTANCE_MAX)
            continue;
        x = cell%roi_w;
        y = cell/roi_w;
        if (!have_attached) {
            component_reset(&attached, x, y);
            have_attached = 1;
        }
        component_add(&attached, x, y, 0U);
    }
    return have_attached &&
           attached.count >= SOURCE_REFINE_AXIS_MIN_PIXELS &&
           describe_source_component(&attached, shape, NULL, NULL);
}

static uint32_t source_refined_color_support(uint8_t color_label,
                                             const SourceRefineRoi *roi,
                                             uint32_t roi_w,
                                             uint32_t grid_w,
                                             uint32_t grid_h,
                                             const Component *component)
{
    uint32_t support = 0U;
    uint32_t index;
    for (index = 0; index < component->count; ++index) {
        uint32_t cell = queue_storage[index];
        uint32_t x = roi->x0+cell%roi_w;
        uint32_t y = roi->y0+cell/roi_w;
        if (x >= source_sample_phase_x && y >= source_sample_phase_y &&
            (x-source_sample_phase_x)%VISION_SAMPLE_STEP == 0U &&
            (y-source_sample_phase_y)%VISION_SAMPLE_STEP == 0U) {
            uint32_t coarse_x = (x-source_sample_phase_x)/VISION_SAMPLE_STEP;
            uint32_t coarse_y = (y-source_sample_phase_y)/VISION_SAMPLE_STEP;
            if (coarse_x < grid_w && coarse_y < grid_h &&
                morphology_scratch[coarse_y*grid_w+coarse_x] == color_label)
                support++;
        }
    }
    return support;
}

static void source_build_color_distance(uint32_t roi_w, uint32_t roi_h)
{
    const uint32_t infinity = 0x3fffffffU;
    uint32_t pixels = roi_w*roi_h;
    uint32_t index;
    uint32_t y;
    for (index = 0; index < pixels; ++index)
        v_integral[index] = wall_marker_mask[index] ? 0U : infinity;
    for (y = 0; y < roi_h; ++y) {
        uint32_t x;
        for (x = 0; x < roi_w; ++x) {
            uint32_t here = y*roi_w+x;
            uint32_t value = v_integral[here];
            uint32_t candidate;
            if (x > 0U && v_integral[here-1U]+3U < value)
                value = v_integral[here-1U]+3U;
            if (y > 0U && v_integral[here-roi_w]+3U < value)
                value = v_integral[here-roi_w]+3U;
            if (x > 0U && y > 0U) {
                candidate = v_integral[here-roi_w-1U]+4U;
                if (candidate < value) value = candidate;
            }
            if (x+1U < roi_w && y > 0U) {
                candidate = v_integral[here-roi_w+1U]+4U;
                if (candidate < value) value = candidate;
            }
            v_integral[here] = value;
        }
    }
    for (y = roi_h; y-- > 0U;) {
        uint32_t x;
        for (x = roi_w; x-- > 0U;) {
            uint32_t here = y*roi_w+x;
            uint32_t value = v_integral[here];
            uint32_t candidate;
            if (x+1U < roi_w && v_integral[here+1U]+3U < value)
                value = v_integral[here+1U]+3U;
            if (y+1U < roi_h && v_integral[here+roi_w]+3U < value)
                value = v_integral[here+roi_w]+3U;
            if (x+1U < roi_w && y+1U < roi_h) {
                candidate = v_integral[here+roi_w+1U]+4U;
                if (candidate < value) value = candidate;
            }
            if (x > 0U && y+1U < roi_h) {
                candidate = v_integral[here+roi_w-1U]+4U;
                if (candidate < value) value = candidate;
            }
            v_integral[here] = value;
        }
    }
}

static int source_add_companion_color_components(uint32_t roi_w,
                                                 uint32_t roi_h,
                                                 const Component *primary,
                                                 float *axis_x,
                                                 float *axis_y)
{
    uint32_t pixels = roi_w*roi_h;
    uint32_t seed;
    int companion_count = 0;
    memset(visited, 0, pixels);
    for (seed = 0U; seed < pixels; ++seed) {
        Component component;
        uint32_t index;
        uint32_t nearest = 0x3fffffffU;
        int is_primary = 0;
        if (visited[seed] ||
            !(source_marker_masks[seed] & SOURCE_MARKER_COLOR))
            continue;
        collect_source_marker_component(seed, SOURCE_MARKER_COLOR,
                                        roi_w, roi_h, &component);
        for (index = 0U; index < component.count; ++index) {
            uint32_t cell = queue_storage[index];
            uint32_t distance = v_integral[cell];
            if (wall_marker_mask[cell]) is_primary = 1;
            if (distance < nearest) nearest = distance;
        }
        if (is_primary) continue;
        if (component.count < SOURCE_REFINE_COMPANION_MIN_PIXELS ||
            nearest > SOURCE_REFINE_COMPANION_DISTANCE_MAX)
            continue;
        if (component.count*4U < primary->count*3U ||
            component.count*3U > primary->count*4U)
            continue;
        companion_count++;
        if (companion_count == 1) {
            float primary_cx = (float)primary->sum_x/(float)primary->count;
            float primary_cy = (float)primary->sum_y/(float)primary->count;
            float companion_cx = (float)component.sum_x/(float)component.count;
            float companion_cy = (float)component.sum_y/(float)component.count;
            float dx = companion_cx-primary_cx;
            float dy = companion_cy-primary_cy;
            float distance = sqrtf(dx*dx+dy*dy);
            if (distance > 0.0f) {
                *axis_x = -dy/distance;
                *axis_y = dx/distance;
            } else {
                companion_count = 0;
            }
        }
        for (index = 0U; index < component.count; ++index)
            wall_marker_mask[queue_storage[index]] = 1U;
    }
    return companion_count == 1;
}

static uint32_t source_white_contact_pixels(uint32_t roi_w, uint32_t roi_h,
                                            const Component *white)
{
    uint32_t contact = 0U;
    uint32_t index;
    for (index = 0; index < white->count; ++index) {
        uint32_t cell = queue_storage[index];
        uint32_t x = cell%roi_w;
        uint32_t y = cell/roi_w;
        int dy;
        int adjacent = 0;
        for (dy = -1; dy <= 1 && !adjacent; ++dy) {
            int dx;
            for (dx = -1; dx <= 1; ++dx) {
                int xx;
                int yy;
                if (!dx && !dy) continue;
                xx = (int)x+dx;
                yy = (int)y+dy;
                if (xx >= 0 && yy >= 0 && xx < (int)roi_w &&
                    yy < (int)roi_h &&
                    wall_marker_mask[(uint32_t)yy*roi_w+(uint32_t)xx]) {
                    adjacent = 1;
                    break;
                }
            }
        }
        if (adjacent) contact++;
    }
    return contact;
}

static void source_color_taper_diagnostics(uint32_t roi_w, uint32_t roi_h,
                                            float cx, float cy,
                                            float direction_x,
                                            float direction_y,
                                            float *ratio,
                                            float *robust_tip_projection)
{
    float minimum = 0.0f;
    float maximum = 0.0f;
    float front_sum = 0.0f;
    uint32_t seen = 0U;
    uint32_t front = 0U;
    uint32_t back = 0U;
    uint32_t y;
    for (y = 0; y < roi_h; ++y) {
        uint32_t x;
        for (x = 0; x < roi_w; ++x) {
            float projection;
            if (!wall_marker_mask[y*roi_w+x]) continue;
            projection = ((float)x-cx)*direction_x+
                         ((float)y-cy)*direction_y;
            if (!seen || projection < minimum) minimum = projection;
            if (!seen || projection > maximum) maximum = projection;
            seen++;
        }
    }
    if (!seen || maximum-minimum < 2.0f) {
        *ratio = 1.0f;
        *robust_tip_projection = maximum;
        return;
    }
    for (y = 0; y < roi_h; ++y) {
        uint32_t x;
        for (x = 0; x < roi_w; ++x) {
            float projection;
            if (!wall_marker_mask[y*roi_w+x]) continue;
            projection = ((float)x-cx)*direction_x+
                         ((float)y-cy)*direction_y;
            if (projection <= minimum+0.30f*(maximum-minimum)) back++;
            if (projection >= maximum-0.30f*(maximum-minimum)) {
                front_sum += projection;
                front++;
            }
        }
    }
    *ratio = back ? (float)front/(float)back : 1.0f;
    *robust_tip_projection = front ? front_sum/(float)front : maximum;
}

static int source_pair_sanity(const SourceRefinedPair *pair)
{
    return pair->color.count >= VISION_SOURCE_REFINE_MIN_COLOR_PIXELS &&
           pair->white.count >= VISION_SOURCE_REFINE_MIN_WHITE_PIXELS &&
           pair->color_shape.aspect <= VISION_SOURCE_REFINE_MAX_COLOR_ASPECT &&
           pair->white_eigen_ratio >=
               VISION_SOURCE_REFINE_MIN_WHITE_EIGEN_RATIO &&
           pair->attachment >= VISION_SOURCE_REFINE_MIN_ATTACHMENT &&
           pair->taper_ratio <= VISION_SOURCE_REFINE_TAPER_MAX &&
           pair->nearest_distance <= SOURCE_REFINE_NEAREST_MAX &&
           pair->relative_area >= SOURCE_REFINE_AREA_RATIO_MIN &&
           pair->relative_area <= SOURCE_REFINE_AREA_RATIO_MAX &&
           pair->center_ratio >= SOURCE_REFINE_CENTER_RATIO_MIN &&
           pair->center_ratio <= SOURCE_REFINE_CENTER_RATIO_MAX &&
           pair->pair_aspect <= SOURCE_REFINE_PAIR_ASPECT_MAX &&
           pair->pair_fill >= SOURCE_REFINE_PAIR_FILL_MIN;
}

static void source_finish_refined_pair(SourceRefinedPair *pair,
                                       uint32_t roi_w, uint32_t roi_h)
{
    Component combined;
    merge_source_components(&pair->color, &pair->white, &combined);
    describe_source_component(&combined, &pair->combined_shape, NULL, NULL);
    /* The white stroke supplies an undirected axis.  Select the orange
     * triangle's narrow end so SOURCE always points at its apex. */
    if (pair->white_eigen_ratio >= SOURCE_REFINE_CLEAN_WHITE_EIGEN_MIN &&
        pair->attachment >= SOURCE_REFINE_CLEAN_WHITE_ATTACHMENT_MIN &&
        pair->relative_area <= SOURCE_REFINE_CLEAN_WHITE_AREA_MAX) {
        pair->direction_x = pair->white_shape.ux;
        pair->direction_y = pair->white_shape.uy;
        pair->direction_center_x = pair->white_shape.cx;
        pair->direction_center_y = pair->white_shape.cy;
    } else {
        pair->direction_x = pair->white_axis_shape.ux;
        pair->direction_y = pair->white_axis_shape.uy;
        pair->direction_center_x = pair->color_shape.cx;
        pair->direction_center_y = pair->color_shape.cy;
    }
    source_color_taper_diagnostics(roi_w, roi_h,
                                   pair->direction_center_x,
                                   pair->direction_center_y,
                                   pair->direction_x, pair->direction_y,
                                   &pair->taper_ratio,
                                   &pair->robust_tip_projection);
    if (pair->taper_ratio > 1.0f) {
        pair->direction_x = -pair->direction_x;
        pair->direction_y = -pair->direction_y;
        source_color_taper_diagnostics(roi_w, roi_h,
                                       pair->direction_center_x,
                                       pair->direction_center_y,
                                       pair->direction_x, pair->direction_y,
                                       &pair->taper_ratio,
                                       &pair->robust_tip_projection);
    }
}

static void refine_source_roi(const uint8_t *frame, uint32_t stride,
                              uint32_t grid_w, uint32_t grid_h,
                              uint32_t frame_width, uint32_t frame_height,
                              uint8_t color_label,
                              const SourceRefineRoi *roi,
                              SourceRefinedPair *result)
{
    uint32_t roi_w = roi->x1-roi->x0;
    uint32_t roi_h = roi->y1-roi->y0;
    uint32_t pixels = roi_w*roi_h;
    Component best_color;
    Shape best_color_shape;
    uint32_t best_color_seed = 0U;
    uint32_t best_support = 0U;
    float companion_axis_x = 0.0f;
    float companion_axis_y = 0.0f;
    int companion_axis_valid;
    int have_color = 0;
    uint32_t seed;
    SourceRefinedPair best_pair;
    SourceRefinedPair best_valid_pair;
    int have_pair = 0;
    int have_valid_pair = 0;
    memset(result, 0, sizeof(*result));
    result->roi = *roi;
    source_build_full_resolution_masks(frame, stride, roi);
    memset(visited, 0, pixels);
    for (seed = 0; seed < pixels; ++seed) {
        Component component;
        Shape shape;
        uint32_t support;
        if (visited[seed] ||
            !(source_marker_masks[seed] & SOURCE_MARKER_COLOR)) continue;
        collect_source_marker_component(seed, SOURCE_MARKER_COLOR,
                                        roi_w, roi_h, &component);
        support = source_refined_color_support(color_label, roi, roi_w,
                                               grid_w, grid_h, &component);
        if (!support || !describe_source_component(&component, &shape,
                                                   NULL, NULL))
            continue;
        if (!have_color || support > best_support ||
            (support == best_support && component.count > best_color.count)) {
            best_color = component;
            best_color_shape = shape;
            best_color_seed = seed;
            best_support = support;
            have_color = 1;
        }
    }
    if (!have_color) return;
    result->color_found = 1;
    result->color = best_color;
    result->color_shape = best_color_shape;
    result->color_support = best_support;
    memset(wall_marker_mask, 0, pixels);
    memset(visited, 0, pixels);
    collect_source_marker_component(best_color_seed, SOURCE_MARKER_COLOR,
                                    roi_w, roi_h, &best_color);
    for (seed = 0; seed < best_color.count; ++seed)
        wall_marker_mask[queue_storage[seed]] = 1U;
    source_build_color_distance(roi_w, roi_h);
    companion_axis_valid = source_add_companion_color_components(
        roi_w, roi_h, &best_color, &companion_axis_x, &companion_axis_y);
    source_build_color_distance(roi_w, roi_h);
    memset(visited, 0, pixels);
    for (seed = 0; seed < pixels; ++seed) {
        Component white;
        Shape white_shape;
        Shape white_axis_shape;
        SourceRefinedPair candidate;
        float eigen_max;
        float eigen_min;
        float dx;
        float dy;
        float center_distance;
        float bbox_w;
        float bbox_h;
        float bbox_area;
        float area_balance;
        float span_ratio;
        float span_balance;
        uint32_t queue_index;
        uint32_t nearest = 0x3fffffffU;
        uint32_t min_x;
        uint32_t min_y;
        uint32_t max_x;
        uint32_t max_y;
        if (visited[seed] ||
            !(source_marker_masks[seed] & SOURCE_MARKER_WHITE)) continue;
        collect_source_marker_component(seed, SOURCE_MARKER_WHITE,
                                        roi_w, roi_h, &white);
        result->white_found = 1;
        if (!describe_source_component(&white, &white_shape,
                                       &eigen_max, &eigen_min))
            continue;
        if (!source_describe_attached_white_axis(roi_w, roi_h,
                                                  &white_axis_shape))
            continue;
        if (companion_axis_valid) {
            white_axis_shape.ux = companion_axis_x;
            white_axis_shape.uy = companion_axis_y;
        }
        dx = best_color_shape.cx-white_shape.cx;
        dy = best_color_shape.cy-white_shape.cy;
        center_distance = sqrtf(dx*dx+dy*dy);
        if (center_distance <= 0.0f) continue;
        for (queue_index = 0; queue_index < white.count; ++queue_index) {
            uint32_t distance = v_integral[queue_storage[queue_index]];
            if (distance < nearest) nearest = distance;
        }
        min_x = best_color.min_x < white.min_x ? best_color.min_x : white.min_x;
        min_y = best_color.min_y < white.min_y ? best_color.min_y : white.min_y;
        max_x = best_color.max_x > white.max_x ? best_color.max_x : white.max_x;
        max_y = best_color.max_y > white.max_y ? best_color.max_y : white.max_y;
        bbox_w = (float)(max_x-min_x+1U);
        bbox_h = (float)(max_y-min_y+1U);
        bbox_area = bbox_w*bbox_h;
        memset(&candidate, 0, sizeof(candidate));
        candidate.roi = *roi;
        candidate.color_found = 1;
        candidate.white_found = 1;
        candidate.pair_found = 1;
        candidate.color = best_color;
        candidate.white = white;
        candidate.color_shape = best_color_shape;
        candidate.white_shape = white_shape;
        candidate.white_axis_shape = white_axis_shape;
        candidate.color_support = best_support;
        candidate.direction_x = dx/center_distance;
        candidate.direction_y = dy/center_distance;
        candidate.nearest_distance = (float)nearest/3.0f;
        candidate.contact_pixels = source_white_contact_pixels(
            roi_w, roi_h, &white);
        candidate.attachment = (float)candidate.contact_pixels/
                               white_shape.major;
        candidate.relative_area = (float)white.count/(float)best_color.count;
        candidate.center_ratio = center_distance/
                                 (bbox_w > bbox_h ? bbox_w : bbox_h);
        candidate.pair_fill = (float)(best_color.count+white.count)/bbox_area;
        candidate.pair_aspect = bbox_w > bbox_h ? bbox_w/bbox_h : bbox_h/bbox_w;
        candidate.white_eigen_ratio = eigen_min > 1.0e-6f ?
                                      eigen_max/eigen_min : 1.0e9f;
        candidate.white_normal = fabsf(
            white_shape.ux*(-candidate.direction_y)+
            white_shape.uy*candidate.direction_x);
        if (best_color.min_x == 0U) candidate.color_touches_roi |= 1U;
        if (best_color.min_y == 0U) candidate.color_touches_roi |= 2U;
        if (best_color.max_x+1U == roi_w) candidate.color_touches_roi |= 4U;
        if (best_color.max_y+1U == roi_h) candidate.color_touches_roi |= 8U;
        if (white.min_x == 0U) candidate.white_touches_roi |= 1U;
        if (white.min_y == 0U) candidate.white_touches_roi |= 2U;
        if (white.max_x+1U == roi_w) candidate.white_touches_roi |= 4U;
        if (white.max_y+1U == roi_h) candidate.white_touches_roi |= 8U;
        candidate.touches_roi = candidate.color_touches_roi |
                                candidate.white_touches_roi;
        area_balance = candidate.relative_area <= 1.0f ?
                       candidate.relative_area : 1.0f/candidate.relative_area;
        span_ratio = white_shape.major/best_color_shape.major;
        span_balance = span_ratio <= 1.0f ? span_ratio : 1.0f/span_ratio;
        candidate.selection_score =
            8.0f/(1.0f+candidate.nearest_distance)+2.0f*area_balance+
            span_balance+2.0f*candidate.pair_fill/candidate.pair_aspect-
            0.25f*candidate.center_ratio+
            0.01f*sqrtf((float)(best_color.count+white.count));
        /* Prefer a fully observed pair when two structurally similar ROIs
         * compete.  Frame-edge contact is only a ranking penalty, never a
         * rejection: genuine clipped SOURCE captures remain eligible. */
        if ((roi->x0 == 0U && (candidate.touches_roi & 1U)) ||
            (roi->y0 == 0U && (candidate.touches_roi & 2U)) ||
            (roi->x1 == frame_width && (candidate.touches_roi & 4U)) ||
            (roi->y1 == frame_height && (candidate.touches_roi & 8U)))
            candidate.selection_score -= 0.25f;
        source_finish_refined_pair(&candidate, roi_w, roi_h);
        candidate.valid = source_pair_sanity(&candidate);
        if (!have_pair || candidate.selection_score >
                              best_pair.selection_score) {
            best_pair = candidate;
            have_pair = 1;
        }
        if (candidate.valid &&
            (!have_valid_pair || candidate.selection_score >
                                 best_valid_pair.selection_score)) {
            best_valid_pair = candidate;
            have_valid_pair = 1;
        }
    }
    if (!have_pair) return;
    *result = have_valid_pair ? best_valid_pair : best_pair;
}

#ifdef VISION_SOURCE_REFINEMENT_DIAGNOSTICS
static void source_record_best_diagnostics(const SourceRefinedPair *pair)
{
    uint32_t min_x = pair->color.min_x < pair->white.min_x ?
                     pair->color.min_x : pair->white.min_x;
    uint32_t min_y = pair->color.min_y < pair->white.min_y ?
                     pair->color.min_y : pair->white.min_y;
    uint32_t max_x = pair->color.max_x > pair->white.max_x ?
                     pair->color.max_x : pair->white.max_x;
    uint32_t max_y = pair->color.max_y > pair->white.max_y ?
                     pair->color.max_y : pair->white.max_y;
    source_refinement_stats.best_color_pixels = pair->color.count;
    source_refinement_stats.best_white_pixels = pair->white.count;
    source_refinement_stats.best_roi_x = (int)pair->roi.x0;
    source_refinement_stats.best_roi_y = (int)pair->roi.y0;
    source_refinement_stats.best_roi_w = (int)(pair->roi.x1-pair->roi.x0);
    source_refinement_stats.best_roi_h = (int)(pair->roi.y1-pair->roi.y0);
    source_refinement_stats.best_pair_x = (int)(pair->roi.x0+min_x);
    source_refinement_stats.best_pair_y = (int)(pair->roi.y0+min_y);
    source_refinement_stats.best_pair_w = (int)(max_x-min_x+1U);
    source_refinement_stats.best_pair_h = (int)(max_y-min_y+1U);
    source_refinement_stats.best_nearest_distance = pair->nearest_distance;
    source_refinement_stats.best_center_ratio = pair->center_ratio;
    source_refinement_stats.best_relative_area = pair->relative_area;
    source_refinement_stats.best_pair_fill = pair->pair_fill;
    source_refinement_stats.best_pair_aspect = pair->pair_aspect;
    source_refinement_stats.best_white_eigen_ratio = pair->white_eigen_ratio;
    source_refinement_stats.best_white_normal = pair->white_normal;
    source_refinement_stats.best_attachment = pair->attachment;
    source_refinement_stats.best_taper_ratio = pair->taper_ratio;
}
#endif

static int detect_marker_source(const uint8_t *frame, uint32_t stride,
                                VisionDetection *output, int output_capacity,
                                uint32_t width, uint32_t height,
                                uint32_t grid_w, uint32_t grid_h)
{
    SourceMarkerPart color_parts[VISION_SOURCE_MARKER_MAX_PARTS];
    SourceMarkerPart white_parts[VISION_SOURCE_MARKER_MAX_PARTS];
    SourceMarkerPartStats color_stats;
    SourceMarkerPartStats white_stats;
    SourceRefinedPair best;
    SourceRefinedPair best_diagnostic;
    int have_best = 0;
    int have_diagnostic = 0;
    int color_count;
    int white_count;
    int color_index;
    uint32_t roi_calls = 0U;
    uint32_t roi_pixels = 0U;
    uint32_t max_roi_pixels = 0U;
    uint32_t refined_color = 0U;
    uint32_t refined_white = 0U;
    uint32_t refined_pair = 0U;
    uint32_t reject_no_color = 0U;
    uint32_t reject_no_white = 0U;
    uint32_t reject_geometry = 0U;
    memset(&best, 0, sizeof(best));
    memset(&best_diagnostic, 0, sizeof(best_diagnostic));
    if (output_capacity <= 0) return 0;
    color_count = collect_source_marker_parts(
        SOURCE_MARKER_COLOR, grid_w, grid_h, color_parts, &color_stats);
    white_count = collect_source_marker_parts(
        SOURCE_MARKER_WHITE, grid_w, grid_h, white_parts, &white_stats);
    source_label_coarse_colors(color_parts, color_count, grid_w, grid_h);
    for (color_index = 0; color_index < color_count; ++color_index) {
        SourceRefineRoi roi = source_build_refine_roi(
            &color_parts[color_index], white_parts, white_count, width, height);
        SourceRefinedPair candidate;
        SourceRefinedPair retry_candidate;
        uint32_t area = source_refine_roi_area(&roi);
        int trigger_color;
        int trigger_white;
        int trigger_pair;
        roi_calls++;
        roi_pixels += area;
        if (area > max_roi_pixels) max_roi_pixels = area;
        refine_source_roi(frame, stride, grid_w, grid_h, width, height,
                          (uint8_t)(color_index+1), &roi, &candidate);
        uint32_t coarse_span_x =
            (color_parts[color_index].max_x-
             color_parts[color_index].min_x+1U)*VISION_SAMPLE_STEP;
        uint32_t coarse_span_y =
            (color_parts[color_index].max_y-
             color_parts[color_index].min_y+1U)*VISION_SAMPLE_STEP;
        uint32_t coarse_span = coarse_span_x > coarse_span_y ?
                               coarse_span_x : coarse_span_y;
        if (candidate.pair_found && candidate.valid &&
            candidate.white_touches_roi &&
            !candidate.color_touches_roi && coarse_span >= 96U) {
            SourceRefineRoi retry = source_build_retry_roi(
                &roi, candidate.white_touches_roi, width, height);
            if (!source_refine_roi_equal(&roi, &retry) &&
                source_refine_roi_area(&retry) <= GRID_MAX_PIXELS) {
                area = source_refine_roi_area(&retry);
                roi_calls++;
                roi_pixels += area;
                if (area > max_roi_pixels) max_roi_pixels = area;
                refine_source_roi(frame, stride, grid_w, grid_h,
                                  width, height,
                                  (uint8_t)(color_index+1), &retry,
                                  &retry_candidate);
                if (retry_candidate.valid ||
                    (!candidate.valid && retry_candidate.pair_found))
                    candidate = retry_candidate;
            }
        }
        if (candidate.pair_found) {
            TRACE("source_refine_pair color_index=%d coarse=(%u,%u %ux%u) roi=(%u,%u %ux%u) color=%u white=%u support=%u valid=%d score=%.3f nearest=%.2f center=%.3f area=%.3f fill=%.3f aspect=%.3f color_aspect=%.3f white_eigen=%.3f attachment=%.3f taper=%.3f color_edge=%u white_edge=%u\n",
                  color_index, color_parts[color_index].min_x*VISION_SAMPLE_STEP,
                  color_parts[color_index].min_y*VISION_SAMPLE_STEP,
                  coarse_span_x, coarse_span_y, candidate.roi.x0,
                  candidate.roi.y0, candidate.roi.x1-candidate.roi.x0,
                  candidate.roi.y1-candidate.roi.y0, candidate.color.count,
                  candidate.white.count, candidate.color_support,
                  candidate.valid, candidate.selection_score,
                  candidate.nearest_distance, candidate.center_ratio,
                  candidate.relative_area, candidate.pair_fill,
                  candidate.pair_aspect, candidate.color_shape.aspect,
                  candidate.white_eigen_ratio, candidate.attachment,
                  candidate.taper_ratio, candidate.color_touches_roi,
                  candidate.white_touches_roi);
        }
        trigger_color = candidate.color_found;
        trigger_white = candidate.white_found;
        trigger_pair = candidate.pair_found;
        refined_color += (uint32_t)trigger_color;
        refined_white += (uint32_t)trigger_white;
        refined_pair += (uint32_t)trigger_pair;
        if (!trigger_color) reject_no_color++;
        else if (!trigger_white || !trigger_pair) reject_no_white++;
        else if (!candidate.valid) reject_geometry++;
        if (candidate.pair_found &&
            (!have_diagnostic || candidate.selection_score >
                                 best_diagnostic.selection_score)) {
            best_diagnostic = candidate;
            have_diagnostic = 1;
        }
        if (candidate.valid &&
            (!have_best || candidate.selection_score > best.selection_score)) {
            best = candidate;
            have_best = 1;
        }
    }
    TRACE("source refine summary source_refine_trigger=%d source_refine_roi=%u pixels=%u max_roi=%u source_refine_color_found=%u source_refine_white_found=%u source_refine_pair_found=%u source_refine_reject_no_color=%u source_refine_reject_no_white=%u source_refine_reject_geometry=%u source_refine_accept=%d\n",
          color_count, roi_calls, roi_pixels, max_roi_pixels, refined_color,
          refined_white, refined_pair, reject_no_color, reject_no_white,
          reject_geometry, have_best);
#ifdef VISION_SOURCE_REFINEMENT_DIAGNOSTICS
    source_refinement_stats.coarse_color_triggers = (uint32_t)color_count;
    source_refinement_stats.roi_calls = roi_calls;
    source_refinement_stats.roi_pixels = roi_pixels;
    source_refinement_stats.max_roi_pixels = max_roi_pixels;
    source_refinement_stats.refined_color_found = refined_color;
    source_refinement_stats.refined_white_found = refined_white;
    source_refinement_stats.refined_pair_found = refined_pair;
    source_refinement_stats.reject_no_color = reject_no_color;
    source_refinement_stats.reject_no_white = reject_no_white;
    source_refinement_stats.reject_geometry = reject_geometry;
    source_refinement_stats.accepted = have_best ? 1U : 0U;
    if (have_best) source_record_best_diagnostics(&best);
    else if (have_diagnostic) source_record_best_diagnostics(&best_diagnostic);
#endif
    if (!have_best) return 0;
    {
        VisionDetection *detection = output;
        uint32_t min_x = best.color.min_x < best.white.min_x ?
                         best.color.min_x : best.white.min_x;
        uint32_t min_y = best.color.min_y < best.white.min_y ?
                         best.color.min_y : best.white.min_y;
        uint32_t max_x = best.color.max_x > best.white.max_x ?
                         best.color.max_x : best.white.max_x;
        uint32_t max_y = best.color.max_y > best.white.max_y ?
                         best.color.max_y : best.white.max_y;
        float combined_count = (float)(best.color.count+best.white.count);
        float combined_cx = (float)best.roi.x0+
            (best.color_shape.cx*(float)best.color.count+
             best.white_shape.cx*(float)best.white.count)/combined_count;
        float combined_cy = (float)best.roi.y0+
            (best.color_shape.cy*(float)best.color.count+
             best.white_shape.cy*(float)best.white.count)/combined_count;
        float color_cx = (float)best.roi.x0+best.direction_center_x;
        float color_cy = (float)best.roi.y0+best.direction_center_y;
        memset(detection, 0, sizeof(*detection));
        detection->type = VISION_SOURCE;
        detection->center_x = (int)lroundf(combined_cx);
        detection->center_y = (int)lroundf(combined_cy);
        detection->geometry_center_x = combined_cx;
        detection->geometry_center_y = combined_cy;
        detection->bbox_x = (int)(best.roi.x0+min_x);
        detection->bbox_y = (int)(best.roi.y0+min_y);
        detection->bbox_w = (int)(max_x-min_x+1U);
        detection->bbox_h = (int)(max_y-min_y+1U);
        detection->angle_deg = (int)lroundf(
            atan2f(best.direction_y, best.direction_x)*180.0f/PI_F);
        detection->confidence_percent = 100;
        detection->sampled_area = best.color.count+best.white.count;
        detection->axis_x = best.direction_x;
        detection->axis_y = best.direction_y;
        detection->major_length = best.combined_shape.major;
        detection->minor_width = best.combined_shape.minor;
        detection->source_tip_x = (int)lroundf(
            color_cx+best.direction_x*best.robust_tip_projection);
        detection->source_tip_y = (int)lroundf(
            color_cy+best.direction_y*best.robust_tip_projection);
        detection->source_direction_x = best.direction_x;
        detection->source_direction_y = best.direction_y;
        detection->direction_valid = 1;
        TRACE("source_refine_accept roi=(%u,%u %ux%u) color=%u@(%.1f,%.1f) white=%u@(%.1f,%.1f) pair=(%d,%d %dx%d) nearest=%.2f center=%.3f area=%.3f fill=%.3f aspect=%.3f white_pca=%.3f white_normal=%.3f attachment=%.3f taper=%.3f color_axis=(%.3f,%.3f) white_axis=(%.3f,%.3f) attached_axis=(%.3f,%.3f) angle=%d\n",
              best.roi.x0, best.roi.y0, best.roi.x1-best.roi.x0,
              best.roi.y1-best.roi.y0, best.color.count,
              best.roi.x0+best.color_shape.cx,
              best.roi.y0+best.color_shape.cy, best.white.count,
              best.roi.x0+best.white_shape.cx,
              best.roi.y0+best.white_shape.cy, detection->bbox_x,
              detection->bbox_y, detection->bbox_w, detection->bbox_h,
              best.nearest_distance, best.center_ratio, best.relative_area,
              best.pair_fill, best.pair_aspect, best.white_eigen_ratio,
              best.white_normal, best.attachment, best.taper_ratio,
              best.color_shape.ux, best.color_shape.uy,
              best.white_shape.ux, best.white_shape.uy,
              best.white_axis_shape.ux, best.white_axis_shape.uy,
              detection->angle_deg);
    }
    return 1;
}

#else

static float source_marker_part_gap(const SourceMarkerPart *first,
                                    const SourceMarkerPart *second)
{
    float gap_x = 0.0f;
    float gap_y = 0.0f;
    if (first->max_x < second->min_x)
        gap_x = (float)(second->min_x-first->max_x-1U);
    else if (second->max_x < first->min_x)
        gap_x = (float)(first->min_x-second->max_x-1U);
    if (first->max_y < second->min_y)
        gap_y = (float)(second->min_y-first->max_y-1U);
    else if (second->max_y < first->min_y)
        gap_y = (float)(first->min_y-second->max_y-1U);
    return sqrtf(gap_x*gap_x+gap_y*gap_y);
}

static int source_color_tapers(const Component *component, uint32_t grid_w,
                               float direction_x, float direction_y,
                               float *robust_tip_projection)
{
    float min_projection = 0.0f;
    float max_projection = 0.0f;
    float front_sum = 0.0f;
    uint32_t front_count = 0U;
    uint32_t back_count = 0U;
    uint32_t index;
    for (index = 0; index < component->count; ++index) {
        uint32_t cell = queue_storage[index];
        float dx = (float)(cell%grid_w)-
                   (float)component->sum_x/(float)component->count;
        float dy = (float)(cell/grid_w)-
                   (float)component->sum_y/(float)component->count;
        float projection = dx*direction_x+dy*direction_y;
        if (index == 0U || projection < min_projection)
            min_projection = projection;
        if (index == 0U || projection > max_projection)
            max_projection = projection;
    }
    if (max_projection-min_projection < 2.0f) return 0;
    for (index = 0; index < component->count; ++index) {
        uint32_t cell = queue_storage[index];
        float dx = (float)(cell%grid_w)-
                   (float)component->sum_x/(float)component->count;
        float dy = (float)(cell/grid_w)-
                   (float)component->sum_y/(float)component->count;
        float projection = dx*direction_x+dy*direction_y;
        if (projection <= min_projection+
                0.30f*(max_projection-min_projection))
            back_count++;
        if (projection >= max_projection-
                0.30f*(max_projection-min_projection)) {
            front_sum += projection;
            front_count++;
        }
    }
    if (!front_count || !back_count ||
        (float)front_count >
            (float)back_count*VISION_SOURCE_MARKER_FRONT_BACK_MAX)
        return 0;
    *robust_tip_projection = front_sum/(float)front_count;
    return 1;
}

static int detect_marker_source(const uint8_t *frame, uint32_t stride,
                                VisionDetection *output, int output_capacity,
                                uint32_t width, uint32_t height,
                                uint32_t grid_w, uint32_t grid_h)
{
    SourceMarkerPart color_parts[VISION_SOURCE_MARKER_MAX_PARTS];
    SourceMarkerPart white_parts[VISION_SOURCE_MARKER_MAX_PARTS];
    const SourceMarkerPart *best_color = NULL;
    const SourceMarkerPart *best_white = NULL;
    float best_score = 0.0f;
    float second_score = 0.0f;
    SourceMarkerPartStats color_stats;
    SourceMarkerPartStats white_stats;
    int color_count;
    int white_count;
    int color_index;
    (void)frame;
    (void)stride;
    if (output_capacity <= 0) return 0;
    color_count = collect_source_marker_parts(
        SOURCE_MARKER_COLOR, grid_w, grid_h, color_parts, &color_stats);
    white_count = collect_source_marker_parts(
        SOURCE_MARKER_WHITE, grid_w, grid_h, white_parts, &white_stats);
    TRACE("source marker parts total_color_parts=%u kept_color_parts=%u overflow_color_parts=%u total_white_parts=%u kept_white_parts=%u overflow_white_parts=%u\n",
          color_stats.total_parts, color_stats.kept_parts,
          color_stats.overflow_parts, white_stats.total_parts,
          white_stats.kept_parts, white_stats.overflow_parts);
#ifdef VISION_TRACE
    {
        int region_y;
        for (region_y = 0; region_y < VISION_SOURCE_MARKER_REGION_ROWS;
             ++region_y) {
            int offset = region_y*VISION_SOURCE_MARKER_REGION_COLS;
            fprintf(stderr,
                    "source marker regions row=%d color=%u,%u,%u,%u white=%u,%u,%u,%u\n",
                    region_y,
                    color_stats.region_counts[offset],
                    color_stats.region_counts[offset+1],
                    color_stats.region_counts[offset+2],
                    color_stats.region_counts[offset+3],
                    white_stats.region_counts[offset],
                    white_stats.region_counts[offset+1],
                    white_stats.region_counts[offset+2],
                    white_stats.region_counts[offset+3]);
        }
    }
#endif
    for (color_index = 0; color_index < color_count; ++color_index) {
        const SourceMarkerPart *color = &color_parts[color_index];
        int white_index;
        for (white_index = 0; white_index < white_count; ++white_index) {
            const SourceMarkerPart *white = &white_parts[white_index];
            uint32_t min_x = color->min_x < white->min_x ?
                color->min_x : white->min_x;
            uint32_t min_y = color->min_y < white->min_y ?
                color->min_y : white->min_y;
            uint32_t max_x = color->max_x > white->max_x ?
                color->max_x : white->max_x;
            uint32_t max_y = color->max_y > white->max_y ?
                color->max_y : white->max_y;
            float bbox_w = (float)(max_x-min_x+1U);
            float bbox_h = (float)(max_y-min_y+1U);
            float bbox_area = bbox_w*bbox_h;
            float aspect = bbox_w > bbox_h ? bbox_w/bbox_h : bbox_h/bbox_w;
            float fill = (float)(color->count+white->count)/bbox_area;
            float white_color_ratio = (float)white->count/(float)color->count;
            float dx = color->cx-white->cx;
            float dy = color->cy-white->cy;
            float center_distance = sqrtf(dx*dx+dy*dy);
            float max_dimension = bbox_w > bbox_h ? bbox_w : bbox_h;
            float center_ratio = center_distance/max_dimension;
            float marker_axis_x;
            float marker_axis_y;
            float axis_alignment;
            float score = (float)(color->count+white->count)*fill;
            float selection_score = score*fill/aspect;
            if (center_distance <= 0.0f) continue;
            marker_axis_x = dx/center_distance;
            marker_axis_y = dy/center_distance;
            axis_alignment = fabsf(marker_axis_x*color->ux+
                                   marker_axis_y*color->uy);
            if (source_marker_part_gap(color, white) >
                    VISION_SOURCE_MARKER_MAX_GAP_CELLS ||
                white_color_ratio < VISION_SOURCE_MARKER_WHITE_COLOR_RATIO_MIN ||
                white_color_ratio > VISION_SOURCE_MARKER_WHITE_COLOR_RATIO_MAX ||
                aspect > VISION_SOURCE_MARKER_ASPECT_MAX ||
                fill < VISION_SOURCE_MARKER_FILL_MIN ||
                center_ratio < VISION_SOURCE_MARKER_CENTER_RATIO_MIN ||
                center_ratio > VISION_SOURCE_MARKER_CENTER_RATIO_MAX ||
                color->aspect > VISION_SOURCE_MARKER_COLOR_ASPECT_MAX ||
                axis_alignment < VISION_SOURCE_MARKER_AXIS_ALIGNMENT_MIN ||
                score < VISION_SOURCE_MARKER_SCORE_MIN)
                continue;
            TRACE("source candidate color=%u@(%.1f,%.1f) white=%u@(%.1f,%.1f) aspect=%.2f fill=%.2f support=%.2f rank=%.3f\n",
                  color->count, color->cx, color->cy,
                  white->count, white->cx, white->cy, aspect, fill, score,
                  selection_score);
            if (!best_color || selection_score > best_score) {
                second_score = best_score;
                best_color = color;
                best_white = white;
                best_score = selection_score;
            } else if (selection_score > second_score) {
                second_score = selection_score;
            }
        }
    }
    if (!best_color || !best_white ||
        (second_score > 0.0f &&
         best_score < second_score*VISION_SOURCE_MARKER_SELECTION_RATIO_MIN))
        return 0;
    {
        Component color_component;
        Component white_component;
        Component combined_component;
        Shape combined_shape;
        VisionDetection *detection = output;
        uint32_t min_x = best_color->min_x < best_white->min_x ?
            best_color->min_x : best_white->min_x;
        uint32_t min_y = best_color->min_y < best_white->min_y ?
            best_color->min_y : best_white->min_y;
        uint32_t max_x = best_color->max_x > best_white->max_x ?
            best_color->max_x : best_white->max_x;
        uint32_t max_y = best_color->max_y > best_white->max_y ?
            best_color->max_y : best_white->max_y;
        uint32_t pixel_x1 = (max_x+1U)*VISION_SAMPLE_STEP;
        uint32_t pixel_y1 = (max_y+1U)*VISION_SAMPLE_STEP;
        float direction_x;
        float direction_y;
        float robust_tip_projection;
        float combined_count = (float)(best_color->count+best_white->count);
        float combined_cx = (best_color->cx*(float)best_color->count+
                             best_white->cx*(float)best_white->count)/
                            combined_count;
        float combined_cy = (best_color->cy*(float)best_color->count+
                             best_white->cy*(float)best_white->count)/
                            combined_count;
        memset(visited, 0, grid_w*grid_h);
        collect_source_marker_component(best_color->seed, SOURCE_MARKER_COLOR,
                                        grid_w, grid_h, &color_component);
        memset(visited, 0, grid_w*grid_h);
        collect_source_marker_component(best_white->seed, SOURCE_MARKER_WHITE,
                                        grid_w, grid_h, &white_component);
        merge_source_components(&color_component, &white_component,
                                &combined_component);
        if (!describe_component(&combined_component, &combined_shape)) return 0;
        direction_x = best_color->cx-best_white->cx;
        direction_y = best_color->cy-best_white->cy;
        {
            float direction_length = sqrtf(direction_x*direction_x+
                                           direction_y*direction_y);
            if (direction_length <= 0.0f) return 0;
            direction_x /= direction_length;
            direction_y /= direction_length;
        }
        memset(visited, 0, grid_w*grid_h);
        collect_source_marker_component(best_color->seed, SOURCE_MARKER_COLOR,
                                        grid_w, grid_h, &color_component);
        if (!source_color_tapers(&color_component, grid_w, direction_x,
                                 direction_y, &robust_tip_projection))
            return 0;
        if (pixel_x1 > width) pixel_x1 = width;
        if (pixel_y1 > height) pixel_y1 = height;
        memset(detection, 0, sizeof(*detection));
        detection->type = VISION_SOURCE;
        detection->center_x = (int)lroundf(
            combined_cx*VISION_SAMPLE_STEP+1.5f);
        detection->center_y = (int)lroundf(
            combined_cy*VISION_SAMPLE_STEP+1.5f);
        detection->geometry_center_x = (float)detection->center_x;
        detection->geometry_center_y = (float)detection->center_y;
        detection->bbox_x = (int)(min_x*VISION_SAMPLE_STEP);
        detection->bbox_y = (int)(min_y*VISION_SAMPLE_STEP);
        detection->bbox_w = (int)pixel_x1-detection->bbox_x;
        detection->bbox_h = (int)pixel_y1-detection->bbox_y;
        detection->angle_deg = (int)lroundf(
            atan2f(direction_y, direction_x)*180.0f/PI_F);
        detection->confidence_percent = 100;
        detection->sampled_area = (best_color->count+best_white->count)*
                                  VISION_SAMPLE_STEP*VISION_SAMPLE_STEP;
        detection->axis_x = direction_x;
        detection->axis_y = direction_y;
        detection->major_length = combined_shape.major*VISION_SAMPLE_STEP;
        detection->minor_width = combined_shape.minor*VISION_SAMPLE_STEP;
        detection->source_tip_x = (int)lroundf(
            (best_color->cx+direction_x*robust_tip_projection)*
            VISION_SAMPLE_STEP+1.5f);
        detection->source_tip_y = (int)lroundf(
            (best_color->cy+direction_y*robust_tip_projection)*
            VISION_SAMPLE_STEP+1.5f);
        detection->source_direction_x = direction_x;
        detection->source_direction_y = direction_y;
        detection->direction_valid = 1;
        TRACE("source marker color=%u@(%.1f,%.1f) white=%u@(%.1f,%.1f) rank=%.3f angle=%d\n",
              best_color->count, best_color->cx, best_color->cy,
              best_white->count, best_white->cx, best_white->cy,
              best_score, detection->angle_deg);
    }
    return 1;
}

#endif

static int boxes_overlap_wall(const VisionDetection *detections, int count,
                              const Component *wall)
{
    int wx0 = (int)wall->min_x * VISION_SAMPLE_STEP;
    int wy0 = (int)wall->min_y * VISION_SAMPLE_STEP;
    int wx1 = ((int)wall->max_x + 1) * VISION_SAMPLE_STEP;
    int wy1 = ((int)wall->max_y + 1) * VISION_SAMPLE_STEP;
    int wall_area = (wx1-wx0)*(wy1-wy0);
    int i;
    for (i = 0; i < count; ++i) {
        int x0;
        int y0;
        int x1;
        int y1;
        int overlap;
        x0 = detections[i].bbox_x > wx0 ? detections[i].bbox_x : wx0;
        y0 = detections[i].bbox_y > wy0 ? detections[i].bbox_y : wy0;
        x1 = detections[i].bbox_x+detections[i].bbox_w < wx1 ?
             detections[i].bbox_x+detections[i].bbox_w : wx1;
        y1 = detections[i].bbox_y+detections[i].bbox_h < wy1 ?
             detections[i].bbox_y+detections[i].bbox_h : wy1;
        overlap = (x1>x0 && y1>y0) ? (x1-x0)*(y1-y0) : 0;
        if ((uint32_t)overlap * 100U >
            (uint32_t)wall_area * VISION_WALL_COLORED_OVERLAP_PERCENT) return 1;
    }
    return 0;
}

static void fill_detection(VisionDetection *detection, VisionType type,
                           const Component *component, const Shape *shape,
                           uint32_t width, uint32_t height, int angle_deg)
{
    uint32_t x1 = (component->max_x+1U) * VISION_SAMPLE_STEP;
    uint32_t y1 = (component->max_y+1U) * VISION_SAMPLE_STEP;
    float radians = (float)angle_deg*PI_F/180.0f;
    float axis_x = cosf(radians);
    float axis_y = sinf(radians);
    float normal_x = -axis_y;
    float normal_y = axis_x;
    float min_longitudinal = 0.0f;
    float max_longitudinal = 0.0f;
    float min_transverse = 0.0f;
    float max_transverse = 0.0f;
    uint32_t grid_w = width/VISION_SAMPLE_STEP;
    uint32_t index;
    memset(detection, 0, sizeof(*detection));
    detection->type = type;
    detection->center_x = (int)lroundf(shape->cx*VISION_SAMPLE_STEP + 1.5f);
    detection->center_y = (int)lroundf(shape->cy*VISION_SAMPLE_STEP + 1.5f);
    for (index = 0; index < component->count; ++index) {
        uint32_t cell = queue_storage[index];
        float x = (float)(cell%grid_w)*VISION_SAMPLE_STEP + 1.5f;
        float y = (float)(cell/grid_w)*VISION_SAMPLE_STEP + 1.5f;
        float longitudinal = x*axis_x + y*axis_y;
        float transverse = x*normal_x + y*normal_y;
        if (index == 0U || longitudinal < min_longitudinal)
            min_longitudinal = longitudinal;
        if (index == 0U || longitudinal > max_longitudinal)
            max_longitudinal = longitudinal;
        if (index == 0U || transverse < min_transverse)
            min_transverse = transverse;
        if (index == 0U || transverse > max_transverse)
            max_transverse = transverse;
    }
    detection->geometry_center_x =
        axis_x*0.5f*(min_longitudinal+max_longitudinal) +
        normal_x*0.5f*(min_transverse+max_transverse);
    detection->geometry_center_y =
        axis_y*0.5f*(min_longitudinal+max_longitudinal) +
        normal_y*0.5f*(min_transverse+max_transverse);
    detection->bbox_x = (int)(component->min_x * VISION_SAMPLE_STEP);
    detection->bbox_y = (int)(component->min_y * VISION_SAMPLE_STEP);
    if (x1 > width) x1 = width;
    if (y1 > height) y1 = height;
    detection->bbox_w = (int)x1 - detection->bbox_x;
    detection->bbox_h = (int)y1 - detection->bbox_y;
    detection->angle_deg = type == VISION_TARGET ? 0 : angle_deg;
    detection->confidence_percent =
        type == VISION_WALL ? 75 : (type == VISION_SOURCE ? 80 : (type == VISION_TARGET ? 96 : 99));
    detection->sampled_area = component->count * VISION_SAMPLE_STEP *
                              VISION_SAMPLE_STEP;
    detection->axis_x = axis_x;
    detection->axis_y = axis_y;
    detection->major_length = max_longitudinal-min_longitudinal+
                              VISION_SAMPLE_STEP;
    detection->minor_width = max_transverse-min_transverse+
                             VISION_SAMPLE_STEP;
}

static int detect_marker_walls(VisionDetection *output, int output_capacity,
                               uint32_t width, uint32_t height,
                               uint32_t grid_w, uint32_t grid_h)
{
    WallMarker markers[VISION_WALL_MARKER_MAX_CANDIDATES];
    uint32_t pixels = grid_w * grid_h;
    int marker_count = 0;
    int result_count = 0;
    uint32_t seed;
    int first_index;
    memset(visited, 0, pixels);
    for (seed = 0; seed < pixels; ++seed) {
        Component component;
        Shape shape;
        if (visited[seed] || !wall_marker_mask[seed]) continue;
        collect_wall_marker_component(seed, grid_w, grid_h, &component);
        if (component.count < VISION_WALL_MARKER_MIN_SAMPLES ||
            component.count > VISION_WALL_MARKER_MAX_SAMPLES ||
            !describe_component(&component, &shape) ||
            shape.aspect < VISION_WALL_MARKER_ASPECT_MIN ||
            shape.aspect > VISION_WALL_MARKER_ASPECT_MAX ||
            shape.fill < VISION_WALL_MARKER_FILL_MIN)
            continue;
        if (marker_count < VISION_WALL_MARKER_MAX_CANDIDATES) {
            markers[marker_count].shape = shape;
            markers[marker_count].count = component.count;
            marker_count++;
        }
    }
    for (first_index = 0; first_index < marker_count; ++first_index) {
        int second_index;
        const Shape *first = &markers[first_index].shape;
        for (second_index = first_index + 1;
             second_index < marker_count && result_count < output_capacity;
             ++second_index) {
            const Shape *second = &markers[second_index].shape;
            float dx;
            float dy;
            float distance;
            float axis_x;
            float axis_y;
            float average_major;
            float average_minor;
            float spacing;
            float parallel_dot;
            float first_perpendicular_dot;
            float second_perpendicular_dot;
            float center_x;
            float center_y;
            float corridor_half_long;
            float corridor_half_short;
            float corridor_extent_x;
            float corridor_extent_y;
            int corridor_x0;
            int corridor_x1;
            int corridor_y0;
            int corridor_y1;
            uint32_t corridor_total = 0;
            uint32_t corridor_dark = 0;
            float half_long;
            float half_short;
            float extent_x;
            float extent_y;
            uint32_t area_pixels;
            int bbox_x0;
            int bbox_y0;
            int bbox_x1;
            int bbox_y1;
            int angle_deg;
            int y;
            if (fmaxf(first->major, second->major) /
                    fminf(first->major, second->major) >
                        VISION_WALL_MARKER_MAJOR_RATIO_MAX ||
                fmaxf(first->minor, second->minor) /
                    fminf(first->minor, second->minor) >
                        VISION_WALL_MARKER_MINOR_RATIO_MAX)
                continue;
            dx = second->cx - first->cx;
            dy = second->cy - first->cy;
            distance = sqrtf(dx*dx + dy*dy);
            if (distance <= 0.0f) continue;
            axis_x = dx / distance;
            axis_y = dy / distance;
            average_major = 0.5f * (first->major + second->major);
            average_minor = 0.5f * (first->minor + second->minor);
            spacing = distance / average_major;
            if (spacing < VISION_WALL_MARKER_SPACING_MIN ||
                spacing > VISION_WALL_MARKER_SPACING_MAX)
                continue;
            parallel_dot = fabsf(first->ux*second->ux + first->uy*second->uy);
            first_perpendicular_dot = fabsf(first->ux*axis_x + first->uy*axis_y);
            second_perpendicular_dot = fabsf(second->ux*axis_x + second->uy*axis_y);
            if (parallel_dot < VISION_WALL_MARKER_PARALLEL_DOT_MIN ||
                first_perpendicular_dot > VISION_WALL_MARKER_PERP_DOT_MAX ||
                second_perpendicular_dot > VISION_WALL_MARKER_PERP_DOT_MAX)
                continue;
            center_x = 0.5f * (first->cx + second->cx);
            center_y = 0.5f * (first->cy + second->cy);
            corridor_half_long = distance * VISION_WALL_MARKER_LONGITUDINAL;
            corridor_half_short = average_major * VISION_WALL_MARKER_TRANSVERSE;
            corridor_extent_x = fabsf(axis_x)*corridor_half_long +
                                fabsf(axis_y)*corridor_half_short;
            corridor_extent_y = fabsf(axis_y)*corridor_half_long +
                                fabsf(axis_x)*corridor_half_short;
            corridor_x0 = (int)floorf(center_x-corridor_extent_x);
            corridor_x1 = (int)ceilf(center_x+corridor_extent_x);
            corridor_y0 = (int)floorf(center_y-corridor_extent_y);
            corridor_y1 = (int)ceilf(center_y+corridor_extent_y);
            for (y = corridor_y0; y <= corridor_y1; ++y) {
                int x;
                if (y < 0 || y >= (int)grid_h) continue;
                for (x = corridor_x0; x <= corridor_x1; ++x) {
                    float local_x;
                    float local_y;
                    float longitudinal;
                    float transverse;
                    if (x < 0 || x >= (int)grid_w) continue;
                    local_x = (float)x - center_x;
                    local_y = (float)y - center_y;
                    longitudinal = local_x*axis_x + local_y*axis_y;
                    transverse = -local_x*axis_y + local_y*axis_x;
                    if (fabsf(longitudinal) > corridor_half_long ||
                        fabsf(transverse) > corridor_half_short)
                        continue;
                    corridor_total++;
                    if (pixel_v[(uint32_t)y*grid_w+(uint32_t)x] <=
                            VISION_WALL_MARKER_DARK_V_MAX)
                        corridor_dark++;
                }
            }
            if (corridor_total < VISION_WALL_MARKER_MIN_SAMPLES ||
                corridor_dark * 100U <
                    corridor_total * VISION_WALL_MARKER_DARK_PERCENT_MIN)
                continue;
            half_long = distance*0.5f + average_minor*0.75f;
            half_short = average_major*0.5f + average_minor*0.5f;
            area_pixels = (uint32_t)lroundf(4.0f * half_long * half_short *
                                            VISION_SAMPLE_STEP * VISION_SAMPLE_STEP);
            if (area_pixels < VISION_WALL_MIN_AREA_PIXELS ||
                area_pixels > width*height*VISION_WALL_MAX_FRAME_FRACTION_PERCENT/100U)
                continue;
            extent_x = fabsf(axis_x)*half_long + fabsf(axis_y)*half_short;
            extent_y = fabsf(axis_y)*half_long + fabsf(axis_x)*half_short;
            bbox_x0 = (int)floorf((center_x-extent_x)*VISION_SAMPLE_STEP + 1.5f);
            bbox_y0 = (int)floorf((center_y-extent_y)*VISION_SAMPLE_STEP + 1.5f);
            bbox_x1 = (int)ceilf((center_x+extent_x)*VISION_SAMPLE_STEP + 1.5f);
            bbox_y1 = (int)ceilf((center_y+extent_y)*VISION_SAMPLE_STEP + 1.5f);
            if (bbox_x0 < 0) bbox_x0 = 0;
            if (bbox_y0 < 0) bbox_y0 = 0;
            if (bbox_x1 > (int)width) bbox_x1 = (int)width;
            if (bbox_y1 > (int)height) bbox_y1 = (int)height;
            if (bbox_x1 <= bbox_x0 || bbox_y1 <= bbox_y0) continue;
            angle_deg = (int)lroundf(atan2f(axis_y, axis_x)*180.0f/PI_F);
            if (angle_deg >= 90) angle_deg -= 180;
            if (angle_deg < -90) angle_deg += 180;
            memset(&output[result_count], 0, sizeof(output[result_count]));
            output[result_count].type = VISION_WALL;
            output[result_count].center_x =
                (int)lroundf(center_x*VISION_SAMPLE_STEP + 1.5f);
            output[result_count].center_y =
                (int)lroundf(center_y*VISION_SAMPLE_STEP + 1.5f);
            output[result_count].geometry_center_x =
                (float)output[result_count].center_x;
            output[result_count].geometry_center_y =
                (float)output[result_count].center_y;
            output[result_count].bbox_x = bbox_x0;
            output[result_count].bbox_y = bbox_y0;
            output[result_count].bbox_w = bbox_x1-bbox_x0;
            output[result_count].bbox_h = bbox_y1-bbox_y0;
            output[result_count].angle_deg = angle_deg;
            output[result_count].confidence_percent = 100;
            output[result_count].sampled_area = area_pixels;
            output[result_count].axis_x = axis_x;
            output[result_count].axis_y = axis_y;
            output[result_count].major_length =
                2.0f*half_long*VISION_SAMPLE_STEP;
            output[result_count].minor_width =
                2.0f*half_short*VISION_SAMPLE_STEP;
            TRACE("wall markers n=%u/%u spacing=%.2f dark=%u/%u angle=%d\n",
                  markers[first_index].count, markers[second_index].count,
                  spacing, corridor_dark, corridor_total, angle_deg);
            result_count++;
        }
    }
    return result_count;
}

static int overlap_percent(const VisionDetection *first,
                           const VisionDetection *second)
{
    int x0 = first->bbox_x > second->bbox_x ? first->bbox_x : second->bbox_x;
    int y0 = first->bbox_y > second->bbox_y ? first->bbox_y : second->bbox_y;
    int x1 = first->bbox_x + first->bbox_w < second->bbox_x + second->bbox_w ?
             first->bbox_x + first->bbox_w : second->bbox_x + second->bbox_w;
    int y1 = first->bbox_y + first->bbox_h < second->bbox_y + second->bbox_h ?
             first->bbox_y + first->bbox_h : second->bbox_y + second->bbox_h;
    int intersection = x1 > x0 && y1 > y0 ? (x1-x0) * (y1-y0) : 0;
    int first_area = first->bbox_w * first->bbox_h;
    int second_area = second->bbox_w * second->bbox_h;
    int union_area = first_area + second_area - intersection;
    return union_area > 0 ? intersection * 100 / union_area : 0;
}

static int sort_and_suppress(VisionDetection *detections, int count)
{
    int i;
    int kept = 0;
    for (i = 0; i < count; ++i) {
        int best = i;
        int j;
        for (j = i + 1; j < count; ++j) {
            if (detections[j].confidence_percent >
                    detections[best].confidence_percent ||
                (detections[j].confidence_percent ==
                     detections[best].confidence_percent &&
                 detections[j].sampled_area > detections[best].sampled_area))
                best = j;
        }
        if (best != i) {
            VisionDetection temporary = detections[i];
            detections[i] = detections[best];
            detections[best] = temporary;
        }
    }
    for (i = 0; i < count; ++i) {
        int duplicate = 0;
        int j;
        for (j = 0; j < kept; ++j) {
            if (overlap_percent(&detections[i], &detections[j]) >= 50) {
                duplicate = 1;
                break;
            }
        }
        if (!duplicate) detections[kept++] = detections[i];
    }
    return kept;
}

static int detection_is_in_playfield(const VisionDetection *detection,
                                     uint32_t width, uint32_t height)
{
    if (width != VISION_FIXED_CAMERA_WIDTH || height != VISION_FIXED_CAMERA_HEIGHT)
        return 1;
    return detection->center_x >= VISION_PLAYFIELD_X_MIN &&
           detection->center_x <= VISION_PLAYFIELD_X_MAX &&
           detection->center_y < VISION_PLAYFIELD_Y_MAX;
}

static int mirror_is_covered_by_source(const VisionDetection *mirror,
                                       const VisionDetection *source)
{
    int x0 = mirror->bbox_x > source->bbox_x ?
             mirror->bbox_x : source->bbox_x;
    int y0 = mirror->bbox_y > source->bbox_y ?
             mirror->bbox_y : source->bbox_y;
    int x1 = mirror->bbox_x + mirror->bbox_w < source->bbox_x + source->bbox_w ?
             mirror->bbox_x + mirror->bbox_w : source->bbox_x + source->bbox_w;
    int y1 = mirror->bbox_y + mirror->bbox_h < source->bbox_y + source->bbox_h ?
             mirror->bbox_y + mirror->bbox_h : source->bbox_y + source->bbox_h;
    int overlap = x1 > x0 && y1 > y0 ? (x1-x0)*(y1-y0) : 0;
    int mirror_area = mirror->bbox_w*mirror->bbox_h;
    return mirror_area > 0 && (uint32_t)overlap * 100U >=
           (uint32_t)mirror_area * VISION_SOURCE_MIRROR_OVERLAP_PERCENT;
}

static int filter_fixed_camera_detections(VisionDetection *detections, int count,
                                          uint32_t width, uint32_t height)
{
    int index;
    int kept = 0;
    for (index = 0; index < count; ++index) {
        int source_index;
        int covered = 0;
        if (!detection_is_in_playfield(&detections[index], width, height))
            continue;
        if (detections[index].type == VISION_MIRROR) {
            for (source_index = 0; source_index < count; ++source_index) {
                if (detections[source_index].type == VISION_SOURCE &&
                    mirror_is_covered_by_source(&detections[index],
                                                &detections[source_index])) {
                    covered = 1;
                    break;
                }
            }
        }
        if (!covered) detections[kept++] = detections[index];
    }
    return kept;
}

int vision_detect_objects_bgr888(const uint8_t *frame, uint32_t width,
                                 uint32_t height, uint32_t stride,
                                 VisionDetection *output,
                                 int output_capacity)
{
    static const uint8_t body_bits[4] = {
        BIT_YELLOW, BIT_BLUE, BIT_ORANGE, BIT_WALL
    };
    static const VisionType body_types[4] = {
        VISION_MIRROR, VISION_PORTAL_A, VISION_PORTAL_B,
        VISION_WALL
    };
    uint32_t grid_w;
    uint32_t grid_h;
    int result_count = 0;
    int body_index;
    if (!frame || !output || output_capacity <= 0 || width < VISION_SAMPLE_STEP ||
        height < VISION_SAMPLE_STEP || stride < width*3U) return -1;
    grid_w = width / VISION_SAMPLE_STEP;
    grid_h = height / VISION_SAMPLE_STEP;
    if (grid_w > GRID_MAX_W || grid_h > GRID_MAX_H ||
        width > GRID_MAX_W * VISION_SAMPLE_STEP ||
        height > GRID_MAX_H * VISION_SAMPLE_STEP) return -2;
#ifdef VISION_SOURCE_REFINEMENT_DIAGNOSTICS
    memset(&source_refinement_stats, 0, sizeof(source_refinement_stats));
#endif
    create_masks(frame, stride, grid_w, grid_h);
    result_count = detect_marker_walls(output, output_capacity, width, height,
                                       grid_w, grid_h);
    if (result_count < output_capacity)
        result_count += detect_marker_source(
            frame, stride, output+result_count,
            output_capacity-result_count, width, height, grid_w, grid_h);
    for (body_index = 0; body_index < 4 && result_count < output_capacity; ++body_index) {
        uint8_t bit = body_bits[body_index];
        VisionType type = body_types[body_index];
        uint32_t pixels = grid_w * grid_h;
        uint32_t seed;
        memset(visited, 0, pixels);
        for (seed = 0; seed < pixels && result_count < output_capacity; ++seed) {
            Component component;
            Shape shape;
            int geometry_pass;
            int marker_pass;
            int angle_deg;
            int allow_refined_portal;
            if (visited[seed] || !(pixel_masks[seed] & bit)) continue;
            collect_component(seed, bit, grid_w, grid_h, &component);
            if (component.count < VISION_MIN_COMPONENT_SAMPLES ||
                component.count * VISION_SAMPLE_STEP * VISION_SAMPLE_STEP >
                    width * height * VISION_MAX_FRAME_FRACTION_PERCENT / 100U ||
                !describe_component(&component, &shape)) continue;
            if ((type == VISION_PORTAL_A || type == VISION_PORTAL_B) &&
                component.count * VISION_SAMPLE_STEP * VISION_SAMPLE_STEP <
                    VISION_PORTAL_MIN_AREA_PIXELS)
                continue;
            if (type == VISION_WALL &&
                (component.count * VISION_SAMPLE_STEP * VISION_SAMPLE_STEP <
                     VISION_WALL_MIN_AREA_PIXELS ||
                 component.count * VISION_SAMPLE_STEP * VISION_SAMPLE_STEP >
                     width * height * VISION_WALL_MAX_FRAME_FRACTION_PERCENT / 100U))
                continue;
            angle_deg = shape.angle_deg;
            geometry_pass = geometry_ok(type, &shape);
            allow_refined_portal = component.min_x > 0U &&
                                   component.min_y > 0U &&
                                   component.max_x + 1U < grid_w &&
                                   component.max_y + 1U < grid_h;
            marker_pass = geometry_pass ?
                verify_markers(type, bit, &shape, frame, width, height, stride,
                               allow_refined_portal, &angle_deg) : 0;
            TRACE("candidate %s n=%u aspect=%.2f fill=%.2f circ=%.2f geometry=%d marker=%d\n",
                  vision_type_name(type), component.count, shape.aspect,
                  shape.fill,
                  shape.circularity, geometry_pass, marker_pass);
            if (!geometry_pass || !marker_pass) continue;
            if (type == VISION_WALL &&
                (!wall_has_contrast(&component, &shape, grid_w, grid_h) ||
                 boxes_overlap_wall(output, result_count, &component))) continue;
            if (type == VISION_PORTAL_A || type == VISION_PORTAL_B) {
                int read_index;
                int write_index = 0;
                uint32_t portal_area = component.count*VISION_SAMPLE_STEP*
                                       VISION_SAMPLE_STEP;
                /* A two-cell-thick detection clipped by the frame cannot
                 * contain a complete Mirror endpoint pair.  Once the Portal's
                 * three independent white components are proven, discard only
                 * that severe edge fragment; normal and multi-object Mirrors
                 * remain untouched. */
                for (read_index = 0; read_index < result_count; ++read_index) {
                    const VisionDetection *existing = &output[read_index];
                    int frame_clipped = existing->bbox_x <= 0 ||
                        existing->bbox_y <= 0 ||
                        existing->bbox_x+existing->bbox_w >= (int)width ||
                        existing->bbox_y+existing->bbox_h >= (int)height;
                    int two_cells_thick =
                        existing->bbox_w <= (int)(2U*VISION_SAMPLE_STEP) ||
                        existing->bbox_h <= (int)(2U*VISION_SAMPLE_STEP);
                    int tiny = existing->sampled_area*8U < portal_area;
                    if (existing->type == VISION_MIRROR && frame_clipped &&
                        two_cells_thick && tiny)
                        continue;
                    if (write_index != read_index)
                        output[write_index] = output[read_index];
                    write_index++;
                }
                result_count = write_index;
            }
            fill_detection(&output[result_count], type, &component, &shape,
                           width, height, angle_deg);
            if (type == VISION_PORTAL_A || type == VISION_PORTAL_B)
                output[result_count].confidence_percent = 100;
            result_count++;
        }
    }
    return filter_fixed_camera_detections(output, result_count, width, height);
}

int vision_detect_bgr888(const uint8_t *frame, uint32_t width, uint32_t height,
                         uint32_t stride, VisionDetection *output,
                         int output_capacity)
{
    int count = vision_detect_objects_bgr888(frame, width, height, stride,
                                             output, output_capacity);
    int target_count;
    if (count < 0 || count >= output_capacity) return count;
    target_count = green_target_detect_bgr888(frame, width, height, stride,
                                              output + count,
                                              output_capacity - count);
    if (target_count < 0) return target_count;
#ifdef VISION_PORTAL_DIAGNOSTICS
    if (portal_diagnostic_type >= 0) {
        int diagnostic_index;
        for (diagnostic_index = 0;
             diagnostic_index < count+target_count; ++diagnostic_index) {
            fprintf(stderr,
                    "PORTAL_DIAG arbitration type=%s confidence=%d area=%u "
                    "bbox=(%d,%d,%d,%d)\n",
                    vision_type_name(output[diagnostic_index].type),
                    output[diagnostic_index].confidence_percent,
                    output[diagnostic_index].sampled_area,
                    output[diagnostic_index].bbox_x,
                    output[diagnostic_index].bbox_y,
                    output[diagnostic_index].bbox_w,
                    output[diagnostic_index].bbox_h);
        }
    }
#endif
    count = sort_and_suppress(output, count + target_count);
    return filter_fixed_camera_detections(output, count, width, height);
}

const char *vision_type_name(VisionType type)
{
    static const char *names[] = {
        "MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL"
    };
    return type <= VISION_WALL ? names[type] : "UNKNOWN";
}
