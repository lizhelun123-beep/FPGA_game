#ifndef GAME_BAREMETAL_IO_H
#define GAME_BAREMETAL_IO_H
#include "game_linux_capture.h"

/* One Cortex-A9/core0 owner; addresses come from its byte-matched XSA/BSP.
 * DMA stores are static linker-owned DDR, disjoint from the CPU image.
 * No OS, file system, interrupt callback, second core or dynamic DMA owner. */
uint64_t game_baremetal_now_ms(void);
int game_baremetal_prepare(void);
void game_baremetal_display_platform(GameDisplayPlatform *platform);
int game_baremetal_capture_start(void);
/* Service pending display retirement while awaiting capture START events.
 * Both remain owned by this one loop; no device buffer is reused early. */
int game_baremetal_capture_copy(uint8_t *cpu, size_t capacity,
    GameCaptureStamp *stamp, GameLinuxDisplay *display, void (*service_uart)(void));
int game_baremetal_capture_check(void);
int game_baremetal_capture_stop(void);
void game_baremetal_first_fault(const char *stage);
#endif
