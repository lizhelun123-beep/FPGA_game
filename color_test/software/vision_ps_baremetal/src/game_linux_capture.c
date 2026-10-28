#define _POSIX_C_SOURCE 200809L
#include "game_linux_capture.h"
#include "game_linux_display.h"
#include "scene_protocol.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#if defined(__linux__)
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

#define CAPTURE_SPAN GAME_CAPTURE_FRAME_SPAN
#define CAPTURE_ERRORS 0x000089f0U
static int owner_active;
int game_capture_parked_slot_valid(const GameCaptureDmaState *s,uint64_t base,
                                   unsigned slot,unsigned writer)
{
    unsigned i;
    const uint32_t mask=0x00ff101fU; /* count=1,IRQ enabled,RS1,park,no genlock/count halt/reset */
    if (!s || slot>=3U || writer>=3U || slot==writer || !base || (base&4095U) ||
        base>UINT64_C(0x40000000)-3U*(uint64_t)CAPTURE_SPAN ||
        (s->control&mask)!=0x00011001U || (s->status&(CAPTURE_ERRORS|1U)) ||
        ((s->park>>8)&31U)!=writer || ((s->park>>24)&31U)!=writer ||
        s->vsize!=720U || s->hsize!=3840U || (s->stride&65535U)!=5760U) return 0;
    for (i=0;i<3U;++i)
        if (s->addresses[i]!=base+(uint64_t)i*CAPTURE_SPAN) return 0;
    return 1;
}
int game_capture_detect_bgr(const uint8_t *bgr,uint32_t sequence,uint32_t capture_ms,
                            char *line,unsigned capacity)
{
    VisionDetection detections[VISION_MAX_DETECTIONS];
    int count;
    if (!bgr || !line || !sequence) return -1;
    count=vision_detect_bgr888(bgr,1280,720,3840,detections,VISION_MAX_DETECTIONS);
    return scene_protocol_encode(line,capacity,detections,count,count>=0,
                                 sequence,sequence,capture_ms,1280,720);
}
int game_capture_image_copy(const GameCaptureImageView *image,VisionCanvas *destination)
{
    uintptr_t source,target;
    unsigned row;
    if (!image || !image->data || image->width!=1280U || image->height!=720U ||
        image->stride!=3840U || image->capacity!=3840U*720U ||
        !image->stamp.generation || !image->stamp.sequence ||
        !vision_canvas_valid(destination) || destination->width!=1280 ||
        destination->height!=720) return -1;
    source=(uintptr_t)image->data;target=(uintptr_t)destination->data;
    if (image->capacity>UINTPTR_MAX-source || destination->capacity>UINTPTR_MAX-target ||
        (source<target+destination->capacity && target<source+image->capacity)) return -1;
    for (row=0;row<720U;++row)
        memcpy(destination->data+(size_t)row*destination->stride,
               image->data+(size_t)row*image->stride,3840U);
    return 0;
}
#if defined(__linux__)
static GameDisplayPlatform allocator;
static uint8_t *pixels;
static uint64_t physical;
static uint8_t *cpu_copy;
static int memory_fd=-1;
static volatile uint32_t *capture_regs;
static int stopped(int healthy)
{
    uint32_t control,status;
    if (!capture_regs || !allocator.barrier || allocator.barrier(allocator.context)) return 0;
    control=capture_regs[0x30/4];status=capture_regs[0x34/4];
    return !(control&1U) && (status&1U) && (!healthy || !(status&CAPTURE_ERRORS));
}
static int parked_slot(unsigned slot,unsigned writer)
{
    GameCaptureDmaState s;
    unsigned i;
    if (!owner_active || !pixels || !capture_regs || !allocator.barrier ||
        allocator.barrier(allocator.context)) return 0;
    s.control=capture_regs[0x30/4];s.status=capture_regs[0x34/4];
    s.park=capture_regs[0x28/4];s.vsize=capture_regs[0xa0/4];
    s.hsize=capture_regs[0xa4/4];s.stride=capture_regs[0xa8/4];
    for (i=0;i<3U;++i) s.addresses[i]=capture_regs[0xac/4+i];
    return game_capture_parked_slot_valid(&s,physical,slot,writer) &&
           capture_regs[0x28/4]==s.park && !allocator.barrier(allocator.context);
}
#endif

