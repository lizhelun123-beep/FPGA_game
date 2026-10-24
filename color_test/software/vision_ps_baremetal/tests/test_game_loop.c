/* Offline boundary tests. No clock reads, sleeps, detector runs or devices. */
#include "game_loop.h"
#include "game_evdev.h"
#include "game_config.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(c) do { ++checks; if (!(c)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); \
} } while (0)

static GameLoopOutput step(GameLoop *loop, uint64_t now, const GameLoopEvent *event,
                            GameStatus expected)
{
    GameLoopOutput out;
    GameSnapshot app;
    CHECK(game_loop_step(loop, now, event, &out) == expected);
    CHECK(out.status == expected);
    CHECK(game_app_snapshot(&loop->app, &app) == GAME_OK);
    CHECK(memcmp(&out.game, &app, sizeof(app)) == 0);
    CHECK(out.menu.start_enabled == (out.game.state == GAME_PREPARING && out.game.ready));
    return out;
}

static GameLoopOutput mouse(GameLoop *loop, uint64_t now, GameMouseKind kind, int x, int y)
{
    GameLoopEvent e;
    e.kind = GAME_LOOP_MOUSE; e.data.mouse = (GameMouseEvent){kind, x, y};
    return step(loop, now, &e, GAME_OK);
}

static GameLoopOutput menu(GameLoop *loop, uint64_t now, GameMenuKind kind,
                            unsigned int id, GameStatus expected)
{
    GameLoopEvent e;
    e.kind = GAME_LOOP_MENU; e.data.menu = (GameMenuAction){kind, id};
    return step(loop, now, &e, expected);
}

static GameLoopOutput click(GameLoop *loop, uint64_t now, GameMenuRect r)
{
    mouse(loop, now, GAME_MOUSE_MOVE, r.x+r.width/2, r.y+r.height/2);
    mouse(loop, now, GAME_MOUSE_LEFT_DOWN, 0, 0);
    return mouse(loop, now, GAME_MOUSE_LEFT_UP, 0, 0);
}

static void init(GameLoop *loop)
{
    CHECK(game_loop_init(loop, &game_default_config, &game_uncalibrated_identity_mapping,
                         &game_default_menu_layout) == GAME_OK);
    CHECK(step(loop, 0, NULL, GAME_OK).game.state == GAME_SELECT_LEVEL);
}

static GameCaptureStamp dispatch(GameLoop *loop, uint64_t now, uint64_t seq, uint64_t captured)
{
    GameLoopEvent e;
    GameLoopOutput out;
    e.kind = GAME_LOOP_DISPATCH;
    e.data.dispatch.sequence = seq; e.data.dispatch.captured_ms = captured;
    out = step(loop, now, &e, GAME_OK);
    CHECK(out.has_stamp && out.stamp.sequence == seq && out.stamp.captured_ms == captured);
    return out.stamp;
}

/* Pose fixtures from generated config, as in the existing adapter tests.
 * Runtime entry never manufactures these observations or solves a scene. */
static int fixture(unsigned int id, VisionDetection *d, int unsolved)
{
    const GameLevelConfig *level = &game_default_config.levels[id-1];
    int i;
    for (i = 0; i < level->object_count; ++i) {
        const SceneObject *o = &level->objects[i].anchor;
        memset(&d[i], 0, sizeof(d[i]));
        d[i].type = (VisionType)o->type; /* canonical enum ordering is checked below */
        d[i].geometry_center_x = o->center.x; d[i].geometry_center_y = o->center.y;
        d[i].axis_x = o->axis.x; d[i].axis_y = o->axis.y;
        d[i].direction_valid = o->type == RAY_OBJECT_SOURCE;
        d[i].source_direction_x = o->axis.x; d[i].source_direction_y = o->axis.y;
        if (id == 1 && unsolved && o->type == RAY_OBJECT_SOURCE) {
            d[i].source_direction_x = d[i].axis_x = 0;
            d[i].source_direction_y = d[i].axis_y = 1;
        }
    }
    return level->object_count; /* original 077 stays unsolved */
}

