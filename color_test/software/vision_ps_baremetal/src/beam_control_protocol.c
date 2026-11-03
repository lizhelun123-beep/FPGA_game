#include "beam_control_protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

static uint32_t crc32(const char *data, size_t length)
{
    uint32_t crc=0xffffffffU;
    size_t i;
    unsigned bit;
    for (i=0; i<length; ++i) {
        crc^=(unsigned char)data[i];
        for (bit=0; bit<8; ++bit)
            crc=(crc>>1)^(0xedb88320U&(0U-(crc&1U)));
    }
    return crc^0xffffffffU;
}

static int hex_value(char ch)
{
    if (ch>='0' && ch<='9') return ch-'0';
    if (ch>='a' && ch<='f') return ch-'a'+10;
    if (ch>='A' && ch<='F') return ch-'A'+10;
    return -1;
}

static int parse_unsigned(const char *text, unsigned long long maximum,
                          unsigned long long *value)
{
    char *end;
    unsigned long long result;
    if (!text || !*text || text[0]=='-') return 0;
    { const char *p=text; while (*p) { if (*p<'0' || *p>'9') return 0; ++p; } }
    errno=0;
    result=strtoull(text,&end,10);
    if (errno==ERANGE || *end || result>maximum) return 0;
    *value=result;
    return 1;
}

static int parse_signed(const char *text, long long minimum, long long maximum,
                        long long *value)
{
    char *end;
    long long result;
    if (!text || !*text) return 0;
    { const char *p=text; if (*p=='-') ++p; if (!*p) return 0;
      while (*p) { if (*p<'0' || *p>'9') return 0; ++p; } }
    errno=0;
    result=strtoll(text,&end,10);
    if (errno==ERANGE || *end || result<minimum || result>maximum) return 0;
    *value=result;
    return 1;
}

static int base64_value(char c)
{
    if (c>='A' && c<='Z') return c-'A';
    if (c>='a' && c<='z') return c-'a'+26;
    if (c>='0' && c<='9') return c-'0'+52;
    if (c=='+') return 62;
    if (c=='/') return 63;
    return -1;
}

static uint64_t little_integer(const unsigned char *p, unsigned n)
{
    uint64_t v=0;
    unsigned i;
    for (i=0; i<n; ++i) v|=(uint64_t)p[i]<<(8U*i);
    return v;
}

static int parse_level(const char *text, BeamControlMessage *m)
{
    unsigned char data[30];
    unsigned i, out=0;
    if (strlen(text)!=40U || text[39]!='=') return 0;
    for (i=0; i<40U; i+=4U) {
        int a=base64_value(text[i]), b=base64_value(text[i+1]);
        int c=base64_value(text[i+2]), d=i==36U ? 0 : base64_value(text[i+3]);
        if (a<0 || b<0 || c<0 || d<0 || (i==36U && (c&3))) return 0;
        data[out++]=(unsigned char)((a<<2)|(b>>4));
        data[out++]=(unsigned char)((b<<4)|(c>>2));
        if (i!=36U) data[out++]=(unsigned char)((c<<6)|d);
    }
    memset(m,0,sizeof *m);
    m->type=BEAM_CONTROL_LEVEL;
    m->level_id=data[0];
    m->generation=little_integer(data+1,8);
    m->x_milli=(int32_t)(uint32_t)little_integer(data+9,4);
    m->y_milli=(int32_t)(uint32_t)little_integer(data+13,4);
    m->dx_micro=(int32_t)(uint32_t)little_integer(data+17,4);
    m->dy_micro=(int32_t)(uint32_t)little_integer(data+21,4);
    m->nonce=(uint32_t)little_integer(data+25,4);
    return m->level_id>=1U && m->level_id<=15U && m->generation && m->nonce &&
        m->x_milli>=0 && m->x_milli<=1279000 && m->y_milli>=0 && m->y_milli<=719000 &&
        m->dx_micro>=-1000000 && m->dx_micro<=1000000 &&
        m->dy_micro>=-1000000 && m->dy_micro<=1000000 && (m->dx_micro || m->dy_micro);
}

