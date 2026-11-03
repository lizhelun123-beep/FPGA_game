#include "game_baremetal_io.h"
#include "game_beam_config.h"
#include "xparameters.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xgpiops.h"
#include "xtime_l.h"
#include "ov5640.h"
#include "i2c/PS_i2c.h"
#include "sleep.h"
#include <stdio.h>
#include <string.h>

#define CAP XPAR_AXIVDMA_1_BASEADDR
#define DISP XPAR_AXIVDMA_0_BASEADDR
#define CSI XPAR_MIPI_CSI_2_RX_0_S_AXI_LITE_BASEADDR
#define PHY XPAR_MIPI_D_PHY_RX_0_S_AXI_LITE_BASEADDR
#define CLK XPAR_AXI_DYNCLK_0_BASEADDR
#define VTC XPAR_VTC_0_BASEADDR
#define SPAN GAME_CAPTURE_FRAME_SPAN
#define RUN 1U
#define HALTED 1U
#define ERRORS 0x000089f0U
#define EVENT 0x1000U /* IRQFrameCount is START, not EOF. */
#define CAMERA_GPIO 54U

/* SPAN is divisible by cache-line size; slots never share a cache line.
 * Linker locations, NOT guessed physical addresses. No DMA buffer is freed. */
static uint8_t capture_pixels[3U*SPAN] __attribute__((aligned(4096)));
static uint8_t display_pixels[3U*SPAN] __attribute__((aligned(4096)));
static struct {
    XGpioPs gpio;
    XIicPs i2c;
    unsigned prepared, gpio_ready, sensor_ready, capture_armed, display_claimed;
    unsigned display_allocated, timing_dirty, writer, warmed, capture_phase;
    uint64_t sequence;
    uint32_t packets, crc, csi_version;
} owner;

/* First observation survives cleanup and is readable in Vitis/JTAG. Not a
 * persistent file: UART is the export path in this filesystem-free program. */
volatile struct {
    uint32_t valid, cap_cr, cap_sr, cap_park, display_cr, display_sr;
    uint32_t csi_control, counters_valid, counters_coherent, capture_phase;
    uint32_t packets, crc, boundary_valid, boundary[24];
    uint64_t observed_ms;
} game_beam_first_fault;

