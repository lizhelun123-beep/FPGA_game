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

static void portal_scaled(int cx,int cy,float angle,unsigned body,int solid,int ring,float scale)
{
    int sx=cx-(int)lroundf(68*scale*cosf(angle)),sy=cy-(int)lroundf(68*scale*sinf(angle));
    int rx=cx+(int)lroundf(68*scale*cosf(angle)),ry=cy+(int)lroundf(68*scale*sinf(angle));
    shape(cx,cy,angle,200*scale,64*scale,body,0);
    if(solid) shape(sx,sy,0,8*scale,8*scale,0xffffffU,1);
    if(ring) {
        shape(rx,ry,0,15*scale,15*scale,0xffffffU,1);
        shape(rx,ry,0,10*scale,10*scale,body,1);
    }
}
static void portal(int cx,int cy,float angle,unsigned body,int solid,int ring)
{portal_scaled(cx,cy,angle,body,solid,ring,1);}

static void ring_sectors(int cx,int cy,unsigned color,unsigned sector_mask)
{
    int x,y;
    for(y=cy-16;y<=cy+16;++y) for(x=cx-16;x<=cx+16;++x) {
        int dx=x-cx,dy=y-cy;
        int radius_sq=dx*dx+dy*dy;
        unsigned sector;
        unsigned char *p;
        if(x<0 || y<0 || x>=W || y>=H || radius_sq<10*10 || radius_sq>15*15)
            continue;
        if(dy<0) sector=dx>=0 ? 0U : 1U;
        else sector=dx<0 ? 2U : 3U;
        if(!(sector_mask&(1U<<sector))) continue;
        p=image+y*STRIDE+x*3;
        p[0]=(unsigned char)color; p[1]=(unsigned char)(color>>8); p[2]=(unsigned char)(color>>16);
    }
}

static void portal_radial_fixture(VisionType type,float angle,unsigned sector_mask,
                                  int solid,int second_ring,int filled_ring)
{
    const unsigned body=type==VISION_PORTAL_A ? 0x424c80U : 0x806c42U;
    const unsigned warm_white=0xb8ae8cU;
    int sx=600-(int)lroundf(68*cosf(angle));
    int sy=360-(int)lroundf(68*sinf(angle));
    int rx=600+(int)lroundf(68*cosf(angle));
    int ry=360+(int)lroundf(68*sinf(angle));
    background();
    shape(600,360,angle,200,64,body,0);
    if(solid) shape(sx,sy,0,8,8,warm_white,1);
    if(filled_ring) shape(rx,ry,0,15,15,warm_white,1);
    else ring_sectors(rx,ry,warm_white,sector_mask);
    if(second_ring) ring_sectors(sx,sy,warm_white,sector_mask);
}

