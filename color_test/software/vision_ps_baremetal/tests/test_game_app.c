/* Boundary tests using VisionDetection pose fixtures from generated anchors.
 * These are not detector/photo acceptance tests. Time is entirely simulated. */
#include "game_app.h"
#include "game_config.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)

static GameSnapshot snapshot(const GameApp *app)
{
    GameSnapshot view;
    CHECK(game_app_snapshot(app, &view) == GAME_OK);
    return view;
}

static void init(GameApp *app, unsigned int level, uint64_t now)
{
    CHECK(game_app_init(app, &game_default_config,
                        &game_uncalibrated_identity_mapping) == GAME_OK);
    CHECK(snapshot(app).state == GAME_SELECT_LEVEL);
    CHECK(game_app_select(app, level, now) == GAME_OK);
    CHECK(snapshot(app).state == GAME_PREPARING);
    CHECK(!snapshot(app).object_count && !snapshot(app).ready);
}

static int fixture(unsigned int id, VisionDetection *detections, int unsolved)
{
    const GameLevelConfig *level = NULL;
    int i;
    for (i = 0; i < game_default_config.level_count; ++i)
        if (game_default_config.levels[i].id == id) level = &game_default_config.levels[i];
    CHECK(level != NULL);
    for (i = 0; i < level->object_count; ++i) {
        VisionDetection *d = &detections[i];
        const SceneObject *o = &level->objects[i].anchor;
        memset(d, 0, sizeof(*d));
        switch (o->type) {
        case RAY_OBJECT_MIRROR: d->type = VISION_MIRROR; break;
        case RAY_OBJECT_PORTAL_A: d->type = VISION_PORTAL_A; break;
        case RAY_OBJECT_PORTAL_B: d->type = VISION_PORTAL_B; break;
        case RAY_OBJECT_TARGET: d->type = VISION_TARGET; break;
        case RAY_OBJECT_SOURCE: d->type = VISION_SOURCE; break;
        case RAY_OBJECT_WALL: d->type = VISION_WALL; break;
        default: CHECK(0);
        }
        d->geometry_center_x = o->center.x;
        d->geometry_center_y = o->center.y;
        d->axis_x = o->axis.x; d->axis_y = o->axis.y;
        d->source_direction_x = o->axis.x; d->source_direction_y = o->axis.y;
        d->direction_valid = d->type == VISION_SOURCE;
        /* No measured size/tip should escape into fixed virtual models. */
        d->bbox_w = 999; d->bbox_h = 777;
        d->major_length = 999; d->minor_width = 777;
        d->source_tip_x = 1234; d->source_tip_y = 654;
        if (unsolved && id == 1 && d->type == VISION_SOURCE) {
            d->source_direction_x = d->axis_x = 0;
            d->source_direction_y = d->axis_y = 1;
        }
        if (unsolved && id == 2 && d->type == VISION_PORTAL_A) {
            d->geometry_center_x = d->geometry_center_y = 600;
            d->axis_x = 1; d->axis_y = 0;
        }
    }
    return level->object_count; /* Original 077 is already unsolved. */
}

static VisionDetection *find(VisionDetection *d, int count, VisionType type)
{
    int i;
    for (i = 0; i < count; ++i) if (d[i].type == type) return &d[i];
    CHECK(0); return NULL;
}

static GameDetectionFrame frame(GameApp *app, const VisionDetection *d, int count,
                                 uint64_t sequence, uint64_t captured)
{
    GameDetectionFrame f;
    CHECK(game_app_capture_stamp(app, sequence, captured, &f.stamp) == GAME_OK);
    f.valid = 1; f.held = 0; f.detections = d; f.count = count;
    return f;
}

/* Re-trace the PUBLIC models with the canonical solver/scale and compare the
 * entire ray. This catches a raw-model/constrained-ray publication mismatch. */
