#include "beam_control_protocol.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    BeamControlMessage message;
    char line[BEAM_CONTROL_MAX_LINE];
    int length=beam_control_format_ready(line,sizeof line,3,7,72000,500000,
                                          1000000,0,11,1234);
    if (argc==2) {
        if (!beam_control_parse(argv[1],strlen(argv[1]),&message) ||
            message.type!=BEAM_CONTROL_LEVEL) return 3;
        length=beam_control_format_ready(line,sizeof line,message.level_id,message.generation,
            message.x_milli,message.y_milli,message.dx_micro,message.dy_micro,message.nonce,1234);
        if (length<0) return 4;
        fputs(line,stdout);
        return 0;
    }
    if (length<0 || !beam_control_parse(line,(size_t)length,&message) ||
        message.type!=BEAM_CONTROL_READY || message.level_id!=3U ||
        message.generation!=7U || message.x_milli!=72000 ||
        message.nonce!=11U || message.board_ms!=1234U) return 1;
    line[length-4]^='1';
    if (beam_control_parse(line,(size_t)length,&message)) return 2;
    puts("PASS_BEAM_CONTROL_PROTOCOL_CRC_AND_FIELDS");
    return 0;
}
