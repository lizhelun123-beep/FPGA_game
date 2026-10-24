#include "vision_ps.h"
#include "vision_overlay.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define WIDTH 1280
#define HEIGHT 720
#define STRIDE (1920 * 3)

static uint8_t frame[HEIGHT * STRIDE];

static void pixel(int x, int y, uint8_t b, uint8_t g, uint8_t r)
{
    uint8_t *p;
    if (x < 0 || x >= WIDTH || y < 0 || y >= HEIGHT) return;
    p = frame + y * STRIDE + x * 3;
    p[0] = b;
    p[1] = g;
    p[2] = r;
}

static void clear(uint8_t b, uint8_t g, uint8_t r)
{
    int y;
    for (y = 0; y < HEIGHT; ++y) {
        int x;
        for (x = 0; x < WIDTH; ++x) pixel(x, y, b, g, r);
    }
}

static void rectangle(int x0, int y0, int x1, int y1,
                      uint8_t b, uint8_t g, uint8_t r)
{
    int y;
    for (y = y0; y <= y1; ++y) {
        int x;
        for (x = x0; x <= x1; ++x) pixel(x, y, b, g, r);
    }
}

static void circle(int cx, int cy, int radius, uint8_t b, uint8_t g, uint8_t r)
{
    int y;
    for (y = cy-radius; y <= cy+radius; ++y) {
        int x;
        for (x = cx-radius; x <= cx+radius; ++x) {
            int dx = x-cx;
            int dy = y-cy;
            if (dx*dx+dy*dy <= radius*radius) pixel(x, y, b, g, r);
        }
    }
}

static int edge(int ax, int ay, int bx, int by, int x, int y)
{
    return (x-ax)*(by-ay) - (y-ay)*(bx-ax);
}

static void triangle(int ax, int ay, int bx, int by, int cx, int cy,
                     uint8_t b, uint8_t g, uint8_t r)
{
    int min_x = ax < bx ? (ax < cx ? ax : cx) : (bx < cx ? bx : cx);
    int max_x = ax > bx ? (ax > cx ? ax : cx) : (bx > cx ? bx : cx);
    int min_y = ay < by ? (ay < cy ? ay : cy) : (by < cy ? by : cy);
    int max_y = ay > by ? (ay > cy ? ay : cy) : (by > cy ? by : cy);
    int y;
    for (y = min_y; y <= max_y; ++y) {
        int x;
        for (x = min_x; x <= max_x; ++x) {
            int e0 = edge(ax, ay, bx, by, x, y);
            int e1 = edge(bx, by, cx, cy, x, y);
            int e2 = edge(cx, cy, ax, ay, x, y);
            if ((e0 >= 0 && e1 >= 0 && e2 >= 0) ||
                (e0 <= 0 && e1 <= 0 && e2 <= 0)) pixel(x, y, b, g, r);
        }
    }
}

static void source_triangle_layer(int cx, int cy, float length,
                                  float half_base, int angle_deg,
                                  uint8_t b, uint8_t g, uint8_t r)
{
    float angle = (float)angle_deg * 3.14159265358979323846f / 180.0f;
    float ux = cosf(angle);
    float uy = sinf(angle);
    float nx = -uy;
    float ny = ux;
    float tip_x = (float)cx + ux*length*0.5f;
    float tip_y = (float)cy + uy*length*0.5f;
    float base_x = (float)cx - ux*length*0.5f;
    float base_y = (float)cy - uy*length*0.5f;
    triangle((int)lroundf(tip_x), (int)lroundf(tip_y),
             (int)lroundf(base_x+nx*half_base),
             (int)lroundf(base_y+ny*half_base),
             (int)lroundf(base_x-nx*half_base),
             (int)lroundf(base_y-ny*half_base), b, g, r);
}

