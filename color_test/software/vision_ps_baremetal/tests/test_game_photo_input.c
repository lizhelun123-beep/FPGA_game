/* Real supplied photographs, canonical detector and unchanged game rules.
 * Synthetic time is ONLY for directed core checks, never board acceptance. */
#include "game_photo_input.h"
#include "game_loop.h"
#include "game_config.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"line=%d check=%s\n",__LINE__,#x); return 1; } } while (0)
static int near(float a,float b) { return fabsf(a-b)<0.001f; }
int main(int argc,char **argv)
{
    GamePhotoInput input={0};
    GameLoop loop;
    unsigned level;
    CHECK(argc==2);
    CHECK(game_photo_load(&input,argv[1]));
    CHECK(!game_photo_load(&input,argv[1]));
    CHECK(game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,
                         &game_default_menu_layout)==GAME_OK);
    for (level=1;level<=3;++level) {
        GameLoopEvent e;
        GameLoopOutput out;
        GameDetectionFrame frame;
        GameCaptureStamp stamp;
        const GameLevelConfig *config=&game_default_config.levels[level-1];
        uint64_t now=level*10000U;
        int i;
        memset(&e,0,sizeof e); e.kind=GAME_LOOP_MENU;
        e.data.menu=(GameMenuAction){GAME_MENU_SELECT,level};
        CHECK(game_loop_step(&loop,now,&e,&out)==GAME_OK);
        e.data.menu=(GameMenuAction){GAME_MENU_START,0};
        CHECK(game_loop_step(&loop,now,&e,&out)!=GAME_OK);
        CHECK(out.game.state==GAME_PREPARING && !out.game.ready && !out.game.stars);
        e.kind=GAME_LOOP_DISPATCH; e.data.dispatch.sequence=level; e.data.dispatch.captured_ms=now;
        CHECK(game_loop_step(&loop,now,&e,&out)==GAME_OK && out.has_stamp);
        stamp=out.stamp;
        CHECK(!game_photo_detect(&input,0,stamp,&frame));
        CHECK(game_photo_detect(&input,level,stamp,&frame));
        CHECK(frame.stamp.generation==stamp.generation && frame.stamp.sequence==stamp.sequence &&
              frame.stamp.captured_ms==now && frame.valid && !frame.held);
        CHECK(frame.count==config->object_count);
        e.kind=GAME_LOOP_DETECTION; e.data.detection=frame;
        CHECK(game_loop_step(&loop,now,&e,&out)==GAME_OK);
        CHECK(out.game.scene_valid && out.game.object_count==config->object_count);
        CHECK(out.game.state==GAME_PREPARING && !out.game.stars && !out.game.elapsed_ms);
        CHECK(out.game.ready==!out.game.ray.success);
        for (i=0;i<out.game.object_count;++i) {
            const SceneObject *o=&out.game.objects[i];
            const GameObjectConfig *rule=&config->objects[i];
            CHECK(o->type==rule->anchor.type);
            if (rule->motion!=GAME_FREE) {
                CHECK(near(o->center.x,rule->anchor.center.x) && near(o->center.y,rule->anchor.center.y));
            }
            if (rule->motion==GAME_FIXED) {
                float length=sqrtf(rule->anchor.axis.x*rule->anchor.axis.x+rule->anchor.axis.y*rule->anchor.axis.y);
                CHECK(near(o->axis.x,rule->anchor.axis.x/length) && near(o->axis.y,rule->anchor.axis.y/length));
            }
            if (o->type==RAY_OBJECT_SOURCE) {
                CHECK(near(o->source_tip.x,o->center.x+o->axis.x*o->length*(2.0f/3.0f)) &&
                      near(o->source_tip.y,o->center.y+o->axis.y*o->length*(2.0f/3.0f)));
            }
        }
        printf("PHOTO_CORE level=%u solved=%d ready=%d segments=%d state=%d\n",level,
               out.game.ray.success,out.game.ready,out.game.ray.segment_count,out.game.state);
        e.kind=GAME_LOOP_MENU; e.data.menu=(GameMenuAction){GAME_MENU_START,0};
        if (out.game.ray.success) {
            CHECK(game_loop_step(&loop,now,&e,&out)==GAME_NEED_UNSOLVED);
            CHECK(out.game.state==GAME_PREPARING && !out.game.stars);
        } else {
            CHECK(game_loop_step(&loop,now,&e,&out)==GAME_OK);
            CHECK(out.game.state==GAME_RUNNING && !out.game.stars);
        }
        CHECK(game_loop_step(&loop,now+game_default_config.scene_max_age_ms+1,NULL,&out)==GAME_OK);
        CHECK(!out.game.scene_valid && !out.game.ready);
        /* Same real detections: a new sequence with the OLD dispatch time
         * must stay stale, and another selection must reject the old epoch. */
        e.kind=GAME_LOOP_DETECTION; e.data.detection=frame;
        e.data.detection.stamp.sequence+=100;
        CHECK(game_loop_step(&loop,now+1000,&e,&out)==GAME_STALE_SCENE);
        e.kind=GAME_LOOP_MENU; e.data.menu=(GameMenuAction){GAME_MENU_SELECT,level};
        CHECK(game_loop_step(&loop,now+1001,&e,&out)==GAME_OK);
        e.kind=GAME_LOOP_DETECTION; e.data.detection=frame;
        CHECK(game_loop_step(&loop,now+1002,&e,&out)==GAME_OLD_GENERATION);
        CHECK(!out.game.scene_valid && !out.game.stars);
    }
    game_photo_close(&input);
    CHECK(!input.pixels[0] && !input.pixels[1] && !input.pixels[2]);
    printf("PHOTO_CORE_PASS checks=%u synthetic_time=1 board_acceptance=0\n",checks);
    return 0;
}