static void test_portal_radial_ring_fallback(void)
{
    VisionDetection d[VISION_MAX_DETECTIONS],*p;
    int i,k,n;
    /* Same radial implementation for blue A/orange B. Check a fragmented
     * 3/4 ring over all8rotations while the solid endpoint is unusable. */
    for(k=0;k<2;++k) {
        VisionType type=k ? VISION_PORTAL_B : VISION_PORTAL_A;
        for(i=0;i<8;++i) {
            float angle=(float)i*pi/4.0f;
            portal_radial_fixture(type,angle,0x7U,0,0,0);
            n=detect(d); p=find(d,n,type);
            assert(p);
            assert(p->confidence_percent==96);
            assert(p->axis_x*cosf(angle)+p->axis_y*sinf(angle)>.98f);
            assert(fabsf(p->geometry_center_x-600)<12.0f);
            assert(fabsf(p->geometry_center_y-360)<12.0f);
        }
        /* Real solid+ring stays on the highest-confidence path. */
        portal_radial_fixture(type,0,0xfU,1,0,0);
        p=find(d,detect(d),type); assert(p && p->confidence_percent==100);
        /* Half ring, filled highlight, non-body center and two independent
         * rings remain identity failures for both carriers. */
        portal_radial_fixture(type,0,0x3U,0,0,0);
        assert(!find(d,detect(d),type));
        portal_radial_fixture(type,0,0xfU,0,0,1);
        assert(!find(d,detect(d),type));
        portal_radial_fixture(type,0,0xfU,0,0,0);
        shape(668,360,0,8,8,0x505050U,1);
        assert(!find(d,detect(d),type));
        portal_radial_fixture(type,0,0xfU,0,1,0);
        assert(!find(d,detect(d),type));
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
    for(i=0;i<8;++i) {
        float a=(float)i*pi/4;
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
    n=detect(d); p=find(d,n,VISION_PORTAL_A); assert(p && p->confidence_percent==96);
    background(); shape(600,360,0,200,60,0x101010U,0);
    assert(!find(d,detect(d),VISION_WALL)); /* Bars cannot be bypassed. */
    shape(524,360,0,12,60,0xffffffU,0); shape(676,360,0,12,60,0xffffffU,0);
    n=detect(d); assert(find(d,n,VISION_WALL));
    background(); shape(600,360,0,40,40,0x309030U,1);
    n=detect(d); p=find(d,n,VISION_TARGET); assert(p);
    assert(p->major_length==p->minor_width);
}

static void test_pale_blocks(void)
{
    VisionDetection d[VISION_MAX_DETECTIONS];
    VisionDetectionDiagnostics s;
    int i,n;
    /* Screen-derived pale colors, validated as synthetic controlled inputs.
     * Endpoints remain mandatory at every orientation, not a color-only pass. */
    for(i=0;i<8;++i) {
        float a=(float)i*pi/4;
        background(); portal(600,360,a,0xbdac8aU,1,1);
        assert(find(d,detect(d),VISION_PORTAL_B));
        /* Use actual pale blue R=166 G=211 B=254. */
        background(); portal(600,360,a,0xa6d3feU,1,1);
        assert(find(d,detect(d),VISION_PORTAL_A));
        background(); portal(600,360,a,0xbdac8aU,1,0);
        assert(!find(d,detect(d),VISION_PORTAL_B));
        /*50cm ->38.5cm gives about1.30x projected length on a flat plane. */
        background(); portal_scaled(600,360,a,0xbdac8aU,1,1,1.30f);
        assert(find(d,detect(d),VISION_PORTAL_B));
        background(); portal_scaled(600,360,a,0xa6d3feU,1,1,1.30f);
        assert(find(d,detect(d),VISION_PORTAL_A));
    }
    background(); shape(600,360,0,200,64,0xffffd5U,0);
    shape(535,360,0,11,11,0x535353U,1); shape(665,360,0,11,11,0x535353U,1);
    assert(find(d,detect(d),VISION_MIRROR)); /* relative darkness, not absolute black */
    background(); shape(600,360,0,200,64,0xffffd5U,0);
    assert(!find(d,detect(d),VISION_MIRROR));
    background(); shape(600,360,pi/2,210,76,0x3b3b3bU,0);
    shape(600,275,0,76,24,0xffffffU,0); shape(600,445,0,76,24,0xffffffU,0);
    n=detect(d); assert(find(d,n,VISION_WALL));
    vision_get_detection_diagnostics(&s); assert(s.wall_marker_accepted==1);
    background(); shape(600,360,pi/2,210,76,0x3b3b3bU,0);
    shape(600,275,0,76,24,0xffffffU,0);
    assert(!find(d,detect(d),VISION_WALL)); /* still requires a pair */
    background(); shape(600,360,pi/2,273,99,0x3b3b3bU,0);
    shape(600,249,0,99,31,0xffffffU,0); shape(600,471,0,99,31,0xffffffU,0);
    assert(find(d,detect(d),VISION_WALL));
    background(); shape(600,360,0,40,40,0x8fbabaU,1); /* cyan green H90: must reject */
    assert(!find(d,detect(d),VISION_TARGET));
    background(); shape(600,360,0,40,40,0x8ab4a0U,1); /* low-S green */
    assert(find(d,detect(d),VISION_TARGET));
    background(); assert(detect(d)==0);
    vision_get_detection_diagnostics(&s);
    assert(!s.mask_pixels[6] && !s.accepted[VISION_MIRROR]);
}

static void test_exit(void)
{
    int i,side,policy,angle_case,entry_case;
    SceneObject objects[2];
    for(i=0;i<8;++i) for(side=-1;side<=1;side+=2)
    for(policy=-1;policy<=1;policy+=2) for(angle_case=-1;angle_case<=1;++angle_case)
    for(entry_case=-9;entry_case<=9;++entry_case) {
        float a=(float)i*pi/4;
        RayPoint u={cosf(a),sinf(a)},v={-sinf(a),cosf(a)};
        RayGameResult r;
        const float offset=(float)entry_case*7.0f; /* local_u=-.9..+.9: full long edge. */
        const float hit_y=360.0f+offset;
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
        assert(fabsf(r.segments[1].start.x-(900+offset*u.x+16*(float)policy*v.x))<.02f);
        assert(fabsf(r.segments[1].start.y-(360+offset*u.y+16*(float)policy*v.y))<.02f);
        {
            float dx=r.segments[1].end.x-r.segments[1].start.x;
            float dy=r.segments[1].end.y-r.segments[1].start.y;
            assert((dx*v.x+dy*v.y)*(float)policy>0);
            assert(fabsf(dx*u.x+dy*u.y)<.1f);
        }
    }
}

static void shaded_portal(float a,unsigned body,unsigned white,int faded_end,int ring)
{
    int sx=600-(int)lroundf(68*cosf(a)),sy=360-(int)lroundf(68*sinf(a));
    int rx=600+(int)lroundf(68*cosf(a)),ry=360+(int)lroundf(68*sinf(a));
    background();
    shape(600,360,a,200,64,body,0);
    if(faded_end) shape(600-(int)lroundf(80*cosf(a)),360-(int)lroundf(80*sinf(a)),
                        a,40,64,0x555555U,0); /* Lost colored tip, marks still visible. */
    shape(sx,sy,0,8,8,white,1);
    if(ring) {
        shape(rx,ry,0,15,15,white,1);
        shape(rx,ry,0,10,10,body,1);
    }
}

static void test_dim_portal_pose(void)
{
    static const unsigned bodies[2]={0x46535fU,0x6e5837U};
    static const unsigned whites[2]={0x888888U,0x949494U}; /* Both below globalV150. */
    VisionDetection d[VISION_MAX_DETECTIONS],*p;
    VisionDetectionDiagnostics stats;
    int k,i,faded;
    for(k=0;k<2;++k) for(i=0;i<8;++i) for(faded=0;faded<2;++faded) {
        float a=(float)i*pi/4;
        VisionType type=k ? VISION_PORTAL_B : VISION_PORTAL_A;
        shaded_portal(a,bodies[k],whites[k],faded,1);
        p=find(d,detect(d),type); assert(p);
        assert(fabsf(p->geometry_center_x-600)<2 && fabsf(p->geometry_center_y-360)<2);
        assert(p->axis_x*cosf(a)+p->axis_y*sinf(a)>.998f);
        vision_get_detection_diagnostics(&stats);
        assert(!stats.mask_pixels[6]); /* Global white/WALL rules unchanged. */
        shaded_portal(a,bodies[k],whites[k],faded,0);
        assert(!find(d,detect(d),type)); /* Missing ring still rejected in dim light. */
        shaded_portal(a,bodies[k],0x646464U,faded,1);
        assert(!find(d,detect(d),type)); /* No local bright contrast, no identity. */
    }
    /* Two white disks cannot substitute for the solid+colored-center ring. */
    shaded_portal(0,bodies[0],whites[0],0,1);
    shape(668,360,0,15,15,whites[0],1);
    assert(!find(d,detect(d),VISION_PORTAL_A));
    /* Off-carrier pairs remain rejected by finite span/center/alignment gates. */
    background(); shape(600,360,0,200,64,bodies[0],0);
    shape(600,300,0,8,8,whites[0],1);
    shape(600,420,0,15,15,whites[0],1); shape(600,420,0,10,10,bodies[0],1);
    assert(!find(d,detect(d),VISION_PORTAL_A));
}

static void test_desaturated_portal_and_warm_marks(void)
{
    const unsigned blue=0x464a50U; /* HSV S~32: carrier, not global white. */
    const unsigned orange=0x806c42U;
    const unsigned warm=0xb8ae8cU; /* S~61: warm-cast local white. */
    VisionDetection d[VISION_MAX_DETECTIONS],*p;
    VisionDetectionDiagnostics stats;
    int i,k;
    for(k=0;k<2;++k) for(i=0;i<8;++i) {
        float a=(float)i*pi/4;
        unsigned body=k ? orange : blue;
        VisionType type=k ? VISION_PORTAL_B : VISION_PORTAL_A;
        shaded_portal(a,body,warm,0,1);
        p=find(d,detect(d),type); assert(p);
        assert(fabsf(p->geometry_center_x-600)<2 && fabsf(p->geometry_center_y-360)<2);
        assert(p->axis_x*cosf(a)+p->axis_y*sinf(a)>.998f);
        vision_get_detection_diagnostics(&stats);
        assert(!stats.mask_pixels[6]); /* Warm local marks do not change global white. */
        shaded_portal(a,body,warm,0,0);
        assert(!find(d,detect(d),type));
        shaded_portal(a,body,0xb8a070U,0,1); /* Colored marks exceed local S bound. */
        assert(!find(d,detect(d),type));
    }
    shaded_portal(0,blue,warm,0,1);
    shape(668,360,0,15,15,warm,1); /* Two disks still cannot become a Portal. */
    assert(!find(d,detect(d),VISION_PORTAL_A));
    shaded_portal(0,0x505050U,warm,0,1); /* A grey carrier has no blue identity. */
    assert(!find(d,detect(d),VISION_PORTAL_A));
    /* Bright pale body joins the warm mask and engulfs the solid mark; the
     * strict local retry must retain the original complete marker pair. */
    background();
    shape(600,360,0,200,64,0xc8b496U,0);
    shape(545,360,0,65,42,0xe6d2b4U,0);
    shape(532,360,0,8,8,0xffffffU,1);
    shape(668,360,0,15,15,0xffffffU,1);
    shape(668,360,0,10,10,0xc8b496U,1);
    p=find(d,detect(d),VISION_PORTAL_B); assert(p);
    assert(fabsf(p->geometry_center_x-600)<2 && p->axis_x>.998f);
}

static void test_complete_scene(void)
{
    VisionDetection d[VISION_MAX_DETECTIONS];
    VisionDetectionDiagnostics stats;
    GameBeam b;
    GameBeamConfig c={GAME_BEAM_CONFIG_VERSION,W,H,{32,500},{1,0},0,
                      VISION_STABILITY_B,VISION_PROFILE_RESTORED,6000,250,1,250};
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
    vision_get_detection_diagnostics(&stats);
    assert(stats.mask_pixels[0] && stats.mask_pixels[1] && stats.mask_pixels[2]);
    assert(stats.mask_pixels[3] && stats.mask_pixels[5] && stats.mask_pixels[6]);
    assert(stats.component_candidates[VISION_MIRROR] > 0);
    assert(stats.component_candidates[VISION_PORTAL_A] > 0);
    assert(stats.component_candidates[VISION_PORTAL_B] > 0);
    assert(stats.component_candidates[VISION_TARGET] > 0);
    assert(stats.geometry_pass[VISION_MIRROR] > 0);
    assert(stats.marker_pass[VISION_MIRROR] > 0);
    assert(stats.marker_pass[VISION_PORTAL_A] > 0);
    assert(stats.marker_pass[VISION_PORTAL_B] > 0);
    assert(stats.accepted[VISION_MIRROR] == 1);
    assert(stats.accepted[VISION_PORTAL_A] == 1);
    assert(stats.accepted[VISION_PORTAL_B] == 1);
    assert(stats.accepted[VISION_TARGET] == 1);
    assert(stats.accepted[VISION_WALL] == 1);
    assert(stats.wall_marker_components >= 2 && stats.wall_marker_accepted == 1);
    assert(game_beam_init(&b,&c,1,1)==GAME_BEAM_OK);
    f=(GameDetectionFrame){{1,1,10},1,0,d,n};
    assert(game_beam_submit(&b,&f,0,11)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){1,2,110};
    assert(game_beam_submit(&b,&f,0,111)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&b)->object_count==5);
    assert(game_beam_snapshot(&b)->supported_mask==GAME_BEAM_PHYSICAL_MASK);
    assert(game_beam_snapshot(&b)->ray.segment_count==1);
    assert(game_beam_snapshot(&b)->ray.segments[0].start.x==32);

    /* User-authorized slow-input policy: actual 266/318ms input cadence now
     * confirms the SAME five-class scene; 350 is inclusive, 351 reacquires.
     * The default250 fixtures elsewhere retain their original policy. */
    c.stability_support_gap_ms=350;
    assert(game_beam_init(&b,&c,2,1)==GAME_BEAM_OK);
    f.stamp=(GameCaptureStamp){2,1,5476};
    assert(game_beam_submit(&b,&f,0,5713)==GAME_BEAM_PENDING);
    assert(!game_beam_snapshot(&b)->missing_mask); /* No physical SOURCE. */
    f.stamp=(GameCaptureStamp){2,2,5742};
    assert(game_beam_submit(&b,&f,0,5980)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&b)->valid && game_beam_snapshot(&b)->object_count==5);
    assert(game_beam_snapshot(&b)->captured_ms==5742);
    assert(game_beam_snapshot(&b)->supported_mask==GAME_BEAM_PHYSICAL_MASK);
    assert(game_beam_snapshot(&b)->ray.segment_count>0);
    f.stamp=(GameCaptureStamp){2,3,6060};
    assert(game_beam_submit(&b,&f,0,6298)==GAME_BEAM_OK);
    f.stamp=(GameCaptureStamp){2,4,6410};
    assert(game_beam_submit(&b,&f,0,6648)==GAME_BEAM_OK);
    f.stamp=(GameCaptureStamp){2,5,6761};
    assert(game_beam_submit(&b,&f,0,6999)==GAME_BEAM_PENDING);
    assert(!game_beam_snapshot(&b)->valid && !game_beam_snapshot(&b)->object_count);
    assert(!game_beam_snapshot(&b)->ray.segment_count);
    assert(game_beam_snapshot(&b)->captured_ms==6761);
    f.stamp=(GameCaptureStamp){2,6,7111};
    assert(game_beam_submit(&b,&f,0,7349)==GAME_BEAM_OK);
    assert(game_beam_reset(&b,3,7350)==GAME_BEAM_OK);
    f.stamp=(GameCaptureStamp){3,1,7360};
    assert(game_beam_submit(&b,&f,0,7361)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){3,2,7678};
    assert(game_beam_submit(&b,&f,0,7679)==GAME_BEAM_OK);
    /* A real miss still invalidates the current scene, despite the longer
     * support gap. The separately bounded display keeps its original stamp. */
    f.stamp=(GameCaptureStamp){3,3,7690}; f.detections=NULL; f.count=0;
    assert(game_beam_submit(&b,&f,0,7691)==GAME_BEAM_UNAVAILABLE);
    assert(!game_beam_snapshot(&b)->valid && !game_beam_snapshot(&b)->ray.segment_count);
    assert(game_beam_snapshot(&b)->missing_mask==GAME_BEAM_PHYSICAL_MASK);
    assert(game_beam_snapshot(&b)->captured_ms==7690);
}

