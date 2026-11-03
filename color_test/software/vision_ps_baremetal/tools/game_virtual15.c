#if defined(__linux__)
#define _POSIX_C_SOURCE 200809L
#endif

/*
 * Camera-free PYNQ/Linux presentation target.
 *
 * This entry deliberately builds a scene from the generated level table and
 * sends it through the existing C ray solver and renderer.  It does not
 * initialize OV5640, CSI, S2MM, a detector, or a capture worker.  The logical
 * emitter remains level data; it is never presented as a camera SOURCE.
 *
 * --check is host-only and writes one 1280x720 PPM per configured level.
 * On ARM, --virtual15 cycles the same fifteen completed CPU frames through
 * the existing three-store display owner.  The caller may pass --level N to
 * hold one level, or --seconds N to cycle for a bounded interval.
 */
#include "game_config.h"
#include "game_input.h"
#include "game_linux_display.h"
#include "game_render.h"
#include "ray_game.h"
#include "virtual15_lvgl_ui.h"

#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__linux__)
#include <time.h>
#endif

#if defined(__linux__)
static volatile sig_atomic_t stop_requested;
static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}
#endif

static int normalize(RayPoint *point)
{
    float length;
    if (!point || !isfinite(point->x) || !isfinite(point->y)) return 0;
    length = hypotf(point->x, point->y);
    if (!isfinite(length) || length < 1.0e-6f) return 0;
    point->x /= length;
    point->y /= length;
    return 1;
}

static int make_reference_view(unsigned level_id, uint64_t stamp,
                               GameLoopOutput *published)
{
    const GameLevelConfig *level = NULL;
    GameMenuInput menu_input;
    RayGameResult scaled;
    RayPoint emission, direction;
    float scale;
    int i, index, count;
    if (!published || !level_id) return 0;
    for (index = 0; index < game_default_config.level_count; ++index)
        if (game_default_config.levels[index].id == level_id)
            level = &game_default_config.levels[index];
    if (!level) return 0;

    memset(published, 0, sizeof(*published));
    published->game.state = GAME_PREPARING;
    published->game.level_id = level_id;
    published->game.generation = level_id;
    published->game.scene_sequence = 1;
    published->game.captured_ms = stamp;
    published->game.remaining_ms = game_default_config.duration_ms;
    published->game.scene_valid = 1;
    published->game.scene_status = GAME_OK;

    count = level->object_count;
    if (count < 1 || count > GAME_MAX_MODELS) return 0;
    for (i = 0; i < count; ++i) {
        SceneObject object = level->objects[i].anchor;
        if ((unsigned)object.type >= RAY_OBJECT_TYPE_COUNT ||
            !normalize(&object.axis)) return 0;
        object.length = game_default_config.model_sizes[object.type].x;
        object.width = game_default_config.model_sizes[object.type].y;
        object.source_tip = (RayPoint){0, 0};
        object.source_direction = (RayPoint){0, 0};
        object.direction_valid = 0;
        published->game.objects[i] = object;
    }

    if (!level->emitter.enabled || count >= GAME_MAX_MODELS) return 0;
    emission = level->emitter.point;
    direction = level->emitter.direction;
    if (!normalize(&direction)) return 0;
    published->game.objects[count] = (SceneObject){
        RAY_OBJECT_SOURCE, emission, direction,
        game_default_config.model_sizes[RAY_OBJECT_SOURCE].x,
        game_default_config.model_sizes[RAY_OBJECT_SOURCE].y,
        emission, direction, 1
    };
    ++count;
    published->game.object_count = count;

    scale = game_default_config.physics_scale;
    if (!isfinite(scale) || scale < 1.0f) return 0;
    {
        SceneObject scaled_objects[GAME_MAX_MODELS];
        for (i = 0; i < count; ++i) {
            scaled_objects[i] = published->game.objects[i];
            scaled_objects[i].center.x *= scale;
            scaled_objects[i].center.y *= scale;
            scaled_objects[i].source_tip.x *= scale;
            scaled_objects[i].source_tip.y *= scale;
            scaled_objects[i].length *= scale;
            scaled_objects[i].width *= scale;
        }
        emission.x *= scale;
        emission.y *= scale;
        if (ray_game_trace_from_emitter_policy(
                scaled_objects, count, game_default_config.width * scale + 1.0f,
                game_default_config.height * scale + 1.0f, emission, direction,
                game_default_config.portal_b_exit_side, &scaled)) return 0;
    }
    published->game.ray = scaled;
    for (i = 0; i < published->game.ray.segment_count; ++i) {
        published->game.ray.segments[i].start.x /= scale;
        published->game.ray.segments[i].start.y /= scale;
        published->game.ray.segments[i].end.x /= scale;
        published->game.ray.segments[i].end.y /= scale;
    }
    published->game.render_budget_exceeded =
        published->game.ray.segment_count > game_default_config.render_max_ray_segments;
    published->game.ready = !published->game.ray.success;
    if (published->game.ray.success)
        published->game.scene_status = GAME_NEED_UNSOLVED;

    memset(&menu_input, 0, sizeof(menu_input));
    menu_input.connected = 1;
    published->menu = game_menu_view(&menu_input, &game_default_menu_layout,
                                     &published->game);
    published->status = GAME_OK;
    published->has_stamp = 0;
    return 1;
}

