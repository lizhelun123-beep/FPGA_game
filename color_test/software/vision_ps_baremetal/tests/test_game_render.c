/* Deterministic host-only rendering. Observation poses reuse the existing
 * generated-anchor fixtures in test_game_loop.c; no detector or runtime fill. */
#include "game_render.h"
#include "game_config.h"
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define W 1280
#define H 800
#define STRIDE (W*3+19)
#define SPAN ((size_t)(H-1)*STRIDE+W*3)
#define GUARD 37
static unsigned checks;
#define CHECK(c) do { ++checks; if (!(c)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c); exit(1); } } while (0)
static uint8_t memory[GUARD+SPAN+GUARD],reference[SPAN];
static VisionCanvas canvas={memory+GUARD,W,H,STRIDE,SPAN};
static const char *preview_path;
static void guards(void)
{
    size_t i;
    int y;
    for (i=0;i<GUARD;++i) CHECK(memory[i]==0xa5 && memory[GUARD+SPAN+i]==0xa5);
    for (y=0;y<H-1;++y) for (i=W*3;i<STRIDE;++i) CHECK(canvas.data[(size_t)y*STRIDE+i]==0xa5);
}
static unsigned rgb(int x,int y)
{
    uint8_t *b=canvas.data+(size_t)y*canvas.stride+(size_t)x*3;
    return (unsigned)b[0]|((unsigned)b[1]<<8)|((unsigned)b[2]<<16);
}
static GameLoopOutput step(GameLoop *loop,uint64_t now,const GameLoopEvent *e)
{
    GameLoopOutput p;
    CHECK(game_loop_step(loop,now,e,&p)==GAME_OK);
    return p;
}
static GameLoopOutput menu(GameLoop *l,uint64_t now,GameMenuKind kind,unsigned id)
{
    GameLoopEvent e;
    memset(&e,0,sizeof e); e.kind=GAME_LOOP_MENU; e.data.menu=(GameMenuAction){kind,id};
    return step(l,now,&e);
}
static GameLoopOutput observation(GameLoop *l,uint64_t now,unsigned id,int unsolved,uint64_t seq)
{
    VisionDetection d[GAME_MAX_MODELS];
    GameLoopEvent e;
    const GameLevelConfig *level=&game_default_config.levels[id-1];
    int i;
    memset(d,0,sizeof d); memset(&e,0,sizeof e);
    for (i=0;i<level->object_count;++i) {
        const SceneObject *o=&level->objects[i].anchor;
        d[i].type=(VisionType)o->type;
        d[i].geometry_center_x=o->center.x; d[i].geometry_center_y=o->center.y;
        d[i].axis_x=d[i].source_direction_x=o->axis.x;
        d[i].axis_y=d[i].source_direction_y=o->axis.y;
        d[i].direction_valid=o->type==RAY_OBJECT_SOURCE;
        if (id==1 && unsolved && o->type==RAY_OBJECT_SOURCE) {
            d[i].axis_x=d[i].source_direction_x=0;
            d[i].axis_y=d[i].source_direction_y=1;
        }
    }
    e.kind=GAME_LOOP_DETECTION;
    e.data.detection=(GameDetectionFrame){{l->app.session.view.generation,seq,now},1,0,d,level->object_count};
    return step(l,now,&e);
}
static GameRenderStatus render(const GameLoopOutput *p)
{
    GameLoopOutput copy=*p;
    GameRenderStatus status=game_render(p,&game_default_config,&game_default_menu_layout,&game_default_render_config,&canvas);
    CHECK(!memcmp(p,&copy,sizeof copy)); guards(); return status;
}
static void unchanged(void) { CHECK(!memcmp(reference,canvas.data,SPAN)); guards(); }
static void test_rejections(GameLoopOutput *p)
{
    VisionCanvas c=canvas;
    GameRenderConfig r=game_default_render_config;
    GameLoopOutput bad=*p;
    memcpy(reference,canvas.data,SPAN);
#define BAD_BUFFER() CHECK(game_render(p,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_BUFFER); unchanged()
    c.width=0; BAD_BUFFER(); c=canvas; c.height=-1; BAD_BUFFER(); c=canvas;
    c.width=INT_MAX; BAD_BUFFER(); c=canvas; c.stride=W*3-1; BAD_BUFFER(); c=canvas;
    c.capacity=SPAN-1; BAD_BUFFER(); c=canvas; c.stride=SIZE_MAX; c.capacity=SIZE_MAX; BAD_BUFFER(); c=canvas;
    c.stride=SIZE_MAX/(H-1)+1; c.capacity=SIZE_MAX; BAD_BUFFER(); c=canvas;
    c.data=NULL; BAD_BUFFER(); c=canvas;
#undef BAD_BUFFER
    c.width=W-1;
    CHECK(game_render(p,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_LAYOUT); unchanged(); c=canvas;
    r.scene.x=INT_MAX;
    CHECK(game_render(p,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_LAYOUT); unchanged();
    r=game_default_render_config; r.scene=game_default_menu_layout.start;
    CHECK(game_render(p,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_LAYOUT); unchanged();
    r=game_default_render_config;
    bad.game.object_count=GAME_MAX_MODELS+1;
    CHECK(game_render(&bad,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_SNAPSHOT); unchanged();
    bad=*p; bad.game.ray.segment_count=RAY_GAME_MAX_SEGMENTS+1;
    CHECK(game_render(&bad,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_SNAPSHOT); unchanged();
    bad=*p; bad.menu.start_enabled=!bad.menu.start_enabled;
    CHECK(game_render(&bad,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_SNAPSHOT); unchanged();
    bad=*p; bad.game.objects[0].center.x=0.0f/0.0f;
    CHECK(game_render(&bad,&game_default_config,&game_default_menu_layout,&r,&c)==GAME_RENDER_BAD_SNAPSHOT); unchanged();
    puts("PASS dimension/stride/capacity/overflow/layout/mixed-menu/NaN rejection before writes");
}
static void test_clip(GameLoopOutput p)
{
    int i;
    GameMenuInput input;
    if (preview_path) {
        GameLoopOutput budget=p;
        FILE *file;
        /* Renderer capacity fixture only: repeat already published segments;
         * never synthesize observations or alter the running application. */
        for (i=budget.game.ray.segment_count;i<RAY_GAME_MAX_SEGMENTS;++i)
            budget.game.ray.segments[i]=p.game.ray.segments[i%p.game.ray.segment_count];
        budget.game.ray.segment_count=RAY_GAME_MAX_SEGMENTS;
        budget.game.render_budget_exceeded=1;
        CHECK(render(&budget)==GAME_RENDER_FULL_RAY);
        file=fopen(preview_path,"wb"); CHECK(file!=NULL);
        CHECK(game_render_write_ppm(&canvas,file)==GAME_RENDER_OK); CHECK(fclose(file)==0);
    }
    memset(&input,0,sizeof input); input.connected=1; input.x=INT_MIN; input.y=INT_MAX;
    p.menu=game_menu_view(&input,&game_default_menu_layout,&p.game);
    for (i=0;i<p.game.object_count;++i) {
        p.game.objects[i].center=(RayPoint){(i&1)?FLT_MAX:-FLT_MAX,(i&2)?FLT_MAX:-FLT_MAX};
        p.game.objects[i].length=FLT_MAX; p.game.objects[i].width=FLT_MAX;
        p.game.objects[i].source_tip=(RayPoint){FLT_MAX,-FLT_MAX};
    }
    p.game.ray.segment_count=RAY_GAME_MAX_SEGMENTS; p.game.render_budget_exceeded=1;
    for (i=0;i<RAY_GAME_MAX_SEGMENTS;++i)
        p.game.ray.segments[i]=(RaySegment){{-FLT_MAX,(float)i*30},{FLT_MAX,(float)i*30}};
    CHECK(render(&p)==GAME_RENDER_FULL_RAY);
    /* All 17 published segments have yellow pixels; nothing is truncated to 5. */
    for (i=0;i<RAY_GAME_MAX_SEGMENTS;++i) {
        double scale=419.0/game_default_config.height;
        int y=192+(int)lround(i*30*scale);
        int found=rgb(519,y)==0xFFE12AU || rgb(519,y+1)==0xFFE12AU || rgb(519,y-1)==0xFFE12AU;
        if (!found) fprintf(stderr,"segment %d y=%d rgb=%06x\n",i,y,rgb(519,y));
        CHECK(found);
    }
    game_render_text(&canvas,INT_MIN,INT_MAX,"场景无效TEXT",4,0xffffff);
    game_render_text(&canvas,INT_MAX,INT_MIN,"场景过期",4,0xffffff);
    game_render_text(&canvas,-13,-15,"光线游戏XYZ012",2,0xffffff);
    vision_canvas_text(&canvas,INT_MIN,INT_MAX,"SAFE",8,0xffffff);
    guards();
    /* Each of the six canonical model expressions, across all four edges. */
    for (i=0;i<RAY_OBJECT_TYPE_COUNT*4;++i) {
        SceneObject o=p.game.objects[0];
        o.type=(RayObjectType)(i%RAY_OBJECT_TYPE_COUNT);
        o.center=(RayPoint){(i/6&1)?1279:0,(i/6&2)?799:0};
        o.source_tip=o.center; o.axis=(RayPoint){1,0}; o.length=100; o.width=40;
        vision_canvas_object(&canvas,&o,1,0,0);
    }
    guards(); puts("PASS all six models / extreme finite coordinates / 17 full rays / pointer and UTF-8 clipping");
}
static void test_buttons(GameLoopOutput p)
{
    int i;
    GameMenuInput input;
    for (i=0;i<4;++i) {
        GameMenuRect r=i<3?game_default_menu_layout.levels[i].rect:game_default_menu_layout.start;
        GameMenuAction a;
        game_menu_input_init(&input); input.x=r.x+8; input.y=r.y+8;
        p.menu=game_menu_view(&input,&game_default_menu_layout,&p.game);
        CHECK(render(&p)==GAME_RENDER_OK);
        CHECK(rgb(r.x,r.y)!=rgb(r.x-1,r.y));
        CHECK(rgb(r.x+r.width-1,r.y)!=rgb(r.x+r.width,r.y));
        input.x=r.x; input.y=r.y;
        (void)game_menu_input(&input,&game_default_menu_layout,&p.game,(GameMouseEvent){GAME_MOUSE_LEFT_DOWN,0,0});
        a=game_menu_input(&input,&game_default_menu_layout,&p.game,(GameMouseEvent){GAME_MOUSE_LEFT_UP,0,0});
        CHECK(a.kind==(i<3?GAME_MENU_SELECT:GAME_MENU_START));
        input.x=r.x+r.width;
        CHECK(game_menu_view(&input,&game_default_menu_layout,&p.game).hover.kind==GAME_MENU_NONE);
        input.x=r.x; input.y=r.y+r.height;
        CHECK(game_menu_view(&input,&game_default_menu_layout,&p.game).hover.kind==GAME_MENU_NONE);
    }
    puts("PASS visual button edges equal actual half-open hit regions / explicit available start");
}

static void fit720_checks(void)
{
    const size_t stride=3840+17,span=719*stride+3840;
    uint8_t *bytes=malloc(span+32),*copy=malloc(span);
    VisionCanvas out={bytes+16,1280,720,stride,span},bad;
    unsigned x,y,k;
    CHECK(bytes && copy);
    for (y=0;y<800;++y) for (x=0;x<1280;++x) {
        uint8_t *p=canvas.data+(size_t)y*canvas.stride+x*3;
        p[0]=(uint8_t)x; p[1]=(uint8_t)y; p[2]=(uint8_t)(x+y);
    }
    memset(bytes,0xa5,span+32);
    CHECK(game_render_fit_720p(&canvas,&out)==GAME_RENDER_OK);
    for (y=0;y<720;y+=719) {
        for (x=0;x<64;++x) for (k=0;k<3;++k)
            CHECK(!out.data[y*stride+x*3+k] && !out.data[y*stride+(1216+x)*3+k]);
        for (x=0;x<1152;x+=1151) {
            const uint8_t *a=out.data+y*stride+(64+x)*3;
            const uint8_t *b=canvas.data+((y*20+10)/18)*canvas.stride+((x*20+10)/18)*3;
            CHECK(!memcmp(a,b,3));
        }
    }
    for (y=0;y<719;++y) for (x=3840;x<stride;++x) CHECK(out.data[y*stride+x]==0xa5);
    for (k=0;k<16;++k) CHECK(bytes[k]==0xa5 && bytes[16+span+k]==0xa5);
    memcpy(copy,out.data,span); bad=canvas; bad.height=799;
    CHECK(game_render_fit_720p(&bad,&out)==GAME_RENDER_BAD_BUFFER && !memcmp(copy,out.data,span));
    bad=out; bad.data=canvas.data; bad.capacity=canvas.capacity;
    CHECK(game_render_fit_720p(&canvas,&bad)==GAME_RENDER_BAD_BUFFER);
    free(copy); free(bytes);
}

int main(int argc,char **argv)
{
    fit720_checks();
    GameLoop l,before;
    GameLoopOutput p,old,changed;
    FILE *file;
    unsigned char header[3];
    CHECK(argc<=3); preview_path=argc>=2?argv[1]:NULL;
    memset(memory,0xa5,sizeof memory);
    CHECK(game_loop_init(&l,&game_default_config,&game_uncalibrated_identity_mapping,&game_default_menu_layout)==GAME_OK);
    p=step(&l,0,NULL); CHECK(render(&p)==GAME_RENDER_OK);
    p=menu(&l,0,GAME_MENU_SELECT,3); CHECK(render(&p)==GAME_RENDER_OK);
    p=observation(&l,1,3,0,1); before=l; old=p;
    CHECK(p.game.scene_valid && p.game.ready && p.game.object_count==5);
    CHECK(render(&p)==GAME_RENDER_OK); memcpy(reference,canvas.data,SPAN);
    CHECK(render(&p)==GAME_RENDER_OK); unchanged(); CHECK(!memcmp(&l,&before,sizeof l));
    test_rejections(&p); test_clip(p); test_buttons(p);
    p=menu(&l,2,GAME_MENU_START,0); CHECK(p.game.state==GAME_RUNNING); CHECK(render(&p)==GAME_RENDER_OK);
    p=step(&l,300,NULL); CHECK(!p.game.scene_valid && p.game.scene_status==GAME_STALE_SCENE);
    CHECK(render(&p)==GAME_RENDER_OK); memcpy(reference,canvas.data,SPAN);
    /* Invalid geometry cannot masquerade as a fresh scene even if arrays remain. */
    changed=p; memcpy(changed.game.objects,old.game.objects,sizeof old.game.objects); changed.game.object_count=old.game.object_count;
    changed.game.ray=old.game.ray; CHECK(render(&changed)==GAME_RENDER_OK);
    /* Scene region is identical; footer deliberately reports the stored ray count. */
    { int y; for (y=192;y<612;++y) CHECK(!memcmp(reference+(size_t)y*STRIDE+80*3,canvas.data+(size_t)y*STRIDE+80*3,880*3)); }
    p=step(&l,180002,NULL); CHECK(p.game.state==GAME_TIMED_OUT && !p.game.remaining_ms); CHECK(render(&p)==GAME_RENDER_OK);
    p=menu(&l,180003,GAME_MENU_SELECT,1); CHECK(p.game.generation==old.game.generation+1 && !p.game.stars && !p.game.object_count);
    CHECK(render(&p)==GAME_RENDER_OK);
    p=observation(&l,180004,1,1,1); CHECK(p.game.ready); CHECK(render(&p)==GAME_RENDER_OK);
    p=menu(&l,180005,GAME_MENU_START,0); p=observation(&l,180006,1,0,2);
    CHECK(p.game.state==GAME_CLEARED && p.game.stars==3 && p.game.captured_ms==180006 && p.game.scene_sequence==2);
    CHECK(render(&p)==GAME_RENDER_OK); memcpy(reference,canvas.data,SPAN);
    /* Changing each member in the same full publication affects its own pixels. */
    changed=p; changed.game.stars=1; CHECK(render(&changed)==GAME_RENDER_OK); CHECK(memcmp(reference,canvas.data,SPAN));
    changed=p; changed.game.remaining_ms=1234; CHECK(render(&changed)==GAME_RENDER_OK); CHECK(memcmp(reference,canvas.data,SPAN));
    changed=p; changed.game.generation++; CHECK(render(&changed)==GAME_RENDER_OK); CHECK(memcmp(reference,canvas.data,SPAN));
    changed=p; changed.game.objects[0].center.x+=100; CHECK(render(&changed)==GAME_RENDER_OK); CHECK(memcmp(reference,canvas.data,SPAN));
    changed=p; changed.game.ray.segment_count=0; CHECK(render(&changed)==GAME_RENDER_OK); CHECK(memcmp(reference,canvas.data,SPAN));
    changed=p; changed.menu.connected=0; changed.menu.hover=(GameMenuAction){GAME_MENU_NONE,0}; CHECK(render(&changed)==GAME_RENDER_OK);
    CHECK(memcmp(reference,canvas.data,SPAN));
    CHECK(render(&p)==GAME_RENDER_OK);
    file=tmpfile(); CHECK(file!=NULL); CHECK(game_render_write_ppm(&canvas,file)==GAME_RENDER_OK);
    rewind(file); CHECK(fread(header,1,3,file)==3 && !memcmp(header,"P6\n",3)); CHECK(fclose(file)==0);
    puts("PASS full-publication determinism / game immutability / prepare/run/clear/timeout/stale/disconnect / level generation clearing / PPM");
    if (argc==3) {
        GameRenderAssets art={0};
        GameLoopOutput preserved=p;
        CHECK(game_render_assets_load(&art,argv[2],&game_default_config,&game_default_render_config)==GAME_RENDER_OK);
        CHECK(art.loads==1 && art.bytes==13956928U);
        {
            VisionCanvas overlap=canvas;
            overlap.data=art.storage+4000000U;
            CHECK(game_render_cached(&p,&game_default_config,&game_default_menu_layout,&game_default_render_config,&art,&overlap)==GAME_RENDER_BAD_BUFFER);
        }
        CHECK(game_render_assets_load(&art,argv[2],&game_default_config,&game_default_render_config)==GAME_RENDER_BAD_ASSET);
        CHECK(game_render_cached(&p,&game_default_config,&game_default_menu_layout,&game_default_render_config,&art,&canvas)==GAME_RENDER_OK);
        guards(); memcpy(reference,canvas.data,SPAN);
        changed=p; changed.game.objects[0].center.x+=130; changed.game.objects[0].axis=(RayPoint){1,0};
        CHECK(game_render_cached(&changed,&game_default_config,&game_default_menu_layout,&game_default_render_config,&art,&canvas)==GAME_RENDER_OK);
        CHECK(memcmp(reference,canvas.data,SPAN)); guards();
        CHECK(game_render_cached(&p,&game_default_config,&game_default_menu_layout,&game_default_render_config,&art,&canvas)==GAME_RENDER_OK);
        unchanged(); CHECK(!memcmp(&p,&preserved,sizeof p));
        changed=p; changed.game.objects[0].center=(RayPoint){FLT_MAX,-FLT_MAX};
        CHECK(game_render_cached(&changed,&game_default_config,&game_default_menu_layout,&game_default_render_config,&art,&canvas)==GAME_RENDER_OK);
        guards();
        game_render_assets_free(&art); CHECK(!art.storage && !art.bytes && !art.loads);
        game_render_assets_free(&art);
        puts("PASS resident cached compositor / guard and stride preservation / immutable snapshot / moving restore / hostile clip / single-load lifecycle");
    }
    printf("game_render: %u assertions passed\n",checks); return 0;
}
