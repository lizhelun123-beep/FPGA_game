/* Synthetic/offline regression of the actual restored detector and beam core. */
#include "game_beam.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define W 1280
#define H 720
#define STRIDE (W*3+64)
static unsigned char image[H*STRIDE];
static const float pi=3.14159265358979323846f;

static void background(void)
{
    int y;
    memset(image,0xA5,sizeof image);
    for (y=0;y<H;++y) memset(image+y*STRIDE,120,W*3);
}

static void shape(int cx,int cy,float angle,float width,float height,
                  unsigned color,int circle)
{
    int x,y;
    float ux=cosf(angle),uy=sinf(angle);
    int radius=(int)ceilf(hypotf(width,height))+2;
    for(y=cy-radius;y<=cy+radius;++y) for(x=cx-radius;x<=cx+radius;++x) {
        float dx=(float)(x-cx),dy=(float)(y-cy);
        float a=dx*ux+dy*uy,b=-dx*uy+dy*ux;
        unsigned char *p;
        if(x<0 || y<0 || x>=W || y>=H) continue;
        if(circle ? dx*dx+dy*dy>width*width : fabsf(a)>width/2 || fabsf(b)>height/2) continue;
        p=image+y*STRIDE+x*3;
        p[0]=(unsigned char)color; p[1]=(unsigned char)(color>>8); p[2]=(unsigned char)(color>>16);
    }
}

static int detect(VisionDetection *d)
{
    int n=vision_detect_bgr888(image,W,H,STRIDE,d,VISION_MAX_DETECTIONS);
    int i,y,x;
    assert(n>=0);
    for(i=0;i<n;++i) { assert(d[i].type!=VISION_SOURCE); assert(d[i].geometry_is_effective); }
    for(y=0;y<H;++y) for(x=W*3;x<STRIDE;++x) assert(image[y*STRIDE+x]==0xA5);
    return n;
}

static VisionDetection *find(VisionDetection *d,int n,VisionType kind)
{
    int i;
    for(i=0;i<n;++i) if(d[i].type==kind) return &d[i];
    return NULL;
}

static void portal(int cx,int cy,float angle,unsigned body,int solid,int ring)
{
    int sx=cx-(int)lroundf(68*cosf(angle)),sy=cy-(int)lroundf(68*sinf(angle));
    int rx=cx+(int)lroundf(68*cosf(angle)),ry=cy+(int)lroundf(68*sinf(angle));
    shape(cx,cy,angle,200,64,body,0);
    if(solid) shape(sx,sy,0,8,8,0xffffffU,1);
    if(ring) {
        shape(rx,ry,0,15,15,0xffffffU,1);
        shape(rx,ry,0,10,10,body,1);
    }
}

static void test_markers(void)
{
    VisionDetection d[VISION_MAX_DETECTIONS],*p;
    SceneObject obj;
    int n,i;
    assert(vision_set_real_scene_profile(VISION_PROFILE_RESTORED)==0);
    /* No backend or measured-tag template is configured. */
    background(); shape(600,640,0,200,60,0xdcdc00U,0);
    shape(535,640,0,11,11,0x101010U,1); shape(665,640,0,11,11,0x101010U,1);
    n=detect(d); p=find(d,n,VISION_MIRROR); assert(p);
    assert(p->center_y>590 && p->major_length>110 && p->major_length<155);
    assert(ray_game_scene_from_detections(p,1,&obj,1)==1);
    assert(fabsf(obj.length-p->major_length)<.001f); /* No double .66. */
    background(); shape(600,640,0,200,60,0xdcdc00U,0);
    assert(!find(d,detect(d),VISION_MIRROR)); /* Black identity still required. */
    for(i=0;i<4;++i) {
        float a=(float)i*pi/2;
        background(); portal(600,360,a,0x1464c8U,1,1);
        n=detect(d); p=find(d,n,VISION_PORTAL_A); assert(p);
        assert(p->axis_x*cosf(a)+p->axis_y*sinf(a)>.995f);
        background(); portal(600,360,a,0xffa000U,1,1);
        n=detect(d); p=find(d,n,VISION_PORTAL_B); assert(p);
        assert(p->axis_x*cosf(a)+p->axis_y*sinf(a)>.995f);
    }
    background(); portal(600,640,0,0x1464c8U,1,1);
    assert(find(d,detect(d),VISION_PORTAL_A));
    background(); portal(600,360,0,0x1464c8U,1,0);
    assert(!find(d,detect(d),VISION_PORTAL_A));
    background(); portal(600,360,0,0x1464c8U,0,1);
    assert(!find(d,detect(d),VISION_PORTAL_A));
    background(); shape(600,360,0,200,60,0x101010U,0);
    assert(!find(d,detect(d),VISION_WALL)); /* Bars cannot be bypassed. */
    shape(524,360,0,12,60,0xffffffU,0); shape(676,360,0,12,60,0xffffffU,0);
    n=detect(d); assert(find(d,n,VISION_WALL));
    background(); shape(600,360,0,40,40,0x309030U,1);
    n=detect(d); p=find(d,n,VISION_TARGET); assert(p);
    assert(p->major_length==p->minor_width);
}

