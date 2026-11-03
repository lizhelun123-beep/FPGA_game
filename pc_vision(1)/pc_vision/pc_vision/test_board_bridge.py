"""No real UART. Exercise C encoding, C gameplay and Godot transport separately."""
import dataclasses
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
import zlib

from .board_native import NativeBoardGame, compile_host, ROOT, SRC
from .board_pose import HEADER, PREFIX, SUFFIX, decode_pose, PoseParser, PoseOrder, ClockBounds, PoseFrame
from .godot_bridge import BoardGamePresenter, PresentationSocket


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.temporary.name)/("pose.exe" if os.name == "nt" else "pose")
        compile_host([SRC.parent/"tests/test_beam_pose_packet.c", SRC/"beam_pose_protocol.c"], cls.exe)
        cls.wire = subprocess.check_output([str(cls.exe)])
        cls.rows = cls.wire.splitlines(keepends=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_c_packet_and_pending_never_carries_old_pose(self):
        frame, pending = map(decode_pose, self.rows)
        self.assertEqual((frame.sequence, frame.captured_ms, frame.published_ms), (456, 1000, 1099))
        self.assertEqual(len(frame.models), 5)
        self.assertAlmostEqual(frame.models[0]["center"][0], 100.25)
        self.assertEqual(pending.status, "PENDING")
        self.assertFalse(pending.valid)
        self.assertEqual(pending.models, ())

    def test_every_split_noise_sync_and_crc_recovery(self):
        for split in range(len(self.wire)+1):
            parser = PoseParser()
            found = parser.feed(b"logs\n"+self.wire[:split])+parser.feed(self.wire[split:])
            self.assertEqual(len(found), 2)
        parser = PoseParser()
        damaged = bytearray(self.rows[0]); damaged[35] ^= 1
        found = parser.feed(bytes(damaged)+b"@SYNC2:1234abcd:12345\r\n"+self.rows[1])
        self.assertEqual(parser.rejected, 1)
        self.assertEqual(found[0], ("1234abcd", 12345))
        self.assertEqual(found[1].status, "PENDING")
        parser.feed(b"x"*100000)
        self.assertLessEqual(len(parser.buffer), 404)

    def test_invalid_pose_semantics_rejected_even_with_valid_crc(self):
        data = bytearray.fromhex(self.rows[0][len(PREFIX):-len(SUFFIX)].decode())
        for position, value in ((0, 1), (3, 1), (HEADER.size, 4), (HEADER.size+1, 0)):
            bad = bytearray(data)
            bad[position] = value
            struct.pack_into("<I", bad, len(bad)-4, zlib.crc32(bad[:-4]))
            with self.assertRaises(ValueError):
                decode_pose(PREFIX+bad.hex().encode()+SUFFIX)

    def test_duplicates_restart_and_clock_bounds(self):
        frame = decode_pose(self.rows[0])
        order = PoseOrder()
        self.assertTrue(order.accept(frame)[0])
        self.assertFalse(order.accept(frame)[0])
        self.assertFalse(order.accept(dataclasses.replace(frame, sequence=455))[0])
        boot = dataclasses.replace(frame, tx=0, sequence=0, captured_ms=0, valid=False, models=())
        self.assertEqual(order.accept(boot), (True, True))
        self.assertTrue(order.accept(frame)[0])
        clock = ClockBounds(2000, 2020, 1000)
        self.assertEqual(clock.map(1100, 2100), (2099, 2121))
        with self.assertRaises(ValueError):
            clock.map(1100, 8000)
        with self.assertRaises(ValueError):
            ClockBounds(0, 251, 1)


class CGameTests(unittest.TestCase):
    def setUp(self):
        self.core = NativeBoardGame()
        self.config = json.loads((ROOT/"pc_vision/game_config.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.core.close()

    def frame(self, sequence, captured, hit=False):
        emitter = self.config["board_game"]["levels"][0]["emitter"]
        point, direction = emitter["point"], emitter["direction"]
        target = [point[i]+180*direction[i] for i in (0, 1)] if hit else [100, 650]
        models = (dict(type="MIRROR", center=[1100, 650], axis=[1, 0], size=[140, 12]),
                  dict(type="TARGET", center=target, axis=[1, 0], size=[64, 64]))
        return PoseFrame(sequence, 1, sequence, captured, captured+20, True, "OK", 9, 0, 0, models)

    def test_menu_slots_and_original_three_layouts_fixed_emitters(self):
        game = self.config["board_game"]
        self.assertEqual(tuple(game["selection"][key] for key in ("version", "slot_count", "columns", "rows")), (1, 15, 5, 3))
        self.assertEqual(len(game["levels"]), 15)
        for index, level in enumerate(game["levels"][:3], 1):
            self.assertEqual(level["reference"], f"sample_photo/{74+index:03d}.png")
            self.assertFalse(any(o["type"] == "SOURCE" for o in level["objects"]))
            self.assertAlmostEqual(math.hypot(*level["emitter"]["direction"]), 1)
            old_centers = ([354.1875, 465.3125], [998.3125, 323], [972.875, 517.375])
            for axis in (0, 1):
                old_center = level["emitter"]["point"][axis]-level["emitter"]["direction"][axis]*(36+3/self.config["physics_scale"])
                self.assertAlmostEqual(old_center, old_centers[index-1][axis])
            state = self.core.command(f"select {10000+index} {index}")
            self.assertEqual(state["status"], 0)
        for level_id in range(4, 16):
            state = self.core.command(f"select {10000+level_id} {level_id}")
            self.assertEqual(state["status"], 0)
        self.assertEqual(self.core.command("select 10020 16")["status"], 5)

    def test_random_layouts_preserve_first_three_and_are_visible_and_repeatable(self):
        from .level_layouts import populate_random_levels
        seed = self.config["board_game"]["selection"]["random_seed"]
        generated = populate_random_levels(self.config, seed)
        levels = generated["board_game"]["levels"]
        self.assertEqual(levels, self.config["board_game"]["levels"])
        changed = populate_random_levels(self.config, seed+1)["board_game"]["levels"]
        self.assertEqual(changed[:3], levels[:3])
        self.assertNotEqual(changed[3:], levels[3:])
        self.assertEqual(len({json.dumps(l["objects"], sort_keys=True) for l in levels[3:]}), 12)
        for level in levels[3:]:
            self.assertEqual(level["solvability"], "not_checked")
            self.assertAlmostEqual(math.hypot(*level["emitter"]["direction"]), 1)
            kinds = {obj["type"] for obj in level["objects"]}
            self.assertIn("TARGET", kinds)
            self.assertIn("MIRROR", kinds)
            self.assertEqual("PORTAL_A" in kinds, "PORTAL_B" in kinds)
            self.assertNotIn("SOURCE", kinds)
            for obj in level["objects"]:
                self.assertAlmostEqual(math.hypot(*obj["axis"]), 1)
                length, width = self.config["model_sizes"][obj["type"]]
                ax, ay = obj["axis"]
                for center, radius, maximum in zip(obj["center"],
                    ((abs(ax)*length+abs(ay)*width)/2, (abs(ay)*length+abs(ax)*width)/2), (1279, 719)):
                    self.assertGreaterEqual(center-radius, 0)
                    self.assertLessEqual(center+radius, maximum)

    def test_preparation_start_fresh_hit_and_old_generation_rejected(self):
        state = self.core.command("select 20000 1")
        generation = state["generation"]
        frame = self.frame(11, 20010)
        state = self.core.frame(20020, generation, frame, 20010)
        self.assertTrue(state["ready"])
        self.assertEqual(len(state["models"]), 3)  # Two physical + logical source.
        source = next(o for o in state["models"] if o["type"] == "SOURCE")
        self.assertTrue(source["logical_emitter"])
        self.assertEqual(state["segments"][0][:2], source["center"])
        self.assertEqual(self.core.command("start 20021")["game_state"], 2)
        hit = self.frame(12, 20030, hit=True)
        state = self.core.frame(20040, generation, hit, 20030)
        self.assertEqual((state["game_state"], state["stars"]), (3, 3))
        new = self.core.command("select 20041 2")
        old = self.core.frame(20042, generation, hit, 20030)
        self.assertEqual(old["status"], 6)
        self.assertEqual(old["generation"], new["generation"])

    def test_pending_stale_disconnect_never_score_and_timer_continues(self):
        state = self.core.command("select 30000 1")
        generation = state["generation"]
        self.core.frame(30020, generation, self.frame(1, 30010), 30010)
        self.core.command("start 30021")
        frame = dataclasses.replace(self.frame(2, 30030, hit=True), valid=False, status="PENDING", models=())
        state = self.core.frame(30040, generation, frame, 30030)
        self.assertEqual(state["game_state"], 2)
        self.assertFalse(state["valid"])
        self.assertEqual(self.core.command("tick 210021")["game_state"], 4)
        state = self.core.command("select 220000 1")
        generation = state["generation"]
        self.core.frame(220020, generation, self.frame(1, 220010), 220010)
        self.assertTrue(self.core.state["ready"])
        self.core.command("clear 220021")
        self.assertFalse(self.core.state["ready"])
        state = self.core.frame(220400, generation, self.frame(2, 220100, hit=True), 220100)
        self.assertEqual(state["status"], 9)

    def test_presentation_hold_preserves_stamps_and_has_no_effect_on_c(self):
        presenter = BoardGamePresenter(self.core, self.config)
        presenter.epoch = 1
        presenter.select(1, 300000)
        clock = ClockBounds(300000, 300002, 1000)
        frame = self.frame(10, 1010)
        snapshot = presenter.update(frame, 1, True, clock, 300030)
        self.assertEqual(snapshot["state"], "LIVE")
        pending = dataclasses.replace(frame, sequence=11, captured_ms=1100, valid=False,
                                      models=(), status="PENDING", pending_mask=1)
        held = presenter.update(pending, 1, True, clock, 300120)
        self.assertEqual(held["state"], "HELD")
        self.assertEqual(held["sequence"], (1 << 48) | 10)
        self.assertEqual(held["board_frame"]["captured_ms"], 1010)
        self.assertFalse(self.core.state["valid"])
        disconnected = presenter.update(None, 1, False, None, 300121)
        self.assertEqual(disconnected["state"], "DISCONNECTED")
        self.assertEqual(disconnected["models"], [])

    def test_board_reconnect_keeps_running_timer_and_frozen_result_provenance(self):
        presenter = BoardGamePresenter(self.core, self.config)
        presenter.epoch = 1
        presenter.select(1, 500000)
        clock = ClockBounds(500000, 500002, 1000)
        presenter.update(self.frame(1, 1010), 1, True, clock, 500030)
        presenter.action({"action": "start"}, 500031, True)
        generation = self.core.state["generation"]
        presenter.update(None, 1, False, None, 500040)
        presenter.update(None, 2, True, None, 501000)
        self.assertEqual(self.core.state["game_state"], 2)
        self.assertEqual(self.core.state["generation"], generation)
        self.assertEqual(self.core.state["elapsed_ms"], 969)
        fresh_clock = ClockBounds(501000, 501002, 2000)
        won = presenter.update(self.frame(1, 2040, hit=True), 2, True, fresh_clock, 501060)
        self.assertEqual(won["game_state"], 3)
        unchanged = presenter.update(self.frame(2, 2060), 2, True, fresh_clock, 501080)
        self.assertEqual(unchanged["board_frame"]["sequence"], 1)
        self.assertEqual(unchanged["board_frame"]["captured_ms"], 2040)
        offline_result = presenter.update(None, 3, False, None, 501090)
        self.assertEqual(offline_result["game_state"], 3)
        self.assertEqual(offline_result["board_frame"]["captured_ms"], 2040)
        self.assertEqual(offline_result["models"], [])


class SocketTests(unittest.TestCase):
    def test_loopback_complete_snapshot_and_command(self):
        server = PresentationSocket(0)
        client = socket.create_connection(("127.0.0.1", server.port))
        client.settimeout(1)
        try:
            server.publish(dict(models=[], segments=[], sequence=100))
            server.poll()
            self.assertEqual(json.loads(client.recv(4096))["sequence"], 100)
            client.sendall(b'{"action":"select","level_id":2}\n')
            self.assertEqual(server.poll(), [dict(action="select", level_id=2)])
            client.sendall(b'{"action":"inject","models":[]}\n')
            self.assertEqual(server.poll(), [])
        finally:
            client.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
