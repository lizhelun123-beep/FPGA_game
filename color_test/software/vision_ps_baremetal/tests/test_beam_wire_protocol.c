#include "beam_wire_protocol.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static void write_packet(const char *wire, int n)
{
    assert(n>0 && n<=(int)BEAM_WIRE_MAX_PACKET);
    assert(fwrite(wire,1,(size_t)n,stdout)==(size_t)n);
}
int main(int argc, char **argv)
{
    char wire[BEAM_WIRE_MAX_PACKET], internal[BEAM_CONTROL_MAX_LINE+1];
    BeamWireParser parser={0};
    BeamWirePacket packet={0};
    BeamControlMessage level={0};
    int n,i;
#ifdef _WIN32
    _setmode(_fileno(stdin),_O_BINARY);
    _setmode(_fileno(stdout),_O_BINARY);
#endif
    level.type=BEAM_CONTROL_LEVEL; level.level_id=2; level.generation=0xfedcba9876543210ULL;
    level.nonce=0xff00ff00U; level.x_milli=1234567; level.y_milli=700125;
    level.dx_micro=-600000; level.dy_micro=800000;
    if (argc>1 && !strcmp(argv[1],"roundtrip")) {
        int byte;
        while ((byte=getchar())!=EOF) {
            if (!beam_wire_feed(&parser,(uint8_t)byte,&packet)) continue;
            if (packet.type==BEAM_WIRE_SYNC && packet.length==4) {
                write_packet(wire,beam_wire_sync_reply(wire,sizeof wire,
                    (uint32_t)beam_wire_le(packet.payload,4),123400,123405));
            } else {
                BeamControlMessage m;
                assert(beam_wire_control_decode(&packet,&m));
                assert(packet.type==BEAM_WIRE_LEVEL || packet.type==BEAM_WIRE_START || packet.type==BEAM_WIRE_RESET);
                m.board_ms=123456;
                if (m.type==BEAM_CONTROL_LEVEL) m.type=BEAM_CONTROL_READY;
                else if (m.type==BEAM_CONTROL_START) { m.type=BEAM_CONTROL_STARTED; m.level_id=2; }
                else m.type=BEAM_CONTROL_RESET_ACK;
                write_packet(wire,beam_wire_control_encode(wire,sizeof wire,&m));
            }
        }
        return 0;
    }
    /* Round-trip every possible payload byte through the actual C framing. */
    for (i=0;i<256;++i) {
        uint8_t p[BEAM_WIRE_MAX_PAYLOAD];
        unsigned j;
        for (j=0;j<sizeof p;++j) p[j]=(uint8_t)(i+(int)j);
        n=beam_wire_encode(wire,sizeof wire,BEAM_WIRE_ERROR,p,sizeof p);
        for (j=0;j<(unsigned)n;++j) {
            int complete=beam_wire_feed(&parser,(uint8_t)wire[j],&packet);
            assert(complete==(j==(unsigned)n-1U));
        }
        assert(packet.length==sizeof p && !memcmp(packet.payload,p,sizeof p));
    }
    {
        GameBeamSnapshot s={0};
        int kinds[5]={RAY_OBJECT_MIRROR,RAY_OBJECT_PORTAL_A,RAY_OBJECT_PORTAL_B,RAY_OBJECT_TARGET,RAY_OBJECT_WALL};
        s.generation=17; s.sequence=1234567890123ULL; s.captured_ms=123400;
        s.width=1280; s.height=720; s.valid=1; s.status=GAME_BEAM_OK;
        s.raw_mask=GAME_BEAM_PHYSICAL_MASK; s.object_count=5;
        for (i=0;i<5;++i) {
            SceneObject *o=&s.objects[i];
            float angle=(float)i*0.71f;
            o->type=(RayObjectType)kinds[i]; o->center.x=100.25f+150.0f*(float)i; o->center.y=301.125f;
            o->axis.x=cosf(angle); o->axis.y=sinf(angle); o->length=164.125f; o->width=55.25f;
        }
        n=beam_wire_pose_encode(wire,sizeof wire,&s,&level,0xfffffff0U,123456);
        assert(n==130);
        write_packet(wire,n);
        s.valid=0; s.status=GAME_BEAM_PENDING; s.pending_mask=2; s.missing_mask=2|16;
        n=beam_wire_pose_encode(wire,sizeof wire,&s,&level,0xfffffff1U,123460);
        assert(n==70);
        write_packet(wire,n);
        s.valid=1; s.status=GAME_BEAM_OK; s.objects[0].axis.x=NAN;
        assert(beam_wire_pose_encode(wire,sizeof wire,&s,&level,1,123456)<0);
    }
    n=beam_control_format_ready(internal,sizeof internal,level.level_id,level.generation,
        level.x_milli,level.y_milli,level.dx_micro,level.dy_micro,level.nonce,123456);
    write_packet(wire,beam_wire_control_reply(wire,sizeof wire,internal,(size_t)n));
    write_packet(wire,beam_wire_sync_reply(wire,sizeof wire,0x00ff1200U,123400,123405));
    return 0;
}
