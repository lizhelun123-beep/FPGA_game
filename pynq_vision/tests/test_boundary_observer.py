"""Host CSR/first-fault checks; no PYNQ imports, device or image allocation."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pynq_vision import boundary_observer as boundary
from pynq_vision.hardware import CsiReceiver


class ObserverCSR:
    def __init__(self, version=boundary.OBSERVER_VERSION):
        self.version = version
        self.sequence = 0
        self.index = 0
        self.source = [boundary.OBSERVER_MAGIC] + [0] * 23
        self.published = list(self.source)
        self.reads, self.writes = [], []
        self.busy = False
        self.torn = False
        self.ignore_freeze = False
        self.rearm_on_freeze = False
        self.misindex = False

    def read(self, offset):
        self.reads.append(offset)
        if offset == 0x00:
            return 2
        if offset == 0x04:
            return 1440
        if offset == 0x08:
            return 0
        if offset == 0x0C:
            return self.version
        if offset == 0x10:
            return self.sequence
        if offset == 0x14:
            return int(self.busy)
        if offset == 0x18:
            return self.index ^ int(self.misindex)
        if offset == 0x1C:
            if self.torn:
                self.sequence = (self.sequence + 1) & 0xFFFFFFFF
                self.torn = False
            return self.published[self.index]
        raise AssertionError('unexpected MMIO read 0x{:x}'.format(offset))

    def write(self, offset, value):
        self.writes.append((offset, value))
        if offset == 0x10:
            if value != 1:
                raise AssertionError('unexpected snapshot request')
            self.published = list(self.source)
            self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        elif offset == 0x18:
            self.index = value & 0xFF
            if value & boundary.ARM:
                epoch = (self.source[6] + 1) & 0xFFFFFFFF
                self.source = [boundary.OBSERVER_MAGIC, 2, 0, 0, 0, 0, epoch] + [0] * 17
            if value & boundary.FREEZE and not self.ignore_freeze:
                if not self.source[1] & 1:
                    self.source[1] |= 1
                    self.source[2] = boundary.FREEZE
                if self.rearm_on_freeze:
                    self.source[6] += 1
        else:
            raise AssertionError('unexpected MMIO write 0x{:x}'.format(offset))


class Clock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        self.value += 0.000001
        return self.value

    def sleep(self, duration):
        self.value += duration


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.time_patch = patch.object(boundary.time, 'monotonic', self.clock.monotonic)
        self.sleep_patch = patch.object(boundary.time, 'sleep', self.clock.sleep)
        self.time_patch.start()
        self.sleep_patch.start()
        self.addCleanup(self.time_patch.stop)
        self.addCleanup(self.sleep_patch.stop)
        self.csr = ObserverCSR()
        self.observer = boundary.BoundaryObserver(self.csr)

    def test_legacy_core_rejected_before_any_extended_or_write_access(self):
        csr = ObserverCSR(0x00010002)
        with self.assertRaisesRegex(RuntimeError, 'CSI1.3'):
            boundary.BoundaryObserver(csr).snapshot()
        self.assertEqual(csr.reads, [0x0C])
        self.assertEqual(csr.writes, [])

    def test_old_packet_snapshot_supported_on_both_versions_without_extended_access(self):
        for version in (0x00010002, 0x00010003):
            csr = ObserverCSR(version)
            result = CsiReceiver(csr).snapshot()
            self.assertEqual(result['long_packets'], 1440)
            self.assertEqual(result['version'], version)
            self.assertFalse(set(csr.reads) & {0x18, 0x1C})
            self.assertEqual(csr.writes, [(0x10, 1)])

    def test_coherent_words_decode_actual_stream_units_and_sequence_wrap(self):
        self.csr.sequence = 0xFFFFFFFF
        self.csr.source[8:16] = [2, 720, 0, 0, 320, 720, 320, 320]
        self.csr.source[16:24] = [2, 720, 0, 0, 1280, 720, 1280, 1280]
        result = self.observer.snapshot()
        self.assertEqual(result['snapshot_sequence'], 0)
        self.assertEqual(result['csi_output']['last_line_pixels'], 1280)
        self.assertEqual(result['vdma_input']['last_line_pixels'], 1280)
        self.assertEqual(result['csi_output']['expected_beats_per_line'], 320)
        self.assertEqual(result['vdma_input']['expected_beats_per_line'], 1280)
        self.assertEqual(result['raw_words'], self.csr.source)
        self.assertEqual(result['csi_output']['current_frame_index'], 2)
        self.assertEqual(result['csi_output']['last_completed_frame_index'], 1)
        self.assertTrue(result['csi_output']['last_line_terminated'])

    def test_tap_frame_indices_remain_independent_across_pipeline_latency(self):
        self.csr.source[8:16] = [3, 1440, 0, 3, 320, 720, 320, 320]
        self.csr.source[16:24] = [2, 1439, 719, 1279, 1280, 720, 1280, 1280]
        result = self.observer.snapshot()
        self.assertEqual(result['csi_output']['current_frame_index'], 3)
        self.assertEqual(result['vdma_input']['current_frame_index'], 2)
        self.assertEqual(result['csi_output']['last_completed_frame_index'], 2)
        self.assertEqual(result['vdma_input']['last_completed_frame_index'], 1)
        self.assertIn('Pipeline latency', result['frame_alignment'])

    def test_partial_sof_word4_is_unterminated_line_length_not_last_tlast(self):
        self.csr.source[1:3] = [3, 1 << 2]
        self.csr.source[8:16] = [2, 719, 0, 1, 17, 719, 320, 320]
        result = self.observer.snapshot()
        stream = result['csi_output']
        self.assertEqual(stream['last_line_beats'], 17)
        self.assertEqual(stream['last_line_pixels'], 68)
        self.assertFalse(stream['last_line_terminated'])
        self.assertEqual(stream['last_line_beats_meaning'], 'unterminated line before accepted SOF')
        self.assertTrue(result['vdma_input']['last_completed_frame_index'] is None)

    def test_unseen_first_sof_has_no_frame_index_or_terminated_line(self):
        result = self.observer.snapshot()
        for stream in (result['csi_output'], result['vdma_input']):
            self.assertIsNone(stream['current_frame_index'])
            self.assertIsNone(stream['last_completed_frame_index'])
            self.assertFalse(stream['last_line_terminated'])

    def test_arm_confirms_source_epoch_then_software_freeze(self):
        self.csr.source[6] = 0xFFFFFFFF
        armed = self.observer.arm()
        self.assertEqual(armed['arm_sequence'], 0)
        self.assertTrue(armed['armed'])
        self.assertFalse(armed['frozen'])
        self.csr.source[3] = 54321
        frozen = self.observer.freeze()
        self.assertEqual(frozen['freeze_origin'], 'software_after_fault')
        self.assertIn('not the exact VDMA error cycle', frozen['freeze_time_semantics'])
        self.assertIn('earlier first-fault latch', frozen['packet_crc_scope'])
        self.assertEqual(frozen['video_tick'], 54321)
        self.assertEqual([v for o, v in self.csr.writes if o == 0x18 and v & boundary.ARM],
                         [boundary.ARM])
        self.assertEqual([v for o, v in self.csr.writes if o == 0x18 and v & boundary.FREEZE],
                         [boundary.FREEZE])

    def test_hardware_first_fault_is_not_overwritten_by_software_freeze(self):
        self.csr.source[1:4] = [3, 0x100, 123]
        self.csr.source[6] = 4
        self.csr.source[16:24] = [1, 720, 720, 7, 1279, 0, 1279, 1280]
        result = self.observer.freeze()
        self.assertEqual(result['first_reason'], 0x100)
        self.assertEqual(result['freeze_origin'], 'first_observer_fault')
        self.assertEqual(result['vdma_input']['last_line_beats'], 1279)
        self.assertFalse(any(offset == 0x18 and value & boundary.FREEZE
                             for offset, value in self.csr.writes))

    def test_never_armed_observer_cannot_be_claimed_as_fault_capture(self):
        with self.assertRaisesRegex(RuntimeError, 'not armed'):
            self.observer.freeze()

    def test_torn_publication_and_wrong_index_are_rejected(self):
        self.csr.torn = True
        with self.assertRaisesRegex(RuntimeError, 'changed during read'):
            self.observer.snapshot()
        self.csr.misindex = True
        with self.assertRaisesRegex(RuntimeError, 'index did not latch'):
            self.observer.snapshot()

    def test_busy_snapshot_does_not_issue_competing_request(self):
        self.csr.busy = True
        with self.assertRaisesRegex(RuntimeError, 'idle'):
            self.observer.snapshot()
        self.assertEqual(self.csr.writes, [])

    def test_missing_freeze_ack_times_out_without_rearm_or_clear(self):
        self.observer.arm()
        self.csr.ignore_freeze = True
        with self.assertRaisesRegex(RuntimeError, 'timed out|idle|not acknowledged'):
            self.observer.freeze()
        command_values = [v for offset, v in self.csr.writes if offset == 0x18 and v > 255]
        self.assertEqual(command_values, [boundary.ARM, boundary.FREEZE])
        self.assertFalse(any(offset == 0 for offset, _ in self.csr.writes))

    def test_rearm_during_freeze_cannot_replace_the_fault_epoch(self):
        self.observer.arm()
        self.csr.rearm_on_freeze = True
        with self.assertRaisesRegex(RuntimeError, 'rearmed'):
            self.observer.freeze()

    def test_wrong_observer_magic_is_not_valid_evidence(self):
        self.csr.source[0] = 0
        with self.assertRaisesRegex(RuntimeError, 'magic'):
            self.observer.snapshot()


_worker_path = Path(__file__).resolve().parents[2] / 'color_test/software/vision_ps_baremetal/tools/game_capture_worker.py'
_spec = importlib.util.spec_from_file_location('boundary_test_worker', str(_worker_path))
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


class WorkerFaultTests(unittest.TestCase):
    def _session(self, original):
        def fail():
            raise original
        return SimpleNamespace(stage='warmup_writer0', sequence=0, writer=0,
                               held=None, previous={'long_packets': 0, 'crc_errors': 0},
                               poll=fail)

    def test_boundary_failure_cannot_replace_original_dma_fault(self):
        original = RuntimeError('original DMA0x90')
        original.snapshot = {'status': 0x15090, 'park': 0}
        def fail_snapshot():
            raise RuntimeError('snapshot timeout')
        diagnostics = io.StringIO()
        with self.assertRaises(RuntimeError) as caught:
            worker.serve(self._session(original), iter((None,)), io.StringIO(), diagnostics,
                         SimpleNamespace(freeze=fail_snapshot))
        self.assertIs(caught.exception, original)
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertEqual(fault['first_sample'], original.snapshot)
        self.assertEqual(fault['error'], 'original DMA0x90')
        self.assertIn('snapshot timeout', fault['boundary_snapshot_failure'])
        self.assertNotIn('boundary_snapshot', fault)

    def test_passive_snapshot_is_attached_before_fault_is_reraised(self):
        original = RuntimeError('DMA0x90')
        original.snapshot = {'status': 0x15090, 'park': 0}
        calls = []
        def freeze():
            calls.append('freeze_before_exception_returns')
            return {'frozen': True, 'first_reason': 0x100}
        diagnostics = io.StringIO()
        with self.assertRaises(RuntimeError):
            worker.serve(self._session(original), iter((None,)), io.StringIO(), diagnostics,
                         SimpleNamespace(freeze=freeze))
        self.assertEqual(calls, ['freeze_before_exception_returns'])
        fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
        self.assertTrue(fault['boundary_snapshot']['frozen'])
        self.assertEqual(fault['first_sample'], original.snapshot)

    def test_first_fault_is_exclusively_saved_with_boot_and_original_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = worker.EvidenceSink(directory, 'current-boot', 'first_fault.json')
            original = RuntimeError('DMA0x90')
            original.snapshot = {'status': 0x15090, 'park': 0}
            diagnostics = io.StringIO()
            snapshot = {'frozen': True, 'first_reason': 0x100,
                        'freeze_origin': 'first_observer_fault'}
            with self.assertRaises(RuntimeError) as caught:
                worker.serve(self._session(original), iter((None,)), io.StringIO(), diagnostics,
                             SimpleNamespace(freeze=lambda: snapshot), sink)
            self.assertIs(caught.exception, original)
            saved = json.loads(sink.path.read_text())
            self.assertEqual(saved['boot_id'], 'current-boot')
            self.assertIsInstance(saved['monotonic'], float)
            self.assertEqual(saved['first_sample'], original.snapshot)
            self.assertEqual(saved['boundary_snapshot'], snapshot)
            self.assertEqual(saved['error'], 'DMA0x90')
            self.assertIn('first_fault_file', diagnostics.getvalue())

    def test_fault_file_io_failure_cannot_replace_the_original_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = worker.EvidenceSink(directory, 'current-boot', 'first_fault.json')
            original = RuntimeError('DMA0x90')
            original.snapshot = {'status': 0x15090}
            diagnostics = io.StringIO()
            with patch.object(worker.os, 'open', side_effect=OSError('evidence storage failed')):
                with self.assertRaises(RuntimeError) as caught:
                    worker.serve(self._session(original), iter((None,)), io.StringIO(), diagnostics,
                                 SimpleNamespace(freeze=lambda: {'frozen': True}), sink)
            self.assertIs(caught.exception, original)
            fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
            self.assertIn('evidence storage failed', fault['first_fault_file_failure'])
            self.assertEqual(fault['first_sample'], original.snapshot)

    def test_existing_first_fault_is_neither_refrozen_nor_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = worker.EvidenceSink(directory, 'current-boot', 'first_fault.json')
            sink({'first_sample': {'status': 0x15090}, 'operation': 'original'})
            before = sink.path.read_bytes()
            original = RuntimeError('later error')
            def forbidden_freeze():
                raise AssertionError('must not refreeze retained first fault')
            diagnostics = io.StringIO()
            with self.assertRaises(RuntimeError) as caught:
                worker.serve(self._session(original), iter((None,)), io.StringIO(), diagnostics,
                             SimpleNamespace(freeze=forbidden_freeze), sink)
            self.assertIs(caught.exception, original)
            self.assertEqual(sink.path.read_bytes(), before)
            fault = json.loads(diagnostics.getvalue().split('LIVE_CAPTURE_FIRST_FAULT ', 1)[1])
            self.assertIn('first_fault_file_preserved', fault)
            self.assertIn('boundary_snapshot_skipped', fault)

    def test_diagnostic_io_failure_cannot_replace_original_fault(self):
        original = RuntimeError('original fault')
        class BrokenDiagnostics:
            def write(self, value):
                raise OSError('diagnostic pipe closed')
        with self.assertRaises(RuntimeError) as caught:
            worker.serve(self._session(original), iter((None,)), io.StringIO(), BrokenDiagnostics())
        self.assertIs(caught.exception, original)


class EvidenceFileTests(unittest.TestCase):
    def test_exclusive_write_fsync_and_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            original_fsync = os.fsync
            with patch.object(worker.os, 'fsync', wraps=original_fsync) as fsync:
                sink({'operation': 'poll'})
            fsync.assert_called_once()
            before = sink.path.read_bytes()
            with self.assertRaises(FileExistsError):
                sink({'operation': 'later'})
            self.assertEqual(sink.path.read_bytes(), before)

    def test_failed_fsync_does_not_delete_or_overwrite_created_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            with patch.object(worker.os, 'fsync', side_effect=OSError('fsync failed')):
                with self.assertRaisesRegex(OSError, 'fsync failed'):
                    sink({'operation': 'poll'})
            self.assertTrue(sink.path.exists())
            before = sink.path.read_bytes()
            with self.assertRaises(FileExistsError):
                sink({'operation': 'retry'})
            self.assertEqual(sink.path.read_bytes(), before)

    def test_normal_final_freezes_and_saves_before_cleanup_without_false_dma_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            final_sink = worker.EvidenceSink(directory, 'boot-A', 'boundary_final.json')
            diagnostics, calls = io.StringIO(), []
            def freeze():
                calls.append('freeze')
                return {'frozen': True, 'first_reason': boundary.FREEZE,
                        'freeze_origin': 'software_after_fault'}
            record = worker.capture_boundary_final(SimpleNamespace(freeze=freeze), diagnostics,
                                                   final_sink, fault_sink)
            calls.append('cleanup')
            self.assertEqual(calls, ['freeze', 'cleanup'])
            self.assertIsNone(record['first_sample'])
            self.assertEqual(record['operation'], 'passive_observer_final')
            self.assertFalse(fault_sink.path.exists())
            saved = json.loads(final_sink.path.read_text())
            self.assertEqual(saved['boot_id'], 'boot-A')
            self.assertEqual(saved['boundary_snapshot']['freeze_origin'], 'software_after_fault')
            self.assertTrue(diagnostics.getvalue().startswith('LIVE_BOUNDARY_FINAL '))

    def test_normal_final_retains_first_hardware_fault_once(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            final_sink = worker.EvidenceSink(directory, 'boot-A', 'boundary_final.json')
            calls = []
            def freeze():
                calls.append('freeze')
                return {'frozen': True, 'first_reason': 0x100,
                        'freeze_origin': 'first_observer_fault'}
            observer = SimpleNamespace(freeze=freeze)
            worker.capture_boundary_final(observer, io.StringIO(), final_sink, fault_sink)
            before_fault, before_final = fault_sink.path.read_bytes(), final_sink.path.read_bytes()
            first = json.loads(before_fault)
            self.assertEqual(first['operation'], 'passive_observer_final')
            self.assertIsNone(first['first_sample'])
            worker.capture_boundary_final(observer, io.StringIO(), final_sink, fault_sink)
            self.assertEqual(calls, ['freeze'])
            self.assertEqual(fault_sink.path.read_bytes(), before_fault)
            self.assertEqual(final_sink.path.read_bytes(), before_final)

    def test_existing_first_fault_skips_final_refreeze_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            final_sink = worker.EvidenceSink(directory, 'boot-A', 'boundary_final.json')
            fault_sink({'operation': 'poll', 'first_sample': {'status': 0x15090}})
            before = fault_sink.path.read_bytes()
            def forbidden():
                raise AssertionError('must not refreeze')
            record = worker.capture_boundary_final(SimpleNamespace(freeze=forbidden), io.StringIO(),
                                                   final_sink, fault_sink)
            self.assertIn('boundary_snapshot_skipped', record)
            self.assertEqual(fault_sink.path.read_bytes(), before)
            self.assertTrue(final_sink.path.exists())

    def test_final_snapshot_or_save_failure_keeps_original_normal_return(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_sink = worker.EvidenceSink(directory, 'boot-A', 'first_fault.json')
            final_sink = worker.EvidenceSink(directory, 'boot-A', 'boundary_final.json')
            def fail_snapshot():
                raise RuntimeError('final snapshot failed')
            diagnostics = io.StringIO()
            record = worker.capture_boundary_final(SimpleNamespace(freeze=fail_snapshot), diagnostics,
                                                   final_sink, fault_sink)
            self.assertIn('final snapshot failed', record['boundary_snapshot_failure'])
            self.assertTrue(final_sink.path.exists())
            other_final = worker.EvidenceSink(directory, 'boot-A', 'other_final.json')
            with patch.object(worker.os, 'open', side_effect=OSError('final write failed')):
                record = worker.capture_boundary_final(SimpleNamespace(freeze=fail_snapshot), diagnostics,
                                                       other_final, fault_sink)
            self.assertIn('final write failed', record['boundary_final_file_failure'])
if __name__ == '__main__':
    unittest.main()