static void coherent(const GameSnapshot *view)
{
    SceneObject scaled[GAME_MAX_MODELS];
    RayGameResult ray;
    float scale = game_default_config.physics_scale;
    int i;
    CHECK(view->scene_valid);
    for (i = 0; i < view->object_count; ++i) {
        scaled[i] = view->objects[i];
        scaled[i].center.x *= scale; scaled[i].center.y *= scale;
        scaled[i].source_tip.x *= scale; scaled[i].source_tip.y *= scale;
        scaled[i].length *= scale; scaled[i].width *= scale;
    }
    CHECK(ray_game_trace(scaled, view->object_count,
                         game_default_config.width*scale+1,
                         game_default_config.height*scale+1, &ray) == 0);
    CHECK(ray.success == view->ray.success && ray.termination == view->ray.termination);
    CHECK(ray.segment_count == view->ray.segment_count);
    CHECK(ray.hit_count == view->ray.hit_count);
    for (i = 0; i < ray.hit_count; ++i) CHECK(ray.hit_types[i] == view->ray.hit_types[i]);
    for (i = 0; i < ray.segment_count; ++i) {
        CHECK(fabsf(ray.segments[i].start.x/scale-view->ray.segments[i].start.x) < 0.002f);
        CHECK(fabsf(ray.segments[i].start.y/scale-view->ray.segments[i].start.y) < 0.002f);
        CHECK(fabsf(ray.segments[i].end.x/scale-view->ray.segments[i].end.x) < 0.002f);
        CHECK(fabsf(ray.segments[i].end.y/scale-view->ray.segments[i].end.y) < 0.002f);
    }
}

static int reject_map(const void *context, const SceneObject *camera, SceneObject *mapped)
{
    (void)context; (void)camera; (void)mapped; return 0;
}

static void test_mapping(void)
{
    GameApp app;
    VisionDetection d[VISION_MAX_DETECTIONS];
    SceneObject canonical[VISION_MAX_DETECTIONS];
    GameAdaptedScene adapted;
    GameDetectionFrame f;
    GameSceneMapping mapping = game_uncalibrated_identity_mapping;
    int count = fixture(3, d, 0);
    init(&app, 3, 0);
    f = frame(&app, d, count, UINT64_C(0x100000001), UINT64_C(0x200000002));
    f.stamp.generation = UINT64_C(0x300000003);
    CHECK(game_scene_adapt(&mapping, &f, &adapted) == GAME_OK);
    CHECK(adapted.input.sequence == f.stamp.sequence);
    CHECK(adapted.input.generation == f.stamp.generation);
    CHECK(adapted.input.captured_ms == f.stamp.captured_ms);
    CHECK(adapted.input.objects == adapted.objects && adapted.input.object_count == count);
    CHECK(ray_game_scene_from_detections(d, count, canonical, VISION_MAX_DETECTIONS) == count);
    CHECK(memcmp(canonical, adapted.objects, (size_t)count*sizeof(*canonical)) == 0);
    CHECK(!mapping.calibrated && !strcmp(mapping.coordinate_space, "uncalibrated_preview"));
    f.held = 1;
    CHECK(game_scene_adapt(&mapping, &f, &adapted) == GAME_OK && adapted.input.held);
    f.valid = 0;
    CHECK(game_scene_adapt(&mapping, &f, &adapted) == GAME_INVALID_SCENE);
    CHECK(!adapted.input.valid && adapted.input.held);
    CHECK(adapted.input.sequence == f.stamp.sequence && adapted.input.captured_ms == f.stamp.captured_ms);
    f.valid = 1; f.held = 0;
    mapping.map_pose = reject_map;
    CHECK(game_scene_adapt(&mapping, &f, &adapted) == GAME_INVALID_SCENE);
    CHECK(!adapted.input.valid);
    CHECK(game_app_init(&app, &game_default_config, &mapping) == GAME_OK);
    CHECK(game_app_select(&app, 3, 0) == GAME_OK);
    f.stamp.generation = snapshot(&app).generation; f.stamp.captured_ms = 1;
    CHECK(game_app_submit(&app, &f, 1) == GAME_INVALID_SCENE);
    mapping.coordinate_space = "unprovided_mm_calibration";
    CHECK(game_app_init(&app, &game_default_config, &mapping) == GAME_BAD_CONFIG);
    puts("PASS identity mapping / mapping failure / exact 64-bit capture metadata");
}

