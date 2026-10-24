#include "vision_ps.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int number(const char *text)
{
    return (int)strtol(text, NULL, 10);
}

int main(int argc, char **argv)
{
    if (argc == 5 && strcmp(argv[1], "pixel") == 0) {
        uint8_t h, s, v;
        vision_bgr_to_hsv_pixel((uint8_t)number(argv[2]),
                                (uint8_t)number(argv[3]),
                                (uint8_t)number(argv[4]), &h, &s, &v);
        printf("%u %u %u\n", h, s, v);
        return 0;
    }
    if (argc == 5 && strcmp(argv[1], "hsv") == 0) {
        printf("%u\n", vision_classify_hsv_pixel((uint8_t)number(argv[2]),
                                                  (uint8_t)number(argv[3]),
                                                  (uint8_t)number(argv[4])));
        return 0;
    }
    if (argc == 6 && strcmp(argv[1], "detect") == 0) {
        uint32_t width = (uint32_t)number(argv[2]);
        uint32_t height = (uint32_t)number(argv[3]);
        uint32_t stride = (uint32_t)number(argv[4]);
        size_t bytes = (size_t)height * stride;
        VisionDetection detections[VISION_MAX_DETECTIONS];
        uint8_t *frame = (uint8_t *)malloc(bytes);
        FILE *stream = fopen(argv[5], "rb");
        int count;
        int i;
        if (!frame || !stream || fread(frame, 1, bytes, stream) != bytes) {
            if (stream) fclose(stream);
            free(frame);
            return 2;
        }
        fclose(stream);
        count = vision_detect_bgr888(frame, width, height, stride,
                                     detections, VISION_MAX_DETECTIONS);
        free(frame);
        printf("%d\n", count);
        for (i = 0; i < count; ++i) {
            const VisionDetection *d = &detections[i];
            printf("%s %d %d %d %d %d %d %d %u %d %.6f %.6f %d %d\n",
                   vision_type_name(d->type), d->center_x, d->center_y,
                   d->bbox_x, d->bbox_y, d->bbox_w, d->bbox_h,
                   d->angle_deg, d->sampled_area, d->direction_valid,
                   d->source_direction_x, d->source_direction_y,
                   d->source_tip_x, d->source_tip_y);
        }
        return count < 0 ? 3 : 0;
    }
    fprintf(stderr, "usage: vision_probe pixel B G R | hsv H S V | detect W H STRIDE RAW\n");
    return 2;
}
