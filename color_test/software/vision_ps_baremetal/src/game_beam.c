#include "game_beam.h"

#include <math.h>
#include <string.h>

static int finite_point(RayPoint p)
{
    return isfinite(p.x) && isfinite(p.y);
}

static int unit(RayPoint *p)
{
    float n;
    if (!p || !finite_point(*p)) return 0;
    n = hypotf(p->x, p->y);
    if (!isfinite(n) || n <= 1.0e-6f) return 0;
    p->x /= n;
    p->y /= n;
    return 1;
}

static int valid_config(const GameBeamConfig *c)
{
    RayPoint direction;
    if (!c || c->version != GAME_BEAM_CONFIG_VERSION ||
        c->width < 2 || c->height < 2 || c->width > 16384 || c->height > 16384 ||
        (c->max_age_ms != 0 && c->max_age_ms != 250
#ifdef BEAM_PYNQ_RUNTIME
         && c->max_age_ms != 600
#endif
         ) || !finite_point(c->emitter_point) ||
        c->emitter_point.x < 0 || c->emitter_point.x > (float)c->width-1 ||
        c->emitter_point.y < 0 || c->emitter_point.y > (float)c->height-1 ||
        (c->stability_algorithm != VISION_STABILITY_A &&
         c->stability_algorithm != VISION_STABILITY_B) ||
        c->detector_profile < VISION_PROFILE_LEGACY || c->detector_profile > VISION_PROFILE_RESTORED ||
        c->portal_b_exit_side < -1 || c->portal_b_exit_side > 1 ||
        (c->stability_support_gap_ms != 250U && c->stability_support_gap_ms != 350U &&
         c->stability_support_gap_ms != 500U) ||
        c->display_timeout_ms > 6000 || c->display_dropout_ms > 250 ||
        (c->display_timeout_ms && c->display_dropout_ms > c->display_timeout_ms))
        return 0;
    direction = c->emitter_direction;
    return unit(&direction);
}

static void clear_view(GameBeam *beam, GameBeamStatus status)
{
    GameBeamSnapshot *v = &beam->view;
    uint64_t generation = v->generation, sequence = v->sequence, captured = v->captured_ms;
    unsigned width = beam->config.width, height = beam->config.height;
    RayPoint point = beam->config.emitter_point, direction = beam->config.emitter_direction;
    unsigned raw = v->raw_mask, supported = v->supported_mask;
    unsigned pending = v->pending_mask, missing = v->missing_mask, restricted = v->restricted_mask;
    memset(v, 0, sizeof(*v));
    v->generation = generation;
    v->width = width; v->height = height;
    v->emitter_point = point; v->emitter_direction = direction;
    v->sequence = sequence; v->captured_ms = captured;
    v->raw_mask = raw; v->supported_mask = supported;
    v->pending_mask = pending; v->missing_mask = missing; v->restricted_mask = restricted;
    v->status = status;
}

static int admit(const GameBeam *beam, const GameDetectionFrame *frame,
                 uint64_t now_ms)
{
    if (!beam || !beam->initialized || !frame || !frame->valid || frame->held ||
        frame->stamp.generation != beam->view.generation ||
        !frame->stamp.sequence || !frame->stamp.captured_ms ||
        frame->stamp.captured_ms > now_ms ||
        (beam->config.max_age_ms &&
         now_ms-frame->stamp.captured_ms > beam->config.max_age_ms) ||
        (beam->have_sequence && (frame->stamp.sequence <= beam->last_sequence ||
                                 frame->stamp.captured_ms <= beam->last_capture_ms)))
        return 0;
    return 1;
}

static unsigned class_mask(const VisionDetection *d, int count)
{
    unsigned mask = 0;
    int i;
    for (i=0; i<count; ++i) {
        unsigned bit;
        if (!d[i].geometry_is_effective || (unsigned)d[i].type > VISION_WALL ||
            d[i].type == VISION_SOURCE) return 0;
        bit = 1U << (unsigned)d[i].type;
        if (mask & bit) return 0;
        mask |= bit;
    }
    return mask;
}

