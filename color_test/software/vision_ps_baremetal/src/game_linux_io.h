#ifndef GAME_LINUX_IO_H
#define GAME_LINUX_IO_H
#include "game_pump.h"
#ifdef __cplusplus
extern "C" {
#endif
#define GAME_LINUX_CALLS_VERSION 1U
#define GAME_LINUX_READY 1U
#define GAME_LINUX_FAULT 2U
#define GAME_LINUX_WAKE 4U
/* Syscall seam: results are nonnegative or -errno, never ambient errno.
 * One bounded attempt per call, including EINTR. Real implementation below
 * uses Linux headers; host tests inject these calls without accessing devices. */
typedef struct {
    unsigned int version;
    void *context;
    int (*layout)(void *,GameEvdevLayout *);
    int (*clock_ms)(void *,uint64_t *);
    int (*open_input)(void *,const char *);
    int (*close_input)(void *,int);
    ptrdiff_t (*read_input)(void *,int,unsigned char *,size_t);
    int (*poll_input)(void *,int,int,int,unsigned int *);
    int (*left_button)(void *,int,int *);
} GameLinuxCalls;
typedef struct {
    void *context;
    int (*result)(void *,GameDetectionFrame *);
    int (*stopping)(void *);
    void (*publish)(void *,const GamePumpOutput *);
    /* Drain the borrowed nonblocking wake fd; 0=done, negative=fatal.
     * Required with wake_fd>=0, so readiness never stays latched. */
    int (*wake)(void *);
} GameLinuxHooks;
typedef struct {
    GameLinuxCalls calls;
    GameLinuxHooks hooks;
    GameEvdevLayout layout;
    int fd,wake_fd,error,clock_failed;
    uint64_t epoch,last_ms;
} GameLinuxIO;
/* Returns NULL on non-Linux hosts. Linux call table performs actual syscalls
 * ONLY when explicitly called; querying the table has no device side effects. */
const GameLinuxCalls *game_linux_system_calls(void);
/* Single owner, no threads/discovery/automatic reopen. Initialization validates
 * the compiled UAPI layout and samples monotonic time, but opens no device.
 * wake_fd is borrowed; input fd is owned. Caller shares this clock with capture. */
int game_linux_io_init(GameLinuxIO *,const GameLinuxCalls *,const GameLinuxHooks *,int wake_fd);
int game_linux_io_open(GameLinuxIO *,const char *explicit_path);
void game_linux_io_close(GameLinuxIO *);
GamePumpIO game_linux_pump_io(GameLinuxIO *);
/* On fatal clock/poll/wake error, return to owner; do not retry a pump with a
 * failed clock. Device detach alone leaves the running game timer unchanged.
 * No capture/display backend or target-runtime compatibility is implied. */
#ifdef __cplusplus
}
#endif
#endif