static int parse_fields(char *fields, BeamControlMessage *message,
                        BeamControlType type)
{
    char *tokens[8]={0};
    char *cursor=fields;
    unsigned count=0;
    unsigned long long u;
    long long s;
    while (cursor && count<8U) {
        tokens[count++]=cursor;
        cursor=strchr(cursor,',');
        if (cursor) *cursor++=0;
    }
    if (cursor ||
        (type==BEAM_CONTROL_START && count!=2U) ||
        (type==BEAM_CONTROL_RESET && count!=2U) ||
        (type==BEAM_CONTROL_READY && count!=8U) ||
        (type==BEAM_CONTROL_STARTED && count!=4U) ||
        (type==BEAM_CONTROL_RESET_ACK && count!=3U) ||
        (type==BEAM_CONTROL_ERROR && count!=3U)) return 0;
    memset(message,0,sizeof(*message));
    message->type=type;
    if (type==BEAM_CONTROL_READY) {
        if (!parse_unsigned(tokens[0],15,&u) || !u) return 0;
        message->level_id=(uint32_t)u;
        if (!parse_unsigned(tokens[1],UINT64_MAX,&u) || !u) return 0;
        message->generation=u;
        if (!parse_signed(tokens[2],-2000000,2000000,&s)) return 0;
        message->x_milli=(int32_t)s;
        if (!parse_signed(tokens[3],-2000000,2000000,&s)) return 0;
        message->y_milli=(int32_t)s;
        if (!parse_signed(tokens[4],-2000000,2000000,&s)) return 0;
        message->dx_micro=(int32_t)s;
        if (!parse_signed(tokens[5],-2000000,2000000,&s)) return 0;
        message->dy_micro=(int32_t)s;
        if (!parse_unsigned(tokens[6],UINT32_MAX,&u) || !u) return 0;
        message->nonce=(uint32_t)u;
        if (!parse_unsigned(tokens[7],UINT64_MAX,&u)) return 0;
        message->board_ms=u;
        return 1;
    }
    if (type==BEAM_CONTROL_START || type==BEAM_CONTROL_RESET) {
        if (!parse_unsigned(tokens[0],UINT64_MAX,&u) || !u) return 0;
        message->generation=u;
        if (!parse_unsigned(tokens[1],UINT32_MAX,&u) || !u) return 0;
        message->nonce=(uint32_t)u;
        return 1;
    }
    if (type==BEAM_CONTROL_STARTED) {
        if (!parse_unsigned(tokens[0],15,&u) || !u) return 0;
        message->level_id=(uint32_t)u;
        if (!parse_unsigned(tokens[1],UINT64_MAX,&u) || !u) return 0;
        message->generation=u;
        if (!parse_unsigned(tokens[2],UINT32_MAX,&u) || !u) return 0;
        message->nonce=(uint32_t)u;
        if (!parse_unsigned(tokens[3],UINT64_MAX,&u)) return 0;
        message->board_ms=u;
        return 1;
    }
    if (type==BEAM_CONTROL_RESET_ACK) {
        if (!parse_unsigned(tokens[0],UINT64_MAX,&u) || !u) return 0;
        message->generation=u;
        if (!parse_unsigned(tokens[1],UINT32_MAX,&u) || !u) return 0;
        message->nonce=(uint32_t)u;
        if (!parse_unsigned(tokens[2],UINT64_MAX,&u)) return 0;
        message->board_ms=u;
        return 1;
    }
    if (type==BEAM_CONTROL_ERROR) {
        if (!parse_unsigned(tokens[0],UINT32_MAX,&u)) return 0;
        message->error_code=(uint32_t)u;
        if (!parse_unsigned(tokens[1],UINT64_MAX,&u)) return 0;
        message->generation=u;
        if (!parse_unsigned(tokens[2],UINT32_MAX,&u)) return 0;
        message->nonce=(uint32_t)u;
        return 1;
    }
    return 0;
}