GameBeamStatus game_beam_init(GameBeam *beam, const GameBeamConfig *config,
                              uint64_t generation, uint64_t now_ms)
{
    if (!beam || !valid_config(config) || !generation) return GAME_BEAM_BAD_CONFIG;
    memset(beam, 0, sizeof(*beam));
    beam->config = *config;
    (void)unit(&beam->config.emitter_direction);
    beam->initialized = 1;
    beam->reset_ms = beam->last_now_ms = now_ms;
    beam->view.generation = generation;
    beam->view.width = config->width; beam->view.height = config->height;
    beam->view.emitter_point = config->emitter_point;
    beam->view.emitter_direction = beam->config.emitter_direction;
    beam->view.status = GAME_BEAM_NO_FRAME;
    vision_stabilizer_timed_reset(&beam->stabilizer);
    return GAME_BEAM_OK;
}

GameBeamStatus game_beam_reconfigure(GameBeam *beam, const GameBeamConfig *config,
                                     uint64_t generation, uint64_t now_ms)
{
    GameBeamSnapshot *view;
    if (!beam || !beam->initialized || !valid_config(config)) return GAME_BEAM_BAD_CONFIG;
    if (now_ms<beam->last_now_ms) return GAME_BEAM_BAD_TIME;
    if (!generation || generation < beam->view.generation) return GAME_BEAM_OLD_GENERATION;
    beam->config = *config;
    (void)unit(&beam->config.emitter_direction);
    if (generation == beam->view.generation) {
        /* A new logical level may share the capture owner's generation.
         * Clear its scene/filter without changing original camera stamps. */
        beam->last_now_ms=beam->reset_ms=now_ms;
        beam->last_sequence=beam->last_capture_ms=0;
        beam->have_sequence=0;
        beam->have_display=beam->have_absence=0;
        memset(&beam->display_view,0,sizeof beam->display_view);
        vision_stabilizer_timed_reset(&beam->stabilizer);
        view=&beam->view;
        memset(view,0,sizeof *view);
        view->generation=generation;
        view->width=beam->config.width; view->height=beam->config.height;
        view->emitter_point=beam->config.emitter_point;
        view->emitter_direction=beam->config.emitter_direction;
        view->status=GAME_BEAM_NO_FRAME;
        return GAME_BEAM_OK;
    }
    return game_beam_reset(beam,generation,now_ms);
}

GameBeamStatus game_beam_reset(GameBeam *beam, uint64_t generation,
                               uint64_t now_ms)
{
    if (!beam || !beam->initialized || generation <= beam->view.generation)
        return GAME_BEAM_OLD_GENERATION;
    beam->view.generation = generation;
    beam->last_now_ms = beam->reset_ms = now_ms;
    beam->last_sequence = beam->last_capture_ms = 0;
    beam->have_sequence = 0;
    vision_stabilizer_timed_reset(&beam->stabilizer);
    /* A generation reset is an explicit display reset; do not retain the
     * previous generation's camera geometry or ray across a new session. */
    beam->have_display = beam->have_absence = 0;
    memset(&beam->display_view, 0, sizeof(beam->display_view));
    beam->view.sequence = beam->view.captured_ms = 0;
    clear_view(beam, GAME_BEAM_NO_FRAME);
    return GAME_BEAM_OK;
}

