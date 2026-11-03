#include "game_beam.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static VisionDetection detection(VisionType type, float x, float y,
                                 float ax, float ay, float length, float width)
{
    VisionDetection d;
    memset(&d, 0, sizeof(d));
    d.type=type; d.geometry_center_x=x; d.geometry_center_y=y;
    d.center_x=(int)x; d.center_y=(int)y; d.axis_x=ax; d.axis_y=ay;
    d.major_length=length; d.minor_width=width;
    d.bbox_w=(int)length; d.bbox_h=(int)width;
    d.confidence_percent=100; d.geometry_is_effective=1;
    return d;
}

static GameDetectionFrame frame(VisionDetection *d, int count,
                                uint64_t generation, uint64_t sequence,
                                uint64_t captured)
{
    GameDetectionFrame f;
    memset(&f, 0, sizeof(f));
    f.stamp=(GameCaptureStamp){generation,sequence,captured};
    f.valid=1; f.detections=d; f.count=count;
    return f;
}

int main(void)
{
    GameBeam beam;
    GameBeamConfig config={GAME_BEAM_CONFIG_VERSION,1280,720,
                           {32,360},{1,0},250,VISION_STABILITY_A,0,0,0,0,250};
    VisionDetection target=detection(VISION_TARGET,100,360,1,0,30,30);
    VisionDetection mirror=detection(VISION_MIRROR,300,360,0,1,46,25);
    VisionDetection portals[2]={
        detection(VISION_PORTAL_A,400,360,0,1,150,50),
        detection(VISION_PORTAL_B,700,360,0,1,150,50)};
    GameDetectionFrame f;
    const GameBeamSnapshot *view;
    assert(!strcmp(game_beam_status_name(GAME_BEAM_STALE),"STALE"));
    assert(!strcmp(game_beam_status_name(GAME_BEAM_BAD_ARGUMENT),"BAD_ARGUMENT"));
    assert(!strcmp(game_beam_status_name((GameBeamStatus)-1),"UNKNOWN"));

    assert(game_beam_init(&beam,&config,7,1)==GAME_BEAM_OK);
    f=frame(NULL,0,7,1,10);
    assert(game_beam_submit(&beam,&f,0,11)==GAME_BEAM_OK);
    view=game_beam_snapshot(&beam);
    assert(view->valid && view->object_count==0 && view->ray.segment_count==1);
    assert(fabsf(view->ray.segments[0].start.x-32)<.01f);
    assert(fabsf(view->ray.segments[0].end.x-1279)<.01f);

    f=frame(&target,1,7,2,20);
    assert(game_beam_submit(&beam,&f,0,21)==GAME_BEAM_OK);
    view=game_beam_snapshot(&beam);
    assert(view->valid && view->ray.success && view->ray.termination==RAY_GAME_TARGET);
    /* A hit is a property of this frame only; the next empty frame continues. */
    f=frame(NULL,0,7,3,30);
    assert(game_beam_submit(&beam,&f,0,31)==GAME_BEAM_OK);
    view=game_beam_snapshot(&beam);
    assert(view->valid && !view->ray.success && view->ray.termination==RAY_GAME_BOUNDARY);

    f=frame(portals,2,7,4,40);
    assert(game_beam_submit(&beam,&f,1U<<VISION_PORTAL_A,41)==GAME_BEAM_RESTRICTED);
    assert(!game_beam_snapshot(&beam)->valid);
    /* Current validity never borrows a display-only retained result. */
    assert(game_beam_snapshot(&beam)->object_count==0);
    assert(game_beam_snapshot(&beam)->ray.segment_count==0);

    config.stability_algorithm=VISION_STABILITY_B;
    assert(game_beam_reset(&beam,8,50)==GAME_BEAM_OK);
    f=frame(&mirror,1,8,1,60);
    assert(game_beam_submit(&beam,&f,0,61)==GAME_BEAM_OK);
    mirror.axis_x=0.64f; mirror.axis_y=0.77f;
    f=frame(&mirror,1,8,2,120);
    assert(game_beam_submit(&beam,&f,0,121)==GAME_BEAM_PENDING ||
           game_beam_snapshot(&beam)->valid);
    f=frame(&mirror,1,8,3,180);
    assert(game_beam_submit(&beam,&f,0,181)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&beam)->valid);
    f=frame(&mirror,1,7,4,190);
    assert(game_beam_submit(&beam,&f,0,191)==GAME_BEAM_STALE);
    f=frame(&mirror,1,8,3,195);
    assert(game_beam_submit(&beam,&f,0,196)==GAME_BEAM_DUPLICATE_FRAME);
    assert(game_beam_tick(&beam,500)==GAME_BEAM_STALE);
    assert(!game_beam_snapshot(&beam)->valid);
    /* ARM permits unsigned enums: the range check must reject negative and
     * out-of-range inputs without relying on a type<zero comparison. */
    assert(game_beam_reset(&beam,9,510)==GAME_BEAM_OK);
    target.type=(VisionType)-1;
    f=frame(&target,1,9,1,520);
    assert(game_beam_submit(&beam,&f,0,521)==GAME_BEAM_INVALID_GEOMETRY);
    target.type=(VisionType)(VISION_WALL+1);
    f=frame(&target,1,9,1,530);
    assert(game_beam_submit(&beam,&f,0,531)==GAME_BEAM_INVALID_GEOMETRY);
    f=frame(NULL,0,9,1,540);
    assert(game_beam_submit(&beam,&f,0,541)==GAME_BEAM_OK);
    /* The untimed camera-overlay test permits slow processing of a new CPU
     * frame, while preserving its original identity and clock validation. */
    config.max_age_ms=0;
    assert(game_beam_init(&beam,&config,10,1)==GAME_BEAM_OK);
    assert(game_beam_tick(&beam,2)==GAME_BEAM_STALE); /* Still needs a frame. */
    f=frame(NULL,0,10,1,10);
    assert(game_beam_submit(&beam,&f,0,1373)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&beam)->captured_ms==10);
    assert(game_beam_tick(&beam,5000)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&beam)->valid);
    assert(game_beam_submit(&beam,&f,0,5001)==GAME_BEAM_DUPLICATE_FRAME);
    f=frame(NULL,0,9,2,20);
    assert(game_beam_submit(&beam,&f,0,5002)==GAME_BEAM_STALE);
    f=frame(NULL,0,10,2,6000);
    assert(game_beam_submit(&beam,&f,0,5003)==GAME_BEAM_STALE); /* Future time. */
    f=frame(NULL,0,10,2,9);
    assert(game_beam_submit(&beam,&f,0,5004)==GAME_BEAM_STALE); /* Capture reversal. */
    f=frame(NULL,0,10,2,20);
    f.held=1;
    assert(game_beam_submit(&beam,&f,0,5005)==GAME_BEAM_STALE);
    f.held=0;
    assert(game_beam_submit(&beam,&f,0,5006)==GAME_BEAM_OK);
    assert(game_beam_snapshot(&beam)->sequence==2);
    assert(game_beam_tick(&beam,5005)==GAME_BEAM_BAD_TIME);
    config.max_age_ms=250;
    assert(game_beam_init(&beam,&config,11,1)==GAME_BEAM_OK);
    f=frame(NULL,0,11,1,10);
    assert(game_beam_submit(&beam,&f,0,260)==GAME_BEAM_OK); /* Inclusive. */
    f=frame(NULL,0,11,2,20);
    assert(game_beam_submit(&beam,&f,0,271)==GAME_BEAM_STALE);
    config.max_age_ms=251;
    assert(game_beam_init(&beam,&config,12,1)==GAME_BEAM_BAD_CONFIG);
    /* Six raw candidates can only contain a duplicate/invalid identity among
     * the five physical classes.  Treat it as nonfatal scene ambiguity and
     * retain the previous complete authority snapshot. */
    {
        VisionDetection ambiguous[7];
        GameBeamSnapshot shown;
        config.max_age_ms=0;
        config.display_timeout_ms=6000;
        config.display_dropout_ms=250;
        ambiguous[0]=detection(VISION_MIRROR,200,200,1,0,80,20);
        ambiguous[1]=detection(VISION_PORTAL_A,350,200,1,0,120,30);
        ambiguous[2]=detection(VISION_PORTAL_B,550,200,1,0,120,30);
        ambiguous[3]=detection(VISION_TARGET,750,200,1,0,30,30);
        ambiguous[4]=detection(VISION_WALL,950,200,1,0,120,30);
        ambiguous[5]=detection(VISION_PORTAL_B,550,400,1,0,120,30);
        ambiguous[6]=detection(VISION_PORTAL_A,350,400,1,0,120,30);
        assert(game_beam_init(&beam,&config,13,1)==GAME_BEAM_OK);
        f=frame(NULL,0,13,1,10);
        assert(game_beam_submit(&beam,&f,0,11)==GAME_BEAM_OK);
        /* Seven raw candidates are still within the detector's observation
         * capacity; the duplicate identities make the scene ambiguous and
         * must remain nonfatal to display/scanout. */
        f=frame(ambiguous,7,13,2,20);
        assert(game_beam_submit(&beam,&f,0,21)==GAME_BEAM_INVALID_GEOMETRY);
        assert(!game_beam_snapshot(&beam)->valid);
        assert(game_beam_display_snapshot(&beam,21,&shown));
        assert(shown.display_stale && shown.sequence==1 && shown.captured_ms==10);
        assert(!game_beam_display_snapshot(&beam,60010,&shown));
        assert(game_beam_retained_snapshot(&beam,&shown));
        assert(shown.display_stale && !shown.valid && !shown.ray.success && shown.ray.segment_count>0);
        assert(shown.sequence==1 && shown.captured_ms==10);
        assert(!game_beam_snapshot(&beam)->valid && !game_beam_snapshot(&beam)->ray.segment_count);
    }
    puts("game beam checks passed");
    return 0;
}
