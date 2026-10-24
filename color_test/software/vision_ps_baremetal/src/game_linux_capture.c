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

#define CAPTURE_SPAN (5760U*720U)
#define CAPTURE_ERRORS 0x000089f0U
static int owner_active;
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
int game_capture_owner_prepare(uint64_t *virtual_address,uint64_t *physical_address)
{
#if defined(__linux__)
    GameDisplayMode mode;
    void *mapped;
    if (!virtual_address || !physical_address || owner_active) return -1;
    *virtual_address=0;*physical_address=0;
    game_display_linux_platform(&allocator);
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
    (void)virtual_address;(void)physical_address;return -1;
#endif
}
