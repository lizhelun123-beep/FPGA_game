"""Minimal AXI VDMA 6.3 MMIO driver for this fixed BGR888 pipeline."""

import time

import numpy as np

from .constants import (ACTIVE_LINE_BYTES, FRAME_BYTES, FRAME_COUNT, HEIGHT,
                        STRIDE, WIDTH, check_frame_contract)
from .registers import RegisterBlock

MM2S_CONTROL = 0x00
MM2S_STATUS = 0x04
S2MM_CONTROL = 0x30
S2MM_STATUS = 0x34
PARK_POINTER = 0x28
MM2S_VSIZE = 0x50
S2MM_VSIZE = 0xA0

HSIZE_DELTA = 0x04
STRIDE_DELTA = 0x08
START_ADDRESS_DELTA = 0x0C
START_ADDRESS_STEP = 0x04

RUNSTOP = 0x00000001
CIRCULAR = 0x00000002
RESET = 0x00000004
HALTED = 0x00000001
ERRORS = 0x000089F0  # PG020: includes EOLLateErr (bit15), excludes reserved bits.
FRAME_COMPLETE = 0x00001000  # Historical name: IRQFrameCount event, at frame START (PG020).
FRAME_IRQ_ENABLE = 0x00001000
FRAME_COUNTER_ONE = 1 << 16
FRAME_COUNT_ENABLE = 1 << 4

READ_REFERENCE_MASK = 0x0000001F
WRITE_REFERENCE_MASK = 0x00001F00
CURRENT_READ_SHIFT = 16
CURRENT_WRITE_SHIFT = 24
CURRENT_FRAME_MASK = 0x1F


def device_address(buffer):
    nbytes = getattr(buffer, "nbytes", None)
    if not isinstance(nbytes, int) or nbytes < FRAME_BYTES:
        raise ValueError("VDMA buffer does not own a complete frame allocation")
    address = getattr(buffer, "device_address", None)
    if address is None:
        address = getattr(buffer, "physical_address", None)
    if address is None:
        raise TypeError("CMA buffer has no device/physical address")
    address = int(address)
    if address <= 0 or address + FRAME_BYTES > 0x100000000:
        raise ValueError("VDMA requires a nonzero complete 32-bit frame span")
    if address & 63:
        raise ValueError("VDMA frame address is not 64-byte aligned")
    return address


def stride_view(buffer):
    """Return a 720x1280x3 BGR view while excluding 1920 padding bytes/row."""
    check_frame_contract()
    flat = np.asarray(buffer, dtype=np.uint8).reshape(-1)
    if flat.nbytes < FRAME_BYTES:
        raise ValueError("frame buffer is smaller than stride * height")
    return np.ndarray((HEIGHT, WIDTH, 3), dtype=np.uint8, buffer=flat,
                      strides=(STRIDE, 3, 1))


def _checked_sync(buffer, name):
    operation = getattr(buffer, name, None)
    if operation is None:
        raise RuntimeError("qualified status-returning {} is required".format(name))
    status = operation()
    if type(status) is not int or status != 0:
        raise RuntimeError("{} did not confirm success: {!r}".format(name, status))


def sync_for_cpu(buffer):
    _checked_sync(buffer, "sync_for_cpu_checked")


def sync_for_device(buffer):
    _checked_sync(buffer, "sync_for_device_checked")


