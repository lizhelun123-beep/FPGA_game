/* Minimal offline entry: real C solver, canonical generated templates, fake
 * monotonic timestamps. No detector, OS timer, sleep, GUI or board access. */
#include "game_session.h"
#include "game_config.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(condition) do { \
    ++checks; \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(1); \
    } \
} while (0)

static int near(float a, float b) { return fabsf(a-b) < 0.002f; }
static void same_point(RayPoint a, RayPoint b)
{
    CHECK(near(a.x, b.x)); CHECK(near(a.y, b.y));
}
static SceneObject *find(SceneObject *objects, int count, RayObjectType type)
{
    int i;
    for (i = 0; i < count; ++i) if (objects[i].type == type) return &objects[i];
    CHECK(0);
    return NULL;
}
static const SceneObject *effective(const GameSession *s, RayObjectType type)
{
    int i;
    for (i = 0; i < s->view.object_count; ++i)
        if (s->view.objects[i].type == type) return &s->view.objects[i];
    CHECK(0);
    return NULL;
}
static int reference(GameSession *s, SceneObject *objects)
{
    int i;
    for (i = 0; i < s->level->object_count; ++i) {
        objects[i] = s->level->objects[i].anchor;
        objects[i].source_direction = objects[i].axis;
        objects[i].direction_valid = objects[i].type == RAY_OBJECT_SOURCE;
        /* Bbox size / raw tip must never override fixed model geometry. */
        objects[i].length = 999; objects[i].width = 777;
        objects[i].source_tip = (RayPoint){999, 999};
    }
    return s->level->object_count;
}
static GameStatus submit(GameSession *s, SceneObject *objects, int count,
                         uint64_t sequence, uint64_t captured, uint64_t now)
{
    GameSceneInput input = {GAME_SCENE_VERSION, s->view.generation, sequence,
                            captured, 1, 0, objects, count};
    return game_session_submit(s, &input, now);
}
static void init(GameSession *s, unsigned int id, uint64_t now)
{
    CHECK(game_session_init(s, &game_default_config) == GAME_OK);
    CHECK(s->view.state == GAME_SELECT_LEVEL);
    CHECK(game_session_select(s, id, now) == GAME_OK);
}
static void unsolve(GameSession *s, SceneObject *objects, int count)
{
    if (s->view.level_id == 1) {
        SceneObject *o = find(objects, count, RAY_OBJECT_SOURCE);
        o->source_direction = o->axis = (RayPoint){0, 1};
    } else if (s->view.level_id == 2) {
        SceneObject *o = find(objects, count, RAY_OBJECT_PORTAL_A);
        o->center = (RayPoint){600, 600}; o->axis = (RayPoint){1, 0};
    }
    /* The original 077 layout is already a legal unsolved scene. */
}

