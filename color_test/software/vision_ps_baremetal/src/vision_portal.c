#include "vision_portal.h"
#include "apriltag.h"
#include "tag36h11.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#ifdef GAME_BEAM_STANDALONE
#include "xtime_l.h"
#endif

static apriltag_detector_t *detector;
static apriltag_family_t *family;
static uint8_t gray[1280U*720U];
static VisionPortalTag observations[6];
static int observed_count, duplicate_mask, configured;
static VisionPortalTemplate models[2];
static VisionPortalTiming last_timing;

static uint64_t portal_now_us(void)
{
#ifdef GAME_BEAM_STANDALONE
    XTime ticks;
    XTime_GetTime(&ticks);
    return ticks/COUNTS_PER_SECOND*1000000ULL +
        ticks%COUNTS_PER_SECOND*1000000ULL/COUNTS_PER_SECOND;
#else
    return 0;
#endif
}

void vision_portal_last_timing(VisionPortalTiming *timing)
{
    if (timing) *timing=last_timing;
}

static void detector_timing(void)
{
#ifdef GAME_BEAM_STANDALONE
    int i;
    int64_t after_blur=-1, after_quad=-1, after_threshold=-1;
    int64_t after_components=-1, after_clusters=-1;
    /* Read the upstream profiler it already maintains; no detector settings,
     * image scaling, tag family or corner/refinement gates are changed. */
    for (i=0; i<zarray_size(detector->tp->stamps); ++i) {
        struct timeprofile_entry stamp;
        zarray_get(detector->tp->stamps,i,&stamp);
        if (!strcmp(stamp.name,"blur/sharp")) after_blur=stamp.utime;
        else if (!strcmp(stamp.name,"threshold")) {
            after_threshold=stamp.utime;
            if (after_blur>=0 && after_threshold>=after_blur) {
                last_timing.threshold_us=(uint64_t)(after_threshold-after_blur);
                last_timing.quad_stage_mask|=1U;
            }
        } else if (!strcmp(stamp.name,"unionfind")) {
            after_components=stamp.utime;
            if (after_threshold>=0 && after_components>=after_threshold) {
                last_timing.components_us=(uint64_t)(after_components-after_threshold);
                last_timing.quad_stage_mask|=2U;
            }
        } else if (!strcmp(stamp.name,"make clusters")) {
            after_clusters=stamp.utime;
            if (after_components>=0 && after_clusters>=after_components) {
                last_timing.clusters_us=(uint64_t)(after_clusters-after_components);
                last_timing.quad_stage_mask|=4U;
            }
        } else if (!strcmp(stamp.name,"fit quads to clusters")) {
            if (after_clusters>=0 && stamp.utime>=after_clusters) {
                last_timing.fit_quads_us=(uint64_t)(stamp.utime-after_clusters);
                last_timing.quad_stage_mask|=8U;
            }
        }
        else if (!strcmp(stamp.name,"quads")) {
            after_quad=stamp.utime;
            if (after_blur>=0 && after_quad>=after_blur)
                last_timing.quad_us=(uint64_t)(after_quad-after_blur);
        } else if (!strcmp(stamp.name,"decode+refinement") &&
                   after_quad>=0 && stamp.utime>=after_quad)
            last_timing.decode_us=(uint64_t)(stamp.utime-after_quad);
    }
#endif
}

static int slot(int id)
{
    if (id >= 10 && id <= 12) return id-10;
    if (id >= 20 && id <= 22) return id-17;
    return -1;
}

int vision_portal_configure(const VisionPortalTemplate templates[2])
{
    int p, t, c;
    configured = 0;
    if (!templates) return -1;
    for (p=0; p<2; ++p) {
        const VisionPortalTemplate *m=&templates[p];
        float norm=hypotf(m->axis[0],m->axis[1]);
        if (!isfinite(norm) || fabsf(norm-1)>0.001f ||
            !isfinite(m->length) || !isfinite(m->width) ||
            m->length<=m->width || m->width<=1 ||
            !isfinite(m->reference_scale) || m->reference_scale<=0 ||
            (m->handedness!=1 && m->handedness!=-1) ||
            !isfinite(m->center[0]) || !isfinite(m->center[1])) return -1;
        for (t=0; t<3; ++t) for (c=0; c<4; ++c)
            if (!isfinite(m->corners[t][c][0]) ||
                !isfinite(m->corners[t][c][1])) return -1;
    }
    memcpy(models,templates,sizeof(models));
    configured=1;
    return 0;
}

