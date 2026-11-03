/* Directed host checks for dimensions recovered from measured marker
 * templates. No detector/camera, CAD data or millimetre-accuracy claim. */
#include "game_session.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)
static int near(float a, float b) { return fabsf(a-b) < 0.002f; }

static GameConfig configuration(int mode, RayPoint emission_point)
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
    config.model_sizes[RAY_OBJECT_MIRROR] = (RayPoint){140, 12};
    config.level_count = 1;
    level = &config.levels[0];
    level->id = 1; level->reference = "sample_photo(1)/fixture.png";
    level->emitter = (GameEmitterConfig){1, {0, 0}, {1, 0}};
    level->emitter.point = emission_point;
    level->object_count = 3;
    level->objects[0].anchor.type = RAY_OBJECT_MIRROR;
    level->objects[0].anchor.center = (RayPoint){500, 300};
    level->objects[0].anchor.axis = (RayPoint){0, 1};
    level->objects[1].anchor.type = RAY_OBJECT_TARGET;
    level->objects[1].anchor.center = (RayPoint){1100, 100};
    level->objects[1].anchor.axis = (RayPoint){1, 0};
    level->objects[2].anchor.type = RAY_OBJECT_WALL;
    level->objects[2].anchor.center = (RayPoint){800, 600};
    level->objects[2].anchor.axis = (RayPoint){0, 1};
    for (i = 0; i < 3; ++i) {
        level->objects[i].motion = GAME_FREE;
        level->objects[i].use_template_geometry = mode;
    }
    return config;
}

static void observations(const GameConfig *config, SceneObject *objects)
{
    int i;
    for (i = 0; i < 3; ++i) objects[i] = config->levels[0].objects[i].anchor;
    /* Black-dot centers project 54 mm to 108 px; effective reflection is
     * 46 mm. Session receives the final 92 px, without another size ratio. */
    objects[0].length = 108.0f*46.0f/54.0f;
    objects[0].width = 50;
    /* Wall white centers project 61 mm to 122 px. The whole body is 80x25 mm. */
    objects[2].length = 122.0f*80.0f/61.0f;
    objects[2].width = 122.0f*25.0f/61.0f;
    objects[1].length = objects[1].width = 30.0f*2.0f;
}

static GameStatus submit(GameSession *session, SceneObject *objects, uint64_t seq)
{
    GameSceneInput input = {GAME_SCENE_VERSION, session->view.generation,
                            seq, seq, 1, 0, objects, 3};
    return game_session_submit(session, &input, seq);
}

static void init(GameSession *session, const GameConfig *config)
{
    CHECK(game_session_init(session, config) == GAME_OK);
    CHECK(game_session_select(session, 1, 0) == GAME_OK);
}

static void test_finite_mirror(void)
{
    GameConfig config = configuration(GAME_GEOMETRY_MARKER_TEMPLATE, (RayPoint){100, 345});
    GameSession session;
    SceneObject objects[3];
    init(&session, &config);
    observations(&config, objects);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[0].length, 92));
    CHECK(near(session.view.objects[0].center.y-session.view.objects[0].length/2, 254));
    CHECK(near(session.view.objects[0].center.y+session.view.objects[0].length/2, 346));
    CHECK(session.view.ray.segment_count == 2 && session.view.ray.hit_count == 1);
    CHECK(session.view.ray.hit_types[0] == RAY_OBJECT_MIRROR);
    CHECK(near(session.view.ray.segments[0].end.x, 500));
    CHECK(near(session.view.ray.segments[0].end.y, 345));
    CHECK(near(session.view.ray.segments[1].end.x, 0));
    config.levels[0].emitter.point.y = 347;
    init(&session, &config);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(session.view.ray.segment_count == 1 && !session.view.ray.hit_count);
    CHECK(near(session.view.ray.segments[0].end.x, 1279));
    config = configuration(GAME_GEOMETRY_CONFIGURED, (RayPoint){100, 347});
    init(&session, &config);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[0].length, 140));
    CHECK(session.view.ray.segment_count == 2 && session.view.ray.hit_count == 1);
}