static void test_constraints(void)
{
    GameSession s;
    SceneObject objects[GAME_MAX_MODELS];
    SceneObject fixed[GAME_MAX_MODELS];
    RayGameResult fixed_ray;
    const SceneObject *source;
    int count, i;
    init(&s, 1, 0);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 1, 1) == GAME_OK);
    CHECK(s.view.ray.success && s.view.ray.segment_count == 2);
    CHECK(!s.view.ready && s.view.scene_status == GAME_NEED_UNSOLVED);
    memcpy(fixed, s.view.objects, sizeof(fixed));
    fixed_ray = s.view.ray;
    for (i = 0; i < count; ++i) {
        objects[i].center.x += 120; objects[i].center.y += 30;
        objects[i].axis = (RayPoint){0.6f, 0.8f};
    }
    CHECK(submit(&s, objects, count, 2, 2, 2) == GAME_OK);
    CHECK(memcmp(&fixed_ray, &s.view.ray, sizeof(fixed_ray)) == 0);
    find(objects, count, RAY_OBJECT_SOURCE)->source_direction = (RayPoint){0, -2};
    CHECK(submit(&s, objects, count, 3, 3, 3) == GAME_OK);
    for (i = 0; i < count; ++i) {
        same_point(s.view.objects[i].center, fixed[i].center);
        if (fixed[i].type != RAY_OBJECT_SOURCE)
            same_point(s.view.objects[i].axis, fixed[i].axis);
    }
    source = effective(&s, RAY_OBJECT_SOURCE);
    same_point(source->axis, (RayPoint){0, -1});
    same_point(source->source_tip, (RayPoint){source->center.x, source->center.y-36});
    same_point(s.view.ray.segments[0].start,
               (RayPoint){source->source_tip.x, source->source_tip.y-0.03f});
    CHECK(near(source->length, 54) && near(source->width, 40));

    CHECK(game_session_select(&s, 2, 10) == GAME_OK);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 11, 11) == GAME_OK);
    CHECK(s.view.ray.success && s.view.ray.segment_count == 2);
    memcpy(fixed, s.view.objects, sizeof(fixed));
    /* Shuffle identities: portal binding cannot depend on array position. */
    { SceneObject swap = objects[0]; objects[0] = objects[3]; objects[3] = swap; }
    for (i = 0; i < count; ++i) {
        objects[i].center.x += 55; objects[i].center.y += 65;
        objects[i].axis = (RayPoint){0.6f, 0.8f};
        objects[i].source_direction = (RayPoint){1, 0};
    }
    find(objects, count, RAY_OBJECT_PORTAL_B)->axis = (RayPoint){-1, 0};
    CHECK(submit(&s, objects, count, 2, 12, 12) == GAME_OK);
    for (i = 0; i < count; ++i) {
        RayObjectType type = s.view.objects[i].type;
        if (type == RAY_OBJECT_PORTAL_A || type == RAY_OBJECT_PORTAL_B) {
            SceneObject *raw = find(objects, count, type);
            same_point(s.view.objects[i].center, raw->center);
            same_point(s.view.objects[i].axis, raw->axis);
        } else {
            same_point(s.view.objects[i].center, fixed[i].center);
            same_point(s.view.objects[i].axis, fixed[i].axis);
        }
    }
    same_point(effective(&s, RAY_OBJECT_SOURCE)->source_tip, fixed[0].source_tip);

    CHECK(game_session_select(&s, 3, 20) == GAME_OK);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 21, 21) == GAME_OK);
    CHECK(s.view.scene_valid && s.view.ready && !s.view.ray.success);
    CHECK(s.view.ray.termination == RAY_GAME_BOUNDARY);
    CHECK(s.view.ray.segment_count == 3 && s.view.ray.hit_count == 2);
    CHECK(s.view.ray.hit_types[0] == RAY_OBJECT_PORTAL_A);
    CHECK(s.view.ray.hit_types[1] == RAY_OBJECT_MIRROR);
    memcpy(fixed, s.view.objects, sizeof(fixed));
    for (i = 0; i < count; ++i) {
        objects[i].center.x += 30; objects[i].center.y += 40;
        objects[i].axis = objects[i].source_direction = (RayPoint){1, 0};
    }
    CHECK(submit(&s, objects, count, 2, 22, 22) == GAME_OK);
    for (i = 0; i < count; ++i) {
        if (fixed[i].type == RAY_OBJECT_MIRROR) {
            same_point(s.view.objects[i].center, objects[i].center);
            same_point(s.view.objects[i].axis, objects[i].axis);
            /* The finite reflection surface uses the effective pose. */
            CHECK(near(s.view.objects[i].center.x-s.view.objects[i].length/2, objects[i].center.x-70));
        } else {
            same_point(s.view.objects[i].center, fixed[i].center);
            same_point(s.view.objects[i].axis, fixed[i].axis);
        }
    }
    puts("PASS fixed / rotate_only / free, class binding, derived geometry, original 077");
}

/* Construct a solution by moving only the permitted MIRROR. Uses the actual
 * canonical C ray leaving Portal B, then the reflection bisector towards TARGET.
 * This pose is a test input, never a replacement template or initial puzzle. */
static void solve_third(GameSession *s, SceneObject *objects, int count)
{
    RaySegment incoming = s->view.ray.segments[1];
    const SceneObject *target = effective(s, RAY_OBJECT_TARGET);
    SceneObject *mirror = find(objects, count, RAY_OBJECT_MIRROR);
    float dx = incoming.end.x-incoming.start.x;
    float dy = incoming.end.y-incoming.start.y;
    float norm = hypotf(dx, dy);
    RayPoint out;
    CHECK(norm > 1);
    dx /= norm; dy /= norm;
    mirror->center.x = target->center.x;
    mirror->center.y = incoming.start.y+(mirror->center.x-incoming.start.x)*dy/dx;
    out.x = target->center.x-mirror->center.x;
    out.y = target->center.y-mirror->center.y;
    norm = hypotf(out.x, out.y);
    out.x /= norm; out.y /= norm;
    mirror->axis = (RayPoint){dx+out.x, dy+out.y};
}