static GameLoopOutput submit(GameLoop *loop, uint64_t now, GameCaptureStamp stamp,
                              VisionDetection *d, int count, GameStatus expected)
{
    GameLoopEvent e;
    e.kind = GAME_LOOP_DETECTION;
    e.data.detection = (GameDetectionFrame){stamp, 1, 0, d, count};
    return step(loop, now, &e, expected);
}

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
    CHECK(ray_game_trace(scaled, view->object_count, game_default_config.width*scale+1,
                         game_default_config.height*scale+1, &ray) == 0);
    CHECK(ray.success == view->ray.success && ray.termination == view->ray.termination);
    CHECK(ray.segment_count == view->ray.segment_count && ray.hit_count == view->ray.hit_count);
    for (i = 0; i < ray.hit_count; ++i) CHECK(ray.hit_types[i] == view->ray.hit_types[i]);
    for (i = 0; i < ray.segment_count; ++i) {
        CHECK(fabsf(ray.segments[i].start.x/scale-view->ray.segments[i].start.x) < 0.002f);
        CHECK(fabsf(ray.segments[i].start.y/scale-view->ray.segments[i].start.y) < 0.002f);
        CHECK(fabsf(ray.segments[i].end.x/scale-view->ray.segments[i].end.x) < 0.002f);
        CHECK(fabsf(ray.segments[i].end.y/scale-view->ray.segments[i].end.y) < 0.002f);
    }
}

static void test_menu(void)
{
    GameLoop loop;
    GameLoopOutput out;
    GameMenuRect r = game_default_menu_layout.levels[2].rect;
    GameMenuLayout bad = game_default_menu_layout;
    VisionDetection d[VISION_MAX_DETECTIONS];
    GameCaptureStamp stamp;
    GameSnapshot frozen;
    int count;
    init(&loop);
    out = mouse(&loop, 1, GAME_MOUSE_MOVE, -10, 999999);
    CHECK(out.menu.x == 0 && out.menu.y == game_default_menu_layout.height-1);
    CHECK(!out.game.level_id && !out.game.object_count);
    mouse(&loop, 1, GAME_MOUSE_MOVE, r.x+r.width, r.y); /* half-open edge */
    mouse(&loop, 1, GAME_MOUSE_LEFT_DOWN, 0, 0);
    CHECK(mouse(&loop, 1, GAME_MOUSE_LEFT_UP, 0, 0).game.generation == 0);
    mouse(&loop, 2, GAME_MOUSE_MOVE, r.x, r.y);
    out = mouse(&loop, 2, GAME_MOUSE_LEFT_DOWN, 0, 0);
    CHECK(!out.game.generation && !out.action.kind);
    out = mouse(&loop, 2, GAME_MOUSE_LEFT_DOWN, 0, 0); /* held/repeated DOWN */
    CHECK(!out.game.generation && !out.action.kind);
    out = mouse(&loop, 2, GAME_MOUSE_LEFT_UP, 0, 0);
    CHECK(out.action.kind == GAME_MENU_SELECT && out.action.level_id == 3);
    CHECK(out.game.generation == 1 && out.game.state == GAME_PREPARING);
    CHECK(mouse(&loop, 2, GAME_MOUSE_LEFT_UP, 0, 0).game.generation == 1);
    CHECK(click(&loop, 3, game_default_menu_layout.start).game.state == GAME_PREPARING);
    CHECK(!step(&loop, 1000, NULL, GAME_OK).game.elapsed_ms); /* untimed setup */
    menu(&loop, 1000, GAME_MENU_START, 0, GAME_INVALID_SCENE);
    count = fixture(3, d, 0);
    stamp = dispatch(&loop, 1001, UINT64_C(4294967297), 1001);
    out = submit(&loop, 1001, stamp, d, count, GAME_OK);
    CHECK(out.game.ready && out.game.state == GAME_PREPARING && !out.game.stars);
    coherent(&out.game);
    frozen = out.game;
    out = mouse(&loop, 1002, GAME_MOUSE_MOVE, 100, 300);
    CHECK(memcmp(&frozen, &out.game, sizeof(frozen)) == 0); /* mouse cannot move models */
    out = click(&loop, 1002, game_default_menu_layout.start);
    CHECK(out.action.kind == GAME_MENU_START && out.game.state == GAME_RUNNING);
    CHECK(!out.menu.start_enabled && out.game.generation == stamp.generation);
    CHECK(click(&loop, 1003, game_default_menu_layout.start).action.kind == GAME_MENU_NONE);
    /* A select that occurs between press/release cancels the original click. */
    mouse(&loop, 1004, GAME_MOUSE_MOVE, r.x, r.y);
    mouse(&loop, 1004, GAME_MOUSE_LEFT_DOWN, 0, 0);
    menu(&loop, 1004, GAME_MENU_SELECT, 2, GAME_OK);
    out = mouse(&loop, 1004, GAME_MOUSE_LEFT_UP, 0, 0);
    CHECK(out.game.level_id == 2 && out.game.generation == 2 && !out.action.kind);
    /* Entering a button while held cannot select it. */
    mouse(&loop, 1005, GAME_MOUSE_MOVE, 0, 0);
    mouse(&loop, 1005, GAME_MOUSE_LEFT_DOWN, 0, 0);
    mouse(&loop, 1005, GAME_MOUSE_MOVE, r.x, r.y);
    CHECK(!mouse(&loop, 1005, GAME_MOUSE_LEFT_UP, 0, 0).action.kind);
    bad.start = bad.levels[0].rect;
    CHECK(game_loop_init(&loop, &game_default_config, &game_uncalibrated_identity_mapping,
                         &bad) == GAME_BAD_CONFIG);
    puts("PASS menu edges / single click / explicit start / no pose editing / derived menu / layout");
}

