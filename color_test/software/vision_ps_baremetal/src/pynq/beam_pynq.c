#include "beam_pynq.h"
#include "game_beam.h"
#include "game_beam_config.h"
#include "beam_control_state.h"
#include "beam_wire_protocol.h"
#include "beam_pynq_portal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W 1280U
#define H 720U
#define ROW (W*3U)
#define PIXELS (ROW*H)
struct BeamPynq {
    GameBeam beam;
    BeamControlState control;
    BeamWireParser parser;
    BeamPynqClock clock;
    void *clock_context;
    uint64_t last_now, ticket;
    GameCaptureStamp committed;
    uint32_t tx;
    int stage, failed;
    uint8_t pixels[3U*PIXELS]; /* input, committed background, complete canvas */
};
static BeamPynq *active;

static int now_ms(BeamPynq *a, uint64_t *now)
{
    if (!a || a!=active || a->failed || a->clock(a->clock_context,now) || *now<a->last_now) {
        if (a && a==active) a->failed=1;
        return -1;
    }
    a->last_now=*now;
    return 0;
}

unsigned beam_pynq_abi(void) { return 1U; }
size_t beam_pynq_result_size(void) { return sizeof(BeamPynqResult); }

BeamPynq *beam_pynq_open(uint64_t generation, BeamPynqClock clock, void *context)
{
    BeamPynq *a;
    uint64_t now;
    if (active || !generation || !clock || clock(context,&now)) return NULL;
    if (game_beam_default_config.width!=W || game_beam_default_config.height!=H ||
        game_beam_default_config.detector_profile!=VISION_PROFILE_RESTORED) return NULL;
    a=(BeamPynq *)calloc(1,sizeof(*a));
    if (!a) return NULL;
    if (vision_set_real_scene_profile(VISION_PROFILE_RESTORED) ||
        game_beam_init(&a->beam,&game_beam_default_config,generation,now)!=GAME_BEAM_OK) {
        free(a); return NULL;
    }
    a->clock=clock; a->clock_context=context; a->last_now=now;
    active=a;
    return a;
}

void beam_pynq_close(BeamPynq *a)
{
    if (a && a==active) { active=NULL; free(a); }
}

int beam_pynq_receive(BeamPynq *a, unsigned byte, uint8_t *reply, size_t capacity)
{
    BeamWirePacket packet;
    BeamControlMessage message;
    char internal[BEAM_CONTROL_MAX_LINE+1U];
    uint64_t received, sent;
    int n;
    if (!a || a!=active || a->failed || a->stage || byte>255U || !reply ||
        capacity<BEAM_WIRE_MAX_PACKET) return -1;
    if (!beam_wire_feed(&a->parser,(uint8_t)byte,&packet)) return 0;
    if (now_ms(a,&received)) return -1;
    if (packet.type==BEAM_WIRE_SYNC && packet.length==4U) {
        if (now_ms(a,&sent)) return -1;
        return beam_wire_sync_reply((char *)reply,capacity,
            (uint32_t)beam_wire_le(packet.payload,4),received,sent);
    }
    if (!beam_wire_control_decode(&packet,&message)) return 0;
    n=beam_control_receive(&a->control,&a->beam,&message,received,internal,sizeof internal);
    if (n<0) { a->failed=1; return -1; }
    return n ? beam_wire_control_reply((char *)reply,capacity,internal,(size_t)n) : 0;
}

