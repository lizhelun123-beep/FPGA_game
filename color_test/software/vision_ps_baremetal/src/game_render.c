#include "game_render.h"
#include "game_font.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

static const unsigned pose_counts[6]={36,72,72,1,72,36};
static uint32_t art_u32(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint32_t art_hash(const uint8_t *p,size_t n)
{
    uint32_t h=2166136261U;
    size_t i;
    for (i=0;i<n;++i) h=(h^p[i])*16777619U;
    return h;
}
static uint32_t art_geometry(const GameConfig *c,const GameRenderConfig *r)
{
    float values[18];
    uint8_t bytes[72];
    int i,j;
    values[0]=c->width; values[1]=c->height;
    values[2]=(float)r->scene.x; values[3]=(float)r->scene.y;
    values[4]=(float)r->scene.width; values[5]=(float)r->scene.height;
    for (i=0;i<6;++i) { values[6+i*2]=c->model_sizes[i].x; values[7+i*2]=c->model_sizes[i].y; }
    for (i=0;i<18;++i) {
        uint32_t v;
        memcpy(&v,&values[i],4);
        for (j=0;j<4;++j) bytes[i*4+j]=(uint8_t)(v>>(j*8));
    }
    return art_hash(bytes,sizeof bytes);
}
void game_render_assets_free(GameRenderAssets *a)
{
    if (a) { free(a->storage); memset(a,0,sizeof *a); }
}
GameRenderStatus game_render_assets_load(GameRenderAssets *a,const char *path,
                                         const GameConfig *c,const GameRenderConfig *r)
{
    FILE *f;
    uint8_t header[24];
    size_t n,at=0;
    unsigned i,kind,pose;
    GameRenderStatus status=GAME_RENDER_BAD_ASSET;
    if (!a || a->storage || !path || !c || !r || sizeof(float)!=4) return GAME_RENDER_BAD_ASSET;
    f=fopen(path,"rb");
    if (!f) return GAME_RENDER_IO_ERROR;
    if (fread(header,1,sizeof header,f)!=sizeof header || memcmp(header,"RAYART1\0",8) ||
        art_u32(header+16)!=290 || art_u32(header+20)!=art_geometry(c,r)) goto done;
    n=art_u32(header+8);
    /* Exact contract also bounds allocation before accepting untrusted bytes. */
    if (n!=3072000U+289U*112U*112U*3U+290U*32U) goto done;
    a->storage=(uint8_t *)malloc(n);
    if (!a->storage) { status=GAME_RENDER_IO_ERROR; goto done; }
    a->bytes=n;
    if (fread(a->storage,1,n,f)!=n || fgetc(f)!=EOF || ferror(f) ||
        art_hash(a->storage,n)!=art_u32(header+12)) goto done;
    for (i=0;i<290;++i) {
        uint8_t *p;
        unsigned w,h,ax,ay,bytes;
        VisionCanvas image;
        if (n-at<32) goto done;
        p=a->storage+at; kind=art_u32(p); pose=art_u32(p+4);
        w=art_u32(p+8); h=art_u32(p+12); ax=art_u32(p+16); ay=art_u32(p+20);
        bytes=art_u32(p+24); at+=32;
        if (art_u32(p+28) || bytes>n-at) goto done;
        if (kind==6) {
            if (i || pose || w!=1280 || h!=800 || ax || ay || bytes!=3072000) goto done;
        } else if (kind>=6 || pose>=pose_counts[kind] || w!=112 || h!=112 ||
                   ax!=56 || ay!=56 || bytes!=37632 || a->poses[kind][pose].data) goto done;
        image=(VisionCanvas){a->storage+at,(int)w,(int)h,(size_t)w*3,bytes};
        if (kind==6) a->background=image;
        else a->poses[kind][pose]=image;
        at+=bytes;
    }
    if (at!=n || !a->background.data) goto done;
    for (kind=0;kind<6;++kind) for (pose=0;pose<72;++pose) {
        if (pose<pose_counts[kind] && !a->poses[kind][pose].data) goto done;
        a->poses[kind][pose]=a->poses[kind][pose%pose_counts[kind]];
    }
    a->geometry_signature=art_geometry(c,r); a->loads=1; status=GAME_RENDER_OK;
done:
    if (fclose(f)) status=GAME_RENDER_IO_ERROR;
    if (status!=GAME_RENDER_OK) game_render_assets_free(a);
    return status;
}

#define BG 0x101D2CU
#define PANEL 0x1C3044U
#define INK 0xEDF4FAU
#define MUTED 0x9CB2C7U
#define ACCENT 0x52D5C1U
#define WARNING 0xFFCC66U

/* Avoid legacy MinGW snprintf's non-ISO I64 length modifier. */
static void decimal(uint64_t n,char out[21])
{
    char reverse[20];
    int count=0,i;
    do { reverse[count++]=(char)('0'+n%10); n/=10; } while (n);
    for (i=0;i<count;++i) out[i]=reverse[count-1-i];
    out[count]=0;
}

/* UTF-8 short labels only; malformed bytes use an outlined missing glyph.
 * Pixel placement remains double until clipped, including INT_MIN origins. */
void game_render_text(const VisionCanvas *c, int x, int y, const char *s, int scale, unsigned rgb)
{
    double pen=x;
    if (!vision_canvas_valid(c) || !s || scale<1 || scale>4) return;
    while (*s && pen<c->width) {
        const unsigned char *p=(const unsigned char *)s;
        uint32_t code=*p;
        size_t n=1,i;
        int row,col;
        const GameGlyph *glyph=NULL;
        if (p[0]>=0xe0 && p[0]<=0xef && p[1] && p[2] &&
            (p[1]&0xc0)==0x80 && (p[2]&0xc0)==0x80) {
            code=((uint32_t)(p[0]&15)<<12)|((uint32_t)(p[1]&63)<<6)|(p[2]&63); n=3;
        }
        if (code<128) {
            char ascii[2]={(char)code,0};
            if (pen>=-6*scale) vision_canvas_text(c,(int)pen,y,ascii,scale,rgb);
            pen+=6*scale; s+=n; continue;
        }
        for (i=0;i<sizeof(game_glyphs)/sizeof(game_glyphs[0]);++i)
            if (game_glyphs[i].code==code) { glyph=&game_glyphs[i]; break; }
        for (row=0;row<16;++row) for (col=0;col<16;++col) {
            int on=glyph ? (glyph->rows[row]&(1U<<col))!=0 : row==1 || row==14 || col==1 || col==14;
            double xx=pen+col*scale,yy=(double)y+row*scale;
            if (on && xx>=-scale && xx<c->width && yy>=-scale && yy<c->height)
                vision_canvas_rect(c,(int)xx,(int)yy,scale,scale,rgb);
        }
        pen+=18*scale; s+=n;
    }
}
static int valid_rect(GameMenuRect r, int w, int h)
{
    return r.x>=0 && r.y>=0 && r.width>=2 && r.height>=2 &&
           r.width<=w && r.height<=h && r.x<=w-r.width && r.y<=h-r.height;
}
static int overlaps(GameMenuRect a,GameMenuRect b)
{
    return a.x<b.x+b.width && b.x<a.x+a.width && a.y<b.y+b.height && b.y<a.y+a.height;
}
static int valid_snapshot(const GameLoopOutput *p)
{
    const GameSnapshot *s=&p->game;
    int i;
    if ((unsigned)s->state>GAME_TIMED_OUT || s->stars>3 ||
        s->object_count<0 || s->object_count>GAME_MAX_MODELS ||
        s->ray.segment_count<0 || s->ray.segment_count>RAY_GAME_MAX_SEGMENTS ||
        s->ray.hit_count<0 || s->ray.hit_count>RAY_GAME_MAX_INTERACTIONS) return 0;
    for (i=0;i<s->object_count;++i) {
        const SceneObject *o=&s->objects[i];
        if ((unsigned)o->type>=RAY_OBJECT_TYPE_COUNT || !isfinite(o->center.x) ||
            !isfinite(o->center.y) || !isfinite(o->axis.x) || !isfinite(o->axis.y) ||
            !isfinite(o->length) || !isfinite(o->width) || o->length<=0 || o->width<=0 ||
            !isfinite(o->source_tip.x) || !isfinite(o->source_tip.y) ||
            !isfinite(o->source_direction.x) || !isfinite(o->source_direction.y)) return 0;
    }
    for (i=0;i<s->ray.segment_count;++i) {
        const RaySegment *r=&s->ray.segments[i];
        if (!isfinite(r->start.x) || !isfinite(r->start.y) || !isfinite(r->end.x) || !isfinite(r->end.y)) return 0;
    }
    return 1;
}
static void button(const VisionCanvas *c,GameMenuRect r,const char *label,int enabled,int selected,int hover,int down)
{
    unsigned edge=selected?ACCENT:hover?INK:0x36546CU;
    unsigned fill=!enabled?0x253443U:hover?(down?0x306B70U:0x30566CU):selected?0x234E55U:PANEL;
    int len=(int)strlen(label)/3;
    vision_canvas_rect(c,r.x,r.y,r.width,r.height,edge);
    vision_canvas_rect(c,r.x+3,r.y+3,r.width-6,r.height-6,fill);
    game_render_text(c,r.x+(r.width-len*54)/2,r.y+(r.height-48)/2,label,3,enabled?INK:MUTED);
}
static void star(const VisionCanvas *c,int x,int y,int active)
{
    VisionPoint p[10];
    int i;
    for (i=0;i<10;++i) {
        double a=-1.5707963267948966+i*0.6283185307179586,r=(i&1)?8:18;
        p[i]=(VisionPoint){x+r*cos(a),y+r*sin(a)};
    }
    /* Non-convex star drawn as five triangles sharing the center. */
    for (i=0;i<10;i+=2) {
        VisionPoint q[3]={{x,y},p[(i+9)%10],p[i]};
        VisionPoint t[3]={{x,y},p[i],p[(i+1)%10]};
        vision_canvas_polygon(c,q,3,active?WARNING:0x31485CU,active?WARNING:0x31485CU);
        vision_canvas_polygon(c,t,3,active?WARNING:0x31485CU,active?WARNING:0x31485CU);
    }
}
GameRenderStatus game_render_cached_source(const GameLoopOutput *p,const GameConfig *config,
                             const GameMenuLayout *layout,const GameRenderConfig *render,
                                    const GameRenderAssets *assets,const VisionCanvas *c,const char *source_label)
{
    const GameSnapshot *s;
    GameMenuInput input;
    GameMenuView derived;
    VisionCanvas scene;
    GameMenuRect box;
    double scale,ox,oy;
    int i,known_level=0,show_scene;
    char text[192];
    char generation[21],sequence[21],captured[21],elapsed[21],minutes[21];
    static const char *const states[]={"选择关卡","准备","运行","通关","超时"};
    static const char *const levels[]={"关卡一","关卡二","关卡三"};
    static const char *const models[]={"镜面","门 A","门 B","目标","光源","墙"};
    if (!vision_canvas_valid(c)) return GAME_RENDER_BAD_BUFFER;
    if (!p || !config || !layout || !render || render->version!=GAME_RENDER_VERSION ||
        !game_menu_layout_valid(layout,config) || layout->width!=1280 || layout->height!=800 ||
        c->width!=layout->width || c->height!=layout->height ||
        !valid_rect(render->scene,c->width,c->height) || !isfinite(config->width) ||
        !isfinite(config->height) || config->width<1 || config->height<1 ||
        config->width>1e9 || config->height>1e9) return GAME_RENDER_BAD_LAYOUT;
    box=render->scene;
    if (overlaps(box,layout->start)) return GAME_RENDER_BAD_LAYOUT;
    for (i=0;i<layout->level_count;++i) if (overlaps(box,layout->levels[i].rect)) return GAME_RENDER_BAD_LAYOUT;
    if (!valid_snapshot(p)) return GAME_RENDER_BAD_SNAPSHOT;
    s=&p->game;
    for (i=0;i<layout->level_count;++i) if (layout->levels[i].level_id==s->level_id) known_level=1;
    if (!known_level && s->state!=GAME_SELECT_LEVEL) return GAME_RENDER_BAD_SNAPSHOT;
    memset(&input,0,sizeof input);
    input.x=p->menu.x; input.y=p->menu.y; input.connected=p->menu.connected; input.left_down=p->menu.left_down;
    derived=game_menu_view(&input,layout,s);
    if (derived.start_enabled!=p->menu.start_enabled || derived.hover.kind!=p->menu.hover.kind ||
        derived.hover.level_id!=p->menu.hover.level_id) return GAME_RENDER_BAD_SNAPSHOT;
    if (assets) {
        uintptr_t a=(uintptr_t)assets->storage,b=(uintptr_t)c->data;
        size_t span=(size_t)(c->height-1)*c->stride+(size_t)c->width*3;
        if (!assets->storage || assets->loads!=1 || assets->geometry_signature!=art_geometry(config,render))
            return GAME_RENDER_BAD_ASSET;
        if (a<=b ? b-a<assets->bytes : a-b<span) return GAME_RENDER_BAD_BUFFER;
        if (game_render_blit(&assets->background,c,0,0,0,0)!=GAME_RENDER_OK) return GAME_RENDER_BAD_BUFFER;
    } else vision_canvas_rect(c,0,0,c->width,c->height,BG);
    game_render_text(c,80,14,"光线游戏",2,INK);
    /* Explicitly a preview. No calibrated mm/A3 claims are made by this API. */
    game_render_text(c,860,20,"未标定预览",2,WARNING);
    for (i=0;i<layout->level_count;++i) {
        int hover=p->menu.hover.kind==GAME_MENU_SELECT && p->menu.hover.level_id==layout->levels[i].level_id;
        button(c,layout->levels[i].rect,levels[i],1,s->level_id==layout->levels[i].level_id,hover,p->menu.left_down);
    }
    button(c,layout->start,"开始",p->menu.start_enabled,0,p->menu.hover.kind==GAME_MENU_START,p->menu.left_down);
    game_render_text(c,820,681,p->menu.start_enabled?"可用":"不可用",2,p->menu.start_enabled?ACCENT:MUTED);
    if (!assets) vision_canvas_rect(c,box.x,box.y,box.width,box.height,PANEL);
    /* Subcanvas capacity shrinks with its byte offset. Pixels outside scene
     * cannot overwrite menu/status even for extreme model/line coordinates. */
    scene=(VisionCanvas){c->data+(size_t)box.y*c->stride+(size_t)box.x*3,
                         box.width,box.height,c->stride,
                         c->capacity-((size_t)box.y*c->stride+(size_t)box.x*3)};
    scale=fmin((box.width-1)/(double)config->width,(box.height-1)/(double)config->height);
    ox=fmax(0,(box.width-1-config->width*scale)/2);
    oy=fmax(0,(box.height-1-config->height*scale)/2);
    if (assets) {
        size_t offset=(size_t)floor(oy)*scene.stride+(size_t)floor(ox)*3;
        scene.data+=offset; scene.capacity-=offset;
        scene.width=(int)floor(config->width*scale)+1;
        scene.height=(int)floor(config->height*scale)+1;
        ox-=floor(ox); oy-=floor(oy);
    }
    for (i=0;!assets && i<=20;++i) {
        double x=ox+config->width*scale*i/20,y=oy+config->height*scale*i/20;
        vision_canvas_line(&scene,(VisionPoint){x,oy},(VisionPoint){x,oy+config->height*scale},0,0x294257U);
        vision_canvas_line(&scene,(VisionPoint){ox,y},(VisionPoint){ox+config->width*scale,y},0,0x294257U);
    }
    show_scene=s->scene_valid && (s->scene_status==GAME_OK || s->scene_status==GAME_NEED_UNSOLVED) && s->state!=GAME_SELECT_LEVEL;
    if (show_scene) {
        for (i=0;i<s->object_count;++i) {
            const SceneObject *o=&s->objects[i];
            if (!assets) vision_canvas_object(&scene,o,scale,ox,oy);
            else {
                double angle=atan2(o->axis.y,o->axis.x)*180/3.14159265358979323846;
                double x=ox+scale*o->center.x,y=oy+scale*o->center.y;
                int pose=((int)floor(angle/5+0.5)%72+72)%72;
                if (o->type==RAY_OBJECT_SOURCE) {
                    angle=atan2(o->source_direction.y,o->source_direction.x)*180/3.14159265358979323846;
                    pose=((int)floor(angle/5+0.5)%72+72)%72;
                }
                /* Clip doubles before conversion, including hostile snapshots. */
                if (x>=-112 && x<scene.width+112 && y>=-112 && y<scene.height+112) {
                    (void)game_render_blit(&assets->poses[o->type][pose],&scene,(int)floor(x+.5)-56,(int)floor(y+.5)-56,1,0xFF00FFU);
                    if (o->type==RAY_OBJECT_MIRROR) {
                        VisionPoint a={x-scale*o->axis.x*o->length/2,y-scale*o->axis.y*o->length/2};
                        VisionPoint b={x+scale*o->axis.x*o->length/2,y+scale*o->axis.y*o->length/2};
                        vision_canvas_line(&scene,a,b,0,0xFCFFFFU);
                    } else if (o->type==RAY_OBJECT_SOURCE) {
                        VisionPoint tip={ox+scale*o->source_tip.x,oy+scale*o->source_tip.y};
                        vision_canvas_line(&scene,(VisionPoint){x,y},tip,0,0xFFDAEDU);
                    }
                }
            }
        }
        for (i=0;i<s->ray.segment_count;++i) {
            const RaySegment *r=&s->ray.segments[i];
            VisionPoint a={ox+scale*r->start.x,oy+scale*r->start.y},b={ox+scale*r->end.x,oy+scale*r->end.y};
            vision_canvas_line(&scene,a,b,3,BG); vision_canvas_line(&scene,a,b,1,0xFFE12AU);
        }
    } else game_render_text(&scene,assets?(scene.width-216)/2:210,180,
                            assets && s->state==GAME_SELECT_LEVEL?"选择关卡":
                            s->scene_status==GAME_STALE_SCENE?"场景过期":"场景无效",3,WARNING);
    for (i=0;i<RAY_OBJECT_TYPE_COUNT;++i) {
        int x=80+i*146;
        vision_canvas_circle(c,(VisionPoint){x+5,631},4,0,vision_object_color((RayObjectType)i));
        game_render_text(c,x+16,620,models[i],1,vision_object_color((RayObjectType)i));
    }
    game_render_text(c,1000,208,states[s->state],2,s->state==GAME_CLEARED?ACCENT:INK);
    game_render_text(c,1000,286,"剩余时间",2,MUTED);
    /* Only formatting the published remaining_ms; no timer or score policy. */
    decimal(s->remaining_ms/60000,minutes);
    (void)snprintf(text,sizeof text,"%s%s:%02u",s->remaining_ms<600000?"0":"",minutes,(unsigned)((s->remaining_ms/1000)%60));
    vision_canvas_text(c,1000,320,text,4,INK);
    game_render_text(c,1000,400,"成绩",2,MUTED);
    for (i=0;i<3;++i) star(c,1020+i*62,452,i<(int)s->stars);
    if (s->render_budget_exceeded) {
        game_render_text(c,1000,524,"光线超限",2,WARNING);
        (void)snprintf(text,sizeof text,"ALL %d / %d",s->ray.segment_count,config->render_max_ray_segments);
        vision_canvas_text(c,1000,570,text,2,WARNING);
    }
    if (!p->menu.connected) game_render_text(c,80,680,"输入断开",2,WARNING);
    else if (!show_scene && (!assets || s->state!=GAME_SELECT_LEVEL)) game_render_text(c,80,680,"场景无效",2,WARNING);
    else if (s->state==GAME_PREPARING && !s->ready) {
        if (assets) game_render_text(c,80,680,"目标命中",2,WARNING);
        else vision_canvas_text(c,80,680,"NEED UNSOLVED",2,WARNING);
    }
    if (assets) {
        const char *hint=s->state==GAME_SELECT_LEVEL?"选择关卡":
                         s->state==GAME_CLEARED || s->state==GAME_TIMED_OUT?"可选关":
                         s->level_id==1?"转动光源":s->level_id==2?"移动双门":"移动镜面";
        game_render_text(c,80,728,hint,2,MUTED);
        game_render_text(c,1000,563,"可选关",1,MUTED);
    }
    decimal(s->generation,generation); decimal(s->scene_sequence,sequence);
    decimal(s->captured_ms,captured); decimal(s->elapsed_ms,elapsed);
    (void)snprintf(text,sizeof text,"L%u  GEN:%s  SEQ:%s  CAP:%s  MS:%s  RAY:%d",
                   s->level_id,generation,sequence,captured,elapsed,s->ray.segment_count);
    if (!assets) vision_canvas_text(c,80,773,text,1,MUTED);
    if (source_label) game_render_text(c,80,773,source_label,1,WARNING);
    if (p->menu.connected) {
        double x=p->menu.x,y=p->menu.y;
        VisionPoint pointer[3]={{x,y},{x+3,y+22},{x+17,y+15}};
        vision_canvas_polygon(c,pointer,3,INK,BG);
    }
    return s->render_budget_exceeded?GAME_RENDER_FULL_RAY:GAME_RENDER_OK;
}
GameRenderStatus game_render_cached(const GameLoopOutput *p,const GameConfig *config,
                                    const GameMenuLayout *layout,const GameRenderConfig *render,
                                    const GameRenderAssets *assets,const VisionCanvas *c)
{
    return game_render_cached_source(p,config,layout,render,assets,c,NULL);
}
GameRenderStatus game_render(const GameLoopOutput *p,const GameConfig *config,
                             const GameMenuLayout *layout,const GameRenderConfig *render,
                             const VisionCanvas *c)
{
    return game_render_cached(p,config,layout,render,NULL,c);
}
GameRenderStatus game_render_write_ppm(const VisionCanvas *c,FILE *stream)
{
    int x,y;
    if (!vision_canvas_valid(c)) return GAME_RENDER_BAD_BUFFER;
    if (!stream || fprintf(stream,"P6\n%d %d\n255\n",c->width,c->height)<0) return GAME_RENDER_IO_ERROR;
    for (y=0;y<c->height;++y) for (x=0;x<c->width;++x) {
        const uint8_t *b=c->data+(size_t)y*c->stride+(size_t)x*3;
        unsigned char rgb[3]={b[2],b[1],b[0]};
        if (fwrite(rgb,1,3,stream)!=3) return GAME_RENDER_IO_ERROR;
    }
    return ferror(stream)?GAME_RENDER_IO_ERROR:GAME_RENDER_OK;
}

GameRenderStatus game_render_read_bgr(FILE *stream,const VisionCanvas *asset)
{
    int y;
    if (!vision_canvas_valid(asset)) return GAME_RENDER_BAD_BUFFER;
    if (!stream) return GAME_RENDER_IO_ERROR;
    for (y=0;y<asset->height;++y)
        if (fread(asset->data+(size_t)y*asset->stride,1,(size_t)asset->width*3,stream)!=
            (size_t)asset->width*3) return GAME_RENDER_IO_ERROR;
    if (fgetc(stream)!=EOF) return GAME_RENDER_BAD_ASSET;
    return ferror(stream)?GAME_RENDER_IO_ERROR:GAME_RENDER_OK;
}

GameRenderStatus game_render_blit(const VisionCanvas *asset,const VisionCanvas *target,
                                  int x,int y,int keyed,unsigned color_key)
{
    int64_t left=x,top=y,right,bottom,xx,yy;
    uintptr_t a,b;
    size_t aspan,bspan;
    if (!vision_canvas_valid(asset) || !vision_canvas_valid(target)) return GAME_RENDER_BAD_BUFFER;
    if ((keyed!=0 && keyed!=1) || color_key>0xFFFFFFU) return GAME_RENDER_BAD_ASSET;
    a=(uintptr_t)asset->data; b=(uintptr_t)target->data;
    aspan=(size_t)(asset->height-1)*asset->stride+(size_t)asset->width*3;
    bspan=(size_t)(target->height-1)*target->stride+(size_t)target->width*3;
    if (a<=b ? b-a<aspan : a-b<bspan) return GAME_RENDER_BAD_BUFFER;
    right=(int64_t)x+asset->width; bottom=(int64_t)y+asset->height;
    if (left<0) left=0;
    if (top<0) top=0;
    if (right>target->width) right=target->width;
    if (bottom>target->height) bottom=target->height;
    if (left>=right || top>=bottom) return GAME_RENDER_OK;
    for (yy=top;yy<bottom;++yy) {
        const uint8_t *src=asset->data+(size_t)(yy-y)*asset->stride+(size_t)(left-x)*3;
        uint8_t *dst=target->data+(size_t)yy*target->stride+(size_t)left*3;
        if (!keyed) memcpy(dst,src,(size_t)(right-left)*3);
        else for (xx=left;xx<right;++xx,src+=3,dst+=3) {
            unsigned rgb=((unsigned)src[2]<<16)|((unsigned)src[1]<<8)|src[0];
            if (rgb!=color_key) memcpy(dst,src,3);
        }
    }
    return GAME_RENDER_OK;
}


GameRenderStatus game_render_fit_720p(const VisionCanvas *source,const VisionCanvas *out)
{
    uintptr_t a,b;
    unsigned x,y;
    if (!vision_canvas_valid(source) || !vision_canvas_valid(out) ||
        source->width!=1280 || source->height!=800 || out->width!=1280 || out->height!=720)
        return GAME_RENDER_BAD_BUFFER;
    a=(uintptr_t)source->data; b=(uintptr_t)out->data;
    if (source->capacity>UINTPTR_MAX-a || out->capacity>UINTPTR_MAX-b ||
        (a<b+out->capacity && b<a+source->capacity)) return GAME_RENDER_BAD_BUFFER;
    for (y=0;y<720;++y) {
        const uint8_t *row=source->data+(size_t)((y*20U+10U)/18U)*source->stride;
        uint8_t *dest=out->data+(size_t)y*out->stride;
        memset(dest,0,1280U*3U);
        for (x=0;x<1152;++x)
            memcpy(dest+(x+64U)*3U,row+((x*20U+10U)/18U)*3U,3);
    }
    return GAME_RENDER_OK;
}