static void test_schedule(void)
{
    GameLoop loop;
    GameLoopOutput out;
    GameSnapshot before;
    GameCaptureStamp old, fresh;
    VisionDetection d[VISION_MAX_DETECTIONS];
    int count;
    uint64_t base = UINT64_C(4294967296);
    init(&loop);
    menu(&loop, base, GAME_MENU_SELECT, 1, GAME_OK);
    old = dispatch(&loop, base+1, base+90, base+1);
    click(&loop, base+2, game_default_menu_layout.levels[2].rect);
    count = fixture(3, d, 0);
    fresh = dispatch(&loop, base+3, base+1, base+3);
    out = submit(&loop, base+3, fresh, d, count, GAME_OK);
    before = out.game;
    out = submit(&loop, base+4, old, d, count, GAME_OLD_GENERATION);
    CHECK(memcmp(&before, &out.game, sizeof(before)) == 0);
    CHECK(old.generation == 1 && old.sequence == base+90 && old.captured_ms == base+1);
    CHECK(out.game.generation == 2 && out.game.scene_sequence == base+1);
    click(&loop, base+5, game_default_menu_layout.start);
    out = mouse(&loop, base+1005, GAME_MOUSE_DISCONNECT, 0, 0);
    CHECK(out.game.state == GAME_RUNNING && out.game.elapsed_ms == 1000 && !out.menu.connected);
    CHECK(!out.game.scene_valid); /* freshness still expires during input loss */
    out = step(&loop, base+2005, NULL, GAME_OK);
    CHECK(out.game.elapsed_ms == 2000 && out.game.remaining_ms == 178000);
    out = mouse(&loop, base+3005, GAME_MOUSE_CONNECT, 0, 0);
    CHECK(out.game.state == GAME_RUNNING && out.game.elapsed_ms == 3000 && out.menu.connected);
    /* Held button on reconnect cannot select/reset/pause. */
    mouse(&loop, base+3005, GAME_MOUSE_MOVE, game_default_menu_layout.levels[0].rect.x,
          game_default_menu_layout.levels[0].rect.y);
    mouse(&loop, base+3005, GAME_MOUSE_LEFT_DOWN, 0, 0);
    out = mouse(&loop, base+3005, GAME_MOUSE_LEFT_UP, 0, 0);
    CHECK(out.game.generation == 2 && out.game.elapsed_ms == 3000 && !out.action.kind);
    out = step(&loop, base+180005, NULL, GAME_OK);
    CHECK(out.game.state == GAME_TIMED_OUT && !out.game.remaining_ms && !out.game.stars);
    before = out.game;
    mouse(&loop, base+180006, GAME_MOUSE_DISCONNECT, 0, 0);
    out = mouse(&loop, base+180007, GAME_MOUSE_CONNECT, 0, 0);
    CHECK(memcmp(&before, &out.game, sizeof(before)) == 0);
    /* Reversed time must not consume the release/press latch. */
    { GameLoopEvent e;
      GameMenuInput input = loop.input;
      e.kind = GAME_LOOP_MOUSE; e.data.mouse = (GameMouseEvent){GAME_MOUSE_LEFT_UP, 0, 0};
      step(&loop, base+180006, &e, GAME_BAD_TIME);
      CHECK(memcmp(&input, &loop.input, sizeof(input)) == 0); }
    puts("PASS original dispatch stamp / old result rejection / 64-bit time / idle timeout / input recovery");
}

