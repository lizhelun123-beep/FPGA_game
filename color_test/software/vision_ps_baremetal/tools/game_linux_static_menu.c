#if defined(__linux__)
#define _POSIX_C_SOURCE 200809L
#endif
/* --check is pure CPU. Reviewed 720p modes require the installed same-boot
 * hardware/software gate. --menu720 uses real mouse input and stopped-buffer
 * updates; the native800 --display path remains closed. */
#include "game_linux_display.h"
#include "game_linux_capture.h"
#include "game_render.h"
#include "game_linux_io.h"
#include "game_config.h"
#include "game_photo_input.h"
#include "game_beam.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>
#include <signal.h>
#if defined(__linux__)
#include <time.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/select.h>
#include <sys/time.h>
#include <unistd.h>
#endif

static volatile sig_atomic_t deferred_exit;
static void defer_exit(int signal_number) { deferred_exit=signal_number; }

#if defined(__linux__)
/* Camera-only fixed-emitter path. It deliberately does not construct
 * GameLoop/GameSession: the beam owner accepts the current unique subset of
 * physical classes and presents one atomic source-image/ray snapshot. */
typedef struct {
    GameLinuxDisplay display;
    GameLinuxLiveSession session;
    GameDisplayPlatform display_platform, capture_platform;
    VisionCanvas frame;
    GameBeam beam;
    const GameLinuxCalls *calls;
    int live_in, live_out, live_pid, ready, capture_owned;
    uint64_t capture_virtual, capture_physical;
    uint64_t generation;
    unsigned frame_count;
    int first_frame;
    char line[256];
    size_t line_used;
} Beam720;

static int beam_now(Beam720 *b,uint64_t *now)
{
    return b->calls->clock_ms(b->calls->context,now);
}

static int beam_image_frame(void *context,const GameDetectionFrame *detections,
                            const GameCaptureImageView *image)
{
    Beam720 *b=context;
    uint64_t now;
    GameBeamStatus status;
    const GameBeamSnapshot *snapshot;
    if (!b || !detections || !image || detections->stamp.generation!=b->generation ||
        beam_now(b,&now) || game_capture_image_copy(image,&b->frame)) return -1;
    status=game_beam_submit(&b->beam,detections,0,now);
    if (status==GAME_BEAM_BAD_TIME || status==GAME_BEAM_BAD_ARGUMENT ||
        status==GAME_BEAM_OLD_GENERATION || status==GAME_BEAM_DUPLICATE_FRAME)
        return -1;
    snapshot=game_beam_snapshot(&b->beam);
    if (!snapshot || game_beam_render(snapshot,&b->frame)) return -1;
    if (game_display_update(&b->display,&b->frame,500)!=GAME_DISPLAY_OK) return -1;
    ++b->frame_count;
    if (!b->first_frame) {
        b->first_frame=1;
        printf("BEAM_FIRST_FRAME sequence=%llu captured_ms=%llu\n",
               (unsigned long long)image->stamp.sequence,
               (unsigned long long)image->stamp.captured_ms);
        fflush(stdout);
    }
    return 0;
}

static int beam_spawn(Beam720 *b)
{
    int in_pipe[2],out_pipe[2]; pid_t pid; char span[32];
    if (pipe(in_pipe) || pipe(out_pipe)) return -1;
    snprintf(span,sizeof span,"%u",GAME_CAPTURE_FRAME_SPAN);
    pid=fork();
    if (pid<0) return -1;
    if (!pid) {
        char address[32];
        snprintf(address,sizeof address,"%llu",(unsigned long long)b->capture_physical);
        {
            char *const argv[]={(char*)"python3",(char*)"-B",
                (char*)"/run/game_live_camera/capture/capture_worker.py",(char*)"--game-bridge",
                (char*)"--bridge-physical",address,(char*)"--bridge-span",span,NULL};
            dup2(in_pipe[0],STDIN_FILENO); dup2(out_pipe[1],STDOUT_FILENO);
            close(in_pipe[0]);close(in_pipe[1]);close(out_pipe[0]);close(out_pipe[1]);
            execv("/usr/bin/python3",argv); _exit(127);
        }
    }
    close(in_pipe[0]); close(out_pipe[1]);
    b->live_in=in_pipe[1]; b->live_out=out_pipe[0]; b->live_pid=pid;
    fcntl(b->live_out,F_SETFL,fcntl(b->live_out,F_GETFL,0)|O_NONBLOCK);
    return 0;
}

static int beam_wait_ready(Beam720 *b,unsigned timeout_ms)
{
    uint64_t start,now; fd_set set; struct timeval tv; int n;
    char data[256]; size_t used=0;
    if (beam_now(b,&start)) return -1;
    for (;;) {
        if (beam_now(b,&now) || now-start>timeout_ms) return -1;
        FD_ZERO(&set); FD_SET(b->live_out,&set); tv.tv_sec=0;tv.tv_usec=100000;
        n=select(b->live_out+1,&set,NULL,NULL,&tv);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) continue;
        n=(int)read(b->live_out,data+used,sizeof(data)-used-1U);
        if (n<=0) return -1;
        used+=(size_t)n; data[used]='\0';
        if (strstr(data,"BRIDGE_READY ")) { b->ready=1; return 0; }
        if (used==sizeof(data)-1U) return -1;
    }
}

static int beam_read_lines(Beam720 *b)
{
    unsigned char bytes[256]; ssize_t n; size_t i;
    while ((n=read(b->live_out,bytes,sizeof bytes))>0) for (i=0;i<(size_t)n;++i) {
        if (bytes[i]=='\n') {
            unsigned long long sequence,captured; unsigned slot,writer; char extra;
            uint32_t copy_ms=0,detect_ms=0; int result;
            b->line[b->line_used]='\0';
            if (!strncmp(b->line,"BRIDGE_READY",12)) { b->ready=1; b->line_used=0; continue; }
            if (!strncmp(b->line,"FRAME ",6)) {
                if (sscanf(b->line,"FRAME %llu %llu %u %u %c",&sequence,&captured,
                           &slot,&writer,&extra)!=4 || !sequence || slot>=3U || writer>=3U || slot==writer)
                    return -1;
                result=game_capture_owner_dispatch_image_parked(slot,writer,b->generation,sequence,
                    captured,beam_image_frame,b,&copy_ms,&detect_ms);
                if (result || dprintf(b->live_in,"FRAME_DONE\n")<0) return -1;
                /* ACK releases only the CPU lease. The worker requires a new
                 * START for each frame, after copy/detection/display succeed. */
                if (!deferred_exit && dprintf(b->live_in,"START\n")<0) return -1;
            }
            b->line_used=0;
        } else if (b->line_used+1U<sizeof b->line) b->line[b->line_used++]=(char)bytes[i];
        else return -1;
    }
    return n==0 || (n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK)?-1:0;
}

