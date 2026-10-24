#include "vision_perf.h"
#if VISION_PERF_ENABLE
#include <string.h>

VisionPerfStat vision_perf_stats[PERF_STAGE_COUNT];
static VisionPerfStat snapshot[PERF_STAGE_COUNT];
static uint64_t last_poll, last_report, first_fifo, last_fifo, wire_idle;
static uint64_t publish_us, observed_start_ms, diag_bytes, fifo_bytes;
static uint32_t observed_frame, packet_frame, packet_tx, full_count, unobserved;
static int have_poll, have_first, awaiting_idle;
static uint64_t metadata[6][3];
static char line[65];
static unsigned int offset, length, row = PERF_STAGE_COUNT + 6U;
static uint32_t report;

static void hex_field(char *out, uint64_t value, unsigned int digits)
{
    static const char hex[] = "0123456789abcdef";
    while (digits) { out[--digits] = hex[value & 15U]; value >>= 4; }
}

void vision_perf_record(VisionPerfStage stage, uint64_t us)
{
    VisionPerfStat *s = &vision_perf_stats[stage];
    ++s->n;
    s->total += us;
    if (us > s->maximum) s->maximum = us;
}
void vision_perf_end(VisionPerfStage stage, uint64_t start)
{
    vision_perf_record(stage, vision_perf_now() - start);
}
void vision_perf_observation(uint32_t frame, uint32_t processing_start_ms)
{
    observed_frame = frame;
    observed_start_ms = processing_start_ms;
    publish_us = vision_perf_now();
}
void vision_perf_packet(uint32_t frame, uint32_t tx, uint64_t queued_us)
{
    /* A later write without an intervening idle observation makes the previous
     * packet's wire completion unknowable; do not invent a wire timestamp. */
    if (awaiting_idle) ++unobserved;
    awaiting_idle = have_first = 0;
    packet_frame = frame;
    packet_tx = tx;
    first_fifo = last_fifo = wire_idle = 0;
    vision_perf_end(PERF_QUEUE_AGE, queued_us);
}
void vision_perf_fifo_first(void)
{
    first_fifo = vision_perf_now(); have_first = 1;
}
void vision_perf_fifo(unsigned int before, unsigned int after, int done, int full)
{
    if (full) ++full_count;
    fifo_bytes += after - before;
    if (after == before) return;
    if (!have_first) vision_perf_fifo_first();
    if (done) {
        last_fifo = vision_perf_now();
        vision_perf_record(PERF_FIFO_SPAN, last_fifo - first_fifo);
        awaiting_idle = 1;
    }
}
void vision_perf_wire_idle(int idle)
{
    if (idle && awaiting_idle) {
        wire_idle = vision_perf_now();
        vision_perf_record(PERF_WIRE_IDLE_UPPER, wire_idle - first_fifo);
        awaiting_idle = 0;
    }
}
void vision_perf_poll(void)
{
    uint64_t now = vision_perf_now();
    if (have_poll) vision_perf_record(PERF_POLL_GAP, now - last_poll);
    last_poll = now;
    have_poll = 1;
}
int vision_perf_diag_active(void) { return offset < length; }

unsigned int vision_perf_diag_poll(const SceneStream *stream, int idle,
    SceneStreamPutByte put, void *context, unsigned int budget)
{
    uint64_t now;
    unsigned int written = 0;
    PERF_START(start);
    if (!put || !budget) return 0;
    if (offset == length) {
        unsigned int id;
        uint32_t n;
        uint64_t total, maximum;
        /* Admission requires the 64-byte HW FIFO AND shifter to be empty.
         * A whole 61-byte row then fits. Unexpected sink refusal is still safe:
         * the caller resumes this row before allowing another scene packet. */
        if (!idle || budget < 61U) return 0;
        now = vision_perf_now();
        if (row == PERF_STAGE_COUNT + 6U) {
            if (now - last_report < (uint64_t)VISION_PERF_REPORT_MS * 1000U) return 0;
            last_report = now; /* No catch-up queue, even if reports take long. */
            ++report;
            memcpy(snapshot, vision_perf_stats, sizeof snapshot);
            metadata[0][0] = observed_frame;
            metadata[0][1] = observed_start_ms;
            metadata[0][2] = publish_us;
            metadata[1][0] = packet_tx;
            metadata[1][1] = first_fifo;
            metadata[1][2] = last_fifo;
            metadata[2][0] = packet_tx;
            metadata[2][1] = wire_idle; /* 0 = not observed, NOT zero latency. */
            metadata[2][2] = packet_frame;
            metadata[3][0] = stream->sent; /* FIFO accepted, NOT wire complete. */
            metadata[3][1] = stream->replaced;
            metadata[3][2] = full_count;
            metadata[4][0] = unobserved;
            metadata[4][1] = fifo_bytes;
            metadata[4][2] = diag_bytes;
            metadata[5][0] = (uint32_t)(now / 1000U);
            metadata[5][1] = ((uint64_t)stream->offset << 32) | stream->length;
            metadata[5][2] = ((uint64_t)stream->frame << 32) | stream->tx_sequence;
            row = 0;
        }
        if (row < PERF_STAGE_COUNT) {
            id = row; n = snapshot[row].n;
            total = snapshot[row].total; maximum = snapshot[row].maximum;
        } else {
            unsigned int m = row - PERF_STAGE_COUNT;
            id = 0xf0U + m; n = (uint32_t)metadata[m][0];
            total = metadata[m][1]; maximum = metadata[m][2];
        }
        /* Fixed work, no printf/heap/64-bit decimal formatting dependency. */
        memcpy(line, "@PF1 00000000 00 00000000 0000000000000000 0000000000000000\r\n", 62);
        hex_field(line + 5, report, 8); hex_field(line + 14, id, 2);
        hex_field(line + 17, n, 8); hex_field(line + 26, total, 16);
        hex_field(line + 43, maximum, 16);
        offset = 0; length = 61;
        ++row;
    }
    while (budget && offset < length) {
        if (!put(context, (unsigned char)line[offset])) break;
        ++offset; ++diag_bytes; --budget; ++written;
    }
    PERF_END(PERF_REPORT, start);
    return written;
}
#endif
