"""Host register/pipe fault regressions; no PYNQ, board or pixel allocation."""
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pynq_vision.constants import FRAME_BYTES
from pynq_vision.hardware import CsiReceiver
from pynq_vision.live_capture import ContinuousCapture
from pynq_vision.vdma import (AxiVdma, CaptureBoundaryFault, CIRCULAR, ERRORS, FRAME_COMPLETE,
                              FRAME_COUNT_ENABLE, HALTED, PARK_POINTER,
                              RUNSTOP, S2MM_CONTROL, S2MM_STATUS)


class Clock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class CameraMMIO:
    """Abstract line/SOF register model, not RTL or AXI-write completion proof.

    CSI accepted packets, video EOLs and SOF are distinct events. A whole line
    can be missing with CRC0; SOF then raises geometry errors without halting.
    """
    def __init__(self, events):
        self.values = {S2MM_STATUS: HALTED}
        self.events = events
        self.writes = []
        self.reads = []
        self.running = False
        self.starts = self.polls = 0
        self.progress = True
        self.stuck_halt = False
        self.overflow = False
        self.force_error = 0
        self.received_packets = self.video_lines = self.crc_errors = 0
        self.drop_line_frame = None
        self.drop_before_csi = True

    def lines(self, csi_packets, video_lines, crc_errors=0):
        self.received_packets += csi_packets
        self.video_lines += video_lines
        self.crc_errors += crc_errors

    def sof(self):
        if self.starts:
            if self.video_lines < 720:
                self.values[S2MM_STATUS] |= 0x90  # IntErr + SOFEarly, NOT HALTED
            elif self.video_lines > 720:
                self.values[S2MM_STATUS] |= 0x810
            self.events.append(('frame_end', self.starts, self.video_lines))
        self.video_lines = 0
        self.starts += 1
        park = self.values.get(PARK_POINTER, 0)
        writer = (park >> 8) & 31
        self.values[PARK_POINTER] = (park & 0x00FFFFFF) | (writer << 24)
        self.values[S2MM_STATUS] |= FRAME_COMPLETE
        self.events.append(('start', self.starts, writer))

    def frame(self):
        if self.starts:
            video = 719 if self.starts == self.drop_line_frame else 720
            packets = video if self.drop_before_csi else 720
            self.lines(packets, video)
            if self.values[S2MM_CONTROL] & FRAME_COUNT_ENABLE:
                # A START IRQ alone never halts or completes the one-shot.
                self.values[S2MM_CONTROL] &= ~RUNSTOP
                self.values[S2MM_STATUS] |= HALTED
                self.overflow = self.running
                return
        self.sof()

    def read(self, offset):
        self.reads.append(offset)
        if offset == S2MM_STATUS and self.running:
            self.polls += 1
            if self.progress and self.values[S2MM_CONTROL] & RUNSTOP and self.polls % 5 == 0:
                self.frame()
            self.values[S2MM_STATUS] |= self.force_error
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.writes.append((offset, value))
        if offset == S2MM_STATUS:
            self.values[offset] &= ~(value & (ERRORS | 0x7000))
        elif offset == S2MM_CONTROL:
            if value & 4:
                self.values[offset] = 0
                self.values[S2MM_STATUS] = HALTED
            else:
                self.values[offset] = value
                if value & RUNSTOP:
                    self.values[S2MM_STATUS] &= ~HALTED
                else:
                    self.events.append(('dma.stop',))
                    if not self.stuck_halt:
                        self.values[S2MM_STATUS] |= HALTED
        elif offset == PARK_POINTER:
            self.values[offset] = (self.values.get(offset, 0) & 0xFFFF0000) | (value & 0xFFFF)
        else:
            self.values[offset] = value


class Receiver(CsiReceiver):
    def __init__(self, mmio, events):
        self.mmio, self.events = mmio, events
        self.resets = self.snapshots = 0
        self.crc_at_start = None
        self.tail_reads = 0
        self.tail_packets = 0
        self.tail_crc = False
        self.control = 2
        self.regs = SimpleNamespace(write=lambda offset, value: events.append(('csi', value)))

    def reset_enable(self):
        self.resets += 1
        self.events.append(('csi.reset',))

    def snapshot(self):
        self.snapshots += 1
        if self.tail_reads:
            self.tail_reads -= 1
            self.tail_packets += 1
        crc = self.mmio.crc_errors + int(self.crc_at_start is not None and self.mmio.starts >= self.crc_at_start)
        if self.tail_crc and self.tail_packets >= 3:
            crc += 1
        self.events.append(('snapshot', self.mmio.starts, crc))
        return dict(control=self.control | (self.OVERFLOW if self.mmio.overflow else 0),
                    long_packets=self.mmio.received_packets + self.tail_packets,
                    crc_errors=crc, snapshot_sequence=self.snapshots, version=0x10002)


