/* Fixed-emitter real-camera application. Standalone main, no menus/levels/KEY. */
#include "game_baremetal_io.h"
#include "game_beam_config.h"
#include "vision_portal.h"
#include "scene_protocol.h"
#include "xparameters.h"
#include "xil_io.h"
#include "xuartps_hw.h"
#include "sleep.h"
#include <stdio.h>
#include <string.h>

static uint8_t cpu_image[1280U*720U*3U] __attribute__((aligned(64)));
static GameBeam beam;
static GameLinuxDisplay display; /* Existing portable owner; no Linux platform. */
static VisionDetection detections[VISION_MAX_DETECTIONS];
static SceneStream scene_stream;

/* The board emits complete scene-v1 packets on the same PS UART used for
 * diagnostics.  Drain each packet before the next diagnostic line so a
 * human-readable log can never split a packet. */
static int scene_uart_put(void *context, unsigned char byte)
{
    (void)context;
    if (Xil_In32(STDOUT_BASEADDRESS + XUARTPS_SR_OFFSET) & XUARTPS_SR_TXFULL)
        return 0;
    Xil_Out32(STDOUT_BASEADDRESS + XUARTPS_FIFO_OFFSET, byte);
    return 1;
}

static void scene_uart_flush(void)
{
    unsigned int guard = 0;
    while (scene_stream.offset < scene_stream.length && guard++ < 5000U) {
        scene_stream_poll(&scene_stream, (uint32_t)game_baremetal_now_ms(),
                          scene_uart_put, NULL, 64U);
        if (scene_stream.offset < scene_stream.length)
            usleep(1000);
    }
}

static void scene_stream_publish_frame(const VisionDetection *objects, int count,
                                       int valid, uint64_t frame, uint64_t captured_ms)
{
    scene_stream_publish(&scene_stream, objects, count, valid,
                         (uint32_t)frame, (uint32_t)captured_ms);
    scene_uart_flush();
}
static struct {
    GameCaptureStamp stamp;
    uint64_t capture_begin, copy_done, detect_done, tags_done, submit_at, submit_done;
    uint64_t render_done, display_begin, display_done;
    int count, portal_called, display_status;
    GameBeamStatus status;
    VisionPortalTiming portal;
} frame_timing;

static long long elapsed(uint64_t end,uint64_t begin)
{
    return begin && end>=begin ? (long long)(end-begin) : -1;
}

static void print_frame_timing(const char *stage)
{
    uint64_t now=game_baremetal_now_ms();
    printf("BEAM_FRAME_DIAGNOSTIC stage=%s status=%s(%d) generation=%llu sequence=%llu captured_ms=%llu submit_at_ms=%llu age_at_detect_ms=%lld age_at_submit_ms=%lld age_now_ms=%lld count=%d\r\n",
        stage,game_beam_status_name(frame_timing.status),(int)frame_timing.status,
        (unsigned long long)frame_timing.stamp.generation,
        (unsigned long long)frame_timing.stamp.sequence,
        (unsigned long long)frame_timing.stamp.captured_ms,
        (unsigned long long)frame_timing.submit_at,
        elapsed(frame_timing.copy_done,frame_timing.stamp.captured_ms),
        elapsed(frame_timing.submit_at,frame_timing.stamp.captured_ms),
        elapsed(now,frame_timing.stamp.captured_ms),frame_timing.count);
    printf("BEAM_FRAME_COST capture_wait_copy_ms=%lld detect_ms=%lld tag_overlay_ms=%lld submit_ms=%lld render_ms=%lld display_ms=%lld display_status=%d\r\n",
        elapsed(frame_timing.copy_done,frame_timing.capture_begin),
        elapsed(frame_timing.detect_done,frame_timing.copy_done),
        elapsed(frame_timing.tags_done,frame_timing.detect_done),
        elapsed(frame_timing.submit_done,frame_timing.tags_done),
        elapsed(frame_timing.render_done,frame_timing.submit_done),
        elapsed(frame_timing.display_done,frame_timing.display_begin),frame_timing.display_status);
    printf("BEAM_PORTAL_COST called=%d clock_available=%d gray_us=%llu detector_us=%llu quad_us=%llu decode_us=%llu fit_us=%llu raw_tags=%lu accepted_tags=%lu quads=%lu\r\n",
        frame_timing.portal_called,frame_timing.portal.clock_available,
        (unsigned long long)frame_timing.portal.grayscale_us,
        (unsigned long long)frame_timing.portal.detector_us,
        (unsigned long long)frame_timing.portal.quad_us,
        (unsigned long long)frame_timing.portal.decode_us,
        (unsigned long long)frame_timing.portal.fit_us,
        (unsigned long)frame_timing.portal.raw_tags,(unsigned long)frame_timing.portal.accepted_tags,
        (unsigned long)frame_timing.portal.quads);
    printf("BEAM_QUAD_COST stage_mask=%lu threshold_us=%llu components_us=%llu clusters_us=%llu fit_quads_us=%llu\r\n",
        (unsigned long)frame_timing.portal.quad_stage_mask,
        (unsigned long long)frame_timing.portal.threshold_us,
        (unsigned long long)frame_timing.portal.components_us,
        (unsigned long long)frame_timing.portal.clusters_us,
        (unsigned long long)frame_timing.portal.fit_quads_us);
}