int game_capture_owner_can_exit(void) { return !owner_active; }
int game_capture_owner_sync(unsigned slot)
{
#if defined(__linux__)
    /* cacheable=0 and the same reviewed noncached driver mapping. A dsb
     * orders device completion and CPU access; no invented coherent flag. */
    if (!owner_active || !pixels || slot>=3U || !stopped(1)) return -1;
    return allocator.barrier(allocator.context);
#else
    (void)slot;return -1;
#endif
}
int game_capture_detect_owned(uint32_t sequence,uint32_t capture_ms,char *line,
                              unsigned capacity,uint32_t *copy_ms,uint32_t *detect_ms)
{
#if defined(__linux__)
    uint64_t began,copied,ended;
    unsigned row;
    int result;
    if (!copy_ms || !detect_ms || !cpu_copy || !pixels ||
        game_capture_owner_sync(0) || allocator.now_ms(allocator.context,&began) ||
        !sequence || capture_ms>began || began-capture_ms>5000U) return -1;
    for (row=0;row<720U;++row) memcpy(cpu_copy+row*3840U,pixels+row*5760U,3840U);
    if (game_capture_owner_sync(0) || allocator.now_ms(allocator.context,&copied)) return -1;
    result=game_capture_detect_bgr(cpu_copy,sequence,capture_ms,line,capacity);
    if (allocator.now_ms(allocator.context,&ended) || ended<copied || copied<began) return -1;
    *copy_ms=(uint32_t)(copied-began);*detect_ms=(uint32_t)(ended-copied);
    return result;
#else
    (void)sequence;(void)capture_ms;(void)line;(void)capacity;(void)copy_ms;(void)detect_ms;
    return -1;
#endif
}

static int dispatch_owned(int parked,unsigned slot,unsigned writer,
                                uint64_t generation,uint64_t sequence,
                                uint64_t captured_ms,GameCaptureFrameCallback callback,
                                GameCaptureImageCallback image_callback,
                                void *context,uint32_t *copy_ms,uint32_t *detect_ms)
{
#if defined(__linux__)
    uint64_t began,copied,ended;
    unsigned row;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    GameDetectionFrame frame;
    int count,result;
    if (!generation || !sequence || (!callback && !image_callback) ||
        (callback && image_callback) || !copy_ms || !detect_ms ||
        !cpu_copy || !pixels || (parked?!parked_slot(slot,writer):game_capture_owner_sync(slot)) ||
        allocator.now_ms(allocator.context,&began) || captured_ms>began ||
        began-captured_ms>5000U) return -1;
    for (row=0;row<720U;++row)
        memcpy(cpu_copy+row*3840U,pixels+(size_t)slot*CAPTURE_SPAN+row*5760U,3840U);
    if ((parked?!parked_slot(slot,writer):game_capture_owner_sync(slot)) ||
        allocator.now_ms(allocator.context,&copied)) return -1;
    count=vision_detect_bgr888(cpu_copy,1280,720,3840,detections,VISION_MAX_DETECTIONS);
    frame=(GameDetectionFrame){(GameCaptureStamp){generation,sequence,captured_ms},
                               count>=0,0,detections,count};
    if (image_callback) {
        const GameCaptureImageView image={cpu_copy,1280U,720U,3840U,3840U*720U,frame.stamp};
        result=image_callback(context,&frame,&image);
    } else result=callback(context,&frame);
    if (allocator.now_ms(allocator.context,&ended) || ended<copied || copied<began) return -1;
    *copy_ms=(uint32_t)(copied-began);*detect_ms=(uint32_t)(ended-copied);
    return result;
#else
    (void)parked;(void)slot;(void)writer;
    (void)generation;(void)sequence;(void)captured_ms;(void)callback;(void)image_callback;(void)context;
    (void)copy_ms;(void)detect_ms;return -1;
#endif
}

