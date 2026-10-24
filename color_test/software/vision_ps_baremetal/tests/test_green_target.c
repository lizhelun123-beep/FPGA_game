#include "green_target_detector.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define WIDTH 1280
#define HEIGHT 720
#define STRIDE 5760

static uint8_t frame[HEIGHT * STRIDE];

static void pixel(int x, int y, uint8_t b, uint8_t g, uint8_t r)
{
    uint8_t *value;
    if (x < 0 || x >= WIDTH || y < 0 || y >= HEIGHT) return;
    value = frame + y * STRIDE + x * 3;
    value[0] = b;
    value[1] = g;
    value[2] = r;
}

static void clear(uint8_t b, uint8_t g, uint8_t r)
{
    int y;
    memset(frame, 0xA5, sizeof(frame));
    for (y = 0; y < HEIGHT; ++y) {
        int x;
        for (x = 0; x < WIDTH; ++x) pixel(x, y, b, g, r);
    }
}

static void circle(int cx, int cy, int outer_radius, int inner_radius,
                   uint8_t b, uint8_t g, uint8_t r)
{
    int y;
    for (y = cy - outer_radius; y <= cy + outer_radius; ++y) {
        int x;
        for (x = cx - outer_radius; x <= cx + outer_radius; ++x) {
            int dx = x - cx;
            int dy = y - cy;
            int distance = dx * dx + dy * dy;
            if (distance <= outer_radius * outer_radius &&
                distance >= inner_radius * inner_radius)
                pixel(x, y, b, g, r);
        }
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

static int near(int actual, int expected, int tolerance)
{
    int difference = actual - expected;
    if (difference < 0) difference = -difference;
    return difference <= tolerance;
}

static int expect_one_at(int expected_x, int expected_y)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count = green_target_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                            detections, VISION_MAX_DETECTIONS);
    if (count != 1 || detections[0].type != VISION_TARGET ||
        !near(detections[0].center_x, expected_x, 5) ||
        !near(detections[0].center_y, expected_y, 5)) {
        fprintf(stderr, "expected one TARGET near %d,%d; count=%d\n",
                expected_x, expected_y, count);
        return 0;
    }
    return 1;
}

int main(void)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    unsigned y;
    unsigned x;
    int count;

    /* Low-contrast green sampled from the supplied real-scene captures. */
    clear(100, 100, 100);
    circle(470, 105, 42, 0, 88, 116, 93);
    if (!expect_one_at(470, 105)) return 1;

    clear(100, 100, 100);
    circle(160, 250, 55, 35, 40, 62, 59);
    if (!expect_one_at(160, 250)) return 1;

    /* A near-square green rectangle passes aspect but must fail ellipse/fill. */
    clear(100, 100, 100);
    rectangle(80, 100, 200, 200, 88, 116, 93);
    count = green_target_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                       detections, VISION_MAX_DETECTIONS);
    if (count != 0) {
        fprintf(stderr, "green rectangle accepted\n");
        return 1;
    }

    clear(100, 100, 100);
    rectangle(20, 20, 22, 22, 88, 116, 93);
    rectangle(600, 300, 602, 302, 88, 116, 93);
    count = green_target_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                       detections, VISION_MAX_DETECTIONS);
    if (count != 0) {
        fprintf(stderr, "small green noise accepted\n");
        return 1;
    }

    clear(100, 100, 100);
    count = green_target_detect_bgr888(frame, WIDTH, HEIGHT, STRIDE,
                                       detections, VISION_MAX_DETECTIONS);
    if (count != 0) {
        fprintf(stderr, "gray background accepted\n");
        return 1;
    }
    if (green_target_detect_bgr888(frame, WIDTH, HEIGHT, WIDTH * 3 - 1,
                                   detections, VISION_MAX_DETECTIONS) != -1) {
        fprintf(stderr, "short stride accepted\n");
        return 1;
    }
    for (y = 0; y < HEIGHT; ++y)
        for (x = WIDTH * 3; x < STRIDE; ++x)
            if (frame[y * STRIDE + x] != 0xA5) {
                fprintf(stderr, "detector modified stride padding\n");
                return 1;
            }

    printf("green target host tests passed\n");
    return 0;
}

