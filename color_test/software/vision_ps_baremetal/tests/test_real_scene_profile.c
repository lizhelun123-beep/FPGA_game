#include "vision_ps.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#define W 1280U
#define H 720U
static uint8_t frame[W*H*3U];

static int no_portals(const uint8_t *pixels, uint32_t w, uint32_t h,
                      uint32_t stride, VisionDetection *output, int capacity)
{
    (void)pixels; (void)w; (void)h; (void)stride; (void)output; (void)capacity;
    return 0;
}

static void rectangle(int x, int y, int w, int h, int b, int g, int r)
{
    int yy;
    for (yy=y; yy<y+h; ++yy) {
        int xx;
        for (xx=x; xx<x+w; ++xx) {
            uint8_t *p = frame+((uint32_t)yy*W+(uint32_t)xx)*3U;
            p[0]=(uint8_t)b; p[1]=(uint8_t)g; p[2]=(uint8_t)r;
        }
    }
}

static void disk(int x, int y, int radius, int b, int g, int r)
{
    int yy;
    for (yy=y-radius; yy<=y+radius; ++yy) {
        int xx;
        for (xx=x-radius; xx<=x+radius; ++xx)
            if ((xx-x)*(xx-x)+(yy-y)*(yy-y)<=radius*radius)
                rectangle(xx,yy,1,1,b,g,r);
    }
}

static void ellipse(int x, int y, int rx, int ry, int b, int g, int r)
{
    int yy;
    for (yy=y-ry; yy<=y+ry; ++yy) {
        int xx;
        for (xx=x-rx; xx<=x+rx; ++xx)
            if ((xx-x)*(xx-x)*ry*ry+(yy-y)*(yy-y)*rx*rx<=rx*rx*ry*ry)
                rectangle(xx,yy,1,1,b,g,r);
    }
}

static void background(void)
{
    rectangle(0,0,W,H,48,56,65);
}

int main(int argc, char **argv)
{
    VisionDetection d[16];
    /* Synthetic fixture measurements only. Runtime values come from the
     * unique game config, not defaults hidden inside the C detector. */
    const VisionRealSceneGeometry measured = {
        46.0f/54.0f, 80.0f/54.0f, 25.0f/54.0f, 80.0f/61.0f, 1.0f
    };
    VisionRealSceneGeometry invalid;
    int count;
    assert(vision_set_real_scene_profile(1)==-3);
    vision_set_portal_detector(no_portals);
    assert(vision_set_real_scene_profile(1)==-4);
    assert(vision_set_real_scene_geometry(NULL)==-1);
    invalid = measured;
    invalid.mirror_reflective_to_marker_span = NAN;
    assert(vision_set_real_scene_geometry(&invalid)==-1);
    invalid = measured;
    invalid.wall_body_to_marker_span = 0.0f;
    assert(vision_set_real_scene_geometry(&invalid)==-1);
    assert(vision_set_real_scene_geometry(&measured)==0);
    assert(vision_set_real_scene_profile(1)==0);
    if (argc==2 && strcmp(argv[1],"--pipe")==0) {
#ifdef _WIN32
        _setmode(0, _O_BINARY);
#endif
        while (fread(frame,1,sizeof(frame),stdin)==sizeof(frame)) {
            int i;
            count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
            printf("%d",count);
            for (i=0;i<count;++i)
                printf(" %s,%d,%d,%d,%.2f,%.2f",vision_type_name(d[i].type),
                    d[i].center_x,d[i].center_y,d[i].angle_deg,
                    d[i].major_length,d[i].minor_width);
            printf("\n"); fflush(stdout);
        }
        return 0;
    }
    background();
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==0);
    /* A beige tagged Portal body cannot become a yellow Mirror. */
    rectangle(500,300,240,80,90,120,140);
    rectangle(520,320,32,32,200,205,200);
    rectangle(610,304,32,32,200,205,200);
    rectangle(700,320,32,32,200,205,200);
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==0);
    background();
    rectangle(500,300,240,75,90,120,140);
    rectangle(551,328,138,20,180,190,180);
    disk(539,338,12,5,15,20); disk(701,338,12,5,15,20);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_MIRROR);
    assert(d[0].geometry_is_effective==1);
    assert(abs(d[0].center_x-620)<=3 && abs(d[0].center_y-338)<=3);
    assert(fabsf(d[0].major_length-138.0f)<8.0f);
    assert(fabsf(d[0].minor_width-75.0f)<8.0f);
    assert(abs(d[0].bbox_w-240)<10);
    /* Without one endpoint the bright strip does not authorize a Mirror. */
    rectangle(680,318,40,40,90,120,140);
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==0);
    background();
    rectangle(500,300,240,75,5,15,20);
    rectangle(515,300,27,75,180,190,180);
    rectangle(698,300,27,75,180,190,180);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_WALL);
    assert(d[0].geometry_is_effective==1);
    assert(abs(d[0].center_x-620)<=3 && abs(d[0].center_y-338)<=3);
    assert(fabsf(d[0].major_length-240.0f)<8.0f);
    assert(fabsf(d[0].minor_width-75.0f)<8.0f);
#ifdef GAME_BEAM_STANDALONE
    /* A complete object in the lower camera row must not be removed by the
     * legacy six-class UI playfield cutoff at y<590. */
    background();
    rectangle(500,610,240,75,5,15,20);
    rectangle(515,610,27,75,180,190,180);
    rectangle(698,610,27,75,180,190,180);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_WALL);
    assert(d[0].center_y >= 640 && d[0].center_y <= 656);
    /* The same dark body remains a WALL candidate even when the white end
     * bars are absent or washed out in the bottom-row view. */
    background();
    rectangle(500,610,240,75,5,15,20);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_WALL);
#endif
    background();
    disk(640,360,40,33,59,44);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_TARGET);
    assert(d[0].geometry_is_effective==1);
    assert(d[0].major_length==d[0].minor_width);
    assert(vision_detect_objects_bgr888(frame,W,H,W*3U,d,16)==0);
    /* Missing a quarter of the disk cannot publish a new circular boundary. */
    rectangle(590,360,50,50,180,190,180);
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==0);
    background();
    /* Warm image corners reduce the disk's G-R contrast to two levels. */
    disk(100,100,35,24,56,54);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_TARGET);
    background();
    ellipse(640,360,46,44,33,72,44);
    count=vision_detect_bgr888(frame,W,H,W*3U,d,16);
    assert(count==1 && d[0].type==VISION_TARGET);
    assert(d[0].bbox_w!=d[0].bbox_h);
    assert(d[0].major_length==d[0].minor_width);
    assert(d[0].major_length==(float)(d[0].bbox_w<d[0].bbox_h ?
                                     d[0].bbox_w : d[0].bbox_h));
    assert(abs(d[0].center_x-640)<=2 && abs(d[0].center_y-360)<=2);
    /* An elongated green object is not a circular target. */
    background(); rectangle(500,300,200,30,33,59,44);
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==0);
    vision_set_portal_detector(NULL);
    assert(vision_detect_bgr888(frame,W,H,W*3U,d,16)==-3);
    assert(vision_set_real_scene_profile(0)==0);
    puts("real-scene profile checks passed");
    return 0;
}
