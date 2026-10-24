#include "green_target_detector.h"

#include <stddef.h>
#include <string.h>

#include "vision_ps_config.h"

#define GREEN_GRID_MAX_W (1280U / VISION_SAMPLE_STEP)
#define GREEN_GRID_MAX_H (720U / VISION_SAMPLE_STEP)
#define GREEN_GRID_MAX_PIXELS (GREEN_GRID_MAX_W * GREEN_GRID_MAX_H)

typedef struct {
    uint32_t count;
    uint32_t min_x;
    uint32_t min_y;
    uint32_t max_x;
    uint32_t max_y;
    uint64_t sum_x;
    uint64_t sum_y;
} GreenComponent;

static uint8_t green_mask[GREEN_GRID_MAX_PIXELS];
static uint8_t morphology_scratch[GREEN_GRID_MAX_PIXELS];
static uint8_t visited[GREEN_GRID_MAX_PIXELS];
static uint32_t component_queue[GREEN_GRID_MAX_PIXELS];

static int is_green(uint8_t h, uint8_t s, uint8_t v)
{
    return h >= VISION_GREEN_TARGET_H_MIN && h <= VISION_GREEN_TARGET_H_MAX &&
           s >= VISION_GREEN_TARGET_S_MIN && v >= VISION_GREEN_TARGET_V_MIN;
}

static void erode_cross(const uint8_t *source, uint8_t *destination,
                        uint32_t width, uint32_t height)
{
    uint32_t y;
    for (y = 0; y < height; ++y) {
        uint32_t x;
        for (x = 0; x < width; ++x) {
            uint32_t index = y * width + x;
            uint8_t value = source[index];
            if (x) value &= source[index - 1U];
            if (x + 1U < width) value &= source[index + 1U];
            if (y) value &= source[index - width];
            if (y + 1U < height) value &= source[index + width];
            destination[index] = value;
        }
    }
}

static void dilate_cross(const uint8_t *source, uint8_t *destination,
                         uint32_t width, uint32_t height)
{
    uint32_t y;
    for (y = 0; y < height; ++y) {
        uint32_t x;
        for (x = 0; x < width; ++x) {
            uint32_t index = y * width + x;
            uint8_t value = source[index];
            if (x) value |= source[index - 1U];
            if (x + 1U < width) value |= source[index + 1U];
            if (y) value |= source[index - width];
            if (y + 1U < height) value |= source[index + width];
            destination[index] = value;
        }
    }
}

static void open_close(uint32_t width, uint32_t height)
{
    erode_cross(green_mask, morphology_scratch, width, height);
    dilate_cross(morphology_scratch, green_mask, width, height);
    dilate_cross(green_mask, morphology_scratch, width, height);
    erode_cross(morphology_scratch, green_mask, width, height);
}

static void component_reset(GreenComponent *component, uint32_t x, uint32_t y)
{
    memset(component, 0, sizeof(*component));
    component->min_x = component->max_x = x;
    component->min_y = component->max_y = y;
}

static void component_add(GreenComponent *component, uint32_t x, uint32_t y)
{
    ++component->count;
    if (x < component->min_x) component->min_x = x;
    if (x > component->max_x) component->max_x = x;
    if (y < component->min_y) component->min_y = y;
    if (y > component->max_y) component->max_y = y;
    component->sum_x += x;
    component->sum_y += y;
}

