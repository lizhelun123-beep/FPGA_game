"""Wire-v3 C/Python interchange, framing recovery and admission; no devices."""
import dataclasses
import math
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

from . import board_wire as wire
from .board_control import ControlFrame
from .board_native import SRC, compile_host, NativeBoardGame, ROOT
from .board_pose import ClockBounds, PoseFrame
from .godot_bridge import BoardGamePresenter
import json


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.folder.name)/'wire.exe'
        compile_host([SRC.parent/'tests/test_beam_wire_protocol.c', SRC/'beam_wire_protocol.c',
                      SRC/'beam_control_protocol.c'], cls.exe)
        cls.packets = subprocess.check_output([str(cls.exe)])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_c_encoded_pose_identity_dimensions_pending_and_sync(self):
        parser = wire.BinaryParser()
        pose, pending, ready, sync = parser.feed(self.packets)
        self.assertEqual(parser.rejected, 0)
        self.assertEqual((pose.wire_version, pose.level_id, pose.session_generation, pose.nonce),
                         (3, 2, 0xfedcba9876543210, 0xff00ff00))
        self.assertEqual((pose.generation, pose.sequence, pose.captured_ms, pose.published_ms),
                         (17, 1234567890123, 123400, 123456))
        self.assertEqual(pose.models[0]['center'], [100.25, 301.125])
        self.assertEqual(pose.models[0]['size'], [164.125, 55.25])
        for index, model in enumerate(pose.models):
            decoded = math.atan2(model['axis'][1], model['axis'][0])
            self.assertLess(abs(math.remainder(decoded-index*.71, math.tau)), .000049)
        self.assertEqual((pending.valid, pending.models, pending.status, pending.missing_mask), (False, (), 'PENDING', 2))
        self.assertEqual(ready.kind, 'READY2')
        self.assertEqual(sync, ('00ff1200', 123400, 123405))

    def test_every_split_binary_zeros_text_noise_and_maximum_buffer(self):
        expected = wire.BinaryParser().feed(self.packets)
        for split in range(len(self.packets)+1):
            parser = wire.BinaryParser()
            actual = parser.feed(b'BEAM_DIAGNOSTICS version=14\r\n'+self.packets[:split])
            actual += parser.feed(self.packets[split:])
            self.assertEqual(actual, expected)
            self.assertEqual(parser.rejected, 0)
        parser = wire.BinaryParser()
        parser.feed(b'\x00\xff'+b'x'*100000)
        self.assertLessEqual(len(parser.framing.buffer), wire.MAX_ENCODED)
        self.assertEqual(parser.feed(self.packets), expected)

    def test_corrupt_crc_length_version_and_truncated_frame_resynchronize(self):
        first = wire.PacketParser().feed(self.packets)[0]
        good = wire.encode_packet(*first)
        raw = bytearray(wire.cobs_decode(good[2:-1]))
        for offset in (0, 2, 4, 12, len(raw)-1):
            corrupted = bytearray(raw)
            corrupted[offset] ^= 1
            parser = wire.BinaryParser()
            found = parser.feed(wire.PREFIX+wire.cobs_encode(corrupted)+b'\x00'+good)
            self.assertEqual(len(found), 1)
            self.assertEqual(parser.rejected, 1)
        for size in range(2, len(good)):
            parser = wire.BinaryParser()
            found = parser.feed(good[:size]+good)
            # A missing final delimiter can be supplied by the next packet's
            # leading zero; that first body is already complete and CRC-valid.
            self.assertEqual(len(found), 2 if size == len(good)-1 else 1)

    def test_all_control_messages_python_to_c_and_fifo_bound(self):
        emitter = {'point': [1234.567, 700.125], 'direction': [-.6, .8]}
        generation, nonce = (1 << 64)-1, 0xffffffff
        commands = [wire.encode_level(15, generation, emitter, nonce),
                    wire.encode_start(generation, nonce), wire.encode_reset(generation, nonce),
                    wire.encode_sync('ff00ff00')]
        self.assertEqual([len(row) for row in commands], [43, 26, 26, 18])
        self.assertTrue(all(len(row) <= 64 for row in commands))
        responses = wire.BinaryParser().feed(subprocess.check_output([str(self.exe), 'roundtrip'], input=b''.join(commands)))
        self.assertEqual([r.kind for r in responses[:3]], ['READY2', 'STARTED2', 'RESET2ACK'])
        self.assertEqual((responses[0].level_id, responses[0].generation, responses[0].nonce), (15, generation, nonce))
        self.assertEqual((responses[0].x_milli, responses[0].dx_micro), (1234567, -600000))
        self.assertEqual(responses[3], ('ff00ff00', 123400, 123405))

    def test_noise_and_v2_text_cannot_be_accepted_as_v3(self):
        parser = wire.BinaryParser()
        self.assertEqual(parser.feed(b'@SYNC2:12345678:123456\r\n@LEVEL2:bad\r\n'+b'x'*100000), [])
        random_source = random.Random(42)
        data = bytes(random_source.randrange(256) for _ in range(100000))
        self.assertEqual(parser.feed(data), [])
        self.assertEqual(len(parser.feed(self.packets)), 4)

    def test_crc_valid_semantically_invalid_pose_is_rejected(self):
        _, body = wire.PacketParser().feed(self.packets)[0]
        for offset, value in ((0, 0), (49, 2), (50, 1), (51, 0xff), (54, 6), (55, 0), (56, 4), (57, 0)):
            payload = bytearray(body); payload[offset] = value
            parser = wire.BinaryParser()
            self.assertEqual(parser.feed(wire.encode_packet(wire.POSE, payload)), [])
            self.assertEqual(parser.rejected, 1)

    def test_geometry_quantization_error_bounds_and_packet_sizes(self):
        random_source = random.Random(11)
        for sequence in range(1, 301):
            angle = random_source.uniform(-math.pi, math.pi)
            x, y = random_source.uniform(0, 1279), random_source.uniform(0, 719)
            length, width = random_source.uniform(1, 4096), random_source.uniform(1, 4096)
            model = dict(type='MIRROR', center=[x, y], axis=[math.cos(angle), math.sin(angle)], size=[length, width])
            frame = PoseFrame(sequence, 1, sequence, sequence, sequence+1, True, 'OK', 1, 0, 0, (model,))
            packet = wire.encode_pose(frame, 2, 7, 19)
            decoded = wire.BinaryParser().feed(packet)[0].models[0]
            self.assertLessEqual(max(abs(a-b) for a, b in zip(decoded['center'], model['center'])), 1/32+1e-9)
            self.assertLessEqual(max(abs(a-b) for a, b in zip(decoded['size'], model['size'])), 1/16+1e-9)
            self.assertLessEqual(abs(math.remainder(math.atan2(*reversed(decoded['axis']))-angle, math.tau)), math.pi/65536+1e-9)
        frames = wire.BinaryParser().feed(self.packets)
        pose = frames[0]
        self.assertEqual(len(wire.encode_pose(dataclasses.replace(pose, models=pose.models[:3]), 2, 7, 19)), 106)
        self.assertEqual(len(wire.encode_pose(pose, 2, 7, 19)), 130)

    def test_sync_processing_time_is_removed_without_relaxing_uncertainty(self):
        clock = ClockBounds(1000, 1320, 500, 600)
        self.assertEqual((clock.low, clock.high), (500, 720))
        with self.assertRaises(ValueError):
            ClockBounds(1000, 1400, 500, 600)
        with self.assertRaises(ValueError):
            ClockBounds(1000, 1010, 500, 520)

    def test_pose_from_old_session_never_replaces_running_scene(self):
        core = NativeBoardGame()
        try:
            config = json.loads((ROOT/'pc_vision/game_config.json').read_text(encoding='utf-8'))
            presenter = BoardGamePresenter(core, config)
            presenter.epoch = 1
            presenter.select(1, 1000)
            presenter.started_ms = 1000
            pose = wire.BinaryParser().feed(self.packets)[0]
            snapshot = presenter.update(pose, 1, True, ClockBounds(1000, 1000, 123400), 1010)
            self.assertIsNone(presenter.last_frame)
            self.assertEqual(snapshot['models'], [])
        finally:
            core.close()


if __name__ == '__main__':
    unittest.main()
