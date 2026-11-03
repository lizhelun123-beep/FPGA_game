#ifndef BEAM_CONTROL_STATE_H
#define BEAM_CONTROL_STATE_H

#include "beam_control_protocol.h"
#include "game_beam.h"

typedef struct {
    BeamControlMessage level;
    int ready, pose_enabled, display_submitted;
} BeamControlState;

/* PC generation/nonce identify commands. Camera generation/sequence/time stay
 * in the capture owner's namespace and are never replaced by PC identities. */
int beam_control_receive(BeamControlState *state, GameBeam *beam,
                         const BeamControlMessage *message, uint64_t now_ms,
                         char *response, size_t capacity);
void beam_control_display_submitted(BeamControlState *state);
/* Call only after the existing display owner's retirement fence succeeds. */
int beam_control_display_retired(BeamControlState *state, uint64_t now_ms,
                                 char *response, size_t capacity);

#endif
