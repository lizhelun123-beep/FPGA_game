#ifndef GAME_LINUX_DISPLAY_H
#define GAME_LINUX_DISPLAY_H

#include "vision_overlay.h"
#include <stdio.h>

#define GAME_DISPLAY_VERSION 2U
#define GAME_DISPLAY_WIDTH 1280U
#define GAME_DISPLAY_HEIGHT 800U
#define GAME_DISPLAY_HSIZE 3840U
#define GAME_DISPLAY_STRIDE 5760U
#define GAME_DISPLAY_SPAN 4608000U

/* No built-in panel timing. All values belong to ONE reviewed sink/bit/clock
 * profile. pixel_hz is the integer-Hz result of ref*M/(D*O*5), not a nominal
 * requested clock. The game remains 1280x800; the named, fixed 720p control
 * profile supports scoped transport/menu validation, not native800 acceptance. */
typedef struct {
    unsigned version, width, height, stride;
    unsigned h_front, h_sync, h_back, v_front, v_sync, v_back;
    unsigned h_positive, v_positive;
    uint32_t reference_hz, multiplier, divider, output_divider;
    uint32_t pixel_hz, axis_hz;
    uint32_t sink_pixel_min_hz, sink_pixel_max_hz;
    uint32_t sink_refresh_min_millihz, sink_refresh_max_millihz;
    const char *timing_evidence;
} GameDisplayMode;

typedef enum {
    GAME_DISPLAY_OK=0, GAME_DISPLAY_BAD_ARGUMENT, GAME_DISPLAY_BAD_MODE,
    GAME_DISPLAY_UNQUALIFIED, GAME_DISPLAY_BUSY, GAME_DISPLAY_IO,
    GAME_DISPLAY_TIMEOUT, GAME_DISPLAY_DMA_ERROR, GAME_DISPLAY_BAD_STATE
} GameDisplayStatus;
typedef enum {
    GAME_DISPLAY_EMPTY=0, GAME_DISPLAY_PREPARED, GAME_DISPLAY_SCANNING,
    GAME_DISPLAY_RETAINED
} GameDisplayState;

/* Single exclusive owner. All callbacks return 0 on success. No callback may
 * reset global xlnk state. Allocation failures return no owned allocation;
 * successful allocations must be individually freeable even if validation
 * rejects their address. flush must check the installed library/cache contract.
 * barrier orders BOTH CPU stores and device register writes (ARM dmb/dsb).
 * qualify must establish matching artifacts, accepted STA/CDC/pins, sink mode,
 * exclusive resources, Linux-safe clocks/reset/HP and libcma semantics BEFORE
 * any library load/device open/MMIO/allocation. It must not simply trust
 * caller-supplied booleans. qualify itself must have no such side effects.
 * acquire runs ONLY after qualification. Even a failed acquire can own partial
 * resources; close must unwind those in reverse order, retaining on failure.
 * configure must leave timing output disabled; on failure it unwinds its own
 * partial clock/VTC changes. Fixed display ABI: dynclk STAT[0]=DRP done,
 * STAT[1]=qualified display ready (sticky isolation after lock loss).
 * Both must be set after a fresh transaction, followed by reset settling.
 * output(0) must not remove clocks needed for MM2S halt. finish restores only
 * this owner's resources, after HALTED; it must retain ownership on failure.
 * CTRL=0 requests isolation; it does not physically stop the MMCM clock.
 * close follows finish AND individual release, never global xlnk reset/close.
 * It may unload a library only with proven task-local destructor semantics.
 * now_ms is monotonic, wait_ms bounded; read/write address ONLY display MM2S.
 * This portable seam is not a Linux clock/reset or bitstream loader. */
typedef struct {
    unsigned version;
    void *context;
    int (*qualify)(void *, const GameDisplayMode *);
    int (*allocate)(void *, size_t, uint8_t **, uint64_t *);
    int (*release)(void *, uint8_t *);
    int (*flush)(void *, uint8_t *, uint64_t, size_t);
    int (*barrier)(void *);
    int (*configure)(void *, const GameDisplayMode *, unsigned);
    int (*output)(void *, int);
    int (*finish)(void *);
    int (*read)(void *, unsigned, uint32_t *);
    int (*write)(void *, unsigned, uint32_t);
    int (*now_ms)(void *, uint64_t *);
    int (*wait_ms)(void *, unsigned);
    int (*acquire)(void *);
    int (*close)(void *);
} GameDisplayPlatform;

