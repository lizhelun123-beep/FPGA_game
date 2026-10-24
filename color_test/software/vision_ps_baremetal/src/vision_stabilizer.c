#include "vision_stabilizer.h"

#include <math.h>
#include <string.h>

#define PI_F 3.14159265358979323846f
#define SOURCE_CONFIRM_SAMPLES 8
#define PORTAL_CONFIRM_SAMPLES 5
#define MIRROR_WALL_CONFIRM_SAMPLES 4
#define TARGET_CONFIRM_SAMPLES 3
#define SOURCE_DEAD_POSITION 8.0f
#define SOURCE_DEAD_ANGLE_DEG 5.0f
#define SOURCE_MOVE_POSITION 24.0f
#define SOURCE_MOVE_ANGLE_DEG 17.0f
#define OBJECT_DEAD_POSITION 6.0f
#define OBJECT_DEAD_ANGLE_DEG 5.0f
#define OBJECT_MOVE_POSITION 16.0f
#define OBJECT_MOVE_ANGLE_DEG 12.0f
#define PORTAL_MOVE_POSITION 18.0f
#define TARGET_MOVE_POSITION 14.0f
#define CANDIDATE_POSITION_GATE 8.0f
#define CANDIDATE_ANGLE_GATE_DEG 6.0f
#define SOURCE_CANDIDATE_POSITION_GATE 5.0f
#define SOURCE_CANDIDATE_ANGLE_GATE_DEG 2.0f
#define CANDIDATE_SIZE_RATIO 1.15f

static int track_slot(VisionType type)
{
    return (unsigned int)type <= (unsigned int)VISION_WALL ? (int)type : -1;
}

static int required_samples(VisionType type)
{
    switch (type) {
    case VISION_SOURCE: return SOURCE_CONFIRM_SAMPLES;
    case VISION_PORTAL_A:
    case VISION_PORTAL_B: return PORTAL_CONFIRM_SAMPLES;
    case VISION_TARGET: return TARGET_CONFIRM_SAMPLES;
    case VISION_MIRROR:
    case VISION_WALL:
    default: return MIRROR_WALL_CONFIRM_SAMPLES;
    }
}

static int is_directed(VisionType type)
{
    return type == VISION_SOURCE || type == VISION_PORTAL_A ||
           type == VISION_PORTAL_B;
}

static void detection_direction(const VisionDetection *detection,
                                float *x, float *y)
{
    if (detection->type == VISION_SOURCE) {
        *x = detection->source_direction_x;
        *y = detection->source_direction_y;
    } else {
        *x = detection->axis_x;
        *y = detection->axis_y;
    }
}

static int normalize(float *x, float *y)
{
    float magnitude = sqrtf((*x)*(*x) + (*y)*(*y));
    if (magnitude <= 1.0e-6f) return 0;
    *x /= magnitude;
    *y /= magnitude;
    return 1;
}

static float center_x(const VisionDetection *detection)
{
    return detection->geometry_center_x != 0.0f || detection->center_x == 0 ?
           detection->geometry_center_x : (float)detection->center_x;
}

static float center_y(const VisionDetection *detection)
{
    return detection->geometry_center_y != 0.0f || detection->center_y == 0 ?
           detection->geometry_center_y : (float)detection->center_y;
}

static float position_distance(const VisionDetection *first,
                               const VisionDetection *second)
{
    float dx;
    float dy;
    if (first->type == VISION_SOURCE) {
        dx = (float)(first->source_tip_x-second->source_tip_x);
        dy = (float)(first->source_tip_y-second->source_tip_y);
    } else {
        dx = center_x(first)-center_x(second);
        dy = center_y(first)-center_y(second);
    }
    return sqrtf(dx*dx + dy*dy);
}