static void test_flow(void)
{
    GameSession s;
    SceneObject objects[GAME_MAX_MODELS];
    GameSnapshot locked;
    uint64_t generation;
    int count;
    init(&s, 1, 100);
    CHECK(game_session_start(&s, 101) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 102, 102) == GAME_OK);
    CHECK(game_session_start(&s, 102) == GAME_NEED_UNSOLVED);
    CHECK(game_session_tick(&s, 999999) == GAME_OK);
    CHECK(s.view.state == GAME_PREPARING && s.view.elapsed_ms == 0);
    CHECK(s.view.remaining_ms == 180000);
    unsolve(&s, objects, count);
    CHECK(submit(&s, objects, count, 2, 1000000, 1000000) == GAME_OK);
    CHECK(s.view.ready);
    CHECK(game_session_start(&s, 1000000) == GAME_OK);
    CHECK(!s.view.ready && s.view.state == GAME_RUNNING);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 3, 1000001, 1000001) == GAME_OK);
    CHECK(s.view.state == GAME_CLEARED && s.view.stars == 3 && s.view.elapsed_ms == 1);
    locked = s.view;
    CHECK(game_session_tick(&s, 2000000) == GAME_OK);
    CHECK(submit(&s, objects, count, 4, 2000000, 2000000) == GAME_BAD_STATE);
    CHECK(memcmp(&s.view, &locked, sizeof(locked)) == 0);
    generation = s.view.generation;
    CHECK(game_session_select(&s, 3, 2000000) == GAME_OK); /* skip 2 */
    CHECK(s.view.generation == generation+1 && s.view.stars == 0);
    CHECK(s.view.remaining_ms == 180000 && s.view.object_count == 0 && s.view.ray.segment_count == 0);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 2000001, 2000001) == GAME_OK);
    CHECK(game_session_start(&s, 2000001) == GAME_OK);
    solve_third(&s, objects, count);
    CHECK(submit(&s, objects, count, 2, 2060001, 2060001) == GAME_OK);
    CHECK(s.view.state == GAME_CLEARED && s.view.stars == 2);
    CHECK(s.view.ray.segment_count == 3 && s.view.ray.success);
    CHECK(game_session_select(&s, 2, 2060002) == GAME_OK); /* all selectable */
    count = reference(&s, objects);
    unsolve(&s, objects, count);
    CHECK(submit(&s, objects, count, 1, 2060003, 2060003) == GAME_OK);
    CHECK(game_session_start(&s, 2060003) == GAME_OK);
    CHECK(game_session_tick(&s, 2060126) == GAME_OK);
    CHECK(s.view.elapsed_ms == 123 && s.view.remaining_ms == 179877);
    puts("PASS explicit start / preparation / independent timers / skip / locked results / MIRROR-only solution");
}

static void test_boundaries(void)
{
    const uint64_t times[] = {0, 59999, 60000, 119999, 120000, 179999, 180000, 180001};
    const unsigned int stars[] = {3, 3, 2, 2, 1, 1, 0, 0};
    size_t i;
    for (i = 0; i < sizeof(times)/sizeof(times[0]); ++i) {
        GameSession s;
        SceneObject objects[GAME_MAX_MODELS];
        int count;
        init(&s, 1, 0);
        count = reference(&s, objects);
        unsolve(&s, objects, count);
        CHECK(submit(&s, objects, count, 1, 0, 0) == GAME_OK);
        CHECK(game_session_start(&s, 1) == GAME_OK);
        count = reference(&s, objects);
        CHECK(submit(&s, objects, count, 2, 1+times[i], 1+times[i]) ==
              (times[i] >= 180000 ? GAME_BAD_STATE : GAME_OK));
        CHECK(s.view.stars == stars[i]);
        CHECK(s.view.state == (times[i] >= 180000 ? GAME_TIMED_OUT : GAME_CLEARED));
        CHECK(s.view.elapsed_ms == (times[i] >= 180000 ? 180000 : times[i]));
    }
    {
        GameSession s;
        SceneObject objects[GAME_MAX_MODELS];
        int count;
        init(&s, 1, 0);
        count = reference(&s, objects); unsolve(&s, objects, count);
        CHECK(submit(&s, objects, count, 1, 0, 0) == GAME_OK);
        CHECK(game_session_start(&s, 1) == GAME_OK);
        count = reference(&s, objects);
        CHECK(submit(&s, objects, count, 2, 60000, 60010) == GAME_OK);
        CHECK(s.view.stars == 3 && s.view.elapsed_ms == 59999); /* capture, not delivery time */
    }
    puts("PASS exact 60 / 120 / 180 second boundaries and captured-hit scoring");
}

