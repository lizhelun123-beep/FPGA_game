#include "beam_control_state.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    GameBeam beam;
    GameBeamConfig config={GAME_BEAM_CONFIG_VERSION,1280,720,
                           {32,500},{1,0},0,VISION_STABILITY_B,2,6000,250,1,350};
    BeamControlState state={0};
    BeamControlMessage level={0}, start={0}, ack;
    GameDetectionFrame frame={{1,100,1000},1,0,NULL,0};
    char response[BEAM_CONTROL_MAX_LINE+1];
    int n;
    assert(game_beam_init(&beam,&config,1,1)==GAME_BEAM_OK);
    level.type=BEAM_CONTROL_LEVEL; level.level_id=2; level.generation=27;
    level.x_milli=400000; level.y_milli=200000;
    level.dx_micro=0; level.dy_micro=1000000; level.nonce=123;
    start.type=BEAM_CONTROL_START; start.generation=27; start.nonce=123;
    assert(!state.pose_enabled);
    n=beam_control_receive(&state,&beam,&level,100,response,sizeof response);
    assert(n==0 && !state.ready && !state.pose_enabled);
    assert(beam.view.generation==1 && fabsf(beam.config.emitter_point.x-400)<.001f);
    n=beam_control_receive(&state,&beam,&start,101,response,sizeof response);
    assert(n>0 && !state.pose_enabled); /* A premature START has no effect. */
    assert(beam_control_display_retired(&state,102,response,sizeof response)==0);
    beam_control_display_submitted(&state);
    n=beam_control_display_retired(&state,103,response,sizeof response);
    assert(n>0 && state.ready && !state.pose_enabled);
    assert(beam_control_parse(response,(size_t)n,&ack) && ack.type==BEAM_CONTROL_READY);
    assert(ack.generation==27 && ack.nonce==123 && ack.x_milli==400000);
    n=beam_control_receive(&state,&beam,&start,104,response,sizeof response);
    assert(n>0 && state.pose_enabled);
    assert(beam_control_parse(response,(size_t)n,&ack) && ack.type==BEAM_CONTROL_STARTED);
    /* A lost ACK may cause repeated LEVEL/START; neither clears the scene. */
    beam.have_sequence=1; beam.last_sequence=99;
    assert(beam_control_receive(&state,&beam,&level,105,response,sizeof response)>0);
    assert(state.pose_enabled && beam.have_sequence && beam.last_sequence==99);
    assert(beam_control_receive(&state,&beam,&start,106,response,sizeof response)>0);
    assert(state.pose_enabled);
    /* Next PC generation still consumes original camera generation 1. */
    level.generation=28;
    assert(beam_control_receive(&state,&beam,&level,107,response,sizeof response)==0);
    assert(!state.pose_enabled && !state.ready && beam.view.generation==1);
    n=beam_control_receive(&state,&beam,&start,108,response,sizeof response);
    assert(n>0 && !state.pose_enabled);
    assert(game_beam_submit(&beam,&frame,0,1001)!=GAME_BEAM_OLD_GENERATION);
    assert(beam.view.generation==1 && beam.view.sequence==100 && beam.view.captured_ms==1000);
    start.type=BEAM_CONTROL_RESET; start.generation=28;
    assert(beam_control_receive(&state,&beam,&start,1002,response,sizeof response)>0);
    assert(!state.pose_enabled && !state.ready && !state.level.level_id);
    /* A new PC process may begin at generation 1 with a different nonce. */
    level.generation=1; level.nonce=456;
    assert(beam_control_receive(&state,&beam,&level,1003,response,sizeof response)==0);
    assert(state.level.nonce==456 && beam.view.generation==1);
    puts("PASS_BOARD_HANDSHAKE_DISPLAY_FENCE_POSE_GATE_RETRY_LEVEL_RESET_CAMERA_IDENTITY");
    return 0;
}
