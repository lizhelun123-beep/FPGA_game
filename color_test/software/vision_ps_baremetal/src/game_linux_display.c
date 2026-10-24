#if defined(__linux__)
#define _POSIX_C_SOURCE 200809L
#endif
#include "game_linux_display.h"

#include <string.h>
#if defined(__linux__)
#include <errno.h>
#include <time.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

#define CR 0x00U
#define SR 0x04U
#define PARK 0x28U
#define VSIZE 0x50U
#define HSIZE 0x54U
#define STRIDE 0x58U
#define ADDRESS 0x5cU
#define RUN 1U
#define HALTED 1U
#define ERRORS 0x00000ff0U
#define FRAME_EVENT 0x00001000U
#define CONTINUOUS_RUN 0x00010001U /* threshold1,park,IRQ output masked,RS1 */
#define FRAME_SPAN_720 4147200U

static int control_720p(const GameDisplayMode *m)
{
    return m && m->width==1280 && m->height==720 && m->stride==5760 &&
        m->h_front==110 && m->h_sync==40 && m->h_back==220 &&
        m->v_front==5 && m->v_sync==5 && m->v_back==20 &&
        m->h_positive==1 && m->v_positive==1 && m->reference_hz==100000000 &&
        m->multiplier==52 && m->divider==7 && m->output_divider==2 &&
        m->pixel_hz==74285714 && m->axis_hz==142857132;
}

void game_display_control_720p_mode(GameDisplayMode *m)
{
    if (!m) return;
    *m=(GameDisplayMode){GAME_DISPLAY_VERSION,1280,720,5760,110,40,220,5,5,20,
        1,1,100000000,52,7,2,74285714,142857132,74000000,75000000,59000,61000,
        "CONTROL_720P_FIXED; sink acceptance is a board-test result"};
}

