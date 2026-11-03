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

enum { VISION_STABILITY_A = 0, VISION_STABILITY_B = 1 };

typedef struct {
    int have_observation, have_candidate;
    uint64_t observed_ms, candidate_since_ms;
    float position_speed, angular_speed;
    VisionDetection previous_raw;
} VisionTimedTrack;

/* Separate opt-in storage: never mix timed and legacy updates on one track.
 * Poses reuse the existing per-class geometry/sample representation. */
typedef struct {
    VisionStabilizer poses;
    VisionTimedTrack timing[VISION_STABILIZER_TRACK_COUNT];
    int algorithm, have_capture;
    uint64_t last_capture_ms;
} VisionTimedStabilizer;

typedef struct {
    uint64_t captured_ms;
    int timestamp_accepted;
    unsigned int supported_mask, pending_mask, missing_mask, committed_mask;
} VisionTimedStatus;

void vision_stabilizer_timed_reset(VisionTimedStabilizer *stabilizer);

/* Camera-pixel preview settings, pending a comparison on real motion video:
 * A: adaptive position/angle low-pass; one reliable first observation seeds it.
 * B: position OR angle triggers; 0.75 px/0.25 deg deadband, 1.5 px/0.75 deg
 * fast-release threshold; >=2 observations spanning 100 ms for acquisition,
 * 60 ms for a large change, or 120 ms for a small adjustment. No mm claim.
 * Mirror/Wall use 180-deg equivalence; Portal uses ID-directed 360-deg axes.
 * A gap >250 ms resets acquisition, rather than reviving a saved pose as fresh.
 *
 * Input contains only reliable current observations, not predicted/held poses;
 * restricted single-Tag poses must already be excluded upstream. Portal uses
 * its reliable axis; direction_valid retains the legacy SOURCE-only meaning.
 * Ambiguous duplicate classes are missing.
 * Output includes only geometry supported by THIS input: missing classes and
 * unconfirmed B candidates never emit the previous pose. Display retention
 * belongs to the caller. Required pending/missing classes cannot score.
 * Original captured_ms is returned unchanged; duplicate/out-of-order timestamps
 * return 0 with timestamp_accepted=0 and do not modify history or freshness.
 * Return output count or -1 on bad arguments. raw and output may alias.
 * capacity must accommodate all six class slots. No clocks/devices are read. */
int vision_stabilizer_update_timed(VisionTimedStabilizer *stabilizer,
                                   const VisionDetection *raw, int count,
                                   uint64_t captured_ms, int algorithm,
                                   VisionDetection *output, int capacity,
                                   VisionTimedStatus *status);

/* 使用同一时序稳定算法，显式指定 250、350 或 500ms 连续观测支持间隔。
 * This controls reacquisition only: missing input still emits no old pose,
 * and captured_ms, confirmation delays and deadbands retain their meanings.
 * The original entry point keeps its historical 250ms policy. */
int vision_stabilizer_update_timed_gap(VisionTimedStabilizer *stabilizer,
                                   const VisionDetection *raw, int count,
                                   uint64_t captured_ms, int algorithm,
                                   VisionDetection *output, int capacity,
                                   VisionTimedStatus *status,
                                   unsigned support_gap_ms);

#endif
