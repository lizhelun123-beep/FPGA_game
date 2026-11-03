#include "beam_pynq_display.h"
#include <stdlib.h>

/* The existing complete-frame/triple-store display state machine is used
 * unchanged. Python owns the platform callbacks, allocations and PYNQ MMIO. */
struct BeamPynqDisplay { GameLinuxDisplay owner; };
size_t beam_pynq_platform_size(void) { return sizeof(GameDisplayPlatform); }
int beam_pynq_barrier(void)
{
#if defined(__linux__) && defined(__arm__)
    __asm__ __volatile__("dsb sy" ::: "memory");
#elif defined(__linux__)
    __sync_synchronize();
#endif
    return 0;
}
BeamPynqDisplay *beam_pynq_display_new(void)
{
    BeamPynqDisplay *d=calloc(1,sizeof *d);
    if (d) game_display_init(&d->owner);
    return d;
}
int beam_pynq_display_prepare(BeamPynqDisplay *d,const GameDisplayPlatform *p)
{
    GameDisplayMode mode;
    VisionCanvas canvas;
    int result;
    uint8_t *blank;
    if (!d || !p) return GAME_DISPLAY_BAD_ARGUMENT;
    blank=calloc(1,3840U*720U);
    if (!blank) return GAME_DISPLAY_IO;
    canvas=(VisionCanvas){blank,1280,720,3840U,3840U*720U};
    game_display_control_720p_mode(&mode);
    result=(int)game_display_prepare_continuous(&d->owner,&mode,p,&canvas);
    free(blank);
    return result ? result : (int)game_display_start(&d->owner,500);
}
int beam_pynq_display_submit(BeamPynqDisplay *d,const uint8_t *bgr,size_t n)
{
    VisionCanvas canvas={(uint8_t *)bgr,1280,720,3840U,n};
    return d ? (int)game_display_submit(&d->owner,&canvas,500) : GAME_DISPLAY_BAD_ARGUMENT;
}
int beam_pynq_display_poll(BeamPynqDisplay *d)
{ return d ? (int)game_display_poll(&d->owner) : GAME_DISPLAY_BAD_ARGUMENT; }
int beam_pynq_display_stop(BeamPynqDisplay *d)
{ return d ? (int)game_display_stop(&d->owner,1000) : GAME_DISPLAY_BAD_ARGUMENT; }
int beam_pynq_display_free(BeamPynqDisplay *d)
{
    if (!d || !game_display_owner_can_exit(&d->owner)) return -1;
    free(d); return 0;
}
