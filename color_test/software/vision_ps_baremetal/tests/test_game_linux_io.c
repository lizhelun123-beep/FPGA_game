/* Fake syscalls only. Never open a real input/clock/poll/ioctl endpoint. */
#include "game_linux_io.h"
#include "game_config.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(c) do { ++checks; if (!(c)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c); exit(1); } } while (0)
typedef struct {
    uint64_t now;
    int clocks,fail_at,layout_error,opens,closes,reads,polls,timeout,polled_fd;
    int open_result,poll_result,button_result,down,wakes,wake_error;
    unsigned events,published,buttons;
    ptrdiff_t read_result;
    unsigned char bytes[128]; size_t used,length,chunk;
    GamePumpOutput saved;
} Fake;
static int layout(void *ctx,GameEvdevLayout *out)
{ Fake *f=ctx; *out=GAME_EVDEV_LE32; return f->layout_error; }
static int clock_ms(void *ctx,uint64_t *out)
{ Fake *f=ctx; ++f->clocks; if (f->fail_at==f->clocks) return -EIO; *out=f->now; return 0; }
static int open_input(void *ctx,const char *path)
{ Fake *f=ctx; CHECK(!strcmp(path,"mock-input")); ++f->opens; return f->open_result; }
static int close_input(void *ctx,int fd)
{ Fake *f=ctx; CHECK(fd==7); ++f->closes; return 0; }
static ptrdiff_t read_input(void *ctx,int fd,unsigned char *out,size_t capacity)
{
    Fake *f=ctx; size_t n=f->length-f->used;
    CHECK(fd==7); ++f->reads;
    if (!n) return f->read_result;
    if (n>capacity) n=capacity;
    if (f->chunk && n>f->chunk) n=f->chunk;
    memcpy(out,f->bytes+f->used,n); f->used+=n; return (ptrdiff_t)n;
}
static int poll_input(void *ctx,int fd,int wake_fd,int timeout,unsigned *events)
{
    Fake *f=ctx; CHECK(wake_fd== -1 || wake_fd==11); CHECK(timeout>0);
    ++f->polls; f->timeout=timeout; f->polled_fd=fd; *events=f->events;
    if (!f->poll_result) f->now+=(unsigned)timeout;
    return f->poll_result;
}
static int button(void *ctx,int fd,int *down)
{ Fake *f=ctx; CHECK(fd==7); ++f->buttons; *down=f->down; return f->button_result; }
static void publish(void *ctx,const GamePumpOutput *output)
{ Fake *f=ctx; ++f->published; f->saved=*output; }
static int wake(void *ctx) { Fake *f=ctx; ++f->wakes; return f->wake_error; }
static GamePumpIO init(Fake *f,GameLinuxIO *io,int wake_fd)
{
    GameLinuxCalls calls={GAME_LINUX_CALLS_VERSION,f,layout,clock_ms,open_input,close_input,
                         read_input,poll_input,button};
    GameLinuxHooks hooks={f,NULL,NULL,publish,wake};
    memset(f,0,sizeof *f); f->open_result=7; f->read_result=-EAGAIN;
    CHECK(game_linux_io_init(io,&calls,&hooks,wake_fd));
    CHECK(f->opens==0 && io->fd== -1 && io->layout==GAME_EVDEV_LE32);
    return game_linux_pump_io(io);
}
static void test_calls(void)
{
    Fake f; GameLinuxIO io; GamePumpIO api=init(&f,&io,-1);
    unsigned char bytes[8]; GameReadResult read;
    int i;
    CHECK(game_linux_io_open(&io,"mock-input")); CHECK(io.epoch==1);
    CHECK(!game_linux_io_open(&io,"mock-input") && f.opens==1);
    f.read_result=-EINTR; read=api.read(&io,bytes,sizeof bytes); CHECK(read.status==GAME_READ_INTERRUPTED && io.fd==7);
    f.read_result=-EAGAIN; CHECK(api.read(&io,bytes,sizeof bytes).status==GAME_READ_AGAIN);
    f.length=3; memcpy(f.bytes,"abc",3); read=api.read(&io,bytes,sizeof bytes);
    CHECK(read.status==GAME_READ_DATA && read.count==3 && !memcmp(bytes,"abc",3));
    f.now=15; CHECK(api.wait_until(&io,20)==GAME_WAIT_READY && f.timeout==5);
    CHECK(api.wait_until(&io,20)==GAME_WAIT_READY && f.polls==1);
    CHECK(api.wait_until(&io,UINT64_MAX)==GAME_WAIT_READY && f.timeout==INT_MAX);
    f.poll_result=-EINTR; CHECK(api.wait_until(&io,f.now+10)==GAME_WAIT_INTERRUPTED);
    f.poll_result=-EIO; CHECK(api.wait_until(&io,f.now+10)==GAME_WAIT_ERROR);
    f.down=1; CHECK(api.resync(&io)==0); f.down=0; CHECK(api.resync(&io)==1);
    f.button_result=-EINTR; CHECK(api.resync(&io)==0 && io.fd==7);
    f.button_result=-ENODEV; CHECK(api.resync(&io)== -1 && io.fd== -1 && f.closes==1);
    game_linux_io_close(&io); CHECK(f.closes==1);
    for (i=0;i<4;++i) {
        int errors[]={0,-ENODEV,-EIO,9};
        GameReadStatus statuses[]={GAME_READ_EOF,GAME_READ_DISCONNECTED,GAME_READ_ERROR,GAME_READ_ERROR};
        CHECK(game_linux_io_open(&io,"mock-input"));
        f.read_result=errors[i]; CHECK(api.read(&io,bytes,sizeof bytes).status==statuses[i]);
        CHECK(io.fd== -1 && f.closes==i+2);
        CHECK(api.read(&io,bytes,sizeof bytes).status==GAME_READ_DISCONNECTED);
    }
    io.epoch=UINT64_MAX; CHECK(!game_linux_io_open(&io,"mock-input"));
    api=init(&f,&io,11); CHECK(game_linux_io_open(&io,"mock-input"));
    f.poll_result=1; f.events=GAME_LINUX_WAKE; CHECK(api.wait_until(&io,10)==GAME_WAIT_READY && f.wakes==1);
    f.wake_error=-EIO; CHECK(api.wait_until(&io,10)==GAME_WAIT_ERROR);
    f.events=GAME_LINUX_FAULT; CHECK(api.wait_until(&io,10)==GAME_WAIT_READY && io.fd== -1);
    CHECK(api.connection(&io).connected==0); f.events=0; f.poll_result=0;
    CHECK(api.wait_until(&io,10)==GAME_WAIT_READY && f.polled_fd== -1);
    puts("PASS syscall results / bounded EINTR / errno / EOF detach / no fd retry / deadline clamp / wake drain / key-state resync");
}
static void record(Fake *f,unsigned type,unsigned code,int value)
{
    unsigned char *p=f->bytes+f->length;
    unsigned i; uint32_t u=(uint32_t)value;
    memset(p,0,16); p[8]=(unsigned char)type; p[10]=(unsigned char)code; p[11]=(unsigned char)(code>>8);
    for (i=0;i<4;++i) p[12+i]=(unsigned char)(u>>(8*i));
    f->length+=16;
}
static void test_pump(void)
{
    Fake f; GameLinuxIO io; GamePumpIO api=init(&f,&io,-1);
    GameLoop loop,before; GamePump pump; GamePumpOutput out;
    unsigned pubs,reads; int i;
    CHECK(game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,&game_default_menu_layout)==GAME_OK);
    CHECK(game_linux_io_open(&io,"mock-input"));
    f.now=UINT64_C(4294967296); CHECK(game_pump_init(&pump,&loop,&game_default_pump_config,io.layout,&api));
    record(&f,1,272,0); record(&f,2,0,1040); record(&f,2,1,114);
    record(&f,1,272,1); record(&f,1,272,0); record(&f,0,0,0); f.chunk=7;
    for (i=0;i<10 && !f.saved.view.game.generation;++i) CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE);
    CHECK(f.saved.view.game.level_id==3 && f.saved.view.game.generation==1);
    CHECK(f.saved.view.game.state==GAME_PREPARING && !f.saved.view.game.object_count && !f.saved.view.game.stars);
    f.read_result=0; CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE);
    CHECK(io.fd== -1 && !f.saved.view.menu.connected);
    reads=(unsigned)f.reads;
    CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE && (unsigned)f.reads==reads && f.polled_fd== -1);
    CHECK(game_linux_io_open(&io,"mock-input") && io.epoch==2);
    f.read_result=-EAGAIN; CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE);
    CHECK(f.saved.view.menu.connected && f.saved.view.game.generation==1);
    /* SYN_DROPPED waits through REPORT before any EVIOCGKEY-style query. */
    f.used=f.length=0; f.chunk=0; record(&f,0,3,0); record(&f,0,0,0);
    CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE && f.buttons==0);
    f.down=1; CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE && f.buttons==1 && !out.view.menu.connected);
    f.down=0; CHECK(game_pump_once(&pump,&out)==GAME_PUMP_CONTINUE && f.buttons==2 && out.view.menu.connected);
    /* Fatal clock failure BEFORE reads cannot tick, consume or publish. */
    before=loop; pubs=f.published; reads=(unsigned)f.reads; f.fail_at=f.clocks+1;
    CHECK(game_pump_once(&pump,&out)==GAME_PUMP_BAD_CLOCK);
    CHECK(!memcmp(&before,&loop,sizeof loop) && f.published==pubs && (unsigned)f.reads==reads);
    CHECK(api.now_ms(&io)==GAME_PUMP_CLOCK_ERROR);
    game_linux_io_close(&io);
    /* Failure sampled after a read cannot consume that read as mouse actions. */
    api=init(&f,&io,-1); CHECK(game_linux_io_open(&io,"mock-input"));
    CHECK(game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,&game_default_menu_layout)==GAME_OK);
    CHECK(game_pump_init(&pump,&loop,&game_default_pump_config,io.layout,&api));
    record(&f,1,272,0); record(&f,2,0,1040); record(&f,2,1,114);
    record(&f,1,272,1); record(&f,1,272,0); record(&f,0,0,0);
    f.fail_at=f.clocks+2; CHECK(game_pump_once(&pump,&out)==GAME_PUMP_BAD_CLOCK);
    CHECK(loop.app.session.view.generation==0 && f.published==0);
    game_linux_io_close(&io);
    puts("PASS Linux-call seam -> fragmented evdev -> pump -> complete menu publication / epoch / dropped-report ioctl ordering / clock-failure isolation");
}
static void test_invalid(void)
{
    Fake f; GameLinuxIO io; GamePumpIO api=init(&f,&io,-1);
    GameLinuxCalls calls=io.calls;
    f.layout_error=-EINVAL; CHECK(!game_linux_io_init(&io,&calls,NULL,-1));
    f.layout_error=0; f.fail_at=f.clocks+1; CHECK(!game_linux_io_init(&io,&calls,NULL,-1));
    f.fail_at=0; CHECK(game_linux_io_init(&io,&calls,NULL,-1));
    f.now=GAME_PUMP_CLOCK_ERROR; CHECK(api.now_ms(&io)==GAME_PUMP_CLOCK_ERROR);
    CHECK(!game_linux_io_init(&io,&calls,NULL,11));
    CHECK(!game_linux_io_init(&io,NULL,NULL,-1));
    CHECK(!game_linux_io_open(&io,"mock-input"));
    puts("PASS layout/init failure / absent callbacks / reserved and failed clocks / wake ownership");
}
int main(void)
{
    test_calls(); test_pump(); test_invalid();
    printf("game_linux_io: %u assertions passed (fake syscalls; no Linux runtime or device access)\n",checks);
    return 0;
}