int game_capture_owner_dispatch(uint64_t generation,uint64_t sequence,
                                uint64_t captured_ms,GameCaptureFrameCallback callback,
                                void *context,uint32_t *copy_ms,uint32_t *detect_ms)
{
    return dispatch_owned(0,0,0,generation,sequence,captured_ms,callback,NULL,context,copy_ms,detect_ms);
}

int game_capture_owner_dispatch_parked(unsigned slot,unsigned writer,
                                      uint64_t generation,uint64_t sequence,
                                      uint64_t captured_ms,GameCaptureFrameCallback callback,
                                      void *context,uint32_t *copy_ms,uint32_t *detect_ms)
{
    return dispatch_owned(1,slot,writer,generation,sequence,captured_ms,callback,NULL,context,copy_ms,detect_ms);
}

int game_capture_owner_dispatch_image_parked(unsigned slot,unsigned writer,
                                      uint64_t generation,uint64_t sequence,
                                      uint64_t captured_ms,GameCaptureImageCallback callback,
                                      void *context,uint32_t *copy_ms,uint32_t *detect_ms)
{
    return dispatch_owned(1,slot,writer,generation,sequence,captured_ms,NULL,callback,context,copy_ms,detect_ms);
}

int game_capture_owner_release(void)
{
#if defined(__linux__)
    if (!owner_active) return 0;
    if (pixels) {
        if (!stopped(0) || allocator.release(allocator.context,pixels)) return -2;
        pixels=NULL;physical=0;
    }
    free(cpu_copy);cpu_copy=NULL;
    if (capture_regs) {
        if (munmap((void *)capture_regs,4096)) return -2;
        capture_regs=NULL;
    }
    if (memory_fd>=0) {
        int fd=memory_fd;memory_fd=-1;
        if (close(fd)) return -2;
    }
    if (allocator.close(allocator.context)) return -2;
    owner_active=0;
    return 0;
#else
    return owner_active?-2:0;
#endif
}
int game_capture_owner_prepare_with_platform(const GameDisplayPlatform *platform,
                                             uint64_t *virtual_address,uint64_t *physical_address)
{
#if defined(__linux__)
    GameDisplayMode mode;
    void *mapped;
    if (!virtual_address || !physical_address || owner_active) return -1;
    *virtual_address=0;*physical_address=0;
    if (platform) allocator=*platform;
    else game_display_linux_platform(&allocator);
    game_display_control_720p_mode(&mode);
    if (allocator.qualify(allocator.context,&mode)) return -1;
    owner_active=1;
    if (allocator.acquire(allocator.context)) goto failed;
    memory_fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
    if (memory_fd<0 || sysconf(_SC_PAGESIZE)!=4096) goto failed;
    mapped=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,memory_fd,(off_t)0x43000000);
    if (mapped==MAP_FAILED) goto failed;
    capture_regs=mapped;
    if (!stopped(1) || allocator.allocate(allocator.context,3U*CAPTURE_SPAN,&pixels,&physical)) goto failed;
    if (!pixels || !physical || (physical&4095U) || physical+3U*CAPTURE_SPAN>UINT64_C(0x40000000)) goto failed;
    cpu_copy=malloc(3840U*720U);
    if (!cpu_copy) goto failed;
    *virtual_address=(uint64_t)(uintptr_t)pixels;*physical_address=physical;
    return 0;
failed:
    return game_capture_owner_release()?-2:-1;
#else
    (void)platform;(void)virtual_address;(void)physical_address;return -1;
#endif
}

int game_capture_owner_prepare(uint64_t *virtual_address,uint64_t *physical_address)
{ return game_capture_owner_prepare_with_platform(NULL,virtual_address,physical_address); }
