/* Authorized, bounded live input diagnostic. No camera/PL/display operations.
 * Start the pointer at the shared first-button center so a headless click has
 * a known hit region. No observations or missing models are manufactured. */
#define _POSIX_C_SOURCE 200809L
#include "game_linux_io.h"
#include "game_config.h"
#include <linux/input.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    const GameLinuxCalls *real;
    GameLoop *loop;
    uint64_t end,publications,reads,polls,bytes,x,y,down,up,reports,selections;
    uint64_t previous_generation;
    unsigned int levels;
    int bad,uneven,clicks_only,interactive;
    GameEvdevLayout layout;
    GamePumpOutput last;
} Probe;
static int layout(void *v,GameEvdevLayout *out)
{ Probe *p=v; int r=p->real->layout(p->real->context,out); if (!r) p->layout=*out; return r; }
static int clock_ms(void *v,uint64_t *out)
{ Probe *p=v; return p->real->clock_ms(p->real->context,out); }
static int open_input(void *v,const char *path)
{ Probe *p=v; return p->real->open_input(p->real->context,path); }
static int close_input(void *v,int fd)
{ Probe *p=v; return p->real->close_input(p->real->context,fd); }
static ptrdiff_t read_input(void *v,int fd,unsigned char *bytes,size_t capacity)
{
    Probe *p=v; ptrdiff_t n; size_t offset;
    ++p->reads; n=p->real->read_input(p->real->context,fd,bytes,capacity);
    if (n<=0 || (size_t)n>capacity) return n;
    p->bytes+=(uint64_t)n;
    if ((size_t)n%(size_t)p->layout) ++p->uneven;
    for (offset=0;offset+(size_t)p->layout<=(size_t)n;offset+=(size_t)p->layout) {
        GameEvdevEvent event;
        if (!game_evdev_decode(p->layout,bytes+offset,(size_t)p->layout,&event)) { ++p->bad; continue; }
        if (event.type==EV_REL && event.code==REL_X) ++p->x;
        if (event.type==EV_REL && event.code==REL_Y) ++p->y;
        if (event.type==EV_KEY && event.code==BTN_LEFT && event.value==1) ++p->down;
        if (event.type==EV_KEY && event.code==BTN_LEFT && event.value==0) ++p->up;
        if (event.type==EV_SYN && event.code==SYN_REPORT) ++p->reports;
    }
    return n;
}
static int poll_input(void *v,int fd,int wake_fd,int timeout,unsigned *events)
{ Probe *p=v; ++p->polls; return p->real->poll_input(p->real->context,fd,wake_fd,timeout,events); }
static int left_button(void *v,int fd,int *down)
{ Probe *p=v; return p->real->left_button(p->real->context,fd,down); }
static int stopping(void *v)
{
    Probe *p=v; uint64_t now;
    if (p->clicks_only && p->interactive && !p->bad && !p->uneven &&
        p->down>=3 && p->up>=3 && p->selections>=2 && p->last.view.menu.connected &&
        p->last.view.game.state==GAME_PREPARING) return 1;
    return clock_ms(v,&now)!=0 || now>=p->end;
}
static void publish(void *v,const GamePumpOutput *out)
{
    Probe *p=v; GameSnapshot current; const GameSnapshot *s=&out->view.game;
    ++p->publications;
    if (game_app_snapshot(&p->loop->app,&current)!=GAME_OK ||
        current.state!=s->state || current.level_id!=s->level_id || current.generation!=s->generation ||
        current.scene_sequence!=s->scene_sequence || current.captured_ms!=s->captured_ms ||
        current.elapsed_ms!=s->elapsed_ms || current.remaining_ms!=s->remaining_ms ||
        current.stars!=s->stars || current.object_count!=s->object_count ||
        current.ray.segment_count!=s->ray.segment_count || current.scene_valid!=s->scene_valid ||
        current.ready!=s->ready || current.scene_status!=s->scene_status ||
        current.render_budget_exceeded!=s->render_budget_exceeded ||
        out->view.menu.start_enabled!=(s->state==GAME_PREPARING && s->ready) ||
        out->reads>GAME_PUMP_READ_MAX || out->results>GAME_PUMP_RESULT_MAX) ++p->bad;
    if (s->object_count || s->ray.segment_count || s->stars || s->scene_valid || s->ready ||
        s->state==GAME_RUNNING || s->state==GAME_CLEARED || s->elapsed_ms) ++p->bad;
    if (s->generation!=p->previous_generation) {
        p->selections+=s->generation-p->previous_generation; p->previous_generation=s->generation;
        if (s->level_id>=1 && s->level_id<=3) p->levels|=1U<<(s->level_id-1);
        printf("NATIVE_MENU level=%u generation=%llu x=%d y=%d\n",s->level_id,
               (unsigned long long)s->generation,out->view.menu.x,out->view.menu.y); fflush(stdout);
    }
    p->last=*out;
}
static uint64_t cpu_ns(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)) return 0;
    return (uint64_t)t.tv_sec*1000000000+(uint64_t)t.tv_nsec;
}
int main(int argc,char **argv)
{
    Probe p; GameLoop loop; GamePump pump; GameLinuxIO linux_io; GamePumpOutput out;
    GameLinuxCalls calls; GameLinuxHooks hooks; GamePumpIO io;
    GameLoopEvent move,start; GameLoopOutput attempted; GamePumpStatus status;
    uint64_t now,cpu_start,cpu_idle,publications_idle,reads_idle,polls_idle,start_ms;
    int left= -1,blocked,seconds,pass;
    if ((argc!=3 && argc!=4) || (argc==4 && strcmp(argv[3],"clicks")) ||
        (seconds=atoi(argv[2]))<5 || seconds>45) return 2;
    memset(&p,0,sizeof p); p.real=game_linux_system_calls(); p.loop=&loop;
    p.clicks_only=argc==4;
    if (!p.real) return 3;
    calls=(GameLinuxCalls){GAME_LINUX_CALLS_VERSION,&p,layout,clock_ms,open_input,close_input,
                          read_input,poll_input,left_button};
    hooks=(GameLinuxHooks){&p,NULL,stopping,publish,NULL};
    if (game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,&game_default_menu_layout)!=GAME_OK ||
        !game_linux_io_init(&linux_io,&calls,&hooks,-1)) { puts("NATIVE_INIT_FAILED"); return 4; }
    if (!game_linux_io_open(&linux_io,argv[1])) { printf("NATIVE_OPEN_FAILED errno=%d\n",linux_io.error); return 5; }
    if (left_button(&p,linux_io.fd,&left)) { game_linux_io_close(&linux_io); return 6; }
    if (clock_ms(&p,&now)) { game_linux_io_close(&linux_io); return 7; }
    memset(&move,0,sizeof move); move.kind=GAME_LOOP_MOUSE; move.data.mouse.kind=GAME_MOUSE_MOVE;
    move.data.mouse.x=game_default_menu_layout.levels[0].rect.x+game_default_menu_layout.levels[0].rect.width/2;
    move.data.mouse.y=game_default_menu_layout.levels[0].rect.y+game_default_menu_layout.levels[0].rect.height/2;
    if (game_loop_step(&loop,now,&move,&attempted)!=GAME_OK) { game_linux_io_close(&linux_io); return 7; }
    io=game_linux_pump_io(&linux_io);
    if (!game_pump_init(&pump,&loop,&game_default_pump_config,linux_io.layout,&io)) { game_linux_io_close(&linux_io); return 8; }
    printf("NATIVE_ABI input_event=%u type=%u code=%u value=%u long=%u layout=%u button=%d\n",
           (unsigned)sizeof(struct input_event),(unsigned)offsetof(struct input_event,type),
           (unsigned)offsetof(struct input_event,code),(unsigned)offsetof(struct input_event,value),
           (unsigned)sizeof(long),(unsigned)linux_io.layout,left); fflush(stdout);
    p.end=now+800; cpu_start=cpu_ns(); status=game_pump_run(&pump,&out);
    cpu_idle=cpu_ns()-cpu_start; publications_idle=p.publications; reads_idle=p.reads; polls_idle=p.polls;
    printf("NATIVE_IDLE status=%d publications=%llu polls=%llu cpu_us=%llu\n",(int)status,
           (unsigned long long)publications_idle,(unsigned long long)polls_idle,(unsigned long long)(cpu_idle/1000));
    if (status!=GAME_PUMP_STOP) { game_linux_io_close(&linux_io); return 9; }
    if (clock_ms(&p,&start_ms)) { game_linux_io_close(&linux_io); return 9; }
    p.end=start_ms+(uint64_t)seconds*1000;
    p.interactive=1;
    printf("NATIVE_INTERACTIVE_READY seconds=%d cursor=%d,%d: click left three times BEFORE moving\n",
           seconds,move.data.mouse.x,move.data.mouse.y); fflush(stdout);
    status=game_pump_run(&pump,&out);
    memset(&start,0,sizeof start); start.kind=GAME_LOOP_MENU; start.data.menu.kind=GAME_MENU_START;
    blocked=(int)game_pump_event(&pump,&start,&attempted);
    pass=status==GAME_PUMP_STOP && !p.bad && !p.uneven &&
         (p.clicks_only ? (p.down>=3 && p.up>=3 && p.selections>=2) : (p.x && p.y && p.down && p.up)) &&
         p.reports && p.selections && polls_idle && publications_idle<100 &&
         cpu_idle<200000000 && p.last.view.menu.connected &&
         attempted.game.state==GAME_PREPARING && blocked==GAME_INVALID_SCENE;
    game_linux_io_close(&linux_io);
    printf("NATIVE_SUMMARY pass=%d status=%d layout=%u bytes=%llu rel_x=%llu rel_y=%llu down=%llu up=%llu syn=%llu selections=%llu levels=%u publications=%llu polls=%llu reads=%llu bad=%d uneven=%d blocked_start=%d final_state=%d final_generation=%llu remaining=%llu idle_reads=%llu clicks_only=%d\n",
           pass,(int)status,(unsigned)p.layout,(unsigned long long)p.bytes,(unsigned long long)p.x,
           (unsigned long long)p.y,(unsigned long long)p.down,(unsigned long long)p.up,
           (unsigned long long)p.reports,(unsigned long long)p.selections,p.levels,
           (unsigned long long)p.publications,(unsigned long long)p.polls,(unsigned long long)p.reads,
           p.bad,p.uneven,blocked,(int)attempted.game.state,(unsigned long long)attempted.game.generation,
           (unsigned long long)attempted.game.remaining_ms,(unsigned long long)reads_idle,p.clicks_only);
    return pass?0:10;
}
