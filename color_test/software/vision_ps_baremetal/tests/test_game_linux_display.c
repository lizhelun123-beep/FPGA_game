/* Fake platform only. Synthetic porch/clock values below are test vectors,
 * NEVER a panel mode, clock recipe, bitstream qualification or hardware proof. */
#if defined(__linux__) && defined(GAME_DISPLAY_NATIVE_RESOURCES_TEST)
#define _POSIX_C_SOURCE 200809L
#endif
#include "game_linux_display.h"
#include "game_render.h"
#include "game_config.h"
#include <stdlib.h>
#include <string.h>
#if defined(__linux__) && defined(GAME_DISPLAY_NATIVE_RESOURCES_TEST)
/* Include the canonical implementation once in this dedicated unit-test build
 * to reach private resource helpers. Do not also link game_linux_display.c.
 * No alternate platform or copied implementation is introduced. */
static int test_xlnk_ioctl(int,unsigned long,void *);
static uint32_t test_read32(volatile uint32_t *);
#define GAME_DISPLAY_XLNK_IOCTL test_xlnk_ioctl
#define GAME_DISPLAY_READ32 test_read32
#include "game_linux_display.c"
#endif

static unsigned checks;
#define CHECK(c) do { ++checks; if (!(c)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c); exit(1); } } while (0)
enum { QUALIFY=1, ALLOCATE, RELEASE, FLUSH, BARRIER, CONFIGURE, OUTPUT_ON,
       OUTPUT_OFF, FINISH, ACQUIRE, LOAD_LIBRARY, OPEN_DEVICE, MAP_DEVICE,
       UNMAP_DEVICE, CLOSE_DEVICE, UNLOAD_LIBRARY, OWNER_WAIT, WRITE=1000 };
typedef struct {
    unsigned event[4096], events, writes, reads, allocations, releases, idle_write_baseline;
    uint32_t reg[128];
    uint64_t now, physical;
    uint8_t *data;
    int reject, alloc_fail, flush_fail, barrier_fail, configure_fail, output_fail;
    int finish_fail, release_fail, read_fail, write_fail, wait_fail, clock_fail;
    int stall_start, stall_stop, frozen_time, backwards_time, invalid_pointer;
    unsigned pointer_offset;
    unsigned acquire_fail, close_fail, library, device, mapped, closes;
    unsigned holds, recover_owner, foreign_resources;
    int continuous, stall_events;
} Fake;
static uint8_t storage[3*GAME_DISPLAY_SPAN+256], source_memory[GAME_DISPLAY_SPAN+128];
static Fake f;
static GameLinuxDisplay display;
static GameDisplayMode mode;
static VisionCanvas source;

static void event(unsigned e)
{
    CHECK(f.events<sizeof f.event/sizeof f.event[0]);
    f.event[f.events++]=e;
}
static int qualify(void *c,const GameDisplayMode *m)
{
    CHECK(c==&f && m!=NULL); event(QUALIFY); return f.reject;
}
static int acquire(void *c)
{
    CHECK(c==&f); event(ACQUIRE);
    CHECK(f.events>=2 && f.event[0]==QUALIFY && f.event[1]==ACQUIRE);
    if (f.acquire_fail==1) return -1;
    event(LOAD_LIBRARY); f.library=1;
    if (f.acquire_fail==2) return -1;
    event(OPEN_DEVICE); f.device=1;
    if (f.acquire_fail==3) return -1;
    event(MAP_DEVICE); f.mapped=1;
    return f.acquire_fail==4?-1:0;
}
static int close_owner(void *c)
{
    CHECK(c==&f && !display.armed && !display.configured && !display.allocation_owned);
    ++f.closes;
    if (f.mapped) {
        event(UNMAP_DEVICE); if (f.close_fail==1) return -1;
        f.mapped=0;
    }
    if (f.device) {
        event(CLOSE_DEVICE); if (f.close_fail==2) return -1;
        f.device=0;
    }
    if (f.library) {
        event(UNLOAD_LIBRARY); if (f.close_fail==3) return -1;
        f.library=0;
    }
    CHECK(f.foreign_resources==7); /* unrelated allocations/maps are untouched */
    return 0;
}
static int allocate(void *c,size_t size,uint8_t **p,uint64_t *physical)
{
    CHECK(c==&f && size==(size_t)mode.stride*mode.height*(f.continuous?3U:1U)); event(ALLOCATE); ++f.allocations;
    if (f.alloc_fail) return -1;
    *p=f.invalid_pointer?(uint8_t *)(uintptr_t)UINTPTR_MAX:f.data+f.pointer_offset;
    *physical=f.physical;
    return 0;
}
static int release(void *c,uint8_t *p)
{
    CHECK(c==&f); CHECK(p!=NULL); event(RELEASE); ++f.releases;
    CHECK(!(f.reg[0]&1U) && (f.reg[1]&1U));
    return f.release_fail;
}
static int flush(void *c,uint8_t *p,uint64_t physical,size_t size)
{
    if (f.continuous) {
        size_t frame=(size_t)mode.stride*mode.height,offset=(size_t)(p-f.data);
        CHECK(c==&f && physical==f.physical+offset);
        if (f.reg[0]&1U) {
            CHECK(size==frame && offset%frame==0 && offset/frame<3);
            CHECK(offset/frame!=(f.reg[0x28/4]&31U) && offset/frame!=((f.reg[0x28/4]>>16)&31U));
        } else CHECK(p==f.data && size==frame*3);
        event(FLUSH);return f.flush_fail;
    }
    CHECK(c==&f && p==f.data && physical==f.physical && size==(size_t)mode.stride*mode.height);
    CHECK(f.writes==f.idle_write_baseline && !(f.reg[0]&1U) && (f.reg[1]&1U)); event(FLUSH); return f.flush_fail;
}
static int barrier(void *c)
{
    CHECK(c==&f); event(BARRIER); return f.barrier_fail;
}
static int configure(void *c,const GameDisplayMode *m,unsigned timeout)
{
    CHECK(c==&f && m->pixel_hz==mode.pixel_hz && timeout>0 && timeout<=1000);
    CHECK(f.writes==f.idle_write_baseline && !(f.reg[0]&1U) && (f.reg[1]&1U)); event(CONFIGURE); return f.configure_fail;
}
static int output(void *c,int enabled)
{
    CHECK(c==&f); event(enabled?OUTPUT_ON:OUTPUT_OFF); return f.output_fail;
}
static int finish(void *c)
{
    CHECK(c==&f); CHECK(!(f.reg[0]&1U) && (f.reg[1]&1U));
    event(FINISH); if (!f.finish_fail) f.idle_write_baseline=f.writes; return f.finish_fail;
}
static int read_reg(void *c,unsigned offset,uint32_t *value)
{
    CHECK(c==&f && (offset==0 || offset==4 || offset==0x28)); ++f.reads;
    if (f.read_fail) return -1;
    *value=f.reg[offset/4]; return 0;
}
static int write_reg(void *c,unsigned offset,uint32_t value)
{
    CHECK(c==&f && (offset==0 || (f.continuous && offset==4) || offset==0x28 ||
          (offset>=0x50 && offset<=0x64 && offset%4==0)));
    event(WRITE+offset); ++f.writes;
    if (f.write_fail && f.writes==(unsigned)f.write_fail) return -1;
    if (offset==4) { CHECK(value==0x1000);f.reg[1]&=~value;return 0; }
    f.reg[offset/4]=value;
    if (offset==0 && !value && !f.stall_stop) f.reg[1]|=1;
    if (offset==0x50 && !f.stall_start) f.reg[1]&=~1U;
    return 0;
}
static int now_ms(void *c,uint64_t *now)
{
    CHECK(c==&f);
    if (f.clock_fail) return -1;
    *now=f.backwards_time?100U-f.now:f.now;
    return 0;
}
static int wait_ms(void *c,unsigned ms)
{
    CHECK(c==&f && (ms==1 || ms==100));
    if (ms==100) {
        event(OWNER_WAIT); ++f.holds;
        CHECK(!game_display_owner_can_exit(&display));
        CHECK(display.buffer && f.library && f.device && f.mapped);
        CHECK(!f.releases && !f.closes);
        if (f.recover_owner && f.holds==2) { f.stall_stop=0; f.wait_fail=0; }
    }
    if (f.wait_fail) return -1;
    if (!f.frozen_time) f.now+=ms;
    if (f.continuous && !f.stall_events && (f.reg[0]&1U) && f.now%5==0) {
        f.reg[0x28/4]=(f.reg[0x28/4]&~0x1f0000U)|((f.reg[0x28/4]&31U)<<16);
        f.reg[1]|=0x1000;
    }
    return 0;
}
static GameDisplayPlatform platform={GAME_DISPLAY_VERSION,&f,qualify,allocate,release,
    flush,barrier,configure,output,finish,read_reg,write_reg,now_ms,wait_ms,acquire,close_owner};