static void test_invalid_inputs(void)
{
    GameSession s;
    SceneObject objects[GAME_MAX_MODELS];
    GameSceneInput in;
    GameSnapshot locked;
    int count, i;
    init(&s, 1, 1000);
    count = reference(&s, objects);
    unsolve(&s, objects, count);
    CHECK(submit(&s, objects, count, 1, 1001, 1001) == GAME_OK);
    CHECK(game_session_start(&s, 1001) == GAME_OK);
    count = reference(&s, objects); /* solved, must not score from any rejected input */
    in = (GameSceneInput){GAME_SCENE_VERSION, s.view.generation, 2, 1002, 0, 0, objects, count};
    CHECK(game_session_submit(&s, &in, 1002) == GAME_INVALID_SCENE);
    CHECK(!s.view.scene_valid && s.view.object_count == 0 && s.view.stars == 0);
    in.valid = 1;
    CHECK(game_session_submit(&s, &in, 1002) == GAME_DUPLICATE_FRAME);
    in.sequence++; in.captured_ms++;
    in.held = 1;
    CHECK(game_session_submit(&s, &in, 1003) == GAME_INVALID_SCENE);
    in.held = 0; in.sequence++; in.captured_ms++;
    CHECK(game_session_submit(&s, &in, 1300) == GAME_STALE_SCENE);
    in.sequence++; in.captured_ms = 1301;
    CHECK(game_session_submit(&s, &in, 1300) == GAME_STALE_SCENE); /* future */
    in.sequence++; in.captured_ms = 1000;
    CHECK(game_session_submit(&s, &in, 1300) == GAME_STALE_SCENE); /* before start */
    in.sequence++; in.captured_ms = 1003;
    CHECK(game_session_submit(&s, &in, 1300) == GAME_STALE_SCENE); /* old capture */
    CHECK(s.view.state == GAME_RUNNING && s.view.stars == 0);
    CHECK(game_session_tick(&s, 1299) == GAME_BAD_TIME);
    /* A solved template must not fill ANY missing observation while playing. */
    for (i = 0; i < count; ++i) {
        SceneObject missing[GAME_MAX_MODELS];
        int j, k = 0;
        for (j = 0; j < count; ++j) if (j != i) missing[k++] = objects[j];
        CHECK(submit(&s, missing, k, 8+(uint64_t)i, 1301+(uint64_t)i, 1301+(uint64_t)i) == GAME_INVALID_SCENE);
        CHECK(s.view.state == GAME_RUNNING && !s.view.stars && !s.view.scene_valid);
    }
    objects[1] = objects[0]; /* duplicated SOURCE, solved template cannot win */
    CHECK(submit(&s, objects, count, 11, 1304, 1304) == GAME_INVALID_SCENE);
    CHECK(s.view.state == GAME_RUNNING && !s.view.stars);
    count = reference(&s, objects);
    find(objects, count, RAY_OBJECT_MIRROR)->type = RAY_OBJECT_WALL; /* class absent from this level */
    CHECK(submit(&s, objects, count, 12, 1305, 1305) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    in = (GameSceneInput){GAME_SCENE_VERSION+1, s.view.generation, 13, 1306, 1, 0, objects, count};
    CHECK(game_session_submit(&s, &in, 1306) == GAME_INVALID_SCENE);
    CHECK(s.view.state == GAME_RUNNING && !s.view.stars);
    /* Missing each class in level 3, including every fixed anchor. Never fill
     * a missing observed class from a solved/fixed template. */
    CHECK(game_session_select(&s, 3, 1400) == GAME_OK);
    count = reference(&s, objects);
    for (i = 0; i < count; ++i) {
        SceneObject missing[GAME_MAX_MODELS];
        int j, k = 0;
        for (j = 0; j < count; ++j) if (j != i) missing[k++] = objects[j];
        CHECK(submit(&s, missing, k, (uint64_t)i+1, 1401+(uint64_t)i, 1401+(uint64_t)i) == GAME_INVALID_SCENE);
        CHECK(!s.view.scene_valid && s.view.object_count == 0);
    }
    objects[4] = objects[3]; /* duplicated PORTAL_B, missing MIRROR */
    CHECK(submit(&s, objects, count, 6, 1406, 1406) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    find(objects, count, RAY_OBJECT_SOURCE)->direction_valid = 0;
    CHECK(submit(&s, objects, count, 7, 1407, 1407) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    find(objects, count, RAY_OBJECT_MIRROR)->center.x = NAN;
    CHECK(submit(&s, objects, count, 8, 1408, 1408) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    find(objects, count, RAY_OBJECT_MIRROR)->axis = (RayPoint){0, 0};
    CHECK(submit(&s, objects, count, 9, 1409, 1409) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    find(objects, count, RAY_OBJECT_MIRROR)->center.x = 1280;
    CHECK(submit(&s, objects, count, 10, 1410, 1410) == GAME_INVALID_SCENE);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 11, 1411, 1411) == GAME_OK);
    CHECK(game_session_tick(&s, 1661) == GAME_OK); /* inclusive max age */
    CHECK(s.view.scene_valid);
    CHECK(game_session_start(&s, 1662) == GAME_STALE_SCENE);
    CHECK(!s.view.ready && s.view.state == GAME_PREPARING);
    in = (GameSceneInput){GAME_SCENE_VERSION, s.view.generation, 12, 1663, 1, 0, objects, count};
    CHECK(game_session_select(&s, 1, 1663) == GAME_OK);
    CHECK(game_session_submit(&s, &in, 1663) == GAME_OLD_GENERATION);
    CHECK(!s.view.scene_valid);
    CHECK(game_session_select(&s, 3, 1664) == GAME_OK); /* revisiting same level also changes generation */
    in.captured_ms = 1665;
    CHECK(game_session_submit(&s, &in, 1665) == GAME_OLD_GENERATION);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 1666, 1666) == GAME_OK);
    CHECK(game_session_start(&s, 1666) == GAME_OK);
    /* Even while RUNNING, a delayed result from a previously selected level
     * cannot replace the current model/ray version or unlock a score. */
    locked = s.view;
    in.captured_ms = 1667;
    CHECK(game_session_submit(&s, &in, 1667) == GAME_OLD_GENERATION);
    CHECK(s.view.scene_sequence == locked.scene_sequence && !s.view.stars);
    CHECK(s.view.state == GAME_RUNNING && s.view.generation == locked.generation);
    CHECK(game_session_tick(&s, 181666) == GAME_OK); /* no input still times out */
    CHECK(s.view.state == GAME_TIMED_OUT && !s.view.stars);
    locked = s.view;
    CHECK(game_session_tick(&s, 999999) == GAME_OK);
    CHECK(memcmp(&locked, &s.view, sizeof(locked)) == 0);
    puts("PASS invalid / held / stale / duplicate / missing / old generation / timeout without frames");
}

static void test_contract_and_budget(void)
{
    GameConfig config = game_default_config;
    GameSession s;
    SceneObject objects[GAME_MAX_MODELS];
    int count;
    CHECK(RAY_GAME_MAX_SEGMENTS == 17);
    CHECK(config.level_count == 3 && config.max_models == 6 && config.render_max_ray_segments == 5);
    CHECK(config.duration_ms == 180000 && config.star_threshold_ms[0] == 60000 && config.star_threshold_ms[1] == 120000);
    CHECK(config.levels[0].objects[0].motion == GAME_ROTATE_ONLY);
    config.version++;
    CHECK(game_session_init(&s, &config) == GAME_BAD_CONFIG);
    config = game_default_config;
    config.levels[2].objects[4].anchor.type = RAY_OBJECT_PORTAL_B;
    CHECK(game_session_init(&s, &config) == GAME_BAD_CONFIG);
    config = game_default_config;
    config.render_max_ray_segments = 1; /* force budget violation, preserve complete physics */
    CHECK(game_session_init(&s, &config) == GAME_OK);
    CHECK(game_session_select(&s, 1, 0) == GAME_OK);
    CHECK(game_session_select(&s, 9, 0) == GAME_UNKNOWN_LEVEL);
    count = reference(&s, objects);
    CHECK(submit(&s, objects, count, 1, 1, 1) == GAME_OK);
    CHECK(s.view.ray.segment_count == 2 && s.view.ray.success && s.view.render_budget_exceeded);
    CHECK(s.view.state == GAME_PREPARING && s.view.scene_status == GAME_NEED_UNSOLVED);
    puts("PASS config validation / complete solver output / separate render budget");
}

int main(void)
{
    test_contract_and_budget();
    test_constraints();
    test_flow();
    test_boundaries();
    test_invalid_inputs();
    printf("PASS game session: %u checks (host only; no board acceptance)\n", checks);
    return 0;
}