static void test_flow(void)
{
    GameApp app;
    VisionDetection d[VISION_MAX_DETECTIONS];
    GameDetectionFrame f;
    GameSnapshot view, frozen;
    FILE *text;
    char line[512];
    int count, i, models = 0, segments = 0;
    init(&app, 1, 0);
    CHECK(game_app_start(&app, 0) == GAME_INVALID_SCENE);
    count = fixture(1, d, 0); f = frame(&app, d, count, 1, 1);
    CHECK(game_app_submit(&app, &f, 1) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.state == GAME_PREPARING && !view.ready && !view.stars);
    CHECK(view.scene_status == GAME_NEED_UNSOLVED);
    CHECK(game_app_start(&app, 1) == GAME_NEED_UNSOLVED);
    count = fixture(1, d, 1); f = frame(&app, d, count, 2, 2);
    CHECK(game_app_submit(&app, &f, 2) == GAME_OK);
    CHECK(snapshot(&app).ready && snapshot(&app).state == GAME_PREPARING);
    CHECK(game_app_tick(&app, 200) == GAME_OK && snapshot(&app).elapsed_ms == 0);
    CHECK(game_app_start(&app, 200) == GAME_OK);
    count = fixture(1, d, 0);
    /* Translating the rotation-only SOURCE and moving fixed objects must not
     * move the constrained models/ray. Observed sizes/tip are also ignored. */
    for (i = 0; i < count; ++i) {
        d[i].geometry_center_x += 20; d[i].geometry_center_y += 10;
    }
    f = frame(&app, d, count, 3, 60000);
    CHECK(game_app_submit(&app, &f, 60100) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.state == GAME_CLEARED && view.stars == 3 && view.elapsed_ms == 59800);
    CHECK(view.captured_ms == 60000 && view.scene_sequence == 3);
    CHECK(view.object_count == count && view.ray.success);
    CHECK(view.objects[0].center.x == game_default_config.levels[0].objects[0].anchor.center.x);
    CHECK(view.objects[0].length == game_default_config.model_sizes[RAY_OBJECT_SOURCE].x);
    coherent(&view);
    frozen = view;
    memset(d, 0, sizeof(d)); /* no retained pointer into detector scratch */
    CHECK(game_app_tick(&app, 500000) == GAME_OK);
    view = snapshot(&app);
    CHECK(memcmp(&view, &frozen, sizeof(view)) == 0);
    text = tmpfile(); CHECK(text != NULL);
    CHECK(game_app_write_snapshot(&app, text) == 0);
    rewind(text);
    CHECK(fgets(line, sizeof(line), text) != NULL);
    CHECK(strstr(line, "mapping=uncalibrated_preview calibrated=0") != NULL);
    CHECK(strstr(line, "generation=1 sequence=3 captured_ms=60000") != NULL);
    while (fgets(line, sizeof(line), text)) {
        if (!strncmp(line, "model=", 6)) ++models;
        if (!strncmp(line, "segment=", 8)) ++segments;
    }
    CHECK(models == view.object_count && segments == view.ray.segment_count);
    CHECK(fclose(text) == 0);
    puts("PASS explicit preparation/start/clear / capture-time score / coherent copied text snapshot");
}

static void test_invalid(void)
{
    /* Each case starts RUNNING with an unsolved candidate, then presents a
     * nominally solved fixture with one invalidity. None may produce a win. */
    int mode;
    for (mode = 0; mode < 15; ++mode) {
        GameApp app;
        VisionDetection d[VISION_MAX_DETECTIONS];
        GameDetectionFrame f;
        GameSnapshot view;
        GameStatus expected = GAME_INVALID_SCENE;
        int count;
        init(&app, 1, 0);
        count = fixture(1, d, 1); f = frame(&app, d, count, 1, 1);
        CHECK(game_app_submit(&app, &f, 1) == GAME_OK);
        CHECK(game_app_start(&app, 2) == GAME_OK);
        count = fixture(1, d, 0); f = frame(&app, d, count, 2, 3);
        switch (mode) {
        case 0: find(d, count, VISION_SOURCE)->direction_valid = 0; break;
        case 1: find(d, count, VISION_SOURCE)->source_direction_x =
                find(d, count, VISION_SOURCE)->source_direction_y = 0; break;
        case 2: find(d, count, VISION_MIRROR)->axis_x =
                find(d, count, VISION_MIRROR)->axis_y = 0; break;
        case 3: f.count--; break;
        case 4: d[1] = d[0]; break;
        case 5: f.held = 1; break;
        case 6: f.valid = 0; break;
        case 7: expected = GAME_STALE_SCENE; break; /* old capture, fresh receipt */
        case 8: f.stamp.sequence = 1; expected = GAME_DUPLICATE_FRAME; break;
        case 9: find(d, count, VISION_MIRROR)->axis_x = NAN; break;
        case 10: d[0].geometry_center_x = NAN; break;
        case 11: d[1].type = (VisionType)99; break;
        case 12: f.count = VISION_MAX_DETECTIONS+1; break; /* no truncation */
        case 13: f.detections = NULL; break;
        case 14: find(d, count, VISION_SOURCE)->source_direction_x = INFINITY; break;
        }
        CHECK(game_app_submit(&app, &f, mode == 7 ? 254 : 3) == expected);
        view = snapshot(&app);
        CHECK(view.state == GAME_RUNNING && !view.stars && !view.ray.success);
        if (mode != 8) CHECK(!view.scene_valid && !view.object_count);
        /* Replaying the repaired same frame cannot repair an invalid capture. */
        count = fixture(1, d, 0); f.valid = 1; f.held = 0;
        f.detections = d; f.count = count;
        CHECK(game_app_submit(&app, &f, mode == 7 ? 254 : 3) == GAME_DUPLICATE_FRAME);
        CHECK(snapshot(&app).state == GAME_RUNNING);
    }
    puts("PASS invalid directions / missing / duplicate / held / stale / replay / malformed detection data");
}