static void test_exit(void)
{
    int i,side,policy,angle_case;
    SceneObject objects[2];
    for(i=0;i<8;++i) for(side=-1;side<=1;side+=2)
    for(policy=-1;policy<=1;policy+=2) for(angle_case=-1;angle_case<=1;++angle_case) {
        float a=(float)i*pi/4;
        RayPoint u={cosf(a),sinf(a)},v={-sinf(a),cosf(a)};
        RayGameResult r;
        const float hit_y=384.5f; /* local_u=.35 on the entry long edge. */
        float tangent=(float)angle_case*.4f;
        float normal=sqrtf(1-tangent*tangent);
        RayPoint incoming={-(float)side*normal,tangent};
        RayPoint origin={300+(float)side*15-120*incoming.x,hit_y-120*incoming.y};
        memset(objects,0,sizeof objects);
        objects[0].type=RAY_OBJECT_PORTAL_A; objects[0].center=(RayPoint){300,360};
        objects[0].axis=(RayPoint){0,1}; objects[0].length=140; objects[0].width=30;
        objects[1].type=RAY_OBJECT_PORTAL_B; objects[1].center=(RayPoint){900,360};
        objects[1].axis=u; objects[1].length=140; objects[1].width=30;
        assert(ray_game_trace_from_emitter_policy(objects,2,W,H,origin,incoming,policy,&r)==0);
        assert(r.segment_count>=2 && r.hit_types[0]==RAY_OBJECT_PORTAL_A);
        assert(fabsf(r.segments[1].start.x-(900+24.5f*u.x+16*(float)policy*v.x))<.02f);
        assert(fabsf(r.segments[1].start.y-(360+24.5f*u.y+16*(float)policy*v.y))<.02f);
        {
            float dx=r.segments[1].end.x-r.segments[1].start.x;
            float dy=r.segments[1].end.y-r.segments[1].start.y;
            assert((dx*v.x+dy*v.y)*(float)policy>0);
            assert(fabsf(dx*u.x+dy*u.y)<.1f);
        }
    }
}

static void test_complete_scene(void)
{
    VisionDetection d[VISION_MAX_DETECTIONS];
    GameBeam b;
    GameBeamConfig c={GAME_BEAM_CONFIG_VERSION,W,H,{32,500},{1,0},0,
                      VISION_STABILITY_B,VISION_PROFILE_RESTORED,6000,250,1};
    GameDetectionFrame f;
    int n;
    background();
    shape(250,150,0,200,60,0xdcdc00U,0);
    shape(185,150,0,11,11,0x101010U,1); shape(315,150,0,11,11,0x101010U,1);
    portal(600,150,0,0x1464c8U,1,1);
    portal(1000,150,0,0xffa000U,1,1);
    shape(250,350,0,200,60,0x101010U,0);
    shape(174,350,0,12,60,0xffffffU,0); shape(326,350,0,12,60,0xffffffU,0);
    shape(600,350,0,40,40,0x309030U,1);
    n=detect(d); assert(n==5);
    assert(find(d,n,VISION_MIRROR) && find(d,n,VISION_PORTAL_A) &&
           find(d,n,VISION_PORTAL_B) && find(d,n,VISION_WALL) && find(d,n,VISION_TARGET));
    assert(game_beam_init(&b,&c,1,1)==GAME_BEAM_OK);
    f=(GameDetectionFrame){{1,1,10},1,0,d,n};
    assert(game_beam_submit(&b,&f,0,11)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){1,2,110};
    assert(game_beam_submit(&b,&f,0,111)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&b)->object_count==5);
    assert(game_beam_snapshot(&b)->supported_mask==GAME_BEAM_PHYSICAL_MASK);
    assert(game_beam_snapshot(&b)->ray.segment_count==1);
    assert(game_beam_snapshot(&b)->ray.segments[0].start.x==32);
}

