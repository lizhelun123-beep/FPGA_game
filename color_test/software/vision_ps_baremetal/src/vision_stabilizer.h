#ifndef VISION_STABILIZER_H
#define VISION_STABILIZER_H

#include "vision_ps.h"

#define VISION_STABILIZER_TRACK_COUNT 6
#define VISION_STABILIZER_MAX_SAMPLES 8

typedef struct {
    int active;
    int sample_count;
    unsigned int missed_frames;
    VisionDetection confirmed;
    VisionDetection samples[VISION_STABILIZER_MAX_SAMPLES];
    float candidate_position_spread;
    float candidate_angle_spread_deg;
    unsigned int raw_observations;
    unsigned int valid_samples;
    unsigned int commit_count;
    unsigned int direction_flip_rejections;
} VisionDirectionTrack;

typedef struct {
    VisionDirectionTrack tracks[VISION_STABILIZER_TRACK_COUNT];
    unsigned int frames;
} VisionStabilizer;

void vision_stabilizer_reset(VisionStabilizer *stabilizer);

/* Convert raw detections into persistent confirmed poses. Candidate samples do
 * not have to be consecutive; a miss pauses acquisition and never removes a
 * confirmed pose. The caller must provide the writable array capacity. */
int vision_stabilizer_update(VisionStabilizer *stabilizer,
                             VisionDetection *detections, int count,
                             int capacity);

#endif