class Sensor:
    def __init__(self, mmio, csi, events):
        self.mmio, self.csi, self.events = mmio, csi, events
        self.starts = self.stops = 0

    def start(self):
        self.starts += 1
        self.events.append(('sensor.start',))
        self.mmio.running = True

    def stop(self):
        self.stops += 1
        self.events.append(('sensor.stop',))
        self.mmio.running = False
        self.csi.tail_reads = 3


class CaptureFixture(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.patches = [patch('time.monotonic', self.clock.monotonic),
                        patch('time.sleep', self.clock.sleep)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.events = []
        self.mmio = CameraMMIO(self.events)
        self.dma = AxiVdma(self.mmio)
        self.csi = Receiver(self.mmio, self.events)
        self.sensor = Sensor(self.mmio, self.csi, self.events)
        self.buffers = [SimpleNamespace(device_address=0x38000000 + i * FRAME_BYTES,
                                        nbytes=FRAME_BYTES) for i in range(3)]
        self.session = ContinuousCapture(self.dma, self.csi, self.sensor, self.buffers)


class LiveCaptureTests(CaptureFixture):
    def test_many_frames_keep_sink_running_and_freeze_only_excluded_store(self):
        stamps, slots = [], []
        for _ in range(12):
            frame = self.session.acquire()
            slots.append(frame['slot'])
            stamps.append(frame['captured_ms'])
            self.assertNotEqual(frame['slot'], frame['writer'])
            self.assertEqual(self.dma.current_write_index(), frame['writer'])
            self.assertLess(frame['captured_ms'], int(self.clock.value * 1000))
            self.assertGreaterEqual(frame['health']['packet_delta'], 720)
            with self.assertRaisesRegex(RuntimeError, 'FRAME_DONE'):
                self.session.acquire()
            self.session.acknowledge()
        self.assertEqual(slots, [0, 1, 2] * 4)
        self.assertEqual(stamps, sorted(set(stamps)))
        self.assertEqual(self.sensor.starts, 1)
        self.assertEqual(self.sensor.stops, 0)
        self.assertEqual(self.csi.resets, 1)
        self.assertFalse(self.mmio.overflow)
        self.assertTrue(self.mmio.values[S2MM_CONTROL] & RUNSTOP)
        self.assertFalse(any(v & FRAME_COUNT_ENABLE for o, v in self.mmio.writes if o == S2MM_CONTROL))
        self.session.close()
        self.assertLess(self.events.index(('sensor.stop',)), self.events.index(('dma.stop',)))
        self.assertLess(self.events.index(('dma.stop',)), self.events.index(('csi', 0)))

    def test_park_ack_and_stale_irq_do_not_grant_a_frame(self):
        self.session.acquire()
        self.session.acknowledge()
        self.mmio.progress = False
        self.mmio.values[S2MM_STATUS] |= FRAME_COMPLETE
        with self.assertRaisesRegex(RuntimeError, 'retirement timeout'):
            self.dma.wait_parked_write(self.session.writer, timeout=0.02)

    def test_retirement_requires_two_fresh_starts_after_writer_ack(self):
        self.session.acquire()
        start_count = self.mmio.starts
        self.dma.park_write((self.session.writer + 1) % 3)
        self.dma.wait_parked_write((self.session.writer + 1) % 3)
        # The acknowledgement/start IRQ is discarded; two later starts remain.
        self.assertGreaterEqual(self.mmio.starts - start_count, 3)

    def test_crc_tail_error_after_720_pixels_never_reaches_frame_output(self):
        self.csi.crc_at_start = 6  # after old frame starts, during the retirement fence
        with self.assertRaisesRegex(RuntimeError, 'unhealthy CSI'):
            self.session.acquire()
        self.assertIsNone(self.session.held)
        self.assertEqual(self.session.sequence, 0)

    def test_actual_726_packet_overflow_receipt_still_rejected(self):
        before = dict(control=2, long_packets=0, crc_errors=0)
        after = dict(control=0x80000002, long_packets=726, crc_errors=0)
        with self.assertRaisesRegex(RuntimeError, 'unhealthy CSI'):
            self.csi.validate_window(before, after)

    def test_csi_disable_cannot_masquerade_as_healthy_stale_counters(self):
        self.session.acquire()
        self.session.acknowledge()
        self.csi.control = 0
        with self.assertRaisesRegex(RuntimeError, 'disabled or reset'):
            self.session.acquire()

    def test_one_shot_model_reproduces_loss_of_sink(self):
        self.dma.configure(True, self.buffers, circular=False, one_shot=True)
        self.sensor.start()
        self.mmio.frame()
        self.assertFalse(self.mmio.values[S2MM_STATUS] & HALTED)
        self.assertEqual(self.mmio.received_packets, 0)
        self.mmio.frame()
        self.assertTrue(self.mmio.overflow)
        self.assertTrue(self.mmio.values[S2MM_STATUS] & HALTED)

    def test_dma_late_line_error_rejects_retirement(self):
        self.session.acquire()
        self.session.acknowledge()
        self.mmio.force_error = 1 << 15
        with self.assertRaisesRegex(RuntimeError, 'failed during park'):
            self.session.acquire()

    def test_writer_change_before_ack_is_rejected(self):
        self.session.acquire()
        self.dma.park_write((self.session.writer + 1) % 3)
        with self.assertRaisesRegex(RuntimeError, 'ownership changed'):
            self.session.acknowledge()

    def test_stop_drains_delayed_crc_tail_before_isolation(self):
        self.session.acquire()
        self.csi.tail_crc = True
        with self.assertRaisesRegex(RuntimeError, 'producer stop/tail'):
            self.session.close()
        self.assertFalse(self.session.armed)
        self.assertTrue(self.mmio.values[S2MM_STATUS] & HALTED)
        self.assertEqual(self.events[-1], ('csi', 0))
        self.assertGreaterEqual(self.csi.tail_packets, 3)

    def test_unconfirmed_halt_retains_receiver_and_ownership(self):
        self.session.acquire()
        self.mmio.stuck_halt = True
        with self.assertRaises(RuntimeError):
            self.session.close()
        self.assertTrue(self.session.armed)
        self.assertNotIn(('csi', 0), self.events)
        self.assertIsNotNone(self.session.held)

    def test_long_session_has_no_fixed_60_second_sensor_reset(self):
        self.session.acquire()
        self.session.acknowledge()
        self.clock.value += 65
        self.mmio.frame()  # hardware continues independently of the C detector
        self.session.poll()
        self.assertEqual(self.sensor.stops, 0)
        self.assertEqual(self.csi.resets, 1)

    def test_short_frame_with_crc_zero_also_faults_without_changing_park(self):
        self.dma.configure(True, self.buffers, circular=True)
        self.dma.park_write(0)
        self.sensor.start()
        self.mmio.progress = False
        self.mmio.sof()
        self.mmio.lines(csi_packets=719, video_lines=719)
        self.mmio.sof()
        self.assertEqual(self.csi.snapshot()['crc_errors'], 0)
        with self.assertRaises(CaptureBoundaryFault) as caught:
            self.dma.wait_parked_write(0)
        self.assertEqual(caught.exception.snapshot['error_mask'], 0x90)
        self.assertEqual(caught.exception.snapshot['writer'], 0)
        self.assertTrue(self.mmio.values[S2MM_CONTROL] & RUNSTOP)
        self.assertFalse(self.mmio.values[S2MM_STATUS] & HALTED)

    def test_full_csi_packet_count_cannot_prove_full_video_frame(self):
        self.dma.configure(True, self.buffers, circular=True)
        self.dma.park_write(0)
        self.sensor.start()
        self.mmio.progress = False
        before = self.csi.snapshot()
        self.mmio.sof()
        self.mmio.lines(csi_packets=720, video_lines=719)
        self.mmio.sof()
        self.assertEqual(self.csi.validate_window(before, self.csi.snapshot())['packet_delta'], 720)
        with self.assertRaises(CaptureBoundaryFault) as caught:
            self.dma.wait_parked_write(0)
        self.assertEqual(caught.exception.snapshot['error_mask'], 0x90)

    def test_first_failure_snapshot_survives_different_cleanup_error(self):
        self.session.acquire()
        self.session.acknowledge()
        self.mmio.progress = False
        self.mmio.values[S2MM_CONTROL] |= CIRCULAR
        with self.assertRaises(CaptureBoundaryFault) as caught:
            self.dma.wait_parked_write(self.session.writer)
        sample = caught.exception.snapshot
        self.assertEqual(sample['reasons'], ['control_contract'])
        self.assertEqual(sample['error_mask'], 0)
        self.mmio.values[S2MM_STATUS] |= 0x90  # later stop/tail fault is distinct
        self.assertEqual(sample['error_mask'], 0)
        self.assertEqual(sample['status'] & ERRORS, 0)

    def test_first_fault_snapshot_uses_only_existing_reads_and_no_writes(self):
        self.dma.configure(True, self.buffers, circular=True)
        self.dma.park_write(0)
        self.mmio.values[S2MM_STATUS] |= 0x90
        reads, writes = len(self.mmio.reads), len(self.mmio.writes)
        with self.assertRaises(CaptureBoundaryFault) as caught:
            self.dma.wait_parked_write(0)
        self.assertEqual(self.mmio.reads[reads:], [S2MM_CONTROL, S2MM_STATUS, PARK_POINTER])
        self.assertEqual(len(self.mmio.writes), writes)
        self.assertEqual(caught.exception.snapshot['phase'], 0)
        self.assertEqual(caught.exception.snapshot['fresh_starts'], 0)


_path = Path(__file__).resolve().parents[2] / 'color_test/software/vision_ps_baremetal/tools/game_capture_worker.py'
_spec = importlib.util.spec_from_file_location('game_capture_worker', str(_path))
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


class WorkerProtocolTests(CaptureFixture):
    def test_real_coordinator_ack_start_stop_with_original_stamps(self):
        out = io.StringIO()
        worker.serve(self.session, iter(('START', 'FRAME_DONE', 'START', 'FRAME_DONE', 'STOP')),
                     out, io.StringIO())
        frames = [line.split() for line in out.getvalue().splitlines()]
        self.assertEqual([f[1] for f in frames], ['1', '2'])
        self.assertEqual([f[3:] for f in frames], [['0', '1'], ['1', '2']])
        self.assertTrue(all(int(f[2]) < int(self.clock.value * 1000) for f in frames))
        self.assertEqual(self.sensor.starts, 1)
        self.session.close()

    def test_coalesced_pipe_ack_start_is_not_buffered_away(self):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b'FRAME_DONE\nSTART\nSTOP\n')
            os.close(write_fd)
            write_fd = -1
            with patch.object(worker.select, 'select', return_value=([read_fd], [], [])):
                self.assertEqual(list(worker.commands(read_fd, [False])), ['FRAME_DONE', 'START', 'STOP'])
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)

    def test_first_bad_frame_is_logged_before_cleanup_and_not_published(self):
        # Missing whole RAW10 row in the first retirement window; payload CRC0.
        self.mmio.drop_line_frame = 5
        out, diagnostics = io.StringIO(), io.StringIO()
        with self.assertRaises(CaptureBoundaryFault):
            worker.serve(self.session, iter(('START',)), out, diagnostics)
        self.assertEqual(out.getvalue(), '')
        import json
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertEqual(fault['stage'], 'retire_old_writer')
        self.assertEqual(fault['first_sample']['writer'], 1)
        self.assertEqual(fault['first_sample']['error_mask'], 0x90)
        self.assertEqual(fault['operation'], 'acquire')
        self.assertEqual(fault['previous_csi']['crc_errors'], 0)
        self.assertEqual(self.session.sequence, 0)
        self.assertIsNone(self.session.held)
        self.assertTrue(fault['first_sample']['control'] & RUNSTOP)
        self.session.close()
        self.assertFalse(self.mmio.values[S2MM_CONTROL] & RUNSTOP)
        self.assertTrue(fault['first_sample']['control'] & RUNSTOP)

    def test_csi_validation_failure_is_distinct_from_dma_retirement(self):
        self.csi.crc_at_start = 6
        diagnostics = io.StringIO()
        with self.assertRaises(RuntimeError):
            worker.serve(self.session, iter(('START',)), io.StringIO(), diagnostics)
        import json
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertEqual(fault['stage'], 'validate_retired_csi')
        self.assertIsNone(fault['first_sample'])
        self.assertIn('unhealthy CSI', fault['error'])

    def test_poll_failure_also_logs_the_original_register_sample(self):
        self.session.acquire()
        self.mmio.force_error = 1 << 15
        diagnostics = io.StringIO()
        with self.assertRaises(CaptureBoundaryFault):
            worker.serve(self.session, iter((None,)), io.StringIO(), diagnostics)
        import json
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertEqual(fault['operation'], 'poll')
        self.assertEqual(fault['first_sample']['error_mask'], 1 << 15)

    def test_ack_failure_also_logs_before_cleanup(self):
        self.session.acquire()
        acknowledge = self.session.acknowledge
        def changed_writer():
            self.dma.park_write((self.session.writer + 1) % 3)
            acknowledge()
        self.session.acknowledge = changed_writer
        diagnostics = io.StringIO()
        with self.assertRaises(CaptureBoundaryFault):
            worker.serve(self.session, iter(('FRAME_DONE',)), io.StringIO(), diagnostics)
        import json
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertEqual(fault['operation'], 'acknowledge')
        self.assertEqual(fault['first_sample']['operation'], 'check_parked_write')
        self.session.close()
        self.assertFalse(self.mmio.values[S2MM_CONTROL] & RUNSTOP)
        self.assertTrue(fault['first_sample']['control'] & RUNSTOP)


if __name__ == '__main__':
    unittest.main()