static void reset(void)
{
    memset(&f,0,sizeof f); memset(storage,0xa5,sizeof storage);
    memset(source_memory,0x6d,sizeof source_memory);
    f.data=(uint8_t *)(((uintptr_t)storage+127U)&~(uintptr_t)63U);
    f.physical=0x18000000U; f.reg[1]=1;
    f.foreign_resources=7;
    game_display_init(&display);
    mode=(GameDisplayMode){GAME_DISPLAY_VERSION,1280,800,5760,40,80,200,3,6,31,
        0,1,100000000,8,1,2,80000000,142857132,79000000,81000000,59000,61000,
        "SYNTHETIC TEST ONLY; NO SINK EVIDENCE"};
    source=(VisionCanvas){source_memory+64,1280,800,3840,3072000};
}
static void prepare(void)
{
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_OK);
}

static void control_profile(const char *bmp)
{
    FILE *file;
    uint8_t first[3],last[3];
    unsigned row;
    reset(); game_display_control_720p_mode(&mode);
    CHECK(game_display_mode_valid(&mode)==GAME_DISPLAY_OK);
    source.height=720; source.capacity=2764800;
    file=fopen(bmp,"rb"); CHECK(file!=NULL);
    CHECK(game_display_read_control_bmp(file,&source)==GAME_DISPLAY_OK);
    CHECK(fclose(file)==0);
    memcpy(first,source.data+8U*3840+8U*3,3);
    memcpy(last,source.data+711U*3840+8U*3,3);
    CHECK(first[0]==0 && first[1]==0 && first[2]==255);
    CHECK(last[0]==255 && last[1]==0 && last[2]==0);
    prepare(); CHECK(display.span==4147200 && f.allocations==1);
    for (row=0;row<720;++row) {
        unsigned j;
        CHECK(memcmp(f.data+(size_t)row*5760,source.data+(size_t)row*3840,3840)==0);
        for (j=3840;j<5760;++j) CHECK(f.data[(size_t)row*5760+j]==0);
    }
    CHECK(f.data[4147200]==0xa5); /* no 800-line overrun */
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_OK);
    CHECK(f.reg[0x50/4]==720 && f.reg[0x54/4]==3840 && f.reg[0x58/4]==5760);
    CHECK(f.reg[0x5c/4]==f.physical && f.reg[0x5c/4+1]==f.physical &&
          f.reg[0x5c/4+2]==f.physical);
    CHECK(game_display_observe(&display,5,5)==GAME_DISPLAY_OK);
    CHECK(game_display_owner_can_exit(&display) && f.releases==1);
    /* Strict file contract: every truncated/header/wrong-height/extra case
     * rejects before ANY allocation or DMA write. Preserve real fixture. */
    for (row=0;row<5;++row) {
        unsigned i,n=row==0?53:2764854;
        FILE *bad=tmpfile(); CHECK(bad!=NULL);
        file=fopen(bmp,"rb"); CHECK(file!=NULL);
        for (i=0;i<n;++i) {
            int c=fgetc(file); CHECK(c!=EOF);
            if ((row==1 && i==28) || (row==2 && i==22)) c=0;
            if (row==3 && i==2764853) break;
            CHECK(fputc(c,bad)!=EOF);
        }
        if (row==4) CHECK(fputc(0,bad)!=EOF);
        CHECK(fclose(file)==0); rewind(bad);
        CHECK(game_display_read_control_bmp(bad,&source)!=GAME_DISPLAY_OK);
        CHECK(fclose(bad)==0);
    }
    printf("PASS fixed720 BMP/copy/padding/single-buffer/order/stop and negative files: %u checks\n",checks);
}
static void start(void)
{
    prepare(); CHECK(game_display_start(&display,5)==GAME_DISPLAY_OK);
}
static int index_of(unsigned e)
{
    unsigned i;
    for (i=0;i<f.events;++i) if (f.event[i]==e) return (int)i;
    return -1;
}
static void modes(void)
{
    GameDisplayMode original;
    GameDisplayPlatform p;
    reset(); original=mode;
    CHECK(game_display_mode_valid(&mode)==GAME_DISPLAY_OK);
#define BAD(field,value) do { mode=original; mode.field=(value); CHECK(game_display_mode_valid(&mode)==GAME_DISPLAY_BAD_MODE); } while (0)
    BAD(version,0); BAD(width,1920); BAD(height,720); BAD(stride,3840);
    BAD(h_front,0); BAD(h_sync,0); BAD(h_back,0); BAD(v_front,0);
    BAD(v_sync,0); BAD(v_back,0); BAD(h_front,UINT32_MAX); BAD(v_back,UINT32_MAX);
    BAD(h_positive,2); BAD(v_positive,2); BAD(reference_hz,0);
    BAD(multiplier,1); BAD(multiplier,65); BAD(divider,0); BAD(divider,107);
    BAD(output_divider,0); BAD(output_divider,129); BAD(multiplier,5);
    BAD(pixel_hz,80000001); BAD(axis_hz,79999999); BAD(sink_pixel_min_hz,80000001);
    BAD(sink_pixel_max_hz,79999999); BAD(sink_pixel_min_hz,0);
    BAD(sink_refresh_min_millihz,60000); BAD(sink_refresh_max_millihz,59000);
    BAD(sink_refresh_max_millihz,59523); BAD(sink_refresh_max_millihz,1000001);
    BAD(sink_refresh_min_millihz,0); BAD(timing_evidence,NULL); BAD(timing_evidence,"");
#undef BAD
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_MODE);
    CHECK(!f.allocations && !f.reads && !f.writes);
    mode=original; f.reject=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_UNQUALIFIED);
    CHECK(!f.reads && !f.allocations);
    CHECK(!f.library && !f.device && !f.mapped && !f.closes);
    CHECK(f.events==1 && f.event[0]==QUALIFY);
    f.reject=0; p=platform; p.barrier=NULL;
    CHECK(game_display_prepare(&display,&mode,&p,&source)==GAME_DISPLAY_BAD_ARGUMENT);
    source.capacity--;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_ARGUMENT);
    CHECK(!f.allocations);
}
static void pixels_and_order(void)
{
    unsigned y;
    size_t x;
    int rs, last;
    reset();
    /* red, green, blue stored B,G,R; final pixel tests full last-row bounds. */
    source.data[0]=0; source.data[1]=0; source.data[2]=255;
    source.data[3]=0; source.data[4]=255; source.data[5]=0;
    source.data[6]=255; source.data[7]=0; source.data[8]=0;
    source.data[source.capacity-1]=0x37;
    prepare();
    CHECK(display.span==4608000 && display.physical==f.physical);
    for (y=0;y<800;++y) {
        CHECK(memcmp(f.data+(size_t)y*5760,source.data+(size_t)y*3840,3840)==0);
        for (x=3840;x<5760;++x) CHECK(f.data[(size_t)y*5760+x]==0);
    }
    for (x=1;x<=64;++x) {
        CHECK(f.data[-(ptrdiff_t)x]==0xa5 && f.data[GAME_DISPLAY_SPAN+x-1]==0xa5);
        CHECK(source_memory[x-1]==0x6d && source_memory[3072000+64+x-1]==0x6d);
    }
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_OK);
    CHECK(display.state==GAME_DISPLAY_SCANNING && display.armed);
    rs=index_of(WRITE); last=index_of(WRITE+0x50);
    CHECK(index_of(FLUSH)>index_of(CONFIGURE));
    CHECK(index_of(BARRIER)>index_of(FLUSH) && index_of(BARRIER)<rs);
    CHECK(f.reg[0]==1 && f.reg[0x28/4]==0);
    CHECK(f.reg[0x5c/4]==f.physical && f.reg[0x60/4]==f.physical && f.reg[0x64/4]==f.physical);
    CHECK(f.reg[0x58/4]==5760 && f.reg[0x54/4]==3840 && f.reg[0x50/4]==800);
    CHECK(last>index_of(WRITE+0x54) && last>index_of(WRITE+0x58));
    CHECK(f.event[last+1]==BARRIER && f.event[last+2]==OUTPUT_ON);
    CHECK(f.writes==8 && f.releases==0);
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_BAD_STATE);
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_STATE);
    CHECK(game_display_observe(&display,30,5)==GAME_DISPLAY_OK);
    CHECK(f.now==30 && f.releases==1 && display.state==GAME_DISPLAY_EMPTY);
    CHECK(index_of(OUTPUT_OFF)>last && index_of(RELEASE)>index_of(FINISH));
    CHECK(index_of(UNMAP_DEVICE)>index_of(RELEASE));
    CHECK(index_of(CLOSE_DEVICE)>index_of(UNMAP_DEVICE));
    CHECK(index_of(UNLOAD_LIBRARY)>index_of(CLOSE_DEVICE));
    CHECK(!f.library && !f.device && !f.mapped && f.foreign_resources==7);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK && f.releases==1);
    reset(); source.stride=3853; source.capacity=799U*3853U+3840U;
    for (y=0;y<800;++y) source.data[(size_t)y*source.stride+3839]=(uint8_t)y;
    prepare();
    for (y=0;y<800;++y)
        CHECK(memcmp(f.data+(size_t)y*5760,source.data+(size_t)y*3853,3840)==0);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
}
static void lifecycle(void)
{
    unsigned stage;
    GameDisplayPlatform native;
    reset();
    CHECK(game_display_owner_can_exit(&display));
    CHECK(game_display_linux_preflight()==GAME_DISPLAY_UNQUALIFIED);
    game_display_linux_platform(&native);
    /* Real closed qualification, instrument all subsequent resource callbacks.
     * The synthetic mode cannot qualify the native adapter. */
    native.context=&f; native.acquire=acquire; native.close=close_owner;
    native.allocate=allocate; native.read=read_reg; native.write=write_reg;
    CHECK(game_display_prepare(&display,&mode,&native,&source)==GAME_DISPLAY_UNQUALIFIED);
    CHECK(!f.events && !f.reads && !f.writes && !f.allocations && !f.closes);
    CHECK(!f.library && !f.device && !f.mapped && game_display_owner_can_exit(&display));
#if defined(__linux__)
    {
        uint64_t before,after;
        CHECK(native.now_ms(NULL,&before)==0);
        CHECK(native.wait_ms(NULL,1)==0 && native.barrier(NULL)==0);
        CHECK(native.now_ms(NULL,&after)==0 && after>=before);
        CHECK(native.now_ms(NULL,NULL)!=0 && native.wait_ms(NULL,1001)!=0);
    }
#endif
    for (stage=1;stage<=4;++stage) {
        reset(); f.acquire_fail=stage;
        CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_IO);
        CHECK(!f.reads && !f.allocations && !f.writes && f.closes==1);
        CHECK(!f.library && !f.device && !f.mapped && game_display_owner_can_exit(&display));
        if (stage>=3) CHECK(index_of(CLOSE_DEVICE)<index_of(UNLOAD_LIBRARY));
        if (stage==4) CHECK(index_of(UNMAP_DEVICE)<index_of(CLOSE_DEVICE));
    }
    reset(); f.read_fail=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_IO);
    CHECK(!f.allocations && f.closes==1 && game_display_owner_can_exit(&display));
    reset(); f.alloc_fail=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_IO);
    CHECK(!f.releases && f.closes==1 && game_display_owner_can_exit(&display));
    for (stage=1;stage<=3;++stage) {
        reset(); start(); f.close_fail=stage;
        CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO);
        CHECK(f.releases==1 && !display.buffer && display.owner_active);
        CHECK(!game_display_owner_can_exit(&display));
        CHECK(stage==3 || f.library); /* no unload following failed unmap/close */
        if (stage<3) CHECK(index_of(UNLOAD_LIBRARY)<0);
        f.close_fail=0;
        CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
        CHECK(f.releases==1 && game_display_owner_can_exit(&display));
    }
    reset(); f.acquire_fail=4; f.close_fail=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_IO);
    CHECK(display.owner_active && !game_display_owner_can_exit(&display));
    CHECK(f.library && f.device && f.mapped && !f.allocations);
    f.close_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.stall_stop=1; f.recover_owner=1; f.wait_fail=1;
    game_display_owner_drain(&display,5);
    CHECK(f.holds==2 && f.releases==1 && f.closes==1);
    CHECK(index_of(RELEASE)>index_of(OWNER_WAIT));
    CHECK(game_display_owner_can_exit(&display) && f.foreign_resources==7);
    game_display_owner_drain(&display,5);
    CHECK(f.releases==1 && f.closes==1);
}
static void failures(void)
{
    unsigned i;
    reset(); f.reg[0]=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BUSY);
    CHECK(!f.allocations && !f.writes);
    reset(); f.reg[1]=0;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BUSY);
    reset(); f.reg[1]|=0x20;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_DMA_ERROR);
    reset(); f.alloc_fail=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_IO);
    CHECK(!display.buffer && !f.releases);
    reset(); f.invalid_pointer=1;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_ARGUMENT);
    CHECK(display.state==GAME_DISPLAY_RETAINED && !f.releases && !f.writes);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_BAD_ARGUMENT && !f.releases);
    for (i=0;i<4;++i) {
        reset();
        if (i==0) f.physical=0;
        if (i==1) f.physical=0x100000000ULL;
        if (i==2) f.physical=0xfffff000ULL;
        if (i==3) f.pointer_offset=1;
        CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_ARGUMENT);
        CHECK(f.releases==1 && !f.writes && storage[0]==0xa5);
    }
    reset(); f.physical++;
    CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_ARGUMENT);
    reset(); prepare(); f.configure_fail=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO);
    CHECK(!f.writes && game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); prepare(); f.flush_fail=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO);
    CHECK(index_of(OUTPUT_ON)<0 && index_of(WRITE)<0 && !display.armed);
    CHECK(!f.writes && game_display_stop(&display,5)==GAME_DISPLAY_OK);
    CHECK(index_of(FINISH)>index_of(FLUSH) && index_of(RELEASE)>index_of(FINISH));
    CHECK(index_of(UNLOAD_LIBRARY)>index_of(RELEASE));
    reset(); prepare(); f.barrier_fail=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO);
    CHECK(!f.writes); f.barrier_fail=0;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    /* Every failed commit write is potentially visible: never free on error. */
    for (i=1;i<=8;++i) {
        reset(); prepare(); f.write_fail=(int)i;
        CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO);
        CHECK(display.state==GAME_DISPLAY_RETAINED && !f.releases);
        f.write_fail=0;
        CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK && f.releases==1);
    }
    reset(); prepare(); f.stall_start=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_TIMEOUT);
    CHECK(f.now==5 && !f.releases);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.stall_stop=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_TIMEOUT);
    CHECK(display.state==GAME_DISPLAY_RETAINED && display.buffer && !f.releases);
    CHECK(index_of(FINISH)<0 && index_of(OUTPUT_OFF)<0);
    CHECK(!f.closes && f.library && f.device && f.mapped);
    CHECK(!game_display_owner_can_exit(&display));
    f.stall_stop=0;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK && f.releases==1);
    reset(); start(); f.read_fail=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO && !f.releases);
    f.read_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.reg[1]|=0x10;
    CHECK(game_display_status(&display)==GAME_DISPLAY_DMA_ERROR);
    CHECK(game_display_observe(&display,30,5)==GAME_DISPLAY_DMA_ERROR && f.releases==1);
    reset(); start(); f.frozen_time=1;
    CHECK(game_display_observe(&display,5,5)==GAME_DISPLAY_TIMEOUT && f.releases==1);
    reset(); start(); f.backwards_time=1;
    CHECK(game_display_observe(&display,5,5)==GAME_DISPLAY_IO && f.releases==1);
    reset(); start(); f.clock_fail=1;
    CHECK(game_display_observe(&display,5,5)==GAME_DISPLAY_IO && !f.releases);
    f.clock_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.wait_fail=1;
    CHECK(game_display_observe(&display,5,5)==GAME_DISPLAY_IO && f.releases==1);
    reset(); start(); f.output_fail=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO && !f.releases);
    f.output_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.finish_fail=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO && !f.releases);
    f.finish_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); prepare(); f.release_fail=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO && display.buffer);
    f.release_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); prepare(); f.output_fail=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO && !f.releases);
    f.output_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); prepare(); f.read_fail=1;
    CHECK(game_display_start(&display,5)==GAME_DISPLAY_IO && !f.writes);
    f.read_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.stall_stop=1; f.frozen_time=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_TIMEOUT && !f.releases);
    f.stall_stop=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); f.barrier_fail=1;
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_IO && !f.releases);
    f.barrier_fail=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start();
    CHECK(game_display_start(&display,0)==GAME_DISPLAY_BAD_ARGUMENT);
    CHECK(game_display_observe(&display,30001,5)==GAME_DISPLAY_BAD_ARGUMENT);
    CHECK(game_display_stop(&display,1001)==GAME_DISPLAY_BAD_ARGUMENT && !f.releases);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
}