int vision_portal_initialize(void)
{
    if (!detector) {
        family=tag36h11_create();
        detector=apriltag_detector_create();
        if (!family || !detector) { vision_portal_shutdown(); return -1; }
        apriltag_detector_add_family_bits(detector,family,1);
        /* Small, blurred camera tags need original pixels. This does not
         * resize camera data, weaken hamming checks, or upsample for display. */
        detector->quad_decimate=1.0f;
        detector->nthreads=1;
        detector->refine_edges=1;
    }
    return 0;
}

int vision_portal_scan_bgr888(const uint8_t *frame, uint32_t width,
    uint32_t height, uint32_t stride)
{
    uint32_t x,y;
    int i, seen=0;
    uint64_t began, gray_done, detector_done;
    zarray_t *found;
    image_u8_t image={.width=(int)width,.height=(int)height,
                     .stride=(int)width,.buf=gray};
    observed_count=duplicate_mask=0;
    if (!frame || !width || !height || width>1280 || height>720 || stride<width*3U ||
        vision_portal_initialize()) return -1;
    {
        uint64_t sequence=last_timing.scan_sequence+1U;
        memset(&last_timing,0,sizeof last_timing);
        last_timing.scan_sequence=sequence;
#ifdef GAME_BEAM_STANDALONE
        last_timing.clock_available=1;
#endif
    }
    began=portal_now_us();
    for (y=0; y<height; ++y) for (x=0; x<width; ++x) {
        const uint8_t *bgr=frame+(size_t)y*stride+x*3U;
        gray[y*width+x]=(uint8_t)((29U*bgr[0]+150U*bgr[1]+77U*bgr[2])>>8);
    }
    gray_done=portal_now_us();
    last_timing.grayscale_us=gray_done-began;
    found=apriltag_detector_detect(detector,&image);
    detector_done=portal_now_us();
    last_timing.detector_us=detector_done-gray_done;
    last_timing.quads=detector->nquads;
    detector_timing();
    if (!found) return -1;
    last_timing.raw_tags=(uint32_t)zarray_size(found);
    for (i=0; i<zarray_size(found); ++i) {
        apriltag_detection_t *d;
        VisionPortalTag *o;
        int s,c;
        zarray_get(found,i,&d);
        s=slot(d->id);
        if (s<0 || d->hamming>1 || !isfinite(d->decision_margin) ||
            d->decision_margin<10) continue;
        if (seen&(1<<s)) { duplicate_mask|=1<<(s/3); continue; }
        seen|=1<<s;
        if (observed_count>=6) continue;
        o=&observations[observed_count++];
        o->id=d->id; o->hamming=d->hamming; o->margin=d->decision_margin;
        for (c=0; c<4; ++c) {
            o->corners[c][0]=(float)d->p[c][0];
            o->corners[c][1]=(float)d->p[c][1];
        }
    }
    apriltag_detections_destroy(found);
    last_timing.accepted_tags=(uint32_t)observed_count;
    return observed_count;
}

int vision_portal_last_tags(VisionPortalTag *tags, int capacity)
{
    if (!tags || capacity<observed_count) return -1;
    memcpy(tags,observations,(size_t)observed_count*sizeof(*tags));
    return observed_count;
}

/* Solve the measured rigid object-to-image projection using every visible,
 * ID-matched corner. The local affine approximation is a camera-pixel preview,
 * not a completed common physical-plane or lens calibration.
 * The rigid-shape/residual gates reject inconsistent tags instead of averaging
 * their centers. At least two spatially separated tags are required. */
static int solve(double a[3][3],double b[3],double out[3])
{
    double m[3][4];
    int i,j,k;
    for(i=0;i<3;++i) { for(j=0;j<3;++j)m[i][j]=a[i][j];m[i][3]=b[i]; }
    for(i=0;i<3;++i) {
        int best=i;
        for(j=i+1;j<3;++j) if(fabs(m[j][i])>fabs(m[best][i]))best=j;
        if(fabs(m[best][i])<1e-8)return 0;
        for(k=i;k<4;++k) { double v=m[i][k];m[i][k]=m[best][k];m[best][k]=v; }
        for(j=i+1;j<3;++j) {
            double factor=m[j][i]/m[i][i];
            for(k=i;k<4;++k)m[j][k]-=factor*m[i][k];
        }
    }
    for(i=2;i>=0;--i) { double v=m[i][3];for(j=i+1;j<3;++j)v-=m[i][j]*out[j];out[i]=v/m[i][i]; }
    return 1;
}