static void test_retention(void)
{
    GameBeam b;
    GameBeamConfig c={GAME_BEAM_CONFIG_VERSION,W,H,{32,360},{1,0},0,
                      VISION_STABILITY_B,VISION_PROFILE_RESTORED,6000,250,1,250};
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
        assert(image[360*STRIDE+200*3+1]==0xFF); /* Retained ray keeps full brightness. */
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
    /* Picture age reaching the250ms removal grace must not blank a frame
     * while waiting for the next measured subset to be admitted. */
    assert(game_beam_display_snapshot(&b,6850,&shown));
    assert(shown.display_stale && shown.sequence==3 && shown.captured_ms==6600);
    f.stamp=(GameCaptureStamp){2,5,6880};
    assert(game_beam_submit(&b,&f,0,6881)==GAME_BEAM_OK); /* Explicit sustained removal. */
    assert(!game_beam_snapshot(&b)->object_count);
}

static void test_constant_picture_after_long_gap(void)
{
    static unsigned char reference[sizeof image];
    GameBeam b;
    GameBeamConfig c={GAME_BEAM_CONFIG_VERSION,W,H,{32,360},{1,0},0,
                      VISION_STABILITY_B,VISION_PROFILE_RESTORED,6000,250,1,350};
    VisionDetection d;
    GameDetectionFrame f;
    GameBeamSnapshot shown;
    VisionCanvas canvas={image,W,H,STRIDE,sizeof image};
    memset(&d,0,sizeof d); d.type=VISION_MIRROR;
    d.geometry_center_x=300; d.geometry_center_y=360;
    d.center_x=300; d.center_y=360; d.axis_y=1;
    d.major_length=100; d.minor_width=20; d.geometry_is_effective=1;
    f=(GameDetectionFrame){{1,1,10},1,0,&d,1};
    assert(game_beam_init(&b,&c,1,1)==GAME_BEAM_OK);
    assert(game_beam_submit(&b,&f,0,11)==GAME_BEAM_PENDING);
    assert(!game_beam_display_snapshot(&b,11,&shown)); /* No invented first frame. */
    assert(!game_beam_retained_snapshot(&b,&shown));
    f.stamp=(GameCaptureStamp){1,2,276};
    assert(game_beam_submit(&b,&f,0,277)==GAME_BEAM_OK);
    assert(game_beam_display_snapshot(&b,277,&shown) && shown.valid);
    background();
    assert(!game_beam_render(&shown,&canvas));
    memcpy(reference,image,sizeof image);

    /* A1300ms observation gap still resets B, but cannot blank/dim the
     * previously confirmed picture. New pose does not leak into that picture. */
    d.geometry_center_x=320; d.center_x=320;
    f.stamp=(GameCaptureStamp){1,3,1576};
    assert(game_beam_submit(&b,&f,0,1813)==GAME_BEAM_PENDING);
    assert(!game_beam_snapshot(&b)->valid && !game_beam_snapshot(&b)->ray.segment_count);
    assert(game_beam_display_snapshot(&b,1813,&shown));
    assert(shown.display_stale && !shown.valid && !shown.ray.success);
    assert(shown.sequence==2 && shown.captured_ms==276 && shown.objects[0].center.x==300);
    background();
    assert(!game_beam_render(&shown,&canvas));
    assert(!memcmp(reference,image,sizeof image)); /* All pixels, lines and row padding. */

    /* More pending/restricted input never refreshes the retained stamp. */
    f.stamp=(GameCaptureStamp){1,4,2876};
    assert(game_beam_submit(&b,&f,1U<<VISION_PORTAL_A,3113)==GAME_BEAM_RESTRICTED);
    assert(game_beam_display_snapshot(&b,6275,&shown));
    assert(shown.sequence==2 && shown.captured_ms==276);
    background();
    assert(!game_beam_render(&shown,&canvas));
    assert(!memcmp(reference,image,sizeof image));
    assert(!game_beam_display_snapshot(&b,6276,&shown)); /* Original stamp+6000, inclusive expiry. */
    /* Standalone's persistent presentation survives an arbitrarily long
     * recognition/capture outage. It neither dims the ray nor refreshes the
     * original scene stamps; the current observation stays invalid/empty. */
    assert(game_beam_retained_snapshot(&b,&shown));
    assert(!shown.valid && shown.display_stale && !shown.ray.success);
    assert(shown.sequence==2 && shown.captured_ms==276);
    assert(!game_beam_snapshot(&b)->valid && !game_beam_snapshot(&b)->object_count &&
           !game_beam_snapshot(&b)->ray.segment_count);
    assert(!game_beam_display_snapshot(&b,60276,&shown));
    assert(game_beam_retained_snapshot(&b,&shown));
    background();
    assert(!game_beam_render(&shown,&canvas));
    assert(!memcmp(reference,image,sizeof image));

    /* Confirmation replaces model and ray together; further pending again
     * retains that new complete result with identical brightness. */
    f.stamp=(GameCaptureStamp){1,5,6376};
    assert(game_beam_submit(&b,&f,0,6377)==GAME_BEAM_PENDING);
    f.stamp=(GameCaptureStamp){1,6,6642};
    assert(game_beam_submit(&b,&f,0,6643)==GAME_BEAM_OK);
    assert(game_beam_display_snapshot(&b,6643,&shown) && shown.valid);
    assert(shown.sequence==6 && shown.captured_ms==6642 && shown.objects[0].center.x==320);
    background();
    assert(!game_beam_render(&shown,&canvas));
    assert(memcmp(reference,image,sizeof image));
    memcpy(reference,image,sizeof image);
    d.geometry_center_x=340; d.center_x=340;
    f.stamp=(GameCaptureStamp){1,7,6908};
    assert(game_beam_submit(&b,&f,0,6909)==GAME_BEAM_PENDING);
    assert(game_beam_display_snapshot(&b,6909,&shown));
    assert(shown.display_stale && shown.sequence==6);
    assert(game_beam_retained_snapshot(&b,&shown));
    assert(shown.sequence==6 && shown.captured_ms==6642 && shown.objects[0].center.x==320);
    background();
    assert(!game_beam_render(&shown,&canvas));
    assert(!memcmp(reference,image,sizeof image));
    /* An explicit level/reset clears presentation even if capture generation
     * stays unchanged; stale geometry never crosses into a new emitter. */
    c.emitter_point.x=64;
    assert(game_beam_reconfigure(&b,&c,1,6910)==GAME_BEAM_OK);
    assert(!game_beam_retained_snapshot(&b,&shown));
    assert(game_beam_reset(&b,2,6911)==GAME_BEAM_OK);
    assert(!game_beam_display_snapshot(&b,6911,&shown));
    assert(!game_beam_retained_snapshot(&b,&shown));
}

int main(void)
{
    test_markers(); test_portal_radial_ring_fallback();
    test_pale_blocks(); test_dim_portal_pose();
    test_desaturated_portal_and_warm_marks(); test_exit(); test_complete_scene(); test_retention();
    test_constant_picture_after_long_gap();
    puts("restored markers / Portal B exit / constant-brightness bounded+persistent ray hold /1300ms gap checks passed");
    return 0;
}
