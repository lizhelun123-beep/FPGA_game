#include "game_session.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static int normalize(RayPoint *axis)
{
    float norm;
    if (!isfinite(axis->x) || !isfinite(axis->y)) return 0;
    norm = hypotf(axis->x, axis->y);
    if (!isfinite(norm) || norm < 1.0e-6f) return 0;
    axis->x /= norm;
    axis->y /= norm;
    return 1;
}

static int inside(RayPoint point, const GameConfig *config)
{
    return isfinite(point.x) && isfinite(point.y) &&
           point.x >= 0 && point.x <= config->width &&
           point.y >= 0 && point.y <= config->height;
}

/* Canonical fixed model semantics from pc_vision.game_scene.Model:
 * centroid-based triangle tip, directed portal axis, circular TARGET.
 * ray_game.c derives finite mirror endpoints from center/axis/length. */
static int model(SceneObject *object, const GameConfig *config)
{
    RayPoint size = config->model_sizes[object->type];
    if (!inside(object->center, config) || !normalize(&object->axis)) return 0;
    object->length = size.x;
    object->width = size.y;
    object->source_tip = (RayPoint){0, 0};
    object->source_direction = (RayPoint){0, 0};
    object->direction_valid = object->type == RAY_OBJECT_SOURCE;
    if (object->direction_valid) {
        object->source_direction = object->axis;
        object->source_tip.x = object->center.x + object->axis.x*size.x*(2.0f/3.0f);
        object->source_tip.y = object->center.y + object->axis.y*size.x*(2.0f/3.0f);
        if (!inside(object->source_tip, config)) return 0;
    }
    return 1;
}

static int valid_config(const GameConfig *config)
{
    int i, j, k;
    if (!config || config->version != GAME_CONFIG_VERSION ||
        !config->coordinate_space || !isfinite(config->width) ||
        !isfinite(config->height) || config->width <= 0 || config->height <= 0 ||
        !isfinite(config->physics_scale) || config->physics_scale < 1 ||
        config->physics_scale > 10000 ||
        !isfinite(config->width*config->physics_scale) ||
        !isfinite(config->height*config->physics_scale) ||
        config->max_models < 1 || config->max_models > GAME_MAX_MODELS ||
        config->render_max_ray_segments < 1 ||
        config->render_max_ray_segments > RAY_GAME_MAX_SEGMENTS ||
        config->scene_max_age_ms == 0 || config->duration_ms == 0 ||
        config->star_threshold_ms[0] == 0 ||
        config->star_threshold_ms[0] >= config->star_threshold_ms[1] ||
        config->star_threshold_ms[1] >= config->duration_ms ||
        config->level_count < 1 || config->level_count > GAME_MAX_LEVELS) return 0;
    for (i = 0; i < RAY_OBJECT_TYPE_COUNT; ++i) {
        RayPoint size = config->model_sizes[i];
        if (!isfinite(size.x) || !isfinite(size.y) ||
            !isfinite(size.x*config->physics_scale) ||
            !isfinite(size.y*config->physics_scale) ||
            size.x*config->physics_scale <= 10 ||
            size.y*config->physics_scale <= 10) return 0;
    }
    if (config->model_sizes[RAY_OBJECT_TARGET].x !=
        config->model_sizes[RAY_OBJECT_TARGET].y) return 0;
    for (i = 0; i < config->level_count; ++i) {
        const GameLevelConfig *level = &config->levels[i];
        unsigned int mask = 0;
        if (!level->id || !level->reference || level->object_count < 1 ||
            level->object_count > config->max_models) return 0;
        for (k = 0; k < i; ++k)
            if (config->levels[k].id == level->id) return 0;
        for (j = 0; j < level->object_count; ++j) {
            SceneObject object = level->objects[j].anchor;
            GameMotion motion = level->objects[j].motion;
            if (object.type < 0 || object.type >= RAY_OBJECT_TYPE_COUNT ||
                (mask & (1U << object.type)) ||
                motion < GAME_FIXED || motion > GAME_FREE ||
                !model(&object, config)) return 0;
            mask |= 1U << object.type;
        }
        if (!(mask & (1U << RAY_OBJECT_SOURCE)) ||
            !(mask & (1U << RAY_OBJECT_TARGET)) ||
            !!(mask & (1U << RAY_OBJECT_PORTAL_A)) !=
            !!(mask & (1U << RAY_OBJECT_PORTAL_B))) return 0;
    }
    return 1;
}