static void barrier(void) { __asm__ volatile("dmb sy\n\tdsb sy" ::: "memory"); }
uint64_t game_baremetal_now_ms(void)
{
    XTime ticks;
    XTime_GetTime(&ticks);
    return (ticks/COUNTS_PER_SECOND)*1000ULL +
        (ticks%COUNTS_PER_SECOND)*1000ULL/COUNTS_PER_SECOND;
}
static int halted(UINTPTR base, unsigned offset)
{
    barrier();
    return !(Xil_In32(base+offset)&RUN) && (Xil_In32(base+offset+4U)&HALTED);
}
static int poll(UINTPTR address, uint32_t mask, uint32_t value, unsigned timeout)
{
    uint64_t start=game_baremetal_now_ms();
    unsigned i;
    for (i=0; i<=timeout; ++i) {
        barrier();
        if ((Xil_In32(address)&mask)==value) return 0;
        if (game_baremetal_now_ms()-start>=timeout || i==timeout) break;
        usleep(1000);
    }
    return -1;
}
static int snapshot(uint32_t *packets, uint32_t *crc)
{
    uint32_t sequence;
    unsigned i;
    uint64_t start=game_baremetal_now_ms();
    if (owner.csi_version==0x10001U && GAME_BEAM_BASELINE_LIVE) {
        /* Historical1.1 has only direct counter CSRs. No write to0x10/0x14:
         * those addresses can alias older registers. Repeated reads reject
         * visible changes, but do NOT establish a coherent CDC snapshot.
         * Keep the CRC rejection rule; label this observation explicitly. */
        for (i=0; i<1000U; ++i) {
            uint32_t p=Xil_In32(CSI+4U),c=Xil_In32(CSI+8U);
            barrier();
            if (Xil_In32(CSI+4U)==p && Xil_In32(CSI+8U)==c) {
                *packets=p; *crc=c; return 0;
            }
            if (game_baremetal_now_ms()-start>=100U) break;
        }
        return -1;
    }
    if ((owner.csi_version!=0x10002U && owner.csi_version!=0x10003U) ||
        (Xil_In32(CSI+0x14U)&1U)) return -1;
    sequence=Xil_In32(CSI+0x10U)+1U;
    Xil_Out32(CSI+0x10U,1U); barrier();
    for (i=0; i<=1000U; ++i) {
        if (!(Xil_In32(CSI+0x14U)&1U) && Xil_In32(CSI+0x10U)==sequence) {
            *packets=Xil_In32(CSI+4U); *crc=Xil_In32(CSI+8U);
            barrier();
            return Xil_In32(CSI+0x10U)==sequence &&
                !(Xil_In32(CSI+0x14U)&1U) ? 0 : -1;
        }
        if (game_baremetal_now_ms()-start>=100U) break;
        usleep(100);
    }
    return -1;
}
static int read_boundary(uint32_t words[24])
{
    uint32_t packets,crc,sequence;
    unsigned i;
    if (snapshot(&packets,&crc)) return -1;
    sequence=Xil_In32(CSI+0x10U);
    for (i=0; i<24U; ++i) {
        Xil_Out32(CSI+0x18U,i); barrier();
        if ((Xil_In32(CSI+0x18U)&255U)!=i) return -1;
        words[i]=Xil_In32(CSI+0x1cU);
    }
    return words[0]==0x42564f31U && Xil_In32(CSI+0x10U)==sequence &&
        !(Xil_In32(CSI+0x14U)&1U) ? 0 : -1;
}
static int boundary_arm(void)
{
    uint32_t before[24],after[24],epoch;
    unsigned i;
    uint64_t start=game_baremetal_now_ms();
    if (owner.csi_version!=0x10003U) return 0;
    if (read_boundary(before)) return -1;
    epoch=before[6]+1U;
    Xil_Out32(CSI+0x18U,1U<<30); barrier();
    for (i=0; i<100U; ++i) {
        if (read_boundary(after)) return -1;
        if (after[6]==epoch && (after[1]&3U)==2U) return 0;
        if (game_baremetal_now_ms()-start>=100U) break;
        usleep(1000);
    }
    return -1;
}
void game_baremetal_first_fault(const char *stage)
{
    uint32_t words[24],packets,crc;
    unsigned i;
    uint64_t freeze_started;
    if (game_beam_first_fault.valid) return;
    game_beam_first_fault.observed_ms=game_baremetal_now_ms();
    game_beam_first_fault.cap_cr=Xil_In32(CAP+0x30U);
    game_beam_first_fault.cap_sr=Xil_In32(CAP+0x34U);
    game_beam_first_fault.cap_park=Xil_In32(CAP+0x28U);
    game_beam_first_fault.display_cr=Xil_In32(DISP);
    game_beam_first_fault.display_sr=Xil_In32(DISP+4U);
    game_beam_first_fault.csi_control=Xil_In32(CSI);
    game_beam_first_fault.counters_coherent=GAME_BEAM_COUNTERS_COHERENT;
    game_beam_first_fault.capture_phase=owner.capture_phase;
    game_beam_first_fault.valid=1U; /* Original registers retained before any stop. */
    if (!snapshot(&packets,&crc)) {
        game_beam_first_fault.packets=packets; game_beam_first_fault.crc=crc;
        game_beam_first_fault.counters_valid=1U;
    }
    if (owner.csi_version==0x10003U && !read_boundary(words)) {
        if (!(words[1]&1U)) {
            freeze_started=game_baremetal_now_ms();
            Xil_Out32(CSI+0x18U,1U<<31); barrier();
            for (i=0; i<100U; ++i) {
                if (read_boundary(words)) break;
                if (words[1]&1U) break;
                if (game_baremetal_now_ms()-freeze_started>=100U) break;
                usleep(1000);
            }
        }
        if (words[1]&1U) {
            for (i=0; i<24U; ++i) game_beam_first_fault.boundary[i]=words[i];
            game_beam_first_fault.boundary_valid=1U;
        }
    }
    printf("BEAM_FIRST_FAULT stage=%s phase=%u cap_cr=%08lx cap_sr=%08lx park=%08lx display_cr=%08lx display_sr=%08lx counters_valid=%lu coherent=%d packets=%lu crc=%lu\r\n",
        stage,owner.capture_phase,(unsigned long)game_beam_first_fault.cap_cr,
        (unsigned long)game_beam_first_fault.cap_sr,(unsigned long)game_beam_first_fault.cap_park,
        (unsigned long)game_beam_first_fault.display_cr,(unsigned long)game_beam_first_fault.display_sr,
        (unsigned long)game_beam_first_fault.counters_valid,
        GAME_BEAM_COUNTERS_COHERENT,
        (unsigned long)game_beam_first_fault.packets,(unsigned long)game_beam_first_fault.crc);
    if (game_beam_first_fault.boundary_valid)
        for (i=0; i<24U; ++i)
            printf("BEAM_BOUNDARY word=%u value=%08lx\r\n",i,
                (unsigned long)game_beam_first_fault.boundary[i]);
}

