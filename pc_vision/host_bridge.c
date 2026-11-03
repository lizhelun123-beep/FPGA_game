/* Small host ABI. Production recognition and physics remain in the PS sources. */
#include "ray_game.h"
#include "scene_protocol.h"
#include <math.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef VISION_WITH_APRILTAG
#include "vision_portal.h"
#include "game_session.h"
#include "game_scene_adapter.h"
#include "vision_stabilizer.h"
extern const GameConfig game_default_config;
static GameSession real_session;
static VisionTimedStabilizer real_stabilizer;
static VisionDetection pending_detections[VISION_MAX_DETECTIONS];
static GameDetectionFrame pending_frame;
static int real_initialized, pending_available;
static uint64_t real_selected_ms, real_detect_sequence, real_detect_capture;
static int real_have_detection;

static void real_snapshot(int status)
{
    const GameSnapshot *v=game_session_snapshot(&real_session);
    int i;
    printf("{\"status\":%d,\"state\":%d,\"level\":%u,\"generation\":%llu,"
           "\"sequence\":%llu,\"captured_ms\":%llu,\"valid\":%d,\"ready\":%d,"
           "\"elapsed_ms\":%llu,\"remaining_ms\":%llu,\"stars\":%u,\"objects\":[",
           status,v->state,v->level_id,(unsigned long long)v->generation,
           (unsigned long long)v->scene_sequence,(unsigned long long)v->captured_ms,
           v->scene_valid,v->ready,(unsigned long long)v->elapsed_ms,
           (unsigned long long)v->remaining_ms,v->stars);
    for(i=0;i<v->object_count;++i) {
        const SceneObject *o=&v->objects[i];
        printf("%s[%d,%.7g,%.7g,%.7g,%.7g,%.7g,%.7g,%.7g,%.7g,%.7g,%.7g,%d]",
            i?",":"",o->type,o->center.x,o->center.y,o->axis.x,o->axis.y,
            o->length,o->width,o->source_tip.x,o->source_tip.y,
            o->source_direction.x,o->source_direction.y,o->direction_valid);
    }
    printf("],\"segments\":[");
    for(i=0;i<v->ray.segment_count;++i) {
        const RaySegment *s=&v->ray.segments[i];
        printf("%s[%.7g,%.7g,%.7g,%.7g]",i?",":"",s->start.x,s->start.y,s->end.x,s->end.y);
    }
    printf("],\"success\":%d,\"termination\":%d}\n",v->ray.success,v->ray.termination);
}
#endif
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
static int game_detect(const uint8_t *frame, uint32_t width, uint32_t height,
    uint32_t stride, uint32_t sequence, char *line, unsigned int capacity)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count = vision_detect_bgr888(frame, width, height, stride,
                                   detections, VISION_MAX_DETECTIONS);
    return scene_protocol_encode(line, capacity, detections, count, count >= 0,
                                 sequence, sequence, 0, (uint16_t)width, (uint16_t)height);
}
/* Twelve floats/object; explicit arrays avoid exposing compiler struct layout.
 * The same fixed model geometry used by the renderer is passed here.
 * Canonical epsilon=1, source offset=3 become 1/scale and 3/scale plane units.
 * Adding 1 to the frame extent accounts for C's inclusive pixel boundary. */
static int game_trace(const float *rows, int count, float width, float height,
    float scale, float *segments, int *info)
{
    SceneObject objects[VISION_MAX_DETECTIONS];
    RayGameResult result;
    int n, k, status;
    if (!rows || !segments || !info || count < 0 || count > VISION_MAX_DETECTIONS ||
        !isfinite(scale) || scale < 1 || !isfinite(width) || !isfinite(height) ||
        width <= 0 || height <= 0) return -1;
    memset(objects, 0, sizeof(objects));
    for (n = 0; n < count; ++n) {
        const float *r = rows + n*12;
        SceneObject *o = objects + n;
        for (k = 0; k < 12; ++k) if (!isfinite(r[k])) return -1;
        if (r[0] < 0 || r[0] >= RAY_OBJECT_TYPE_COUNT || r[5] <= 0 || r[6] <= 0)
            return -1;
        o->type = (RayObjectType)(int)r[0];
        o->center = (RayPoint){r[1]*scale, r[2]*scale};
        o->axis = (RayPoint){r[3], r[4]};
        o->length = r[5]*scale; o->width = r[6]*scale;
        o->source_tip = (RayPoint){r[7]*scale, r[8]*scale};
        o->source_direction = (RayPoint){r[9], r[10]};
        o->direction_valid = (int)r[11];
    }
    status = ray_game_trace(objects, count, width*scale+1, height*scale+1, &result);
    info[0] = result.segment_count; info[1] = result.interaction_count;
    info[2] = result.success; info[3] = result.termination; info[4] = result.hit_count;
    for (n = 0; n < result.hit_count; ++n) info[5+n] = result.hit_types[n];
    for (n = 0; n < result.segment_count; ++n) {
        segments[n*4] = result.segments[n].start.x/scale;
        segments[n*4+1] = result.segments[n].start.y/scale;
        segments[n*4+2] = result.segments[n].end.x/scale;
        segments[n*4+3] = result.segments[n].end.y/scale;
    }
    return status;
}