static void beam_stop_worker(Beam720 *b)
{
    int status;
    if (b->live_in>=0) { (void)dprintf(b->live_in,"STOP\n"); close(b->live_in); b->live_in=-1; }
    if (b->live_pid>0) { (void)waitpid(b->live_pid,&status,0); b->live_pid=0; }
    if (b->live_out>=0) { close(b->live_out); b->live_out=-1; }
}

static int beam720_run(unsigned seconds)
{
    Beam720 b; GameDisplayMode mode; uint64_t start,now; int result=1;
    int stop_result=GAME_DISPLAY_OK,session_result=GAME_DISPLAY_OK;
    GameBeamConfig config={GAME_BEAM_CONFIG_VERSION,1280,720,{32,500},{1,0},250,VISION_STABILITY_B,0,0,0,0};
    memset(&b,0,sizeof b); b.live_in=b.live_out=-1; b.calls=game_linux_system_calls();
    b.generation=1; b.frame=(VisionCanvas){NULL,1280,720,3840,2764800};
    b.frame.data=(uint8_t*)malloc(b.frame.capacity);
    if (!b.frame.data || !b.calls || signal(SIGINT,defer_exit)==SIG_ERR || signal(SIGTERM,defer_exit)==SIG_ERR)
        { fprintf(stderr,"BEAM_FAIL stage=allocate_or_signal\n"); goto done; }
    printf("BEAM_DISPLAY_PREPARE_BEGIN width=1280 height=720 stride=3840\n");
    fflush(stdout);
    game_display_init(&b.display); game_display_control_720p_mode(&mode);
    if (game_beam_init(&b.beam,&config,b.generation,0)!=GAME_BEAM_OK ||
        game_linux_live_session_open(&b.session)!=GAME_DISPLAY_OK ||
        game_linux_live_session_platform(&b.session,GAME_LINUX_LIVE_DISPLAY,&b.display_platform)!=GAME_DISPLAY_OK ||
        game_linux_live_session_platform(&b.session,GAME_LINUX_LIVE_CAPTURE,&b.capture_platform)!=GAME_DISPLAY_OK ||
        game_display_prepare_continuous(&b.display,&mode,&b.display_platform,&b.frame)!=GAME_DISPLAY_OK)
        { fprintf(stderr,"BEAM_FAIL stage=display_prepare\n"); goto done; }
    printf("BEAM_DISPLAY_PREPARED buffers=3 stride=5760 hsize=3840 vsize=720\n");
    fflush(stdout);
    if (game_capture_owner_prepare_with_platform(&b.capture_platform,&b.capture_virtual,&b.capture_physical))
        { fprintf(stderr,"BEAM_FAIL stage=capture_prepare\n"); goto done; }
    b.capture_owned=1;
    if (game_display_start(&b.display,500)!=GAME_DISPLAY_OK)
        { fprintf(stderr,"BEAM_FAIL stage=display_start\n"); goto done; }
    printf("BEAM_HDMI_STARTED cr=%08lx sr=%08lx\n",
           (unsigned long)b.display.last_control,(unsigned long)b.display.last_status);
    fflush(stdout);
    if (beam_spawn(&b)!=0)
        { fprintf(stderr,"BEAM_FAIL stage=capture_spawn\n"); goto done; }
    if (beam_wait_ready(&b,10000))
        { fprintf(stderr,"BEAM_FAIL stage=capture_ready\n"); goto done; }
    printf("BEAM_CAPTURE_READY\n");
    fflush(stdout);
    if (dprintf(b.live_in,"START\n")<0 || beam_now(&b,&start)) {
        fprintf(stderr,"BEAM_FAIL stage=capture_start\n");
        goto done;
    }
    while (!deferred_exit) {
        fd_set set; struct timeval tv; int n;
        if (beam_now(&b,&now)) {
            fprintf(stderr,"BEAM_FAIL stage=clock\n");
            goto done;
        }
        if (now-start>=(uint64_t)seconds*1000U) { result=0; break; }
        FD_ZERO(&set);FD_SET(b.live_out,&set);tv.tv_sec=0;tv.tv_usec=100000;
        n=select(b.live_out+1,&set,NULL,NULL,&tv);
        if (n<0 && errno==EINTR) continue;
        if (n<0) {
            fprintf(stderr,"BEAM_FAIL stage=capture_wait\n");
            goto done;
        }
        if (n>0 && beam_read_lines(&b)) {
            fprintf(stderr,"BEAM_FAIL stage=frame_dispatch\n");
            goto done;
        }
    }
    if (deferred_exit && b.first_frame) result=0;
done:
    if (!b.first_frame && !deferred_exit) {
        fprintf(stderr,"BEAM_NO_FRAME\n");
        result=1;
    }
    beam_stop_worker(&b);
    if (b.capture_owned) {
        while (!game_capture_owner_can_exit()) {
            if (game_capture_owner_release()==0) break;
            (void)b.capture_platform.wait_ms(b.capture_platform.context,100);
        }
        b.capture_owned=0;
    }
    if (!game_display_owner_can_exit(&b.display)) {
        stop_result=game_display_stop(&b.display,500);
        if (stop_result!=GAME_DISPLAY_OK) game_display_owner_drain(&b.display,500);
    }
    if (b.session.impl)
        session_result=game_linux_live_session_close(&b.session);
    if (stop_result!=GAME_DISPLAY_OK || session_result!=GAME_DISPLAY_OK ||
        !game_display_owner_can_exit(&b.display) || !game_capture_owner_can_exit() ||
        !game_linux_live_session_can_exit(&b.session)) result=1;
    printf("BEAM_SAFE_STOP result=%d run_result=%d session_close=%d owner_can_exit=%d capture_owner_can_exit=%d session_can_exit=%d frames=%u\n",
           stop_result,result,session_result,game_display_owner_can_exit(&b.display),
           game_capture_owner_can_exit(),game_linux_live_session_can_exit(&b.session),b.frame_count);
    fflush(stdout);
    free(b.frame.data);
    return result;
}
#endif
static int control_bmp(const char *path)
{
    GameDisplayMode mode;
    GameDisplayPlatform platform;
    GameLinuxDisplay display;
    VisionCanvas canvas;
    GameDisplayStatus result,stopped;
    FILE *file;
    int close_result;
    uint8_t *pixels=malloc(2764800);
    if (!pixels) return 1;
    canvas=(VisionCanvas){pixels,1280,720,3840,2764800};
    file=fopen(path,"rb");
    if (!file) { free(pixels); return 1; }
    result=game_display_read_control_bmp(file,&canvas);
    close_result=fclose(file);
    if (result!=GAME_DISPLAY_OK || close_result) { free(pixels); return 1; }
    printf("CONTROL_FILE_OK width=1280 height=720 BGR24 row=3840 bytes=2764800\n");
    game_display_init(&display);
    game_display_control_720p_mode(&mode);
    game_display_linux_platform(&platform);
    /* A catchable request defers exit until halt/cleanup. SIGKILL/power loss
     * cannot be made transactional by userspace and are not recovery tests. */
    if (signal(SIGINT,defer_exit)==SIG_ERR || signal(SIGTERM,defer_exit)==SIG_ERR) {
        free(pixels); return 1;
    }
    result=deferred_exit?GAME_DISPLAY_IO:
        game_display_prepare(&display,&mode,&platform,&canvas);
    free(pixels); /* independent CPU source; never the DMA allocation */
    if (result==GAME_DISPLAY_OK && !deferred_exit) result=game_display_start(&display,500);
    if (result==GAME_DISPLAY_OK && !deferred_exit) {
        printf("CONTROL_SCAN_READY cr=%08lx sr=%08lx physical=%08lx span=%lu "
               "pixel_candidate=74285714 rational=5200000000/70 duration_ms=20000\n",
               (unsigned long)display.last_control,(unsigned long)display.last_status,
               (unsigned long)display.physical,(unsigned long)display.span);
        fflush(stdout);
        result=game_display_observe(&display,20000,500);
    }
    stopped=game_display_stop(&display,500);
    printf("CONTROL_STOP result=%u stop=%u cr=%08lx sr=%08lx owner_can_exit=%d signal=%d\n",
           result,stopped,(unsigned long)display.last_control,(unsigned long)display.last_status,
           game_display_owner_can_exit(&display),(int)deferred_exit);
    fflush(stdout);
    if (!game_display_owner_can_exit(&display)) {
        fputs("OWNER_RETAINED: no global reset, no release/exit while state is uncertain\n",stderr);
        fflush(stderr);
        game_display_owner_drain(&display,500);
    }
    return result==GAME_DISPLAY_OK && stopped==GAME_DISPLAY_OK && !deferred_exit?0:1;
}

