/* Fake DMA platform: queued display can retire during unrelated capture waits.
 * No hardware, addresses, clocks or event timing here qualify a real device. */
#include "game_linux_display.h"
#include "beam_uart_log.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
_Alignas(64) static unsigned char stores[3U*5760U*720U];
static unsigned char image[1280U*720U*3U];
static uint32_t regs[32];
static uint64_t clock_ms;
static unsigned releases,flushes;
static int stall;
static int qualify(void *ctx,const GameDisplayMode *m) {(void)ctx;(void)m;return 0;}
static int acquire(void *ctx) {(void)ctx;return 0;}
static int alloc(void *ctx,size_t n,uint8_t **p,uint64_t *phys)
{(void)ctx;assert(n==sizeof stores);*p=stores;*phys=0x18000000;return 0;}
static int release(void *ctx,uint8_t *p)
{(void)ctx;assert(p==stores && !(regs[0]&1U) && (regs[1]&1U));++releases;return 0;}
static int flush(void *ctx,uint8_t *p,uint64_t physical,size_t n)
{
    const size_t frame=5760U*720U;
    size_t slot=(size_t)(p-stores)/frame;
    (void)ctx;
    assert(physical==0x18000000U+(size_t)(p-stores));
    if(regs[0]&1U) {
        assert(n==frame && slot!=((regs[10]>>16)&31U) && slot!=(regs[10]&31U));
    }
    ++flushes;return 0;
}
static int barrier(void *ctx) {(void)ctx;return 0;}
static int configure(void *ctx,const GameDisplayMode *m,unsigned t) {(void)ctx;(void)m;(void)t;return 0;}
static int output(void *ctx,int on) {(void)ctx;(void)on;return 0;}
static int finish(void *ctx) {(void)ctx;assert(!(regs[0]&1U) && (regs[1]&1U));return 0;}
static int read_reg(void *ctx,unsigned off,uint32_t *v) {(void)ctx;assert(off/4<32);*v=regs[off/4];return 0;}
static int write_reg(void *ctx,unsigned off,uint32_t v)
{
    (void)ctx;assert(off/4<32);
    if(off==4) regs[1]&=~v;
    else {regs[off/4]=v;if(off==0 && !(v&1U)) regs[1]|=1U;if(off==0x50) regs[1]&=~1U;}
    return 0;
}
static int now(void *ctx,uint64_t *v) {(void)ctx;*v=clock_ms;return 0;}
static int wait_ms(void *ctx,unsigned ms)
{
    unsigned i;(void)ctx;
    for(i=0;i<ms;++i) {
        ++clock_ms;
        if(!stall && (regs[0]&1U) && clock_ms%5==0) {
            regs[10]=(regs[10]&~0x1f0000U)|((regs[10]&31U)<<16);regs[1]|=0x1000U;
        }
    }
    return 0;
}
static int close_owner(void *ctx) {(void)ctx;return 0;}
static void test_overlap(void)
{
    GameLinuxDisplay d;
    GameDisplayMode m;
    GameDisplayPlatform p={GAME_DISPLAY_VERSION,NULL,qualify,alloc,release,flush,barrier,
        configure,output,finish,read_reg,write_reg,now,wait_ms,acquire,close_owner};
    VisionCanvas canvas={image,1280,720,3840,sizeof image};
    const size_t frame=5760U*720U;
    unsigned i,saved_flushes;
    uint64_t submitted;
    GameDisplayStatus s;
    memset(regs,0,sizeof regs);regs[1]=1;clock_ms=0;stall=0;
    memset(image,0x25,sizeof image);game_display_init(&d);game_display_control_720p_mode(&m);
    assert(game_display_prepare_continuous(&d,&m,&p,&canvas)==GAME_DISPLAY_OK);
    assert(game_display_start(&d,100)==GAME_DISPLAY_OK);
    regs[1]|=0x1000U; /* Stale START cannot retire a queued store. */
    memset(image,0x51,sizeof image);submitted=clock_ms;
    assert(game_display_submit(&d,&canvas,100)==GAME_DISPLAY_OK);
    assert(d.update_pending && d.current_slot==0 && clock_ms==submitted);
    saved_flushes=flushes;
    assert(game_display_submit(&d,&canvas,100)==GAME_DISPLAY_BUSY && flushes==saved_flushes);
    assert(stores[0]==0x25 && stores[frame]==0x51);
    /* Simulate120ms of necessary capture waiting, servicing display each ms. */
    for(i=0;i<120;++i) {
        s=game_display_poll(&d);assert(s==GAME_DISPLAY_BUSY || s==GAME_DISPLAY_OK);
        if(clock_ms-submitted<15) assert(d.current_slot==0);
        wait_ms(NULL,1);
    }
    assert(!d.update_pending && d.current_slot==1 && d.fresh_frame_events==2);
    assert(clock_ms-submitted==120); /* no serial additional display wait */
    memset(image,0x75,sizeof image);
    assert(game_display_update(&d,&canvas,100)==GAME_DISPLAY_OK && d.current_slot==2);
    assert(d.fresh_frame_events==4 && stores[frame]==0x51 && stores[2*frame]==0x75);
    assert(stores[2*frame+3840]==0); /* initialized padding survives all queues */
    stall=1;
    assert(game_display_submit(&d,&canvas,20)==GAME_DISPLAY_OK);
    wait_ms(NULL,21);
    assert(game_display_poll(&d)==GAME_DISPLAY_TIMEOUT && d.state==GAME_DISPLAY_RETAINED);
    assert(!releases && stores[2*frame]==0x75);
    assert(game_display_submit(&d,&canvas,100)==GAME_DISPLAY_BAD_STATE);
    assert(game_display_stop(&d,100)==GAME_DISPLAY_OK && releases==1 && game_display_owner_can_exit(&d));
}
static char wire[4096];
static unsigned used,budget;
static int sink(unsigned char ch) {if(!budget)return 0;--budget;wire[used++]=(char)ch;return 1;}
static int append(BeamUartLog *q,const char *fmt,...)
{int n;va_list a;va_start(a,fmt);n=beam_uart_log_vprintf(q,fmt,a);va_end(a);return n;}
static void test_uart(void)
{
    BeamUartLog q={{0},0,0};unsigned i;
    assert(append(&q,"BEAM_DETECT value=%d\r\n",123)>0);
    budget=0;assert(beam_uart_log_poll(&q,sink,64)==1 && !used);
    budget=3;assert(beam_uart_log_poll(&q,sink,64)==1 && used==3);
    assert(append(&q,"do not append in-flight")<0);
    for(i=0;q.used && i<100;++i){budget=2;assert(beam_uart_log_poll(&q,sink,64)>=0);}
    assert(!q.used && !q.offset && !strcmp(wire,"BEAM_DETECT value=123\r\n"));
    memset(wire,0,sizeof wire);used=0;
    assert(append(&q,"%03000d",1)<0 && !q.used); /* no truncated packet accepted */
    assert(append(&q,"complete\n")>0);budget=64;
    assert(!beam_uart_log_poll(&q,sink,64) && !strcmp(wire,"complete\n"));
}
int main(void) {test_overlap();test_uart();puts("PASS queued display two-START retirement/overlap/timeout/HALTED and bounded UART queue");return 0;}