GameBeamStatus game_beam_submit(GameBeam *beam, const GameDetectionFrame *frame,
                                unsigned restricted_mask, uint64_t now_ms)
{
    VisionDetection stable[VISION_MAX_DETECTIONS];
    VisionTimedStatus timed;
    SceneObject objects[GAME_BEAM_MAX_OBJECTS];
    RayGameResult ray;
    unsigned raw_mask;
    int count, object_count, result, i;
    if (!beam || !beam->initialized) return GAME_BEAM_BAD_ARGUMENT;
    if (now_ms < beam->last_now_ms) return GAME_BEAM_BAD_TIME;
    beam->last_now_ms = now_ms;
    if (!admit(beam, frame, now_ms)) {
        if (frame && frame->stamp.generation == beam->view.generation &&
            frame->stamp.sequence && beam->have_sequence &&
            frame->stamp.sequence <= beam->last_sequence)
            return GAME_BEAM_DUPLICATE_FRAME;
        if (beam->config.max_age_ms && frame &&
            frame->stamp.generation == beam->view.generation &&
            frame->stamp.captured_ms && frame->stamp.captured_ms <= now_ms &&
            now_ms-frame->stamp.captured_ms > beam->config.max_age_ms)
            clear_view(beam, GAME_BEAM_STALE);
        return GAME_BEAM_STALE;
    }
    /* The detector may expose more raw candidates than the five unique game
     * classes (for example two Portal B bodies).  That is observation
     * ambiguity, not a caller/API failure.  Let class_mask reject duplicate,
     * SOURCE or invalid identities as INVALID_GEOMETRY so the display owner
     * can retain its last complete frame. */
    if (frame->count < 0 || frame->count > VISION_MAX_DETECTIONS ||
        (frame->count && !frame->detections)) return GAME_BEAM_BAD_ARGUMENT;
    raw_mask = class_mask(frame->detections, frame->count);
    if (frame->count && !raw_mask) {
        clear_view(beam, GAME_BEAM_INVALID_GEOMETRY);
        return GAME_BEAM_INVALID_GEOMETRY;
    }
    beam->last_sequence = frame->stamp.sequence;
    beam->last_capture_ms = frame->stamp.captured_ms;
    beam->have_sequence = 1;
    count = vision_stabilizer_update_timed_gap(&beam->stabilizer, frame->detections,
                                           frame->count, frame->stamp.captured_ms,
                                           beam->config.stability_algorithm,
                                           stable, VISION_MAX_DETECTIONS, &timed,
                                           beam->config.stability_support_gap_ms);
    beam->view.raw_mask = raw_mask;
    beam->view.supported_mask = timed.supported_mask;
    beam->view.pending_mask = timed.pending_mask;
    /* The shared stabilizer has six historical slots; this beam has five
     * physical classes and never requires an observed SOURCE. */
    beam->view.missing_mask = timed.missing_mask & GAME_BEAM_PHYSICAL_MASK;
    beam->view.restricted_mask = restricted_mask;
    beam->view.sequence = frame->stamp.sequence;
    beam->view.captured_ms = frame->stamp.captured_ms;
    if (!timed.timestamp_accepted) return GAME_BEAM_DUPLICATE_FRAME;
    if (beam->have_display && (beam->display_view.raw_mask & ~raw_mask)) {
        if (!beam->have_absence) {
            beam->absence_since_ms = frame->stamp.captured_ms;
            beam->have_absence = 1;
        }
        if (frame->stamp.captured_ms-beam->absence_since_ms < beam->config.display_dropout_ms) {
            clear_view(beam, GAME_BEAM_UNAVAILABLE);
            return GAME_BEAM_UNAVAILABLE;
        }
    } else beam->have_absence = 0;
    if (restricted_mask) { clear_view(beam, GAME_BEAM_RESTRICTED); return GAME_BEAM_RESTRICTED; }
    if (timed.pending_mask) { clear_view(beam, GAME_BEAM_PENDING); return GAME_BEAM_PENDING; }
    if (count < 0 || count > GAME_BEAM_MAX_OBJECTS) {
        clear_view(beam, GAME_BEAM_UNAVAILABLE); return GAME_BEAM_UNAVAILABLE;
    }
    for (i=0; i<count; ++i)
        if (stable[i].type == VISION_SOURCE || !stable[i].geometry_is_effective)
            { clear_view(beam, GAME_BEAM_INVALID_GEOMETRY); return GAME_BEAM_INVALID_GEOMETRY; }
    object_count = ray_game_scene_from_detections(stable, count, objects,
                                                   GAME_BEAM_MAX_OBJECTS);
    if (object_count != count || object_count > GAME_BEAM_MAX_OBJECTS) {
        clear_view(beam, GAME_BEAM_INVALID_GEOMETRY); return GAME_BEAM_INVALID_GEOMETRY;
    }
    result = ray_game_trace_from_emitter_policy(objects, object_count,
                                         (float)beam->config.width,
                                         (float)beam->config.height,
                                         beam->config.emitter_point,
                                         beam->config.emitter_direction,
                                         beam->config.portal_b_exit_side, &ray);
    if (result < 0) { clear_view(beam, GAME_BEAM_INVALID_GEOMETRY); return GAME_BEAM_INVALID_GEOMETRY; }
    beam->view.object_count = object_count;
    memcpy(beam->view.objects, objects, (size_t)object_count*sizeof(objects[0]));
    beam->view.ray = ray;
    beam->view.valid = 1;
    beam->view.status = GAME_BEAM_OK;
    beam->display_view = beam->view;
    beam->have_display = 1;
    beam->have_absence = 0;
    return GAME_BEAM_OK;
}