/* Same CPU canvas as the existing menu. Fixed demo asset sizes are a file
 * contract, not a second game configuration or a DMA allocation scheme. */
static int load_asset(const char *directory,const char *name,VisionCanvas *c,int w,int h)
{
    char path[4096];
    FILE *f;
    GameRenderStatus status;
    int n=snprintf(path,sizeof path,"%s/%s",directory,name);
    if (n<0 || (size_t)n>=sizeof path) return 0;
    c->width=w; c->height=h; c->stride=(size_t)w*3; c->capacity=c->stride*(size_t)h;
    c->data=(uint8_t *)malloc(c->capacity);
    if (!c->data) return 0;
    f=fopen(path,"rb");
    if (!f) { fprintf(stderr,"Cannot read asset: %s\n",path); return 0; }
    status=game_render_read_bgr(f,c);
    if (fclose(f)!=0) status=GAME_RENDER_IO_ERROR;
    if (status!=GAME_RENDER_OK) fprintf(stderr,"Invalid BGR asset: %s\n",path);
    return status==GAME_RENDER_OK;
}

static int pose_command(char *line,int values[3])
{
    char *p=line,*end;
    int i;
    for (i=0;i<3;++i) {
        long value;
        errno=0; value=strtol(p,&end,10);
        if (end==p || errno==ERANGE || value<INT_MIN || value>INT_MAX) return 0;
        values[i]=(int)value; p=end;
        if (i<2 && !isspace((unsigned char)*p)) return 0;
    }
    while (isspace((unsigned char)*p)) ++p;
    return !*p && (values[2]==0 || values[2]==90);
}

static int sprite_replay(const char *assets,const char *replay,const char *output)
{
    VisionCanvas background={0},poses[2]={{0},{0}},canvas={0};
    FILE *commands=NULL;
    char line[256],path[4096];
    unsigned frames=0;
    int result=1;
    if (!load_asset(assets,"background.bgr",&background,1280,800) ||
        !load_asset(assets,"mirror_000.bgr",&poses[0],128,128) ||
        !load_asset(assets,"mirror_090.bgr",&poses[1],128,128)) goto done;
    canvas=(VisionCanvas){NULL,1280,800,GAME_DISPLAY_STRIDE,GAME_DISPLAY_SPAN};
    canvas.data=(uint8_t *)calloc(1,canvas.capacity);
    commands=fopen(replay,"r");
    if (!canvas.data || !commands) goto done;
    while (fgets(line,sizeof line,commands)) {
        FILE *frame;
        int values[3],n,ok;
        char *p=line;
        while (isspace((unsigned char)*p)) ++p;
        if (!*p || *p=='#') continue;
        if (!pose_command(p,values)) { fputs("Invalid replay: expected x y pose(0|90)\n",stderr); goto done; }
        /* Restore cached background each update. No asset reads inside this loop,
         * no retained dirty rectangles, no active scan-buffer mutation. */
        if (game_render_blit(&background,&canvas,0,0,0,0)!=GAME_RENDER_OK ||
            game_render_blit(&poses[values[2]==90],&canvas,values[0],values[1],1,0xFF00FFU)!=GAME_RENDER_OK)
            goto done;
        n=snprintf(path,sizeof path,"%s/frame_%03u.ppm",output,frames);
        if (n<0 || (size_t)n>=sizeof path) goto done;
        frame=fopen(path,"wb");
        if (!frame) goto done;
        ok=game_render_write_ppm(&canvas,frame)==GAME_RENDER_OK;
        if (fclose(frame)!=0) ok=0;
        if (!ok) goto done;
        printf("SPRITE_CPU_FRAME frame=%u x=%d y=%d pose=%d\n",frames,values[0],values[1],values[2]);
        if (++frames==UINT_MAX) goto done;
    }
    if (ferror(commands) || !frames) goto done;
    printf("SPRITE_CPU_CHECK assets_loaded=3 background_loads=1 frames=%u "
           "width=1280 height=800 BGR888 stride=5760 span=4608000 HDMI=UNVERIFIED\n",frames);
    result=0;
done:
    if (commands && fclose(commands)!=0) result=1;
    free(canvas.data); free(background.data); free(poses[0].data); free(poses[1].data);
    return result;
}