static uint32_t bmp_u32(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
GameDisplayStatus game_display_read_control_bmp(FILE *f,VisionCanvas *c)
{
    uint8_t h[54];
    unsigned row;
    if (!f || !vision_canvas_valid(c) || c->width!=1280 || c->height!=720)
        return GAME_DISPLAY_BAD_ARGUMENT;
    if (fread(h,1,sizeof h,f)!=sizeof h || h[0]!='B' || h[1]!='M' ||
        bmp_u32(h+2)!=2764854 || bmp_u32(h+6)!=0 || bmp_u32(h+10)!=54 ||
        bmp_u32(h+14)!=40 || bmp_u32(h+18)!=1280 || bmp_u32(h+22)!=720 ||
        h[26]!=1 || h[27] || h[28]!=24 || h[29] || bmp_u32(h+30)!=0 ||
        bmp_u32(h+34)!=2764800) return GAME_DISPLAY_BAD_ARGUMENT;
    for (row=0;row<720;++row)
        if (fread(c->data+(size_t)(719-row)*c->stride,1,3840,f)!=3840)
            return GAME_DISPLAY_IO;
    if (fgetc(f)!=EOF || ferror(f)) return GAME_DISPLAY_IO;
    return GAME_DISPLAY_OK;
}

GameDisplayStatus game_display_mode_valid(const GameDisplayMode *m)
{
    uint64_t h, v, clock, denominator, frame_divisor;
    if (!m) return GAME_DISPLAY_BAD_ARGUMENT;
    if (m->version!=GAME_DISPLAY_VERSION || m->width!=GAME_DISPLAY_WIDTH ||
        (m->height!=GAME_DISPLAY_HEIGHT && !control_720p(m)) ||
        m->stride!=GAME_DISPLAY_STRIDE ||
        !m->h_front || !m->h_sync || !m->h_back || !m->v_front ||
        !m->v_sync || !m->v_back || m->h_positive>1 || m->v_positive>1 ||
        !m->timing_evidence || !m->timing_evidence[0]) return GAME_DISPLAY_BAD_MODE;
    h=(uint64_t)m->width+m->h_front+m->h_sync+m->h_back;
    v=(uint64_t)m->height+m->v_front+m->v_sync+m->v_back;
    if (h>8191 || v>8191 || !m->reference_hz ||
        m->multiplier<2 || m->multiplier>64 || !m->divider || m->divider>106 ||
        !m->output_divider || m->output_divider>128) return GAME_DISPLAY_BAD_MODE;
    clock=(uint64_t)m->reference_hz*m->multiplier;
    if (clock<600000000ULL*m->divider || clock>1200000000ULL*m->divider)
        return GAME_DISPLAY_BAD_MODE;
    denominator=(uint64_t)m->divider*m->output_divider*5U;
    if (clock/denominator!=m->pixel_hz || m->pixel_hz<1 ||
        m->axis_hz<m->pixel_hz || !m->sink_pixel_min_hz ||
        m->sink_pixel_min_hz>m->sink_pixel_max_hz ||
        clock<(uint64_t)m->sink_pixel_min_hz*denominator ||
        clock>(uint64_t)m->sink_pixel_max_hz*denominator ||
        !m->sink_refresh_min_millihz ||
        m->sink_refresh_min_millihz>m->sink_refresh_max_millihz ||
        m->sink_refresh_max_millihz>1000000U)
        return GAME_DISPLAY_BAD_MODE;
    /* Compare the rational refresh without rounding it into the sink range.
     * Bounds above keep both products below UINT64_MAX. */
    frame_divisor=denominator*h*v;
    if (clock*1000U<(uint64_t)m->sink_refresh_min_millihz*frame_divisor ||
        clock*1000U>(uint64_t)m->sink_refresh_max_millihz*frame_divisor)
        return GAME_DISPLAY_BAD_MODE;
    return GAME_DISPLAY_OK;
}

void game_display_init(GameLinuxDisplay *d)
{
    if (d) memset(d,0,sizeof(*d));
}

static int platform_valid(const GameDisplayPlatform *p)
{
    return p && p->version==GAME_DISPLAY_VERSION && p->qualify && p->allocate &&
        p->release && p->flush && p->barrier && p->configure && p->output &&
        p->finish && p->read && p->write && p->now_ms && p->wait_ms &&
        p->acquire && p->close;
}

static GameDisplayStatus registers(GameLinuxDisplay *d)
{
    GameDisplayPlatform *p=&d->platform;
    if (p->read(p->context,CR,&d->last_control) ||
        p->read(p->context,SR,&d->last_status)) return GAME_DISPLAY_IO;
    return GAME_DISPLAY_OK;
}

static GameDisplayStatus prepare_abort(GameLinuxDisplay *d, GameDisplayStatus reason)
{
    /* No MM2S write has occurred. stop also closes a partial platform acquire.
     * Preserve the primary error; a retained state still requires owner_drain. */
    (void)game_display_stop(d,1);
    return reason;
}

static GameDisplayStatus prepare_frames(GameLinuxDisplay *d, const GameDisplayMode *m,
    const GameDisplayPlatform *p, const VisionCanvas *source,unsigned frames)
{
    GameDisplayStatus s;
    unsigned y;
    if (!d || !platform_valid(p) || !source) return GAME_DISPLAY_BAD_ARGUMENT;
    if (!game_display_owner_can_exit(d)) return GAME_DISPLAY_BAD_STATE;
    s=game_display_mode_valid(m);
    if (s!=GAME_DISPLAY_OK) return s;
    if (!vision_canvas_valid(source) || source->width!=(int)m->width ||
        source->height!=(int)m->height)
        return GAME_DISPLAY_BAD_ARGUMENT;
    if (p->qualify(p->context,m)) return GAME_DISPLAY_UNQUALIFIED;
    d->platform=*p;
    d->owner_active=1;
    d->state=GAME_DISPLAY_RETAINED;
    if (p->acquire(p->context)) return prepare_abort(d,GAME_DISPLAY_IO);
    s=registers(d);
    if (s!=GAME_DISPLAY_OK) return prepare_abort(d,s);
    if ((d->last_control&RUN) || !(d->last_status&HALTED))
        return prepare_abort(d,GAME_DISPLAY_BUSY);
    if (d->last_status&ERRORS) return prepare_abort(d,GAME_DISPLAY_DMA_ERROR);
    d->mode=*m;
    d->frame_span=(size_t)m->stride*m->height;
    d->frame_count=frames;
    d->span=d->frame_span*frames;
    if (p->allocate(p->context,d->span,&d->buffer,&d->physical)) {
        /* A failure with an unexpected pointer violates the callback contract.
         * Retain rather than lose its ownership or pass a sentinel to free. */
        if (d->buffer) { d->allocation_owned=1; return GAME_DISPLAY_IO; }
        return prepare_abort(d,GAME_DISPLAY_IO);
    }
    d->allocation_owned=1;
    d->state=GAME_DISPLAY_PREPARED;
    if (!d->buffer || (uintptr_t)d->buffer==UINTPTR_MAX) {
        /* A platform violated its allocation contract. Do not pass a failure
         * sentinel to a library's free routine, or discard the uncertain owner. */
        d->state=GAME_DISPLAY_RETAINED;
        return GAME_DISPLAY_BAD_ARGUMENT;
    }
    if (((uintptr_t)d->buffer&63U) || !d->physical || (d->physical&63U) ||
        d->physical>UINT32_MAX || d->span-1U>UINT32_MAX-d->physical) {
        return prepare_abort(d,GAME_DISPLAY_BAD_ARGUMENT);
    }
    memset(d->buffer,0,d->span); /* padding and the entire final row are owned */
    for (y=0;y<m->height*frames;++y)
        memcpy(d->buffer+(size_t)(y/m->height)*d->frame_span+(size_t)(y%m->height)*m->stride,
               source->data+(size_t)(y%m->height)*source->stride,GAME_DISPLAY_HSIZE);
    return GAME_DISPLAY_OK;
}

GameDisplayStatus game_display_prepare(GameLinuxDisplay *d,const GameDisplayMode *m,
    const GameDisplayPlatform *p,const VisionCanvas *source)
{ return prepare_frames(d,m,p,source,1); }
GameDisplayStatus game_display_prepare_continuous(GameLinuxDisplay *d,const GameDisplayMode *m,
    const GameDisplayPlatform *p,const VisionCanvas *source)
{ return prepare_frames(d,m,p,source,3); }

static GameDisplayStatus wait_state(GameLinuxDisplay *d, unsigned timeout, int halted)
{
    GameDisplayPlatform *p=&d->platform;
    uint64_t start, now, previous;
    unsigned count;
    GameDisplayStatus s;
    if (p->now_ms(p->context,&start)) return GAME_DISPLAY_IO;
    previous=start;
    /* Poll budget also bounds a broken/non-advancing injected clock. */
    for (count=0;count<=timeout;++count) {
        s=registers(d);
        if (s!=GAME_DISPLAY_OK) return s;
        if (halted) {
            if (!(d->last_control&RUN) && (d->last_status&HALTED)) return GAME_DISPLAY_OK;
        } else {
            if (d->last_status&ERRORS) return GAME_DISPLAY_DMA_ERROR;
            if ((d->last_control&RUN) && !(d->last_status&HALTED)) return GAME_DISPLAY_OK;
        }
        if (p->now_ms(p->context,&now) || now<previous) return GAME_DISPLAY_IO;
        previous=now;
        if (now-start>=timeout || count==timeout) break;
        if (p->wait_ms(p->context,1)) return GAME_DISPLAY_IO;
    }
    return GAME_DISPLAY_TIMEOUT;
}

GameDisplayStatus game_display_start(GameLinuxDisplay *d, unsigned timeout)
{
    GameDisplayPlatform *p;
    GameDisplayStatus s;
    uint32_t park;
    unsigned i;
    if (!d || !timeout || timeout>1000) return GAME_DISPLAY_BAD_ARGUMENT;
    if (d->state!=GAME_DISPLAY_PREPARED) return GAME_DISPLAY_BAD_STATE;
    p=&d->platform;
    s=registers(d);
    if (s!=GAME_DISPLAY_OK) return s;
    if ((d->last_control&RUN) || !(d->last_status&HALTED)) return GAME_DISPLAY_BUSY;
    if (d->last_status&ERRORS) return GAME_DISPLAY_DMA_ERROR;
    if (p->configure(p->context,&d->mode,timeout)) return GAME_DISPLAY_IO;
    d->configured=1;
    if (p->flush(p->context,d->buffer,d->physical,d->span) || p->barrier(p->context))
        return GAME_DISPLAY_IO;
    /* A failed write may have reached hardware: conservatively retain. */
    d->armed=1;
    d->state=GAME_DISPLAY_RETAINED;
    if (p->write(p->context,CR,d->frame_count==3?CONTINUOUS_RUN:RUN)) return GAME_DISPLAY_IO;
    if (p->read(p->context,PARK,&park) || p->write(p->context,PARK,park&~31U))
        return GAME_DISPLAY_IO;
    for (i=0;i<3;++i)
        if (p->write(p->context,ADDRESS+4U*i,(uint32_t)(d->physical+
            (d->frame_count==3?i*d->frame_span:0)))) return GAME_DISPLAY_IO;
    if (p->write(p->context,STRIDE,d->mode.stride) ||
        p->write(p->context,HSIZE,GAME_DISPLAY_HSIZE) || p->barrier(p->context) ||
        p->write(p->context,VSIZE,d->mode.height) || p->barrier(p->context))
        return GAME_DISPLAY_IO;
    if (p->output(p->context,1)) return GAME_DISPLAY_IO;
    s=wait_state(d,timeout,0);
    if (s==GAME_DISPLAY_OK) { d->state=GAME_DISPLAY_SCANNING; d->current_slot=0; ++d->submitted; }
    return s;
}

GameDisplayStatus game_display_status(GameLinuxDisplay *d)
{
    GameDisplayStatus s;
    if (!d || d->state!=GAME_DISPLAY_SCANNING) return GAME_DISPLAY_BAD_STATE;
    s=registers(d);
    if (s!=GAME_DISPLAY_OK) return s;
    if (d->last_status&ERRORS) return GAME_DISPLAY_DMA_ERROR;
    if (!(d->last_control&RUN) || (d->last_status&HALTED)) return GAME_DISPLAY_IO;
    return GAME_DISPLAY_OK;
}

static GameDisplayStatus halt_and_finish(GameLinuxDisplay *d, unsigned timeout)
{
    GameDisplayPlatform *p;
    GameDisplayStatus s;
    int output_error=0;
    if (!d || !timeout || timeout>1000) return GAME_DISPLAY_BAD_ARGUMENT;
    if (game_display_owner_can_exit(d)) return GAME_DISPLAY_OK;
    if (!d->owner_active || !platform_valid(&d->platform)) return GAME_DISPLAY_BAD_STATE;
    p=&d->platform;
    d->state=GAME_DISPLAY_RETAINED;
    if (d->armed) {
        /* Keep timing/clocks running while the last outstanding frame drains. */
        if (p->write(p->context,CR,0) || p->barrier(p->context)) return GAME_DISPLAY_IO;
        s=wait_state(d,timeout,1);
        if (s!=GAME_DISPLAY_OK) return s;
        d->armed=0;
    }
    if (d->configured) {
        output_error=p->output(p->context,0);
        if (output_error || p->finish(p->context)) return GAME_DISPLAY_IO;
        d->configured=0;
    }
    return GAME_DISPLAY_OK;
}

/* PG020 counts frame STARTS. Two fresh count events after observing the
 * newly parked current store guarantee a complete intervening free-run frame.
 * The requested store remains fixed;old stores cannot be read again. This is
 * deliberately stronger than a PARK write/readback or a stale IRQ flag.
 * PYNQ MM2S uses frame-count pacing and rotating frame stores;no reset/error
 * clearing is borrowed. CPU writes resume only after this retirement fence. */
static GameDisplayStatus retire_to(GameLinuxDisplay *d,unsigned target,unsigned timeout)
{
    GameDisplayPlatform *p=&d->platform;
    GameDisplayStatus s;
    uint64_t start,now,previous;
    uint32_t park;
    unsigned i,phase=0,events=0;
    if (p->now_ms(p->context,&start)) return GAME_DISPLAY_IO;
    previous=start;
    for (i=0;i<=timeout;++i) {
        s=game_display_status(d); if (s!=GAME_DISPLAY_OK) return s;
        if (p->read(p->context,PARK,&park)) return GAME_DISPLAY_IO;
        d->last_park=park;
        if ((park&31U)!=target) return GAME_DISPLAY_BAD_STATE;
        if (((park>>16)&31U)==target) {
            if (!phase || (phase==1 && (d->last_status&FRAME_EVENT))) {
                if (p->write(p->context,SR,FRAME_EVENT) || p->barrier(p->context)) return GAME_DISPLAY_IO;
                phase=1;
            } else if (phase==1) phase=2; /* observed W1C low before re-arm */
            else if (d->last_status&FRAME_EVENT) {
                ++events; ++d->fresh_frame_events;
                if (events==2) { d->current_slot=target; return GAME_DISPLAY_OK; }
                if (p->write(p->context,SR,FRAME_EVENT) || p->barrier(p->context)) return GAME_DISPLAY_IO;
                phase=1;
            }
        } else if (phase) return GAME_DISPLAY_BAD_STATE;
        if (p->now_ms(p->context,&now) || now<previous) return GAME_DISPLAY_IO;
        previous=now;
        if (now-start>=timeout || i==timeout) break;
        if (p->wait_ms(p->context,1)) return GAME_DISPLAY_IO;
    }
    return GAME_DISPLAY_TIMEOUT;
}
static GameDisplayStatus continuous_update(GameLinuxDisplay *d,const VisionCanvas *source,unsigned timeout)
{
    GameDisplayPlatform *p=&d->platform;
    GameDisplayStatus s;
    uint32_t park;
    unsigned slot=(d->current_slot+1)%3,y;
    uint8_t *dst=d->buffer+(size_t)slot*d->frame_span;
    s=game_display_status(d); if (s!=GAME_DISPLAY_OK) return s;
    if (p->read(p->context,PARK,&park)) return GAME_DISPLAY_IO;
    if ((park&31U)!=d->current_slot || ((park>>16)&31U)!=d->current_slot)
        return GAME_DISPLAY_BAD_STATE;
    memset(dst,0,d->frame_span);
    for (y=0;y<d->mode.height;++y)
        memcpy(dst+(size_t)y*d->mode.stride,source->data+(size_t)y*source->stride,GAME_DISPLAY_HSIZE);
    if (p->flush(p->context,dst,d->physical+(size_t)slot*d->frame_span,d->frame_span) ||
        p->barrier(p->context)) return GAME_DISPLAY_IO;
    if (p->write(p->context,PARK,(park&~31U)|slot) || p->barrier(p->context)) return GAME_DISPLAY_IO;
    ++d->submitted;
    return retire_to(d,slot,timeout);
}

GameDisplayStatus game_display_update(GameLinuxDisplay *d,const VisionCanvas *source,unsigned timeout)
{
    GameDisplayStatus s;
    uintptr_t a,b;
    unsigned y;
    if (!d || !source || !timeout || timeout>1000) return GAME_DISPLAY_BAD_ARGUMENT;
    if (d->state!=GAME_DISPLAY_SCANNING) return GAME_DISPLAY_BAD_STATE;
    if (!vision_canvas_valid(source) || source->width!=(int)d->mode.width ||
        source->height!=(int)d->mode.height) return GAME_DISPLAY_BAD_ARGUMENT;
    a=(uintptr_t)source->data; b=(uintptr_t)d->buffer;
    if (!b || source->capacity>UINTPTR_MAX-a || d->span>UINTPTR_MAX-b ||
        (a<b+d->span && b<a+source->capacity)) return GAME_DISPLAY_BAD_ARGUMENT;
    if (d->frame_count==3) {
        s=continuous_update(d,source,timeout);
        if (s!=GAME_DISPLAY_OK) d->state=GAME_DISPLAY_RETAINED;
        return s;
    }
    s=game_display_status(d);
    if (s!=GAME_DISPLAY_OK) return s;
    s=halt_and_finish(d,timeout);
    if (s!=GAME_DISPLAY_OK) return s; /* uncertain halt: no buffer mutation */
    memset(d->buffer,0,d->span);
    for (y=0;y<d->mode.height;++y)
        memcpy(d->buffer+(size_t)y*d->mode.stride,
               source->data+(size_t)y*source->stride,GAME_DISPLAY_HSIZE);
    d->state=GAME_DISPLAY_PREPARED;
    return game_display_start(d,timeout);
}

GameDisplayStatus game_display_stop(GameLinuxDisplay *d,unsigned timeout)
{
    GameDisplayStatus s;
    GameDisplayPlatform *p;
    s=halt_and_finish(d,timeout);
    if (s!=GAME_DISPLAY_OK || game_display_owner_can_exit(d)) return s;
    p=&d->platform;
    if (d->allocation_owned) {
        if (!d->buffer || (uintptr_t)d->buffer==UINTPTR_MAX) return GAME_DISPLAY_BAD_ARGUMENT;
        if (p->release(p->context,d->buffer)) return GAME_DISPLAY_IO;
        d->buffer=NULL;
        d->allocation_owned=0;
        d->physical=0;
    }
    if (p->close(p->context)) return GAME_DISPLAY_IO;
    d->owner_active=0;
    d->span=0;
    d->state=GAME_DISPLAY_EMPTY;
    return GAME_DISPLAY_OK;
}

GameDisplayStatus game_display_observe(GameLinuxDisplay *d, unsigned duration, unsigned timeout)
{
    GameDisplayPlatform *p;
    GameDisplayStatus s=GAME_DISPLAY_OK, stopped;
    uint64_t start, now, previous;
    unsigned polls=0;
    if (!d || !duration || duration>30000 || !timeout || timeout>1000)
        return GAME_DISPLAY_BAD_ARGUMENT;
    if (d->state!=GAME_DISPLAY_SCANNING) return GAME_DISPLAY_BAD_STATE;
    p=&d->platform;
    if (p->now_ms(p->context,&start)) s=GAME_DISPLAY_IO;
    else {
        previous=start;
        while (s==GAME_DISPLAY_OK) {
            s=game_display_status(d);
            if (s!=GAME_DISPLAY_OK) break;
            if (p->now_ms(p->context,&now) || now<previous) { s=GAME_DISPLAY_IO; break; }
            previous=now;
            if (now-start>=duration) break;
            if (++polls>duration+1U) { s=GAME_DISPLAY_TIMEOUT; break; }
            if (p->wait_ms(p->context,1)) { s=GAME_DISPLAY_IO; break; }
        }
    }
    stopped=game_display_stop(d,timeout);
    return stopped==GAME_DISPLAY_OK?s:stopped;
}

int game_display_owner_can_exit(const GameLinuxDisplay *d)
{
    return d && d->state==GAME_DISPLAY_EMPTY && !d->owner_active &&
        !d->allocation_owned && !d->buffer && !d->armed && !d->configured;
}

void game_display_owner_drain(GameLinuxDisplay *d, unsigned timeout)
{
    if (!d) return;
    if (!timeout || timeout>1000) timeout=100;
    while (!game_display_owner_can_exit(d)) {
        (void)game_display_stop(d,timeout);
        if (!game_display_owner_can_exit(d)) {
            /* No failure (including wait failure) licenses return/exit/dlclose.
             * An irrecoverable owner stays here for explicit recovery policy. */
            (void)d->platform.wait_ms(d->platform.context,100);
        }
    }
}

GameDisplayStatus game_display_linux_preflight(void)
{
    /* The task-local checker verifies the paired build, current boot/kernel,
     * executable, exclusive owners and load receipt. No force flag, PYNQ import
     * or libcma constructor. --check/default game execution stays CPU-only.
     * Until the complete receipt exists this diagnostic also fails closed. */
#if defined(__linux__) && defined(__arm__)
    struct stat st;
    pid_t child;
    int status;
#ifdef GAME_CAMERA_CAPTURE_CHECKER
    const char *checker="/run/game_live_camera/capture/qualify.py";
#elif defined(GAME_PHOTO_DISPLAY_CHECKER)
    const char *checker="/run/game_single_image_720p/photo_levels_1/qualify.py";
#else
    const char *checker="/run/game_single_image_720p/continuous/qualify.py";
#endif
    if (sizeof(void *)!=4 || lstat(checker,&st) || !S_ISREG(st.st_mode) ||
        st.st_uid!=0 || (st.st_mode&0022)) return GAME_DISPLAY_UNQUALIFIED;
    child=fork();
    if (child<0) return GAME_DISPLAY_UNQUALIFIED;
    if (!child) {
        execl("/usr/bin/python3","python3",checker,"--qualify",(char *)NULL);
        _exit(127);
    }
    while (waitpid(child,&status,0)<0) if (errno!=EINTR) return GAME_DISPLAY_UNQUALIFIED;
    if (WIFEXITED(status) && WEXITSTATUS(status)==0) return GAME_DISPLAY_OK;
#endif
    return GAME_DISPLAY_UNQUALIFIED;
}

static int linux_qualify(void *context, const GameDisplayMode *mode)
{
    (void)context;
    return !control_720p(mode) || game_display_linux_preflight()!=GAME_DISPLAY_OK;
}

/* Native register-resource ownership. No operation below is reachable from the
 * application before the closed qualification gate. No PS initialization,
 * clock/reset change, DMA reset or library constructor is used by acquire. */
#if defined(__linux__)
typedef struct {
    int memory_fd, lease_fd, lease_owned, armed;
    void *map[3]; /* MM2S, existing dynclk, existing VTC; one 4KiB page each */
    int xlnk_fd, allocation_id, allocation_uncertain, buffer_unmapped, timing_dirty;
    uint8_t *buffer;
    uint32_t physical;
    size_t span;
} LinuxDisplayResources;
static LinuxDisplayResources linux_resources={.memory_fd=-1,.lease_fd=-1,.xlnk_fd=-1};
static int linux_finish(void *context);
static int linux_barrier(void *context);
static int linux_wait(void *context,unsigned ms);

static void linux_resources_init(LinuxDisplayResources *r)
{
    memset(r,0,sizeof *r); r->memory_fd=-1; r->lease_fd=-1; r->xlnk_fd=-1;
}
static int linux_map_regions(LinuxDisplayResources *r,const off_t offsets[3])
{
    unsigned i;
    if (!r || !offsets || r->memory_fd<0 || r->lease_fd<0 || !r->lease_owned ||
        sysconf(_SC_PAGESIZE)!=4096) return -1;
    for (i=0;i<3;++i)
        if (r->map[i] || offsets[i]<0 || offsets[i]%4096) return -1;
    for (i=0;i<3;++i) {
        void *v=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,r->memory_fd,offsets[i]);
        if (v==MAP_FAILED) return -1; /* prior mappings/fds remain owned */
        r->map[i]=v;
    }
    return 0;
}
static int linux_close(void *context)
{
    LinuxDisplayResources *r=(LinuxDisplayResources *)context;
    unsigned i;
    int fd,result;
    if (!r || r->armed || r->allocation_id || r->allocation_uncertain) return -1;
    if (r->timing_dirty && linux_finish(r)) return -1;
    if (r->xlnk_fd>=0) {
        fd=r->xlnk_fd; r->xlnk_fd=-1;
        if (close(fd)) return -1;
    }
    for (i=3;i>0;--i) if (r->map[i-1]) {
        if (munmap(r->map[i-1],4096)) return -1;
        r->map[i-1]=NULL;
    }
    if (r->memory_fd>=0) {
        fd=r->memory_fd; r->memory_fd=-1;
        /* Linux consumes close's fd even on EINTR/late errors. Never retry the
         * number, which another thread may already have reused. */
        result=close(fd);
        if (result) return -1;
    }
    if (r->lease_fd>=0) {
        fd=r->lease_fd; r->lease_fd=-1; r->lease_owned=0;
        if (close(fd)) return -1;
    }
    return 0;
}
static int linux_acquire(void *context)
{
    LinuxDisplayResources *r=(LinuxDisplayResources *)context;
    const off_t offsets[3]={0x43010000,0x43c00000,0x43c10000};
    struct stat st;
    if (r!=&linux_resources || game_display_linux_preflight()!=GAME_DISPLAY_OK ||
        r->memory_fd>=0 || r->lease_fd>=0 || r->map[0] || r->map[1] || r->map[2]) return -1;
    linux_resources_init(r);
    r->lease_fd=open("/run/lock/game_linux_display.lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    if (r->lease_fd<0 || fstat(r->lease_fd,&st) || !S_ISREG(st.st_mode) ||
        st.st_nlink!=1 || st.st_uid!=geteuid() || (st.st_mode&0077) ||
        flock(r->lease_fd,LOCK_EX|LOCK_NB)) return -1;
    r->lease_owned=1;
    /* The persistent lock inode is never unlinked by close: a replaced inode
     * could allow two owners. This cooperative lease alone is NOT proof that
     * PYNQ/kernel/other pre-existing PL owners have been excluded. */
    r->memory_fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
    if (r->memory_fd<0) return -1;
    return linux_map_regions(r,offsets);
}
#ifndef GAME_DISPLAY_READ32
#define GAME_DISPLAY_READ32(p) (*(p))
#endif
static int linux_read(void *context,unsigned offset,uint32_t *value)
{
    LinuxDisplayResources *r=(LinuxDisplayResources *)context;
    volatile uint32_t *regs;
    if (!r || !r->lease_owned || !r->map[0] || !value ||
        (offset!=CR && offset!=SR && offset!=PARK)) return -1;
    regs=(volatile uint32_t *)r->map[0];
    *value=regs[offset/4U];
    /* During scanning, failure of the display qualifier is observable even
     * when VDMA has not yet reported an error. RS=0 cleanup reads stay usable. */
    if (offset==SR && (regs[CR/4U]&RUN) &&
        (!r->map[1] || (GAME_DISPLAY_READ32((volatile uint32_t *)r->map[1]+1)&3U)!=3U))
        return -1;
    if (offset==SR && (*value&HALTED) && !(regs[CR/4U]&RUN)) r->armed=0;
    return 0;
}
static int linux_write(void *context,unsigned offset,uint32_t value)
{
    LinuxDisplayResources *r=(LinuxDisplayResources *)context;
    volatile uint32_t *regs;
    if (!r || !r->lease_owned || !r->map[0]) return -1;
    regs=(volatile uint32_t *)r->map[0];
    switch (offset) {
    case CR:
        if (value!=0 && value!=RUN && !(value==CONTINUOUS_RUN && r->span==3U*FRAME_SPAN_720)) return -1;
        /* No reset,circular/finite count or IRQ-output enable. */
        if (value&RUN) r->armed=1; /* retain BEFORE a potentially visible start */
        break;
    case PARK:
        if ((value&31U)>=(r->span==3U*FRAME_SPAN_720?3U:1U) ||
            ((value^regs[PARK/4U])&~31U)) return -1;
        break;
    case SR: if (value!=FRAME_EVENT || r->span!=3U*FRAME_SPAN_720) return -1; break;
    case VSIZE: if (value!=720U) return -1; break;
    case HSIZE: if (value!=GAME_DISPLAY_HSIZE) return -1; break;
    case STRIDE: if (value!=GAME_DISPLAY_STRIDE) return -1; break;
    case ADDRESS: case ADDRESS+4U: case ADDRESS+8U:
        if (!r->buffer || (value&63U) ||
            (r->span!=FRAME_SPAN_720 && r->span!=3U*FRAME_SPAN_720) ||
            value!=r->physical+(r->span==3U*FRAME_SPAN_720?(offset-ADDRESS)/4U*FRAME_SPAN_720:0U)) return -1;
        break;
    default: return -1; /* rejects S2MM, status clear, reserved and odd offsets */
    }
    regs[offset/4U]=value;
    return 0;
}

