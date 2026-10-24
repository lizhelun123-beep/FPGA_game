/* Fake clock/FIFO only. Production UART arbitration is extracted by Python. */
#include "vision_perf.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
typedef uint32_t u32;
#define STDOUT_BASEADDRESS 0U
#define XUARTPS_SR_OFFSET 0U
#define XUARTPS_FIFO_OFFSET 4U
#define XUARTPS_SR_TXFULL 16U
#define XUARTPS_SR_TXEMPTY 8U
#define XUARTPS_SR_TACTIVE 2048U
static uint64_t clock_us;
static unsigned int space = 64, writes;
static SceneStream scene_stream;
uint64_t vision_perf_now(void) { return clock_us; }
static unsigned int NowMs(void) { return (unsigned int)(clock_us / 1000U); }
static uint32_t Xil_In32(unsigned int address)
{
    assert(address == XUARTPS_SR_OFFSET);
    return space == 64 ? XUARTPS_SR_TXEMPTY :
        XUARTPS_SR_TACTIVE | (space ? 0U : XUARTPS_SR_TXFULL);
}
static void Xil_Out32(unsigned int address, unsigned int byte)
{
    assert(address == XUARTPS_FIFO_OFFSET && space);
    --space; ++writes; putchar((int)byte);
}
#include "perf_uart.inc"
static void poll(void)
{
    unsigned int before = writes;
    SceneUartPoll();
    assert(writes - before <= 64U);
}
static void drain(void) { space = 64; }
static int partial(void *context, unsigned char byte)
{
    unsigned int *limit = context;
    if (!*limit) return 0;
    --*limit; putchar(byte); return 1;
}
int main(void)
{
    VisionDetection object;
    unsigned int i, limit;
#ifdef _WIN32
    _setmode(1, _O_BINARY);
#endif
    vision_perf_record(PERF_COPY, 7);
    vision_perf_record(PERF_COPY, 13);
    assert(vision_perf_stats[PERF_COPY].n == 2);
    assert(vision_perf_stats[PERF_COPY].total == 20);
    assert(vision_perf_stats[PERF_COPY].maximum == 13);
    vision_perf_record(PERF_RAY, UINT64_C(0x100000001));
    vision_perf_record(PERF_RAY, 5);
    assert(vision_perf_stats[PERF_RAY].total == UINT64_C(0x100000006));
    scene_stream_init(&scene_stream, 8, 115200);
    poll(); /* boot occupies 60 bytes; no diagnostic admission into that FIFO */
    assert(writes == 60);
    drain(); clock_us = 1000; poll();
    drain(); clock_us = 5000000;
    poll(); /* snapshot row 0, <=61 bytes */
    assert(writes == 121);
    for (i = 0; i < 40; ++i) { drain(); poll(); }
    memset(&object, 0, sizeof object);
    object.type = VISION_TARGET;
    object.center_x = 100; object.center_y = 200;
    clock_us = 5100000;
    scene_stream_publish(&scene_stream, &object, 1, 1, 77, 5100);
    clock_us += 123000; drain(); poll(); /* first 64 bytes */
    assert(scene_stream.offset == 64 && scene_stream.length == 108);
    poll(); /* FIFO full: no wait and no diagnostic interleaving */
    assert(scene_stream.offset == 64);
    clock_us += 800000; drain(); poll(); /* finish scene after a CPU gap */
    assert(scene_stream.offset == 108);
    assert(vision_perf_stats[PERF_QUEUE_AGE].total == 123000);
    assert(vision_perf_stats[PERF_FIFO_SPAN].maximum == 800000);
    clock_us += 50000; drain(); poll();
    assert(vision_perf_stats[PERF_WIRE_IDLE_UPPER].maximum == 850000);
    vision_perf_record(PERF_COPY, 999);
    clock_us = 10000000;
    /* Unexpected partial diagnostic sink still resumes before any scene. */
    limit = 5;
    vision_perf_diag_poll(&scene_stream, 1, partial, &limit, 64);
    assert(vision_perf_diag_active());
    scene_stream_publish(&scene_stream, NULL, 0, 1, 78, 10000);
    drain(); poll(); /* production arbitration finishes diagnostic only */
    assert(scene_stream.pending && !vision_perf_diag_active());
    drain(); poll(); /* next diagnostic row + 3 scene bytes share the budget */
    assert(!scene_stream.pending && scene_stream.offset == 3U);
    drain(); poll(); /* then finish the pending scene */
    assert(!scene_stream.pending && scene_stream.offset == scene_stream.length);
    /* Complete this immutable report even while live stats keep changing. */
    for (i = 0; i < 40; ++i) { drain(); poll(); }
    assert(vision_perf_stats[PERF_COPY].total == 1019);
    clock_us = 11000000;
    for (i = 0; i < 40; ++i) { drain(); poll(); }
    assert(!vision_perf_diag_active());
    return 0;
}
