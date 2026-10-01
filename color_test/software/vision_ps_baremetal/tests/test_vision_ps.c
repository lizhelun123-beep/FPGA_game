#include "vision_ps.h"
#include "vision_overlay.h"

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

static void capsule(int x0, int y0, int x1, int y1,
                    uint8_t b, uint8_t g, uint8_t r)
{
    int radius = (y1-y0)/2;
    rectangle(x0+radius, y0, x1-radius, y1, b, g, r);
    circle(x0+radius, y0+radius, radius, b, g, r);
    circle(x1-radius, y0+radius, radius, b, g, r);
}

static int has_type(const VisionDetection *detections, int count, VisionType type)
{
    int i;
    for (i = 0; i < count; ++i) if (detections[i].type == type) return 1;
    return 0;
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

    triangle(360, 235, 360, 345, 500, 290, 180, 30, 225);
    rectangle(650, 255, 950, 325, 65, 60, 58);
}

int main(void)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count;
    int type;
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

    /* WALL must cover both dark and exposure-lifted halves. */
    clear(156, 151, 146);
    rectangle(100, 250, 249, 320, 48, 48, 48);
    rectangle(250, 250, 400, 320, 95, 95, 95);
    count = vision_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                 detections, VISION_MAX_DETECTIONS);
    if (!has_type(detections, count, VISION_WALL)) {
        fprintf(stderr, "brightness-gradient wall missing\n");
        return 1;
    }

    /* Overlay must clip at all four edges and leave stride padding intact. */
    {
        unsigned y, x;
        VisionDetection edge[2] = {
            {VISION_SOURCE, 0, 0, -10, -10, 35, 35, 0, 80, 100},
            {VISION_WALL, WIDTH-1, HEIGHT-1, WIDTH-20, HEIGHT-20, 40, 40, 0, 75, 100}
        };
        memset(frame, 0xA5, sizeof frame);
        vision_overlay(frame, WIDTH, HEIGHT, STRIDE, edge, 2, 17);
        for (y = 0; y < HEIGHT; ++y)
            for (x = WIDTH*3; x < STRIDE; ++x)
                if (frame[y*STRIDE+x] != 0xA5) {
                    fprintf(stderr, "overlay wrote into row padding\n"); return 1;
                }
        if (frame[(HEIGHT-1)*STRIDE+(WIDTH-1)*3+2] != 255) {
            fprintf(stderr, "overlay BGR center missing\n"); return 1;
        }
        vision_overlay(frame, WIDTH, HEIGHT, STRIDE, NULL, 0, 1);
    }
    printf("vision_ps host tests passed (including overlay clipping)\n");
    return 0;
}
