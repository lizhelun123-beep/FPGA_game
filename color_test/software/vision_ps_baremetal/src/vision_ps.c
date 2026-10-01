#include "vision_ps.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#ifdef VISION_TRACE
#include <stdio.h>
#define TRACE(...) fprintf(stderr, __VA_ARGS__)
#else
#define TRACE(...) do { } while (0)
#endif

#define GRID_MAX_W 320
#define GRID_MAX_H 180
#define GRID_MAX_PIXELS (GRID_MAX_W * GRID_MAX_H)
#define FRAME_MAX_W (GRID_MAX_W * VISION_SAMPLE_STEP)
#define FRAME_MAX_H (GRID_MAX_H * VISION_SAMPLE_STEP)
#define FRAME_MAX_PIXELS (FRAME_MAX_W * FRAME_MAX_H)

#define BIT_YELLOW  VISION_MASK_YELLOW
#define BIT_BLUE    VISION_MASK_BLUE
#define BIT_ORANGE  VISION_MASK_ORANGE
#define BIT_GREEN   VISION_MASK_GREEN
#define BIT_MAGENTA VISION_MASK_MAGENTA
#define BIT_BLACK   VISION_MASK_BLACK
#define BIT_WHITE   VISION_MASK_WHITE
#define BIT_WALL    VISION_MASK_WALL

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
    uint32_t inner_total;
    uint32_t annulus_total;
    uint32_t white_inner;
    uint32_t white_annulus;
    uint32_t black_inner;
    uint32_t body_inner;
} MarkerSample;

static uint8_t pixel_masks[GRID_MAX_PIXELS];
static uint8_t pixel_v[GRID_MAX_PIXELS];
static uint8_t visited[GRID_MAX_PIXELS];
static uint8_t full_masks[FRAME_MAX_PIXELS];
static uint8_t morphology_scratch[FRAME_MAX_PIXELS];
static uint32_t queue_storage[GRID_MAX_PIXELS];

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
    if (in_range(h, VISION_BLUE_H_MIN, VISION_BLUE_H_MAX) &&
        s >= VISION_BLUE_S_MIN && v >= VISION_BLUE_V_MIN) mask |= BIT_BLUE;
    if (in_range(h, VISION_ORANGE_H_MIN, VISION_ORANGE_H_MAX) &&
        s >= VISION_ORANGE_S_MIN && v >= VISION_ORANGE_V_MIN) mask |= BIT_ORANGE;
    if (in_range(h, VISION_GREEN_H_MIN, VISION_GREEN_H_MAX) &&
        s >= VISION_GREEN_S_MIN && v >= VISION_GREEN_V_MIN) mask |= BIT_GREEN;
    if ((h >= VISION_MAGENTA_H_MIN || h <= VISION_MAGENTA_H_WRAP_MAX) &&
        s >= VISION_MAGENTA_S_MIN && v >= VISION_MAGENTA_V_MIN) mask |= BIT_MAGENTA;
    if (v <= VISION_BLACK_V_MAX) mask |= BIT_BLACK;
    if (s <= VISION_WHITE_S_MAX && v >= VISION_WHITE_V_MIN) mask |= BIT_WHITE;
    if (s <= VISION_WALL_S_MAX && v <= VISION_WALL_V_MAX) mask |= BIT_WALL;
    return mask;
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

static void create_masks(const uint8_t *frame, uint32_t width, uint32_t height,
                         uint32_t stride, uint32_t grid_w, uint32_t grid_h)
{
    uint32_t y;
    for (y = 0; y < height; ++y) {
        uint32_t x;
        for (x = 0; x < width; ++x) {
            const uint8_t *pixel = frame + y * stride + x * 3U;
            uint8_t h, s, v;
            vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
            full_masks[y * width + x] = vision_classify_hsv_pixel(h, s, v);
        }
    }
    morphology_open_close(full_masks, morphology_scratch, width, height);
    for (y = 0; y < grid_h; ++y) {
        uint32_t x;
        uint32_t source_y = y * VISION_SAMPLE_STEP + 1U;
        for (x = 0; x < grid_w; ++x) {
            uint32_t source_x = x * VISION_SAMPLE_STEP + 1U;
            const uint8_t *pixel = frame + source_y * stride + source_x * 3U;
            uint8_t b = pixel[0];
            uint8_t g = pixel[1];
            uint8_t r = pixel[2];
            uint8_t v = r > g ? r : g;
            uint32_t index = y * grid_w + x;
            if (b > v) v = b;
            pixel_masks[index] = full_masks[source_y * width + source_x];
            pixel_v[index] = v;
        }
    }
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
    uint32_t box_area;
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
    box_area = (component->max_x-component->min_x+1U) *
               (component->max_y-component->min_y+1U);
    shape->fill = (float)component->count / (float)box_area;
    shape->circularity = component->perimeter ?
        (4.0f * PI_F * count) / ((float)component->perimeter * component->perimeter) : 0.0f;
    return 1;
}

