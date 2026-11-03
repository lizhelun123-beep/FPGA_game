#include "beam_pose_protocol.h"
#include <math.h>
#include <string.h>

static void le(uint8_t *p, uint64_t v, unsigned n)
{
    unsigned i;
    for (i=0; i<n; ++i) { p[i]=(uint8_t)v; v>>=8; }
}
static void number(uint8_t *p, float v)
{
    uint32_t bits;
    memcpy(&bits,&v,4);
    le(p,bits,4);
}
int beam_pose_encode(char *line, size_t capacity, const GameBeamSnapshot *s,
                     uint32_t tx_sequence, uint64_t published_ms)
{
    uint8_t data[BEAM_POSE_HEADER_BYTES+BEAM_POSE_OBJECT_BYTES*GAME_BEAM_MAX_OBJECTS+4U];
    static const char hex[]="0123456789ABCDEF";
    size_t bytes, i;
    uint32_t crc=0xffffffffU;
    int count, j;
    if (!s || !line || s->object_count<0 || s->object_count>GAME_BEAM_MAX_OBJECTS ||
        s->width!=1280 || s->height!=720 || published_ms<s->captured_ms ||
        (unsigned)s->status>GAME_BEAM_NO_FRAME) return -1;
    count=s->valid && !s->display_stale ? s->object_count : 0;
    bytes=BEAM_POSE_HEADER_BYTES+BEAM_POSE_OBJECT_BYTES*(size_t)count;
    if (capacity<12U+2U*(bytes+4U)+1U) return -1;
    memset(data,0,sizeof data);
    data[0]=2; data[1]=(uint8_t)(s->valid && !s->display_stale);
    data[2]=(uint8_t)count; data[3]=VISION_PROFILE_RESTORED;
    le(data+4,tx_sequence,4);
    le(data+8,s->generation,8); le(data+16,s->sequence,8);
    le(data+24,s->captured_ms,8); le(data+32,published_ms,8);
    le(data+40,s->width,2); le(data+42,s->height,2);
    le(data+44,(unsigned)s->status,2); le(data+46,s->raw_mask,2);
    le(data+48,s->pending_mask,2);
    /* Generic timed diagnostics can include the unused SOURCE slot. It is
     * not a physical requirement in POSE2; preserve every actual missing bit. */
    le(data+50,s->missing_mask & GAME_BEAM_PHYSICAL_MASK,2);
    for (j=0; j<count; ++j) {
        const SceneObject *o=&s->objects[j];
        float values[6]={o->center.x,o->center.y,o->axis.x,o->axis.y,o->length,o->width};
        uint8_t *p=data+BEAM_POSE_HEADER_BYTES+BEAM_POSE_OBJECT_BYTES*(size_t)j;
        unsigned k;
        if ((unsigned)o->type>RAY_OBJECT_WALL || o->type==RAY_OBJECT_SOURCE ||
            o->center.x<0 || o->center.x>1279 || o->center.y<0 || o->center.y>719 ||
            o->length<=0 || o->width<=0 || fabsf(hypotf(o->axis.x,o->axis.y)-1)>0.01f)
            return -1;
        p[0]=(uint8_t)o->type; p[1]=1; /* effective, B supported, never HELD */
        for (k=0; k<6; ++k) {
            if (!isfinite(values[k])) return -1;
            number(p+4U+4U*k,values[k]);
        }
    }
    for (i=0; i<bytes; ++i) {
        unsigned bit;
        crc^=data[i];
        for (bit=0; bit<8; ++bit) crc=(crc>>1)^(0xedb88320U&(0U-(crc&1U)));
    }
    le(data+bytes,crc^0xffffffffU,4); bytes+=4;
    memcpy(line,"@POSE2:",7);
    for (i=0; i<bytes; ++i) { line[7U+2U*i]=hex[data[i]>>4]; line[8U+2U*i]=hex[data[i]&15U]; }
    memcpy(line+7U+2U*bytes,":END\n",5);
    line[12U+2U*bytes]=0;
    return (int)(12U+2U*bytes);
}