int game_baremetal_prepare(void)
{
    XGpioPs_Config *gpio;
    uintptr_t first=(uintptr_t)capture_pixels,last=(uintptr_t)display_pixels;
    if (owner.prepared || !halted(CAP,0x30U) || !halted(DISP,0) ||
        (Xil_In32(CAP+0x34U)&ERRORS) || (Xil_In32(DISP+4U)&ERRORS)) return -1;
    /* Standalone MMU maps this DDR identically. Linker+BSP must agree. */
    if (first<XPAR_PS7_DDR_0_S_AXI_BASEADDR || last<XPAR_PS7_DDR_0_S_AXI_BASEADDR ||
        first+sizeof(capture_pixels)-1U>XPAR_PS7_DDR_0_S_AXI_HIGHADDR ||
        last+sizeof(display_pixels)-1U>XPAR_PS7_DDR_0_S_AXI_HIGHADDR) return -1;
    owner.csi_version=Xil_In32(CSI+0xcU);
    if (owner.csi_version!=GAME_BEAM_CSI_VERSION) return -1;
    gpio=XGpioPs_LookupConfig(XPAR_XGPIOPS_0_DEVICE_ID);
    if (!gpio || XGpioPs_CfgInitialize(&owner.gpio,gpio,gpio->BaseAddr)!=XST_SUCCESS) return -1;
    owner.gpio_ready=1;
    XGpioPs_WritePin(&owner.gpio,CAMERA_GPIO,0);
    XGpioPs_SetDirectionPin(&owner.gpio,CAMERA_GPIO,1);
    XGpioPs_SetOutputEnablePin(&owner.gpio,CAMERA_GPIO,1);
    usleep(1000000);
    XGpioPs_WritePin(&owner.gpio,CAMERA_GPIO,1); usleep(1000000);
    if (i2c_init(&owner.i2c,XPAR_XIICPS_0_DEVICE_ID,100000)!=XST_SUCCESS) return -1;
    owner.sensor_ready=1; /* A partial configure still needs producer shutdown. */
    if (sensor_configure(&owner.i2c)!=XST_SUCCESS || sensor_stop(&owner.i2c)!=XST_SUCCESS) return -1;
    Xil_Out32(XPAR_AXI_GAMMACORRECTION_0_BASEADDR,3U);
    Xil_Out32(PHY,2U);
    Xil_Out32(CSI,3U); barrier(); usleep(1000);
    Xil_Out32(CSI,2U); barrier(); usleep(1000);
    if (snapshot(&owner.packets,&owner.crc) || owner.packets || owner.crc ||
        (Xil_In32(CSI)&0x80000003U)!=2U || boundary_arm()) return -1;
    owner.prepared=1;
    printf("BEAM_CAPTURE_PREPARED csi_version=%08lx counters_coherent=%d display_mask=%u stride=5760 hsize=3840 vsize=720\r\n",
        (unsigned long)owner.csi_version,GAME_BEAM_COUNTERS_COHERENT,GAME_BEAM_DISPLAY_STATUS_MASK);
    return 0;
}

