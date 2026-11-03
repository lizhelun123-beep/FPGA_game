/* Small host ABI. Production recognition and physics remain in the PS sources. */
#include "ray_game.h"
#include "scene_protocol.h"
#include <math.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
static int game_detect(const uint8_t *frame, uint32_t width, uint32_t height,
    uint32_t stride, uint32_t sequence, char *line, unsigned int capacity)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count = vision_detect_bgr888(frame, width, height, stride,
                                   detections, VISION_MAX_DETECTIONS);
    return scene_protocol_encode(line, capacity, detections, count, count >= 0,
                                 sequence, sequence, 0, (uint16_t)width, (uint16_t)height);
}
/* Twelve floats/object; explicit arrays avoid exposing compiler struct layout.
 * The same fixed model geometry used by the renderer is passed here.
 * Canonical epsilon=1, source offset=3 become 1/scale and 3/scale plane units.
 * Adding 1 to the frame extent accounts for C's inclusive pixel boundary. */
static int game_trace(const float *rows, int count, float width, float height,
    float scale, float *segments, int *info)
{
    SceneObject objects[VISION_MAX_DETECTIONS];
    RayGameResult result;
    int n, k, status;
    if (!rows || !segments || !info || count < 0 || count > VISION_MAX_DETECTIONS ||
        !isfinite(scale) || scale < 1 || !isfinite(width) || !isfinite(height) ||
        width <= 0 || height <= 0) return -1;
    memset(objects, 0, sizeof(objects));
    for (n = 0; n < count; ++n) {
        const float *r = rows + n*12;
        SceneObject *o = objects + n;
        for (k = 0; k < 12; ++k) if (!isfinite(r[k])) return -1;
        if (r[0] < 0 || r[0] >= RAY_OBJECT_TYPE_COUNT || r[5] <= 0 || r[6] <= 0)
            return -1;
        o->type = (RayObjectType)(int)r[0];
        o->center = (RayPoint){r[1]*scale, r[2]*scale};
        o->axis = (RayPoint){r[3], r[4]};
        o->length = r[5]*scale; o->width = r[6]*scale;
        o->source_tip = (RayPoint){r[7]*scale, r[8]*scale};
        o->source_direction = (RayPoint){r[9], r[10]};
        o->direction_valid = (int)r[11];
    }
    status = ray_game_trace(objects, count, width*scale+1, height*scale+1, &result);
    info[0] = result.segment_count; info[1] = result.interaction_count;
    info[2] = result.success; info[3] = result.termination; info[4] = result.hit_count;
    for (n = 0; n < result.hit_count; ++n) info[5+n] = result.hit_types[n];
    for (n = 0; n < result.segment_count; ++n) {
        segments[n*4] = result.segments[n].start.x/scale;
        segments[n*4+1] = result.segments[n].start.y/scale;
        segments[n*4+2] = result.segments[n].end.x/scale;
        segments[n*4+3] = result.segments[n].end.y/scale;
    }
    return status;
}

int main(void)
{
    int command;
    uint8_t *frame = (uint8_t *)malloc(1280U*720U*3U);
    if (!frame) return 2;
#ifdef _WIN32
    _setmode(0, _O_BINARY);
    _setmode(1, _O_BINARY);
#endif
    fputs("SCENE_HOST_V1\n", stdout);
    fflush(stdout);
    while ((command = fgetc(stdin)) != EOF && command != 'Q') {
        if (command == 'D') {
            uint32_t sequence;
            char line[SCENE_PROTOCOL_MAX_LINE+1];
            int length;
            if (fread(&sequence, sizeof(sequence), 1, stdin) != 1 ||
                fread(frame, 1, 1280U*720U*3U, stdin) != 1280U*720U*3U) break;
            length = game_detect(frame, 1280, 720, 1280*3, sequence, line, sizeof(line));
            if (length < 0) break;
            fwrite(line, 1, (size_t)length, stdout);
        } else if (command == 'R') {
            int32_t count, status;
            float dimensions[3], rows[12*VISION_MAX_DETECTIONS] = {0};
            float segments[4*RAY_GAME_MAX_SEGMENTS] = {0};
            int info[5+RAY_GAME_MAX_INTERACTIONS] = {0};
            if (fread(&count, sizeof(count), 1, stdin) != 1 ||
                count < 0 || count > VISION_MAX_DETECTIONS ||
                fread(dimensions, sizeof(float), 3, stdin) != 3 ||
                fread(rows, sizeof(float)*12, (size_t)count, stdin) != (size_t)count) break;
            status = game_trace(rows, count, dimensions[0], dimensions[1], dimensions[2], segments, info);
            fwrite(&status, sizeof(status), 1, stdout);
            fwrite(segments, sizeof(segments), 1, stdout);
            fwrite(info, sizeof(info), 1, stdout);
        } else break;
        fflush(stdout);
    }
    free(frame);
    return 0;
}
