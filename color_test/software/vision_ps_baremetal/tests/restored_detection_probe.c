/* Offline image probe of the canonical detector. Input must be packed BGR. */
#include "vision_ps.h"
#include "ray_game.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv)
{
    unsigned char *frame;
    VisionDetection d[VISION_MAX_DETECTIONS];
    VisionDetectionDiagnostics s;
    FILE *f;
    int n,i;
    if(argc!=2) return 2;
    frame=(unsigned char*)malloc(1280U*720U*3U);
    f=fopen(argv[1],"rb");
    if(!f || !frame) return 2;
    if(fread(frame,1,1280U*720U*3U,f)!=1280U*720U*3U) return 2;
    fclose(f);
    vision_set_real_scene_profile(VISION_PROFILE_RESTORED);
    n=vision_detect_bgr888(frame,1280,720,3840,d,VISION_MAX_DETECTIONS);
    vision_get_detection_diagnostics(&s);
    printf("count=%d masks=%u,%u,%u,%u,%u,%u wall=%u/%u/%u\n",n,
        s.mask_pixels[0],s.mask_pixels[1],s.mask_pixels[2],s.mask_pixels[3],
        s.mask_pixels[5],s.mask_pixels[6],s.wall_marker_components,
        s.wall_marker_pairs_tested,s.wall_marker_accepted);
    for(i=0;i<n;++i) printf("%s center=%d,%d angle=%d bbox=%d,%d,%d,%d axis=%.4f,%.4f size=%.2f,%.2f\n",
        vision_type_name(d[i].type),d[i].center_x,d[i].center_y,d[i].angle_deg,
        d[i].bbox_x,d[i].bbox_y,d[i].bbox_w,d[i].bbox_h,
        d[i].axis_x,d[i].axis_y,d[i].major_length,d[i].minor_width);
    for(i=0;i<6;++i) printf("%s cand=%u geom=%u mark=%u accept=%u\n",vision_type_name((VisionType)i),
        s.component_candidates[i],s.geometry_pass[i],s.marker_pass[i],s.accepted[i]);
    if(n>=0) {
        SceneObject objects[VISION_MAX_DETECTIONS];
        RayGameResult ray;
        int count=ray_game_scene_from_detections(d,n,objects,VISION_MAX_DETECTIONS);
        if(count<0 || ray_game_trace_from_emitter_policy(objects,count,1280,720,
            (RayPoint){32,500},(RayPoint){1,0},1,&ray)) return 4;
        printf("OFFLINE_RAW_SCENE_RAY (no timed confirmation): segments=%d interactions=%d termination=%d\n",
            ray.segment_count,ray.interaction_count,(int)ray.termination);
        for(i=0;i<ray.segment_count;++i) printf("segment%d %.2f,%.2f -> %.2f,%.2f\n",i,
            ray.segments[i].start.x,ray.segments[i].start.y,ray.segments[i].end.x,ray.segments[i].end.y);
    }
    free(frame);
    return n<0?3:0;
}
