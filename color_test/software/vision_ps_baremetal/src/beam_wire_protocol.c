#include "beam_wire_protocol.h"
#include <math.h>
#include <string.h>

uint64_t beam_wire_le(const uint8_t *p, unsigned n)
{
    uint64_t value=0;
    unsigned i;
    for (i=0;i<n;++i) value|=(uint64_t)p[i]<<(8U*i);
    return value;
}
void beam_wire_put(uint8_t *p, uint64_t value, unsigned n)
{
    unsigned i;
    for (i=0;i<n;++i) { p[i]=(uint8_t)value; value>>=8; }
}
static uint32_t crc32(const uint8_t *p, unsigned n)
{
    uint32_t crc=0xffffffffU;
    unsigned i, bit;
    for (i=0;i<n;++i) {
        crc^=p[i];
        for (bit=0;bit<8;++bit) crc=(crc>>1)^(0xedb88320U&(0U-(crc&1U)));
    }
    return crc^0xffffffffU;
}
int beam_wire_encode(char *wire, size_t capacity, unsigned type,
                     const uint8_t *payload, unsigned length)
{
    uint8_t raw[BEAM_WIRE_MAX_RAW];
    unsigned i, pos=3, code_pos=2, code=1, bytes=length+10U;
    if (!wire || !payload || !type || type>BEAM_WIRE_POSE ||
        length>BEAM_WIRE_MAX_PAYLOAD || capacity<bytes+4U) return -1;
    raw[0]='R'; raw[1]='G'; raw[2]=BEAM_WIRE_VERSION; raw[3]=(uint8_t)type;
    beam_wire_put(raw+4,length,2);
    memcpy(raw+6,payload,length);
    beam_wire_put(raw+6+length,crc32(raw,6+length),4);
    wire[0]=0; ((unsigned char *)wire)[1]=0xffU;
    /* COBS: raw is <=170 bytes, so no 254-byte continuation block is needed. */
    for (i=0;i<bytes;++i) {
        if (!raw[i]) { wire[code_pos]=(char)code; code_pos=pos++; code=1; }
        else { wire[pos++]=(char)raw[i]; ++code; }
    }
    wire[code_pos]=(char)code;
    wire[pos++]=0;
    return (int)pos;
}
int beam_wire_feed(BeamWireParser *s, uint8_t byte, BeamWirePacket *packet)
{
    uint8_t raw[BEAM_WIRE_MAX_RAW];
    unsigned in=0,out=0,i,n;
    if (!s || !packet) return 0;
    if (!s->state) { if (!byte) s->state=1; return 0; }
    if (s->state==1) {
        if (byte==0xffU) { s->state=2; s->used=0; }
        else if (byte) s->state=0;
        return 0;
    }
    if (byte) {
        if (s->used<BEAM_WIRE_MAX_ENCODED) s->encoded[s->used++]=byte;
        else { ++s->rejected; s->state=s->used=0; }
        return 0;
    }
    s->state=1;
    while (in<s->used) {
        unsigned code=s->encoded[in++];
        if (!code || in+code-1U>s->used || out+code-1U>sizeof raw) goto bad;
        for (i=1;i<code;++i) raw[out++]=s->encoded[in++];
        if (code!=255U && in<s->used) {
            if (out>=sizeof raw) goto bad;
            raw[out++]=0;
        }
    }
    if (out<10U || raw[0]!='R' || raw[1]!='G' || raw[2]!=BEAM_WIRE_VERSION ||
        raw[3]<BEAM_WIRE_SYNC || raw[3]>BEAM_WIRE_POSE) goto bad;
    n=(unsigned)beam_wire_le(raw+4,2);
    if (n>BEAM_WIRE_MAX_PAYLOAD || out!=n+10U ||
        beam_wire_le(raw+6+n,4)!=crc32(raw,n+6U)) goto bad;
    packet->type=raw[3]; packet->length=n;
    memcpy(packet->payload,raw+6,n);
    s->used=0;
    return 1;
bad:
    ++s->rejected; s->used=0;
    return 0;
}
static void level_put(uint8_t *p, const BeamControlMessage *m)
{
    p[0]=(uint8_t)m->level_id;
    beam_wire_put(p+1,m->generation,8);
    beam_wire_put(p+9,(uint32_t)m->x_milli,4);
    beam_wire_put(p+13,(uint32_t)m->y_milli,4);
    beam_wire_put(p+17,(uint32_t)m->dx_micro,4);
    beam_wire_put(p+21,(uint32_t)m->dy_micro,4);
    beam_wire_put(p+25,m->nonce,4);
}
int beam_wire_control_decode(const BeamWirePacket *p, BeamControlMessage *m)
{
    const uint8_t *b;
    if (!p || !m) return 0;
    memset(m,0,sizeof *m); b=p->payload;
    if ((p->type==BEAM_WIRE_LEVEL && p->length==29U) ||
        (p->type==BEAM_WIRE_READY && p->length==37U)) {
        m->type=p->type==BEAM_WIRE_LEVEL ? BEAM_CONTROL_LEVEL : BEAM_CONTROL_READY;
        m->level_id=b[0]; m->generation=beam_wire_le(b+1,8);
        m->x_milli=(int32_t)(uint32_t)beam_wire_le(b+9,4);
        m->y_milli=(int32_t)(uint32_t)beam_wire_le(b+13,4);
        m->dx_micro=(int32_t)(uint32_t)beam_wire_le(b+17,4);
        m->dy_micro=(int32_t)(uint32_t)beam_wire_le(b+21,4);
        m->nonce=(uint32_t)beam_wire_le(b+25,4);
        if (m->type==BEAM_CONTROL_READY) m->board_ms=beam_wire_le(b+29,8);
        return m->level_id>=1U && m->level_id<=15U && m->generation && m->nonce &&
            m->x_milli>=0 && m->x_milli<=1279000 && m->y_milli>=0 && m->y_milli<=719000 &&
            m->dx_micro>=-1000000 && m->dx_micro<=1000000 &&
            m->dy_micro>=-1000000 && m->dy_micro<=1000000 && (m->dx_micro || m->dy_micro);
    }
    if ((p->type==BEAM_WIRE_START || p->type==BEAM_WIRE_RESET) && p->length==12U) {
        m->type=p->type==BEAM_WIRE_START ? BEAM_CONTROL_START : BEAM_CONTROL_RESET;
        m->generation=beam_wire_le(b,8); m->nonce=(uint32_t)beam_wire_le(b+8,4);
    } else if (p->type==BEAM_WIRE_STARTED && p->length==21U) {
        m->type=BEAM_CONTROL_STARTED; m->level_id=b[0];
        m->generation=beam_wire_le(b+1,8); m->nonce=(uint32_t)beam_wire_le(b+9,4);
        m->board_ms=beam_wire_le(b+13,8);
        if (!m->level_id || m->level_id>15U) return 0;
    } else if (p->type==BEAM_WIRE_RESET_ACK && p->length==20U) {
        m->type=BEAM_CONTROL_RESET_ACK; m->generation=beam_wire_le(b,8);
        m->nonce=(uint32_t)beam_wire_le(b+8,4); m->board_ms=beam_wire_le(b+12,8);
    } else if (p->type==BEAM_WIRE_ERROR && p->length==16U) {
        m->type=BEAM_CONTROL_ERROR; m->error_code=(uint32_t)beam_wire_le(b,4);
        m->generation=beam_wire_le(b+4,8); m->nonce=(uint32_t)beam_wire_le(b+12,4);
    } else return 0;
    return m->generation && m->nonce;
}
int beam_wire_control_encode(char *wire, size_t capacity, const BeamControlMessage *m)
{
    uint8_t p[37];
    unsigned type, n;
    if (!m) return -1;
    if (m->type==BEAM_CONTROL_LEVEL || m->type==BEAM_CONTROL_READY) {
        level_put(p,m); n=m->type==BEAM_CONTROL_LEVEL ? 29U : 37U;
        type=m->type==BEAM_CONTROL_LEVEL ? BEAM_WIRE_LEVEL : BEAM_WIRE_READY;
        if (n==37U) beam_wire_put(p+29,m->board_ms,8);
    } else if (m->type==BEAM_CONTROL_START || m->type==BEAM_CONTROL_RESET) {
        type=m->type==BEAM_CONTROL_START ? BEAM_WIRE_START : BEAM_WIRE_RESET; n=12;
        beam_wire_put(p,m->generation,8); beam_wire_put(p+8,m->nonce,4);
    } else if (m->type==BEAM_CONTROL_STARTED) {
        type=BEAM_WIRE_STARTED; n=21; p[0]=(uint8_t)m->level_id;
        beam_wire_put(p+1,m->generation,8); beam_wire_put(p+9,m->nonce,4);
        beam_wire_put(p+13,m->board_ms,8);
    } else if (m->type==BEAM_CONTROL_RESET_ACK) {
        type=BEAM_WIRE_RESET_ACK; n=20;
        beam_wire_put(p,m->generation,8); beam_wire_put(p+8,m->nonce,4);
        beam_wire_put(p+12,m->board_ms,8);
    } else if (m->type==BEAM_CONTROL_ERROR) {
        type=BEAM_WIRE_ERROR; n=16;
        beam_wire_put(p,m->error_code,4); beam_wire_put(p+4,m->generation,8);
        beam_wire_put(p+12,m->nonce,4);
    } else return -1;
    return beam_wire_encode(wire,capacity,type,p,n);
}
int beam_wire_control_reply(char *wire, size_t capacity, const char *internal, size_t length)
{
    BeamControlMessage message;
    if (!beam_control_parse(internal,length,&message)) return -1;
    return beam_wire_control_encode(wire,capacity,&message);
}
int beam_wire_sync_reply(char *wire, size_t capacity, uint32_t nonce,
                         uint64_t received_ms, uint64_t sent_ms)
{
    uint8_t p[20];
    beam_wire_put(p,nonce,4); beam_wire_put(p+4,received_ms,8); beam_wire_put(p+12,sent_ms,8);
    return beam_wire_encode(wire,capacity,BEAM_WIRE_SYNC_REPLY,p,sizeof p);
}
int beam_wire_pose_encode(char *wire, size_t capacity, const GameBeamSnapshot *s,
                          const BeamControlMessage *level, uint32_t tx, uint64_t published)
{
    uint8_t p[BEAM_WIRE_POSE_HEADER+BEAM_WIRE_OBJECT_BYTES*GAME_BEAM_MAX_OBJECTS];
    int count,j;
    if (!s || !level || !level->level_id || level->level_id>15U || !level->generation || !level->nonce ||
        s->object_count<0 || s->object_count>GAME_BEAM_MAX_OBJECTS || s->width!=1280 ||
        s->height!=720 || !s->generation || published<s->captured_ms ||
        (unsigned)s->status>GAME_BEAM_NO_FRAME) return -1;
    count=s->valid && !s->display_stale ? s->object_count : 0;
    memset(p,0,sizeof p);
    p[0]=(uint8_t)level->level_id; beam_wire_put(p+1,level->generation,8);
    beam_wire_put(p+9,level->nonce,4); beam_wire_put(p+13,tx,4);
    beam_wire_put(p+17,s->generation,8); beam_wire_put(p+25,s->sequence,8);
    beam_wire_put(p+33,s->captured_ms,8); beam_wire_put(p+41,published,8);
    p[49]=(uint8_t)(s->valid && !s->display_stale); p[50]=(uint8_t)s->status;
    p[51]=(uint8_t)s->raw_mask; p[52]=(uint8_t)s->pending_mask;
    p[53]=(uint8_t)(s->missing_mask & GAME_BEAM_PHYSICAL_MASK); p[54]=(uint8_t)count; p[55]=1;
    for (j=0;j<count;++j) {
        const SceneObject *o=&s->objects[j];
        uint8_t *b=p+BEAM_WIRE_POSE_HEADER+BEAM_WIRE_OBJECT_BYTES*(unsigned)j;
        float angle;
        if ((unsigned)o->type>RAY_OBJECT_WALL || o->type==RAY_OBJECT_SOURCE ||
            !isfinite(o->center.x) || !isfinite(o->center.y) || !isfinite(o->axis.x) || !isfinite(o->axis.y) ||
            !isfinite(o->length) || !isfinite(o->width) || o->center.x<0 || o->center.x>1279 ||
            o->center.y<0 || o->center.y>719 || o->length<=0 || o->width<=0 ||
            o->length>4096 || o->width>4096 || fabsf(hypotf(o->axis.x,o->axis.y)-1)>0.01f) return -1;
        angle=atan2f(o->axis.y,o->axis.x);
        if (angle<0) angle+=6.283185307179586f;
        b[0]=(uint8_t)o->type; b[1]=1;
        beam_wire_put(b+2,(uint32_t)floorf(o->center.x*16.0f+0.5f),2);
        beam_wire_put(b+4,(uint32_t)floorf(o->center.y*16.0f+0.5f),2);
        beam_wire_put(b+6,(uint32_t)floorf(angle*10430.37835047045f+0.5f)&65535U,2);
        beam_wire_put(b+8,(uint32_t)floorf(o->length*8.0f+0.5f),2);
        beam_wire_put(b+10,(uint32_t)floorf(o->width*8.0f+0.5f),2);
        if (!beam_wire_le(b+8,2) || !beam_wire_le(b+10,2)) return -1;
    }
    return beam_wire_encode(wire,capacity,BEAM_WIRE_POSE,p,
                             BEAM_WIRE_POSE_HEADER+BEAM_WIRE_OBJECT_BYTES*(unsigned)count);
}