static void rotated_source_marker(int cx, int cy, int length, int angle_deg,
                                  int include_white_band)
{
    float angle = (float)angle_deg * 3.14159265358979323846f / 180.0f;
    float ux = cosf(angle);
    float uy = sinf(angle);
    float nx = -uy;
    float ny = ux;
    float body_length = (float)length;
    float half_base = body_length*0.43f;
    float base_x = (float)cx-ux*body_length*0.5f;
    float base_y = (float)cy-uy*body_length*0.5f;
    float inner_x = base_x+ux*body_length*0.30f;
    float inner_y = base_y+uy*body_length*0.30f;
    float inner_half_base = half_base*0.70f;
    source_triangle_layer(cx, cy, body_length+24.0f, half_base+12.0f,
                          angle_deg, 30, 30, 30);
    source_triangle_layer(cx, cy, body_length, half_base, angle_deg,
                          40, 74, 118);
    if (include_white_band) {
        int base_left_x = (int)lroundf(base_x+nx*half_base);
        int base_left_y = (int)lroundf(base_y+ny*half_base);
        int base_right_x = (int)lroundf(base_x-nx*half_base);
        int base_right_y = (int)lroundf(base_y-ny*half_base);
        int inner_left_x = (int)lroundf(inner_x+nx*inner_half_base);
        int inner_left_y = (int)lroundf(inner_y+ny*inner_half_base);
        int inner_right_x = (int)lroundf(inner_x-nx*inner_half_base);
        int inner_right_y = (int)lroundf(inner_y-ny*inner_half_base);
        triangle(base_left_x, base_left_y, base_right_x, base_right_y,
                 inner_right_x, inner_right_y, 235, 235, 235);
        triangle(base_left_x, base_left_y, inner_right_x, inner_right_y,
                 inner_left_x, inner_left_y, 235, 235, 235);
    }
}

static void capsule(int x0, int y0, int x1, int y1,
                    uint8_t b, uint8_t g, uint8_t r)
{
    int radius = (y1-y0)/2;
    rectangle(x0+radius, y0, x1-radius, y1, b, g, r);
    circle(x0+radius, y0+radius, radius, b, g, r);
    circle(x1-radius, y0+radius, radius, b, g, r);
}

static void rotated_capsule(int cx, int cy, int length, int height,
                            int angle_deg, uint8_t b, uint8_t g, uint8_t r)
{
    float angle = (float)angle_deg * 3.14159265358979323846f / 180.0f;
    float ux = cosf(angle);
    float uy = sinf(angle);
    float radius = (float)height / 2.0f;
    float half_straight = (float)length / 2.0f - radius;
    int extent = length / 2 + height;
    int y;
    for (y = cy - extent; y <= cy + extent; ++y) {
        int x;
        for (x = cx - extent; x <= cx + extent; ++x) {
            float dx = (float)(x - cx);
            float dy = (float)(y - cy);
            float longitudinal = dx * ux + dy * uy;
            float transverse = -dx * uy + dy * ux;
            float end_distance;
            if (longitudinal < -half_straight)
                end_distance = longitudinal + half_straight;
            else if (longitudinal > half_straight)
                end_distance = longitudinal - half_straight;
            else
                end_distance = 0.0f;
            if (end_distance * end_distance + transverse * transverse <=
                radius * radius)
                pixel(x, y, b, g, r);
        }
    }
}

static void rotated_rectangle(int cx, int cy, int length, int height,
                              int angle_deg, uint8_t b, uint8_t g, uint8_t r)
{
    float angle = (float)angle_deg * 3.14159265358979323846f / 180.0f;
    float ux = cosf(angle);
    float uy = sinf(angle);
    float half_length = (float)length / 2.0f;
    float half_height = (float)height / 2.0f;
    int extent = length / 2 + height;
    int y;
    for (y = cy - extent; y <= cy + extent; ++y) {
        int x;
        for (x = cx - extent; x <= cx + extent; ++x) {
            float dx = (float)(x-cx);
            float dy = (float)(y-cy);
            float longitudinal = dx*ux + dy*uy;
            float transverse = -dx*uy + dy*ux;
            if (fabsf(longitudinal) <= half_length &&
                fabsf(transverse) <= half_height)
                pixel(x, y, b, g, r);
        }
    }
}