static void test_retention(void)
{
    GameBeam b;
    GameBeamConfig c={GAME_BEAM_CONFIG_VERSION,W,H,{32,360},{1,0},0,
                      VISION_STABILITY_B,VISION_PROFILE_RESTORED,6000,250,1};
    VisionDetection d;
    GameDetectionFrame f;
    GameBeamSnapshot shown;
    memset(&d,0,sizeof d); d.type=VISION_MIRROR;
    d.geometry_center_x=300; d.geometry_center_y=360;
    d.center_x=300; d.center_y=360; d.axis_y=1;
    d.major_length=100; d.minor_width=20; d.geometry_is_effective=1;
    f=(GameDetectionFrame){{1,1,10},1,0,&d,1};
    assert(game_beam_init(&b,&c,1,1)==GAME_BEAM_OK);
    assert(game_beam_submit(&b,&f,0,11)==GAME_BEAM_PENDING);
    assert(!game_beam_display_snapshot(&b,11,&shown));
    f.stamp.sequence=2; f.stamp.captured_ms=110;
    assert(game_beam_submit(&b,&f,0,111)==GAME_BEAM_OK);
    assert(game_beam_display_snapshot(&b,111,&shown) && shown.valid);
    d.geometry_center_x=320.0f; d.center_x=320; f.stamp.sequence=3; f.stamp.captured_ms=130;
    assert(game_beam_submit(&b,&f,0,131)==GAME_BEAM_PENDING);
    assert(!game_beam_snapshot(&b)->valid && !game_beam_snapshot(&b)->ray.segment_count);
    assert(game_beam_display_snapshot(&b,131,&shown));
    assert(shown.display_stale && !shown.valid && !shown.ray.success);
    assert(shown.sequence==2 && shown.captured_ms==110 && shown.objects[0].center.x==300);
    {
        VisionCanvas canvas={image,W,H,STRIDE,sizeof image};
        background();
        assert(game_beam_render(&shown,&canvas)==0);
        assert(image[360*STRIDE+200*3+1]==0x60); /* Dim retained ray. */
        assert(image[100*STRIDE+200*3+1]==120); /* Original camera background. */
        assert(image[360*STRIDE+W*3]==0xA5); /* Padding untouched. */
    }
    /* Further invalid observations cannot renew the display stamp. */
    f.stamp.sequence=4; f.stamp.captured_ms=150;
    assert(game_beam_submit(&b,&f,1U<<VISION_PORTAL_A,151)==GAME_BEAM_RESTRICTED);
    assert(game_beam_display_snapshot(&b,151,&shown) && shown.sequence==2);
    assert(!game_beam_display_snapshot(&b,6110,&shown));
    assert(game_beam_reset(&b,2,6120)==GAME_BEAM_OK);
    assert(!game_beam_display_snapshot(&b,6120,&shown));
    assert(!game_beam_snapshot(&b)->sequence);
    /* An observation gap >250 ms must still restart B acquisition. */
    f.stamp=(GameCaptureStamp){2,1,6130};
    assert(game_beam_submit(&b,&f,0,6131)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){2,2,6500};
    assert(game_beam_submit(&b,&f,0,6501)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){2,3,6600};
    assert(game_beam_submit(&b,&f,0,6601)==GAME_BEAM_OK);
    f.stamp=(GameCaptureStamp){2,4,6620}; f.count=0; f.detections=NULL;
    assert(game_beam_submit(&b,&f,0,6621)==GAME_BEAM_UNAVAILABLE);
    assert(game_beam_display_snapshot(&b,6621,&shown) && shown.sequence==3);
    assert(!game_beam_display_snapshot(&b,6850,&shown));
    f.stamp=(GameCaptureStamp){2,5,6880};
    assert(game_beam_submit(&b,&f,0,6881)==GAME_BEAM_OK); /* Explicit sustained removal. */
    assert(!game_beam_snapshot(&b)->object_count);
}

int main(void)
{
    test_markers(); test_exit(); test_complete_scene(); test_retention();
    puts("restored markers / Portal B exit / bounded same-frame retention checks passed");
    return 0;
}