int beam_pynq_frame(BeamPynq *a, const uint8_t *bgr, unsigned width,
    unsigned height, size_t stride, size_t capacity, uint64_t generation,
    uint64_t sequence, uint64_t captured_ms, BeamPynqResult *result,
    uint8_t *pose, size_t pose_capacity)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    GameDetectionFrame frame;
    GameBeamStatus status;
    unsigned portal_restricted;
    const GameBeamSnapshot *snapshot;
    GameBeamSnapshot shown;
    const uint8_t *background;
    VisionCanvas canvas;
    uint8_t *input, *saved, *output;
    uint64_t now;
    unsigned y;
    int count, length=0;
    char label[120];
    if (!a || a!=active || a->failed || a->stage || !bgr || !result || !pose ||
        pose_capacity<BEAM_WIRE_MAX_PACKET || width!=W || height!=H || stride<ROW ||
        stride>(SIZE_MAX-ROW)/(H-1U) || capacity<(H-1U)*stride+ROW ||
        !generation || !sequence || !captured_ms || a->ticket==UINT64_MAX) return -1;
    input=a->pixels; saved=input+PIXELS; output=saved+PIXELS;
    /* Reject overlap: no caller may pass a previous canvas as a camera frame. */
    if ((uintptr_t)bgr>UINTPTR_MAX-capacity ||
        ((uintptr_t)bgr<(uintptr_t)output+PIXELS && (uintptr_t)bgr+capacity>(uintptr_t)input)) return -1;
    for (y=0;y<H;++y) memcpy(input+y*ROW,bgr+y*stride,ROW);
    count=vision_detect_bgr888(input,W,H,ROW,detections,VISION_MAX_DETECTIONS);
    if (count<0 || now_ms(a,&now)) { a->failed=1; return -1; }
    frame.stamp.generation=generation; frame.stamp.sequence=sequence; frame.stamp.captured_ms=captured_ms;
    frame.valid=1; frame.held=0; frame.detections=detections; frame.count=count;
    portal_restricted=beam_pynq_portal_restrictions(detections,count);
    /* 观测质量结果由 GameBeam 转为 PENDING/RESTRICTED/INVALID；
     * 这些结果仍需刷新相机画面和保留光路，不能当成进程故障。 */
    status=game_beam_submit(&a->beam,&frame,portal_restricted,now);
    snapshot=game_beam_snapshot(&a->beam);
    if (!snapshot || now_ms(a,&now)) return -1;
    if (a->control.pose_enabled) {
        length=beam_wire_pose_encode((char *)pose,pose_capacity,snapshot,&a->control.level,a->tx++,now);
        if (length<0) { a->failed=1; return -1; }
    }
    if (snapshot->valid) { memcpy(saved,input,PIXELS); a->committed=frame.stamp; }
    background=input;
    if (now_ms(a,&now)) return -1;
    if (game_beam_display_snapshot(&a->beam,now,&shown)) {
        if (shown.generation!=a->committed.generation || shown.sequence!=a->committed.sequence ||
            shown.captured_ms!=a->committed.captured_ms) { a->failed=1; return -1; }
        background=saved;
    } else {
        shown=*snapshot;
        shown.generation=generation; shown.sequence=sequence; shown.captured_ms=captured_ms;
    }
    memcpy(output,background,PIXELS);
    canvas.data=output; canvas.width=W; canvas.height=H; canvas.stride=ROW; canvas.capacity=PIXELS;
    /* 年龄门槛已经由 game_beam_submit 统一处理；过期观测仍要绘制当前相机
     * 背景或保留光路，不能把一次识别过期误判为 PYNQ 进程故障。 */
    if (game_beam_render(&shown,&canvas) || now_ms(a,&now) || now<captured_ms) {
        a->failed=1; return -1;
    }
    snprintf(label,sizeof label,"%s FRAME %llu AGE %llu MS INPUT %s",
        shown.display_stale ? "STALE" : "CAMERA",(unsigned long long)shown.sequence,
        (unsigned long long)(now-shown.captured_ms),game_beam_status_name(status));
    vision_canvas_text(&canvas,12,12,label,2,0xffb000U);
    memset(result,0,sizeof(*result));
    result->ticket=++a->ticket; result->generation=generation; result->sequence=sequence;
    result->captured_ms=captured_ms; result->shown_generation=shown.generation;
    result->shown_sequence=shown.sequence; result->shown_captured_ms=shown.captured_ms;
    result->struct_size=sizeof(*result); result->status=(uint32_t)status;
    result->detections=(uint32_t)count; result->valid=(uint32_t)snapshot->valid;
    result->display_stale=(uint32_t)shown.display_stale; result->pose_bytes=(uint32_t)length;
    result->ray_segments=(uint32_t)snapshot->ray.segment_count;
    result->raw_mask=snapshot->raw_mask; result->pending_mask=snapshot->pending_mask;
    result->missing_mask=snapshot->missing_mask;
    a->stage=1;
    return 0;
}

const uint8_t *beam_pynq_canvas(BeamPynq *a)
{ return a && a==active && !a->failed && a->stage ? a->pixels+2U*PIXELS : NULL; }

int beam_pynq_submitted(BeamPynq *a, uint64_t ticket)
{
    if (!a || a!=active || a->failed || a->stage!=1 || ticket!=a->ticket) return -1;
    beam_control_display_submitted(&a->control); a->stage=2;
    return 0;
}

int beam_pynq_retired(BeamPynq *a, uint64_t ticket, uint8_t *reply, size_t capacity)
{
    char internal[BEAM_CONTROL_MAX_LINE+1U];
    uint64_t now;
    int n;
    if (!a || a!=active || a->failed || a->stage!=2 || ticket!=a->ticket || !reply ||
        capacity<BEAM_WIRE_MAX_PACKET || now_ms(a,&now)) return -1;
    n=beam_control_display_retired(&a->control,now,internal,sizeof internal);
    if (n<0) { a->failed=1; return -1; }
    a->stage=0;
    return n ? beam_wire_control_reply((char *)reply,capacity,internal,(size_t)n) : 0;
}