static int has_type(const VisionDetection *detections, int count, VisionType type)
{
    int i;
    for (i = 0; i < count; ++i) if (detections[i].type == type) return 1;
    return 0;
}

static int count_type(const VisionDetection *detections, int count,
                      VisionType type)
{
    int matches = 0;
    int i;
    for (i = 0; i < count; ++i)
        if (detections[i].type == type) matches++;
    return matches;
}

static const VisionDetection *find_type(const VisionDetection *detections,
                                        int count, VisionType type)
{
    int i;
    for (i = 0; i < count; ++i)
        if (detections[i].type == type) return &detections[i];
    return NULL;
}

static int angle_distance(int first, int second)
{
    int difference = first - second;
    while (difference > 180) difference -= 360;
    while (difference < -180) difference += 360;
    return difference < 0 ? -difference : difference;
}

static int axis_angle_distance(int first, int second)
{
    int difference = angle_distance(first, second);
    return difference > 90 ? 180-difference : difference;
}

static void make_six_objects(void)
{
    clear(156, 151, 146);
    rectangle(40, 50, 300, 110, 0, 230, 240);
    circle(80, 80, 11, 30, 30, 30);
    circle(260, 80, 11, 30, 30, 30);

    capsule(360, 50, 580, 110, 230, 90, 20);
    circle(395, 80, 12, 235, 235, 235);
    circle(545, 80, 15, 235, 235, 235);
    circle(545, 80, 8, 230, 90, 20);

    capsule(650, 50, 870, 110, 0, 135, 255);
    circle(685, 80, 12, 235, 235, 235);
    circle(835, 80, 15, 235, 235, 235);
    circle(835, 80, 8, 0, 135, 255);

    circle(150, 290, 55, 45, 190, 40);
    circle(150, 290, 24, 235, 235, 235);
    circle(150, 290, 15, 45, 190, 40);
    circle(150, 290, 9, 25, 25, 25);

    rotated_source_marker(430, 290, 140, 0, 1);
    rectangle(650, 255, 950, 325, 35, 35, 35);
    rectangle(712, 262, 728, 318, 245, 245, 245);
    rectangle(862, 262, 878, 318, 245, 245, 245);
}

