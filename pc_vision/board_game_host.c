/* PC authority for UART poses. No detector or second stabilizer. The existing
 * game_session/ray_game own all admission, complete rays, timer and score. */
#include "game_session.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
extern const GameConfig game_default_config;

static void output(const GameSession *session, int status)
{
    const GameSnapshot *v=game_session_snapshot(session);
    static const char *const names[]={"MIRROR","PORTAL_A","PORTAL_B","TARGET","SOURCE","WALL"};
    int i;
    printf("{\"status\":%d,\"game_state\":%d,\"generation\":%llu,\"level_id\":%u,"
           "\"sequence\":%llu,\"captured_ms\":%llu,\"valid\":%d,\"ready\":%d,"
           "\"elapsed_ms\":%llu,\"remaining_ms\":%llu,\"stars\":%u,\"models\":[",
           status,v->state,(unsigned long long)v->generation,v->level_id,
           (unsigned long long)v->scene_sequence,(unsigned long long)v->captured_ms,
           v->scene_valid,v->ready,(unsigned long long)v->elapsed_ms,
           (unsigned long long)v->remaining_ms,v->stars);
    for (i=0; i<v->object_count; ++i) {
        const SceneObject *o=&v->objects[i];
        printf("%s{\"type\":\"%s\",\"center\":[%.8g,%.8g],\"axis\":[%.8g,%.8g],"
               "\"size\":[%.8g,%.8g],\"logical_emitter\":%s}",i?",":"",names[o->type],
               o->center.x,o->center.y,o->axis.x,o->axis.y,o->length,o->width,
               o->type==RAY_OBJECT_SOURCE?"true":"false");
    }
    printf("],\"segments\":[");
    for (i=0; i<v->ray.segment_count; ++i) {
        const RaySegment *s=&v->ray.segments[i];
        printf("%s[%.8g,%.8g,%.8g,%.8g]",i?",":"",s->start.x,s->start.y,s->end.x,s->end.y);
    }
    printf("],\"success\":%d,\"termination\":%d}\n",v->ray.success,v->ray.termination);
    fflush(stdout);
}

int main(void)
{
    GameSession session;
    char line[512], command[24];
    int status=(int)game_session_init(&session,&game_default_config);
    if (status!=GAME_OK) return 2;
    output(&session,status);
    while (fgets(line,sizeof line,stdin)) {
        unsigned long long now=0;
        if (sscanf(line,"%23s %llu",command,&now)!=2) return 3;
        if (!strcmp(command,"quit")) break;
        if (!strcmp(command,"select")) {
            unsigned level=0;
            if (sscanf(line,"%*s %*s %u",&level)!=1) return 3;
            status=(int)game_session_select(&session,level,(uint64_t)now);
        } else if (!strcmp(command,"start")) {
            status=(int)game_session_start(&session,(uint64_t)now);
        } else if (!strcmp(command,"start_board")) {
            status=(int)game_session_start_after_board_ready(&session,(uint64_t)now);
        } else if (!strcmp(command,"tick")) {
            status=(int)game_session_tick(&session,(uint64_t)now);
        } else if (!strcmp(command,"clear")) {
            GameSceneInput invalid;
            memset(&invalid,0,sizeof invalid);
            invalid.generation=game_session_snapshot(&session)->generation;
            /* Invalid version clears the scene without inventing a capture
             * sequence or consuming/re-stamping an observation. */
            status=(int)game_session_submit(&session,&invalid,(uint64_t)now);
        } else if (!strcmp(command,"frame")) {
            unsigned long long generation, sequence, captured;
            int valid,count,i;
            SceneObject objects[GAME_MAX_MODELS];
            GameSceneInput input;
            if (sscanf(line,"%*s %*s %llu %llu %llu %d %d",&generation,&sequence,&captured,&valid,&count)!=5 ||
                count<0 || count>GAME_MAX_MODELS || (valid!=0 && valid!=1)) return 3;
            memset(objects,0,sizeof objects);
            for (i=0; i<count; ++i) {
                SceneObject *o=&objects[i];
                int type;
                if (!fgets(line,sizeof line,stdin) ||
                    sscanf(line,"%d %f %f %f %f %f %f",&type,&o->center.x,&o->center.y,
                           &o->axis.x,&o->axis.y,&o->length,&o->width)!=7 ||
                    type<0 || type>RAY_OBJECT_WALL || type==RAY_OBJECT_SOURCE) return 3;
                o->type=(RayObjectType)type;
            }
            memset(&input,0,sizeof input);
            input.version=GAME_SCENE_VERSION;
            input.generation=(uint64_t)generation; input.sequence=(uint64_t)sequence;
            input.captured_ms=(uint64_t)captured; input.valid=valid;
            input.objects=objects; input.object_count=count;
            status=(int)game_session_submit(&session,&input,(uint64_t)now);
        } else return 3;
        output(&session,status);
    }
    return 0;
}
