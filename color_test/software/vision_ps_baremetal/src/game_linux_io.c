#if defined(__linux__)
#define _POSIX_C_SOURCE 200809L
#endif
#include "game_linux_io.h"
#include <errno.h>
#include <limits.h>
#include <string.h>

static uint64_t clock_now(void *context)
{
    GameLinuxIO *io=context;
    uint64_t now=0;
    int status;
    if (io->clock_failed) return GAME_PUMP_CLOCK_ERROR;
    status=io->calls.clock_ms(io->calls.context,&now);
    if (status || now==GAME_PUMP_CLOCK_ERROR || now<io->last_ms) {
        io->error=status<0?status:-ERANGE; io->clock_failed=1;
        return GAME_PUMP_CLOCK_ERROR;
    }
    io->last_ms=now; return now;
}
static void detach(GameLinuxIO *io)
{
    if (io->fd>=0) {
        int fd=io->fd,status;
        io->fd=-1;
        /* Linux close must not be retried on EINTR: fd may already be reused. */
        status=io->calls.close_input(io->calls.context,fd);
        if (status) io->error=status;
    }
}
int game_linux_io_init(GameLinuxIO *io,const GameLinuxCalls *calls,const GameLinuxHooks *hooks,int wake_fd)
{
    if (!io) return 0;
    memset(io,0,sizeof *io); io->fd=io->wake_fd=-1;
    if (!calls || calls->version!=GAME_LINUX_CALLS_VERSION || !calls->layout ||
        !calls->clock_ms || !calls->open_input || !calls->close_input ||
        !calls->read_input || !calls->poll_input || !calls->left_button ||
        wake_fd< -1 || (wake_fd>=0 && (!hooks || !hooks->wake))) return 0;
    io->calls=*calls; if (hooks) io->hooks=*hooks;
    io->wake_fd=wake_fd;
    io->error=calls->layout(calls->context,&io->layout);
    if (io->error || (io->layout!=GAME_EVDEV_LE32 && io->layout!=GAME_EVDEV_LE64)) return 0;
    return clock_now(io)!=GAME_PUMP_CLOCK_ERROR;
}
int game_linux_io_open(GameLinuxIO *io,const char *path)
{
    int fd;
    if (!io || !io->calls.open_input || !path || !*path || io->fd>=0 || io->clock_failed) return 0;
    if (io->epoch==UINT64_MAX) { io->error=-ERANGE; return 0; }
    fd=io->calls.open_input(io->calls.context,path);
    if (fd<0) { io->error=fd; return 0; }
    io->fd=fd; ++io->epoch; io->error=0; return 1;
}
void game_linux_io_close(GameLinuxIO *io) { if (io && io->calls.close_input) detach(io); }
static GamePumpConnection connection(void *context)
{
    GameLinuxIO *io=context;
    return (GamePumpConnection){io->fd>=0,io->epoch};
}
static GameReadResult read_bytes(void *context,unsigned char *bytes,size_t capacity)
{
    GameLinuxIO *io=context;
    ptrdiff_t n;
    GameReadStatus status;
    if (io->fd<0) return (GameReadResult){GAME_READ_DISCONNECTED,0};
    if (!bytes || !capacity || capacity>PTRDIFF_MAX) return (GameReadResult){GAME_READ_ERROR,0};
    n=io->calls.read_input(io->calls.context,io->fd,bytes,capacity);
    if (n>0 && (size_t)n<=capacity) return (GameReadResult){GAME_READ_DATA,(size_t)n};
    if (n==-EINTR) return (GameReadResult){GAME_READ_INTERRUPTED,0};
    if (n==-EAGAIN) return (GameReadResult){GAME_READ_AGAIN,0};
#ifdef EWOULDBLOCK
    if (n==-EWOULDBLOCK) return (GameReadResult){GAME_READ_AGAIN,0};
#endif
    status=n==0?GAME_READ_EOF:(n==-ENODEV || n==-ENXIO)?GAME_READ_DISCONNECTED:GAME_READ_ERROR;
    detach(io); io->error=n<0?(int)n:n==0?0:-EIO;
    return (GameReadResult){status,0};
}
static GameWaitStatus wait_until(void *context,uint64_t deadline)
{
    GameLinuxIO *io=context;
    uint64_t now=clock_now(io),remaining;
    unsigned events=0;
    int timeout,status;
    if (now==GAME_PUMP_CLOCK_ERROR) return GAME_WAIT_ERROR;
    if (deadline<=now) return GAME_WAIT_READY;
    remaining=deadline-now; timeout=remaining>INT_MAX?INT_MAX:(int)remaining;
    status=io->calls.poll_input(io->calls.context,io->fd,io->wake_fd,timeout,&events);
    if (status==-EINTR) return GAME_WAIT_INTERRUPTED;
    if (status<0 || status>1 || (events&~(GAME_LINUX_READY|GAME_LINUX_FAULT|GAME_LINUX_WAKE))) {
        io->error=status<0?status:-EIO; return GAME_WAIT_ERROR;
    }
    if (events&GAME_LINUX_FAULT) { detach(io); io->error=-ENODEV; }
    if (events&GAME_LINUX_WAKE) {
        if (io->wake_fd<0 || !io->hooks.wake || (status=io->hooks.wake(io->hooks.context))!=0) {
            io->error=status<0?status:-EIO; return GAME_WAIT_ERROR;
        }
    }
    return GAME_WAIT_READY;
}
static int resync(void *context)
{
    GameLinuxIO *io=context;
    int down=1,status;
    if (io->fd<0) return -1;
    status=io->calls.left_button(io->calls.context,io->fd,&down);
    if (status==-EINTR || status==-EAGAIN) return 0;
    if (status || (down!=0 && down!=1)) { detach(io); io->error=status?status:-EIO; return -1; }
    /* A held key cannot fabricate a release/click. Recovery waits for observed
     * device state UP, then retains the core's release-after-connect policy. */
    return !down;
}
static int result(void *context,GameDetectionFrame *frame)
{ GameLinuxIO *io=context; return io->hooks.result(io->hooks.context,frame); }
static int stopping(void *context)
{ GameLinuxIO *io=context; return io->hooks.stopping?io->hooks.stopping(io->hooks.context):0; }
static void publish(void *context,const GamePumpOutput *output)
{ GameLinuxIO *io=context; if (io->hooks.publish) io->hooks.publish(io->hooks.context,output); }
GamePumpIO game_linux_pump_io(GameLinuxIO *io)
{
    GamePumpIO pump={GAME_PUMP_IO_VERSION,io,clock_now,connection,read_bytes,wait_until,
                    resync,NULL,stopping,publish};
    if (io && io->hooks.result) pump.result=result;
    return pump;
}

