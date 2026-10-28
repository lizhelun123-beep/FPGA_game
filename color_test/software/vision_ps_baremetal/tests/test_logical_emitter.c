/* Authoritative-session checks with real ray_game intersections and controlled
 * test timestamps. No detector, rendering, devices or generated photo anchors. */
#include "game_session.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)

static GameConfig configuration(void)
{
    GameConfig config;
    int i;
    memset(&config, 0, sizeof(config));
    config.version = GAME_CONFIG_VERSION;
    config.coordinate_space = "uncalibrated_preview";
    config.width = 1279; config.height = 719; config.physics_scale = 100;
    config.max_models = GAME_MAX_MODELS;
    config.render_max_ray_segments = 5;
    config.scene_max_age_ms = 250;
    config.duration_ms = 180000;
    config.star_threshold_ms[0] = 60000;
    config.star_threshold_ms[1] = 120000;
    for (i = 0; i < RAY_OBJECT_TYPE_COUNT; ++i)
        config.model_sizes[i] = (RayPoint){20, 20};
    config.model_sizes[RAY_OBJECT_MIRROR] = (RayPoint){140, 12};
    config.level_count = 2;
    for (i = 0; i < config.level_count; ++i) {
        GameLevelConfig *level = &config.levels[i];
        level->id = (unsigned int)i+1;
        level->reference = "sample_photo(1)/fixture.png";
        level->emitter = (GameEmitterConfig){1, {100, 300}, {1, 0}};
        level->object_count = 2;
        level->objects[0].anchor.type = RAY_OBJECT_MIRROR;
        level->objects[0].anchor.center = (RayPoint){500, 300};
        level->objects[0].anchor.axis = (RayPoint){0.70710678f, 0.70710678f};
        level->objects[0].motion = GAME_FREE;
        level->objects[1].anchor.type = RAY_OBJECT_TARGET;
        level->objects[1].anchor.center = (RayPoint){500, 500};
        level->objects[1].anchor.axis = (RayPoint){1, 0};
        level->objects[1].motion = GAME_FREE;
    }
    config.levels[1].emitter = (GameEmitterConfig){1, {300, 100}, {0, 1}};
    return config;
}

static int same_point(RayPoint a, RayPoint b)
{
    return fabsf(a.x-b.x) < 0.001f && fabsf(a.y-b.y) < 0.001f;
}

static void observations(const GameLevelConfig *level, SceneObject *objects)
{
    int i;
    for (i = 0; i < level->object_count; ++i) objects[i] = level->objects[i].anchor;
}

static GameStatus submit(GameSession *session, SceneObject *objects, int count,
                         uint64_t sequence, uint64_t captured, uint64_t now,
                         int held)
{
    GameSceneInput input = {GAME_SCENE_VERSION, session->view.generation,
        sequence, captured, 1, held, objects, count};
    return game_session_submit(session, &input, now);
}

static void test_flow(void)
{
    GameConfig config = configuration();
    GameSession session;
    SceneObject objects[3];
    const SceneObject *source;
    GameSceneInput old;
    CHECK(game_session_init(&session, &config) == GAME_OK);
    CHECK(game_session_select(&session, 1, 1000) == GAME_OK);
    CHECK(game_session_start(&session, 1000) == GAME_INVALID_SCENE);
    observations(session.level, objects);
    objects[0].center.y = 600; /* live unsolved observation, not an anchor */
    CHECK(submit(&session, objects, 2, 1, 1001, 1001, 0) == GAME_OK);
    CHECK(session.view.scene_valid && session.view.ready);
    CHECK(session.view.object_count == 3 && session.level->object_count == 2);
    source = &session.view.objects[2];
    CHECK(source->type == RAY_OBJECT_SOURCE && source->direction_valid);
    CHECK(same_point(source->center, config.levels[0].emitter.point));
    CHECK(same_point(source->source_tip, config.levels[0].emitter.point));
    CHECK(same_point(session.view.ray.segments[0].start, source->source_tip));
    CHECK(game_session_start(&session, 1002) == GAME_OK);
    CHECK(session.view.state == GAME_RUNNING && !session.view.stars);
    /* A duplicate preparation capture cannot win after Start. */
    observations(session.level, objects);
    CHECK(submit(&session, objects, 2, 1, 1001, 1003, 0) == GAME_DUPLICATE_FRAME);
    CHECK(session.view.state == GAME_RUNNING && !session.view.stars);
    CHECK(submit(&session, objects, 2, 2, 1004, 1004, 0) == GAME_OK);
    CHECK(session.view.state == GAME_CLEARED && session.view.stars == 3);
    CHECK(session.view.ray.segment_count == 2 && session.view.ray.success);
    CHECK(session.view.ray.hit_types[0] == RAY_OBJECT_MIRROR);
    CHECK(session.view.ray.hit_types[1] == RAY_OBJECT_TARGET);
    CHECK(same_point(session.view.ray.segments[0].start,
                     config.levels[0].emitter.point));
    CHECK(same_point(session.view.ray.segments[0].end, (RayPoint){500, 300}));
    old = (GameSceneInput){GAME_SCENE_VERSION, session.view.generation, 3,
                           1005, 1, 0, objects, 2};
    CHECK(game_session_select(&session, 2, 1005) == GAME_OK);
    CHECK(session.view.state == GAME_PREPARING && !session.view.object_count);
    CHECK(!session.view.scene_valid && !session.view.stars && !session.view.ray.segment_count);
    CHECK(game_session_submit(&session, &old, 1005) == GAME_OLD_GENERATION);
    observations(session.level, objects);
    CHECK(submit(&session, objects, 2, 1, 1006, 1006, 0) == GAME_OK);
    CHECK(same_point(session.view.ray.segments[0].start,
                     config.levels[1].emitter.point));
    CHECK(game_session_tick(&session, 1256) == GAME_OK && session.view.scene_valid);
    CHECK(game_session_start(&session, 1257) == GAME_STALE_SCENE);
    CHECK(!session.view.object_count && !session.view.ray.segment_count);
    CHECK(game_session_select(&session, 1, 1258) == GAME_OK);
    CHECK(session.view.generation == 3 && !session.view.scene_valid);
}