static float direction_dot(const VisionDetection *first,
                           const VisionDetection *second, int directed)
{
    float first_x;
    float first_y;
    float second_x;
    float second_y;
    float product;
    detection_direction(first, &first_x, &first_y);
    detection_direction(second, &second_x, &second_y);
    if (!normalize(&first_x, &first_y) || !normalize(&second_x, &second_y))
        return -1.0f;
    product = first_x*second_x + first_y*second_y;
    if (!directed && product < 0.0f) product = -product;
    if (product > 1.0f) product = 1.0f;
    if (product < -1.0f) product = -1.0f;
    return product;
}

static float angle_difference(const VisionDetection *first,
                              const VisionDetection *second, int directed)
{
    return acosf(direction_dot(first, second, directed))*180.0f/PI_F;
}

static float size_ratio(float first, float second)
{
    float maximum;
    float minimum;
    if (first <= 1.0f || second <= 1.0f) return 1.0f;
    maximum = first > second ? first : second;
    minimum = first < second ? first : second;
    return maximum/minimum;
}

static float pose_size_ratio(const VisionDetection *first,
                             const VisionDetection *second)
{
    float length_ratio = size_ratio(first->major_length, second->major_length);
    float width_ratio = size_ratio(first->minor_width, second->minor_width);
    return length_ratio > width_ratio ? length_ratio : width_ratio;
}

static int valid_detection(const VisionDetection *detection)
{
    float x;
    float y;
    if (!detection || track_slot(detection->type) < 0 ||
        detection->major_length <= 1.0f || detection->minor_width <= 1.0f)
        return 0;
    if (detection->type == VISION_SOURCE && !detection->direction_valid)
        return 0;
    if (detection->type == VISION_TARGET) return 1;
    detection_direction(detection, &x, &y);
    return normalize(&x, &y);
}

static int small_change(const VisionDetection *confirmed,
                        const VisionDetection *candidate)
{
    float distance = position_distance(confirmed, candidate);
    float ratio = pose_size_ratio(confirmed, candidate);
    if (confirmed->type == VISION_TARGET)
        return distance <= OBJECT_DEAD_POSITION && ratio <= 1.10f;
    if (confirmed->type == VISION_SOURCE)
        return distance <= SOURCE_DEAD_POSITION && ratio <= 1.12f &&
               angle_difference(confirmed, candidate, 1) <=
                   SOURCE_DEAD_ANGLE_DEG;
    return distance <= OBJECT_DEAD_POSITION && ratio <= 1.10f &&
           angle_difference(confirmed, candidate,
                            is_directed(confirmed->type)) <=
               OBJECT_DEAD_ANGLE_DEG;
}

static int major_change(const VisionDetection *confirmed,
                        const VisionDetection *candidate)
{
    float distance = position_distance(confirmed, candidate);
    float ratio = pose_size_ratio(confirmed, candidate);
    switch (confirmed->type) {
    case VISION_SOURCE:
        return distance >= SOURCE_MOVE_POSITION || ratio >= 1.20f ||
               angle_difference(confirmed, candidate, 1) >=
                   SOURCE_MOVE_ANGLE_DEG;
    case VISION_PORTAL_A:
    case VISION_PORTAL_B:
        /* A Portal direction may change only together with a confirmed move. */
        return distance >= PORTAL_MOVE_POSITION || ratio >= 1.18f;
    case VISION_TARGET:
        return distance >= TARGET_MOVE_POSITION || ratio >= 1.15f;
    case VISION_MIRROR:
    case VISION_WALL:
    default:
        return distance >= OBJECT_MOVE_POSITION || ratio >= 1.18f ||
               angle_difference(confirmed, candidate, 0) >=
                   OBJECT_MOVE_ANGLE_DEG;
    }
}