static void capture_state(GameCaptureDmaState *s)
{
    unsigned i;
    barrier();
    s->control=Xil_In32(CAP+0x30U); s->status=Xil_In32(CAP+0x34U);
    s->park=Xil_In32(CAP+0x28U); s->vsize=Xil_In32(CAP+0xa0U);
    s->hsize=Xil_In32(CAP+0xa4U); s->stride=Xil_In32(CAP+0xa8U);
    for (i=0; i<3U; ++i) s->addresses[i]=Xil_In32(CAP+0xacU+i*4U);
}
static int parked(unsigned slot)
{
    GameCaptureDmaState state;
    capture_state(&state);
    return game_capture_parked_slot_valid(&state,(uintptr_t)capture_pixels,slot,owner.writer) &&
        Xil_In32(CAP+0x28U)==state.park ? 0 : -1;
}
static int circular_layout(int allow_initial_halted)
{
    GameCaptureDmaState s;
    unsigned i;
    capture_state(&s);
    if ((s.control&0x00ff101fU)!=0x10003U || (s.status&ERRORS) ||
        (!allow_initial_halted && (s.status&HALTED)) ||
        ((s.park>>24)&31U)>=3U || s.vsize!=720U || s.hsize!=3840U ||
        (s.stride&65535U)!=5760U) return -1;
    for (i=0; i<3U; ++i)
        if (s.addresses[i]!=(uintptr_t)capture_pixels+(size_t)i*SPAN) return -1;
    return 0;
}
static int circular_warmup(void)
{
    uint64_t start=game_baremetal_now_ms();
    unsigned i,phase=0,starts=0;
    owner.capture_phase=1; /* No PARK request and NO CPU frame access here. */
    for (i=0; i<=2000U; ++i) {
        uint32_t status;
        if (circular_layout(phase==0)) break;
        status=Xil_In32(CAP+0x34U);
        if ((status&ERRORS) || (phase && (status&HALTED))) break;
        if (status&HALTED) {
            /* RS was armed before sensor.start. Allow bounded hardware
             * startup, not a fake frame or a later unexpected halt. */
        } else if (!phase || (phase==1 && (status&EVENT))) {
            Xil_Out32(CAP+0x34U,EVENT); barrier(); phase=1;
        } else if (phase==1) phase=2;
        else if (status&EVENT) {
            if (++starts==3U) return circular_layout(0);
            Xil_Out32(CAP+0x34U,EVENT); barrier(); phase=1;
        }
        if (game_baremetal_now_ms()-start>=2000U || i==2000U) break;
        usleep(1000);
    }
    game_baremetal_first_fault("circular_warmup"); return -1;
}
int game_baremetal_capture_check(void)
{
    if (!owner.capture_armed || parked((owner.writer+1U)%3U) ||
        (Xil_In32(CSI)&0x80000003U)!=2U) {
        game_baremetal_first_fault("capture_check"); return -1;
    }
    return 0;
}
static int park_writer(unsigned writer)
{
    uint32_t value=Xil_In32(CAP+0x28U);
    Xil_Out32(CAP+0x28U,(value&~0x1f00U)|(writer<<8));
    Xil_Out32(CAP+0x30U,0x00011001U); barrier();
    return 0;
}
static int fence(unsigned writer,unsigned required,uint64_t *lower_bound,GameLinuxDisplay *display,void (*service_uart)(void))
{
    uint64_t start=game_baremetal_now_ms(),lower=0,first=0,sampled;
    unsigned i,phase=0,count=0;
    for (i=0; i<=2000U; ++i) {
        uint32_t control,status,park;
        if (display) {
            GameDisplayStatus ds=game_display_poll(display);
            if (ds!=GAME_DISPLAY_OK && ds!=GAME_DISPLAY_BUSY) {
                game_baremetal_first_fault("display_retirement"); return -1;
            }
        }
        if (service_uart) service_uart();
        sampled=game_baremetal_now_ms(); /* BEFORE reading the START event. */
        control=Xil_In32(CAP+0x30U); status=Xil_In32(CAP+0x34U); park=Xil_In32(CAP+0x28U);
        if ((control&0x00ff101fU)!=0x11001U || (status&(ERRORS|HALTED)) ||
            ((park>>8)&31U)!=writer) break;
        if (((park>>24)&31U)==writer) {
            if (!phase || (phase==1 && (status&EVENT))) {
                lower=sampled; Xil_Out32(CAP+0x34U,EVENT); barrier(); phase=1;
            } else if (phase==1) phase=2; /* W1C actually observed LOW. */
            else if (status&EVENT) {
                if (!count) first=lower;
                if (++count==required) { if (lower_bound) *lower_bound=first; return 0; }
                lower=sampled; Xil_Out32(CAP+0x34U,EVENT); barrier(); phase=1;
            }
        } else if (phase) break;
        if (sampled-start>=2000U || i==2000U) break;
        usleep(1000);
    }
    game_baremetal_first_fault("capture_retirement"); return -1;
}
static int health(unsigned minimum_packets)
{
    uint32_t packets,crc;
    if (snapshot(&packets,&crc) || (Xil_In32(CSI)&0x80000003U)!=2U ||
        packets-owner.packets<minimum_packets || packets-owner.packets>0x7fffffffU ||
        crc-owner.crc || crc) {
        game_baremetal_first_fault("csi_health"); return -1;
    }
    owner.packets=packets; owner.crc=crc;
    return 0;
}
int game_baremetal_capture_start(void)
{
    unsigned i;
    if (!owner.prepared || owner.capture_armed || !halted(CAP,0x30U) ||
        (Xil_In32(CAP+0x34U)&ERRORS)) return -1;
    memset(capture_pixels,0,sizeof capture_pixels);
    Xil_DCacheFlushRange((INTPTR)capture_pixels,sizeof capture_pixels); barrier();
    owner.capture_armed=1; /* Every subsequent failure must stop before isolation. */
    /* Exact legacy live startup CR. Do not park before proving sensor/CSI
     * stream progress; that used to conflate circular startup with retirement. */
    Xil_Out32(CAP+0x30U,0x10003U);
    for (i=0; i<3U; ++i) Xil_Out32(CAP+0xacU+i*4U,(uint32_t)(uintptr_t)(capture_pixels+i*SPAN));
    Xil_Out32(CAP+0xa8U,5760U); Xil_Out32(CAP+0xa4U,3840U); barrier();
    Xil_Out32(CAP+0xa0U,720U); barrier();
    owner.capture_phase=1;
    if (sensor_start(&owner.i2c)!=XST_SUCCESS || circular_warmup() || health(720U)) return -1;
    printf("BEAM_CAPTURE_CIRCULAR_OK cr=%08lx sr=%08lx park=%08lx\r\n",
        (unsigned long)Xil_In32(CAP+0x30U),(unsigned long)Xil_In32(CAP+0x34U),
        (unsigned long)Xil_In32(CAP+0x28U));
    owner.capture_phase=2;
    owner.writer=(Xil_In32(CAP+0x28U)>>24)&31U;
    if (owner.writer>=3U || park_writer(owner.writer) || fence(owner.writer,2,NULL,NULL,NULL) || health(720U)) return -1;
    printf("BEAM_CAPTURE_PARKED_OK writer=%u cr=%08lx sr=%08lx\r\n",owner.writer,
        (unsigned long)Xil_In32(CAP+0x30U),(unsigned long)Xil_In32(CAP+0x34U));
    owner.warmed=1;
    owner.capture_phase=3;
    return 0;
}
int game_baremetal_capture_copy(uint8_t *cpu,size_t capacity,GameCaptureStamp *stamp,GameLinuxDisplay *display,void (*service_uart)(void))
{
    unsigned row,slot,next;
    uint64_t captured;
    uintptr_t dst=(uintptr_t)cpu,src=(uintptr_t)capture_pixels;
    if (!owner.warmed || !cpu || capacity!=3840U*720U || !stamp ||
        capacity>UINTPTR_MAX-dst || (dst<src+sizeof capture_pixels && src<dst+capacity)) return -1;
    if (game_baremetal_capture_check() || fence(owner.writer,1,&captured,display,service_uart)) return -1;
    slot=owner.writer; next=(slot+1U)%3U;
    if (park_writer(next) || fence(next,2,NULL,display,service_uart)) return -1;
    owner.writer=next;
    if (health(720U) || parked(slot)) return -1;
    /* Invalidate ONLY the excluded store. Never flush dirty CPU data over a
     * device-written frame, and never invalidate a live DMA writer's cache. */
    Xil_DCacheInvalidateRange((INTPTR)(capture_pixels+slot*SPAN),SPAN); barrier();
    for (row=0; row<720U; ++row)
        memcpy(cpu+row*3840U,capture_pixels+(size_t)slot*SPAN+row*5760U,3840U);
    barrier();
    if (parked(slot)) { game_baremetal_first_fault("capture_copy_exclusion"); return -1; }
    *stamp=(GameCaptureStamp){1U,++owner.sequence,captured};
    return 0;
}
int game_baremetal_capture_stop(void)
{
    int sensor_status=0,stop_status=0;
    uint32_t last_p=0,last_c=0,p,c;
    uint64_t start,quiet;
    if (owner.sensor_ready && sensor_stop(&owner.i2c)!=XST_SUCCESS) sensor_status=-1;
    if (owner.capture_armed) {
        start=quiet=game_baremetal_now_ms();
        if (snapshot(&last_p,&last_c)) sensor_status=-1;
        while (!sensor_status && game_baremetal_now_ms()-quiet<50U) {
            if (game_baremetal_now_ms()-start>=500U) { sensor_status=-1; break; }
            usleep(1000);
            if (snapshot(&p,&c)) { sensor_status=-1; break; }
            if (p!=last_p || c!=last_c) quiet=game_baremetal_now_ms();
            last_p=p; last_c=c;
        }
        /* Quiet is NOT FIFO empty. Only actual RS0/HALTED permits isolation. */
        Xil_Out32(CAP+0x30U,Xil_In32(CAP+0x30U)&~RUN); barrier();
        stop_status=poll(CAP+0x34U,HALTED,HALTED,2000U);
        if (!halted(CAP,0x30U)) stop_status=-1;
    }
    if (stop_status) {
        printf("BEAM_CAPTURE_RETAINED cr=%08lx sr=%08lx\r\n",
            (unsigned long)Xil_In32(CAP+0x30U),(unsigned long)Xil_In32(CAP+0x34U));
        return -1; /* All clocks, receiver and static buffers retained. */
    }
    owner.capture_armed=owner.warmed=0;
    if (owner.gpio_ready) {
        Xil_Out32(CSI,0); barrier();
        XGpioPs_WritePin(&owner.gpio,CAMERA_GPIO,0);
        printf("BEAM_CAPTURE_HALTED cr=%08lx sr=%08lx errors=%08lx\r\n",
            (unsigned long)Xil_In32(CAP+0x30U),(unsigned long)Xil_In32(CAP+0x34U),
            (unsigned long)(Xil_In32(CAP+0x34U)&ERRORS));
    }
    return sensor_status;
}

