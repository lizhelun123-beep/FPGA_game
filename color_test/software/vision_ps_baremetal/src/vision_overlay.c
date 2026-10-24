#include "vision_overlay.h"
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* 5x7 column font, uppercase and digits; scaled 2x for 720p HDMI. */
static const unsigned char letters[26][5] = {
 {126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},
 {127,65,65,34,28},{127,73,73,73,65},{127,9,9,9,1},
 {62,65,73,73,122},{127,8,8,8,127},{0,65,127,65,0},
 {32,64,65,63,1},{127,8,20,34,65},{127,64,64,64,64},
 {127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
 {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},
 {70,73,73,73,49},{1,1,127,1,1},{63,64,64,64,63},
 {31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},
 {7,8,112,8,7},{97,81,73,69,67}
};
static const unsigned char digits[10][5] = {
 {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},
 {33,65,69,75,49},{24,20,18,127,16},{39,69,69,69,57},
 {60,74,73,73,48},{1,113,9,5,3},{54,73,73,73,54},
 {6,73,73,41,30}
};

int vision_canvas_valid(const VisionCanvas *c)
{
    size_t row, span;
    if (!c || !c->data || c->width < 1 || c->height < 1 ||
        c->width > 16384 || c->height > 16384) return 0;
    if ((size_t)c->width > SIZE_MAX/3) return 0;
    row = (size_t)c->width*3;
    if (c->stride < row || (c->height>1 && c->stride > (SIZE_MAX-row)/(size_t)(c->height-1))) return 0;
    span = (size_t)(c->height-1)*c->stride+row;
    return span <= c->capacity && span <= PTRDIFF_MAX;
}
static void pixel(const VisionCanvas *c, int x, int y, unsigned rgb)
{
    uint8_t *p;
    if (x < 0 || y < 0 || x >= c->width || y >= c->height) return;
    p = c->data+(size_t)y*c->stride+(size_t)x*3;
    p[0]=(uint8_t)rgb; p[1]=(uint8_t)(rgb>>8); p[2]=(uint8_t)(rgb>>16);
}
static double clamp(double v, double lo, double hi) { return fmax(lo,fmin(hi,v)); }
static int finite_point(VisionPoint p) { return isfinite(p.x) && isfinite(p.y); }
void vision_canvas_rect(const VisionCanvas *c, int x, int y, int w, int h, unsigned rgb)
{
    int xx, yy, left, right, top, bottom;
    if (!vision_canvas_valid(c) || w <= 0 || h <= 0) return;
    left=(int)clamp(x,0,c->width); right=(int)clamp((double)x+w,0,c->width);
    top=(int)clamp(y,0,c->height); bottom=(int)clamp((double)y+h,0,c->height);
    for (yy=top; yy<bottom; ++yy) for (xx=left; xx<right; ++xx) pixel(c,xx,yy,rgb);
}
static int outcode(const VisionCanvas *c,VisionPoint p)
{
    return (p.x<0?1:p.x>c->width-1?2:0)|(p.y<0?4:p.y>c->height-1?8:0);
}
void vision_canvas_line(const VisionCanvas *c, VisionPoint a, VisionPoint b, int radius, unsigned rgb)
{
    int x0,y0,x1,y1,ix,iy,sx,sy,error,attempt;
    if (!vision_canvas_valid(c) || !finite_point(a) || !finite_point(b) ||
        fabs(a.x)>1e140 || fabs(a.y)>1e140 || fabs(b.x)>1e140 || fabs(b.y)>1e140 ||
        radius<0 || radius>16) return;
    /* Set the clipped boundary coordinate exactly. A t-only clip loses both
     * endpoints to cancellation for e.g. [-FLT_MAX,+FLT_MAX] horizontal rays. */
    for (attempt=0;attempt<8;++attempt) {
        int ca=outcode(c,a),cb=outcode(c,b),code=ca?ca:cb;
        VisionPoint p;
        double t;
        if (!(ca|cb)) break;
        if (ca&cb) return;
        if (code&12) {
            p.y=(code&4)?0:c->height-1;
            t=(p.y-a.y)/(b.y-a.y); p.x=(1-t)*a.x+t*b.x;
        } else {
            p.x=(code&1)?0:c->width-1;
            t=(p.x-a.x)/(b.x-a.x); p.y=(1-t)*a.y+t*b.y;
        }
        if (!finite_point(p)) return;
        if (ca) a=p; else b=p;
    }
    if (outcode(c,a)|outcode(c,b)) return;
    x0=(int)lround(clamp(a.x,0,c->width-1)); y0=(int)lround(clamp(a.y,0,c->height-1));
    x1=(int)lround(clamp(b.x,0,c->width-1)); y1=(int)lround(clamp(b.y,0,c->height-1));
    ix=abs(x1-x0); iy=-abs(y1-y0); sx=x0<x1?1:-1; sy=y0<y1?1:-1; error=ix+iy;
    for (;;) {
        int xx,yy,doubled;
        for (yy=-radius; yy<=radius; ++yy) for (xx=-radius; xx<=radius; ++xx)
            if (xx*xx+yy*yy<=radius*radius) pixel(c,x0+xx,y0+yy,rgb);
        if (x0==x1 && y0==y1) break;
        doubled=2*error;
        if (doubled>=iy) { error+=iy; x0+=sx; }
        if (doubled<=ix) { error+=ix; y0+=sy; }
    }
}
void vision_canvas_polygon(const VisionCanvas *c, const VisionPoint *p, int count, unsigned fill, unsigned edge)
{
    double xmin,xmax,ymin,ymax;
    int i,x,y,left,right,top,bottom;
    if (!vision_canvas_valid(c) || !p || count<3 || count>10) return;
    xmin=xmax=p[0].x; ymin=ymax=p[0].y;
    for (i=0; i<count; ++i) {
        /* A finite coordinate bound keeps cross products below DBL_MAX. The
         * renderer maps float models in double, well inside this bound. */
        if (!finite_point(p[i]) || fabs(p[i].x)>1e140 || fabs(p[i].y)>1e140) return;
        xmin=fmin(xmin,p[i].x); xmax=fmax(xmax,p[i].x);
        ymin=fmin(ymin,p[i].y); ymax=fmax(ymax,p[i].y);
    }
    left=(int)clamp(floor(xmin),0,c->width); right=(int)clamp(ceil(xmax),-1,c->width-1);
    top=(int)clamp(floor(ymin),0,c->height); bottom=(int)clamp(ceil(ymax),-1,c->height-1);
    for (y=top; y<=bottom; ++y) for (x=left; x<=right; ++x) {
        int positive=0,negative=0;
        for (i=0; i<count; ++i) {
            VisionPoint a=p[i], b=p[(i+1)%count];
            double side=(b.x-a.x)*(y-a.y)-(b.y-a.y)*(x-a.x);
            if (side>0) positive=1;
            if (side<0) negative=1;
        }
        if (!(positive && negative)) pixel(c,x,y,fill);
    }
    for (i=0; i<count; ++i) vision_canvas_line(c,p[i],p[(i+1)%count],1,edge);
}
void vision_canvas_circle(const VisionCanvas *c, VisionPoint center, double radius, double thickness, unsigned rgb)
{
    int x,y,left,right,top,bottom;
    double inner;
    if (!vision_canvas_valid(c) || !finite_point(center) || !isfinite(radius) ||
        !isfinite(thickness) || radius<0 || thickness<0 || radius>1e140 ||
        fabs(center.x)>1e140 || fabs(center.y)>1e140) return;
    left=(int)clamp(floor(center.x-radius),0,c->width); right=(int)clamp(ceil(center.x+radius),-1,c->width-1);
    top=(int)clamp(floor(center.y-radius),0,c->height); bottom=(int)clamp(ceil(center.y+radius),-1,c->height-1);
    inner=fmax(0,radius-thickness);
    for (y=top; y<=bottom; ++y) for (x=left; x<=right; ++x) {
        double dx=x-center.x,dy=y-center.y,d=dx*dx+dy*dy;
        if (d<=radius*radius && (thickness==0 || d>=inner*inner)) pixel(c,x,y,rgb);
    }
}
void vision_canvas_text(const VisionCanvas *c, int x, int y, const char *s, int scale, unsigned rgb)
{
    double pen=x;
    if (!vision_canvas_valid(c) || !s || scale<1 || scale>8) return;
    for (; *s; ++s,pen+=6*scale) {
        const unsigned char *g=NULL;
        int col,row;
        if (pen>=c->width) break;
        if (pen+5*scale<0) continue;
        if (*s>='A' && *s<='Z') g=letters[*s-'A'];
        if (*s>='0' && *s<='9') g=digits[*s-'0'];
        for (col=0; col<5; ++col) for (row=0; row<7; ++row) {
            int on=g && (g[col]&(1U<<row));
            double yy=(double)y+row*scale;
            if ((*s=='_' && row==6) || (*s==':' && col==2 && (row==2 || row==5)) ||
                (*s=='-' && row==3) || (*s=='/' && col==4-row/2)) on=1;
            if (on && yy>=-scale && yy<c->height)
                vision_canvas_rect(c,(int)pen+col*scale,(int)yy,scale,scale,rgb);
        }
    }
}
unsigned vision_object_color(RayObjectType type)
{
    static const unsigned colors[RAY_OBJECT_TYPE_COUNT]={0xFAE170U,0x51B8F9U,0xFFA147U,0x5DE688U,0xFF70BBU,0xA59A91U};
    return (unsigned)type<RAY_OBJECT_TYPE_COUNT ? colors[type] : 0;
}
static VisionPoint model_point(const SceneObject *o, double along, double across, double s, double ox, double oy)
{
    VisionPoint p={ox+s*(o->center.x+along*o->axis.x-across*o->axis.y),
                   oy+s*(o->center.y+along*o->axis.y+across*o->axis.x)};
    return p;
}
void vision_canvas_object(const VisionCanvas *c, const SceneObject *o, double s, double ox, double oy)
{
    VisionPoint p[4],center,tip;
    unsigned rgb,fill;
    int count=4;
    if (!vision_canvas_valid(c) || !o || (unsigned)o->type>=RAY_OBJECT_TYPE_COUNT ||
        !isfinite(s) || s<=0 || !isfinite(ox) || !isfinite(oy) ||
        !isfinite(o->center.x) || !isfinite(o->center.y) || !isfinite(o->axis.x) ||
        !isfinite(o->axis.y) || !isfinite(o->length) || !isfinite(o->width) ||
        o->length<=0 || o->width<=0) return;
    rgb=vision_object_color(o->type);
    fill=((rgb&255U)/3U)|((((rgb>>8)&255U)/3U)<<8)|((((rgb>>16)&255U)/3U)<<16);
    center=model_point(o,0,0,s,ox,oy);
    tip=(VisionPoint){ox+s*o->source_tip.x,oy+s*o->source_tip.y};
    if (o->type==RAY_OBJECT_TARGET) {
        double r=s*fmin(o->length,o->width)*0.5;
        vision_canvas_circle(c,center,r,0,rgb);
        vision_canvas_circle(c,center,r*0.55,2,fill);
    } else {
        if (o->type==RAY_OBJECT_SOURCE) {
            if (!finite_point(tip)) return;
            count=3; p[0]=tip;
            p[1]=model_point(o,-o->length/3.0,o->width/2.0,s,ox,oy);
            p[2]=model_point(o,-o->length/3.0,-o->width/2.0,s,ox,oy);
        } else {
            p[0]=model_point(o,-o->length/2.0,-o->width/2.0,s,ox,oy);
            p[1]=model_point(o,o->length/2.0,-o->width/2.0,s,ox,oy);
            p[2]=model_point(o,o->length/2.0,o->width/2.0,s,ox,oy);
            p[3]=model_point(o,-o->length/2.0,o->width/2.0,s,ox,oy);
        }
        vision_canvas_polygon(c,p,count,fill,rgb);
        if (o->type==RAY_OBJECT_MIRROR)
            vision_canvas_line(c,model_point(o,-o->length/2.0,0,s,ox,oy),model_point(o,o->length/2.0,0,s,ox,oy),0,0xFAFBFAU);
        else if (o->type==RAY_OBJECT_PORTAL_A || o->type==RAY_OBJECT_PORTAL_B) {
            vision_canvas_circle(c,model_point(o,-o->length*0.35,0,s,ox,oy),5,0,rgb);
            vision_canvas_circle(c,model_point(o,o->length*0.35,0,s,ox,oy),7,2,rgb);
        } else if (o->type==RAY_OBJECT_SOURCE && o->direction_valid &&
                   isfinite(o->source_direction.x) && isfinite(o->source_direction.y)) {
            VisionPoint back={tip.x-o->source_direction.x*9,tip.y-o->source_direction.y*9};
            VisionPoint w1={back.x-o->source_direction.y*5,back.y+o->source_direction.x*5};
            VisionPoint w2={back.x+o->source_direction.y*5,back.y-o->source_direction.x*5};
            vision_canvas_line(c,center,tip,1,rgb);
            vision_canvas_line(c,tip,w1,1,rgb); vision_canvas_line(c,tip,w2,1,rgb);
        }
    }
}
static void draw_rays(const VisionCanvas *c, const RaySegment *segments, int count)
{
    int i;
    for (i=0; i<count; ++i) {
        VisionPoint a={segments[i].start.x,segments[i].start.y},b={segments[i].end.x,segments[i].end.y};
        vision_canvas_line(c,a,b,3,0); vision_canvas_line(c,a,b,2,0xFFFF00U);
    }
}
static void object_flags(unsigned mask, char flags[RAY_OBJECT_TYPE_COUNT+2])
{
    static const char names[RAY_OBJECT_TYPE_COUNT]={'M','A','B','T','S','W'};
    unsigned i,kept=0;
    for (i=0;i<RAY_OBJECT_TYPE_COUNT;++i) if (mask&(1U<<i)) flags[kept++]=names[i];
    if (!kept) flags[kept++]='N';
    flags[kept]='\0';
}
/* Legacy APIs cannot know caller capacity. New callers use VisionCanvas. */
void vision_overlay(uint8_t *f,unsigned w,unsigned h,unsigned stride,const RaySegment *segments,int count,
                    unsigned detected_mask,unsigned hit_mask,unsigned ms)
{
    VisionCanvas c;
    char label[80],detected[RAY_OBJECT_TYPE_COUNT+2],hit[RAY_OBJECT_TYPE_COUNT+2];
    if (w>16384 || h>16384 || !h || stride>SIZE_MAX/h || count<0 ||
        count>RAY_GAME_MAX_SEGMENTS || (count && !segments)) return;
    c=(VisionCanvas){f,(int)w,(int)h,stride,(size_t)stride*h};
    if (!vision_canvas_valid(&c)) return;
    draw_rays(&c,segments,count); object_flags(detected_mask,detected); object_flags(hit_mask,hit);
    (void)snprintf(label,sizeof label,"%s RAY %d DET %s HIT %s %u MS",VISION_FIRMWARE_UI_ID,count,detected,hit,ms);
    vision_canvas_rect(&c,8,8,(int)strlen(label)*12,16,0);
    vision_canvas_text(&c,8,8,label,2,0x00FF00U);
}
#if VISION_FIXED_SCENE_DEMO
static void legacy_object_label(const VisionCanvas *c,const SceneObject *o)
{
    static const char *const names[RAY_OBJECT_TYPE_COUNT]={"MIRROR","PORTAL_A","PORTAL_B","TARGET","SOURCE","WALL"};
    double left=1e140,top=1e140;
    int i;
    if ((unsigned)o->type>=RAY_OBJECT_TYPE_COUNT) return;
    if (o->type==RAY_OBJECT_TARGET) {
        double r=fmin(o->length,o->width)*0.5;
        left=o->center.x-r; top=o->center.y-r;
    } else for (i=0;i<4;++i) {
        VisionPoint p=model_point(o,(i&1)?o->length/2.0:-o->length/2.0,
                                  (i&2)?o->width/2.0:-o->width/2.0,1,0,0);
        if (o->type==RAY_OBJECT_SOURCE)
            p=i==0?(VisionPoint){o->source_tip.x,o->source_tip.y}:
                    model_point(o,-o->length/3.0,(i&1)?o->width/2.0:-o->width/2.0,1,0,0);
        left=fmin(left,p.x); top=fmin(top,p.y);
    }
    if (!isfinite(left) || !isfinite(top) || left<-100 || left>=c->width || top<-16 || top>c->height+22) return;
    vision_canvas_rect(c,(int)lround(left),(int)lround(top)-22,(int)strlen(names[o->type])*12,16,0);
    vision_canvas_text(c,(int)lround(left),(int)lround(top)-22,names[o->type],2,0x00FF00U);
}
void vision_overlay_scene(uint8_t *f,unsigned w,unsigned h,unsigned stride,const SceneObject *objects,int count,const RayGameResult *ray)
{
    VisionCanvas c;
    unsigned x,y,hit_mask=0;
    int i;
    char label[80],hits[RAY_OBJECT_TYPE_COUNT+2];
    if (w!=VISION_FIXED_SCENE_WIDTH || h!=VISION_FIXED_SCENE_HEIGHT || stride>SIZE_MAX/h ||
        !objects || count<0 || count>VISION_MAX_DETECTIONS || !ray || ray->segment_count<0 ||
        ray->segment_count>RAY_GAME_MAX_SEGMENTS || ray->hit_count<0 || ray->hit_count>RAY_GAME_MAX_INTERACTIONS) return;
    c=(VisionCanvas){f,(int)w,(int)h,stride,(size_t)stride*h};
    if (!vision_canvas_valid(&c)) return;
    for (y=0;y<h;++y) for (x=0;x<w;++x) pixel(&c,(int)x,(int)y,x%64U==0 || y%64U==0?0x232930U:0x1B2128U);
    for (i=0;i<count;++i) { vision_canvas_object(&c,&objects[i],1,0,0); legacy_object_label(&c,&objects[i]); }
    draw_rays(&c,ray->segments,ray->segment_count);
    vision_canvas_line(&c,(VisionPoint){0,0},(VisionPoint){w-1,0},0,0x576A64U);
    vision_canvas_line(&c,(VisionPoint){w-1,0},(VisionPoint){w-1,h-1},0,0x576A64U);
    vision_canvas_line(&c,(VisionPoint){w-1,h-1},(VisionPoint){0,h-1},0,0x576A64U);
    vision_canvas_line(&c,(VisionPoint){0,h-1},(VisionPoint){0,0},0,0x576A64U);
    for (i=0;i<ray->hit_count;++i) if ((unsigned)ray->hit_types[i]<RAY_OBJECT_TYPE_COUNT) hit_mask|=1U<<(unsigned)ray->hit_types[i];
    object_flags(hit_mask,hits);
    vision_canvas_rect(&c,8,8,(int)strlen("FIXED SCENE DEMO  1280X720 PIXELS  CAMERA BYPASSED")*12,16,0);
    vision_canvas_text(&c,8,8,"FIXED SCENE DEMO  1280X720 PIXELS  CAMERA BYPASSED",2,0x00FF00U);
    (void)snprintf(label,sizeof label,"RAY %d HIT %s TARGET %s",ray->segment_count,hits,ray->success?"REACHED":"PENDING");
    vision_canvas_rect(&c,8,30,(int)strlen(label)*12,16,0);
    vision_canvas_text(&c,8,30,label,2,0x00FF00U);
}
#endif
