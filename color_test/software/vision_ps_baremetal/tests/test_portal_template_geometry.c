/* Real solver tests for explicit mapped-template dimensions, independent of
 * any current photo anchors. This is not a camera or millimetre calibration. */
#include "game_session.h"

#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)
static int near(float a, float b) { return fabsf(a-b) < 0.002f; }

static GameConfig configuration(int use_template)
{
    GameConfig config;
    GameLevelConfig *level;
    int i;
    memset(&config, 0, sizeof(config));
    config.version = GAME_CONFIG_VERSION;
    config.coordinate_space = "uncalibrated_preview";
    config.width = 1279; config.height = 719; config.physics_scale = 100;
    config.max_models = 6; config.render_max_ray_segments = 5;
    config.scene_max_age_ms = 250; config.duration_ms = 180000;
    config.star_threshold_ms[0] = 60000; config.star_threshold_ms[1] = 120000;
    for (i = 0; i < RAY_OBJECT_TYPE_COUNT; ++i)
        config.model_sizes[i] = (RayPoint){20, 20};
    config.level_count = 1;
    level = &config.levels[0];
    level->id = 1; level->reference = "sample_photo(1)/fixture.png";
    level->emitter = (GameEmitterConfig){1, {100, 350}, {1, 0}};
    level->object_count = 3;
    level->objects[0].anchor.type = RAY_OBJECT_TARGET;
    level->objects[0].anchor.center = (RayPoint){1000, 375};
    level->objects[0].anchor.axis = (RayPoint){1, 0};
    level->objects[0].motion = GAME_FREE;
    for (i = 1; i < 3; ++i) {
        level->objects[i].anchor.type = i == 1 ? RAY_OBJECT_PORTAL_A : RAY_OBJECT_PORTAL_B;
        level->objects[i].anchor.center = (RayPoint){i == 1 ? 500.0f : 800.0f, 300};
        level->objects[i].anchor.axis = (RayPoint){0, 1};
        level->objects[i].motion = GAME_FREE;
        level->objects[i].use_template_geometry = use_template;
    }
    return config;
}

static void observations(const GameConfig *config, SceneObject *objects)
{
    int i;
    for (i = 0; i < 3; ++i) objects[i] = config->levels[0].objects[i].anchor;
    objects[1].length = 120; objects[1].width = 40;
    objects[2].length = 180; objects[2].width = 60;
}

static GameStatus submit(GameSession *session, SceneObject *objects,
                         uint64_t sequence)
{
    GameSceneInput input = {GAME_SCENE_VERSION, session->view.generation,
                            sequence, sequence, 1, 0, objects, 3};
    return game_session_submit(session, &input, sequence);
}

static void test_shared_geometry(void)
{
    GameConfig config = configuration(1);
    GameSession session;
    SceneObject objects[3];
    CHECK(game_session_init(&session, &config) == GAME_OK);
    CHECK(game_session_select(&session, 1, 0) == GAME_OK);
    observations(&config, objects);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(session.view.scene_valid && session.view.ray.success);
    CHECK(near(session.view.objects[1].length, 120) && near(session.view.objects[1].width, 40));
    CHECK(near(session.view.objects[2].length, 180) && near(session.view.objects[2].width, 60));
    CHECK(session.view.ray.segment_count == 2 && session.view.ray.hit_count == 2);
    CHECK(session.view.ray.hit_types[0] == RAY_OBJECT_PORTAL_A);
    CHECK(session.view.ray.hit_types[1] == RAY_OBJECT_TARGET);
    /* First entry uses A's width. Its normalized local position is mapped to
     * B's different length; the second ray starts at B's actual side + epsilon. */
    CHECK(near(session.view.ray.segments[0].end.x, 480));
    CHECK(near(session.view.ray.segments[0].end.y, 350));
    CHECK(near(session.view.ray.segments[1].start.x, 830.01f));
    CHECK(near(session.view.ray.segments[1].start.y, 375));
    CHECK(near(session.view.ray.segments[1].end.x, 990));
    CHECK(near(session.view.ray.segments[1].end.y, 375));
    /* Update all effective dimensions and rays in the same submission. */
    objects[1].width = 60;
    CHECK(submit(&session, objects, 2) == GAME_OK);
    CHECK(near(session.view.objects[1].width, 60));
    CHECK(near(session.view.ray.segments[0].end.x, 470));
}

static void test_fixed_size_default(void)
{
    GameConfig config = configuration(0);
    GameSession session;
    SceneObject objects[3];
    CHECK(game_session_init(&session, &config) == GAME_OK);
    CHECK(game_session_select(&session, 1, 0) == GAME_OK);
    observations(&config, objects);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[1].length, 20) && near(session.view.objects[1].width, 20));
    CHECK(near(session.view.objects[2].length, 20) && near(session.view.objects[2].width, 20));
    CHECK(session.view.ray.segment_count == 1 && !session.view.ray.success);
    CHECK(session.view.ray.termination == RAY_GAME_BOUNDARY);
    CHECK(near(session.view.ray.segments[0].end.x, 1279));
    CHECK(near(session.view.ray.segments[0].end.y, 350));
    /* Old rules do not start trusting dimensions just because the observation
     * happens to include some; even unusable bbox-era sizes stay irrelevant. */
    objects[1].length = NAN; objects[1].width = INFINITY;
    CHECK(submit(&session, objects, 2) == GAME_OK);
    CHECK(near(session.view.objects[1].length, 20) && near(session.view.objects[1].width, 20));
}

static void test_reject_bad_templates(void)
{
    static const float bad_sizes[] = {0, -1, NAN, INFINITY, FLT_MAX};
    GameConfig config = configuration(1), invalid;
    GameSession session;
    SceneObject objects[3];
    unsigned int i;
    CHECK(game_session_init(&session, &config) == GAME_OK);
    CHECK(game_session_select(&session, 1, 0) == GAME_OK);
    for (i = 0; i < sizeof(bad_sizes)/sizeof(bad_sizes[0]); ++i) {
        observations(&config, objects);
        objects[1].length = bad_sizes[i];
        CHECK(submit(&session, objects, 2*i+1) == GAME_INVALID_SCENE);
        CHECK(!session.view.scene_valid && !session.view.object_count && !session.view.ray.segment_count);
        observations(&config, objects);
        objects[2].width = bad_sizes[i];
        CHECK(submit(&session, objects, 2*i+2) == GAME_INVALID_SCENE);
        CHECK(!session.view.scene_valid && !session.view.object_count && !session.view.ray.segment_count);
    }
    invalid = config; invalid.levels[0].objects[0].use_template_geometry = 1;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[1].use_template_geometry = 2;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[1].motion = GAME_FIXED;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[1].motion = GAME_ROTATE_ONLY;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
}

int main(void)
{
    test_shared_geometry();
    test_fixed_size_default();
    test_reject_bad_templates();
    printf("PASS Portal template geometry: %u checks (host only)\n", checks);
    return 0;
}
