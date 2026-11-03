"""CPU fixtures for the real migrated C detector/protocol, never live input."""
import ctypes as C
import os
from pathlib import Path
import unittest

from pynq_vision.beam_runtime import Beam, CapturedFrame, Clock, DisplayFault, FRAME_BYTES, ROW, run
from pc_vision import board_wire as wire

LIBRARY = os.environ.get("BEAM_PYNQ_HOST_LIBRARY")


def packets(data):
    return wire.PacketParser().feed(data)


def image(target=None, shade=120, stride=ROW):
    raw = bytearray([shade]) * (stride * 720)
    if target:
        cx, cy = target
        for y in range(cy - 40, cy + 41):
            for x in range(cx - 40, cx + 41):
                if (x - cx) ** 2 + (y - cy) ** 2 <= 40 ** 2:
                    offset = y * stride + x * 3
                    raw[offset:offset + 3] = b"\x30\x90\x30"
    return raw


@unittest.skipUnless(LIBRARY, "set BEAM_PYNQ_HOST_LIBRARY to the offline host DLL/SO")
class MigratedBeamTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.beam = Beam(LIBRARY, 7, lambda: self.now)
        self.sequence = 0

    def tearDown(self):
        self.beam.close()

    def frame(self, raw=None, captured=None, stride=ROW):
        self.sequence += 1
        return self.beam.frame(CapturedFrame(image() if raw is None else raw,
            7, self.sequence, self.now if captured is None else captured, stride))

    def finish(self, result):
        self.beam.submitted(result.ticket)
        return self.beam.retired(result.ticket)

    def select(self):
        command = wire.encode_level(2, 11, {"point": [32, 500], "direction": [1, 0]}, 19)
        self.assertEqual(self.beam.receive(command[:13]), [])
        self.assertEqual(self.beam.receive(command[13:]), [])

    def start(self):
        self.select()
        result, canvas, pose = self.frame()
        self.assertEqual(pose, b"")
        ready = packets(self.finish(result))
        self.assertEqual(ready[0][0], wire.READY)
        replies = self.beam.receive(wire.encode_start(11, 19))
        self.assertEqual(packets(b"".join(replies))[0][0], wire.STARTED)

    def test_fragmented_handshake_requires_real_display_lifecycle(self):
        self.select()
        response = self.beam.receive(wire.encode_start(11, 19))
        self.assertEqual(packets(b"".join(response))[0][0], wire.ERROR)
        result, canvas, pose = self.frame()
        self.assertEqual(len(canvas), FRAME_BYTES)
        self.assertEqual(pose, b"")
        with self.assertRaises(RuntimeError):
            self.beam.retired(result.ticket)
        self.beam.submitted(result.ticket)
        with self.assertRaises(RuntimeError):
            self.beam.retired(result.ticket + 1)
        response = self.beam.retired(result.ticket)
        self.assertEqual(packets(response)[0][0], wire.READY)
        with self.assertRaises(RuntimeError):
            self.beam.retired(result.ticket)

    def test_sync_and_bad_crc_do_not_change_session(self):
        bad = bytearray(wire.encode_start(11, 19)); bad[7] ^= 0x40
        self.assertEqual(self.beam.receive(bad), [])
        replies = self.beam.receive(wire.encode_sync("1234abcd"))
        kind, payload = packets(b"".join(replies))[0]
        self.assertEqual(kind, wire.SYNC_REPLY)
        self.assertEqual(int.from_bytes(payload[:4], "little"), 0x1234abcd)
        self.assertEqual(int.from_bytes(payload[4:12], "little"), self.now)
        self.assertEqual(int.from_bytes(payload[12:20], "little"), self.now)

    def test_actual_detector_b_hold_keeps_original_frame_and_pose_is_current(self):
        self.start()
        raw = image((300, 640))  # below the old 590-pixel field limit
        for now in (1100, 1200, 1300):
            self.now = now
            result, canvas, pose = self.frame(raw)
            self.finish(result)
        self.assertEqual(result.detections, 1)
        self.assertEqual(result.valid, 1)
        stable_sequence = result.sequence
        self.now = 1400
        result, held, pose = self.frame(image((400, 640), shade=30))
        self.assertEqual(result.valid, 0)
        self.assertEqual(result.display_stale, 1)
        self.assertEqual(result.shown_sequence, stable_sequence)
        self.assertEqual(result.shown_captured_ms, 1300)
        self.assertEqual(held[100 * ROW:100 * ROW + 30], canvas[100 * ROW:100 * ROW + 30])
        kind, payload = packets(pose)[0]
        self.assertEqual(kind, wire.POSE)
        current = wire.decode_pose(payload)
        self.assertFalse(current.valid)
        self.assertEqual(current.models, ())
        self.assertEqual(current.captured_ms, 1400)
        self.finish(result)
        self.now = 7401
        expired, canvas, pose = self.frame(image(shade=30))
        self.assertFalse(expired.display_stale)
        self.assertEqual(expired.shown_sequence, expired.sequence)
        self.finish(expired)

    def test_input_padding_and_64bit_original_identity(self):
        self.start()
        self.now = (1 << 53) + 1000
        sequence = (1 << 53) + 3
        raw = image(stride=ROW + 64)
        result, canvas, pose = self.beam.frame(CapturedFrame(raw, 7, sequence, self.now, ROW + 64))
        decoded = wire.decode_pose(packets(pose)[0][1])
        self.assertEqual(decoded.sequence, sequence)
        self.assertEqual(decoded.captured_ms, self.now)
        self.assertEqual(result.sequence, sequence)
        self.finish(result)

    def test_b_support_gap_500_inclusive_501_reconfirms(self):
        raw = image((300, 640))
        for gap, expected_valid in ((400, True), (500, True), (501, False)):
            self.beam.close()
            self.now, self.sequence = 1000, 0
            self.beam = Beam(LIBRARY, 7, lambda: self.now)
            first, _, _ = self.frame(raw)
            self.assertFalse(first.valid)
            self.finish(first)
            self.now += gap
            second, _, _ = self.frame(raw)
            self.assertEqual(bool(second.valid), expected_valid)
            self.finish(second)

    def test_pynq_scene_age_600_is_inclusive_and_601_is_stale(self):
        self.start()
        self.now = 1601
        accepted = self.frame(captured=1001)[0]
        self.assertNotEqual(accepted.status, 6)
        self.finish(accepted)
        self.now = 1603
        stale = self.frame(captured=1002)[0]
        self.assertEqual(stale.status, 6)
        self.finish(stale)

    def test_reject_duplicate_capture_and_backward_clock(self):
        result, _, _ = self.frame()
        self.finish(result)
        self.now = 1100
        duplicate, _, _ = self.beam.frame(CapturedFrame(image(), 7, 1, 1000))
        self.assertNotEqual(duplicate.status, 0)
        self.finish(duplicate)
        self.beam.close()
        self.beam = Beam(LIBRARY, 8, lambda: self.now)
        self.now = 1099
        with self.assertRaises(RuntimeError):
            self.beam.receive(wire.encode_sync("1234abcd"))

    def test_invalid_source_span_and_single_detector_owner(self):
        with self.assertRaises(ValueError):
            CapturedFrame(bytes(100), 7, 1, 1000)
        with self.assertRaises(TypeError):
            CapturedFrame(memoryview(image()), 7, 1, 1000)
        with self.assertRaises(RuntimeError):
            Beam(LIBRARY, 8, lambda: self.now)

    def test_control_is_only_applied_at_scene_boundary(self):
        self.select()
        result, _, _ = self.frame()
        with self.assertRaises(RuntimeError):
            self.beam.receive(wire.encode_reset(11, 19))
        self.finish(result)
        response = self.beam.receive(wire.encode_start(11, 20))
        self.assertEqual(packets(b"".join(response))[0][0], wire.ERROR)
        response = self.beam.receive(wire.encode_reset(11, 19))
        self.assertEqual(packets(b"".join(response))[0][0], wire.RESET_ACK)
        self.now = 1100
        result, _, pose = self.frame()
        self.assertEqual(pose, b"")
        self.finish(result)

    def test_runner_prepares_and_drains_owner_before_cpu_or_uart_close(self):
        events = []
        frame = CapturedFrame(image(), 7, 1, self.now)
        class Owner:
            checks = 0
            stops = 0
            def prepare(inner): events.append("prepare")
            def capture_cpu(inner): events.append("capture"); return frame
            def check_capture(inner): inner.checks += 1
            def submit_cpu(inner, canvas, result):
                self.assertEqual(len(canvas), FRAME_BYTES)
                events.append("submit")
            def display_retired(inner, ticket): events.append("retire"); return True
            def stop(inner): inner.stops += 1; events.append("stop")
            def can_exit(inner): return inner.stops >= 2
        class Uart:
            def read(inner): return b""
            def write_packet(inner, packet): pass
            def close(inner): events.append("uart_close")
        owner = Owner()
        run(owner, self.beam, Uart(), lambda: "retire" in events)
        self.assertEqual(events, ["prepare", "capture", "submit", "retire", "stop", "stop", "uart_close"])
        self.assertIsNone(self.beam.handle)

    def test_runner_records_original_fault_before_drain(self):
        events = []
        failure = RuntimeError('capture lease lost')
        class Owner:
            first_fault = None
            def prepare(inner): pass
            def capture_cpu(inner): raise failure
            def stop(inner):
                self.assertEqual(inner.first_fault['error'], repr(failure))
                events.append('halted')
            def can_exit(inner): return 'halted' in events
        class Uart:
            def read(inner): return b''
            def close(inner): events.append('uart_close')
        owner = Owner()
        with self.assertRaises(RuntimeError) as error:
            run(owner, self.beam, Uart(), lambda: False)
        self.assertIs(error.exception, failure)
        self.assertEqual(events, ['halted', 'uart_close'])
        self.assertIsNone(self.beam.handle)

    def test_runner_retries_transient_display_faults_without_ending_session(self):
        events = []
        frame = CapturedFrame(image(), 7, 1, self.now)
        class Owner:
            first_fault = None
            submit_faults = 1
            retire_faults = 1
            def prepare(inner): pass
            def capture_cpu(inner): return frame
            def check_capture(inner): events.append('check')
            def submit_cpu(inner, canvas, result):
                if inner.submit_faults:
                    inner.submit_faults -= 1
                    events.append('submit_fault')
                    raise DisplayFault('temporary display write')
                events.append('submit')
            def display_retired(inner, ticket):
                if inner.retire_faults:
                    inner.retire_faults -= 1
                    events.append('retire_fault')
                    raise DisplayFault('temporary display read')
                events.append('retire')
                return True
            def stop(inner): events.append('stop')
            def can_exit(inner): return True
        class Uart:
            def read(inner): return b''
            def write_packet(inner, packet): pass
            def close(inner): events.append('uart_close')
        owner = Owner()
        run(owner, self.beam, Uart(), lambda: 'retire' in events)
        self.assertIn('submit_fault', events)
        self.assertIn('retire_fault', events)
        self.assertLess(events.index('submit_fault'), events.index('submit'))
        self.assertLess(events.index('retire_fault'), events.index('retire'))
        self.assertEqual(events[-2:], ['stop', 'uart_close'])


if __name__ == "__main__":
    unittest.main()
