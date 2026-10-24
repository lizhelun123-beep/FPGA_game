/* Text replay front end. All time and observations come from stdin; no clock
 * reads, detector replacement, template completion, devices or auto-start. */
#include "game_loop.h"
#include "game_evdev.h"
#include "game_config.h"
#include "game_render.h"

#include <errno.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static GameRenderAssets art;
static VisionCanvas cpu_canvas;
static unsigned rendered_frames;
static void cpu_close(void)
{
    free(cpu_canvas.data); cpu_canvas.data=NULL;
    game_render_assets_free(&art);
}
static int cpu_render(const GameLoopOutput *output)
{
    GameRenderStatus s;
    if (!cpu_canvas.data) {
        size_t size=(size_t)game_default_menu_layout.width*3*(size_t)game_default_menu_layout.height;
        cpu_canvas=(VisionCanvas){NULL,game_default_menu_layout.width,game_default_menu_layout.height,
                                  (size_t)game_default_menu_layout.width*3,size};
        cpu_canvas.data=(uint8_t *)malloc(size);
        if (!cpu_canvas.data) return 0;
    }
    s=game_render_cached(output,&game_default_config,&game_default_menu_layout,&game_default_render_config,
                         art.storage?&art:NULL,&cpu_canvas);
    if (s!=GAME_RENDER_OK && s!=GAME_RENDER_FULL_RAY) return 0;
    ++rendered_frames;
    return 1;
}

/* Script backend, one pending read and one owned completion. No wall clock or
 * Linux syscalls. The persistent mailbox array outlives every synchronous poll. */
typedef struct {
    uint64_t now, until, batches, waits;
    GamePumpConnection link;
    unsigned char bytes[GAME_PUMP_READ_BYTES];
    GameReadResult read;
    GameDetectionFrame completion;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int ready, resynced;
    GamePumpOutput published;
} ReplayIO;
static ReplayIO replay;
static GamePump pump;
static int pumping;
static GameLoopOutput published_view;
static uint64_t replay_now(void *ctx) { return ((ReplayIO *)ctx)->now; }
static GamePumpConnection replay_link(void *ctx) { return ((ReplayIO *)ctx)->link; }
static GameReadResult replay_read(void *ctx, unsigned char *bytes, size_t capacity)
{
    ReplayIO *io = ctx;
    GameReadResult read = io->read;
    if (read.count > capacity) return (GameReadResult){GAME_READ_ERROR, 0};
    memcpy(bytes, io->bytes, read.count);
    io->read = (GameReadResult){GAME_READ_AGAIN, 0};
    return read;
}
static GameWaitStatus replay_wait(void *ctx, uint64_t deadline)
{
    ReplayIO *io = ctx;
    ++io->waits;
    io->now = deadline < io->until ? deadline : io->until;
    return GAME_WAIT_READY;
}
static int replay_resync(void *ctx) { return ((ReplayIO *)ctx)->resynced; }
static int replay_result(void *ctx, GameDetectionFrame *frame)
{
    ReplayIO *io = ctx;
    if (!io->ready) return 0;
    *frame = io->completion; io->ready = 0;
    return 1;
}
static int replay_stop(void *ctx) { ReplayIO *io = ctx; return io->now >= io->until; }
static void replay_publish(void *ctx, const GamePumpOutput *output)
{
    ReplayIO *io = ctx;
    io->published = *output; ++io->batches;
    published_view = output->view;
}
static GameStatus replay_step(GameLoop *loop, uint64_t now, const GameLoopEvent *event,
                               GameLoopOutput *output)
{
    if (!pumping) return game_loop_step(loop, now, event, output);
    replay.now = now;
    return game_pump_event(&pump, event, output);
}