/* File/geometry check only: synthetic dispatch times deliberately exclude any
 * runtime-freshness or hardware claim. Runtime --photos720 uses real clock. */
static int photo_check(const char *directory,const char *pack,const char *output)
{
    GamePhotoInput photos={0};
    GameRenderAssets assets={0};
    VisionCanvas canvas={NULL,1280,800,3840,3072000};
    GameLoop loop;
    unsigned level;
    int result=1;
    canvas.data=malloc(canvas.capacity);
    if (!canvas.data || !game_photo_load(&photos,directory) ||
        game_render_assets_load(&assets,pack,&game_default_config,&game_default_render_config)!=GAME_RENDER_OK ||
        game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,
                       &game_default_menu_layout)!=GAME_OK) goto done;
    puts("PHOTO_CHECK file_input=1 camera=isolated geometry_only=1 synthetic_time=1 no_start=1");
    for (level=1;level<=3;++level) {
        GameLoopEvent e;
        GameLoopOutput view;
        GameCaptureStamp stamp;
        GameRenderStatus rendered;
        char path[4096],label[96];
        FILE *f;
        int n,ok;
        uint64_t now=level*1000U;
        memset(&e,0,sizeof e); e.kind=GAME_LOOP_MENU;
        e.data.menu=(GameMenuAction){GAME_MENU_SELECT,level};
        if (game_loop_step(&loop,now,&e,&view)!=GAME_OK) goto done;
        e.kind=GAME_LOOP_DISPATCH; e.data.dispatch.sequence=level; e.data.dispatch.captured_ms=now;
        if (game_loop_step(&loop,now,&e,&view)!=GAME_OK || !view.has_stamp) goto done;
        stamp=view.stamp; e.kind=GAME_LOOP_DETECTION;
        if (!game_photo_detect(&photos,level,stamp,&e.data.detection) ||
            !game_photo_write(&e.data.detection,level,stdout)) goto done;
        if (game_loop_step(&loop,now,&e,&view)!=GAME_OK ||
            !view.game.scene_valid || game_app_write_view(&loop.app,&view.game,stdout)) goto done;
        (void)snprintf(label,sizeof label,"PHOTO %03u | FILE INPUT | GEOMETRY CHECK",74+level);
        rendered=game_render_cached_source(&view,&game_default_config,&game_default_menu_layout,
                         &game_default_render_config,&assets,&canvas,label);
        if (rendered!=GAME_RENDER_OK && rendered!=GAME_RENDER_FULL_RAY) goto done;
        n=snprintf(path,sizeof path,"%s/photo_%03u.ppm",output,74+level);
        if (n<0 || (size_t)n>=sizeof path || !(f=fopen(path,"wb"))) goto done;
        ok=game_render_write_ppm(&canvas,f)==GAME_RENDER_OK;
        if (fclose(f)) ok=0;
        if (!ok) goto done;
    }
    result=0;
done:
    game_photo_close(&photos); game_render_assets_free(&assets); free(canvas.data);
    return result;
}