static int fit(int portal, VisionDetection *out, uint32_t w,uint32_t h)
{
    const VisionPortalTemplate *m=&models[portal];
    double normal[3][3]={{0}},bx[3]={0},by[3]={0},ax[3],ay[3];
    double error=0, maxerror=0, xnorm,ynorm,orth, ratio;
    float ux=m->axis[0],uy=m->axis[1],cx,cy,vx,vy,wx,wy,len,width;
    int i,j,k,c,n=0,tags=0;
    if(duplicate_mask&(1<<portal))return 0;
    for(i=0;i<observed_count;++i) {
        int s=slot(observations[i].id);
        if(s/3!=portal)continue;
        ++tags;
        for(c=0;c<4;++c) {
            double v[3]={m->corners[s%3][c][0]-m->center[0],
                         m->corners[s%3][c][1]-m->center[1],1};
            for(j=0;j<3;++j) {
                for(k=0;k<3;++k)normal[j][k]+=v[j]*v[k];
                bx[j]+=v[j]*observations[i].corners[c][0];
                by[j]+=v[j]*observations[i].corners[c][1];
            }
            ++n;
        }
    }
    if(tags<2 || !solve(normal,bx,ax) || !solve(normal,by,ay))return 0;
    for(i=0;i<observed_count;++i) {
        int s=slot(observations[i].id);
        if(s/3!=portal)continue;
        for(c=0;c<4;++c) {
            double u=m->corners[s%3][c][0]-m->center[0];
            double v=m->corners[s%3][c][1]-m->center[1];
            double dx=ax[0]*u+ax[1]*v+ax[2]-observations[i].corners[c][0];
            double dy=ay[0]*u+ay[1]*v+ay[2]-observations[i].corners[c][1];
            double e=dx*dx+dy*dy;
            error+=e; if(e>maxerror)maxerror=e;
        }
    }
    vx=(float)(ax[0]*ux+ax[1]*uy); vy=(float)(ay[0]*ux+ay[1]*uy);
    wx=(float)(-ax[0]*uy+ax[1]*ux); wy=(float)(-ay[0]*uy+ay[1]*ux);
    xnorm=hypot(vx,vy); ynorm=hypot(wx,wy);
    orth=fabs(vx*wx+vy*wy)/(xnorm*ynorm);
    ratio=xnorm/ynorm;
    if(!isfinite(error) || sqrt(error/n)>2.0 || maxerror>16 ||
       xnorm<m->reference_scale*0.65 || xnorm>m->reference_scale*1.40 ||
       ynorm<m->reference_scale*0.65 || ynorm>m->reference_scale*1.40 ||
       orth>0.16 || ratio<0.80 || ratio>1.25 ||
       (ax[0]*ay[1]-ax[1]*ay[0])*m->handedness<=0)return 0;
    cx=(float)ax[2];cy=(float)ay[2];
    len=m->length*(float)xnorm;
    width=m->width*fabsf((vx*wy-vy*wx)/(float)xnorm);
    if(cx<0 || cy<0 || cx>=w || cy>=h)return 0;
    memset(out,0,sizeof(*out));
    out->type=portal?VISION_PORTAL_B:VISION_PORTAL_A;
    out->geometry_center_x=cx;out->geometry_center_y=cy;
    out->center_x=(int)lroundf(cx);out->center_y=(int)lroundf(cy);
    out->axis_x=vx/(float)xnorm;out->axis_y=vy/(float)xnorm;
    out->major_length=len;out->minor_width=width;
    out->angle_deg=(int)lroundf(atan2f(out->axis_y,out->axis_x)*180/3.14159265358979323846);
    out->bbox_w=(int)ceilf(fabsf(out->axis_x)*len+fabsf(out->axis_y)*width);
    out->bbox_h=(int)ceilf(fabsf(out->axis_y)*len+fabsf(out->axis_x)*width);
    out->bbox_x=(int)floorf(cx-out->bbox_w/2.0f);out->bbox_y=(int)floorf(cy-out->bbox_h/2.0f);
    out->confidence_percent=tags==3?100:80;
    out->geometry_is_effective=1;
    return 1;
}

int vision_portal_detect_bgr888(const uint8_t *frame,uint32_t width,
    uint32_t height,uint32_t stride,VisionDetection *output,int capacity)
{
    int count=0,p;
    uint64_t began;
    if(!output || capacity<1 || vision_portal_scan_bgr888(frame,width,height,stride)<0)return -1;
    if(!configured)return -1;
    began=portal_now_us();
    for(p=0;p<2 && count<capacity;++p)if(fit(p,output+count,width,height))++count;
    last_timing.fit_us=portal_now_us()-began;
    return count;
}

void vision_portal_shutdown(void)
{
    if(detector)apriltag_detector_destroy(detector);
    if(family)tag36h11_destroy(family);
    detector=NULL;family=NULL;observed_count=duplicate_mask=0;
}
