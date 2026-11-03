#include "beam_pose_protocol.h"
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
int main(void)
{
    GameBeamSnapshot s;
    char line[BEAM_POSE_MAX_LINE+1U];
    const int kinds[5]={0,1,2,3,5};
    int i, n;
#ifdef _WIN32
    _setmode(_fileno(stdout),_O_BINARY);
#endif
    memset(&s,0,sizeof s);
    s.generation=1; s.sequence=456; s.captured_ms=1000;
    s.width=1280; s.height=720; s.valid=1; s.raw_mask=0x2f;
    s.object_count=5;
    for (i=0; i<5; ++i) {
        s.objects[i].type=(RayObjectType)kinds[i];
        s.objects[i].center=(RayPoint){100.25f+100.0f*(float)i,500.5f};
        s.objects[i].axis=(RayPoint){0.6f,0.8f};
        s.objects[i].length=140; s.objects[i].width=30;
    }
    n=beam_pose_encode(line,sizeof line,&s,4,1099);
    if (n<0 || n!=(int)BEAM_POSE_MAX_LINE) return 1;
    fwrite(line,1,(size_t)n,stdout);
    s.valid=0; s.sequence++; s.captured_ms++; s.status=GAME_BEAM_PENDING;
    s.pending_mask=1;
    s.raw_mask&=~(1U<<VISION_PORTAL_A);
    s.missing_mask=(1U<<VISION_SOURCE)|(1U<<VISION_PORTAL_A);
    n=beam_pose_encode(line,sizeof line,&s,5,1100);
    if (n<0) return 2;
    fwrite(line,1,(size_t)n,stdout);
    return 0;
}