static int candidate_matches(const VisionDirectionTrack *track,
                             const VisionDetection *candidate)
{
    int index;
    float position_gate = candidate->type == VISION_SOURCE ?
                          SOURCE_CANDIDATE_POSITION_GATE :
                          CANDIDATE_POSITION_GATE;
    float angle_gate = candidate->type == VISION_SOURCE ?
                       SOURCE_CANDIDATE_ANGLE_GATE_DEG :
                       CANDIDATE_ANGLE_GATE_DEG;
    float minimum_dot = cosf(angle_gate*PI_F/180.0f);
    for (index = 0; index < track->sample_count; ++index) {
        const VisionDetection *sample = &track->samples[index];
        if (position_distance(sample, candidate) > position_gate ||
            pose_size_ratio(sample, candidate) > CANDIDATE_SIZE_RATIO)
            return 0;
        if (sample->type != VISION_TARGET &&
            direction_dot(sample, candidate, is_directed(sample->type)) <
                minimum_dot)
            return 0;
    }
    return 1;
}

static float median(float *values, int count)
{
    int first;
    int second;
    for (first = 0; first < count; ++first)
        for (second = first+1; second < count; ++second)
            if (values[second] < values[first]) {
                float temporary = values[first];
                values[first] = values[second];
                values[second] = temporary;
            }
    if (count & 1) return values[count/2];
    return 0.5f*(values[count/2-1]+values[count/2]);
}

static float median_field(const VisionDirectionTrack *track, int field)
{
    float values[VISION_STABILIZER_MAX_SAMPLES];
    int index;
    for (index = 0; index < track->sample_count; ++index) {
        const VisionDetection *sample = &track->samples[index];
        switch (field) {
        case 0: values[index] = center_x(sample); break;
        case 1: values[index] = center_y(sample); break;
        case 2: values[index] = sample->major_length; break;
        case 3: values[index] = sample->minor_width; break;
        case 4: values[index] = (float)sample->source_tip_x; break;
        default: values[index] = (float)sample->source_tip_y; break;
        }
    }
    return median(values, track->sample_count);
}

static VisionDetection aggregate_samples(VisionDirectionTrack *track)
{
    VisionDetection result = track->samples[0];
    float position_x = median_field(track, 0);
    float position_y = median_field(track, 1);
    float direction_x = 0.0f;
    float direction_y = 0.0f;
    float reference_x;
    float reference_y;
    float maximum_position = 0.0f;
    float maximum_angle = 0.0f;
    int index;
    result.geometry_center_x = position_x;
    result.geometry_center_y = position_y;
    result.center_x = (int)lroundf(position_x);
    result.center_y = (int)lroundf(position_y);
    result.major_length = median_field(track, 2);
    result.minor_width = median_field(track, 3);
    result.source_tip_x = (int)lroundf(median_field(track, 4));
    result.source_tip_y = (int)lroundf(median_field(track, 5));
    result.bbox_x = result.center_x-result.bbox_w/2;
    result.bbox_y = result.center_y-result.bbox_h/2;
    detection_direction(&track->samples[0], &reference_x, &reference_y);
    (void)normalize(&reference_x, &reference_y);
    for (index = 0; index < track->sample_count; ++index) {
        float x;
        float y;
        float distance;
        float angle;
        detection_direction(&track->samples[index], &x, &y);
        if (normalize(&x, &y)) {
            if (!is_directed(result.type) &&
                reference_x*x+reference_y*y < 0.0f) {
                x = -x;
                y = -y;
            }
            direction_x += x;
            direction_y += y;
        }
        if (result.type == VISION_SOURCE) {
            float dx = (float)track->samples[index].source_tip_x-
                       (float)result.source_tip_x;
            float dy = (float)track->samples[index].source_tip_y-
                       (float)result.source_tip_y;
            distance = sqrtf(dx*dx+dy*dy);
        } else {
            float dx = center_x(&track->samples[index])-position_x;
            float dy = center_y(&track->samples[index])-position_y;
            distance = sqrtf(dx*dx+dy*dy);
        }
        angle = angle_difference(&track->samples[0],
                                 &track->samples[index],
                                 is_directed(result.type));
        if (distance > maximum_position) maximum_position = distance;
        if (angle > maximum_angle) maximum_angle = angle;
    }
    (void)normalize(&direction_x, &direction_y);
    result.axis_x = direction_x;
    result.axis_y = direction_y;
    result.angle_deg = (int)lroundf(atan2f(direction_y, direction_x)*
                                    180.0f/PI_F);
    if (result.type == VISION_SOURCE) {
        result.source_direction_x = direction_x;
        result.source_direction_y = direction_y;
        result.direction_valid = 1;
    } else if (result.type == VISION_PORTAL_A ||
               result.type == VISION_PORTAL_B) {
        /* The signed axis is the solid-marker -> ring-marker identity. */
        result.direction_valid = 1;
    }
    track->candidate_position_spread = maximum_position;
    track->candidate_angle_spread_deg = maximum_angle;
    return result;
}