#if defined(__linux__)
typedef struct {
    GameLoop loop;
    GameLinuxIO input;
    GamePump pump;
    GameLinuxDisplay display;
    GameRenderAssets assets;
    VisionCanvas logical, fitted;
    const GameLinuxCalls *calls;
    uint64_t end_ms,last_draw_ms,last_log_ms,menu_begin_ms,compose_ms,compose_max_ms;
    unsigned compositions;
    unsigned frames,level_changes;
    int error,have_view;
    GameLoopOutput previous;
    GamePhotoInput photos;
    int photo_mode,photo_log;
    uint64_t photo_sequence,photo_generation,next_photo_ms,detect_ms;
    GameDetectionFrame photo_frame;
    int live_mode,live_in,live_out,live_pid,live_pending,live_ready,live_inflight;
    size_t live_line_used;
    char live_line[256];
    GameLinuxLiveSession live_session;
    GameDisplayPlatform capture_platform;
    uint64_t live_generation,live_sequence;
    VisionDetection live_detections[VISION_MAX_DETECTIONS];
    GameDetectionFrame live_frame;
    int live_capture_owned,live_display_prepared;
    uint64_t live_virtual,live_physical;
} Menu720;
static int menu720_now(Menu720 *a,uint64_t *now)
{
    if (a->calls->clock_ms(a->calls->context,now)) { a->error=1; return -1; }
    return 0;
}
static int menu720_stopping(void *context)
{
    Menu720 *a=context;
    uint64_t now;
    return deferred_exit || a->error || menu720_now(a,&now) || now>=a->end_ms;
}
static int menu720_render(Menu720 *a,const GameLoopOutput *view)
{
    uint64_t began,ended;
    GameRenderStatus s;
    int failed;
    char label[96];
    const char *source=NULL;
    if (menu720_now(a,&began)) return 1;
    if (a->photo_mode) {
        if (view->game.level_id) (void)snprintf(label,sizeof label,"PHOTO %03u | FILE INPUT | NO CAMERA",74+view->game.level_id);
        else (void)snprintf(label,sizeof label,"PHOTO 075 / 076 / 077 | FILE INPUT | NO CAMERA");
        source=label;
    }
    s=game_render_cached_source(view,&game_default_config,&game_default_menu_layout,
                                         &game_default_render_config,&a->assets,&a->logical,source);
    failed=(s!=GAME_RENDER_OK && s!=GAME_RENDER_FULL_RAY) ||
           game_render_fit_720p(&a->logical,&a->fitted)!=GAME_RENDER_OK;
    if (menu720_now(a,&ended)) return 1;
    ++a->compositions; a->compose_ms+=ended-began;
    if (ended-began>a->compose_max_ms) a->compose_max_ms=ended-began;
    return failed;
}
static int menu720_photo_result(void *context,GameDetectionFrame *frame)
{
    Menu720 *a=context;
    GameSnapshot view;
    GameLoopEvent event;
    GameLoopOutput dispatched;
    uint64_t began,ended;
    if (a->error) return 0;
    if (menu720_now(a,&began) || game_app_snapshot(&a->loop.app,&view)!=GAME_OK) return -1;
    if ((view.state!=GAME_PREPARING && view.state!=GAME_RUNNING) || began>=a->end_ms ||
        (view.generation==a->photo_generation && began<a->next_photo_ms)) return 0;
    memset(&event,0,sizeof event); event.kind=GAME_LOOP_DISPATCH;
    event.data.dispatch.sequence=++a->photo_sequence; event.data.dispatch.captured_ms=began;
    if (game_pump_event(&a->pump,&event,&dispatched)!=GAME_OK || !dispatched.has_stamp ||
        !game_photo_detect(&a->photos,view.level_id,dispatched.stamp,frame) || menu720_now(a,&ended)) return -1;
    a->detect_ms=ended-began; a->next_photo_ms=ended+10;
    if (a->detect_ms>game_default_config.scene_max_age_ms) {
        printf("PHOTO_DETECTION_EXPIRED age_ms=%llu ttl_ms=%llu STOP_NO_RETRY\n",
               (unsigned long long)a->detect_ms,(unsigned long long)game_default_config.scene_max_age_ms);
        fflush(stdout); a->error=1;
    }
    a->photo_log=view.generation!=a->photo_generation;
    a->photo_generation=view.generation; a->photo_frame=*frame;
    return 1;
}
static int menu720_live_request(Menu720 *a)
{
    GameSnapshot view;
    if (!a || !a->live_mode || !a->live_ready || a->live_inflight || a->live_pending) return 0;
    if (game_app_snapshot(&a->loop.app,&view)!=GAME_OK) return -1;
    if (!view.generation || (view.state!=GAME_PREPARING && view.state!=GAME_RUNNING)) return 0;
    if (dprintf(a->live_in,"START\n")<0) return -1;
    a->live_generation=view.generation;a->live_inflight=1;return 0;
}
static int menu720_live_frame(void *context,GameDetectionFrame *frame)
{
    Menu720 *a=context;
    if (!a || !frame || frame->count<0 || frame->count>VISION_MAX_DETECTIONS || a->live_pending) return -1;
    if (frame->count) memcpy(a->live_detections,frame->detections,
                             (size_t)frame->count*sizeof(*a->live_detections));
    a->live_frame=*frame; a->live_frame.detections=a->live_detections;
    {
        int i;
        for (i=0;i<frame->count;++i) {
            const VisionDetection *d=&frame->detections[i];
            printf("LIVE_DETECTION sequence=%llu type=%d x=%.3f y=%.3f angle=%d confidence=%d\n",
                   (unsigned long long)frame->stamp.sequence,(int)d->type,
                   (double)d->geometry_center_x,(double)d->geometry_center_y,d->angle_deg,d->confidence_percent);
        }
    }
    a->live_pending=1;
    return 0;
}
static int menu720_live_result(void *context,GameDetectionFrame *frame)
{
    Menu720 *a=context;
    if (!a || !frame || !a->live_pending) return 0;
    *frame=a->live_frame; a->live_pending=0;
    if (menu720_live_request(a)) return -1;
    return 1;
}
static int menu720_live_line(Menu720 *a,const char *line)
{
    unsigned long long sequence,captured;
    unsigned slot,writer;
    char extra;
    if (!strncmp(line,"BRIDGE_READY",12)) { a->live_ready=1; return 0; }
    if (!strncmp(line,"FRAME ",6)) {
        GameSnapshot view; uint32_t copy_ms=0,detect_ms=0; int n;
        if (sscanf(line,"FRAME %llu %llu %u %u %c",&sequence,&captured,&slot,&writer,&extra)!=4 ||
            !sequence || sequence<=a->live_sequence || slot>=3U || writer>=3U || slot==writer) return -1;
        if (!a->live_ready || !a->live_inflight || a->live_pending || game_app_snapshot(&a->loop.app,&view)!=GAME_OK) return -1;
        a->live_inflight=0;
        a->live_sequence=sequence;
        n=game_capture_owner_dispatch_parked(slot,writer,a->live_generation,sequence,captured,
                                      menu720_live_frame,a,&copy_ms,&detect_ms);
        if (n || dprintf(a->live_in,"FRAME_DONE\n")<0) return -1;
        a->detect_ms=(uint64_t)copy_ms+detect_ms;
        printf("NATIVE_LIVE_FRAME sequence=%llu captured_ms=%llu slot=%u writer=%u copy_ms=%u detect_ms=%u count=%d\n",
               sequence,captured,slot,writer,copy_ms,detect_ms,a->live_frame.count);fflush(stdout);
        return 0;
    }
    return 0;
}
static int menu720_live_wake(void *context)
{
    Menu720 *a=context; unsigned char bytes[256]; ssize_t n; size_t i;
    if (!a || a->live_out<0) return -1;
    while ((n=read(a->live_out,bytes,sizeof bytes))>0) for (i=0;i<(size_t)n;++i) {
        if (bytes[i]=='\n') {
            char line[256]; size_t length=a->live_line_used;
            if (length>=sizeof line) return -1;
            memcpy(line,a->live_line,length); line[length]='\0'; a->live_line_used=0;
            if (menu720_live_line(a,line)) return -1;
        } else if (a->live_line_used+1U<sizeof a->live_line) a->live_line[a->live_line_used++]=(char)bytes[i];
        else return -1;
    }
    return n==0 || (n<0 && (errno!=EAGAIN && errno!=EWOULDBLOCK)) ? -1 : 0;
}
#if defined(__linux__)
static int menu720_live_spawn(Menu720 *a)
{
    int in_pipe[2],out_pipe[2]; pid_t pid; char physical[32],span[32];
    if (!a || pipe(in_pipe)) return -1;
    if (pipe(out_pipe)) { close(in_pipe[0]);close(in_pipe[1]);return -1; }
    snprintf(physical,sizeof physical,"%llu",(unsigned long long)a->live_physical);
    snprintf(span,sizeof span,"%u",GAME_CAPTURE_FRAME_SPAN);
    pid=fork();
    if (pid<0) { close(in_pipe[0]);close(in_pipe[1]);close(out_pipe[0]);close(out_pipe[1]);return -1; }
    if (!pid) {
        char *const argv[]={(char*)"python3",(char*)"-B",
            (char*)"/run/game_live_camera/capture/capture_worker.py",(char*)"--game-bridge",
            (char*)"--bridge-physical",physical,(char*)"--bridge-span",span,NULL};
        dup2(in_pipe[0],STDIN_FILENO);dup2(out_pipe[1],STDOUT_FILENO);
        close(in_pipe[0]);close(in_pipe[1]);close(out_pipe[0]);close(out_pipe[1]);
        execv("/usr/bin/python3",argv);_exit(127);
    }
    close(in_pipe[0]);close(out_pipe[1]);
    a->live_in=in_pipe[1];a->live_out=out_pipe[0];a->live_pid=pid;
    fcntl(a->live_out,F_SETFL,fcntl(a->live_out,F_GETFL,0)|O_NONBLOCK);
    return 0;
}
static int menu720_live_wait_ready(Menu720 *a,unsigned timeout_ms)
{
    uint64_t start,now; char line[256]; size_t used=0; struct timeval tv; fd_set set; int n;
    if (!a || a->live_out<0 || a->calls->clock_ms(a->calls->context,&start)) return -1;
    for (;;) {
        if (a->calls->clock_ms(a->calls->context,&now) || now-start>timeout_ms) return -1;
        FD_ZERO(&set);FD_SET(a->live_out,&set);tv.tv_sec=0;tv.tv_usec=100000;
        n=select(a->live_out+1,&set,NULL,NULL,&tv);if(n<0 && errno==EINTR)continue;if(n<=0)continue;
        n=(int)read(a->live_out,line+used,sizeof(line)-used-1U);if(n<=0)return -1;used+=(size_t)n;line[used]='\0';
        if (strstr(line,"BRIDGE_READY ")) { a->live_ready=1;return 0; }
    }
}
static void menu720_live_stop(Menu720 *a)
{
    int status;
    if (!a) return;
    if (a->live_in>=0) { (void)dprintf(a->live_in,"STOP\n");close(a->live_in);a->live_in=-1; }
    if (a->live_pid>0) { (void)waitpid(a->live_pid,&status,0);a->live_pid=0; }
    if (a->live_out>=0) { close(a->live_out);a->live_out=-1; }
}
#else
static int menu720_live_spawn(Menu720 *a){(void)a;return -1;}
static int menu720_live_wait_ready(Menu720 *a,unsigned timeout_ms){(void)a;(void)timeout_ms;return -1;}
static void menu720_live_stop(Menu720 *a){(void)a;}
#endif
static int menu720_same(const GameLoopOutput *a,const GameLoopOutput *b)
{
    return a->game.state==b->game.state && a->game.generation==b->game.generation &&
        a->game.scene_sequence==b->game.scene_sequence && a->game.ready==b->game.ready &&
        a->game.scene_valid==b->game.scene_valid && a->game.stars==b->game.stars &&
        a->game.remaining_ms/1000==b->game.remaining_ms/1000 &&
        a->menu.x==b->menu.x && a->menu.y==b->menu.y &&
        a->menu.connected==b->menu.connected && a->menu.left_down==b->menu.left_down;
}
static void menu720_publish(void *context,const GamePumpOutput *out)
{
    Menu720 *a=context;
    uint64_t now;
    if (a->error || menu720_now(a,&now)) return;
    if (menu720_live_request(a)) { a->error=1;return; }
    if (a->have_view && menu720_same(&a->previous,&out->view)) return;
    if (menu720_render(a,&out->view) ||
        game_display_update(&a->display,&a->fitted,500)!=GAME_DISPLAY_OK) { a->error=1; return; }
    if (a->have_view && out->view.game.generation!=a->previous.game.generation) ++a->level_changes;
    if (a->photo_mode && (a->photo_log || !a->have_view ||
        a->previous.game.state!=out->view.game.state || a->previous.game.scene_valid!=out->view.game.scene_valid)) {
        printf("PHOTO_RUNTIME dispatch_age_ms=%llu ttl_ms=%llu exposure_freshness=NOT_CLAIMED file_reprocessed=1\n",
               (unsigned long long)a->detect_ms,(unsigned long long)game_default_config.scene_max_age_ms);
        if (a->photo_log) game_photo_write(&a->photo_frame,out->view.game.level_id,stdout);
        game_app_write_view(&a->loop.app,&out->view.game,stdout); a->photo_log=0;
    }
    if (a->live_mode) game_app_write_view(&a->loop.app,&out->view.game,stdout);
    a->previous=out->view; a->have_view=1; a->last_draw_ms=now; ++a->frames;
    if (now-a->last_log_ms>=1000 || out->view.game.generation!=a->previous.game.generation) {
    a->last_log_ms=now;
    printf("NATIVE_MENU_FRAME frames=%u level=%u generation=%llu mouse=%d,%d connected=%d ready=%d\n",
           a->frames,out->view.game.level_id,(unsigned long long)out->view.game.generation,
           out->view.menu.x,out->view.menu.y,out->view.menu.connected,out->view.game.ready);
    fflush(stdout);
    }
}
static int interactive720(const char *mouse,const char *pack,unsigned seconds,const char *control,const char *photo_directory,int live_mode)
{
    Menu720 a;
    GameLoopOutput initial;
    GamePumpOutput output;
    GameDisplayMode mode;
    GameDisplayPlatform platform;
    GameLinuxHooks hooks;
    GamePumpIO io;
    GamePumpStatus pump_status=GAME_PUMP_IO_ERROR;
    GameDisplayStatus stopped;
    uint64_t now;
    int result=1,input_open=0;
    memset(&a,0,sizeof a); a.live_in=a.live_out=-1; a.live_pid=0; a.live_mode=live_mode;
    game_display_init(&a.display); a.calls=game_linux_system_calls();
    if (signal(SIGINT,defer_exit)==SIG_ERR || signal(SIGTERM,defer_exit)==SIG_ERR) goto done;
    /* Zero is reserved for the explicit service entry; bounded CLI modes keep
     * their existing limits. The service still stops through the same drain. */
    if (!a.calls || (seconds && (seconds<5 || seconds>180))) return 2;
    a.photo_mode=photo_directory!=NULL;
    if (a.photo_mode && !game_photo_load(&a.photos,photo_directory)) goto done;
    a.logical=(VisionCanvas){NULL,1280,800,3840,3072000};
    a.fitted=(VisionCanvas){NULL,1280,720,3840,2764800};
    a.logical.data=malloc(a.logical.capacity); a.fitted.data=malloc(a.fitted.capacity);
    if (!a.logical.data || !a.fitted.data ||
        game_render_assets_load(&a.assets,pack,&game_default_config,&game_default_render_config)!=GAME_RENDER_OK)
        goto done;
    if (game_loop_init(&a.loop,&game_default_config,&game_uncalibrated_identity_mapping,
                       &game_default_menu_layout)!=GAME_OK ||
        game_loop_step(&a.loop,0,NULL,&initial)!=GAME_OK || menu720_render(&a,&initial)) goto done;
    hooks=(GameLinuxHooks){&a,live_mode?menu720_live_result:a.photo_mode?menu720_photo_result:NULL,
                           menu720_stopping,menu720_publish,live_mode?menu720_live_wake:NULL};
    game_display_control_720p_mode(&mode);
    if (live_mode) {
        if (signal(SIGPIPE,SIG_IGN)==SIG_ERR) goto done;
        if (game_linux_live_session_open(&a.live_session)!=GAME_DISPLAY_OK ||
            game_linux_live_session_platform(&a.live_session,GAME_LINUX_LIVE_DISPLAY,&platform)!=GAME_DISPLAY_OK ||
            game_linux_live_session_platform(&a.live_session,GAME_LINUX_LIVE_CAPTURE,&a.capture_platform)!=GAME_DISPLAY_OK ||
            game_display_prepare_continuous(&a.display,&mode,&platform,&a.fitted)!=GAME_DISPLAY_OK)
            goto done;
        {
            int capture_result=game_capture_owner_prepare_with_platform(&a.capture_platform,&a.live_virtual,&a.live_physical);
            a.live_capture_owned=!game_capture_owner_can_exit();
            if (capture_result) goto done;
        }
        a.live_capture_owned=1;
        if (game_display_start(&a.display,500)!=GAME_DISPLAY_OK || menu720_live_spawn(&a)!=0 ||
            menu720_live_wait_ready(&a,10000)) goto done;
        a.live_display_prepared=1;
    }
    if (!game_linux_io_init(&a.input,a.calls,&hooks,live_mode?a.live_out:-1)) goto done;
    if (!game_linux_io_open(&a.input,mouse)) { fprintf(stderr,"INPUT_OPEN_FAILED error=%d\n",a.input.error); goto done; }
    input_open=1; io=game_linux_pump_io(&a.input);
    if (!game_pump_init(&a.pump,&a.loop,&game_default_pump_config,a.input.layout,&io)) goto done;
    if (signal(SIGINT,defer_exit)==SIG_ERR || signal(SIGTERM,defer_exit)==SIG_ERR) goto done;
    if (control) {
        FILE *f=fopen(control,"rb");
        GameDisplayStatus loaded=f?game_display_read_control_bmp(f,&a.fitted):GAME_DISPLAY_IO;
        if (f && fclose(f)) loaded=GAME_DISPLAY_IO;
        if (loaded!=GAME_DISPLAY_OK) goto done;
    }
    if (!live_mode && (game_display_linux_platform(&platform),
        game_display_prepare_continuous(&a.display,&mode,&platform,&a.fitted)!=GAME_DISPLAY_OK ||
        game_display_start(&a.display,500)!=GAME_DISPLAY_OK)) goto done;
    if (menu720_now(&a,&now)) goto done;
    a.end_ms=seconds?now+(uint64_t)seconds*1000:UINT64_MAX;
    printf("NATIVE_MENU_CONTINUOUS_STARTED seconds=%u buffers=3 CR=%08lx cacheable=0\n",seconds,(unsigned long)a.display.last_control);fflush(stdout);
    if (control) {
        unsigned image;
        for (image=0;image<6;++image) {
            uint64_t until=now+650;
            size_t k;
            struct timespec pause={0,20000000};
            do {
                if (deferred_exit || game_display_status(&a.display)!=GAME_DISPLAY_OK || menu720_now(&a,&now) || now>=a.end_ms) goto done;
                if (nanosleep(&pause,NULL) && errno!=EINTR) goto done;
            } while (now<until);
            for (k=0;k<a.fitted.capacity;++k) a.fitted.data[k]^=255U;
            if (game_display_update(&a.display,&a.fitted,500)!=GAME_DISPLAY_OK) goto done;
            printf("NATIVE_MENU_STATIC_SWITCH n=%u slot=%u park=%08lx events=%u cr=%08lx sr=%08lx\n",image+1,a.display.current_slot,(unsigned long)a.display.last_park,a.display.fresh_frame_events,(unsigned long)a.display.last_control,(unsigned long)a.display.last_status);fflush(stdout);
            if (menu720_now(&a,&now)) goto done;
        }
        if (menu720_render(&a,&initial) || game_display_update(&a.display,&a.fitted,500)!=GAME_DISPLAY_OK || menu720_now(&a,&now)) goto done;
    }
    a.menu_begin_ms=now; a.last_draw_ms=now; a.last_log_ms=now; a.previous=initial; a.have_view=1; a.frames=1;
    printf("NATIVE_MENU_720_READY logical=1280x800 viewport=1152x720+64 duration_s=%u camera=%s input=%s\n",seconds,live_mode?"live":"isolated",live_mode?"live_C_detector":a.photo_mode?"photo_C_detector":"no_detection_injection");
    fflush(stdout);
    pump_status=game_pump_run(&a.pump,&output);
    if (pump_status==GAME_PUMP_STOP && !a.error && (!deferred_exit || !seconds)) result=0;
done:
    if (input_open) game_linux_io_close(&a.input);
    if (live_mode) menu720_live_stop(&a);
    if (a.menu_begin_ms && menu720_now(&a,&now)==0 && now>a.menu_begin_ms)
        printf("NATIVE_MENU_PERF presented_fps_x1000=%llu compose_avg_ms=%llu compose_max_ms=%llu compositions=%u submissions=%u fresh_events=%u last_park=%08lx\n",
          (unsigned long long)((uint64_t)a.frames*1000000/(now-a.menu_begin_ms)),
          (unsigned long long)(a.compositions?a.compose_ms/a.compositions:0),
          (unsigned long long)a.compose_max_ms,a.compositions,a.display.submitted,a.display.fresh_frame_events,(unsigned long)a.display.last_park);
    if (a.live_capture_owned) {
        while (!game_capture_owner_can_exit()) {
            if (game_capture_owner_release()!=0) {
                result=1;
                (void)a.capture_platform.wait_ms(a.capture_platform.context,100);
            }
        }
        a.live_capture_owned=0;
    }
    stopped=game_display_stop(&a.display,500);
    printf("NATIVE_MENU_720_STOP result=%d pump=%d stop=%u frames=%u level_changes=%u cr=%08lx sr=%08lx owner_can_exit=%d\n",
           result,(int)pump_status,stopped,a.frames,a.level_changes,
           (unsigned long)a.display.last_control,(unsigned long)a.display.last_status,
           game_display_owner_can_exit(&a.display));
    fflush(stdout);
    if (!game_display_owner_can_exit(&a.display)) game_display_owner_drain(&a.display,500);
    if (live_mode && game_linux_live_session_close(&a.live_session)!=GAME_DISPLAY_OK) result=1;
    game_photo_close(&a.photos); game_render_assets_free(&a.assets); free(a.logical.data); free(a.fitted.data);
    return result || stopped!=GAME_DISPLAY_OK;
}
#endif