static void test_generation_timeout_077(void)
{
    GameApp app;
    VisionDetection old_d[VISION_MAX_DETECTIONS], d[VISION_MAX_DETECTIONS];
    GameDetectionFrame old, f;
    GameSnapshot view, before;
    int count;
    init(&app, 1, 0);
    count = fixture(1, old_d, 0); old = frame(&app, old_d, count, 90, 1);
    CHECK(game_app_select(&app, 3, 2) == GAME_OK);
    CHECK(game_app_submit(&app, &old, 3) == GAME_OLD_GENERATION);
    CHECK(old.stamp.generation == 1 && old.stamp.captured_ms == 1);
    CHECK(!snapshot(&app).object_count);
    count = fixture(3, d, 0); f = frame(&app, d, count, 1, 4);
    CHECK(game_app_submit(&app, &f, 4) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.ready && !view.ray.success && view.ray.termination == RAY_GAME_BOUNDARY);
    CHECK(view.object_count == 5 && view.ray.segment_count == 3);
    coherent(&view); /* The unchanged 077 template is legal, not an auto-solution. */
    CHECK(game_app_start(&app, 5) == GAME_OK);
    before = snapshot(&app);
    CHECK(game_app_submit(&app, &old, 6) == GAME_OLD_GENERATION);
    view = snapshot(&app);
    CHECK(view.generation == 2 && view.scene_sequence == before.scene_sequence);
    CHECK(memcmp(view.objects, before.objects, sizeof(view.objects)) == 0);
    CHECK(memcmp(&view.ray, &before.ray, sizeof(view.ray)) == 0);
    CHECK(game_app_tick(&app, 1005) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.elapsed_ms == 1000 && view.remaining_ms == 179000);
    CHECK(!view.scene_valid && !view.stars && view.state == GAME_RUNNING);
    CHECK(game_app_tick(&app, 180005) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.state == GAME_TIMED_OUT && !view.remaining_ms && !view.stars);
    CHECK(game_app_select(&app, 2, 180006) == GAME_OK);
    CHECK(snapshot(&app).remaining_ms == 180000 && snapshot(&app).generation == 3);
    count = fixture(2, d, 1); f = frame(&app, d, count, 1, 180007);
    CHECK(game_app_submit(&app, &f, 180007) == GAME_OK);
    CHECK(game_app_start(&app, 180008) == GAME_OK);
    /* Reverse class order to exercise identity binding through the adapter. */
    count = fixture(2, d, 0);
    { VisionDetection swap = d[0]; d[0] = d[3]; d[3] = swap; }
    f = frame(&app, d, count, 2, 180009);
    CHECK(game_app_submit(&app, &f, 180010) == GAME_OK);
    view = snapshot(&app);
    CHECK(view.state == GAME_CLEARED && view.stars == 3 && view.elapsed_ms == 1);
    coherent(&view);
    CHECK(game_app_submit(&app, NULL, 180010) == GAME_BAD_ARGUMENT);
    CHECK(game_app_tick(&app, 180009) == GAME_BAD_TIME);
    puts("PASS delayed old task / original unsolved 077 / no-input timeout / level 2 class binding");
}

int main(void)
{
    test_mapping();
    test_flow();
    test_invalid();
    test_generation_timeout_077();
    printf("PASS game app: %u checks (host only; no board acceptance)\n", checks);
    return 0;
}
