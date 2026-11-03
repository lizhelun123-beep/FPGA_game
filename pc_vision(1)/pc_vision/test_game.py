"""Focused offline game checks. No serial port, FPGA build or board access."""
import dataclasses
import json
import math
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import zlib

import cv2
import numpy as np

from pc_vision.game_app import read_photo, SceneInput, SerialSceneInput
from pc_vision.game_scene import (GameController, Model, PlaneMapper, Stabilizer,
                                  load_game_config, map_models)
from pc_vision.native import NativeVision
from pc_vision.scene_protocol import Observation, Scene, SceneOrder, StreamParser, decode, encode


def observation(kind="SOURCE", center=(100, 100), axis=(1, 0)):
    return Observation(kind, center, axis, True, (60, 30), 95, center, axis,
                       kind == "SOURCE")


def scene(*objects, frame=1, valid=True):
    return Scene(frame, frame, 0, valid, (1280, 720), tuple(objects))


class ProtocolTests(unittest.TestCase):
    def test_c_encoder_and_bounded_nonblocking_scheduler(self):
        root = Path(__file__).resolve().parents[1]
        app = root / "color_test/software/vision_ps_baremetal"
        with tempfile.TemporaryDirectory(prefix="scene_uart_") as directory:
            executable = Path(directory)/"stream.exe"
            subprocess.run([shutil.which("gcc"), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                f"-I{app / 'src'}", str(app / "src/scene_protocol.c"),
                str(app / "tests/test_scene_stream.c"), "-lm", "-o", str(executable)], check=True, timeout=60)
            wire = subprocess.run([str(executable)], check=True, capture_output=True, timeout=10).stdout
        packets = StreamParser().feed(wire)
        self.assertEqual(len(packets), 6)
        first, boot, full, empty, invalid, rollover = packets
        self.assertEqual((first.frame, first.tx_sequence, first.capture_ms), (123, 45, 6789))
        self.assertEqual(tuple(o.type for o in first.objects),
                         ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL"))
        self.assertEqual(first.objects[0].center, (100.25, 200.5))
        self.assertEqual(first.objects[4].source_direction, (-.8, .6))
        self.assertEqual(first.objects[4].source_tip, (120, 230))
        self.assertTrue(first.objects[4].direction_valid)
        self.assertFalse(boot.valid)
        self.assertEqual((full.frame, len(full.objects)), (10000, 16))
        self.assertTrue(empty.valid)
        self.assertEqual((empty.frame, empty.objects), (10002, ()))
        self.assertFalse(invalid.valid)
        self.assertEqual(rollover.frame, 10004)

    def test_all_split_points_and_atomic_delivery(self):
        expected = scene(observation(), observation("MIRROR"))
        packet = encode(expected)
        for i in range(1, len(packet)):
            parser = StreamParser()
            self.assertEqual(parser.feed(packet[:i]), [])
            self.assertEqual(parser.feed(packet[i:]), [expected])

    def test_logs_concatenation_damage_and_disconnect(self):
        first, second = scene(observation()), scene(observation("WALL"), frame=2)
        packet = encode(first)
        damaged = packet[:30]+b"Z"+packet[31:]
        parser = StreamParser()
        self.assertEqual(parser.feed(b"boot\r\nOBJECT class=SOURCE\r\n"+damaged+
                                     packet+encode(second)), [first, second])
        self.assertEqual(parser.rejected, 1)
        parser.feed(packet[:50])
        parser.disconnect()
        self.assertEqual(parser.feed(packet[50:]), [])
        self.assertEqual(parser.feed(packet), [first])

    def test_dropped_suffix_and_large_logs(self):
        expected = scene(observation())
        parser = StreamParser()
        self.assertEqual(parser.feed(b"log "*100000+encode(expected)[:-6]+encode(expected)), [expected])
        self.assertLessEqual(len(parser.buffer), 828)
        self.assertEqual(parser.rejected, 1)

    def test_checksum_semantics_bounds_and_max_length(self):
        packet = encode(scene(*(observation("WALL") for _ in range(16))))
        self.assertEqual(len(packet), 828)
        self.assertEqual(len(decode(packet).objects), 16)
        corrupted = bytearray(bytes.fromhex(packet[6:-6].decode()))
        corrupted[0] = 2
        corrupted[-4:] = struct.pack("<I", zlib.crc32(corrupted[:-4]))
        with self.assertRaises(ValueError):
            decode(b"@SCN1:"+corrupted.hex().encode()+b":END\r\n")
        packet = bytearray(packet)
        packet[25] = ord("F") if packet[25] != ord("F") else ord("E")
        with self.assertRaises(ValueError):
            decode(bytes(packet))
        self.assertFalse(decode(encode(scene(valid=False))).valid)
        with self.assertRaises(ValueError):
            Scene.from_record({"schema": "old-debug"})


class MappingTests(unittest.TestCase):
    def test_perspective_center_and_direction(self):
        calibration = dict(schema="plane-v1", unit="mm", image_size=[1280, 720],
            image_points=[[100, 100], [1100, 120], [1000, 650], [200, 620]], plane_size=[600, 400])
        mapper = PlaneMapper(calibration)
        for pixel, expected in zip(calibration["image_points"], [(0, 0), (600, 0), (600, 400), (0, 400)]):
            np.testing.assert_allclose(mapper.point(pixel), expected, atol=1e-4)
        actual = mapper.direction((500, 400), (1, 0), 100)
        expected = np.subtract(mapper.point((550, 400)), mapper.point((450, 400)))
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(actual, expected)
        self.assertGreater(abs(actual[1]), .01)  # Must not reuse the image angle.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"plane.json"
            mapper.save(path)
            np.testing.assert_allclose(PlaneMapper.load(path).matrix, mapper.matrix)

    def test_degenerate_and_wrong_resolution_rejected(self):
        calibration = dict(schema="plane-v1", unit="mm", image_size=[1280, 720],
            image_points=[[0, 0], [10, 10], [20, 20], [30, 30]], plane_size=[600, 400])
        with self.assertRaises(ValueError):
            PlaneMapper(calibration)
        calibration["image_size"] = [640, 360]
        with self.assertRaises(ValueError):
            PlaneMapper(calibration)

    def test_fixed_sizes_tip_and_portal_axis(self):
        cfg = load_game_config()
        objects = map_models(scene(observation(), observation("PORTAL_A")), PlaneMapper(), cfg)
        self.assertEqual(objects[0].size, tuple(cfg["model_sizes"]["SOURCE"]))
        np.testing.assert_allclose(objects[0].vertices().mean(axis=0), objects[0].center)
        np.testing.assert_allclose(objects[0].vertices()[0], objects[0].source_tip)
        self.assertEqual(objects[1].axis, (1, 0))
        self.assertEqual(objects[1].size, tuple(cfg["model_sizes"]["PORTAL_A"]))


class StubPhysics:
    def trace(self, objects, *args):
        return dict(segments=[[0, 0, objects[0].center[0], 1]], interactions=0,
                    success=False, termination="BOUNDARY", hits=[])


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_game_config()
        self.game = GameController(StubPhysics(), PlaneMapper(), self.cfg)

    def test_position_and_axis_stability(self):
        stabilizer = Stabilizer(self.cfg)
        model = Model("MIRROR", (100, 100), (1, 0), (140, 12), 90)
        stabilizer.update([model], 0)
        result = stabilizer.update([dataclasses.replace(model, center=(110, 100), axis=(-1, 0))], .1)
        self.assertEqual(result[0].center, (104.5, 100))
        self.assertGreater(result[0].axis[0], .99)
        source = dataclasses.replace(model, type="SOURCE", direction_valid=True)
        stabilizer.clear()
        stabilizer.update([source], 0)
        result = stabilizer.update([dataclasses.replace(source, axis=(-1, 0))], .1)
        self.assertLess(result[0].axis[0], -.99)

    def test_short_and_sustained_dropout_source_immediate(self):
        self.game.accept(scene(observation(), observation("WALL")), 0)
        self.game.accept(scene(), .1)
        self.assertEqual([o.type for o in self.game.live], ["WALL"])
        self.assertTrue(self.game.live[0].held)
        self.assertEqual(self.game.ray["segments"], [])
        self.game.tick(.3)
        self.assertEqual(self.game.live, ())

    def test_lock_pause_unlock_timeout_reset(self):
        self.cfg["timeout_seconds"] = 1.0  # An explicit short timeout still clears.
        self.game.accept(scene(observation()), 0)
        self.assertTrue(self.game.lock(.1))
        fixed, ray = self.game.display, self.game.ray
        self.game.accept(scene(observation(center=(300, 100)), frame=2), .2)
        self.game.tick(2)
        self.assertEqual(self.game.display, fixed)
        self.assertEqual(self.game.ray, ray)
        self.assertFalse(self.game.valid)
        self.game.unlock(2)
        self.assertEqual(self.game.display, ())
        self.game.accept(scene(observation()), 3)
        self.game.pause()
        fixed = self.game.display
        self.game.accept(scene(observation(center=(200, 100)), frame=3), 3.1)
        self.assertEqual(self.game.display, fixed)
        self.game.pause()
        self.assertNotEqual(self.game.display, fixed)
        self.game.reset()
        self.assertFalse(self.game.locked)
        self.assertEqual(self.game.display, ())

    def test_invalid_no_source_and_stale_cannot_lock(self):
        for incoming in (scene(valid=False), scene(observation("TARGET")),
                         scene(observation(), observation())):
            self.game.accept(incoming, 0)
            self.assertFalse(self.game.lock(.01))
            self.assertEqual(self.game.ray["segments"], [])
        self.game.accept(scene(observation()), 1)
        self.assertFalse(self.game.lock(2))

    def test_independent_still_photo_has_no_temporal_blend_or_expiry(self):
        self.game.accept(scene(observation()), 0, True, True)
        self.game.accept(scene(observation(center=(400, 100)), frame=2), .1, True, True)
        self.assertEqual(self.game.display[0].center, (400, 100))
        self.game.tick(1000)
        self.assertTrue(self.game.lock(1000))

    def test_slow_complete_scenes_keep_models_and_rays_until_timeout(self):
        now = 0
        self.game.accept(scene(observation(), observation("TARGET")), now)
        for i, gap in enumerate((.625, 1.5, 2.1, 5.313), 2):
            display, ray = self.game.display, self.game.ray
            for tick in np.arange(now, now+gap, .02):
                self.game.tick(tick)
                self.assertEqual(self.game.display, display)
                self.assertEqual(self.game.ray, ray)
            self.assertEqual(self.game.reason, "Showing last scene (stale)")
            self.assertFalse(self.game.lock(now+gap-.01))
            now += gap
            self.game.accept(scene(observation(center=(100+i, 100)),
                                   observation("TARGET"), frame=i), now)
            self.assertTrue(self.game.ray["segments"])
            self.assertEqual(self.game.reason, "Scene ready")
        self.game.tick(now+self.cfg["timeout_seconds"])
        self.assertEqual(self.game.display, ())
        self.assertFalse(self.game.valid)
        self.assertEqual(self.game.ray["segments"], [])
        self.assertEqual(self.game.reason, "Scene timed out")

    def test_stale_scene_does_not_hide_explicit_source_loss_or_invalid_frame(self):
        for incoming in (scene(), scene(observation("TARGET")), scene(valid=False)):
            with self.subTest(incoming=incoming):
                self.game.reset()
                self.game.accept(scene(observation(), observation("WALL")), 0)
                self.game.tick(1.5)
                self.assertTrue(self.game.ray["segments"])
                self.game.accept(incoming, 1.6)
                self.assertFalse(any(o.type == "SOURCE" for o in self.game.display))
                self.assertEqual(self.game.ray["segments"], [])
                self.game.tick(1.9)
                self.assertFalse(any(o.held for o in self.game.display))
                if not incoming.valid:
                    self.assertEqual(self.game.display, ())
                    self.assertFalse(self.game.valid)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NativeVision()

    @classmethod
    def tearDownClass(cls):
        cls.native.close()

    def test_real_photo_uses_current_six_class_c(self):
        photo = Path(__file__).resolve().parents[1]/"sample_photo/077.png"
        detected = self.native.detect(read_photo(photo), 77)
        self.assertEqual({o.type for o in detected.objects},
                         {"SOURCE", "MIRROR", "PORTAL_A", "PORTAL_B", "TARGET"})
        self.assertTrue(next(o for o in detected.objects if o.type == "SOURCE").direction_valid)

    def test_target_mirror_wall_geometry_and_scale(self):
        source = Model("SOURCE", (100, 100), (1, 0), (54, 40), 100, True)
        target = Model("TARGET", (400, 100), (1, 0), (64, 64), 100)
        result = self.native.trace([source, target], 1000, 700)
        self.assertEqual(result["termination"], "TARGET")
        self.assertAlmostEqual(result["segments"][0][0], source.source_tip[0]+.03, places=3)
        self.assertAlmostEqual(result["segments"][0][2], target.center[0]-target.size[0]/2, places=3)
        mirror = Model("MIRROR", (300, 100), (0, 1), (140, 12), 100)
        result = self.native.trace([source, mirror], 1000, 700)
        self.assertEqual(result["hits"], ["MIRROR"])
        self.assertAlmostEqual(result["segments"][0][2], mirror.mirror_endpoints()[0][0], places=3)
        self.assertAlmostEqual(result["segments"][-1][2], 0, places=3)
        wall = Model("WALL", (300, 100), (0, 1), (160, 30), 100)
        result = self.native.trace([source, wall], 1000, 700)
        self.assertEqual(result["termination"], "WALL")
        self.assertAlmostEqual(result["segments"][0][2], wall.vertices()[:, 0].min(), places=3)

    def test_portal_transfer_target_and_missing_pair(self):
        source = Model("SOURCE", (100, 100), (1, 0), (54, 40), 100, True)
        a = Model("PORTAL_A", (300, 100), (0, 1), (164, 56), 100)
        b = Model("PORTAL_B", (600, 300), (0, 1), (164, 56), 100)
        target = Model("TARGET", (850, 300), (1, 0), (64, 64), 100)
        result = self.native.trace([source, a, b, target], 1000, 700)
        self.assertTrue(result["success"])
        self.assertEqual(result["hits"], ["PORTAL_A", "TARGET"])
        self.assertAlmostEqual(result["segments"][0][2], a.vertices()[:, 0].min(), places=3)
        self.assertAlmostEqual(result["segments"][1][0], b.vertices()[:, 0].max()+.01, places=3)
        self.assertEqual(self.native.trace([source, a], 1000, 700)["termination"], "MISSING_PORTAL")


    def test_moving_rotating_models_and_rays_share_geometry(self):
        cfg = load_game_config()
        cfg.update(position_alpha=1, direction_alpha=1)
        game = GameController(self.native, PlaneMapper(), cfg)
        previous = None
        for i in range(20):
            angle = i*.06
            axis = (math.cos(angle), math.sin(angle))
            game.accept(scene(observation(center=(120+i*2, 130+i), axis=axis),
                              observation("PORTAL_A", center=(600, 500), axis=axis), frame=i+1), i*.125)
            model = next(o for o in game.display if o.type == "SOURCE")
            self.assertEqual(model.size, (54, 40))
            np.testing.assert_allclose(model.center, (120+i*2, 130+i))
            np.testing.assert_allclose(model.axis, axis)
            ray = game.ray["segments"][0]
            np.testing.assert_allclose(ray[:2], np.asarray(model.source_tip)+np.asarray(axis)*.03, atol=.001)
            if previous is not None:
                self.assertNotEqual(previous, ray)
            previous = ray
        # Directed Portal turns keep their sign; SOURCE absence clears rays now.
        game.accept(scene(observation("PORTAL_A", axis=(-1, 0))), 3)
        self.assertEqual(game.ray["segments"], [])
        self.assertEqual(next(o for o in game.live if o.type == "PORTAL_A").axis, (-1, 0))
        game.accept(scene(valid=False), 3.1)
        self.assertEqual(game.display, ())


class SerialTests(unittest.TestCase):
    def test_performance_saved_by_same_fake_reader(self):
        row = b"@PF1 00000001 04 00000002 0000000000000014 000000000000000d\r\n"
        with tempfile.TemporaryDirectory(prefix="perf_receiver_") as directory:
            output = Path(directory)
            worker = SerialSceneInput(SimpleNamespace(serial="FAKE_ONLY", baud=115200), output)
            chunks = [row[:17], row[17:] + encode(self.packet(1))]
            connections = []

            class FakePort:
                def reset_input_buffer(self):
                    pass

                def read(self, size):
                    if chunks:
                        return chunks.pop(0)
                    worker.stop.set()
                    return b""

                def close(self):
                    pass

            def factory(port, baud):
                connections.append((port, baud))
                return FakePort()

            worker.factory = factory
            try:
                worker.start()
                worker.thread.join(timeout=3)
                self.assertFalse(worker.thread.is_alive())
                self.assertIsNone(worker.error)
                self.assertEqual(connections, [("FAKE_ONLY", 115200)])
                self.assertEqual(worker.metrics["scene_frames"], 1)
                self.assertEqual(worker.metrics["performance_records"], 1)
                record, = [json.loads(s) for s in (output / "performance.jsonl").read_text().splitlines()]
                self.assertEqual((record["stage"], record["n"], record["total"], record["maximum"]),
                                 ("detect_six", 2, 20, 13))
                self.assertEqual(record["connection"], 1)
                self.assertGreater(record["received_monotonic"], 0)
            finally:
                worker.close()

    @staticmethod
    def packet(tx, ms=None, **changes):
        value = scene(observation(), frame=tx)
        return dataclasses.replace(value, capture_ms=tx*125 if ms is None else ms, **changes)

    def worker(self, factory=None):
        return SerialSceneInput(SimpleNamespace(serial="FAKE_ONLY", baud=115200), factory=factory)

    def test_sequence_reboot_wrap_reconnect_and_timeout(self):
        gate = SceneOrder()
        self.assertEqual(gate.accept(self.packet(900), 0), (True, True))
        self.assertFalse(gate.accept(self.packet(899), .1)[0])
        self.assertFalse(gate.accept(self.packet(900), 10)[0])  # Timeout never resets sequence.
        boot = Scene(0, 0, 0, False, (1280, 720), ())
        self.assertEqual(gate.accept(boot, 10), (True, True))
        self.assertFalse(gate.accept(self.packet(901), 10.1)[0])
        self.assertEqual(gate.accept(self.packet(1), 10.2), (True, True))
        self.assertFalse(gate.accept(self.packet(902), 10.3)[0])
        self.assertTrue(gate.accept(self.packet(2), 10.4)[0])
        # Damaged/missed boot announcement: three monotonic low-clock packets.
        gate = SceneOrder()
        gate.accept(self.packet(900), 0)
        for i in (1, 2, 3):
            self.assertFalse(gate.accept(self.packet(i), .1)[0])  # Old burst is not a reboot.
        self.assertFalse(gate.accept(self.packet(1), 2.1)[0])
        self.assertFalse(gate.accept(self.packet(2), 2.2)[0])
        self.assertEqual(gate.accept(self.packet(3), 2.3), (True, True))
        gate = SceneOrder()
        gate.accept(self.packet(0xfffffffe, ms=0xfffffffe), 0)
        self.assertTrue(gate.accept(self.packet(1, ms=1), .1)[0])
        worker = self.worker()
        worker.connected = True
        worker.feed(encode(self.packet(1)), 0)
        self.assertEqual(worker.telemetry(.1, .25)["status"], "LIVE")
        self.assertEqual(worker.telemetry(.3, .25)["status"], "STALE")
        worker.disconnected()
        self.assertEqual(worker.telemetry(.3, .25)["status"], "DISCONNECTED")

    def test_slow_rx_rate_is_independent_of_stale_status_and_disconnect_clears(self):
        worker = self.worker()
        worker.connected = True
        for tx, received in enumerate((0, 1.5, 3), 1):
            worker.feed(encode(self.packet(tx)), received)
        event, = worker.poll()
        game = GameController(StubPhysics(), PlaneMapper(), load_game_config())
        game.accept(event[0], event[-1], independent=event[4])
        game.tick(3.3)
        status = worker.telemetry(3.3, .25)
        self.assertEqual(status["status"], "STALE")
        self.assertAlmostEqual(status["hz"], 2/3)
        self.assertTrue(game.ray["segments"])
        self.assertEqual(worker.telemetry(13.01, .25)["hz"], 0)
        worker.disconnected()
        event, = worker.poll()
        game.accept(event[0], event[-1], independent=event[4])
        self.assertEqual(game.display, ())
        self.assertEqual(game.ray["segments"], [])
        self.assertEqual(worker.telemetry(3.3, .25)["hz"], 0)

    def test_high_rate_latest_only_bounded_queue_and_capture_age(self):
        worker = self.worker()
        worker.connected = True
        worker.feed(b"logs\r\n"+b"".join(encode(dataclasses.replace(self.packet(i, ms=0),
            objects=(observation(center=(100+i/100, 100)),))) for i in range(1, 10001)), 10)
        event, = worker.poll()
        self.assertEqual(event[0].frame, 10000)
        self.assertEqual(event[-1], 10)  # UI must not replace receive time with draw time.
        self.assertTrue(event[4])  # First-session reset survives 9999 replacements.
        game = GameController(StubPhysics(), PlaneMapper(), load_game_config())
        game.accept(event[0], event[-1], independent=event[4])
        self.assertEqual(game.display_frame, 10000)
        self.assertEqual(game.display[0].center, (200, 100))
        self.assertEqual(worker.poll(), [])
        self.assertEqual(worker.metrics["overwritten"], 9999)
        self.assertLessEqual(len(worker.times), 128)
        self.assertLessEqual(len(worker.parser.buffer), 828)
        worker.feed(encode(self.packet(9999, ms=0)), 11)
        self.assertEqual(worker.poll(), [])

    def test_fake_reader_reconnect_partial_logs_crc_and_no_real_port(self):
        connected = threading.Event()
        factory_calls = []
        worker = self.worker()

        class FakePort:
            def __init__(self, chunks, fail=False):
                self.chunks, self.fail, self.cleared = list(chunks), fail, False

            def reset_input_buffer(self):
                self.cleared = True

            def read(self, size):
                self_test.assertLessEqual(size, 4096)
                self_test.assertTrue(self.cleared)
                if self.chunks:
                    return self.chunks.pop(0)
                if self.fail:
                    raise OSError("simulated unplug")
                connected.set()
                worker.stop.wait(.01)
                return b""

            def close(self):
                pass

        self_test = self
        packet = encode(self.packet(1))
        damaged = bytearray(packet)
        damaged[20] ^= 1
        streams = [FakePort([packet[:30]], True),
                   FakePort([packet[30:]+b"OBJECT noise\r\n"+damaged+packet+encode(self.packet(2))])]

        def factory(port, baud):
            factory_calls.append((port, baud))
            return streams.pop(0)

        worker.factory = factory
        try:
            worker.start()
            self.assertTrue(connected.wait(timeout=3))
            event, = worker.poll()
            self.assertEqual(event[0].frame, 2)
            self.assertTrue(event[4])
            self.assertEqual(worker.metrics["connections"], 2)
            self.assertGreaterEqual(worker.metrics["crc_or_format_errors"], 1)
            self.assertEqual(factory_calls, [("FAKE_ONLY", 115200)]*2)
            self.assertIsNone(worker.error)
        finally:
            worker.close()
        self.assertFalse(worker.thread.is_alive())

    def test_photo_video_replay_and_original_cli_still_work(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="game_cli_") as directory:
            photo, replay = Path(directory)/"photo", Path(directory)/"replay"
            command = [sys.executable, str(root/"pc_vision/app.py"), "--game", "--headless", "--max-frames", "1"]
            subprocess.run([*command, "--image", str(root/"sample_photo/073.png"), "--output", str(photo)],
                           check=True, capture_output=True, timeout=30)
            subprocess.run([*command, "--replay", str(photo/"scenes.jsonl"), "--output", str(replay)],
                           check=True, capture_output=True, timeout=30)
            self.assertEqual(json.loads((photo/"game_results.json").read_text())[0]["ray"],
                             json.loads((replay/"game_results.json").read_text())[0]["ray"])
            video = Path(directory)/"input.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 8, (1280, 720))
            self.assertTrue(writer.isOpened())
            try:
                writer.write(read_photo(root/"sample_photo/073.png"))
            finally:
                writer.release()
            subprocess.run([*command, "--video", str(video), "--output", str(Path(directory)/"video")],
                           check=True, capture_output=True, timeout=30)
            original = subprocess.run([sys.executable, str(root/"pc_vision/app.py"), "--headless", "--image",
                                      str(root/"sample_photo/073.png"), "--max-frames", "1"],
                                     check=True, capture_output=True, timeout=30)
            self.assertIn("detections", json.loads(original.stdout))


class SchedulingTests(unittest.TestCase):
    def test_slow_recognition_leaves_controller_and_input_poll_available(self):
        entered, release = threading.Event(), threading.Event()

        class SlowDetector:
            def detect(self, frame, sequence):
                entered.set()
                release.wait(timeout=2)
                return scene(observation(), frame=sequence)

        args = SimpleNamespace(image=Path(__file__).resolve().parents[1]/"sample_photo/073.png",
                               photos=None, start_photo=None)
        worker = SceneInput(args, SlowDetector())
        game = GameController(StubPhysics(), PlaneMapper(), load_game_config())
        try:
            worker.start()
            self.assertTrue(entered.wait(timeout=1))
            self.assertEqual(worker.poll(), [])
            game.pause()
            self.assertTrue(game.paused)
            game.reset()
            self.assertFalse(game.paused)
            self.assertTrue(worker.thread.is_alive())
            release.set()
            deadline = time.monotonic()+1
            events = []
            while not events and time.monotonic() < deadline:
                events = worker.poll()
                release.wait(.01)
            self.assertEqual(len(events), 1)
        finally:
            release.set()
            worker.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