class AxiVdma:
    def __init__(self, io):
        self.regs = RegisterBlock(io)
        self.single_frame = False
        self.frame_start_lower_bound = None

    @staticmethod
    def _channel(capture):
        return ((S2MM_CONTROL, S2MM_STATUS, S2MM_VSIZE)
                if capture else (MM2S_CONTROL, MM2S_STATUS, MM2S_VSIZE))

    def reset(self, capture, timeout=1.0):
        self.single_frame = False
        control, _, _ = self._channel(capture)
        self.regs.write(control, self.regs.read(control) | RESET)
        self.regs.wait(control, RESET, 0, timeout=timeout)

    def stop(self, capture, timeout=1.0):
        control, status, _ = self._channel(capture)
        value = self.regs.read(control)
        if value & RUNSTOP:
            self.regs.write(control, value & ~RUNSTOP)
        self.regs.wait(status, HALTED, HALTED, timeout=timeout)
        if self.regs.read(control) & RUNSTOP:
            raise RuntimeError("VDMA RS remained set after HALTED")
        return self.regs.read(status)

    def configure(self, capture, buffers, circular, one_shot=False):
        if len(buffers) != FRAME_COUNT:
            raise ValueError("exactly three VDMA buffers are required")
        if one_shot and (not capture or circular):
            raise ValueError("one-shot capture requires S2MM park mode")
        addresses = [device_address(buffer) for buffer in buffers]
        ordered = sorted(addresses)
        if any(right < left + FRAME_BYTES for left, right in zip(ordered, ordered[1:])):
            raise ValueError("VDMA frame spans overlap")
        control, status, layout = self._channel(capture)
        self.reset(capture)
        self.regs.write(status, 0xFFFFFFFF)
        for index, address in enumerate(addresses):
            self.regs.write(layout + START_ADDRESS_DELTA + index * START_ADDRESS_STEP,
                            address)
        self.regs.write(layout + STRIDE_DELTA, STRIDE)
        self.regs.write(layout + HSIZE_DELTA, ACTIVE_LINE_BYTES)
        value = RUNSTOP | FRAME_COUNTER_ONE
        if circular:
            value |= CIRCULAR
        if one_shot:
            # Park on owned slot0 and let hardware halt after one complete frame.
            self.regs.write(PARK_POINTER, self.regs.read(PARK_POINTER) & ~WRITE_REFERENCE_MASK)
            value |= FRAME_COUNT_ENABLE | FRAME_IRQ_ENABLE
        self.regs.write(control, value)
        # VSIZE is the final write that arms the channel.
        self.frame_start_lower_bound = time.monotonic() if one_shot else None
        self.regs.write(layout, HEIGHT)
        self.single_frame = bool(one_shot)

    def layout(self, capture):
        _, _, base = self._channel(capture)
        return {
            "vsize": self.regs.read(base),
            "hsize": self.regs.read(base + HSIZE_DELTA),
            "stride": self.regs.read(base + STRIDE_DELTA) & 0xFFFF,
            "addresses": [self.regs.read(base + START_ADDRESS_DELTA + i * START_ADDRESS_STEP)
                          for i in range(FRAME_COUNT)],
        }

    def validate_layout(self, capture, buffers):
        actual = self.layout(capture)
        expected_addresses = [device_address(buffer) for buffer in buffers]
        if (actual["vsize"], actual["hsize"], actual["stride"]) != (
                HEIGHT, ACTIVE_LINE_BYTES, STRIDE):
            raise RuntimeError("VDMA layout mismatch: {!r}".format(actual))
        if actual["addresses"] != expected_addresses:
            raise RuntimeError("VDMA address mismatch: {!r}".format(actual))
        return actual

    def status(self, capture):
        _, status, _ = self._channel(capture)
        return self.regs.read(status)

    def clear_frame_complete(self, capture=True):
        _, status, _ = self._channel(capture)
        self.regs.write(status, FRAME_COMPLETE)

    def wait_frame(self, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.status(True)
            if status & (HALTED | ERRORS):
                raise RuntimeError("S2MM failed with status 0x{:08x}".format(status))
            if status & FRAME_COMPLETE:
                return status
            time.sleep(0.001)
        raise RuntimeError("S2MM frame timeout; status=0x{:08x}".format(self.status(True)))

    def current_write_index(self):
        return (self.regs.read(PARK_POINTER) >> CURRENT_WRITE_SHIFT) & CURRENT_FRAME_MASK

    def current_read_index(self):
        return (self.regs.read(PARK_POINTER) >> CURRENT_READ_SHIFT) & CURRENT_FRAME_MASK

    def newest_complete_index(self):
        current = self.current_write_index()
        if current >= FRAME_COUNT:
            raise RuntimeError("invalid S2MM write frame index {}".format(current))
        return (current + FRAME_COUNT - 1) % FRAME_COUNT

    def park_read(self, index):
        if not 0 <= index < FRAME_COUNT:
            raise ValueError("invalid display frame index")
        value = self.regs.read(PARK_POINTER)
        value = (value & ~READ_REFERENCE_MASK) | index
        self.regs.write(PARK_POINTER, value)

    def wait_owned_frame(self, timeout=2.0):
        """Await one full hardware-halted frame; IRQ alone is a start event.

        The native C owner may read the stopped store instead of Python. This
        method grants slot0 only after RS/HALTED and errors have been checked.
        """
        if not self.single_frame:
            raise RuntimeError("active-ring copying is unqualified; use hardware one-shot capture")
        deadline = time.monotonic() + timeout
        lower_bound = self.frame_start_lower_bound
        event_seen = False
        while True:
            sampled = time.monotonic()  # Before the status read, not at completion.
            status = self.status(True)
            if status & ERRORS:
                raise RuntimeError("S2MM failed with status 0x{:08x}".format(status))
            if not event_seen:
                if status & FRAME_COMPLETE:
                    event_seen = True
                    self.frame_start_lower_bound = lower_bound
                else:
                    lower_bound = sampled
            if status & HALTED and status & FRAME_COMPLETE:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("S2MM did not complete and halt one frame")
            time.sleep(0.001)
        if self.regs.read(S2MM_CONTROL) & RUNSTOP or self.current_write_index() != 0:
            raise RuntimeError("one-shot slot0 ownership was not confirmed")
        return 0, status

    def finish_running_capture_to_owned_slot0(self, buffers):
        """Park on slot0 and halt after two complete transfers, without reset.

        PG020 FrameCntEn completes its configured transfers before HALTED.
        Two transfers allow a pending circular store to finish before slot0.
        No CPU access is granted here: wait_owned_frame must still prove the
        IRQ threshold, HALTED/RS0/errors0 and current store0.
        """
        if self.single_frame:
            raise RuntimeError('Expected a running circular capture')
        self.validate_layout(True, buffers)
        control=self.regs.read(S2MM_CONTROL);status=self.status(True)
        if control&(RUNSTOP|CIRCULAR|FRAME_COUNT_ENABLE|RESET)!=(RUNSTOP|CIRCULAR) or status&(HALTED|ERRORS):
            raise RuntimeError('Running capture is not healthy circular mode')
        park=self.regs.read(PARK_POINTER)&~WRITE_REFERENCE_MASK
        self.regs.write(PARK_POINTER,park)
        if self.regs.read(PARK_POINTER)&WRITE_REFERENCE_MASK:
            raise RuntimeError('Capture park request did not latch slot0')
        value=(control&~(CIRCULAR|0x00ff0000))|(2<<16)|FRAME_COUNT_ENABLE|FRAME_IRQ_ENABLE
        self.regs.write(S2MM_CONTROL,value)
        if self.regs.read(S2MM_CONTROL)!=value:
            raise RuntimeError('Two-transfer halt control did not latch')
        self.clear_frame_complete(True)
        self.frame_start_lower_bound=time.monotonic()
        self.single_frame=True
        return {'control':value,'requested_store':0,'complete_transfers_before_halt':2,
                'proof_pending':'no CPU read until wait_owned_frame verifies hardware halt'}

    def capture_copy(self, buffers, timeout=2.0, after_halt=None):
        self.wait_owned_frame(timeout)
        if after_halt is not None:
            # Stop the producer while the already-complete store is owned by
            # CPU. Native sync below rechecks HALTED before any pixel access.
            after_halt()
        index = 0
        sync_started = time.perf_counter()
        sync_for_cpu(buffers[index])
        cache_sync_ms = (time.perf_counter() - sync_started) * 1000.0
        started = time.perf_counter()
        frame = stride_view(buffers[index]).copy()
        copy_ms = (time.perf_counter() - started) * 1000.0
        final_status = self.status(True)
        if (final_status & ERRORS or not final_status & HALTED or
                self.regs.read(S2MM_CONTROL) & RUNSTOP):
            raise RuntimeError("S2MM changed or faulted during stopped-frame copy")
        self.clear_frame_complete(True)
        return index, frame, cache_sync_ms, copy_ms