static float fraction(uint32_t numerator, uint32_t denominator)
{
    return denominator ? (float)numerator / (float)denominator : 0.0f;
}

static void sample_marker(float cx, float cy, float radius, uint8_t body_bit,
                          uint32_t grid_w, uint32_t grid_h, MarkerSample *sample)
{
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
        if (y < 0 || y >= (int)grid_h) continue;
        for (x = x0; x <= x1; ++x) {
            float dx;
            float dy;
            float distance_sq;
            uint8_t bits;
            if (x < 0 || x >= (int)grid_w) continue;
            dx = (float)x - cx;
            dy = (float)y - cy;
            distance_sq = dx*dx + dy*dy;
            if (distance_sq > outer_sq) continue;
            bits = pixel_masks[(uint32_t)y*grid_w+(uint32_t)x];
            if (distance_sq <= inner_sq) {
                sample->inner_total++;
                if (bits & BIT_WHITE) sample->white_inner++;
                if (bits & BIT_BLACK) sample->black_inner++;
                if (bits & body_bit) sample->body_inner++;
            } else if (distance_sq >= outer_sq * 0.36f) {
                sample->annulus_total++;
                if (bits & BIT_WHITE) sample->white_annulus++;
            }
        }
    }
}

static void endpoint_samples(const Shape *shape, uint8_t body_bit,
                             uint32_t grid_w, uint32_t grid_h,
                             MarkerSample *first, MarkerSample *second)
{
    float offset = shape->major * VISION_ENDPOINT_OFFSET;
    float radius = shape->minor * VISION_MARKER_RADIUS;
    if (radius < 2.0f) radius = 2.0f;
    sample_marker(shape->cx-shape->ux*offset, shape->cy-shape->uy*offset,
                  radius, body_bit, grid_w, grid_h, first);
    sample_marker(shape->cx+shape->ux*offset, shape->cy+shape->uy*offset,
                  radius, body_bit, grid_w, grid_h, second);
}

static int is_white_solid(const MarkerSample *sample)
{
    return fraction(sample->white_inner, sample->inner_total) >= VISION_WHITE_SOLID_MIN;
}

static int is_white_ring(const MarkerSample *sample)
{
    return fraction(sample->white_annulus, sample->annulus_total) >= VISION_WHITE_RING_MIN &&
           fraction(sample->body_inner, sample->inner_total) >= VISION_RING_BODY_CENTER_MIN;
}