static int render_level(unsigned level_id, const char *assets_path,
                        const char *output_path, uint64_t stamp,
                        unsigned *segments, int *success)
{
    GameRenderAssets assets = {0};
    GameLoopOutput published;
    VisionCanvas logical = {0}, output = {0};
    FILE *file = NULL;
    GameRenderStatus status;
    int result = 0;
    logical.width = 1280; logical.height = 800; logical.stride = 3840;
    logical.capacity = 1280U * 800U * 3U;
    output.width = 1280; output.height = 720; output.stride = 3840;
    output.capacity = 1280U * 720U * 3U;
    logical.data = (uint8_t *)malloc(logical.capacity);
    output.data = (uint8_t *)malloc(output.capacity);
    if (!logical.data || !output.data ||
        game_render_assets_load(&assets, assets_path, &game_default_config,
                                &game_default_render_config) != GAME_RENDER_OK ||
        !make_reference_view(level_id, stamp, &published)) goto done;
    status = game_render_cached_source(&published, &game_default_config,
                                       &game_default_menu_layout,
                                       &game_default_render_config, &assets,
                                       &logical, "VIRTUAL15 | CONFIG SCENE");
    if (status != GAME_RENDER_OK && status != GAME_RENDER_FULL_RAY) goto done;
    if (game_render_fit_720p(&logical, &output) != GAME_RENDER_OK) goto done;
    if (segments) *segments = (unsigned)published.game.ray.segment_count;
    if (success) *success = published.game.ray.success;
    if (output_path) {
        file = fopen(output_path, "wb");
        if (!file || game_render_write_ppm(&output, file) != GAME_RENDER_OK ||
            fclose(file)) { file = NULL; goto done; }
        file = NULL;
    }
    result = 1;
done:
    if (file) fclose(file);
    game_render_assets_free(&assets);
    free(logical.data); free(output.data);
    return result;
}

static int host_check(const char *assets_path, const char *output_dir)
{
    unsigned level, segments;
    int success;
    char path[4096];
    FILE *manifest;
    if (!assets_path || !output_dir) return 2;
    if (snprintf(path, sizeof(path), "%s/virtual15_manifest.txt", output_dir) < 0 ||
        strlen(path) >= sizeof(path)) return 2;
    manifest = fopen(path, "wb");
    if (!manifest) return 2;
    for (level = 1; level <= (unsigned)game_default_config.level_count; ++level) {
        if (snprintf(path, sizeof(path), "%s/level_%02u.ppm", output_dir, level) < 0 ||
            strlen(path) >= sizeof(path) ||
            !render_level(level, assets_path, path, level * 1000U, &segments, &success)) {
            fclose(manifest);
            return 1;
        }
        fprintf(manifest, "level=%u segments=%u success=%d\n", level, segments, success);
    }
    fprintf(stdout, "VIRTUAL15_HOST_CHECK levels=%d width=1280 height=720 "
                    "camera=0 csi=0 s2mm=0 detector=0 output=%s\n",
            game_default_config.level_count, output_dir);
    fclose(manifest);
    return 0;
}