/* ARM32 xlnk ABI: the identified running driver copies 88 bytes, not the
 * ioctl's encoded four bytes. Alloc fields are len/id/physical/cacheable at
 * offsets 0/4/8/12. See the frozen official headers and matched disassembly.
 * Only the existing allocator's alloc/free operations are used, never RESET,
 * RECRES or SHUTDOWN. No libcma load, constructor or destructor is involved. */
typedef union { uint32_t word[22]; uint8_t byte[88]; } LinuxXlnkArgs;
#ifndef GAME_DISPLAY_XLNK_IOCTL
#define GAME_DISPLAY_XLNK_IOCTL ioctl
#endif
static int linux_allocate(void *context,size_t n,uint8_t **v,uint64_t *p)
{
    LinuxDisplayResources *r=context;
    LinuxXlnkArgs a;
    void *mapped;
    if (!r || !v || !p || (n!=FRAME_SPAN_720 && n!=3U*FRAME_SPAN_720) || r->armed || !r->lease_owned ||
        r->buffer || r->allocation_id || r->allocation_uncertain) return -1;
    *v=NULL; *p=0;
    if (r->xlnk_fd<0) r->xlnk_fd=open("/dev/xlnk",O_RDWR|O_CLOEXEC);
    if (r->xlnk_fd<0) return -1;
    memset(&a,0,sizeof a); a.word[0]=(uint32_t)n; /* cacheable=0 */
    /* A failed ioctl can have allocated before failing copy_to_user/table
     * insertion. Retain the owner; never pretend failure was atomic or retry. */
    r->allocation_uncertain=1;
    if (GAME_DISPLAY_XLNK_IOCTL(r->xlnk_fd,0xc0045802UL,&a)!=0) return -1;
    if (!a.word[1] || a.word[1]>=4096U || !a.word[2] || (a.word[2]&4095U) ||
        n-1U>UINT32_MAX-a.word[2] || a.byte[12]!=0) return -1;
    r->allocation_id=(int)a.word[1]; r->physical=a.word[2]; r->span=n;
    r->allocation_uncertain=0;
    mapped=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_SHARED,r->xlnk_fd,
                (off_t)r->allocation_id*65536);
    if (mapped==MAP_FAILED) {
        memset(&a,0,sizeof a); a.word[0]=(uint32_t)r->allocation_id;
        r->allocation_uncertain=1;
        if (GAME_DISPLAY_XLNK_IOCTL(r->xlnk_fd,0xc0045803UL,&a)==0) {
            r->allocation_id=0; r->allocation_uncertain=0;
        }
        return -1;
    }
    r->buffer=mapped; r->buffer_unmapped=0; *v=mapped; *p=r->physical;
    return 0;
}
static int linux_release(void *context,uint8_t *v)
{
    LinuxDisplayResources *r=context;
    LinuxXlnkArgs a;
    if (!r || r->armed || r->timing_dirty || r->allocation_uncertain ||
        !v || v!=r->buffer || r->allocation_id<=0 || r->xlnk_fd<0) return -1;
    if (!r->buffer_unmapped) {
        if (munmap(r->buffer,r->span)) return -1;
        r->buffer_unmapped=1;
    }
    memset(&a,0,sizeof a); a.word[0]=(uint32_t)r->allocation_id;
    r->allocation_uncertain=1; /* never retry an uncertain free of a global ID */
    if (GAME_DISPLAY_XLNK_IOCTL(r->xlnk_fd,0xc0045803UL,&a)!=0) return -1;
    r->allocation_uncertain=0; r->allocation_id=0; r->buffer=NULL;
    r->physical=0; r->span=0;
    return 0;
}
static int linux_flush(void *context,uint8_t *v,uint64_t p,size_t n)
{
    LinuxDisplayResources *r=context;
    uintptr_t start=(uintptr_t)v,base;
    size_t offset;
    volatile uint32_t *regs;
    uint32_t park;
    if (!r || r->allocation_uncertain || r->buffer_unmapped || !r->buffer || r->allocation_id<=0) return -1;
    base=(uintptr_t)r->buffer;
    if (start<base || start-base>r->span) return -1;
    offset=(size_t)(start-base);
    if (n>r->span-offset || p!=r->physical+offset) return -1;
    if (!r->armed) {
        if (offset || n!=r->span) return -1;
    } else {
        if (r->span!=3U*FRAME_SPAN_720 || n!=FRAME_SPAN_720 || offset%FRAME_SPAN_720 || !r->map[0]) return -1;
        regs=r->map[0];park=regs[PARK/4U];
        if (!(regs[CR/4U]&RUN) || (regs[SR/4U]&(HALTED|ERRORS)) ||
            (park&31U)==offset/FRAME_SPAN_720 || ((park>>16)&31U)==offset/FRAME_SPAN_720) return -1;
    }
    /* Same matched xlnk cacheable=0 allocation/pgprot_noncached mapping.
     * No cached alias;dmb/dsb drains CPU stores before park submission. */
    return linux_barrier(r);
}
static int linux_poll(LinuxDisplayResources *r,unsigned bank,unsigned offset,
                      uint32_t mask,uint32_t expected,unsigned timeout)
{
    volatile uint32_t *regs=r->map[bank];
    unsigned i;
    if (!regs || !timeout || timeout>1000) return -1;
    for (i=0;i<=timeout;++i) {
        if ((GAME_DISPLAY_READ32(regs+offset/4U)&mask)==expected) return 0;
        if (i==timeout || linux_wait(r,1)) break;
    }
    return -1;
}
static int linux_finish(void *context)
{
    LinuxDisplayResources *r=context;
    volatile uint32_t *clock,*vtc,*dma;
    if (!r || r->armed || !r->map[0] || !r->map[1] || !r->map[2]) return -1;
    clock=r->map[1]; vtc=r->map[2]; dma=r->map[0];
    if ((dma[CR/4]&RUN) || !(dma[SR/4]&HALTED)) return -1;
    if (!r->timing_dirty) return 0;
    if (r->timing_dirty==2) {
        /* A READY loss holds VTC in reset: do not touch its AXI slave. */
        if (linux_poll(r,1,4,3,3,1)) return -1;
        vtc[0]=0x03f7ef02U;
        if (linux_barrier(r) || linux_poll(r,2,0,5,0,100)) return -1;
    }
    clock[0]=0;
    /* Completion clears and DISPLAY_READY drops. Clocks remain running. */
    if (linux_barrier(r) || linux_poll(r,1,4,3,0,100)) return -1;
    r->timing_dirty=0;
    return 0;
}
static int linux_configure(void *context,const GameDisplayMode *m,unsigned t)
{
    LinuxDisplayResources *r=context;
    volatile uint32_t *clock,*vtc,*dma;
    unsigned i;
    /* Derived from the canonical ClkFindReg/lookup tables at M52/D7/O2.
     * VTC origin=active-start, matching installed 2023.1 XVtc_ConvTiming2Signal:
     * vertical sync starts at active+front-1. No detector or IRQ is enabled. */
    static const uint32_t clk[6]={0x41,0x69a,0,0x20c4,0xcfafa401,0x00a300ff};
    static const uint32_t timing[][2]={
        {0x60,720U<<16|1280U},{0x68,0},{0x6c,0x7f},
        {0x70,1650},{0x74,750U<<16|750U},{0x78,1430U<<16|1390U},
        {0x7c,1280U<<16|1280U},{0x80,729U<<16|724U},
        {0x84,1390U<<16|1390U},{0x88,1280U<<16|1280U},
        {0x8c,729U<<16|724U},{0x90,1390U<<16|1390U},{0x94,720U<<16}
    };
    if (!r || !control_720p(m) || !t || t>1000 || r->armed || r->timing_dirty ||
        !r->map[0] || !r->map[1] || !r->map[2]) return -1;
    clock=r->map[1]; vtc=r->map[2]; dma=r->map[0];
    if ((dma[CR/4]&RUN) || !(dma[SR/4]&HALTED)) return -1;
    r->timing_dirty=1;
    clock[0]=0; /* READY low resets VTC; no AXI access yet. */
    if (linux_barrier(r) || linux_poll(r,1,4,3,0,t)) goto failed;
    /* Hold isolation with the old pixel clock running before DRP can stop it.
     * This also guarantees the VTC's >=32 slowest-cycle reset pulse. */
    if (linux_wait(r,1)) goto failed;
    for (i=0;i<6;++i) clock[(8U+4U*i)/4U]=clk[i];
    if (linux_barrier(r)) goto failed;
    clock[0]=1;
    if (linux_barrier(r) || linux_poll(r,1,4,3,3,t)) goto failed;
    /* Two proc_sys_reset v5.0 rev13 instances release in their own domains.
     * 1ms exceeds their filter/sequencer latency at both fixed clock states;
     * it is not evidence of physical frequency or FIFO/video alignment. */
    if (linux_wait(r,1) || linux_poll(r,1,4,3,3,t)) goto failed;
    r->timing_dirty=2; /* VTC is accessible only after READY + release wait. */
    vtc[0]=0x03f7ef02U;
    if (linux_barrier(r) || linux_poll(r,2,0,5,0,t)) goto failed;
    for (i=0;i<sizeof timing/sizeof timing[0];++i) vtc[timing[i][0]/4U]=timing[i][1];
    if (linux_barrier(r)) goto failed;
    for (i=0;i<sizeof timing/sizeof timing[0];++i)
        if (vtc[timing[i][0]/4U]!=timing[i][1]) goto failed;
    return 0;
failed:
    (void)linux_finish(r); /* close retains the owner if this cannot unwind */
    return -1;
}
static int linux_output(void *context,int enabled)
{
    LinuxDisplayResources *r=context;
    volatile uint32_t *vtc;
    if (!r || r->timing_dirty!=2 || !r->map[2] || (enabled!=0 && enabled!=1)) return -1;
    if (!enabled && r->armed) return -1;
    if (linux_poll(r,1,4,3,3,1)) return -1;
    vtc=r->map[2]; vtc[0]=0x03f7ef02U|(enabled?5U:0U);
    return linux_barrier(r) || linux_poll(r,2,0,5U,enabled?5U:0U,100);
}
#else
static int linux_acquire(void *c) { (void)c; return -1; }
static int linux_close(void *c) { (void)c; return -1; }
static int linux_read(void *c,unsigned o,uint32_t *v)
{ (void)c; (void)o; (void)v; return -1; }
static int linux_write(void *c,unsigned o,uint32_t v)
{ (void)c; (void)o; (void)v; return -1; }
static int linux_finish(void *c) { (void)c; return -1; }
static int linux_allocate(void *c,size_t n,uint8_t **v,uint64_t *p)
{ (void)c; (void)n; (void)v; (void)p; return -1; }
static int linux_release(void *c,uint8_t *v)
{ (void)c; (void)v; return -1; }
static int linux_flush(void *c,uint8_t *v,uint64_t p,size_t n)
{ (void)c; (void)v; (void)p; (void)n; return -1; }
static int linux_configure(void *c,const GameDisplayMode *m,unsigned t)
{ (void)c; (void)m; (void)t; return -1; }
static int linux_output(void *c,int enabled)
{ (void)c; (void)enabled; return -1; }
#endif
static int linux_barrier(void *context)
{
    (void)context;
#if defined(__linux__) && defined(__arm__)
    __asm__ __volatile__("dsb sy" ::: "memory");
    return 0;
#elif defined(__linux__)
    __sync_synchronize();
    return 0;
#else
    return -1;
#endif
}
static int linux_now(void *context,uint64_t *ms)
{
    (void)context;
#if defined(__linux__)
    struct timespec t;
    if (!ms || clock_gettime(CLOCK_MONOTONIC,&t) || t.tv_sec<0) return -1;
    *ms=(uint64_t)t.tv_sec*1000U+(unsigned long)t.tv_nsec/1000000U;
    return 0;
#else
    (void)ms; return -1;
#endif
}
static int linux_wait(void *context,unsigned ms)
{
    (void)context;
#if defined(__linux__)
    struct timespec request,remaining;
    if (!ms || ms>1000) return -1;
    request.tv_sec=ms/1000U;
    request.tv_nsec=(long)(ms%1000U)*1000000L;
    while (nanosleep(&request,&remaining)) {
        if (errno!=EINTR) return -1;
        request=remaining;
    }
    return 0;
#else
    (void)ms; return -1;
#endif
}

void game_display_linux_platform(GameDisplayPlatform *p)
{
    if (!p) return;
    memset(p,0,sizeof(*p));
    p->version=GAME_DISPLAY_VERSION;
#if defined(__linux__)
    p->context=&linux_resources;
#endif
    p->qualify=linux_qualify;
    p->allocate=linux_allocate; p->release=linux_release; p->flush=linux_flush;
    p->barrier=linux_barrier; p->configure=linux_configure; p->output=linux_output;
    p->finish=linux_finish; p->read=linux_read; p->write=linux_write;
    p->now_ms=linux_now; p->wait_ms=linux_wait;
    p->acquire=linux_acquire; p->close=linux_close;
}