static void help(void)
{
    puts("Offline game; mapping=uncalibrated_preview calibrated=0");
    puts("select NOW_MS LEVEL | start NOW_MS | tick NOW_MS | snapshot | quit");
    puts("pointer NOW_MS X Y | left NOW_MS 0|1 | input NOW_MS 0|1");
    puts("evdev NOW_MS LE32|LE64 HEX_RECORD | dispatch NOW_MS SEQUENCE CAPTURED_MS");
    puts("frame NOW_MS GENERATION SEQUENCE CAPTURED_MS VALID HELD COUNT");
    puts("followed by COUNT lines: TYPE CX CY AX AY DIRECTION_VALID DX DY");
    puts("TYPE: 0=MIRROR 1=PORTAL_A 2=PORTAL_B 3=TARGET 4=SOURCE 5=WALL");
    puts("GENERATION must be saved at capture/dispatch, never filled at receipt.");
    puts("pump_begin NOW_MS LE32|LE64 | pump_bytes HEX_BYTES | pump_io again|interrupt|eof|disconnect|error");
    puts("pump_link 0|1 EPOCH | pump_resync 0|1 | pump_run UNTIL_MS");
    puts("pump_frame: same rows/header as frame, queues one OWNED completion for pump_run.");
    puts("States/statuses are the enum values in game_session.h.");
    puts("render PATH.ppm: export latest complete published view, no tick/state change (offline virtual preview).");
    puts("present: same native canvas as packed BGR on stdout; sync: flush command boundary; resources: CPU-only counters.");
}

static int render_output(const GameLoopOutput *output, const char *path)
{
    FILE *file;
    if (!cpu_render(output)) return 0;
    file=fopen(path,"wb");
    if (!file) return 0;
    {
        GameRenderStatus written=game_render_write_ppm(&cpu_canvas,file);
        int closed=fclose(file);
        if (written!=GAME_RENDER_OK || closed) return 0;
    }
    printf("image path=%s render_status=%d generation=%" PRIu64 " sequence=%" PRIu64 "\n",
           path,output->game.render_budget_exceeded?GAME_RENDER_FULL_RAY:GAME_RENDER_OK,
           output->game.generation,output->game.scene_sequence);
    return 1;
}

static int write_output(const GameLoop *loop, const GameLoopOutput *output)
{
    printf("menu x=%d y=%d connected=%d left=%d start_enabled=%d action=%d level=%u\n",
           output->menu.x, output->menu.y, output->menu.connected, output->menu.left_down,
           output->menu.start_enabled, (int)output->action.kind, output->action.level_id);
    if (output->has_stamp)
        printf("dispatch generation=%" PRIu64 " sequence=%" PRIu64 " captured_ms=%" PRIu64 "\n",
               output->stamp.generation, output->stamp.sequence, output->stamp.captured_ms);
    return game_app_write_view(&loop->app, &output->game, stdout);
}

static int hex_digit(char c)
{
    if (c >= '0' && c <= '9') return c-'0';
    if (c >= 'a' && c <= 'f') return c-'a'+10;
    if (c >= 'A' && c <= 'F') return c-'A'+10;
    return -1;
}

static int decode_record(const char *name, const char *hex, GameEvdevEvent *event)
{
    GameEvdevLayout layout;
    unsigned char bytes[24];
    size_t i;
    if (!strcmp(name, "LE32")) layout = GAME_EVDEV_LE32;
    else if (!strcmp(name, "LE64")) layout = GAME_EVDEV_LE64;
    else return 0;
    if (strlen(hex) != 2*(size_t)layout) return 0;
    for (i = 0; i < (size_t)layout; ++i) {
        int a = hex_digit(hex[2*i]), b = hex_digit(hex[2*i+1]);
        if (a < 0 || b < 0) return 0;
        bytes[i] = (unsigned char)(a*16+b);
    }
    return game_evdev_decode(layout, bytes, (size_t)layout, event);
}

static int read_u64(const char *token, uint64_t *output)
{
    char *end;
    unsigned long long value;
    if (token[0] < '0' || token[0] > '9') return 0;
    errno = 0;
    value = strtoull(token, &end, 10);
    if (errno || *end || value > UINT64_MAX) return 0;
    *output = (uint64_t)value;
    return 1;
}