typedef struct {
    GameDisplayState state;
    GameDisplayMode mode;
    GameDisplayPlatform platform;
    /* Private after prepare: never mutate/free while scanning or retained.
     * Retained owner/process must stay alive if stop cannot prove HALTED. */
    uint8_t *buffer;
    uint64_t physical;
    size_t span;
    size_t frame_span;
    unsigned frame_count, current_slot, submitted, fresh_frame_events;
    uint32_t last_park;
    int armed, configured, owner_active, allocation_owned;
    uint32_t last_control, last_status;
} GameLinuxDisplay;

GameDisplayStatus game_display_mode_valid(const GameDisplayMode *mode);
void game_display_control_720p_mode(GameDisplayMode *mode);
/* Strict test-file reader: 54-byte BI_RGB header, positive 1280x720, BGR24.
 * CPU canvas only. Never allocates/maps a DMA buffer or touches a device. */
GameDisplayStatus game_display_read_control_bmp(FILE *file, VisionCanvas *canvas);
void game_display_init(GameLinuxDisplay *display);
GameDisplayStatus game_display_prepare(GameLinuxDisplay *display,
    const GameDisplayMode *mode, const GameDisplayPlatform *platform,
    const VisionCanvas *rendered);
/* Same allocator,one allocation with three disjoint frame stores.
 * Only the display submission API may write these private buffers. */
GameDisplayStatus game_display_prepare_continuous(GameLinuxDisplay *display,
    const GameDisplayMode *mode, const GameDisplayPlatform *platform,
    const VisionCanvas *rendered);
/* Flush + barrier before RS; park store 0, three identical addresses,
 * stride/HSIZE then VSIZE LAST. No second submission or active-buffer writes. */
GameDisplayStatus game_display_start(GameLinuxDisplay *display, unsigned timeout_ms);
GameDisplayStatus game_display_status(GameLinuxDisplay *display);
/* Three-store mode: full-frame copy to an unowned store;ordered park commit,
 * current-store acknowledgement and two fresh frame-count events. Timing and
 * RS remain continuous. Failures retain every buffer until safe stop.
 * This submit seam also permits a future partial CPU compositor.
 * Legacy single-store diagnostic only: low-rate staged presentation. Drain to HALTED, disable/reset only this
 * display timing pipeline, then copy a disjoint CPU canvas into the SAME
 * allocation and restart. May visibly blank; no vblank/tear-free claim.
 * Qualification/lease/allocation remain owned; uncertain halt never copies. */
GameDisplayStatus game_display_update(GameLinuxDisplay *display,
    const VisionCanvas *rendered, unsigned timeout_ms);
/* Bounded observation, no game ticks/input/render. Caller prints READY only
 * after successful start. 1..30000 ms; always calls stop, including errors. */
GameDisplayStatus game_display_observe(GameLinuxDisplay *display, unsigned duration_ms,
                                      unsigned halt_timeout_ms);
/* Stop, barrier, confirm RS=0 and HALTED, then restore/release. On uncertainty
 * retain allocation and exclusive owner, return error; NEVER exit that owner
 * or unmap as an implicit fallback. Stop can be retried by the same owner. */
GameDisplayStatus game_display_stop(GameLinuxDisplay *display, unsigned timeout_ms);

/* Final owner path: never returns while ANY resource/uncertain allocation is
 * retained. Retry bounded stop, wait, retry; wait errors do not permit exit.
 * Caller must keep this object/context/library alive and defer catchable exit
 * signals until this returns. This cannot survive SIGKILL, OOM or power loss;
 * a reviewed Linux signal/owner policy remains a native qualification gate.
 * Do not install atexit cleanup or dlclose as an alternate error path. */
void game_display_owner_drain(GameLinuxDisplay *display, unsigned timeout_ms);
int game_display_owner_can_exit(const GameLinuxDisplay *display);

/* Native fixed720p diagnostic adapter. Default game800 remains unqualified.
 * Preflight runs the protected task-local, read-only evidence checker on ARM32;
 * absent/current-boot-mismatched receipts fail before device acquisition.
 * Uses existing xlnk alloc/free ioctls with an uncached mapping, not libcma.
 * Any uncertain allocation/free retains the lease; no global reset/force flag. */
GameDisplayStatus game_display_linux_preflight(void);
void game_display_linux_platform(GameDisplayPlatform *platform);

#endif
