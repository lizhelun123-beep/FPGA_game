"""Run the real UART loop against a deterministic in-memory serial device."""
import base64
import contextlib
import io
import sys
import types
import unittest
import zlib
import struct
from unittest.mock import patch

from . import godot_bridge as bridge
from .board_control import LEVEL_PAYLOAD, ControlParser
from . import board_wire as binary


EMITTER = {"point": [384.265, 445.475], "direction": [.834779, -.550586]}


def ack_line(body):
    legacy = ("@%s:%08X\r\n" % (body, zlib.crc32(body.encode()) & 0xffffffff)).encode()
    return binary.encode_control(ControlParser().feed(legacy)[0])


def level_fields(wire):
    return LEVEL_PAYLOAD.unpack(binary.PacketParser().feed(wire)[0][1])


def wire_prefix(wire):
    kind = binary.PacketParser().feed(wire)[0][0]
    return {binary.LEVEL: b"@LEVEL2", binary.START: b"@START2", binary.SYNC: b"@SYNC2"}[kind]


class FakeSerial:
    def __init__(self, worker, limit=8000, on_read=None, on_write=None, write_delay=0):
        self.worker, self.limit = worker, limit
        self.on_read, self.on_write = on_read, on_write
        self.write_delay = write_delay
        self.clock = 0
        self.rx = bytearray()
        self.writes = []
        self.closed = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        self.rx.clear()

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, count):
        self.clock += 20
        if self.on_read:
            self.on_read(self)
        if self.clock >= self.limit:
            self.worker.stop.set()
        data = bytes(self.rx[:count])
        del self.rx[:count]
        return data

    def write(self, wire):
        started = self.clock
        self.clock += self.write_delay
        self.writes.append((started, self.clock, wire))
        if self.on_write:
            result = self.on_write(self, wire)
            if result is not None:
                return result
        return len(wire)