static void clear_scene(GameSnapshot *view, GameStatus reason)
{
    view->scene_valid = view->ready = view->render_budget_exceeded = 0;
    view->object_count = 0;
    view->scene_sequence = view->captured_ms = 0;
    memset(view->objects, 0, sizeof(view->objects));
    memset(&view->ray, 0, sizeof(view->ray));
    view->scene_status = reason;
}

GameStatus game_session_init(GameSession *session, const GameConfig *config)
{
    if (!session) return GAME_BAD_ARGUMENT;
    memset(session, 0, sizeof(*session));
    if (!valid_config(config)) return GAME_BAD_CONFIG;
    session->config = config;
    session->view.state = GAME_SELECT_LEVEL;
    session->view.remaining_ms = config->duration_ms;
    clear_scene(&session->view, GAME_INVALID_SCENE);
    return GAME_OK;
}

GameStatus game_session_tick(GameSession *session, uint64_t now_ms)
{
    GameSnapshot *view;
    if (!session || !session->config) return GAME_BAD_ARGUMENT;
    if (session->have_time && now_ms < session->last_now_ms) return GAME_BAD_TIME;
    session->last_now_ms = now_ms;
    session->have_time = 1;
    view = &session->view;
    if (view->state == GAME_CLEARED || view->state == GAME_TIMED_OUT) return GAME_OK;
    if (view->state == GAME_RUNNING) {
        view->elapsed_ms = now_ms-session->started_ms;
        if (view->elapsed_ms >= session->config->duration_ms) {
            view->state = GAME_TIMED_OUT;
            view->elapsed_ms = session->config->duration_ms;
            view->remaining_ms = view->stars = 0;
            clear_scene(view, GAME_STALE_SCENE);
            return GAME_OK;
        }
        view->remaining_ms = session->config->duration_ms-view->elapsed_ms;
    }
    if (view->scene_valid && now_ms-view->captured_ms > session->config->scene_max_age_ms)
        clear_scene(view, GAME_STALE_SCENE);
    return GAME_OK;
}

GameStatus game_session_select(GameSession *session, unsigned int level_id,
                               uint64_t now_ms)
{
    const GameLevelConfig *level = NULL;
    GameStatus status;
    int i;
    if (!session || !session->config) return GAME_BAD_ARGUMENT;
    for (i = 0; i < session->config->level_count; ++i)
        if (session->config->levels[i].id == level_id) level = &session->config->levels[i];
    if (!level) return GAME_UNKNOWN_LEVEL;
    if (session->view.generation == UINT64_MAX) return GAME_BAD_STATE;
    status = game_session_tick(session, now_ms);
    if (status != GAME_OK) return status;
    session->view.generation++;
    session->view.level_id = level_id;
    session->view.state = GAME_PREPARING;
    session->view.elapsed_ms = session->view.stars = 0;
    session->view.remaining_ms = session->config->duration_ms;
    clear_scene(&session->view, GAME_INVALID_SCENE);
    session->level = level;
    session->selected_ms = now_ms;
    session->started_ms = session->last_sequence = session->last_capture_ms = 0;
    session->have_sequence = 0;
    return GAME_OK;
}

GameStatus game_session_start(GameSession *session, uint64_t now_ms)
{
    GameStatus status = game_session_tick(session, now_ms);
    if (status != GAME_OK) return status;
    if (session->view.state != GAME_PREPARING) return GAME_BAD_STATE;
    if (!session->view.scene_valid) return session->view.scene_status;
    if (!session->view.ready) return GAME_NEED_UNSOLVED;
    session->started_ms = now_ms;
    session->view.state = GAME_RUNNING;
    session->view.ready = 0;
    return GAME_OK;
}

/* Uniform scaling only, matching pc_vision/host_bridge.c. All logical poses
 * come from the public effective models; no raw pose enters the solver.
 * The +1 preserves ray_game.c's inclusive boundary (extent-1).
 * No change to epsilon, intersections, portal semantics or 17-segment cap. */
static int trace(const GameConfig *config, GameSnapshot *view)
{
    SceneObject scaled[GAME_MAX_MODELS];
    float scale = config->physics_scale;
    int i, status;
    for (i = 0; i < view->object_count; ++i) {
        scaled[i] = view->objects[i];
        scaled[i].center.x *= scale;
        scaled[i].center.y *= scale;
        scaled[i].source_tip.x *= scale;
        scaled[i].source_tip.y *= scale;
        scaled[i].length *= scale;
        scaled[i].width *= scale;
    }
    status = ray_game_trace(scaled, view->object_count,
                           config->width*scale+1, config->height*scale+1, &view->ray);
    for (i = 0; i < view->ray.segment_count; ++i) {
        view->ray.segments[i].start.x /= scale;
        view->ray.segments[i].start.y /= scale;
        view->ray.segments[i].end.x /= scale;
        view->ray.segments[i].end.y /= scale;
    }
    view->render_budget_exceeded = view->ray.segment_count > config->render_max_ray_segments;
    return status;
}