#if defined(__linux__)
static int virtual15_run(const char *assets_path, unsigned selected_level,
                         unsigned seconds, int use_lvgl)
{
    GameLinuxDisplay display;
    GameDisplayMode mode;
    GameDisplayPlatform platform;
    VisionCanvas logical = {0}, output = {0};
    VisionCanvas overlay = {0};
    GameRenderAssets assets = {0};
    Virtual15LvglUi lvgl_ui = {0};
    GameDisplayStatus status = GAME_DISPLAY_OK;
    uint64_t start = 0, now = 0;
    unsigned level = selected_level ? selected_level : 1;
    unsigned cycle_ms = 1000;
    int running = 0, result = 1;

    if (!seconds || seconds > 600 || level > (unsigned)game_default_config.level_count ||
        signal(SIGINT, request_stop) == SIG_ERR || signal(SIGTERM, request_stop) == SIG_ERR)
        return 2;
    logical=(VisionCanvas){malloc(1280U*800U*3U),1280,800,3840,1280U*800U*3U};
    output=(VisionCanvas){malloc(1280U*720U*3U),1280,720,3840,1280U*720U*3U};
    overlay=(VisionCanvas){malloc(1280U*720U*3U),1280,720,3840,1280U*720U*3U};
    if (!logical.data || !output.data ||
        !overlay.data ||
        game_render_assets_load(&assets, assets_path, &game_default_config,
                                &game_default_render_config) != GAME_RENDER_OK)
        goto done;
    if (!virtual15_lvgl_ui_init(&lvgl_ui, &overlay, use_lvgl)) goto done;
    if (use_lvgl && !lvgl_ui.enabled)
        printf("VIRTUAL15_LVGL disabled=library_not_built\n");
    game_display_init(&display);
    game_display_control_720p_mode(&mode);
    game_display_linux_platform(&platform);
    {
        GameLoopOutput published;
        GameRenderStatus rendered;
        if (!make_reference_view(level, 1, &published)) goto done;
        rendered=game_render_cached_source(&published,&game_default_config,
            &game_default_menu_layout,&game_default_render_config,&assets,&logical,
            "VIRTUAL15 | CONFIG SCENE");
        if ((rendered!=GAME_RENDER_OK && rendered!=GAME_RENDER_FULL_RAY) ||
            game_render_fit_720p(&logical,&output)!=GAME_RENDER_OK ||
            !virtual15_lvgl_ui_update(&lvgl_ui, level,
                                      (unsigned)(game_default_config.duration_ms / 1000U),
                                      published.game.ray.success) ||
            !virtual15_lvgl_ui_blend(&lvgl_ui, &output) ||
            game_display_prepare_continuous(&display,&mode,&platform,&output)!=GAME_DISPLAY_OK ||
            game_display_start(&display,500)!=GAME_DISPLAY_OK) goto done;
    }
    running=1;
    if (platform.now_ms(platform.context,&start)) goto done;
    printf("VIRTUAL15_READY levels=%d width=1280 height=720 camera=0 csi=0 s2mm=0 detector=0\n",
           game_default_config.level_count);
    fflush(stdout);
    while (!stop_requested) {
        if (platform.now_ms(platform.context,&now) || now-start >= (uint64_t)seconds*1000U) {
            result=0; break;
        }
        if (!selected_level && now-start >= cycle_ms) {
            GameLoopOutput published;
            GameRenderStatus rendered;
            ++level; if (level > (unsigned)game_default_config.level_count) level=1;
            if (!make_reference_view(level, now, &published)) goto done;
            rendered=game_render_cached_source(&published,&game_default_config,
                &game_default_menu_layout,&game_default_render_config,&assets,&logical,
                "VIRTUAL15 | CONFIG SCENE");
            if ((rendered!=GAME_RENDER_OK && rendered!=GAME_RENDER_FULL_RAY) ||
                game_render_fit_720p(&logical,&output)!=GAME_RENDER_OK ||
                !virtual15_lvgl_ui_update(&lvgl_ui, level,
                                          (unsigned)(game_default_config.duration_ms / 1000U),
                                          published.game.ray.success) ||
                !virtual15_lvgl_ui_blend(&lvgl_ui, &output) ||
                game_display_update(&display,&output,500)!=GAME_DISPLAY_OK) goto done;
            cycle_ms += 1000;
            printf("VIRTUAL15_LEVEL level=%u\n",level); fflush(stdout);
        }
        if (platform.wait_ms(platform.context,10)) goto done;
    }
done:
    if (running) {
        status=game_display_stop(&display,500);
        if (status!=GAME_DISPLAY_OK || !game_display_owner_can_exit(&display))
            game_display_owner_drain(&display,500);
        if (status!=GAME_DISPLAY_OK || !game_display_owner_can_exit(&display)) result=1;
    }
    virtual15_lvgl_ui_close(&lvgl_ui);
    game_render_assets_free(&assets);
    free(logical.data); free(output.data); free(overlay.data);
    printf("VIRTUAL15_STOP result=%d status=%d owner_can_exit=%d\n",result,
           (int)status,game_display_owner_can_exit(&display));
    fflush(stdout);
    return result;
}
#endif

int main(int argc, char **argv)
{
    const char *assets = NULL, *output = NULL;
    unsigned level = 0, seconds = 0;
    int virtual_mode = 0, use_lvgl = 0;
    int i;
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--check") && i + 2 < argc) {
            assets=argv[++i]; output=argv[++i];
        } else if (!strcmp(argv[i], "--assets") && i + 1 < argc) {
            assets=argv[++i];
        } else if (!strcmp(argv[i], "--level") && i + 1 < argc) {
            level=(unsigned)strtoul(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) {
            seconds=(unsigned)strtoul(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--virtual15")) {
            virtual_mode=1;
        } else if (!strcmp(argv[i], "--lvgl-ui")) {
            use_lvgl=1;
        } else {
            fprintf(stderr,"usage: game_virtual15 --check ASSETS OUTPUT_DIR\n"
                           "       game_virtual15 --virtual15 --assets ASSETS"
                           " [--level N] [--seconds N] [--lvgl-ui]\n");
            return 2;
        }
    }
    if (output) return host_check(assets, output);
#if !defined(__linux__)
    (void)level; (void)seconds; (void)virtual_mode; (void)use_lvgl;
#endif
#if defined(__linux__)
    if (virtual_mode && assets && seconds)
        return virtual15_run(assets, level, seconds, use_lvgl);
#endif
    fprintf(stderr,"virtual15 runtime requires --assets and --seconds on Linux; "
                   "host uses --check.\n");
    return 2;
}