static void stopped_update_checks(void)
{
    VisionCanvas alias,bad;
    uint8_t *before=malloc(GAME_DISPLAY_SPAN);
    unsigned count;
    CHECK(before);
    reset(); start(); memcpy(before,display.buffer,display.span);
    alias=(VisionCanvas){display.buffer,1280,800,5760,display.span}; count=f.reads;
    CHECK(game_display_update(&display,&alias,5)==GAME_DISPLAY_BAD_ARGUMENT && f.reads==count);
    bad=source; bad.height=799;
    CHECK(game_display_update(&display,&bad,5)==GAME_DISPLAY_BAD_ARGUMENT && f.reads==count);
    CHECK(!memcmp(before,display.buffer,display.span));
    memset(source.data,0x39,source.capacity);
    f.stall_stop=1;
    CHECK(game_display_update(&display,&source,3)==GAME_DISPLAY_TIMEOUT);
    CHECK(!memcmp(before,display.buffer,display.span) && f.releases==0 && f.allocations==1);
    f.stall_stop=0; CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
    reset(); start(); memset(source.data,0x39,source.capacity);
    CHECK(game_display_update(&display,&source,5)==GAME_DISPLAY_OK);
    CHECK(display.state==GAME_DISPLAY_SCANNING && f.allocations==1 && !f.releases);
    CHECK(display.buffer[0]==0x39 && display.buffer[3839]==0x39 && !display.buffer[3840]);
    CHECK(game_display_update(&display,&source,5)==GAME_DISPLAY_OK && f.allocations==1);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK && f.releases==1);
    free(before);
}