class SerialHandshakeTests(unittest.TestCase):
    def run_wire(self, *, queue=True, trace_hook=None, **kwargs):
        records = []

        def trace(record):
            records.append(record)
            if trace_hook:
                trace_hook(worker, record)

        worker = bridge.BoardInput("IN_MEMORY_NO_DEVICE", 115200, trace=trace)
        if queue:
            worker.queue_level(1, 7, EMITTER, 123)
        wire = FakeSerial(worker, **kwargs)
        module = types.SimpleNamespace(Serial=lambda **args: wire, SerialException=OSError)
        with patch.dict(sys.modules, {"serial": module}), \
                patch.object(bridge, "now_ms", lambda: wire.clock), \
                contextlib.redirect_stderr(io.StringIO()):
            worker.run()
        self.assertTrue(wire.closed)
        self.assertTrue(all(len(row[2]) <= 64 for row in wire.writes))
        return worker, wire, records

    def test_missing_sync_ack_cannot_starve_queued_level(self):
        def queue_later(wire):
            if wire.clock == 40:
                wire.worker.queue_level(1, 7, EMITTER, 123)

        worker, wire, records = self.run_wire(queue=False, on_read=queue_later)
        commands = [wire_prefix(row[2]) for row in wire.writes]
        self.assertEqual(commands[:4], [b"@SYNC2", b"@LEVEL2", b"@LEVEL2", b"@LEVEL2"])
        self.assertEqual(wire.writes[1][0], wire.writes[0][1] + bridge.SYNC_TIMEOUT_MS)
        events = worker.poll_transport_events()
        self.assertEqual([event.kind for event in events], ["SENT", "SENT", "SENT", "TIMEOUT"])
        self.assertEqual([event.attempt for event in events], [1, 2, 3, 3])
        self.assertGreaterEqual(events[-1].at_ms-events[-1].sent_ms, bridge.CONTROL_TIMEOUT_MS)
        self.assertTrue(any(row["event"] == "SYNC_TIMEOUT" for row in records))

    def test_control_precedes_initial_sync_and_timeout_uses_write_completion(self):
        worker, wire, _ = self.run_wire(write_delay=300, limit=7200)
        level = [row for row in wire.writes if wire_prefix(row[2]) == b"@LEVEL2"]
        self.assertEqual(len(level), 3)
        self.assertTrue(wire_prefix(wire.writes[0][2]) == b"@LEVEL2")
        for previous, following in zip(level, level[1:]):
            self.assertEqual(following[0]-previous[1], bridge.CONTROL_TIMEOUT_MS)
        events = worker.poll_transport_events()
        self.assertEqual([e.sent_ms for e in events[:3]], [row[1] for row in level])
        self.assertEqual(events[-1].at_ms-level[-1][1], bridge.CONTROL_TIMEOUT_MS)

    def test_wrong_nonce_does_not_ack_and_second_write_can_complete(self):
        def respond(wire, packet):
            if wire_prefix(packet) == b"@LEVEL2":
                level, generation, x, y, dx, dy, nonce = level_fields(packet)
                attempt = sum(wire_prefix(row[2]) == b"@LEVEL2" for row in wire.writes)
                if attempt == 1:
                    nonce += 1
                wire.rx.extend(ack_line(f"READY2:{level},{generation},{x},{y},{dx},{dy},{nonce},1000"))

        worker, wire, records = self.run_wire(on_write=respond, limit=4600)
        self.assertEqual(sum(wire_prefix(row[2]) == b"@LEVEL2" for row in wire.writes), 2)
        controls = [row for row in records if row["event"] == "CONTROL_RX"]
        self.assertEqual([row["matched"] for row in controls], [False, True])
        self.assertFalse(any(event.kind == "TIMEOUT" for event in worker.poll_transport_events()))

    def test_ready_start_and_sync_have_actual_tx_rx_records(self):
        def react(worker, event):
            if event["event"] == "CONTROL_RX" and event["command"] == "READY2" and event["matched"]:
                worker.queue_start(event["generation"], event["nonce"])

        def respond(wire, packet):
            if wire_prefix(packet) == b"@LEVEL2":
                level, generation, x, y, dx, dy, nonce = level_fields(packet)
                wire.rx.extend(ack_line(f"READY2:{level},{generation},{x},{y},{dx},{dy},{nonce},50000"))
            elif wire_prefix(packet) == b"@START2":
                wire.rx.extend(ack_line("STARTED2:1,7,123,50020"))
            elif wire_prefix(packet) == b"@SYNC2":
                nonce = struct.unpack("<I", binary.PacketParser().feed(packet)[0][1])[0]
                wire.rx.extend(binary.encode_packet(binary.SYNC_REPLY, struct.pack("<IQQ", nonce, 50000+wire.clock, 50000+wire.clock)))

        _, wire, records = self.run_wire(on_write=respond, trace_hook=react, limit=2000)
        commands = [wire_prefix(row[2]) for row in wire.writes]
        self.assertEqual(commands[:3], [b"@LEVEL2", b"@START2", b"@SYNC2"])
        self.assertTrue(all(row["matched"] for row in records if row["event"] == "CONTROL_RX"))
        self.assertTrue(any(row["event"] == "SYNC_RX" and row["clock_accepted"] for row in records))
        self.assertTrue(any(row["event"] == "RX_BYTES" and row["data_hex"] for row in records))

    def test_new_level_cancels_old_retry(self):
        def select_new(wire):
            if wire.clock == 100:
                wire.worker.queue_level(2, 8, EMITTER, 123)

        worker, wire, _ = self.run_wire(on_read=select_new, limit=4500)
        levels = [level_fields(row[2])[:2] for row in wire.writes if wire_prefix(row[2]) == b"@LEVEL2"]
        self.assertEqual(levels, [(1, 7), (2, 8), (2, 8)])
        self.assertFalse(any(e.kind == "TIMEOUT" and e.generation == 7 for e in worker.poll_transport_events()))

    def test_partial_write_never_starts_a_control_deadline(self):
        def incomplete(wire, packet):
            wire.worker.stop.set()
            return len(packet)-1

        worker, _, records = self.run_wire(on_write=incomplete)
        self.assertEqual(worker.poll_transport_events(), [])
        self.assertTrue(any(row["event"] == "TX_INCOMPLETE" for row in records))
        self.assertFalse(worker.connected)

    def test_duplicate_queue_does_not_restart_deadline(self):
        def repeat(wire):
            if wire.clock % 500 == 0 and wire.clock <= 5500:
                wire.worker.queue_level(1, 7, EMITTER, 123)

        worker, wire, _ = self.run_wire(on_read=repeat, limit=6500)
        self.assertEqual(sum(wire_prefix(row[2]) == b"@LEVEL2" for row in wire.writes), 3)
        events = worker.poll_transport_events()
        self.assertEqual(events[-1].kind, "TIMEOUT")
        self.assertEqual(events[-1].at_ms, events[0].sent_ms + 3*bridge.CONTROL_TIMEOUT_MS)


if __name__ == "__main__":
    unittest.main()
