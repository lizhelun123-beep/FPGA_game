#include "game_render.h"
#include <limits.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)

static FILE *bytes(const unsigned char *data,size_t size)
{
    FILE *f=tmpfile();
    CHECK(f!=NULL);
    CHECK(fwrite(data,1,size,f)==size);
    rewind(f);
    return f;
}

int main(void)
{
    unsigned char source[16]={1,2,3,255,0,255,99,99,4,5,6,7,8,9,99,99};
    unsigned char target[26],before[26],loaded[16];
    const unsigned char packed[]={1,2,3,255,0,255,4,5,6,7,8,9,42};
    VisionCanvas asset={source,2,2,8,16},canvas={target,3,2,14,26},input={loaded,2,2,8,16};
    FILE *f;
    int i;
    memset(target,0xAA,sizeof target);
    CHECK(game_render_blit(&asset,&canvas,1,0,1,0xFF00FFU)==GAME_RENDER_OK);
    CHECK(memcmp(target+3,source,3)==0);
    CHECK(target[6]==0xAA && target[7]==0xAA && target[8]==0xAA);
    CHECK(memcmp(target+17,source+8,6)==0);
    for (i=9;i<14;++i) CHECK(target[i]==0xAA);
    for (i=23;i<26;++i) CHECK(target[i]==0xAA);
    CHECK(game_render_blit(&asset,&canvas,-1,-1,0,0)==GAME_RENDER_OK);
    CHECK(memcmp(target,source+11,3)==0);
    memcpy(before,target,sizeof target);
    CHECK(game_render_blit(&asset,&canvas,INT_MIN,INT_MIN,0,0)==GAME_RENDER_OK);
    CHECK(game_render_blit(&asset,&canvas,INT_MAX,INT_MAX,0,0)==GAME_RENDER_OK);
    CHECK(game_render_blit(&asset,&canvas,0,0,2,0)==GAME_RENDER_BAD_ASSET);
    CHECK(game_render_blit(&asset,&canvas,0,0,1,0x1000000U)==GAME_RENDER_BAD_ASSET);
    CHECK(game_render_blit(&canvas,&canvas,0,0,0,0)==GAME_RENDER_BAD_BUFFER);
    CHECK(game_render_blit(NULL,&canvas,0,0,0,0)==GAME_RENDER_BAD_BUFFER);
    CHECK(memcmp(before,target,sizeof target)==0);
    memset(loaded,0xCD,sizeof loaded);
    f=bytes(packed,12);
    CHECK(game_render_read_bgr(f,&input)==GAME_RENDER_OK);
    CHECK(fclose(f)==0);
    CHECK(memcmp(loaded,packed,6)==0 && memcmp(loaded+8,packed+6,6)==0);
    CHECK(loaded[6]==0xCD && loaded[7]==0xCD && loaded[14]==0xCD && loaded[15]==0xCD);
    f=bytes(packed,11);
    CHECK(game_render_read_bgr(f,&input)==GAME_RENDER_IO_ERROR);
    CHECK(fclose(f)==0);
    f=bytes(packed,13);
    CHECK(game_render_read_bgr(f,&input)==GAME_RENDER_BAD_ASSET);
    CHECK(fclose(f)==0);
    input.capacity=13;
    memcpy(before,loaded,sizeof loaded);
    f=bytes(packed,12);
    CHECK(game_render_read_bgr(f,&input)==GAME_RENDER_BAD_BUFFER);
    CHECK(memcmp(before,loaded,sizeof loaded)==0 && ftell(f)==0);
    CHECK(fclose(f)==0);
    printf("PASS sprite file/key/clipping/stride/alias checks=%u (CPU only)\n",checks);
    return 0;
}