static void test_wall_and_target(void)
{
    GameConfig config = configuration(GAME_GEOMETRY_MARKER_TEMPLATE, (RayPoint){100, 660});
    GameSession session;
    SceneObject objects[3];
    init(&session, &config);
    observations(&config, objects);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[2].length, 160) && near(session.view.objects[2].width, 50));
    CHECK(session.view.ray.termination == RAY_GAME_WALL);
    CHECK(near(session.view.ray.segments[0].end.x, 775));
    CHECK(near(session.view.ray.segments[0].end.y, 660));
    config.levels[0].emitter.point.y = 681;
    init(&session, &config);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(session.view.ray.termination == RAY_GAME_BOUNDARY && !session.view.ray.hit_count);
    config.levels[0].emitter.point.y = 100;
    init(&session, &config);
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[1].length, 60) && near(session.view.objects[1].width, 60));
    CHECK(session.view.ray.termination == RAY_GAME_TARGET && session.view.ray.success);
    CHECK(near(session.view.ray.segments[0].end.x, 1070));
    objects[1].width = 59.99f;
    CHECK(submit(&session, objects, 2) == GAME_INVALID_SCENE);
    CHECK(!session.view.scene_valid && !session.view.object_count && !session.view.ray.segment_count);
    observations(&config, objects);
    objects[0].length = 0;
    CHECK(submit(&session, objects, 3) == GAME_INVALID_SCENE);
    observations(&config, objects);
    objects[2].width = NAN;
    CHECK(submit(&session, objects, 4) == GAME_INVALID_SCENE);
    /* Default configured geometry still ignores supplied sizes; it cannot
     * opt into marker geometry just because some bbox numbers are present. */
    config = configuration(GAME_GEOMETRY_CONFIGURED, (RayPoint){100, 100});
    init(&session, &config);
    observations(&config, objects);
    objects[1].width = 59.99f;
    CHECK(submit(&session, objects, 1) == GAME_OK);
    CHECK(near(session.view.objects[1].length, 20) && near(session.view.objects[1].width, 20));
    /* Existing float circle intersection at this 100000-unit distance returns
     * 1089.99768 px; account for its rounding without changing solver rules. */
    CHECK(fabsf(session.view.ray.segments[0].end.x-1090) < 0.005f);
}

static void test_configuration_guards(void)
{
    GameConfig config = configuration(GAME_GEOMETRY_MARKER_TEMPLATE, (RayPoint){100, 300}), invalid;
    GameSession session;
    invalid = config; invalid.levels[0].objects[0].use_template_geometry = GAME_GEOMETRY_PORTAL_TEMPLATE;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[0].motion = GAME_FIXED;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[1].motion = GAME_ROTATE_ONLY;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].objects[0].use_template_geometry = 3;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid = config; invalid.levels[0].emitter.enabled = 0;
    invalid.levels[0].objects[2].anchor.type = RAY_OBJECT_SOURCE;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid.levels[0].objects[2].use_template_geometry = GAME_GEOMETRY_CONFIGURED;
    CHECK(game_session_init(&session, &invalid) == GAME_OK);
    invalid = config;
    invalid.levels[0].objects[0].anchor.type = RAY_OBJECT_PORTAL_A;
    invalid.levels[0].objects[2].anchor.type = RAY_OBJECT_PORTAL_B;
    CHECK(game_session_init(&session, &invalid) == GAME_BAD_CONFIG);
    invalid.levels[0].objects[0].use_template_geometry = GAME_GEOMETRY_PORTAL_TEMPLATE;
    invalid.levels[0].objects[2].use_template_geometry = GAME_GEOMETRY_PORTAL_TEMPLATE;
    CHECK(game_session_init(&session, &invalid) == GAME_OK);
}

int main(void)
{
    test_finite_mirror();
    test_wall_and_target();
    test_configuration_guards();
    printf("PASS marker template geometry: %u checks (host only)\n", checks);
    return 0;
}