static void test_observation_gates(void)
{
    GameConfig config = configuration();
    GameSession session;
    SceneObject objects[3];
    CHECK(game_session_init(&session, &config) == GAME_OK);
    CHECK(game_session_select(&session, 1, 0) == GAME_OK);
    observations(session.level, objects);
    CHECK(submit(&session, objects, 1, 1, 1, 1, 0) == GAME_INVALID_SCENE);
    CHECK(game_session_start(&session, 1) == GAME_INVALID_SCENE);
    objects[2] = (SceneObject){0};
    objects[2].type = RAY_OBJECT_SOURCE;
    objects[2].axis = objects[2].source_direction = (RayPoint){1, 0};
    objects[2].direction_valid = 1;
    CHECK(submit(&session, objects, 3, 2, 2, 2, 0) == GAME_INVALID_SCENE);
    objects[0] = objects[2]; /* same count, wrong physical identity */
    CHECK(submit(&session, objects, 2, 3, 3, 3, 0) == GAME_INVALID_SCENE);
    observations(session.level, objects);
    CHECK(submit(&session, objects, 2, 4, 4, 4, 1) == GAME_INVALID_SCENE);
    CHECK(submit(&session, objects, 2, 5, 5, 256, 0) == GAME_STALE_SCENE);
    CHECK(!session.view.scene_valid && !session.view.ray.success);
    objects[0].center.y = 600;
    CHECK(submit(&session, objects, 2, 6, 257, 257, 0) == GAME_OK);
    CHECK(game_session_start(&session, 258) == GAME_OK);
    CHECK(game_session_tick(&session, 180258) == GAME_OK);
    CHECK(session.view.state == GAME_TIMED_OUT && !session.view.stars);
}

static void test_config_and_direct_api(void)
{
    GameConfig config = configuration(), bad;
    GameSession session;
    RayGameResult ray;
    RayPoint origin = {0, 0};
    bad = config; bad.levels[0].emitter.enabled = 2;
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.levels[0].emitter.direction = (RayPoint){0, 0};
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.levels[0].emitter.direction = (RayPoint){2, 0};
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.levels[0].emitter.point.x = NAN;
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.levels[0].objects[0].anchor.type = RAY_OBJECT_SOURCE;
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.levels[0].emitter.enabled = 0; /* legacy still needs SOURCE */
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    bad = config; bad.max_models = 2; /* physical + internal emitter capacity */
    CHECK(game_session_init(&session, &bad) == GAME_BAD_CONFIG);
    CHECK(ray_game_trace_from_emitter(NULL, 0, 1280, 720,
              origin, (RayPoint){1, 0}, &ray) == 0);
    CHECK(ray.termination == RAY_GAME_BOUNDARY && ray.segment_count == 1);
    CHECK(same_point(ray.segments[0].start, origin));
    CHECK(same_point(ray.segments[0].end, (RayPoint){1279, 0}));
    CHECK(ray_game_trace_from_emitter(NULL, 0, 1280, 720,
              (RayPoint){-1, 0}, (RayPoint){1, 0}, &ray) < 0);
    CHECK(ray_game_trace_from_emitter(NULL, 0, 1280, 720,
              origin, (RayPoint){0, 0}, &ray) < 0);
    CHECK(ray_game_trace(NULL, 0, 1280, 720, &ray) == 0);
    CHECK(ray.termination == RAY_GAME_NO_SOURCE && !ray.segment_count);
}

int main(void)
{
    test_flow();
    test_observation_gates();
    test_config_and_direct_api();
    printf("PASS logical emitter: %u checks (host only)\n", checks);
    return 0;
}