static void test_score_copy(void)
{
    GameLoop loop;
    GameLoopOutput out, saved;
    VisionDetection d[VISION_MAX_DETECTIONS];
    GameCaptureStamp stamp;
    int count;
    FILE *file;
    init(&loop);
    click(&loop, 0, game_default_menu_layout.levels[0].rect);
    count = fixture(1, d, 0); /* existing solved fixture must not auto-start */
    stamp = dispatch(&loop, 1, 1, 1);
    out = submit(&loop, 1, stamp, d, count, GAME_OK);
    CHECK(!out.menu.start_enabled && out.game.scene_status == GAME_NEED_UNSOLVED);
    CHECK(click(&loop, 1, game_default_menu_layout.start).game.state == GAME_PREPARING);
    menu(&loop, 1, GAME_MENU_START, 0, GAME_NEED_UNSOLVED);
    count = fixture(1, d, 1);
    stamp = dispatch(&loop, 2, 2, 2);
    submit(&loop, 2, stamp, d, count, GAME_OK);
    /* Readiness can expire between press and release. */
    mouse(&loop, 2, GAME_MOUSE_MOVE, game_default_menu_layout.start.x,
          game_default_menu_layout.start.y);
    mouse(&loop, 2, GAME_MOUSE_LEFT_DOWN, 0, 0);
    CHECK(!mouse(&loop, 253, GAME_MOUSE_LEFT_UP, 0, 0).action.kind);
    stamp = dispatch(&loop, 254, 3, 254);
    submit(&loop, 254, stamp, d, count, GAME_OK);
    click(&loop, 255, game_default_menu_layout.start);
    count = fixture(1, d, 0);
    stamp = dispatch(&loop, 60254, 4, 60254);
    out = submit(&loop, 60300, stamp, d, count, GAME_OK);
    CHECK(out.game.state == GAME_CLEARED && out.game.stars == 3);
    CHECK(out.game.elapsed_ms == 59999 && out.game.scene_sequence == 4);
    CHECK(out.game.captured_ms == 60254 && out.game.generation == 1);
    coherent(&out.game);
    saved = out;
    memset(d, 0, sizeof(d));
    step(&loop, 999999, NULL, GAME_OK);
    menu(&loop, 1000000, GAME_MENU_SELECT, 3, GAME_OK);
    CHECK(saved.game.state == GAME_CLEARED && saved.game.stars == 3);
    coherent(&saved.game); /* no pointers into detector/app publication storage */
    file = tmpfile(); CHECK(file != NULL);
    CHECK(game_app_write_view(&loop.app, &saved.game, file) == 0);
    { char text[512]; rewind(file); CHECK(fgets(text, sizeof(text), file) != NULL);
      CHECK(strstr(text, "state=3 level=1 generation=1 sequence=4 captured_ms=60254") != NULL);
      CHECK(strstr(text, "elapsed_ms=59999 remaining_ms=120001 stars=3") != NULL); }
    CHECK(fclose(file) == 0);
    puts("PASS blocked solved/stale start / capture-time score / immutable coherent publication and serializer");
}