/* Existing portable display owner runs unchanged; this is its BSP platform. */
static int display_qualify(void *ctx,const GameDisplayMode *mode)
{
    (void)ctx;
    return !owner.prepared || mode->height!=720 || game_display_mode_valid(mode)!=GAME_DISPLAY_OK;
}
static int display_acquire(void *ctx)
{ (void)ctx; if (owner.display_claimed) return -1; owner.display_claimed=1; return 0; }
static int display_close(void *ctx)
{ (void)ctx; if (owner.display_allocated || owner.timing_dirty || !halted(DISP,0)) return -1; owner.display_claimed=0; return 0; }
static int display_allocate(void *ctx,size_t size,uint8_t **pixels,uint64_t *physical)
{
    (void)ctx;
    if (!owner.display_claimed || owner.display_allocated || size!=sizeof display_pixels) return -1;
    *pixels=display_pixels; *physical=(uintptr_t)display_pixels; owner.display_allocated=1; return 0;
}
static int display_release(void *ctx,uint8_t *pixels)
{ (void)ctx; if (pixels!=display_pixels || !halted(DISP,0)) return -1; owner.display_allocated=0; return 0; }
static int display_flush(void *ctx,uint8_t *pixels,uint64_t physical,size_t size)
{
    uintptr_t begin=(uintptr_t)display_pixels,address=(uintptr_t)pixels;
    (void)ctx;
    if (address<begin || address-begin>sizeof display_pixels ||
        size>sizeof display_pixels-(address-begin) || physical!=address) return -1;
    Xil_DCacheFlushRange((INTPTR)pixels,size); barrier(); return 0;
}
static int display_barrier(void *ctx) { (void)ctx; barrier(); return 0; }
static int display_now(void *ctx,uint64_t *now)
{ (void)ctx; *now=game_baremetal_now_ms(); return 0; }
static int display_wait(void *ctx,unsigned ms)
{ (void)ctx; if (ms>2000U) return -1; usleep(ms*1000U); return 0; }
static int display_read(void *ctx,unsigned offset,uint32_t *value)
{ (void)ctx; if (offset>0x64U || (offset&3U)) return -1; barrier(); *value=Xil_In32(DISP+offset); return 0; }
static int display_write(void *ctx,unsigned offset,uint32_t value)
{ (void)ctx; if (offset>0x64U || (offset&3U)) return -1; Xil_Out32(DISP+offset,value); barrier(); return 0; }
static int display_finish(void *ctx)
{
    (void)ctx;
    if (!halted(DISP,0)) return -1;
    if (!owner.timing_dirty) return 0;
    if (owner.timing_dirty==2U) {
        if (poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,GAME_BEAM_DISPLAY_STATUS_MASK,1U)) return -1;
        Xil_Out32(VTC,0x03f7ef02U); barrier();
        if (poll(VTC,5U,0U,100U)) return -1;
    }
    Xil_Out32(CLK,0); barrier();
    if (poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,0U,100U)) return -1;
    owner.timing_dirty=0; return 0;
}
static int display_configure(void *ctx,const GameDisplayMode *mode,unsigned timeout)
{
    /* Same fixed720 register values as the existing qualified display profile;
     * clocks/VTC only here. game_display_* owns every MM2S state transition. */
    static const uint32_t clock[6]={0x41,0x69a,0,0x20c4,0xcfafa401,0x00a300ff};
    static const uint32_t timing[][2]={
        {0x60,720U<<16|1280U},{0x68,0},{0x6c,0x7f},
        {0x70,1650},{0x74,750U<<16|750U},{0x78,1430U<<16|1390U},
        {0x7c,1280U<<16|1280U},{0x80,729U<<16|724U},{0x84,1390U<<16|1390U},
        {0x88,1280U<<16|1280U},{0x8c,729U<<16|724U},{0x90,1390U<<16|1390U},{0x94,720U<<16}};
    unsigned i;
    (void)ctx;
    if (display_qualify(NULL,mode) || !halted(DISP,0) || owner.timing_dirty) return -1;
    owner.timing_dirty=1;
    Xil_Out32(CLK,0); barrier();
    if (poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,0U,timeout)) goto failed;
    usleep(1000);
    for (i=0; i<6U; ++i) Xil_Out32(CLK+8U+i*4U,clock[i]);
    barrier(); Xil_Out32(CLK,1); barrier();
    if (poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,GAME_BEAM_DISPLAY_STATUS_MASK,timeout)) goto failed;
    usleep(1000);
    if (poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,GAME_BEAM_DISPLAY_STATUS_MASK,timeout)) goto failed;
    owner.timing_dirty=2;
    Xil_Out32(VTC,0x03f7ef02U); barrier();
    if (poll(VTC,5U,0U,timeout)) goto failed;
    for (i=0; i<sizeof timing/sizeof timing[0]; ++i) Xil_Out32(VTC+timing[i][0],timing[i][1]);
    barrier();
    for (i=0; i<sizeof timing/sizeof timing[0]; ++i)
        if (Xil_In32(VTC+timing[i][0])!=timing[i][1]) goto failed;
    return 0;
failed:
    (void)display_finish(NULL); return -1;
}
static int display_output(void *ctx,int enabled)
{
    (void)ctx;
    if (owner.timing_dirty!=2U || (enabled!=0 && enabled!=1) ||
        (!enabled && !halted(DISP,0)) ||
        poll(CLK+4U,GAME_BEAM_DISPLAY_STATUS_MASK,GAME_BEAM_DISPLAY_STATUS_MASK,1U)) return -1;
    Xil_Out32(VTC,0x03f7ef02U|(enabled?5U:0U)); barrier();
    return poll(VTC,5U,enabled?5U:0U,100U);
}
void game_baremetal_display_platform(GameDisplayPlatform *p)
{
    *p=(GameDisplayPlatform){GAME_DISPLAY_VERSION,NULL,display_qualify,
        display_allocate,display_release,display_flush,display_barrier,
        display_configure,display_output,display_finish,display_read,display_write,
        display_now,display_wait,display_acquire,display_close};
}
