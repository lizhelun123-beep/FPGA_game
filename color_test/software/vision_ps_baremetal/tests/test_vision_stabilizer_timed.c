/* Controlled host observation sequences, not a real-camera A/B comparison. */
#include "vision_stabilizer.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PI_F 3.14159265358979323846f
static unsigned int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)

static VisionDetection pose(VisionType type, float x, float angle)
{
    VisionDetection result;
    memset(&result, 0, sizeof(result));
    result.type = type;
    result.center_x = (int)lroundf(x); result.center_y = 200;
    result.geometry_center_x = x; result.geometry_center_y = 200;
    result.bbox_x = result.center_x-40; result.bbox_y = 185;
    result.bbox_w = 80; result.bbox_h = 30;
    result.major_length = 80; result.minor_width = 25;
    result.axis_x = cosf(angle*PI_F/180.0f);
    result.axis_y = sinf(angle*PI_F/180.0f);
    result.confidence_percent = 100;
    return result;
}

static int near(float a, float b) { return fabsf(a-b) < 0.01f; }
static float angle(const VisionDetection *d)
{
    return atan2f(d->axis_y, d->axis_x)*180.0f/PI_F;
}

static int update(VisionTimedStabilizer *s, VisionDetection value,
                   uint64_t captured, int algorithm, VisionDetection *out,
                   VisionTimedStatus *status)
{
    return vision_stabilizer_update_timed(s, &value, 1, captured, algorithm,
                                          out, VISION_MAX_DETECTIONS, status);
}

static void test_hysteresis_motion(void)
{
    VisionTimedStabilizer s;
    VisionTimedStatus status;
    VisionDetection out[VISION_MAX_DETECTIONS];
    unsigned int bit = 1U << VISION_PORTAL_A;
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 10,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(status.timestamp_accepted && status.pending_mask == bit && !status.supported_mask);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 70,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 110,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(status.supported_mask == bit && status.committed_mask == bit);
    CHECK(!out[0].direction_valid && near(out[0].geometry_center_x, 100));
    CHECK(update(&s, pose(VISION_PORTAL_A, 100.2f, 0.1f), 170,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(!status.pending_mask && !status.committed_mask);
    CHECK(near(out[0].geometry_center_x, 100) && near(angle(&out[0]), 0));
    /* A small adjustment above the deadband also commits after real elapsed
     * time; it cannot remain trapped below the larger release threshold. */
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0.5f), 200,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(status.pending_mask == bit);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0.5f), 260,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0.5f), 320,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(angle(&out[0]), 0.5f) && !out[0].direction_valid);
    /* Both quarter-turn and full directed reversal are legal in place. */
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 90), 350,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 90), 410,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(angle(&out[0]), 90) && near(out[0].geometry_center_x, 100));
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 270), 440,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 270), 500,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(angle(&out[0]), -90));
    CHECK(vision_stabilizer_update_timed(&s, NULL, 0, 520, VISION_STABILITY_B,
                  out, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK(status.missing_mask & bit);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 270), 530,
                  VISION_STABILITY_B, out, &status) == 1);
    /* Expired support has to reacquire; saved geometry cannot score. */
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 270), 1010,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(status.pending_mask == bit && !status.supported_mask);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 270), 1110,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(update(&s, pose(VISION_PORTAL_A, 101, 270), 1140,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 101, 270), 1260,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(out[0].geometry_center_x, 101));
}

static void test_axis_equivalence(void)
{
    VisionTimedStabilizer s;
    VisionTimedStatus status;
    VisionDetection out[VISION_MAX_DETECTIONS];
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_MIRROR, 100, 0), 0,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_MIRROR, 100, 180), 100,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(angle(&out[0]), 0));
    CHECK(update(&s, pose(VISION_MIRROR, 100, 180), 130,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(!status.pending_mask && near(angle(&out[0]), 0));
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_PORTAL_B, 100, 179), 0,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_B, 100, 179), 100,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(update(&s, pose(VISION_PORTAL_B, 100, -179), 130,
                  VISION_STABILITY_B, out, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_B, 100, -179), 190,
                  VISION_STABILITY_B, out, &status) == 1);
    CHECK(near(angle(&out[0]), -179));
}

