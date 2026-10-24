#include "green_target_detector.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    size_t bytes;
    uint8_t *frame;
    FILE *stream;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count;
    int index;

    if (argc != 5) {
        fprintf(stderr, "usage: green_target_probe WIDTH HEIGHT STRIDE RAW\n");
        return 2;
    }
    width = (uint32_t)strtoul(argv[1], NULL, 10);
    height = (uint32_t)strtoul(argv[2], NULL, 10);
    stride = (uint32_t)strtoul(argv[3], NULL, 10);
    bytes = (size_t)height * stride;
    frame = (uint8_t *)malloc(bytes);
    stream = fopen(argv[4], "rb");
    if (!frame || !stream || fread(frame, 1, bytes, stream) != bytes) {
        if (stream) fclose(stream);
        free(frame);
        return 3;
    }
    fclose(stream);
    count = green_target_detect_bgr888(frame, width, height, stride,
                                        detections, VISION_MAX_DETECTIONS);
    free(frame);
    printf("%d\n", count);
    for (index = 0; index < count; ++index) {
        const VisionDetection *detection = &detections[index];
        printf("%d %d %d %d %d %d %u %d\n",
               detection->center_x, detection->center_y,
               detection->bbox_x, detection->bbox_y,
               detection->bbox_w, detection->bbox_h,
               detection->sampled_area, detection->confidence_percent);
    }
    return count < 0 ? 4 : 0;
}

