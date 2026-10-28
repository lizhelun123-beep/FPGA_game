"""Continuous sensor/VDMA coordinator for the existing C allocation owner.

No image allocation or pixel reads here. A frozen store is leased to C until
FRAME_DONE; the other store keeps receiving the unbackpressureable camera.
"""
import time

from .constants import HEIGHT
from .vdma import HALTED, RUNSTOP, S2MM_CONTROL


class ContinuousCapture:
    def __init__(self, dma, csi, sensor, buffers):
        self.dma, self.csi, self.sensor, self.buffers = dma, csi, sensor, buffers
        self.armed = False
        self.writer = 0
        self.held = None
        self.sequence = 0
        self.previous = None
        self.last_check = 0.0
        self.stage = 'standby'

    def _health(self):
        after = self.csi.snapshot()
        if after['control'] & 3 != self.csi.ENABLE:
            raise RuntimeError("CSI disabled or reset during continuous capture")
        health = self.csi.validate_window(self.previous, after)
        self.previous = after
        self.last_check = time.monotonic()
        return after, health

    def acquire(self):
        if self.held is not None:
            raise RuntimeError("FRAME_DONE is required before another START")
        if not self.armed:
            self.stage = 'initialize'
            self.csi.reset_enable()
            self.previous = self.csi.snapshot()
            if (self.previous['long_packets'] or self.previous['crc_errors'] or
                    self.previous['control'] & self.csi.OVERFLOW or
                    self.previous['control'] & 3 != self.csi.ENABLE):
                raise RuntimeError("CSI did not start with clean counters")
            # Mark armed before configuration: partial arming must also halt
            # before the C owner is allowed to release its allocation.
            self.armed = True
            self.dma.configure(True, self.buffers, circular=True)
            self.dma.validate_layout(True, self.buffers)
            self.dma.park_write(self.writer)
            self.sensor.start()
            self.stage = 'warmup_writer%d' % self.writer
            self.dma.wait_parked_write(self.writer)
            self.stage = 'validate_warmup_csi'
            self._health()

        # The bound is sampled BEFORE a fresh start on the old writer, never
        # assigned at fence completion or detector submission. Later overwrites
        # of that writer can only make the bound more conservative.
        self.stage = 'fresh_start_on_old_writer'
        captured = self.dma.wait_parked_write(self.writer, events=1)
        slot = self.writer
        writer = (slot + 1) % len(self.buffers)
        self.stage = 'request_next_writer'
        self.dma.park_write(writer)
        self.stage = 'retire_old_writer'
        self.dma.wait_parked_write(writer)
        self.writer = writer
        self.stage = 'validate_retired_csi'
        after, health = self._health()  # includes the old frame's CRC tail
        if health['packet_delta'] < HEIGHT:
            raise RuntimeError("retired frame lacks a full RAW10 packet window")
        self.sequence += 1
        self.held = (slot, writer)
        self.stage = 'cpu_lease'
        return dict(sequence=self.sequence, captured_ms=int(captured * 1000),
                    slot=slot, writer=writer, csi=after, health=health)

    def acknowledge(self):
        if self.held is None:
            raise RuntimeError("unexpected FRAME_DONE")
        self.dma.check_parked_write(self.writer)
        self.held = None
        self.stage = 'waiting_for_request'

    def poll(self):
        if self.armed:
            self.dma.check_parked_write(self.writer)
            if time.monotonic() - self.last_check >= 1.0:
                self._health()

    def close(self, quiet_seconds=0.05, timeout=0.5):
        """Stop producer first, leave receiver/consumer alive for its tail.

        Counter quiet is a bounded tail observation, NOT a FIFO-empty proof.
        No shutdown frame is published. Only actual RS0/HALTED permits receiver
        isolation and allocation release. The caller retains its mappings and
        clocks if that halt cannot be confirmed.
        """
        failure = None
        try:
            self.sensor.stop()
            if self.armed:
                deadline = time.monotonic() + timeout
                quiet_since = time.monotonic()
                last = self.csi.snapshot()
                while time.monotonic() - quiet_since < quiet_seconds:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("sensor tail did not become quiet")
                    time.sleep(0.001)
                    after = self.csi.snapshot()
                    if (after['long_packets'], after['crc_errors']) != (last['long_packets'], last['crc_errors']):
                        quiet_since = time.monotonic()
                    last = after
                if (last['control'] & self.csi.OVERFLOW or
                        (last['crc_errors'] - self.previous['crc_errors']) & 0xFFFFFFFF):
                    raise RuntimeError("CSI fault during producer stop/tail drain: {!r}".format(last))
        except BaseException as exc:
            failure = exc
        if self.armed:
            self.dma.stop(True, timeout=2.0)
            # Independently check even if an injected/backend stop returned.
            if (not self.dma.status(True) & HALTED or
                    self.dma.regs.read(S2MM_CONTROL) & RUNSTOP):
                raise RuntimeError("CAPTURE_RETAINED: S2MM halt unconfirmed")
            self.armed = False
        self.held = None
        self.csi.regs.write(0, 0)
        if failure is not None:
            raise failure