static void test_adaptive_filter_and_time(void)
{
    VisionTimedStabilizer s, saved;
    VisionTimedStatus status;
    VisionDetection out[VISION_MAX_DETECTIONS];
    float previous;
    unsigned int bit = 1U << VISION_PORTAL_A;
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 0,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(update(&s, pose(VISION_PORTAL_A, 110, 10), 50,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(out[0].geometry_center_x > 100 && out[0].geometry_center_x < 110);
    CHECK(angle(&out[0]) > 0 && angle(&out[0]) < 10);
    CHECK(status.captured_ms == 50 && status.timestamp_accepted && status.supported_mask == bit);
    previous = out[0].geometry_center_x;
    saved = s;
    CHECK(update(&s, pose(VISION_PORTAL_A, 900, 90), 50,
                  VISION_STABILITY_A, out, &status) == 0);
    CHECK(!status.timestamp_accepted && !status.supported_mask && status.captured_ms == 50);
    CHECK(memcmp(&s, &saved, sizeof(s)) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 900, 90), 49,
                  VISION_STABILITY_A, out, &status) == 0);
    CHECK(!status.timestamp_accepted && memcmp(&s, &saved, sizeof(s)) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 200, 90), 100,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(out[0].geometry_center_x > previous && out[0].geometry_center_x < 200);
    CHECK(vision_stabilizer_update_timed(&s, NULL, 0, 150, VISION_STABILITY_A,
                  out, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK(status.missing_mask & bit);
    CHECK(update(&s, pose(VISION_PORTAL_A, 900, 90), 450,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(near(out[0].geometry_center_x, 900) && near(angle(&out[0]), 90));
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 179), 0,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, -179), 50,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(fabsf(angle(&out[0])) > 170);
    vision_stabilizer_timed_reset(&s);
    CHECK(update(&s, pose(VISION_MIRROR, 100, 0), 0,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(update(&s, pose(VISION_MIRROR, 100, 180), 50,
                  VISION_STABILITY_A, out, &status) == 1);
    CHECK(near(angle(&out[0]), 0));
}

static void test_ambiguity_and_reacquisition(void)
{
    VisionTimedStabilizer s, saved, duplicate_b;
    VisionTimedStatus status;
    VisionDetection values[VISION_MAX_DETECTIONS];
    unsigned int bit = 1U << VISION_PORTAL_A;
    vision_stabilizer_timed_reset(&s);
    values[0] = pose(VISION_PORTAL_A, 100, 0);
    CHECK(vision_stabilizer_update_timed(&s, values, 1, 0, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK(vision_stabilizer_update_timed(&s, NULL, 0, 50, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 0);
    /* The miss resets the confirmation timer, even if the reappearance is
     * identical to a pending candidate. */
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 100,
                  VISION_STABILITY_B, values, &status) == 0);
    CHECK(update(&s, pose(VISION_PORTAL_A, 100, 0), 200,
                  VISION_STABILITY_B, values, &status) == 1);
    values[0] = values[1] = pose(VISION_PORTAL_A, 100, 0);
    CHECK(vision_stabilizer_update_timed(&s, values, 2, 220, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK((status.missing_mask & bit) && !status.supported_mask);
    /* Portal B fallback candidates obey the same unique-identity boundary:
     * two orange carriers must remain missing rather than selecting either. */
    vision_stabilizer_timed_reset(&duplicate_b);
    values[0] = values[1] = pose(VISION_PORTAL_B, 100, 0);
    CHECK(vision_stabilizer_update_timed(&duplicate_b, values, 2, 225, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK((status.missing_mask & (1U << VISION_PORTAL_B)) && !status.supported_mask);
    values[0] = pose(VISION_PORTAL_A, 100, 0);
    values[0].axis_x = NAN;
    CHECK(vision_stabilizer_update_timed(&s, values, 1, 230, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 0);
    CHECK(status.missing_mask & bit);
    values[0] = pose(VISION_PORTAL_A, 100, 0);
    CHECK(vision_stabilizer_update_timed(&s, values, 1, 240, VISION_STABILITY_B,
                  values, VISION_MAX_DETECTIONS, &status) == 1);
    CHECK(!values[0].direction_valid); /* scene-v1 Portal flag stays SOURCE-only */
    saved = s;
    CHECK(vision_stabilizer_update_timed(&s, values, 1, 241, 99,
                  values, VISION_MAX_DETECTIONS, &status) == -1);
    CHECK(memcmp(&saved, &s, sizeof(s)) == 0);
    CHECK(vision_stabilizer_update_timed(&s, values, 1, 241, VISION_STABILITY_B,
                  values, 1, &status) == -1);
    CHECK(memcmp(&saved, &s, sizeof(s)) == 0);
}

static void test_mirror_portal_b_support_gap_500(void)
{
    const unsigned gaps[] = {400U, 500U, 501U};
    unsigned i;
    for (i = 0; i < sizeof(gaps)/sizeof(gaps[0]); ++i) {
        VisionTimedStabilizer s;
        VisionTimedStatus status;
        VisionDetection raw[2], out[VISION_MAX_DETECTIONS];
        unsigned mask = (1U << VISION_MIRROR) | (1U << VISION_PORTAL_B);
        raw[0] = pose(VISION_MIRROR, 100, 0);
        raw[1] = pose(VISION_PORTAL_B, 300, 90);
        vision_stabilizer_timed_reset(&s);
        CHECK(vision_stabilizer_update_timed_gap(&s, raw, 2, 1000,
              VISION_STABILITY_B, out, VISION_MAX_DETECTIONS, &status, 500) == 0);
        CHECK(status.pending_mask == mask);
        CHECK(vision_stabilizer_update_timed_gap(&s, raw, 2, 1000+gaps[i],
              VISION_STABILITY_B, out, VISION_MAX_DETECTIONS, &status, 500) ==
              (gaps[i] <= 500U ? 2 : 0));
        CHECK((gaps[i] <= 500U ? status.supported_mask : status.pending_mask) == mask);
        CHECK(status.captured_ms == 1000+gaps[i]);
    }
}

int main(void)
{
    test_hysteresis_motion();
    test_axis_equivalence();
    test_adaptive_filter_and_time();
    test_ambiguity_and_reacquisition();
    test_mirror_portal_b_support_gap_500();
    printf("PASS timed stabilizer: %u checks (controlled host inputs only)\n", checks);
    return 0;
}
