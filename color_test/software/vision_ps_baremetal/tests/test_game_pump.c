/* Fully simulated clock/read/wait/completion; no sleeps or Linux syscalls. */
#include "game_pump.h"
#include "game_config.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;
#define CHECK(c) do { ++checks; if (!(c)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); \
} } while (0)
typedef struct { GameReadResult result; unsigned char bytes[GAME_PUMP_READ_BYTES]; } Read;
typedef struct {
    uint64_t now, until, advance;
    GamePumpConnection link;
    Read reads[16];
    size_t count, next, calls, waits, publications, resyncs;
    int flood, synced, ready, scrub, wait_interrupt, result_error, repeat_result;
    GameDetectionFrame frame;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    GamePump *pump;
    GamePumpOutput saved;
} Fake;
static void put(unsigned char *p, size_t n, uint64_t v)
{
    size_t i;
    for (i = 0; i < n; ++i) p[i] = (unsigned char)(v >> (8*i));
}
static size_t record(unsigned char *p, GameEvdevLayout layout, unsigned int type,
                     unsigned int code, int32_t value)
{
    size_t off = (size_t)layout-8;
    memset(p, 0, (size_t)layout);
    put(p+off, 2, type); put(p+off+2, 2, code); put(p+off+4, 4, (uint32_t)value);
    return (size_t)layout;
}
static uint64_t now_ms(void *ctx) { return ((Fake *)ctx)->now; }
static GamePumpConnection connection(void *ctx) { return ((Fake *)ctx)->link; }
static GameReadResult read_bytes(void *ctx, unsigned char *bytes, size_t capacity)
{
    Fake *f = ctx;
    ++f->calls; f->now += f->advance;
    if (f->flood == 2) return (GameReadResult){GAME_READ_INTERRUPTED, 0};
    if (f->flood == 1) {
        size_t n = record(bytes, f->pump->stream.layout, 2, 8, 1); /* wheel flood */
        n += record(bytes+n, f->pump->stream.layout, 0, 0, 0);
        return (GameReadResult){GAME_READ_DATA, n};
    }
    if (f->next < f->count) {
        Read *r = &f->reads[f->next++];
        CHECK(r->result.count <= capacity);
        memcpy(bytes, r->bytes, r->result.count);
        return r->result;
    }
    return (GameReadResult){GAME_READ_AGAIN, 0};
}
static GameWaitStatus wait_until(void *ctx, uint64_t deadline)
{
    Fake *f = ctx;
    CHECK(deadline > f->now);
    ++f->waits;
    if (f->wait_interrupt) { ++f->now; return GAME_WAIT_INTERRUPTED; }
    f->now = deadline < f->until ? deadline : f->until;
    return GAME_WAIT_READY;
}
static int resync(void *ctx) { Fake *f = ctx; ++f->resyncs; return f->synced; }
static int result(void *ctx, GameDetectionFrame *frame)
{
    Fake *f = ctx;
    if (f->result_error) return -1;
    if (!f->ready) {
        /* Simulate a producer reusing the borrowed array on the next poll. */
        if (f->scrub) memset(f->detections, 0, sizeof(f->detections));
        return 0;
    }
    *frame = f->frame; f->ready = f->repeat_result;
    return 1;
}
static int stopping(void *ctx) { Fake *f = ctx; return f->now >= f->until; }
static void coherent(const GameSnapshot *view)
{
    SceneObject objects[GAME_MAX_MODELS];
    RayGameResult ray;
    float scale = game_default_config.physics_scale;
    int i;
    CHECK(view->scene_valid);
    for (i = 0; i < view->object_count; ++i) {
        objects[i] = view->objects[i];
        objects[i].center.x *= scale; objects[i].center.y *= scale;
        objects[i].source_tip.x *= scale; objects[i].source_tip.y *= scale;
        objects[i].length *= scale; objects[i].width *= scale;
    }
    CHECK(!ray_game_trace(objects, view->object_count, game_default_config.width*scale+1,
                          game_default_config.height*scale+1, &ray));
    CHECK(ray.success == view->ray.success && ray.segment_count == view->ray.segment_count);
    CHECK(ray.termination == view->ray.termination && ray.hit_count == view->ray.hit_count);
    for (i = 0; i < ray.hit_count; ++i) CHECK(ray.hit_types[i] == view->ray.hit_types[i]);
    for (i = 0; i < ray.segment_count; ++i) {
        CHECK(fabsf(ray.segments[i].start.x/scale-view->ray.segments[i].start.x) < 0.002f);
        CHECK(fabsf(ray.segments[i].end.y/scale-view->ray.segments[i].end.y) < 0.002f);
    }
}
static void publish(void *ctx, const GamePumpOutput *output)
{
    Fake *f = ctx;
    GameSnapshot current;
    CHECK(game_app_snapshot(&f->pump->loop->app, &current) == GAME_OK);
    CHECK(!memcmp(&current, &output->view.game, sizeof(current)));
    CHECK(output->view.menu.start_enabled == (current.state == GAME_PREPARING && current.ready));
    CHECK(output->reads <= GAME_PUMP_READ_MAX && output->results <= GAME_PUMP_RESULT_MAX);
    f->saved = *output; ++f->publications;
}
static void init(Fake *f, GameLoop *loop, GamePump *p, GameEvdevLayout layout)
{
    GamePumpIO io = {GAME_PUMP_IO_VERSION, f, now_ms, connection, read_bytes,
                    wait_until, resync, result, stopping, publish};
    memset(f, 0, sizeof(*f)); f->pump = p;
    CHECK(game_loop_init(loop, &game_default_config, &game_uncalibrated_identity_mapping,
                         &game_default_menu_layout) == GAME_OK);
    CHECK(game_pump_init(p, loop, &game_default_pump_config, layout, &io));
}
static GameLoopOutput menu(GamePump *p, GameMenuKind kind, unsigned int id)
{
    GameLoopEvent e;
    GameLoopOutput out;
    e.kind = GAME_LOOP_MENU; e.data.menu = (GameMenuAction){kind, id};
    CHECK(game_pump_event(p, &e, &out) == GAME_OK);
    return out;
}
static GameCaptureStamp dispatch(GamePump *p, uint64_t seq)
{
    GameLoopEvent e;
    GameLoopOutput out;
    e.kind = GAME_LOOP_DISPATCH;
    e.data.dispatch.sequence = seq; e.data.dispatch.captured_ms = now_ms(p->io.context);
    CHECK(game_pump_event(p, &e, &out) == GAME_OK && out.has_stamp);
    return out.stamp;
}
static void fixture(Fake *f, unsigned int level, GameCaptureStamp stamp, int unsolved)
{
    const GameLevelConfig *l = &game_default_config.levels[level-1];
    int i;
    memset(f->detections, 0, sizeof(f->detections));
    for (i = 0; i < l->object_count; ++i) {
        const SceneObject *o = &l->objects[i].anchor;
        VisionDetection *d = &f->detections[i];
        d->type = (VisionType)o->type;
        d->geometry_center_x = o->center.x; d->geometry_center_y = o->center.y;
        d->axis_x = d->source_direction_x = o->axis.x;
        d->axis_y = d->source_direction_y = o->axis.y;
        d->direction_valid = o->type == RAY_OBJECT_SOURCE;
        if (level == 1 && unsolved && d->direction_valid) {
            d->axis_x = d->source_direction_x = 0;
            d->axis_y = d->source_direction_y = 1;
        }
    }
    f->frame = (GameDetectionFrame){stamp, 1, 0, f->detections, l->object_count};
    f->ready = 1;
}
static GamePumpOutput once(Fake *f)
{
    GamePumpOutput out;
    f->until = f->now; /* stop AFTER one full batch; no artificial wait */
    CHECK(game_pump_once(f->pump, &out) == GAME_PUMP_STOP);
    return out;
}
static void queue(Fake *f, const unsigned char *bytes, size_t count, GameReadStatus status)
{
    Read *r;
    CHECK(f->count < 16 && count <= GAME_PUMP_READ_BYTES);
    r = &f->reads[f->count++]; r->result = (GameReadResult){status, count};
    if (count) memcpy(r->bytes, bytes, count);
}
static void wire(Fake *f, unsigned int type, unsigned int code, int value)
{
    unsigned char bytes[24];
    size_t n = record(bytes, f->pump->stream.layout, type, code, value);
    queue(f, bytes, n, GAME_READ_DATA);
}
static void reset_reads(Fake *f) { f->count = f->next = 0; }
typedef struct { GameMouseEvent events[64]; size_t count; } Sink;
static void collect(void *ctx, const GameMouseBatch *batch)
{
    Sink *s = ctx;
    CHECK(s->count+batch->count <= 64);
    memcpy(s->events+s->count, batch->events, batch->count*sizeof(batch->events[0]));
    s->count += batch->count;
}
static void test_stream(GameEvdevLayout layout)
{
    GameEvdevStream stream;
    unsigned char bytes[192];
    size_t n = 0, split;
    n += record(bytes+n, layout, 2, 0, 123);
    n += record(bytes+n, layout, 1, 272, 1);
    n += record(bytes+n, layout, 1, 272, 0);
    n += record(bytes+n, layout, 0, 0, 0);
    for (split = 1; split < (size_t)layout; ++split) {
        Sink sink = {{ {0,0,0} }, 0};
        CHECK(game_evdev_stream_init(&stream, layout, 1280, 800));
        game_evdev_stream_connection(&stream, 1, collect, &sink); sink.count = 0;
        CHECK(game_evdev_stream_feed(&stream, bytes, split, collect, &sink));
        CHECK(!sink.count && stream.used == split);
        CHECK(game_evdev_stream_feed(&stream, bytes+split, n-split-(size_t)layout, collect, &sink));
        CHECK(!sink.count); /* full ordinary records still await SYN_REPORT */
        CHECK(game_evdev_stream_feed(&stream, bytes+n-(size_t)layout, (size_t)layout, collect, &sink));
        CHECK(sink.count == 3 && sink.events[0].x == 123);
        CHECK(sink.events[1].kind == GAME_MOUSE_LEFT_DOWN && sink.events[2].kind == GAME_MOUSE_LEFT_UP);
        CHECK(game_evdev_stream_feed(&stream, bytes, n, collect, &sink));
        CHECK(sink.count == 6 && sink.events[3].x == 246 && !stream.used);
    }
    { Sink sink = {{ {0,0,0} }, 0};
      size_t word = layout == GAME_EVDEV_LE32 ? 4 : 8;
      CHECK(game_evdev_stream_init(&stream, layout, 1280, 800));
      game_evdev_stream_connection(&stream, 1, collect, &sink); sink.count = 0;
      record(bytes, layout, 1, 272, 1); put(bytes+word, word, 1000000);
      CHECK(game_evdev_stream_feed(&stream, bytes, (size_t)layout, collect, &sink));
      CHECK(sink.count == 1 && sink.events[0].kind == GAME_MOUSE_DISCONNECT);
      CHECK(!game_evdev_stream_recover(&stream, collect, &sink));
      record(bytes, layout, 0, 0, 0);
      record(bytes+(size_t)layout, layout, 0, 3, 0); /* another drop after REPORT */
      CHECK(game_evdev_stream_feed(&stream, bytes, 2*(size_t)layout, collect, &sink));
      CHECK(!game_evdev_stream_can_resync(&stream));
      CHECK(!game_evdev_stream_recover(&stream, collect, &sink));
      CHECK(game_evdev_stream_feed(&stream, bytes, (size_t)layout, collect, &sink));
      CHECK(game_evdev_stream_can_resync(&stream));
      CHECK(game_evdev_stream_recover(&stream, collect, &sink));
      CHECK(sink.count == 2 && sink.events[1].kind == GAME_MOUSE_CONNECT); }
    puts("PASS fragmented LE32/LE64 streams / multiple records / report-only delivery");
}
static void test_loss(GameEvdevLayout layout)
{
    Fake f; GameLoop loop; GamePump p; GamePumpOutput out;
    GameReadStatus failures[] = {GAME_READ_EOF, GAME_READ_DISCONNECTED, GAME_READ_ERROR};
    size_t k;
    for (k = 0; k < sizeof(failures)/sizeof(failures[0]); ++k) {
        unsigned char bytes[24];
        init(&f, &loop, &p, layout); f.link = (GamePumpConnection){1, 1};
        wire(&f, 1, 272, 0); wire(&f, 0, 0, 0); once(&f); reset_reads(&f);
        wire(&f, 2, 0, game_default_menu_layout.levels[0].rect.x);
        wire(&f, 2, 1, game_default_menu_layout.levels[0].rect.y);
        wire(&f, 1, 272, 1); wire(&f, 0, 0, 0); out = once(&f);
        CHECK(out.view.menu.left_down); reset_reads(&f);
        wire(&f, 1, 272, 0); /* unfinished release must be discarded */
        record(bytes, layout, 2, 0, 999); queue(&f, bytes, 7, GAME_READ_DATA);
        queue(&f, NULL, 0, failures[k]); out = once(&f);
        CHECK(out.read_status == failures[k] && !p.stream.used);
        CHECK(!out.view.menu.connected && !out.view.menu.left_down && !out.view.game.generation);
        { size_t calls = f.calls; once(&f); CHECK(calls == f.calls); } /* fault latched */
        reset_reads(&f); ++f.link.epoch; /* new fd, even without observed unplug */
        wire(&f, 1, 272, 1); wire(&f, 1, 272, 0); wire(&f, 0, 0, 0);
        out = once(&f); CHECK(!out.view.game.generation && !p.stream.used);
        reset_reads(&f); wire(&f, 1, 272, 1); wire(&f, 1, 272, 0); wire(&f, 0, 0, 0);
        out = once(&f); CHECK(out.view.game.generation == 1);
    }
    init(&f, &loop, &p, layout); f.link = (GamePumpConnection){1, 1};
    f.synced = 1; /* even successful backend resync cannot skip drain boundary */
    wire(&f, 1, 272, 1); wire(&f, 0, 3, 0); out = once(&f);
    CHECK(!out.view.menu.connected && !f.resyncs); reset_reads(&f);
    wire(&f, 1, 272, 0); once(&f); CHECK(!f.resyncs); reset_reads(&f);
    wire(&f, 0, 0, 0); wire(&f, 1, 272, 1); wire(&f, 1, 272, 0); wire(&f, 0, 0, 0);
    out = once(&f); CHECK(!out.view.menu.connected && !f.resyncs); reset_reads(&f);
    f.synced = 0; once(&f); CHECK(f.resyncs == 1 && !p.stream.evdev.connected);
    /* A trailing fragment after REPORT must be completed and discarded before
     * state resync, otherwise the next read would start in the middle. */
    { unsigned char bytes[24];
      record(bytes, layout, 1, 272, 0);
      queue(&f, bytes, 3, GAME_READ_DATA); once(&f); reset_reads(&f);
      CHECK(p.stream.used == 3 && f.resyncs == 2);
      f.synced = 1; queue(&f, bytes+3, (size_t)layout-3, GAME_READ_DATA);
      once(&f); reset_reads(&f); CHECK(!p.stream.used && f.resyncs == 2); }
    f.synced = 1; out = once(&f); CHECK(f.resyncs == 3 && out.view.menu.connected);
    CHECK(!out.view.game.generation && !out.view.menu.left_down);
    puts("PASS EOF/error/disconnect latch / partial and click clearing / epoch recovery / SYN_DROPPED order");
}
static void test_time_and_results(int flood)
{
    Fake f; GameLoop loop; GamePump p; GamePumpOutput out, saved;
    GameCaptureStamp old, stamp;
    init(&f, &loop, &p, GAME_EVDEV_LE32);
    menu(&p, GAME_MENU_SELECT, 1); old = dispatch(&p, UINT64_C(4294967399));
    menu(&p, GAME_MENU_SELECT, 3);
    f.now = 1; fixture(&f, 3, dispatch(&p, UINT64_C(4294967297)), 0);
    f.scrub = 1; out = once(&f); CHECK(out.results == 1 && out.view.game.ready);
    coherent(&out.view.game); saved = out;
    f.now = 2; fixture(&f, 1, old, 1); out = once(&f);
    CHECK(out.result_status == GAME_OLD_GENERATION);
    CHECK(!memcmp(&out.view.game, &saved.view.game, sizeof(saved.view.game)));
    f.now = 3; menu(&p, GAME_MENU_START, 0);
    f.now = 4; f.flood = flood; f.advance = flood ? 3 : 0;
    stamp = dispatch(&p, UINT64_C(4294967298)); fixture(&f, 3, stamp, 0);
    f.repeat_result = 1;
    out = once(&f); /* even continuous input/EINTR yields to completion queue */
    CHECK(out.results == GAME_PUMP_RESULT_MAX && out.reads <= GAME_PUMP_READ_MAX);
    CHECK(out.result_status == GAME_DUPLICATE_FRAME && out.view.game.scene_sequence == stamp.sequence);
    f.repeat_result = f.ready = 0;
    f.until = 180003;
    CHECK(game_pump_run(&p, &out) == GAME_PUMP_STOP);
    CHECK(out.view.game.state == GAME_TIMED_OUT && out.view.game.elapsed_ms == 180000);
    CHECK(!out.view.game.remaining_ms && !out.view.game.stars && out.view.game.generation == 2);
    CHECK(f.publications > 100 && (flood == 1 || f.waits > 100));
    if (!flood) CHECK(f.now == 180003); /* deadline capped to exact timeout */
    if (flood) CHECK(f.now < 180003+4*3+10);
    coherent(&saved.view.game); CHECK(saved.view.game.scene_sequence == UINT64_C(4294967297));
    /* Score and all geometry come from one capture, despite borrowed buffer reuse. */
    f.flood = 0; f.advance = 0; ++f.now; menu(&p, GAME_MENU_SELECT, 1);
    ++f.now; stamp = dispatch(&p, 1); fixture(&f, 1, stamp, 1); once(&f);
    ++f.now; menu(&p, GAME_MENU_START, 0); f.now += 59999;
    stamp = dispatch(&p, 2); fixture(&f, 1, stamp, 0); f.now += 1;
    out = once(&f); CHECK(out.view.game.state == GAME_CLEARED && out.view.game.stars == 3);
    CHECK(out.view.game.elapsed_ms == 59999 && out.view.game.captured_ms == stamp.captured_ms);
    CHECK(out.view.game.scene_sequence == stamp.sequence && out.view.game.generation == stamp.generation);
    coherent(&out.view.game); saved = out;
    ++f.now; menu(&p, GAME_MENU_SELECT, 2); coherent(&saved.view.game);
    CHECK(saved.view.game.stars == 3);
    puts("PASS idle/flood/EINTR timer / deadline wait / original stamp / old task / borrowed results / coherent score");
}
static void test_interrupts_and_faults(void)
{
    Fake f; GameLoop loop; GamePump p; GamePumpOutput out;
    unsigned char bytes[24];
    init(&f, &loop, &p, GAME_EVDEV_LE64); f.link = (GamePumpConnection){1, 1};
    record(bytes, GAME_EVDEV_LE64, 2, 0, 123);
    queue(&f, bytes, 3, GAME_READ_DATA);
    queue(&f, NULL, 0, GAME_READ_INTERRUPTED); queue(&f, NULL, 0, GAME_READ_AGAIN);
    out = once(&f); CHECK(p.stream.used == 3 && out.bytes == 3 && out.reads == 3);
    reset_reads(&f); queue(&f, bytes+3, 21, GAME_READ_DATA); out = once(&f);
    CHECK(!p.stream.used && !out.view.menu.x); /* short read retained across EINTR/EAGAIN */
    reset_reads(&f); f.until = 31; f.wait_interrupt = 1;
    CHECK(game_pump_run(&p, &out) == GAME_PUMP_STOP);
    CHECK(f.now == 31 && f.waits == 31); /* interrupted waits yield to ticks */
    { size_t reads = f.calls; --f.now;
      CHECK(game_pump_once(&p, &out) == GAME_PUMP_BAD_CLOCK && f.calls == reads); }
    ++f.now; f.result_error = 1;
    CHECK(game_pump_once(&p, &out) == GAME_PUMP_IO_ERROR);
    init(&f, &loop, &p, GAME_EVDEV_LE64); f.link = (GamePumpConnection){1, 1};
    queue(&f, NULL, 0, GAME_READ_DATA); out = once(&f);
    CHECK(out.read_status == GAME_READ_ERROR && !out.view.menu.connected);
    puts("PASS short read / EINTR / EAGAIN / interrupted waits / backward clock / completion error");
}
int main(void)
{
    test_stream(GAME_EVDEV_LE32); test_stream(GAME_EVDEV_LE64);
    test_loss(GAME_EVDEV_LE32); test_loss(GAME_EVDEV_LE64);
    test_time_and_results(0); test_time_and_results(1); test_time_and_results(2);
    test_interrupts_and_faults();
    printf("PASS game pump: %u checks (simulated time/I/O only)\n", checks);
    return 0;
}