int main(int argc, char **argv)
{
    GameLoop loop;
    GameLoopOutput published, preserved;
    VisionCanvas canvas;
    uint8_t *pixels;
    uint32_t hash=2166136261U;
    size_t i;
#if defined(__linux__)
    if (argc==3 && strcmp(argv[1],"--beam720")==0) {
        char *end; unsigned long duration;
        errno=0; duration=strtoul(argv[2],&end,10);
        if (errno || end==argv[2] || *end || duration<5 || duration>180) return 2;
        return beam720_run((unsigned)duration);
    }
    if (argc==6 && strcmp(argv[1],"--photos720")==0) {
        char *end;
        unsigned long duration;
        errno=0; duration=strtoul(argv[5],&end,10);
        if (errno || end==argv[5] || *end || duration<10 || duration>120) return 2;
        return interactive720(argv[2],argv[3],(unsigned)duration,NULL,argv[4],0);
    }
    if (argc==6 && strcmp(argv[1],"--continuous720")==0) {
        char *end;
        unsigned long duration;
        errno=0; duration=strtoul(argv[5],&end,10);
        if (errno || end==argv[5] || *end || duration<10 || duration>45) return 2;
        return interactive720(argv[2],argv[3],(unsigned)duration,argv[4],NULL,0);
    }
    if (argc==4 && strcmp(argv[1],"--menu-service720")==0)
        return interactive720(argv[2],argv[3],0,NULL,NULL,0);
    if (argc==5 && strcmp(argv[1],"--menu720")==0) {
        char *end;
        unsigned long duration;
        errno=0; duration=strtoul(argv[4],&end,10);
        if (errno || end==argv[4] || *end || duration<5 || duration>180) return 2;
        return interactive720(argv[2],argv[3],(unsigned)duration,NULL,NULL,0);
    }
    if (argc==5 && strcmp(argv[1],"--live720")==0) {
        char *end; unsigned long duration;
        errno=0; duration=strtoul(argv[4],&end,10);
        if (errno || end==argv[4] || *end || duration<5 || duration>180) return 2;
        return interactive720(argv[2],argv[3],(unsigned)duration,NULL,NULL,1);
    }
#endif
    if (argc==5 && strcmp(argv[1],"--photo-check")==0) return photo_check(argv[2],argv[3],argv[4]);
    if (argc==3 && strcmp(argv[1],"--bmp720")==0) return control_bmp(argv[2]);
    if (argc==7 && strcmp(argv[1],"--assets")==0 && strcmp(argv[3],"--replay")==0 &&
        strcmp(argv[5],"--output")==0) return sprite_replay(argv[2],argv[4],argv[6]);
    if (argc==2 && strcmp(argv[1],"--display")==0) {
        if (game_display_linux_preflight()!=GAME_DISPLAY_UNQUALIFIED) return 1;
        fputs("BLOCKED: no qualified BIT/HWH + board pins/STA/CDC, verified panel timing, "
              "exclusive Linux clock/reset/HP profile, safe libcma close/cache or owner policy.\n"
              "No display/CMA/device operation performed.\n",stderr);
        return 3;
    }
    if (argc!=2 || strcmp(argv[1],"--check")!=0) {
        fputs("usage: game_linux_static_menu --check | --display\n"
              "       game_linux_static_menu --beam720 SECONDS\n"
              "       game_linux_static_menu --assets DIR --replay FILE --output DIR\n",stderr);
        return 2;
    }
    if (game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,
                       &game_default_menu_layout)!=GAME_OK ||
        game_loop_step(&loop,0,NULL,&published)!=GAME_OK) return 1;
    preserved=published;
    pixels=(uint8_t *)calloc(1,GAME_DISPLAY_SPAN);
    if (!pixels) return 1;
    canvas=(VisionCanvas){pixels,1280,800,GAME_DISPLAY_STRIDE,GAME_DISPLAY_SPAN};
    if (game_render(&published,&game_default_config,&game_default_menu_layout,
                    &game_default_render_config,&canvas)!=GAME_RENDER_OK ||
        memcmp(&published,&preserved,sizeof published)!=0) { free(pixels); return 1; }
    for (i=0;i<GAME_DISPLAY_SPAN;++i) { hash^=pixels[i]; hash*=16777619U; }
    printf("STATIC_MENU_CPU_CHECK renders=1 width=1280 height=800 BGR888 "
           "hsize=3840 stride=5760 span=4608000 hash=%08lx "
           "snapshot_unchanged=1 HDMI=UNVERIFIED\n",(unsigned long)hash);
    free(pixels);
    return 0;
}