#if defined(__linux__)
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

/* Older UAPI headers expose timeval directly; newer headers select time64
 * members via these aliases. Use local selectors without redefining UAPI. */
#if defined(input_event_sec) && defined(input_event_usec)
#define GAME_EVENT_SEC input_event_sec
#define GAME_EVENT_USEC input_event_usec
#else
#define GAME_EVENT_SEC time.tv_sec
#define GAME_EVENT_USEC time.tv_usec
#endif

static int system_layout(void *context,GameEvdevLayout *layout)
{
    const uint16_t endian=1;
    size_t size=sizeof(struct input_event),offset=offsetof(struct input_event,type);
    (void)context;
    if (*(const unsigned char *)&endian!=1 ||
        offsetof(struct input_event,code)!=offset+2 || offsetof(struct input_event,value)!=offset+4 ||
        sizeof(((struct input_event *)0)->type)!=2 || sizeof(((struct input_event *)0)->code)!=2 ||
        sizeof(((struct input_event *)0)->value)!=4) return -EINVAL;
    if (size==16 && offset==8) *layout=GAME_EVDEV_LE32;
    else if (size==24 && offset==16) *layout=GAME_EVDEV_LE64;
    else return -EINVAL;
    /* Time word placement must agree too, regardless of libc time64 choices. */
    if (offsetof(struct input_event,GAME_EVENT_SEC)!=0 ||
        offsetof(struct input_event,GAME_EVENT_USEC)!=offset/2 ||
        sizeof(((struct input_event *)0)->GAME_EVENT_SEC)!=offset/2 ||
        sizeof(((struct input_event *)0)->GAME_EVENT_USEC)!=offset/2) return -EINVAL;
    return 0;
}
static int system_clock(void *context,uint64_t *ms)
{
    struct timespec now;
    uint64_t sec,sub;
    (void)context;
    if (clock_gettime(CLOCK_MONOTONIC,&now)) return -errno;
    if (now.tv_sec<0 || now.tv_nsec<0 || now.tv_nsec>=1000000000L) return -ERANGE;
    sec=(uint64_t)now.tv_sec; sub=(uint64_t)now.tv_nsec/1000000;
    if (sec>(UINT64_MAX-1-sub)/1000) return -EOVERFLOW;
    *ms=sec*1000+sub; return 0;
}
static int bit(const unsigned char *bits,unsigned n) { return (bits[n/8]>>(n%8))&1; }
static int system_open(void *context,const char *path)
{
    unsigned char rel[REL_MAX/8+1],keys[KEY_MAX/8+1];
    int fd,status;
    (void)context;
    fd=open(path,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if (fd<0) return -errno;
    memset(rel,0,sizeof rel); memset(keys,0,sizeof keys);
    status=ioctl(fd,EVIOCGBIT(EV_REL,sizeof rel),rel);
    if (status>=0) status=ioctl(fd,EVIOCGBIT(EV_KEY,sizeof keys),keys);
    if (status<0 || !bit(rel,REL_X) || !bit(rel,REL_Y) || !bit(keys,BTN_LEFT)) {
        int error=status<0?errno:ENODEV;
        (void)close(fd); return -error;
    }
    return fd;
}
static int system_close(void *context,int fd)
{ (void)context; return close(fd)?-errno:0; }
static ptrdiff_t system_read(void *context,int fd,unsigned char *bytes,size_t capacity)
{
    ssize_t count;
    (void)context;
    count=read(fd,bytes,capacity); return count<0?-(ptrdiff_t)errno:(ptrdiff_t)count;
}
static int system_poll(void *context,int fd,int wake_fd,int timeout,unsigned *events)
{
    struct pollfd fds[2]={{fd,POLLIN,0},{wake_fd,POLLIN,0}};
    int status;
    (void)context;
    status=poll(fds,2,timeout);
    if (status<0) return -errno;
    *events=0;
    if (fds[0].revents&POLLIN) *events|=GAME_LINUX_READY;
    if (fds[0].revents&(POLLHUP|POLLERR|POLLNVAL)) *events|=GAME_LINUX_FAULT;
    /* Wake fd is owner infrastructure: HUP/fault is fatal, never idle spin. */
    if (fds[1].revents&(POLLHUP|POLLERR|POLLNVAL)) return -EIO;
    if (fds[1].revents&POLLIN) *events|=GAME_LINUX_WAKE;
    return status?1:0;
}
static int system_button(void *context,int fd,int *down)
{
    unsigned char keys[KEY_MAX/8+1];
    (void)context; memset(keys,0,sizeof keys);
    if (ioctl(fd,EVIOCGKEY(sizeof keys),keys)<0) return -errno;
    *down=bit(keys,BTN_LEFT); return 0;
}
const GameLinuxCalls *game_linux_system_calls(void)
{
    static const GameLinuxCalls calls={GAME_LINUX_CALLS_VERSION,NULL,system_layout,
        system_clock,system_open,system_close,system_read,system_poll,system_button};
    return &calls;
}
#else
const GameLinuxCalls *game_linux_system_calls(void) { return NULL; }
#endif