int main(void)
{
    int command;
    uint8_t *frame = (uint8_t *)malloc(1280U*720U*3U);
    if (!frame) return 2;
#ifdef _WIN32
    _setmode(0, _O_BINARY);
    _setmode(1, _O_BINARY);
#endif
    fputs("SCENE_HOST_V1\n", stdout);
    fflush(stdout);
    while ((command = fgetc(stdin)) != EOF && command != 'Q') {
        if (command == 'D') {
            uint32_t sequence;
            char line[SCENE_PROTOCOL_MAX_LINE+1];
            int length;
            if (fread(&sequence, sizeof(sequence), 1, stdin) != 1 ||
                fread(frame, 1, 1280U*720U*3U, stdin) != 1280U*720U*3U) break;
            length = game_detect(frame, 1280, 720, 1280*3, sequence, line, sizeof(line));
            if (length < 0) break;
            fwrite(line, 1, (size_t)length, stdout);
#ifdef VISION_WITH_APRILTAG
        } else if (command == 'L') {
            uint32_t level;
            uint64_t now;
            int status;
            if(fread(&level,sizeof(level),1,stdin)!=1 || fread(&now,sizeof(now),1,stdin)!=1)break;
            if(!real_initialized) {
                if(game_session_init(&real_session,&game_default_config)!=GAME_OK)break;
                real_initialized=1;
            }
            status=game_session_select(&real_session,level,now);
            if(status==GAME_OK) {
                pending_available=0;
                real_selected_ms=now;
                real_have_detection=0;
                vision_stabilizer_timed_reset(&real_stabilizer);
            }
            real_snapshot(status);
        } else if (command == 'E') {
            uint64_t stamp[4];
            int32_t algorithm;
            int count,length;
            VisionDetection raw[VISION_MAX_DETECTIONS];
            char line[SCENE_PROTOCOL_MAX_LINE+1];
            VisionTimedStatus stable;
            if(fread(stamp,sizeof(uint64_t),4,stdin)!=4 ||
               fread(&algorithm,sizeof(algorithm),1,stdin)!=1 ||
               fread(frame,1,1280U*720U*3U,stdin)!=1280U*720U*3U)break;
            /* Reject obsolete work BEFORE it can support a pose candidate.
             * stamp[3] is dispatch/receipt time on the same caller timeline,
             * not a replacement for the original capture/process stamp. */
            count=-1;
            if(real_initialized && stamp[0]==game_session_snapshot(&real_session)->generation &&
               (!real_have_detection || (stamp[1]>real_detect_sequence && stamp[2]>real_detect_capture)) &&
               stamp[2]>=real_selected_ms && stamp[2]<=stamp[3] &&
               stamp[3]-stamp[2]<=game_default_config.scene_max_age_ms &&
               algorithm>=0 && algorithm<=2) {
                real_have_detection=1;
                real_detect_sequence=stamp[1];real_detect_capture=stamp[2];
                count=vision_detect_bgr888(frame,1280,720,1280*3,raw,VISION_MAX_DETECTIONS);
            } else (void)vision_portal_scan_bgr888(NULL,0,0,0);
            if(count>=0 && algorithm!=2)
                count=vision_stabilizer_update_timed(&real_stabilizer,raw,count,stamp[2],algorithm,
                    pending_detections,VISION_MAX_DETECTIONS,&stable);
            else if(count>=0)memcpy(pending_detections,raw,(size_t)count*sizeof(*raw));
            memset(&pending_frame,0,sizeof(pending_frame));
            pending_frame.stamp=(GameCaptureStamp){stamp[0],stamp[1],stamp[2]};
            pending_frame.valid=count>=0;
            pending_frame.detections=pending_detections;
            pending_frame.count=count>=0?count:0;
            pending_available=1;
            length=scene_protocol_encode(line,sizeof(line),pending_detections,pending_frame.count,
                pending_frame.valid,(uint32_t)stamp[1],(uint32_t)stamp[1],(uint32_t)stamp[2],1280,720);
            if(length<0)break;
            fwrite(line,1,(size_t)length,stdout);
        } else if (command == 'F' || command == 'T' || command == 'K') {
            uint64_t now;
            int status=GAME_BAD_STATE;
            GameAdaptedScene scene;
            if(fread(&now,sizeof(now),1,stdin)!=1)break;
            if(!real_initialized)break;
            if(command=='F' && pending_available) {
                (void)game_scene_adapt(&game_uncalibrated_identity_mapping,&pending_frame,&scene);
                status=game_session_submit(&real_session,&scene.input,now);
                if(status==GAME_STALE_SCENE)
                    vision_stabilizer_timed_reset(&real_stabilizer);
                pending_available=0;
            } else if(command=='T')status=game_session_start(&real_session,now);
            else if(command=='K')status=game_session_tick(&real_session,now);
            real_snapshot(status);
        } else if (command == 'P') {
            VisionPortalTemplate templates[2];
            float values[64];
            int32_t status;
            int p;
            if (fread(values,sizeof(float),64,stdin)!=64)break;
            for(p=0;p<2;++p) {
                memcpy(templates[p].corners,values+p*32,24*sizeof(float));
                memcpy(templates[p].center,values+p*32+24,2*sizeof(float));
                memcpy(templates[p].axis,values+p*32+26,2*sizeof(float));
                templates[p].length=values[p*32+28];
                templates[p].width=values[p*32+29];
                templates[p].reference_scale=values[p*32+30];
                templates[p].handedness=values[p*32+31];
            }
            status=vision_portal_configure(templates);
            /* Activation is separate from frame acquisition: no observed
             * SOURCE, synthetic frame stamp, or alternate detector path. */
            vision_set_portal_detector(vision_portal_detect_bgr888);
            fwrite(&status,sizeof(status),1,stdout);
        } else if (command == 'M') {
            float values[5];
            VisionRealSceneGeometry geometry;
            int32_t status;
            if(fread(values,sizeof(float),5,stdin)!=5)break;
            geometry.mirror_reflective_to_marker_span=values[0];
            geometry.mirror_body_to_marker_span=values[1];
            geometry.mirror_body_width_to_marker_span=values[2];
            geometry.wall_body_to_marker_span=values[3];
            geometry.wall_body_width_to_bar_span=values[4];
            status=vision_set_real_scene_geometry(&geometry);
            if(status==0)status=vision_set_real_scene_profile(1);
            fwrite(&status,sizeof(status),1,stdout);
        } else if (command == 'A' || command == 'G') {
            VisionPortalTag tags[6];
            int32_t count;
            int i;
            if(command=='A') {
                if(fread(frame,1,1280U*720U*3U,stdin)!=1280U*720U*3U)break;
                (void)vision_portal_scan_bgr888(frame,1280,720,1280*3);
            }
            count=vision_portal_last_tags(tags,6);
            fwrite(&count,sizeof(count),1,stdout);
            for(i=0;i<count;++i) {
                float row[11];
                row[0]=(float)tags[i].id;
                memcpy(row+1,tags[i].corners,8*sizeof(float));
                row[9]=tags[i].margin;row[10]=(float)tags[i].hamming;
                fwrite(row,sizeof(float),11,stdout);
            }
#endif
        } else if (command == 'R') {
            int32_t count, status;
            float dimensions[3], rows[12*VISION_MAX_DETECTIONS] = {0};
            float segments[4*RAY_GAME_MAX_SEGMENTS] = {0};
            int info[5+RAY_GAME_MAX_INTERACTIONS] = {0};
            if (fread(&count, sizeof(count), 1, stdin) != 1 ||
                count < 0 || count > VISION_MAX_DETECTIONS ||
                fread(dimensions, sizeof(float), 3, stdin) != 3 ||
                fread(rows, sizeof(float)*12, (size_t)count, stdin) != (size_t)count) break;
            status = game_trace(rows, count, dimensions[0], dimensions[1], dimensions[2], segments, info);
            fwrite(&status, sizeof(status), 1, stdout);
            fwrite(segments, sizeof(segments), 1, stdout);
            fwrite(info, sizeof(info), 1, stdout);
        } else break;
        fflush(stdout);
    }
    free(frame);
#ifdef VISION_WITH_APRILTAG
    vision_portal_shutdown();
#endif
    return 0;
}
