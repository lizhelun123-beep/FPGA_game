#include "beam_control_state.h"

static int same_level(const BeamControlMessage *a, const BeamControlMessage *b)
{
    return a->level_id==b->level_id && a->generation==b->generation &&
        a->nonce==b->nonce && a->x_milli==b->x_milli && a->y_milli==b->y_milli &&
        a->dx_micro==b->dx_micro && a->dy_micro==b->dy_micro;
}

static int ready_line(const BeamControlState *s, uint64_t now,
                      char *response, size_t capacity)
{
    const BeamControlMessage *m=&s->level;
    return beam_control_format_ready(response,capacity,m->level_id,m->generation,
        m->x_milli,m->y_milli,m->dx_micro,m->dy_micro,m->nonce,now);
}

int beam_control_receive(BeamControlState *s, GameBeam *beam,
                         const BeamControlMessage *m, uint64_t now,
                         char *response, size_t capacity)
{
    if (!s || !beam || !m) return -1;
    if (m->type==BEAM_CONTROL_LEVEL) {
        GameBeamConfig config=beam->config;
        if (s->level.nonce==m->nonce && s->level.generation==m->generation) {
            if (!same_level(&s->level,m))
                return beam_control_format_error(response,capacity,4,m->generation,m->nonce);
            /* Retries replay acknowledgements; they never reset B or turn off
             * a stream that has already started. */
            return s->ready ? ready_line(s,now,response,capacity) : 0;
        }
        if (s->level.nonce==m->nonce && m->generation<s->level.generation)
            return beam_control_format_error(response,capacity,5,m->generation,m->nonce);
        config.emitter_point.x=(float)m->x_milli/1000.0f;
        config.emitter_point.y=(float)m->y_milli/1000.0f;
        config.emitter_direction.x=(float)m->dx_micro/1000000.0f;
        config.emitter_direction.y=(float)m->dy_micro/1000000.0f;
        if (game_beam_reconfigure(beam,&config,beam->view.generation,now)!=GAME_BEAM_OK)
            return beam_control_format_error(response,capacity,1,m->generation,m->nonce);
        s->level=*m;
        s->ready=s->pose_enabled=s->display_submitted=0;
        return 0; /* READY follows the newly rendered HDMI frame's fence. */
    }
    if (m->generation!=s->level.generation || m->nonce!=s->level.nonce)
        return beam_control_format_error(response,capacity,3,m->generation,m->nonce);
    if (m->type==BEAM_CONTROL_START && s->ready) {
        s->pose_enabled=1;
        return beam_control_format_started(response,capacity,s->level.level_id,
                                           m->generation,m->nonce,now);
    }
    if (m->type==BEAM_CONTROL_RESET) {
        GameBeamConfig config=beam->config;
        if (game_beam_reconfigure(beam,&config,beam->view.generation,now)!=GAME_BEAM_OK)
            return beam_control_format_error(response,capacity,2,m->generation,m->nonce);
        s->ready=s->pose_enabled=s->display_submitted=0;
        s->level.level_id=0;
        return beam_control_format_reset_ack(response,capacity,m->generation,m->nonce,now);
    }
    return beam_control_format_error(response,capacity,3,m->generation,m->nonce);
}

void beam_control_display_submitted(BeamControlState *s)
{
    if (s && s->level.level_id && !s->ready) s->display_submitted=1;
}

int beam_control_display_retired(BeamControlState *s, uint64_t now,
                                 char *response, size_t capacity)
{
    if (!s || !s->display_submitted || s->ready || !s->level.level_id) return 0;
    s->ready=1;
    return ready_line(s,now,response,capacity);
}