static unsigned diagnostic_tags(const VisionCanvas *canvas,const VisionDetection *d,int count)
{
    VisionPortalTag tags[6];
    unsigned seen=0,fitted=0,restricted=0;
    int i,j,n=vision_portal_last_tags(tags,6);
    for (i=0; i<count; ++i)
        if (d[i].type==VISION_PORTAL_A || d[i].type==VISION_PORTAL_B) fitted|=1U<<(unsigned)d[i].type;
    if (n<0) return (1U<<VISION_PORTAL_A)|(1U<<VISION_PORTAL_B);
    for (i=0; i<n; ++i) {
        unsigned bit=1U<<(tags[i].id<20?VISION_PORTAL_A:VISION_PORTAL_B);
        unsigned color=(fitted&bit)?0x40ff40U:0xffb000U;
        seen|=bit;
        for (j=0; j<4; ++j)
            vision_canvas_line(canvas,(VisionPoint){tags[i].corners[j][0],tags[i].corners[j][1]},
                (VisionPoint){tags[i].corners[(j+1)%4][0],tags[i].corners[(j+1)%4][1]},1,color);
    }
    restricted=seen&~fitted; /* Single/inconsistent tags remain diagnostic only. */
    return restricted;
}

int main(void)
{
    GameDisplayPlatform platform;
    GameDisplayMode mode;
    VisionCanvas canvas={cpu_image,1280,720,3840,sizeof cpu_image};
    const char *failure="prepare";
    unsigned frames=0;
    uint64_t last_log=0;
    int capture_stop,display_stop;
    scene_stream_init(&scene_stream, 8U, 115200U);
    /* Explicit boot epoch lets the PC discard a partial packet and reset its
     * sequence gate after a board restart. */
    scene_stream_publish_frame(NULL, 0, 0, 0, 0);
    printf("BEAM_STANDALONE_BEGIN source=(%d,%d) direction=(%d,%d) width=1280 height=720\r\n",
        (int)game_beam_default_config.emitter_point.x,
        (int)game_beam_default_config.emitter_point.y,
        (int)game_beam_default_config.emitter_direction.x,
        (int)game_beam_default_config.emitter_direction.y);
    printf("BEAM_STANDALONE_HARDWARE xsa_sha256=%s\r\n",GAME_BEAM_XSA_SHA256);
    printf("BEAM_DIAGNOSTICS version=3 max_age_ms=%llu age_policy=%s stability=%s capture_time=START_lower_bound\r\n",
        (unsigned long long)game_beam_default_config.max_age_ms,
        game_beam_default_config.max_age_ms ? "reject_expired" : "disabled_test",
        game_beam_default_config.stability_algorithm==VISION_STABILITY_B ? "B" : "A");
    {
        uint32_t control;
        /* Read-only cache evidence. BSP boot.S enables these before main;
         * absence of explicit cache calls in main is not proof of disabled caches. */
        __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(control));
        printf("BEAM_CPU sctlr=%08lx mmu=%u dcache=%u icache=%u\r\n",
            (unsigned long)control,(unsigned)(control&1U),
            (unsigned)((control>>2)&1U),(unsigned)((control>>12)&1U));
    }
    game_display_init(&display);
    if (game_baremetal_prepare()) goto failed;
    failure="measured_detector_configuration";
    if (vision_portal_configure(game_beam_portals) || vision_portal_initialize()) goto failed;
    vision_set_portal_detector(vision_portal_detect_bgr888);
    if (vision_set_real_scene_geometry(&game_beam_marker_geometry) ||
        vision_set_real_scene_profile(1) ||
        game_beam_init(&beam,&game_beam_default_config,1,game_baremetal_now_ms())!=GAME_BEAM_OK) goto failed;
    game_baremetal_display_platform(&platform);
    game_display_control_720p_mode(&mode);
    failure="display_prepare";
    if (game_display_prepare_continuous(&display,&mode,&platform,&canvas)!=GAME_DISPLAY_OK) goto failed;
    failure="display_start";
    if (game_display_start(&display,500)!=GAME_DISPLAY_OK) goto failed;
    printf("BEAM_HDMI_STARTED buffers=3 stride=5760 span=4147200\r\n");
    failure="capture_start";
    if (game_baremetal_capture_start()) goto failed;
    printf("BEAM_CAPTURE_STARTED\r\n");
    for (;;) {
        GameCaptureStamp stamp;
        GameDetectionFrame frame;
        GameBeamStatus status;
        const GameBeamSnapshot *snapshot;
        uint64_t now;
        unsigned restricted;
        VisionPortalTiming portal_before,portal_after;
        char age_label[64];
        int count;
        memset(&frame_timing,0,sizeof frame_timing);
        frame_timing.count=-1;
        frame_timing.display_status=-1;
        frame_timing.status=GAME_BEAM_NO_FRAME;
        frame_timing.capture_begin=game_baremetal_now_ms();
        failure="capture_copy";
        if (game_baremetal_capture_copy(cpu_image,sizeof cpu_image,&stamp)) goto failed;
        frame_timing.stamp=stamp;
        frame_timing.copy_done=game_baremetal_now_ms();
        failure="detect";
        vision_portal_last_timing(&portal_before);
        count=vision_detect_bgr888(cpu_image,1280,720,3840,detections,VISION_MAX_DETECTIONS);
        frame_timing.detect_done=game_baremetal_now_ms();
        frame_timing.count=count;
        scene_stream_publish_frame(detections, count, count >= 0,
                                   stamp.sequence, stamp.captured_ms);
        vision_portal_last_timing(&portal_after);
        frame_timing.portal_called=portal_after.scan_sequence!=portal_before.scan_sequence;
        if (frame_timing.portal_called) frame_timing.portal=portal_after;
        if (count<0) goto failed;
        restricted=frame_timing.portal_called ? diagnostic_tags(&canvas,detections,count) :
            (1U<<VISION_PORTAL_A)|(1U<<VISION_PORTAL_B);
        frame_timing.tags_done=game_baremetal_now_ms();
        frame=(GameDetectionFrame){stamp,1,0,detections,count};
        now=game_baremetal_now_ms();
        frame_timing.submit_at=now;
        failure="beam_submit";
        status=game_beam_submit(&beam,&frame,restricted,now);
        frame_timing.status=status;
        frame_timing.submit_done=game_baremetal_now_ms();
        if (status==GAME_BEAM_STALE || status==GAME_BEAM_BAD_TIME || status==GAME_BEAM_BAD_ARGUMENT ||
            status==GAME_BEAM_OLD_GENERATION || status==GAME_BEAM_DUPLICATE_FRAME) goto failed;
        failure="beam_render";
        snapshot=game_beam_snapshot(&beam);
        if (!snapshot || game_beam_render(snapshot,&canvas)) goto failed;
        now=game_baremetal_now_ms();
        if (now<stamp.captured_ms) goto failed;
        snprintf(age_label,sizeof age_label,"FRAME AGE %llu MS",
            (unsigned long long)(now-stamp.captured_ms));
        vision_canvas_text(&canvas,12,12,age_label,2,0xffb000U);
        frame_timing.render_done=game_baremetal_now_ms();
        failure="pre_display_freshness";
        now=game_baremetal_now_ms();
        if (now<stamp.captured_ms ||
            (beam.config.max_age_ms && now-stamp.captured_ms>beam.config.max_age_ms) ||
            game_baremetal_capture_check()) goto failed;
        failure="display_submit";
        frame_timing.display_begin=game_baremetal_now_ms();
        frame_timing.display_status=(int)game_display_update(&display,&canvas,500);
        frame_timing.display_done=game_baremetal_now_ms();
        if (frame_timing.display_status!=GAME_DISPLAY_OK) goto failed;
        failure="post_display_freshness";
        now=game_baremetal_now_ms();
        if (now<stamp.captured_ms ||
            (beam.config.max_age_ms && now-stamp.captured_ms>beam.config.max_age_ms) ||
            game_baremetal_capture_check()) goto failed;
        ++frames;
        if (frames==1U) printf("BEAM_FIRST_FRAME sequence=%llu captured_ms=%llu\r\n",
            (unsigned long long)stamp.sequence,(unsigned long long)stamp.captured_ms);
        if (frames==1U || now-last_log>=1000U) {
            printf("BEAM_FRAME sequence=%llu age_ms=%llu detections=%d valid=%d beam_status=%d segments=%d raw_mask=%02x supported_mask=%02x pending_mask=%02x restricted_mask=%02x\r\n",
                (unsigned long long)stamp.sequence,(unsigned long long)(now-stamp.captured_ms),
                count,snapshot->valid,(int)status,snapshot->ray.segment_count,
                snapshot->raw_mask,snapshot->supported_mask,snapshot->pending_mask,snapshot->restricted_mask);
            last_log=now;
            print_frame_timing("submitted");
        }
    }
failed:
    game_baremetal_first_fault(failure);
    if (frame_timing.capture_begin) print_frame_timing(failure);
    capture_stop=game_baremetal_capture_stop();
    display_stop=(int)game_display_stop(&display,1000);
    printf("BEAM_SAFE_STOP stage=%s capture_result=%d display_result=%d display_released=%d frames=%u\r\n",
        failure,capture_stop,display_stop,game_display_owner_can_exit(&display),frames);
    /* No exit/reinitialization/retry can reuse uncertain stores. Static RAM,
     * object contexts and clocks needed by an unhalted channel remain alive. */
    for (;;) usleep(1000000);
}