GameBeamStatus game_beam_tick(GameBeam *beam, uint64_t now_ms)
{
    if (!beam || !beam->initialized) return GAME_BEAM_BAD_ARGUMENT;
    if (now_ms < beam->last_now_ms) return GAME_BEAM_BAD_TIME;
    beam->last_now_ms = now_ms;
    if (!beam->have_sequence || (beam->config.max_age_ms &&
        now_ms-beam->last_capture_ms > beam->config.max_age_ms)) {
        clear_view(beam, GAME_BEAM_STALE);
        return GAME_BEAM_STALE;
    }
    return GAME_BEAM_OK;
}

const GameBeamSnapshot *game_beam_snapshot(const GameBeam *beam)
{
    return beam && beam->initialized ? &beam->view : NULL;
}

int game_beam_display_snapshot(const GameBeam *beam, uint64_t now_ms,
                                GameBeamSnapshot *snapshot)
{
    uint64_t limit;
    if (!beam || !beam->initialized || !snapshot || now_ms < beam->last_now_ms) return 0;
    if (beam->view.valid && (!beam->config.max_age_ms ||
        now_ms-beam->view.captured_ms <= beam->config.max_age_ms)) {
        *snapshot = beam->view;
        return 1;
    }
    if (!beam->have_display || beam->display_view.generation != beam->view.generation ||
        now_ms < beam->display_view.captured_ms) return 0;
    /* Hold the last complete camera/model/ray snapshot while new input is
     * unconfirmed, including a short miss. display_dropout_ms still controls
     * measured removal admission in submit(), not the age of this picture. */
    limit = beam->config.display_timeout_ms;
    if (!limit || now_ms-beam->display_view.captured_ms >= limit) return 0;
    return game_beam_retained_snapshot(beam,snapshot);
}

int game_beam_retained_snapshot(const GameBeam *beam, GameBeamSnapshot *snapshot)
{
    if (!beam || !beam->initialized || !snapshot || !beam->have_display ||
        beam->display_view.generation != beam->view.generation) return 0;
    *snapshot = beam->display_view;
    snapshot->valid = 0;
    snapshot->display_stale = 1;
    snapshot->status = beam->view.status;
    snapshot->ray.success = 0; /* No successful result from a display hold. */
    return 1;
}

const char *game_beam_status_name(GameBeamStatus status)
{
    static const char *const names[] = {
        "OK", "BAD_ARGUMENT", "BAD_CONFIG", "BAD_TIME", "OLD_GENERATION",
        "DUPLICATE_FRAME", "STALE", "UNAVAILABLE", "INVALID_GEOMETRY",
        "RESTRICTED", "PENDING", "NO_FRAME"
    };
    return (unsigned)status < sizeof names/sizeof names[0] ? names[(unsigned)status] : "UNKNOWN";
}

int game_beam_render(const GameBeamSnapshot *snapshot, const VisionCanvas *canvas)
{
    int i;
    if (!snapshot || !canvas || !vision_canvas_valid(canvas) ||
        canvas->width != (int)snapshot->width || canvas->height != (int)snapshot->height)
        return -1;
    /* First-version real camera presentation: retain the physical background,
     * draw the ray and virtual emitter, without filling over real objects. */
    for (i=0; i<snapshot->ray.segment_count; ++i) {
        VisionPoint a={snapshot->ray.segments[i].start.x, snapshot->ray.segments[i].start.y};
        VisionPoint b={snapshot->ray.segments[i].end.x, snapshot->ray.segments[i].end.y};
        vision_canvas_line(canvas, a, b, 3, 0);
        /* STALE is carried by metadata/the age label. Alternating supported
         * and pending observations must not pulse the retained ray's color. */
        vision_canvas_line(canvas, a, b, 2, 0xFFFF00U);
    }
    vision_canvas_circle(canvas, (VisionPoint){snapshot->emitter_point.x, snapshot->emitter_point.y}, 8, 2, 0x00FFFFU);
    vision_canvas_line(canvas,
        (VisionPoint){snapshot->emitter_point.x, snapshot->emitter_point.y},
        (VisionPoint){snapshot->emitter_point.x+snapshot->emitter_direction.x*24,
                      snapshot->emitter_point.y+snapshot->emitter_direction.y*24}, 2, 0x00FFFFU);
    return 0;
}