static int constrain(const GameSession *session, const GameSceneInput *input,
                     GameSnapshot *next)
{
    const SceneObject *by_type[RAY_OBJECT_TYPE_COUNT] = {NULL};
    int i;
    if (!input->valid || input->held || !input->objects ||
        input->object_count != session->level->object_count) return 0;
    for (i = 0; i < input->object_count; ++i) {
        const SceneObject *object = &input->objects[i];
        RayPoint axis = object->type == RAY_OBJECT_SOURCE ?
                        object->source_direction : object->axis;
        if (object->type < 0 || object->type >= RAY_OBJECT_TYPE_COUNT ||
            by_type[object->type] || !isfinite(object->center.x) ||
            !isfinite(object->center.y) || !normalize(&axis) ||
            (object->type == RAY_OBJECT_SOURCE && !object->direction_valid)) return 0;
        by_type[object->type] = object;
    }
    next->object_count = session->level->object_count;
    for (i = 0; i < next->object_count; ++i) {
        const GameObjectConfig *rule = &session->level->objects[i];
        SceneObject effective = rule->anchor;
        const SceneObject *observed = by_type[effective.type];
        if (!observed) return 0;
        if (rule->motion == GAME_FREE) effective.center = observed->center;
        if (rule->motion != GAME_FIXED)
            effective.axis = effective.type == RAY_OBJECT_SOURCE ?
                             observed->source_direction : observed->axis;
        if (!model(&effective, session->config)) return 0;
        next->objects[i] = effective;
    }
    return trace(session->config, next) == 0;
}

GameStatus game_session_submit(GameSession *session, const GameSceneInput *input,
                               uint64_t now_ms)
{
    GameSnapshot next;
    GameStatus status;
    if (!input) return GAME_BAD_ARGUMENT;
    status = game_session_tick(session, now_ms);
    if (status != GAME_OK) return status;
    if (session->view.state != GAME_PREPARING && session->view.state != GAME_RUNNING)
        return GAME_BAD_STATE;
    if (input->generation != session->view.generation) return GAME_OLD_GENERATION;
    if (input->version != GAME_SCENE_VERSION) {
        clear_scene(&session->view, GAME_INVALID_SCENE);
        return GAME_INVALID_SCENE;
    }
    if (session->have_sequence && input->sequence <= session->last_sequence)
        return GAME_DUPLICATE_FRAME;
    /* Consume this sequence even if geometry is invalid: repairing/replaying
     * the same capture cannot turn it into a new scoring observation. */
    session->last_sequence = input->sequence;
    if (input->captured_ms > now_ms || input->captured_ms < session->selected_ms ||
        (session->have_sequence && input->captured_ms <= session->last_capture_ms) ||
        (session->view.state == GAME_RUNNING && input->captured_ms < session->started_ms) ||
        now_ms-input->captured_ms > session->config->scene_max_age_ms) {
        session->have_sequence = 1;
        clear_scene(&session->view, GAME_STALE_SCENE);
        return GAME_STALE_SCENE;
    }
    session->have_sequence = 1;
    session->last_capture_ms = input->captured_ms;
    next = session->view;
    if (!constrain(session, input, &next)) {
        clear_scene(&session->view, GAME_INVALID_SCENE);
        return GAME_INVALID_SCENE;
    }
    next.scene_valid = 1;
    next.scene_sequence = input->sequence;
    next.captured_ms = input->captured_ms;
    next.scene_status = GAME_OK;
    next.ready = next.state == GAME_PREPARING && !next.ray.success;
    if (next.state == GAME_PREPARING && next.ray.success)
        next.scene_status = GAME_NEED_UNSOLVED;
    if (next.state == GAME_RUNNING && next.ray.success) {
        next.state = GAME_CLEARED;
        next.elapsed_ms = input->captured_ms-session->started_ms;
        next.remaining_ms = session->config->duration_ms-next.elapsed_ms;
        next.stars = next.elapsed_ms < session->config->star_threshold_ms[0] ? 3U :
                     next.elapsed_ms < session->config->star_threshold_ms[1] ? 2U : 1U;
    }
    session->view = next;
    return GAME_OK;
}

const GameSnapshot *game_session_snapshot(const GameSession *session)
{
    return session ? &session->view : NULL;
}