int main(void)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    VisionMinimalProbe probe;
    int count;
    int type;

    clear(10, 20, 30);
    rectangle(10, 20, 19, 29, 45, 190, 40);
    if (vision_minimal_probe_bgr888(frame, WIDTH, HEIGHT, STRIDE, &probe) != 0 ||
        probe.green_pixels != 100 || probe.green_bbox_x != 10 ||
        probe.green_bbox_y != 20 || probe.green_bbox_w != 10 ||
        probe.green_bbox_h != 10 || probe.green_center_x != 14 ||
        probe.green_center_y != 24 || probe.minimum[0] != 10 ||
        probe.maximum[1] != 190 || probe.mean[2] != 30) {
        fprintf(stderr, "minimal BGR/green probe mismatch\n");
        return 1;
    }
    if (vision_minimal_probe_bgr888(frame, WIDTH, HEIGHT, WIDTH * 3 - 1,
                                    &probe) != -1) {
        fprintf(stderr, "minimal probe accepted short stride\n");
        return 1;
    }
    make_six_objects();
    count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                 detections, VISION_MAX_DETECTIONS);
    if (count != 6) {
        fprintf(stderr, "expected six detections, got %d\n", count);
        for (type = 0; type < count; ++type)
            fprintf(stderr, "  %s\n", vision_type_name(detections[type].type));
        return 1;
    }
    for (type = VISION_MIRROR; type <= VISION_WALL; ++type) {
        if (!has_type(detections, count, (VisionType)type)) {
            fprintf(stderr, "missing %s\n", vision_type_name((VisionType)type));
            return 1;
        }
    }
    {
        const VisionDetection *source_detection =
            find_type(detections, count, VISION_SOURCE);
        if (!source_detection || !source_detection->direction_valid) {
            fprintf(stderr, "accepted SOURCE lacks a valid tip direction\n");
            return 1;
        }
    }

    /* The white band marks the covered side; emission is toward the colored
     * side. The body shape itself is deliberately not used to choose a tip. */
    {
        static const int angles[] = {0, 30, 60, 90, 135, -45};
        unsigned index;
        for (index = 0; index < sizeof(angles) / sizeof(angles[0]); ++index) {
            int angle = angles[index];
            float radians = (float)angle * 3.14159265358979323846f / 180.0f;
            const VisionDetection *source;
            clear(156, 151, 146);
            rotated_source_marker(640, 360, 140, angle, 1);
            count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                         detections, VISION_MAX_DETECTIONS);
            source = find_type(detections, count, VISION_SOURCE);
            if (!source || !source->direction_valid ||
                count_type(detections, count, VISION_SOURCE) != 1 ||
                source->source_direction_x*cosf(radians) +
                    source->source_direction_y*sinf(radians) < 0.94f ||
                angle_distance(source->angle_deg, angle) > 12 ||
                ((float)(source->source_tip_x-source->center_x)*cosf(radians) +
                 (float)(source->source_tip_y-source->center_y)*sinf(radians)) <=
                    0.0f) {
                fprintf(stderr,
                        "marked source angle=%d missing/wrong (%d valid=%d)\n",
                        angle, source ? source->angle_deg : 999,
                        source ? source->direction_valid : 0);
                return 1;
            }
        }

        /* A legacy unmarked body is not a SOURCE.  This is the false-positive
         * guard for hands and warm-coloured Portal bodies. */
        clear(156, 151, 146);
        rotated_source_marker(640, 360, 140, 0, 0);
        count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                     detections, VISION_MAX_DETECTIONS);
        {
            const VisionDetection *source =
                find_type(detections, count, VISION_SOURCE);
            if (source) {
                fprintf(stderr, "unmarked source was accepted\n");
                return 1;
            }
        }

        /* More than 64 valid parts above the real marker must not make a
         * lower-frame SOURCE unreachable through row-major truncation. */
        clear(80, 80, 80);
        {
            int part;
            for (part = 0; part < 70; ++part) {
                int x = 12+(part%10)*16;
                int y = 12+(part/10)*16;
                rectangle(x, y, x+7, y+7, 40, 74, 118);
                rectangle(x+300, y, x+307, y+7, 235, 235, 235);
            }
        }
        rotated_source_marker(640, 600, 140, 0, 1);
        count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                     detections, VISION_MAX_DETECTIONS);
        {
            const VisionDetection *source =
                find_type(detections, count, VISION_SOURCE);
            if (!source || source->center_y < 500 ||
                !source->direction_valid) {
                fprintf(stderr,
                        "spatially partitioned SOURCE retention failed\n");
                return 1;
            }
        }
    }

    /* Portal geometry and solid-to-ring orientation must be rotation invariant. */
    {
        static const int angles[] = {0, 30, 60, 90, 135, -45};
        unsigned index;
        for (index = 0; index < sizeof(angles) / sizeof(angles[0]); ++index) {
            int angle = angles[index];
            float radians = (float)angle * 3.14159265358979323846f / 180.0f;
            int dx = (int)lroundf(cosf(radians) * 75.0f);
            int dy = (int)lroundf(sinf(radians) * 75.0f);
            const VisionDetection *portal;
            clear(156, 151, 146);
            rotated_capsule(640, 360, 220, 60, angle, 230, 90, 20);
            circle(640 - dx, 360 - dy, 12, 235, 235, 235);
            circle(640 + dx, 360 + dy, 15, 235, 235, 235);
            circle(640 + dx, 360 + dy, 8, 230, 90, 20);
            count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                         detections, VISION_MAX_DETECTIONS);
            portal = find_type(detections, count, VISION_PORTAL_A);
            if (!portal || angle_distance(portal->angle_deg, angle) > 12) {
                fprintf(stderr, "rotated portal angle=%d missing/wrong (%d)\n",
                        angle, portal ? portal->angle_deg : 999);
                return 1;
            }
        }
    }

    /* A portal with two white disks must not pass disk+ring validation. */
    clear(156, 151, 146);
    capsule(360, 50, 580, 110, 230, 90, 20);
    circle(395, 80, 12, 235, 235, 235);
    circle(545, 80, 12, 235, 235, 235);
    count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                 detections, VISION_MAX_DETECTIONS);
    if (has_type(detections, count, VISION_PORTAL_A)) {
        fprintf(stderr, "invalid two-disk portal accepted\n");
        return 1;
    }


    /* Transverse-bar WALL pairing and its reported axis are rotation invariant. */
    {
        static const int angles[] = {0, 35, 90, 155};
        unsigned index;
        for (index = 0; index < sizeof(angles) / sizeof(angles[0]); ++index) {
            int angle = angles[index];
            float radians = (float)angle * 3.14159265358979323846f / 180.0f;
            int dx = (int)lroundf(cosf(radians)*35.0f);
            int dy = (int)lroundf(sinf(radians)*35.0f);
            const VisionDetection *wall;
            clear(156, 151, 146);
            rotated_rectangle(640, 360, 100, 32, angle, 35, 35, 35);
            rotated_rectangle(640-dx, 360-dy, 25, 9, angle+90,
                              245, 245, 245);
            rotated_rectangle(640+dx, 360+dy, 25, 9, angle+90,
                              245, 245, 245);
            count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                         detections, VISION_MAX_DETECTIONS);
            wall = find_type(detections, count, VISION_WALL);
            if (!wall || axis_angle_distance(wall->angle_deg, angle) > 12) {
                fprintf(stderr, "rotated wall angle=%d missing/wrong (%d)\n",
                        angle, wall ? wall->angle_deg : 999);
                return 1;
            }
        }
    }

    /* WALL must cover both dark and exposure-lifted halves. */
    clear(156, 151, 146);
    rectangle(100, 250, 249, 320, 35, 35, 35);
    rectangle(250, 250, 400, 320, 55, 55, 55);
    count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                 detections, VISION_MAX_DETECTIONS);
    if (!has_type(detections, count, VISION_WALL)) {
        fprintf(stderr, "brightness-gradient wall missing\n");
        return 1;
    }

    /* Ray overlay must clip at all four edges and leave stride padding intact. */
    {
        unsigned y, x;
        RaySegment edge[2] = {
            {{-10.0f, -10.0f}, {100.0f, 100.0f}},
            {{1100.0f, 540.0f}, {(float)WIDTH+20.0f, (float)HEIGHT+20.0f}}
        };
        memset(frame, 0xA5, sizeof frame);
        vision_overlay(frame, WIDTH, HEIGHT, STRIDE, edge, 2,
                       0U, 0U, 17);
        for (y = 0; y < HEIGHT; ++y)
            for (x = WIDTH*3; x < STRIDE; ++x)
                if (frame[y*STRIDE+x] != 0xA5) {
                    fprintf(stderr, "overlay wrote into row padding\n"); return 1;
                }
        if (frame[100*STRIDE+100*3+2] != 255) {
            fprintf(stderr, "ray overlay BGR line missing\n"); return 1;
        }
        vision_overlay(frame, WIDTH, HEIGHT, STRIDE, NULL, 0,
                       0U, 0U, 1);
    }
    printf("vision_ps host tests passed (including overlay clipping)\n");
    return 0;
}