static GameMouseBatch feed(GameEvdev *evdev, uint16_t type, uint16_t code, int32_t value, int expected)
{
    GameEvdevEvent event = {0, 0, type, code, value};
    GameMouseBatch batch;
    CHECK(game_evdev_feed(evdev, &event, &batch) == expected);
    return batch;
}

static GameLoopOutput deliver(GameLoop *loop, uint64_t now, const GameMouseBatch *batch)
{
    size_t i;
    GameLoopOutput out = step(loop, now, NULL, GAME_OK);
    for (i = 0; i < batch->count; ++i)
        out = mouse(loop, now, batch->events[i].kind, batch->events[i].x, batch->events[i].y);
    return out;
}

static void put_le(unsigned char *bytes, size_t n, uint64_t value)
{
    size_t i;
    for (i = 0; i < n; ++i) bytes[i] = (unsigned char)(value >> (8*i));
}

static void test_evdev(void)
{
    GameEvdev evdev;
    GameLoop loop;
    GameLoopOutput out;
    GameMouseBatch batch;
    GameEvdevEvent decoded;
    unsigned char bytes[24];
    int layout, i;
    for (layout = 16; layout <= 24; layout += 8) {
        size_t word = layout == 16 ? 4 : 8;
        memset(bytes, 0, sizeof(bytes));
        put_le(bytes, word, layout == 16 ? 123 : UINT64_C(4294967297));
        put_le(bytes+word, word, 999999);
        put_le(bytes+2*word, 2, 2); put_le(bytes+2*word+2, 2, 1);
        put_le(bytes+2*word+4, 4, UINT32_MAX-6); /* signed -7 */
        CHECK(game_evdev_decode((GameEvdevLayout)layout, bytes, (size_t)layout, &decoded));
        CHECK(decoded.value == -7 && decoded.type == 2 && decoded.code == 1);
        CHECK(decoded.seconds == (layout == 16 ? 123 : UINT64_C(4294967297)));
        CHECK(decoded.microseconds == 999999);
        CHECK(!game_evdev_decode((GameEvdevLayout)layout, bytes, (size_t)layout-1, &decoded));
        put_le(bytes+word, word, 1000000);
        CHECK(!game_evdev_decode((GameEvdevLayout)layout, bytes, (size_t)layout, &decoded));
        put_le(bytes+word, word, 0); bytes[word-1] = 128; /* negative seconds */
        CHECK(!game_evdev_decode((GameEvdevLayout)layout, bytes, (size_t)layout, &decoded));
    }
    CHECK(!game_evdev_decode((GameEvdevLayout)20, bytes, 20, &decoded));
    init(&loop);
    CHECK(game_evdev_init(&evdev, game_default_menu_layout.width, game_default_menu_layout.height));
    feed(&evdev, 2, 0, game_default_menu_layout.levels[2].rect.x, 0);
    feed(&evdev, 2, 1, game_default_menu_layout.levels[2].rect.y, 0);
    feed(&evdev, 1, 272, 1, 0);
    feed(&evdev, 1, 272, 2, 0); /* Linux autorepeat is ignored */
    feed(&evdev, 1, 272, 0, 0); /* down/up in SAME report must not be collapsed */
    CHECK(!step(&loop, 1, NULL, GAME_OK).game.generation);
    batch = feed(&evdev, 0, 0, 0, 1);
    CHECK(batch.count == 3 && batch.events[0].kind == GAME_MOUSE_MOVE);
    CHECK(batch.events[1].kind == GAME_MOUSE_LEFT_DOWN && batch.events[2].kind == GAME_MOUSE_LEFT_UP);
    out = deliver(&loop, 2, &batch);
    CHECK(out.game.level_id == 3 && out.game.generation == 1 && out.action.kind == GAME_MENU_SELECT);
    feed(&evdev, 1, 272, 1, 0);
    batch = feed(&evdev, 0, 0, 0, 1); deliver(&loop, 3, &batch);
    feed(&evdev, 1, 272, 1, 0);
    batch = feed(&evdev, 0, 0, 0, 1);
    CHECK(deliver(&loop, 4, &batch).game.generation == 1);
    feed(&evdev, 1, 272, 0, 0);
    batch = feed(&evdev, 0, 0, 0, 1);
    CHECK(deliver(&loop, 5, &batch).game.generation == 2);
    CHECK(feed(&evdev, 2, 8, 1, 0).count == 0); /* wheel ignored */
    feed(&evdev, 2, 0, INT32_MIN, 0); feed(&evdev, 2, 1, INT32_MAX, 0);
    batch = feed(&evdev, 0, 0, 0, 1); out = deliver(&loop, 6, &batch);
    CHECK(out.menu.x == 0 && out.menu.y == game_default_menu_layout.height-1);
    feed(&evdev, 2, 0, 123, 0); /* unfinished motion must roll back on loss */
    feed(&evdev, 1, 272, 1, 0);
    batch = feed(&evdev, 0, 3, 0, 1); /* SYN_DROPPED, immediate cancellation */
    CHECK(batch.count == 1 && batch.events[0].kind == GAME_MOUSE_DISCONNECT);
    CHECK(evdev.x == 0 && evdev.y == game_default_menu_layout.height-1);
    deliver(&loop, 7, &batch);
    CHECK(feed(&evdev, 0, 0, 0, 0).count == 0);
    CHECK(feed(&evdev, 1, 272, 0, 0).count == 0);
    game_evdev_connection(&evdev, 1, &batch); deliver(&loop, 8, &batch);
    feed(&evdev, 1, 272, 0, 0);
    batch = feed(&evdev, 0, 0, 0, 1); deliver(&loop, 8, &batch);
    for (i = 0; i < GAME_EVDEV_BATCH_MAX; ++i) feed(&evdev, 1, 272, i%2, 0);
    batch = feed(&evdev, 1, 272, 1, 1); /* bounded queue overflow cancels */
    CHECK(batch.count == 1 && batch.events[0].kind == GAME_MOUSE_DISCONNECT);
    out = deliver(&loop, 9, &batch);
    CHECK(out.game.generation == 2 && !out.menu.connected);
    puts("PASS explicit LE32/LE64 decode / signed REL / SYN ordering / key repeats / dropped reports / overflow");
}

int main(void)
{
    CHECK((int)VISION_SOURCE == (int)RAY_OBJECT_SOURCE && (int)VISION_TARGET == (int)RAY_OBJECT_TARGET);
    CHECK((int)VISION_MIRROR == (int)RAY_OBJECT_MIRROR && (int)VISION_PORTAL_A == (int)RAY_OBJECT_PORTAL_A);
    CHECK((int)VISION_PORTAL_B == (int)RAY_OBJECT_PORTAL_B && (int)VISION_WALL == (int)RAY_OBJECT_WALL);
    test_menu(); test_schedule(); test_score_copy(); test_evdev();
    printf("PASS game input/loop: %u checks (simulated time; host only)\n", checks);
    return 0;
}