static int verify_markers(VisionType type, uint8_t body_bit, const Shape *shape,
                          uint32_t grid_w, uint32_t grid_h, int *angle_deg)
{
    MarkerSample first;
    MarkerSample second;
    if (type == VISION_SOURCE || type == VISION_WALL) return 1;
    if (type == VISION_TARGET) {
        float radius = shape->minor * VISION_MARKER_RADIUS;
        if (radius < 2.0f) radius = 2.0f;
        sample_marker(shape->cx, shape->cy, radius, body_bit, grid_w, grid_h, &first);
        TRACE("target marker white_annulus=%.2f black_inner=%.2f\n",
              fraction(first.white_annulus, first.annulus_total),
              fraction(first.black_inner, first.inner_total));
        return fraction(first.white_annulus, first.annulus_total) >= VISION_TARGET_WHITE_RING_MIN &&
               fraction(first.black_inner, first.inner_total) >= VISION_TARGET_BLACK_CENTER_MIN;
    }
    endpoint_samples(shape, body_bit, grid_w, grid_h, &first, &second);
    TRACE("%s ends solid=%.2f/%.2f ring_white=%.2f/%.2f ring_body=%.2f/%.2f black=%.2f/%.2f\n",
          vision_type_name(type),
          fraction(first.white_inner, first.inner_total),
          fraction(second.white_inner, second.inner_total),
          fraction(first.white_annulus, first.annulus_total),
          fraction(second.white_annulus, second.annulus_total),
          fraction(first.body_inner, first.inner_total),
          fraction(second.body_inner, second.inner_total),
          fraction(first.black_inner, first.inner_total),
          fraction(second.black_inner, second.inner_total));
    if (type == VISION_MIRROR) {
        return fraction(first.black_inner, first.inner_total) >= VISION_BLACK_DISK_MIN &&
               fraction(second.black_inner, second.inner_total) >= VISION_BLACK_DISK_MIN;
    }
    if (is_white_solid(&first) && is_white_ring(&second)) {
        *angle_deg = shape->angle_deg;
        return 1;
    }
    if (is_white_ring(&first) && is_white_solid(&second)) {
        *angle_deg = shape->angle_deg >= 0 ?
            shape->angle_deg - 180 : shape->angle_deg + 180;
        return 1;
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
               shape->fill >= VISION_SOURCE_FILL_MIN;
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
        if (detections[i].type == VISION_WALL) continue;
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
    detection->type = type;
    detection->center_x = (int)lroundf(shape->cx*VISION_SAMPLE_STEP + 1.5f);
    detection->center_y = (int)lroundf(shape->cy*VISION_SAMPLE_STEP + 1.5f);
    detection->bbox_x = (int)(component->min_x * VISION_SAMPLE_STEP);
    detection->bbox_y = (int)(component->min_y * VISION_SAMPLE_STEP);
    if (x1 > width) x1 = width;
    if (y1 > height) y1 = height;
    detection->bbox_w = (int)x1 - detection->bbox_x;
    detection->bbox_h = (int)y1 - detection->bbox_y;
    detection->angle_deg = type == VISION_TARGET ? 0 : angle_deg;
    detection->confidence_percent =
        type == VISION_WALL ? 75 : (type == VISION_SOURCE ? 80 : (type == VISION_TARGET ? 96 : 99));
    detection->sampled_area = component->count;
}

int vision_detect_bgr888(const uint8_t *frame, uint32_t width, uint32_t height,
                         uint32_t stride, VisionDetection *output,
                         int output_capacity)
{
    static const uint8_t body_bits[6] = {
        BIT_YELLOW, BIT_BLUE, BIT_ORANGE, BIT_GREEN, BIT_MAGENTA, BIT_WALL
    };
    static const VisionType body_types[6] = {
        VISION_MIRROR, VISION_PORTAL_A, VISION_PORTAL_B,
        VISION_TARGET, VISION_SOURCE, VISION_WALL
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
        width > FRAME_MAX_W || height > FRAME_MAX_H) return -2;
    create_masks(frame, width, height, stride, grid_w, grid_h);
    for (body_index = 0; body_index < 6 && result_count < output_capacity; ++body_index) {
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
            if (visited[seed] || !(pixel_masks[seed] & bit)) continue;
            collect_component(seed, bit, grid_w, grid_h, &component);
            if (component.count < VISION_MIN_COMPONENT_SAMPLES ||
                component.count * VISION_SAMPLE_STEP * VISION_SAMPLE_STEP >
                    width * height * VISION_MAX_FRAME_FRACTION_PERCENT / 100U ||
                !describe_component(&component, &shape)) continue;
            angle_deg = shape.angle_deg;
            geometry_pass = geometry_ok(type, &shape);
            marker_pass = geometry_pass ?
                verify_markers(type, bit, &shape, grid_w, grid_h, &angle_deg) : 0;
            TRACE("candidate %s n=%u aspect=%.2f fill=%.2f circ=%.2f geometry=%d marker=%d\n",
                  vision_type_name(type), component.count, shape.aspect,
                  shape.fill, shape.circularity, geometry_pass, marker_pass);
            if (!geometry_pass || !marker_pass) continue;
            if (type == VISION_WALL &&
                (!wall_has_contrast(&component, &shape, grid_w, grid_h) ||
                 boxes_overlap_wall(output, result_count, &component))) continue;
            fill_detection(&output[result_count++], type, &component, &shape,
                           width, height, angle_deg);
        }
    }
    return result_count;
}

const char *vision_type_name(VisionType type)
{
    static const char *names[] = {
        "MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL"
    };
    return type <= VISION_WALL ? names[type] : "UNKNOWN";
}
