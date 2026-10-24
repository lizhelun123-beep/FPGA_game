#ifndef GAME_PHOTO_INPUT_H
#define GAME_PHOTO_INPUT_H
#include "game_scene_adapter.h"
#include <stdio.h>

/* Explicit file-input diagnostic, never camera capture. PNG decoding happens
 * losslessly offline; these CPU-owned BGR files never become display pixels.
 * Dispatch time measures a NEW detector execution, not photograph exposure. */
#define GAME_PHOTO_BYTES (1280U * 720U * 3U)
typedef struct {
    uint8_t *pixels[GAME_MAX_LEVELS];
    VisionDetection detections[VISION_MAX_DETECTIONS];
} GamePhotoInput;
int game_photo_load(GamePhotoInput *input, const char *directory);
void game_photo_close(GamePhotoInput *input);
/* Caller supplies the original dispatch stamp BEFORE detection; no cached
 * detections, template completion, timestamp renewal or game-state changes. */
int game_photo_detect(GamePhotoInput *input, unsigned level,
                      GameCaptureStamp stamp, GameDetectionFrame *frame);
int game_photo_write(const GameDetectionFrame *frame, unsigned level, FILE *out);
#endif