static void snapshot(void)
{
    GameLoop loop;
    GameLoopOutput published, saved;
    reset();
    CHECK(game_loop_init(&loop,&game_default_config,&game_uncalibrated_identity_mapping,
                         &game_default_menu_layout)==GAME_OK);
    CHECK(game_loop_step(&loop,0,NULL,&published)==GAME_OK);
    saved=published;
    CHECK(game_render(&published,&game_default_config,&game_default_menu_layout,
                      &game_default_render_config,&source)==GAME_RENDER_OK);
    CHECK(memcmp(&saved,&published,sizeof saved)==0);
    prepare();
    CHECK(memcmp(&saved,&published,sizeof saved)==0);
    CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
}
/* Exercise the actual resident files through the SAME renderer and lifecycle.
 * This uses the fake platform above, including its synthetic 80MHz mode. It
 * does not qualify that mode for a panel or implement a native allocator. */
static void asset_file(const char *directory,const char *name,VisionCanvas *asset,int w,int h)
{
    char path[4096];
    FILE *file;
    int n=snprintf(path,sizeof path,"%s/%s",directory,name);
    CHECK(n>=0 && (size_t)n<sizeof path);
    *asset=(VisionCanvas){NULL,w,h,(size_t)w*3,(size_t)w*3*(size_t)h};
    asset->data=(uint8_t *)malloc(asset->capacity);
    CHECK(asset->data!=NULL);
    file=fopen(path,"rb"); CHECK(file!=NULL);
    CHECK(game_render_read_bgr(file,asset)==GAME_RENDER_OK);
    CHECK(fclose(file)==0);
}
static void compose(const VisionCanvas *background,const VisionCanvas *pose,int x,int y)
{
    CHECK(game_render_blit(background,&source,0,0,0,0)==GAME_RENDER_OK);
    CHECK(game_render_blit(pose,&source,x,y,1,0xFF00FFU)==GAME_RENDER_OK);
}
static void asset_submission(const char *directory,const char *output_directory)
{
    static const int positions[3][3]={{420,300,0},{650,360,0},{650,360,1}};
    VisionCanvas background,poses[2];
    uint8_t *frozen=(uint8_t *)malloc(GAME_DISPLAY_SPAN);
    unsigned frame,row;
    CHECK(frozen!=NULL);
    asset_file(directory,"background.bgr",&background,1280,800);
    asset_file(directory,"mirror_000.bgr",&poses[0],128,128);
    asset_file(directory,"mirror_090.bgr",&poses[1],128,128);
    for (frame=0;frame<3;++frame) {
        char path[4096];
        FILE *dump;
        int n,changed=0;
        reset();
        source=(VisionCanvas){source_memory+64,1280,800,GAME_DISPLAY_STRIDE,GAME_DISPLAY_SPAN};
        compose(&background,&poses[positions[frame][2]],positions[frame][0],positions[frame][1]);
        prepare();
        for (row=0;row<800;++row) {
            size_t offset=(size_t)row*GAME_DISPLAY_STRIDE;
            CHECK(memcmp(f.data+offset,source.data+offset,GAME_DISPLAY_HSIZE)==0);
            /* Source padding stays dirty; prepare must produce zero padding. */
            CHECK(source.data[offset+GAME_DISPLAY_HSIZE]==0x6d);
            CHECK(f.data[offset+GAME_DISPLAY_HSIZE]==0);
        }
        CHECK(game_display_start(&display,5)==GAME_DISPLAY_OK);
        CHECK(index_of(FLUSH)<index_of(WRITE) && index_of(BARRIER)<index_of(WRITE));
        CHECK(f.reg[0x50/4]==800 && f.reg[0x54/4]==3840 && f.reg[0x58/4]==5760);
        memcpy(frozen,f.data,GAME_DISPLAY_SPAN);
        /* Export the prepared fake scan buffer, not the original CPU canvas. */
        n=snprintf(path,sizeof path,"%s/scanout_%03u.bgr",output_directory,frame);
        CHECK(n>=0 && (size_t)n<sizeof path);
        dump=fopen(path,"wb"); CHECK(dump!=NULL);
        CHECK(fwrite(f.data,1,GAME_DISPLAY_SPAN,dump)==GAME_DISPLAY_SPAN);
        CHECK(fclose(dump)==0);
        /* Preparing the next CPU image must not change the active snapshot. */
        compose(&background,&poses[1-positions[frame][2]],120,180);
        for (row=0;row<800;++row) {
            size_t offset=(size_t)row*GAME_DISPLAY_STRIDE;
            if (memcmp(source.data+offset,frozen+offset,GAME_DISPLAY_HSIZE)!=0) changed=1;
        }
        CHECK(changed);
        CHECK(memcmp(f.data,frozen,GAME_DISPLAY_SPAN)==0);
        CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_STATE);
        CHECK(f.allocations==1 && f.releases==0);
        f.stall_stop=1;
        CHECK(game_display_stop(&display,5)==GAME_DISPLAY_TIMEOUT);
        CHECK(display.state==GAME_DISPLAY_RETAINED && !game_display_owner_can_exit(&display));
        CHECK(f.releases==0 && f.closes==0 && f.library && f.device && f.mapped);
        CHECK(memcmp(f.data,frozen,GAME_DISPLAY_SPAN)==0);
        CHECK(game_display_prepare(&display,&mode,&platform,&source)==GAME_DISPLAY_BAD_STATE);
        f.stall_stop=0;
        CHECK(game_display_stop(&display,5)==GAME_DISPLAY_OK);
        CHECK(game_display_owner_can_exit(&display) && f.releases==1 && f.closes==1);
        CHECK(index_of(RELEASE)>index_of(FINISH) && index_of(UNMAP_DEVICE)>index_of(RELEASE));
        printf("STATIC_ASSET_SUBMISSION frame=%u x=%d y=%d pose=%d stride=5760 span=4608000 "
               "source_isolated=1 halt_timeout_retained=1 halted_before_release=1 platform=FAKE\n",
               frame,positions[frame][0],positions[frame][1],positions[frame][2]*90);
    }
    free(frozen); free(background.data); free(poses[0].data); free(poses[1].data);
    printf("PASS resident asset submission: assets_loaded=3 frames=3 platform=FAKE HDMI=UNVERIFIED checks=%u\n",checks);
}
#if defined(__linux__) && defined(GAME_DISPLAY_NATIVE_RESOURCES_TEST)
static int fixture_file(off_t size)
{
    char name[]="/tmp/codex_display_resource_XXXXXX";
    int fd=mkstemp(name);
    CHECK(fd>=0); CHECK(unlink(name)==0); CHECK(ftruncate(fd,size)==0);
    return fd;
}
static int xlnk_fail_alloc,xlnk_fail_free,xlnk_calls,clock_never_locks;
static int clock_done_without_ready;
static volatile uint32_t *model_clock;
static void *model_vtc;
static int test_xlnk_ioctl(int fd,unsigned long code,void *arg)
{
    uint32_t *a=arg;
    CHECK(fd>=0 && arg!=NULL); ++xlnk_calls;
    if (code==0xc0045802UL) {
        CHECK((a[0]==4147200U || a[0]==3U*4147200U) && ((uint8_t *)arg)[12]==0);
        if (xlnk_fail_alloc) return -1;
        a[1]=1; a[2]=0x18000000; return 0;
    }
    CHECK(code==0xc0045803UL && a[0]==1);
    return xlnk_fail_free?-1:0;
}
static uint32_t test_read32(volatile uint32_t *p)
{
    if (model_clock && p==model_clock+1) {
        *p=(!clock_never_locks && model_clock[0])?(clock_done_without_ready?1U:3U):0U;
        /* Real reset-access counterexample: early VTC access must fault in
         * this ordinary-file model, instead of silently reading fake zeros. */
        if (model_vtc) CHECK(mprotect(model_vtc,4096,*p==3U?PROT_READ|PROT_WRITE:PROT_NONE)==0);
    }
    return *p;
}
static void native_memory_timing_checks(void)
{
    LinuxDisplayResources r;
    GameDisplayMode m;
    const off_t offsets[3]={0,4096,8192};
    uint8_t *v=NULL;
    uint64_t physical=0;
    unsigned scenario;
    game_display_control_720p_mode(&m);
    for (scenario=0;scenario<5;++scenario) {
        linux_resources_init(&r);
        r.memory_fd=fixture_file(12288); r.lease_fd=fixture_file(0);
        CHECK(flock(r.lease_fd,LOCK_EX|LOCK_NB)==0); r.lease_owned=1;
        CHECK(linux_map_regions(&r,offsets)==0);
        ((volatile uint32_t *)r.map[0])[SR/4]=HALTED;
        r.xlnk_fd=fixture_file(65536+4149248);
        xlnk_calls=0; xlnk_fail_alloc=scenario==1; xlnk_fail_free=0;
        clock_never_locks=scenario==2; model_clock=r.map[1]; model_vtc=r.map[2];
        CHECK(mprotect(model_vtc,4096,PROT_NONE)==0);
        clock_done_without_ready=scenario==4;
        if (scenario==1) {
            CHECK(linux_allocate(&r,4147200,&v,&physical)!=0);
            CHECK(r.allocation_uncertain && !v && !physical && xlnk_calls==1);
            CHECK(linux_close(&r)!=0 && r.lease_owned && r.memory_fd>=0);
            /* Fake driver only: destroy this retained fixture, not a live CMA
             * allocation. Production has no method that clears uncertainty. */
            r.allocation_uncertain=0;
        } else {
            CHECK(linux_allocate(&r,4147200,&v,&physical)==0);
            CHECK(v && physical==0x18000000 && r.allocation_id==1 && xlnk_calls==1);
            memset(v,0x27,4147200);
            CHECK(linux_flush(&r,v,physical,4147200)==0);
            CHECK(linux_flush(&r,v+1,physical,4147200)!=0);
            CHECK(linux_flush(&r,v,physical+64,4147200)!=0);
            CHECK(linux_flush(&r,v,physical,4147264)!=0);
            if (scenario==2 || scenario==4) {
                CHECK(linux_configure(&r,&m,2)!=0);
                CHECK(!r.timing_dirty && !model_clock[0]);
            } else {
                CHECK(linux_configure(&r,&m,5)==0 && r.timing_dirty);
                CHECK(model_clock[2]==0x41 && model_clock[3]==0x69a &&
                      model_clock[5]==0x20c4 && model_clock[6]==0xcfafa401 &&
                      model_clock[7]==0xa300ff);
                CHECK(((volatile uint32_t *)r.map[2])[0x60/4]==(720U<<16|1280U));
                CHECK(((volatile uint32_t *)r.map[2])[0x80/4]==(729U<<16|724U));
                clock_done_without_ready=1;
                CHECK(linux_output(&r,1)!=0); /* DRP done alone is insufficient */
                CHECK(linux_write(&r,CR,RUN)==0);
                ((volatile uint32_t *)r.map[0])[SR/4]=0;
                { uint32_t status; CHECK(linux_read(&r,SR,&status)!=0); }
                CHECK(linux_write(&r,CR,0)==0);
                ((volatile uint32_t *)r.map[0])[SR/4]=HALTED;
                { uint32_t status; CHECK(linux_read(&r,SR,&status)==0 && !r.armed); }
                clock_done_without_ready=0;
                CHECK(linux_release(&r,v)!=0); /* timing ownership retained */
                CHECK(linux_output(&r,1)==0);
                r.armed=1;
                CHECK(linux_output(&r,0)!=0 && linux_finish(&r)!=0);
                CHECK(linux_close(&r)!=0);
                r.armed=0;
                ((volatile uint32_t *)r.map[0])[SR/4]=0;
                CHECK(linux_finish(&r)!=0 && r.timing_dirty);
                ((volatile uint32_t *)r.map[0])[SR/4]=HALTED;
                CHECK(linux_output(&r,0)==0 && linux_finish(&r)==0);
                CHECK(!r.timing_dirty && !model_clock[0]);
            }
            if (scenario==3) {
                int calls;
                xlnk_fail_free=1;
                CHECK(linux_release(&r,v)!=0 && r.allocation_uncertain && r.buffer_unmapped);
                calls=xlnk_calls;
                CHECK(linux_release(&r,v)!=0 && linux_close(&r)!=0);
                CHECK(xlnk_calls==calls); /* no second free of a reusable global ID */
                r.allocation_uncertain=0; r.allocation_id=0; r.buffer=NULL;
            } else CHECK(linux_release(&r,v)==0 && !r.allocation_id && !r.buffer);
        }
        model_clock=NULL; model_vtc=NULL; v=NULL; physical=0;
        CHECK(linux_close(&r)==0 && !r.lease_owned);
    }
    /* Exact same uncached allocator ABI,one larger mapping. Only disjoint,
     * neither-current-nor-requested frame flushes are legal while scanning. */
    linux_resources_init(&r);r.memory_fd=fixture_file(12288);r.lease_fd=fixture_file(0);
    CHECK(flock(r.lease_fd,LOCK_EX|LOCK_NB)==0);r.lease_owned=1;
    CHECK(linux_map_regions(&r,offsets)==0);r.xlnk_fd=fixture_file(65536+3U*4147200U+4096);
    xlnk_fail_alloc=xlnk_fail_free=0;
    CHECK(linux_allocate(&r,3U*4147200U,&v,&physical)==0);
    CHECK(linux_flush(&r,v,physical,3U*4147200U)==0);
    ((volatile uint32_t *)r.map[0])[SR/4]=0;
    CHECK(linux_write(&r,CR,CONTINUOUS_RUN)==0);
    CHECK(linux_flush(&r,v,physical,4147200U)!=0);
    CHECK(linux_flush(&r,v+4147200U,physical+4147200U,4147200U)==0);
    CHECK(linux_write(&r,PARK,1)==0);
    CHECK(linux_flush(&r,v+4147200U,physical+4147200U,4147200U)!=0);
    CHECK(linux_flush(&r,v+2U*4147200U,physical+2U*4147200U,4147200U)==0);
    CHECK(linux_write(&r,SR,FRAME_EVENT)==0 && linux_write(&r,SR,0x4090)!=0);
    CHECK(linux_release(&r,v)!=0);
    CHECK(linux_write(&r,CR,0)==0);((volatile uint32_t *)r.map[0])[SR/4]=HALTED;
    { uint32_t status;CHECK(linux_read(&r,SR,&status)==0); }
    CHECK(linux_release(&r,v)==0 && linux_close(&r)==0);
    printf("PASS native callbacks on fake files/MMIO/ioctls: %u checks; no devices\n",checks);
}
static void native_resource_checks(void)
{
    LinuxDisplayResources r;
    const off_t offsets[3]={0,4096,8192},bad[3]={0,1,8192};
    volatile uint32_t *regs;
    GameDisplayPlatform p;
    uint32_t value=0x12345678U;
    char path[80];
    int competitor,retired,reused;
    unsigned i;
    game_display_linux_platform(&p);
    CHECK(game_display_linux_preflight()==GAME_DISPLAY_UNQUALIFIED);
    CHECK(p.acquire(p.context)!=0); /* qualification is not bypassed by a test */
    CHECK(linux_resources.memory_fd==-1 && linux_resources.lease_fd==-1);
    linux_resources_init(&r);
    r.memory_fd=fixture_file(12288); r.lease_fd=fixture_file(0);
    CHECK(flock(r.lease_fd,LOCK_EX|LOCK_NB)==0); r.lease_owned=1;
    CHECK(snprintf(path,sizeof path,"/proc/self/fd/%d",r.lease_fd)>0);
    competitor=open(path,O_RDWR|O_CLOEXEC); CHECK(competitor>=0);
    CHECK(flock(competitor,LOCK_EX|LOCK_NB)!=0);
    CHECK(linux_map_regions(&r,bad)!=0 && !r.map[0] && !r.map[1] && !r.map[2]);
    CHECK(linux_map_regions(&r,offsets)==0);
    CHECK(linux_map_regions(&r,offsets)!=0); /* no overwriting live mappings */
    regs=(volatile uint32_t *)r.map[0]; regs[SR/4U]=HALTED;
    CHECK(linux_read(&r,SR,&value)==0 && value==HALTED);
    CHECK(linux_read(&r,0xa0,&value)!=0 && value==HALTED);
    CHECK(linux_read(&r,3,&value)!=0 && linux_read(&r,SR,NULL)!=0);
    CHECK(linux_write(&r,0xa0,1)!=0 && linux_write(&r,SR,0xffffffffU)!=0);
    CHECK(linux_write(&r,CR,4)!=0 && regs[CR/4U]==0); /* no VDMA reset */
    CHECK(linux_write(&r,VSIZE,800)!=0 && linux_write(&r,VSIZE,720)==0);
    CHECK(linux_write(&r,HSIZE,3840)==0 && linux_write(&r,STRIDE,5760)==0);
    CHECK(linux_write(&r,STRIDE,3840)!=0);
    CHECK(linux_write(&r,ADDRESS,0xfffff000U)!=0);
    CHECK(linux_write(&r,ADDRESS,1)!=0 && linux_write(&r,ADDRESS,0)!=0);
    r.buffer=(uint8_t *)r.map[0]; r.physical=0x18000000U; r.span=4147200U;
    CHECK(linux_write(&r,ADDRESS,0x18001000U)!=0);
    for (i=0;i<3;++i) CHECK(linux_write(&r,ADDRESS+4U*i,0x18000000U)==0);
    regs[PARK/4U]=0xa5a5003fU;
    CHECK(linux_write(&r,PARK,0)!=0);
    CHECK(linux_write(&r,PARK,0xa5a50020U)==0);
    CHECK(linux_read(&r,PARK,&value)==0 && value==0xa5a50020U);
    CHECK(linux_write(&r,CR,RUN)==0 && r.armed);
    CHECK(linux_close(&r)!=0 && r.memory_fd>=0 && r.lease_fd>=0 && r.map[0]);
    regs[SR/4U]=0;
    CHECK(linux_write(&r,CR,0)==0 && r.armed);
    CHECK(linux_read(&r,SR,&value)==0 && r.armed);
    CHECK(linux_close(&r)!=0); /* RS clear alone does not authorize unmap */
    regs[SR/4U]=HALTED;
    CHECK(linux_read(&r,SR,&value)==0 && !r.armed);
    /* Other register regions stay unchanged by every public MM2S operation. */
    for (i=0;i<1024;++i) {
        CHECK(((volatile uint32_t *)r.map[1])[i]==0);
        CHECK(((volatile uint32_t *)r.map[2])[i]==0);
    }
    retired=r.memory_fd;
    CHECK(linux_close(&r)==0);
    CHECK(!r.map[0] && !r.map[1] && !r.map[2] && r.memory_fd==-1 && r.lease_fd==-1);
    CHECK(fcntl(retired,F_GETFD)==-1 && errno==EBADF);
    CHECK(flock(competitor,LOCK_EX|LOCK_NB)==0); CHECK(close(competitor)==0);
    reused=fixture_file(0);
    CHECK(linux_close(&r)==0 && fcntl(reused,F_GETFD)>=0); CHECK(close(reused)==0);
    /* A partly acquired owner releases only acquired mappings/descriptors. */
    linux_resources_init(&r); r.memory_fd=fixture_file(4096); r.lease_fd=fixture_file(0);
    CHECK(flock(r.lease_fd,LOCK_EX|LOCK_NB)==0); r.lease_owned=1;
    r.map[0]=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,r.memory_fd,0);
    CHECK(r.map[0]!=MAP_FAILED && linux_close(&r)==0);
    CHECK(linux_close(&r)==0);
    printf("PASS native Linux register resources: %u checks; ordinary temporary files only; device/MMIO/DMA=NOT_RUN\n",checks);
}
#endif
static void continuous_checks(void)
{
    size_t frame;
    unsigned i,configs=0,finishes=0;
    reset();f.continuous=1;
    game_display_control_720p_mode(&mode);source.height=720;
    frame=(size_t)mode.stride*mode.height;
    CHECK(game_display_prepare_continuous(&display,&mode,&platform,&source)==GAME_DISPLAY_OK);
    CHECK(display.span==3*frame && display.frame_count==3);
    CHECK(game_display_start(&display,100)==GAME_DISPLAY_OK);
    CHECK(f.reg[0]==0x10001 && f.reg[0x5c/4]==f.physical && f.reg[0x60/4]==f.physical+frame && f.reg[0x64/4]==f.physical+2*frame);
    memset(source.data,0x32,source.capacity);
    CHECK(game_display_update(&display,&source,100)==GAME_DISPLAY_OK);
    CHECK(display.current_slot==1 && display.fresh_frame_events==2);
    CHECK(f.data[0]==0x6d && f.data[frame]==0x32 && f.data[2*frame]==0x6d);
    memset(source.data,0x54,source.capacity);
    CHECK(game_display_update(&display,&source,100)==GAME_DISPLAY_OK);
    CHECK(display.current_slot==2 && display.fresh_frame_events==4);
    CHECK(f.data[0]==0x6d && f.data[frame]==0x32 && f.data[2*frame]==0x54);
    for (i=0;i<f.events;++i) { if (f.event[i]==CONFIGURE) ++configs;if (f.event[i]==FINISH || f.event[i]==OUTPUT_OFF) ++finishes; }
    CHECK(configs==1 && finishes==0 && f.reg[0]==0x10001);
    /* New store copied,but missing fresh events must retain every allocation.
     * The active store remains byte-identical;another submission is refused. */
    f.stall_events=1;
    CHECK(game_display_update(&display,&source,20)==GAME_DISPLAY_TIMEOUT);
    CHECK(display.state==GAME_DISPLAY_RETAINED && !f.releases && f.data[2*frame]==0x54);
    CHECK(game_display_update(&display,&source,20)==GAME_DISPLAY_BAD_STATE);
    CHECK(game_display_stop(&display,100)==GAME_DISPLAY_OK && f.releases==1 && game_display_owner_can_exit(&display));
    printf("PASS continuous safety: %u checks;three stores,ordered handoff,no timing restart,timeout retains;fake only\n",checks);
}
int main(int argc,char **argv)
{
#if defined(__linux__) && defined(GAME_DISPLAY_NATIVE_RESOURCES_TEST)
    if (argc==2 && strcmp(argv[1],"--native-resources")==0) {
        native_resource_checks(); native_memory_timing_checks(); return 0;
    }
#endif
    if (argc==2 && strcmp(argv[1],"--continuous-checks")==0) { continuous_checks();return 0; }
    if (argc==3 && strcmp(argv[1],"--control-bmp")==0) {
        control_profile(argv[2]); return 0;
    }
    if (argc==5 && strcmp(argv[1],"--assets")==0 && strcmp(argv[3],"--output")==0) {
        asset_submission(argv[2],argv[4]); return 0;
    }
    if (argc!=1) {
        fputs("usage: test_game_linux_display [--assets DIR --output DIR]\n",stderr); return 2;
    }
    modes(); pixels_and_order(); failures(); lifecycle(); stopped_update_checks(); snapshot();
    printf("PASS Linux display fake platform: %u checks; no hardware/panel qualification\n",checks);
    return 0;
}
