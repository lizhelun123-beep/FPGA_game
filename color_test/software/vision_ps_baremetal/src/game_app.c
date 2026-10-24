#include "game_app.h"

#include <inttypes.h>
#include <string.h>

GameStatus game_app_init(GameApp *app, const GameConfig *config,
                         const GameSceneMapping *mapping)
{
    GameStatus status;
    if (!app) return GAME_BAD_ARGUMENT;
    memset(app, 0, sizeof(*app));
    if (!mapping || mapping->version != GAME_MAPPING_VERSION ||
        !mapping->map_pose || !mapping->coordinate_space ||
        !config || !config->coordinate_space ||
        strcmp(mapping->coordinate_space, config->coordinate_space) != 0)
        return GAME_BAD_CONFIG;
    status = game_session_init(&app->session, config);
    if (status == GAME_OK) app->mapping = *mapping;
    return status;
}

GameStatus game_app_select(GameApp *app, unsigned int level_id, uint64_t now_ms)
{
    return game_session_select(app ? &app->session : NULL, level_id, now_ms);
}

GameStatus game_app_capture_stamp(const GameApp *app, uint64_t sequence,
                                  uint64_t captured_ms, GameCaptureStamp *stamp)
{
    const GameSnapshot *view;
    if (!app || !app->session.config || !stamp) return GAME_BAD_ARGUMENT;
    view = game_session_snapshot(&app->session);
    if (view->state != GAME_PREPARING && view->state != GAME_RUNNING)
        return GAME_BAD_STATE;
    *stamp = (GameCaptureStamp){view->generation, sequence, captured_ms};
    return GAME_OK;
}

GameStatus game_app_submit(GameApp *app, const GameDetectionFrame *frame,
                           uint64_t now_ms)
{
    GameAdaptedScene scene;
    GameStatus status;
    if (!app || !app->session.config || !frame) return GAME_BAD_ARGUMENT;
    status = game_scene_adapt(&app->mapping, frame, &scene);
    if (status == GAME_BAD_ARGUMENT) return status;
    /* Invalid data must reach the core too: consume its sequence and clear a
     * candidate. The core alone decides time/generation/terminal precedence. */
    return game_session_submit(&app->session, &scene.input, now_ms);
}

GameStatus game_app_start(GameApp *app, uint64_t now_ms)
{
    return game_session_start(app ? &app->session : NULL, now_ms);
}

GameStatus game_app_tick(GameApp *app, uint64_t now_ms)
{
    return game_session_tick(app ? &app->session : NULL, now_ms);
}

GameStatus game_app_snapshot(const GameApp *app, GameSnapshot *snapshot)
{
    if (!app || !app->session.config || !snapshot) return GAME_BAD_ARGUMENT;
    *snapshot = *game_session_snapshot(&app->session);
    return GAME_OK;
}

int game_app_write_snapshot(const GameApp *app, FILE *output)
{
    GameSnapshot view;
    if (game_app_snapshot(app, &view) != GAME_OK) return -1;
    return game_app_write_view(app, &view, output);
}

int game_app_write_view(const GameApp *app, const GameSnapshot *snapshot, FILE *output)
{
    GameSnapshot view;
    int i;
    if (!app || !app->session.config || !snapshot || !output) return -1;
    view = *snapshot;
    if (fprintf(output, "mapping=%s calibrated=%d state=%d level=%u generation=%" PRIu64
                " sequence=%" PRIu64 " captured_ms=%" PRIu64
                " elapsed_ms=%" PRIu64 " remaining_ms=%" PRIu64
                " stars=%u valid=%d ready=%d scene_status=%d budget_exceeded=%d\n",
                app->mapping.coordinate_space, app->mapping.calibrated,
                (int)view.state, view.level_id, view.generation, view.scene_sequence,
                view.captured_ms, view.elapsed_ms, view.remaining_ms, view.stars,
                view.scene_valid, view.ready, (int)view.scene_status,
                view.render_budget_exceeded) < 0) return -1;
    for (i = 0; i < view.object_count; ++i) {
        const SceneObject *o = &view.objects[i];
        if (fprintf(output, "model=%d type=%d center=%.6g,%.6g axis=%.6g,%.6g"
                    " size=%.6g,%.6g tip=%.6g,%.6g direction=%.6g,%.6g valid=%d\n",
                    i, (int)o->type, o->center.x, o->center.y, o->axis.x, o->axis.y,
                    o->length, o->width, o->source_tip.x, o->source_tip.y,
                    o->source_direction.x, o->source_direction.y,
                    o->direction_valid) < 0) return -1;
    }
    if (fprintf(output, "ray success=%d termination=%d interactions=%d hits=%d segments=%d\n",
                view.ray.success, (int)view.ray.termination, view.ray.interaction_count,
                view.ray.hit_count, view.ray.segment_count) < 0) return -1;
    for (i = 0; i < view.ray.hit_count; ++i)
        if (fprintf(output, "hit=%d type=%d\n", i, (int)view.ray.hit_types[i]) < 0) return -1;
    for (i = 0; i < view.ray.segment_count; ++i)
        if (fprintf(output, "segment=%d start=%.6g,%.6g end=%.6g,%.6g\n", i,
                    view.ray.segments[i].start.x, view.ray.segments[i].start.y,
                    view.ray.segments[i].end.x, view.ray.segments[i].end.y) < 0) return -1;
    return ferror(output) ? -1 : 0;
}