static void add_candidate_sample(VisionDirectionTrack *track,
                                 const VisionDetection *candidate)
{
    if (track->sample_count && !candidate_matches(track, candidate))
        track->sample_count = 0;
    if (track->sample_count < VISION_STABILIZER_MAX_SAMPLES) {
        track->samples[track->sample_count++] = *candidate;
        track->valid_samples++;
    }
    if (track->sample_count >= required_samples(candidate->type)) {
        track->confirmed = aggregate_samples(track);
        track->active = 1;
        track->sample_count = 0;
        track->missed_frames = 0U;
        track->commit_count++;
    }
}

static int choose_detection(const VisionDirectionTrack *track,
                            const VisionDetection *detections, int count,
                            VisionType type)
{
    int selected = -1;
    int matches = 0;
    int index;
    float best_distance = 0.0f;
    for (index = 0; index < count; ++index) {
        float distance;
        if (detections[index].type != type ||
            !valid_detection(&detections[index]))
            continue;
        matches++;
        if (!track->active) {
            selected = index;
            continue;
        }
        distance = position_distance(&track->confirmed, &detections[index]);
        if (selected < 0 || distance < best_distance) {
            selected = index;
            best_distance = distance;
        }
    }
    if (!track->active && matches != 1) return -1;
    return selected;
}

void vision_stabilizer_reset(VisionStabilizer *stabilizer)
{
    if (stabilizer) memset(stabilizer, 0, sizeof(*stabilizer));
}

int vision_stabilizer_update(VisionStabilizer *stabilizer,
                             VisionDetection *detections, int count,
                             int capacity)
{
    VisionDetection raw[VISION_MAX_DETECTIONS];
    int output_count = 0;
    int slot;
    if (!stabilizer || count < 0 || capacity < 0 || count > capacity ||
        count > VISION_MAX_DETECTIONS || capacity > VISION_MAX_DETECTIONS ||
        (capacity && !detections))
        return -1;
    if (count) memcpy(raw, detections, (size_t)count*sizeof(raw[0]));
    stabilizer->frames++;
    for (slot = 0; slot < VISION_STABILIZER_TRACK_COUNT; ++slot) {
        VisionDirectionTrack *track = &stabilizer->tracks[slot];
        VisionType type = (VisionType)slot;
        int selected = choose_detection(track, raw, count, type);
        if (selected < 0) {
            track->missed_frames++;
            continue;
        }
        track->raw_observations++;
        track->missed_frames = 0U;
        if (!track->active) {
            add_candidate_sample(track, &raw[selected]);
            continue;
        }
        if ((type == VISION_PORTAL_A || type == VISION_PORTAL_B) &&
            position_distance(&track->confirmed, &raw[selected]) <
                PORTAL_MOVE_POSITION &&
            direction_dot(&track->confirmed, &raw[selected], 1) < 0.0f) {
            track->direction_flip_rejections++;
            continue;
        }
        if (small_change(&track->confirmed, &raw[selected])) {
            track->sample_count = 0;
            continue;
        }
        if (!major_change(&track->confirmed, &raw[selected])) continue;
        add_candidate_sample(track, &raw[selected]);
    }
    for (slot = 0; slot < VISION_STABILIZER_TRACK_COUNT; ++slot) {
        VisionDirectionTrack *track = &stabilizer->tracks[slot];
        if (!track->active) continue;
        if (output_count >= capacity) return -1;
        detections[output_count++] = track->confirmed;
    }
    return output_count;
}