int beam_control_parse(const char *line, size_t length, BeamControlMessage *message)
{
    char buffer[BEAM_CONTROL_MAX_LINE+1U];
    char *body, *kind_end, *crc_text, *fields;
    size_t body_length, i;
    uint32_t expected=0;
    int digit;
    BeamControlType type=BEAM_CONTROL_NONE;
    if (!line || !message || !length || length>BEAM_CONTROL_MAX_LINE) return 0;
    while (length && (line[length-1]=='\n' || line[length-1]=='\r')) --length;
    if (length<12U || line[0]!='@' || length>BEAM_CONTROL_MAX_LINE) return 0;
    memcpy(buffer,line,length); buffer[length]=0;
    crc_text=strrchr(buffer,':');
    if (!crc_text || strlen(crc_text+1)!=8U) return 0;
    for (i=1; i<9; ++i) { digit=hex_value(crc_text[i]); if (digit<0) return 0; expected=(expected<<4)|(unsigned)digit; }
    *crc_text=0;
    body=buffer+1;
    body_length=strlen(body);
    if (crc32(body,body_length)!=expected) return 0;
    kind_end=strchr(body,':');
    if (!kind_end) return 0;
    *kind_end=0; fields=kind_end+1;
    if (!strcmp(body,"LEVEL2")) type=BEAM_CONTROL_LEVEL;
    else if (!strcmp(body,"START2")) type=BEAM_CONTROL_START;
    else if (!strcmp(body,"RESET2")) type=BEAM_CONTROL_RESET;
    else if (!strcmp(body,"READY2")) type=BEAM_CONTROL_READY;
    else if (!strcmp(body,"STARTED2")) type=BEAM_CONTROL_STARTED;
    else if (!strcmp(body,"RESET2ACK")) type=BEAM_CONTROL_RESET_ACK;
    else if (!strcmp(body,"ERROR2")) type=BEAM_CONTROL_ERROR;
    else return 0;
    if (type==BEAM_CONTROL_LEVEL) return parse_level(fields,message);
    return parse_fields(fields,message,type);
}

static int format_body(char *line, size_t capacity, const char *body)
{
    uint32_t crc;
    int length;
    if (!line || !body) return -1;
    crc=crc32(body,strlen(body));
    length=snprintf(line,capacity,"@%s:%08X\r\n",body,(unsigned)crc);
    if (length<0 || (size_t)length>=capacity) return -1;
    return length;
}

int beam_control_format_ready(char *line, size_t capacity, uint32_t level_id,
                              uint64_t generation, int32_t x_milli, int32_t y_milli,
                              int32_t dx_micro, int32_t dy_micro, uint32_t nonce,
                              uint64_t board_ms)
{
    char body[160];
    int n=snprintf(body,sizeof body,"READY2:%u,%llu,%ld,%ld,%ld,%ld,%u,%llu",
        (unsigned)level_id,(unsigned long long)generation,(long)x_milli,(long)y_milli,
        (long)dx_micro,(long)dy_micro,(unsigned)nonce,(unsigned long long)board_ms);
    return n<0 || (size_t)n>=sizeof body ? -1 : format_body(line,capacity,body);
}

int beam_control_format_started(char *line, size_t capacity, uint32_t level_id,
                                uint64_t generation, uint32_t nonce, uint64_t board_ms)
{
    char body[96];
    int n=snprintf(body,sizeof body,"STARTED2:%u,%llu,%u,%llu",(unsigned)level_id,
        (unsigned long long)generation,(unsigned)nonce,(unsigned long long)board_ms);
    return n<0 || (size_t)n>=sizeof body ? -1 : format_body(line,capacity,body);
}

int beam_control_format_reset_ack(char *line, size_t capacity, uint64_t generation,
                                  uint32_t nonce, uint64_t board_ms)
{
    char body[96];
    int n=snprintf(body,sizeof body,"RESET2ACK:%llu,%u,%llu",(unsigned long long)generation,
        (unsigned)nonce,(unsigned long long)board_ms);
    return n<0 || (size_t)n>=sizeof body ? -1 : format_body(line,capacity,body);
}

int beam_control_format_error(char *line, size_t capacity, uint32_t code,
                              uint64_t generation, uint32_t nonce)
{
    char body[96];
    int n=snprintf(body,sizeof body,"ERROR2:%u,%llu,%u",(unsigned)code,
        (unsigned long long)generation,(unsigned)nonce);
    return n<0 || (size_t)n>=sizeof body ? -1 : format_body(line,capacity,body);
}