static void collect_component(uint32_t seed, uint32_t grid_w, uint32_t grid_h,
                              GreenComponent *component)
{
    static const int8_t neighbor_x[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    static const int8_t neighbor_y[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t seed_x = seed % grid_w;
    uint32_t seed_y = seed / grid_w;

    component_reset(component, seed_x, seed_y);
    visited[seed] = 1U;
    component_queue[tail++] = seed;
    while (head < tail) {
        uint32_t index = component_queue[head++];
        uint32_t x = index % grid_w;
        uint32_t y = index / grid_w;
        int direction;
        component_add(component, x, y);
        for (direction = 0; direction < 8; ++direction) {
            int xx = (int)x + neighbor_x[direction];
            int yy = (int)y + neighbor_y[direction];
            uint32_t neighbor;
            if (xx < 0 || yy < 0 || xx >= (int)grid_w || yy >= (int)grid_h)
                continue;
            neighbor = (uint32_t)yy * grid_w + (uint32_t)xx;
            if (!visited[neighbor] && green_mask[neighbor]) {
                visited[neighbor] = 1U;
                component_queue[tail++] = neighbor;
            }
        }
    }
}

static unsigned ellipse_coverage_percent(const GreenComponent *component,
                                         uint32_t grid_w)
{
    uint64_t bbox_w = component->max_x - component->min_x + 1U;
    uint64_t bbox_h = component->max_y - component->min_y + 1U;
    uint64_t limit = bbox_w * bbox_w * bbox_h * bbox_h;
    uint32_t inside = 0;
    uint32_t i;

    for (i = 0; i < component->count; ++i) {
        uint32_t index = component_queue[i];
        int64_t x = (int64_t)(index % grid_w);
        int64_t y = (int64_t)(index / grid_w);
        int64_t dx = 2 * x - (int64_t)(component->min_x + component->max_x);
        int64_t dy = 2 * y - (int64_t)(component->min_y + component->max_y);
        uint64_t ellipse = (uint64_t)(dx * dx) * bbox_h * bbox_h +
                           (uint64_t)(dy * dy) * bbox_w * bbox_w;
        if (ellipse <= limit) ++inside;
    }
    return component->count ? inside * 100U / component->count : 0U;
}

static int component_is_target(const GreenComponent *component,
                               uint32_t grid_w, uint32_t width,
                               uint32_t height, unsigned *confidence)
{
    uint32_t bbox_w = component->max_x - component->min_x + 1U;
    uint32_t bbox_h = component->max_y - component->min_y + 1U;
    uint32_t long_side = bbox_w > bbox_h ? bbox_w : bbox_h;
    uint32_t short_side = bbox_w > bbox_h ? bbox_h : bbox_w;
    uint32_t bbox_area = bbox_w * bbox_h;
    uint32_t estimated_area = component->count * VISION_SAMPLE_STEP *
                              VISION_SAMPLE_STEP;
    uint32_t frame_area = width * height;
    uint32_t minimum_area = frame_area * VISION_GREEN_TARGET_MIN_AREA_PPM /
                            1000000U;
    uint32_t maximum_area = frame_area * VISION_GREEN_TARGET_MAX_AREA_PERCENT /
                            100U;
    unsigned ellipse_percent;
    unsigned aspect_percent;
    unsigned aspect_score;
    unsigned result;

    if (minimum_area < VISION_GREEN_TARGET_MIN_AREA_PIXELS)
        minimum_area = VISION_GREEN_TARGET_MIN_AREA_PIXELS;
    if (estimated_area < minimum_area || estimated_area > maximum_area ||
        !short_side || long_side * 100U >
            short_side * VISION_GREEN_TARGET_MAX_ASPECT_PERCENT)
        return 0;
    if (component->count * 100U <
            bbox_area * VISION_GREEN_TARGET_MIN_FILL_PERCENT ||
        component->count * 100U >
            bbox_area * VISION_GREEN_TARGET_MAX_FILL_PERCENT)
        return 0;

    ellipse_percent = ellipse_coverage_percent(component, grid_w);
    if (ellipse_percent < VISION_GREEN_TARGET_MIN_ELLIPSE_PERCENT) return 0;

    aspect_percent = long_side * 100U / short_side;
    aspect_score = (VISION_GREEN_TARGET_MAX_ASPECT_PERCENT - aspect_percent) *
                   100U / (VISION_GREEN_TARGET_MAX_ASPECT_PERCENT - 100U);
    result = 50U + aspect_score * 25U / 100U + ellipse_percent * 25U / 100U;
    *confidence = result > 99U ? 99U : result;
    return 1;
}

static void fill_detection(VisionDetection *detection,
                           const GreenComponent *component,
                           uint32_t width, uint32_t height,
                           unsigned confidence)
{
    uint32_t x1 = (component->max_x + 1U) * VISION_SAMPLE_STEP;
    uint32_t y1 = (component->max_y + 1U) * VISION_SAMPLE_STEP;
    memset(detection, 0, sizeof(*detection));
    detection->type = VISION_TARGET;
    detection->center_x = (int)((component->sum_x * VISION_SAMPLE_STEP +
                                 component->count / 2U) / component->count + 1U);
    detection->center_y = (int)((component->sum_y * VISION_SAMPLE_STEP +
                                 component->count / 2U) / component->count + 1U);
    detection->geometry_center_x = (float)detection->center_x;
    detection->geometry_center_y = (float)detection->center_y;
    detection->bbox_x = (int)(component->min_x * VISION_SAMPLE_STEP);
    detection->bbox_y = (int)(component->min_y * VISION_SAMPLE_STEP);
    if (x1 > width) x1 = width;
    if (y1 > height) y1 = height;
    detection->bbox_w = (int)x1 - detection->bbox_x;
    detection->bbox_h = (int)y1 - detection->bbox_y;
    detection->angle_deg = 0;
    detection->confidence_percent = (int)confidence;
    detection->sampled_area = component->count * VISION_SAMPLE_STEP *
                              VISION_SAMPLE_STEP;
    if (detection->bbox_w >= detection->bbox_h) {
        detection->axis_x = 1.0f;
        detection->major_length = (float)detection->bbox_w;
        detection->minor_width = (float)detection->bbox_h;
    } else {
        detection->axis_y = 1.0f;
        detection->angle_deg = 90;
        detection->major_length = (float)detection->bbox_h;
        detection->minor_width = (float)detection->bbox_w;
    }
}

static void insert_detection(VisionDetection *output, int *count, int capacity,
                             const VisionDetection *candidate)
{
    int position = 0;
    int index;
    while (position < *count &&
           output[position].sampled_area >= candidate->sampled_area)
        ++position;
    if (position >= capacity) return;
    if (*count < capacity) ++*count;
    for (index = *count - 1; index > position; --index)
        output[index] = output[index - 1];
    output[position] = *candidate;
}

int green_target_detect_bgr888(const uint8_t *frame, uint32_t width,
                               uint32_t height, uint32_t stride,
                               VisionDetection *output, int output_capacity)
{
    uint32_t grid_w;
    uint32_t grid_h;
    uint32_t grid_pixels;
    uint32_t y;
    int result_count = 0;

    if (!frame || !output || output_capacity <= 0 ||
        width < VISION_SAMPLE_STEP || height < VISION_SAMPLE_STEP ||
        stride < width * 3U)
        return -1;
    grid_w = width / VISION_SAMPLE_STEP;
    grid_h = height / VISION_SAMPLE_STEP;
    if (grid_w > GREEN_GRID_MAX_W || grid_h > GREEN_GRID_MAX_H) return -2;
    grid_pixels = grid_w * grid_h;
    memset(green_mask, 0, grid_pixels);
    memset(visited, 0, grid_pixels);

    for (y = 0; y < grid_h; ++y) {
        uint32_t source_y = y * VISION_SAMPLE_STEP + 1U;
        uint32_t x;
        for (x = 0; x < grid_w; ++x) {
            uint32_t source_x = x * VISION_SAMPLE_STEP + 1U;
            const uint8_t *pixel = frame + source_y * stride + source_x * 3U;
            uint8_t h;
            uint8_t s;
            uint8_t v;
            vision_bgr_to_hsv_pixel(pixel[0], pixel[1], pixel[2], &h, &s, &v);
            green_mask[y * grid_w + x] = (uint8_t)is_green(h, s, v);
        }
    }
    open_close(grid_w, grid_h);

    for (y = 0; y < grid_pixels; ++y) {
        GreenComponent component;
        VisionDetection detection;
        unsigned confidence;
        if (visited[y] || !green_mask[y]) continue;
        collect_component(y, grid_w, grid_h, &component);
        if (!component_is_target(&component, grid_w, width, height, &confidence))
            continue;
        fill_detection(&detection, &component, width, height, confidence);
        insert_detection(output, &result_count, output_capacity, &detection);
    }
    return result_count;
}
