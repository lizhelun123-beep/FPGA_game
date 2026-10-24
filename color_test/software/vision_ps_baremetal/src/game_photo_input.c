#include "game_photo_input.h"
#include <stdlib.h>
#include <string.h>

void game_photo_close(GamePhotoInput *input)
{
    unsigned i;
    if (!input) return;
    for (i=0;i<GAME_MAX_LEVELS;++i) { free(input->pixels[i]); input->pixels[i]=NULL; }
}
int game_photo_load(GamePhotoInput *input,const char *directory)
{
    unsigned i;
    if (!input || !directory) return 0;
    /* Zero initialized, single owner. Never overwrite an existing allocation. */
    for (i=0;i<GAME_MAX_LEVELS;++i) if (input->pixels[i]) return 0;
    for (i=0;i<GAME_MAX_LEVELS;++i) {
        char path[4096];
        FILE *f;
        int n=snprintf(path,sizeof path,"%s/%03u.bgr",directory,75+i),ok;
        if (n<0 || (size_t)n>=sizeof path) goto failed;
        input->pixels[i]=malloc(GAME_PHOTO_BYTES);
        if (!input->pixels[i]) goto failed;
        f=fopen(path,"rb");
        if (!f) goto failed;
        ok=fread(input->pixels[i],1,GAME_PHOTO_BYTES,f)==GAME_PHOTO_BYTES &&
           fgetc(f)==EOF && !ferror(f);
        if (fclose(f)) ok=0;
        if (!ok) goto failed;
    }
    return 1;
failed:
    game_photo_close(input);
    return 0;
}
int game_photo_detect(GamePhotoInput *input,unsigned level,
                      GameCaptureStamp stamp,GameDetectionFrame *frame)
{
    int count;
    if (!input || !frame || level<1 || level>GAME_MAX_LEVELS ||
        !input->pixels[level-1] || !stamp.generation || !stamp.sequence) return 0;
    count=vision_detect_bgr888(input->pixels[level-1],1280,720,3840,
                             input->detections,VISION_MAX_DETECTIONS);
    *frame=(GameDetectionFrame){stamp,count>=0,0,input->detections,count};
    return 1;
}
int game_photo_write(const GameDetectionFrame *frame,unsigned level,FILE *out)
{
    int i;
    if (!frame || !out || frame->count>VISION_MAX_DETECTIONS) return 0;
    if (fprintf(out,"PHOTO_DETECTION photo=%03u level=%u count=%d valid=%d held=%d\n",
                74+level,level,frame->count,frame->valid,frame->held)<0) return 0;
    for (i=0;i<frame->count;++i) {
        const VisionDetection *d=&frame->detections[i];
        if (fprintf(out,"detected=%s center=%d,%d axis=%.6g,%.6g direction_valid=%d direction=%.6g,%.6g tip=%d,%d\n",
                    vision_type_name(d->type),d->center_x,d->center_y,d->axis_x,d->axis_y,
                    d->direction_valid,d->source_direction_x,d->source_direction_y,
                    d->source_tip_x,d->source_tip_y)<0) return 0;
    }
    return 1;
}