int main(int argc,char **argv)
{
    GameLoop loop;
    GameLoopOutput output;
    GameEvdev evdev;
    char line[512], command[24], time_token[32], extra;
    GameStatus status;
    uint64_t now;
    unsigned int level;
    if (atexit(cpu_close)) return 1;
    if (argc!=1 && !(argc==3 && !strcmp(argv[1],"--assets"))) {
        fputs("usage: game_offline [--assets game_assets.bin] < events.replay\n",stderr); return 2;
    }
    if (argc==3 && game_render_assets_load(&art,argv[2],&game_default_config,&game_default_render_config)!=GAME_RENDER_OK) {
        fputs("Asset load rejected (missing, truncated, corrupt or incompatible geometry); no game started.\n",stderr); return 2;
    }
#ifdef _WIN32
    if (_setmode(1,_O_BINARY)==-1) return 1;
#endif
    setvbuf(stdout,NULL,_IONBF,0);
    if (game_loop_init(&loop, &game_default_config, &game_uncalibrated_identity_mapping,
                       &game_default_menu_layout) != GAME_OK ||
        !game_evdev_init(&evdev, game_default_menu_layout.width,
                        game_default_menu_layout.height)) return 1;
    if (game_loop_step(&loop, 0, NULL, &output) != GAME_OK) return 1;
    published_view=output;
    help();
    while (fgets(line, sizeof(line), stdin)) {
        GameLoopEvent event;
        memset(&event, 0, sizeof(event));
        if (sscanf(line, "%23s", command) != 1 || command[0] == '#') continue;
        if (!strcmp(command, "quit")) return 0;
        if (!strcmp(command,"sync")) { puts("READY"); continue; }
        if (!strcmp(command,"resources")) {
            printf("cpu assets_loaded=%u asset_bytes=%lu canvas_bytes=%lu frames=%u hardware=OFF\n",
                   art.loads,(unsigned long)art.bytes,(unsigned long)cpu_canvas.capacity,rendered_frames);
            continue;
        }
        if (!strcmp(command,"present")) {
            if (!cpu_render(&published_view)) return 1;
            printf("BGR %d %d %lu\n",cpu_canvas.width,cpu_canvas.height,(unsigned long)cpu_canvas.capacity);
            if (fwrite(cpu_canvas.data,1,cpu_canvas.capacity,stdout)!=cpu_canvas.capacity) return 1;
            continue;
        }
        if (!strcmp(command, "snapshot")) {
            if (write_output(&loop, &output)) return 1;
            continue;
        }
        if (!strcmp(command,"render")) {
            char path[384];
            if (sscanf(line,"%23s %383s %c",command,path,&extra)!=2) goto malformed;
            if (!render_output(&published_view,path)) { fputs("Offline render/export failed.\n",stderr); return 1; }
            continue;
        }
        if (!strcmp(command, "pump_begin")) {
            char layout[8];
            GamePumpIO io = {GAME_PUMP_IO_VERSION, &replay, replay_now, replay_link,
                replay_read, replay_wait, replay_resync, replay_result, replay_stop, replay_publish};
            if (pumping || evdev.pending.count ||
                sscanf(line, "%23s %31s %7s %c", command, time_token, layout, &extra) != 3 ||
                !read_u64(time_token, &now) || (strcmp(layout, "LE32") && strcmp(layout, "LE64")))
                goto malformed;
            replay.now = now; replay.read.status = GAME_READ_AGAIN;
            replay.link = (GamePumpConnection){1, 1};
            if (!game_pump_init(&pump, &loop, &game_default_pump_config,
                               !strcmp(layout, "LE32") ? GAME_EVDEV_LE32 : GAME_EVDEV_LE64, &io))
                goto malformed;
            pumping = 1; output = pump.latest; status = GAME_OK;
        } else if (!strcmp(command, "pump_bytes")) {
            char hex[2*GAME_PUMP_READ_BYTES+1];
            size_t i, length;
            if (!pumping || replay.read.status != GAME_READ_AGAIN ||
                sscanf(line, "%23s %384s %c", command, hex, &extra) != 2) goto malformed;
            length = strlen(hex);
            if (!length || length%2) goto malformed;
            for (i = 0; i < length/2; ++i) {
                int a = hex_digit(hex[2*i]), b = hex_digit(hex[2*i+1]);
                if (a < 0 || b < 0) goto malformed;
                replay.bytes[i] = (unsigned char)(16*a+b);
            }
            replay.read = (GameReadResult){GAME_READ_DATA, length/2}; status = GAME_OK;
        } else if (!strcmp(command, "pump_io")) {
            char name[16];
            const char *names[] = {"again", "interrupt", "eof", "disconnect", "error"};
            int i;
            if (!pumping || replay.read.status != GAME_READ_AGAIN ||
                sscanf(line, "%23s %15s %c", command, name, &extra) != 2) goto malformed;
            for (i = 0; i < 5 && strcmp(name, names[i]); ++i) {}
            if (i == 5) goto malformed;
            replay.read = (GameReadResult){(GameReadStatus)(GAME_READ_AGAIN+i), 0}; status = GAME_OK;
        } else if (!strcmp(command, "pump_link")) {
            int connected;
            if (!pumping || sscanf(line, "%23s %d %31s %c", command, &connected, time_token, &extra) != 3 ||
                (connected != 0 && connected != 1) || !read_u64(time_token, &now)) goto malformed;
            replay.link = (GamePumpConnection){connected, now}; status = GAME_OK;
        } else if (!strcmp(command, "pump_resync")) {
            int value;
            if (!pumping || sscanf(line, "%23s %d %c", command, &value, &extra) != 2 ||
                (value != 0 && value != 1)) goto malformed;
            replay.resynced = value; status = GAME_OK;
        } else if (!strcmp(command, "pump_run")) {
            GamePumpOutput out;
            if (!pumping || sscanf(line, "%23s %31s %c", command, time_token, &extra) != 2 ||
                !read_u64(time_token, &now) || now < replay.now) goto malformed;
            replay.until = now;
            if (game_pump_run(&pump, &out) != GAME_PUMP_STOP) return 1;
            output = replay.published.view; status = GAME_OK;
            printf("pump now=%" PRIu64 " batches=%" PRIu64 " waits=%" PRIu64 " result_status=%d\n",
                   replay.now, replay.batches, replay.waits, (int)replay.published.result_status);
        } else if (!strcmp(command, "select") &&
            sscanf(line, "%23s %31s %u %c", command, time_token, &level, &extra) == 3 &&
            read_u64(time_token, &now)) {
            event.kind = GAME_LOOP_MENU;
            event.data.menu = (GameMenuAction){GAME_MENU_SELECT, level};
            status = replay_step(&loop, now, &event, &output);
        } else if ((!strcmp(command, "start") || !strcmp(command, "tick")) &&
                   sscanf(line, "%23s %31s %c", command, time_token, &extra) == 2 &&
                   read_u64(time_token, &now)) {
            event.kind = GAME_LOOP_MENU;
            event.data.menu.kind = GAME_MENU_START;
            status = replay_step(&loop, now, !strcmp(command, "start") ? &event : NULL, &output);
        } else if (!strcmp(command, "pointer")) {
            if (pumping || evdev.pending.count) goto malformed;
            event.kind = GAME_LOOP_MOUSE;
            event.data.mouse.kind = GAME_MOUSE_MOVE;
            if (sscanf(line, "%23s %31s %d %d %c", command, time_token,
                       &event.data.mouse.x, &event.data.mouse.y, &extra) != 4 ||
                !read_u64(time_token, &now)) goto malformed;
            status = replay_step(&loop, now, &event, &output);
            /* These are alternate replay sources. Keep their pointer origin
             * aligned; never interleave an unfinished evdev report with them. */
            if (status != GAME_BAD_TIME) {
                evdev.x = evdev.published_x = loop.input.x;
                evdev.y = evdev.published_y = loop.input.y;
            }
        } else if (!strcmp(command, "left") || !strcmp(command, "input")) {
            int value;
            if (pumping) goto malformed;
            if (sscanf(line, "%23s %31s %d %c", command, time_token, &value, &extra) != 3 ||
                !read_u64(time_token, &now) || (value != 0 && value != 1)) goto malformed;
            event.kind = GAME_LOOP_MOUSE;
            if (!strcmp(command, "left") && evdev.pending.count) goto malformed;
            event.data.mouse.kind = !strcmp(command, "left") ?
                (value ? GAME_MOUSE_LEFT_DOWN : GAME_MOUSE_LEFT_UP) :
                (value ? GAME_MOUSE_CONNECT : GAME_MOUSE_DISCONNECT);
            status = replay_step(&loop, now, !strcmp(command, "input") ? NULL : &event, &output);
            if (!strcmp(command, "input") && status != GAME_BAD_TIME) {
                GameMouseBatch batch;
                game_evdev_connection(&evdev, value, &batch);
                if (batch.count) status = replay_step(&loop, now, &event, &output);
            }
        } else if (!strcmp(command, "evdev")) {
            GameEvdevEvent raw;
            GameMouseBatch batch;
            char layout[8], hex[64];
            size_t i;
            if (pumping) goto malformed;
            if (sscanf(line, "%23s %31s %7s %63s %c", command, time_token,
                       layout, hex, &extra) != 4 || !read_u64(time_token, &now) ||
                !decode_record(layout, hex, &raw)) goto malformed;
            status = replay_step(&loop, now, NULL, &output);
            if (status == GAME_OK) {
                if (game_evdev_feed(&evdev, &raw, &batch) < 0) return 1;
                for (i = 0; i < batch.count; ++i) {
                    event.kind = GAME_LOOP_MOUSE; event.data.mouse = batch.events[i];
                    status = replay_step(&loop, now, &event, &output);
                }
            }
        } else if (!strcmp(command, "dispatch")) {
            char sequence[32], captured[32];
            event.kind = GAME_LOOP_DISPATCH;
            if (sscanf(line, "%23s %31s %31s %31s %c", command, time_token,
                       sequence, captured, &extra) != 4 || !read_u64(time_token, &now) ||
                !read_u64(sequence, &event.data.dispatch.sequence) ||
                !read_u64(captured, &event.data.dispatch.captured_ms)) goto malformed;
            status = replay_step(&loop, now, &event, &output);
        } else if (!strcmp(command, "frame") || !strcmp(command, "pump_frame")) {
            GameDetectionFrame frame;
            VisionDetection detections[VISION_MAX_DETECTIONS];
            char generation[32], sequence[32], captured[32];
            int i, kind;
            int queued = !strcmp(command, "pump_frame");
            if (queued && (!pumping || replay.ready)) goto malformed;
            memset(&frame, 0, sizeof(frame));
            memset(detections, 0, sizeof(detections));
            if (sscanf(line, "%23s %31s %31s %31s %31s %d %d %d %c",
                       command, time_token, generation, sequence, captured,
                       &frame.valid, &frame.held, &frame.count, &extra) != 8 ||
                !read_u64(time_token, &now) ||
                !read_u64(generation, &frame.stamp.generation) ||
                !read_u64(sequence, &frame.stamp.sequence) ||
                !read_u64(captured, &frame.stamp.captured_ms) ||
                frame.count < 0 || frame.count > VISION_MAX_DETECTIONS) goto malformed;
            for (i = 0; i < frame.count; ++i) {
                VisionDetection *d = &detections[i];
                if (!fgets(line, sizeof(line), stdin) ||
                    sscanf(line, "%d %f %f %f %f %d %f %f %c", &kind,
                           &d->geometry_center_x, &d->geometry_center_y,
                           &d->axis_x, &d->axis_y, &d->direction_valid,
                           &d->source_direction_x, &d->source_direction_y, &extra) != 8)
                    goto malformed;
                d->type = (VisionType)kind;
            }
            frame.detections = detections;
            event.kind = GAME_LOOP_DETECTION; event.data.detection = frame;
            if (queued) {
                if (now < replay.now) goto malformed;
                replay.now = now;
                memcpy(replay.detections, detections, (size_t)frame.count*sizeof(detections[0]));
                replay.completion = frame; replay.completion.detections = replay.detections;
                replay.ready = 1; status = GAME_OK;
            } else status = replay_step(&loop, now, &event, &output);
        } else {
            goto malformed;
        }
        printf("status=%d\n", (int)status);
        if (!pumping) published_view=output;
        if (write_output(&loop, &output)) return 1;
    }
    return ferror(stdin) ? 1 : 0;
malformed:
    fputs("Malformed command or detection row; see command format above.\n", stderr);
    return 2;
}
