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
from .board_control import ControlFrame, ControlParser, ControlTransportEvent, encode_level
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
        self.assertEqual(pending.missing_mask, 1 << 1)  # PortalA retained; SOURCE removed.

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
        self.assertEqual(PoseParser().feed(b"@SYNC2:1234abcd:12345\r\r\n"), [("1234abcd", 12345)])
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

    def test_control_ack_crc_and_split_rows(self):
        line = encode_level(2, 7, {"point": [32, 500], "direction": [1, 0]}, 19)
        self.assertTrue(line.startswith(b"@LEVEL2:"))
        self.assertLessEqual(len(line), 64)
        # A board response is parsed independently from command rows and may
        # arrive split across UART reads.
        body = "READY2:2,7,32000,500000,1000000,0,19,1234"
        response = ("@%s:%08X\r\n" % (body, zlib.crc32(body.encode("ascii")) & 0xffffffff)).encode("ascii")
        parser = ControlParser()
        self.assertEqual(parser.feed(response[:9]), [])
        frames = parser.feed(response[9:])
        self.assertEqual(frames, [ControlFrame("READY2", 2, 7, 32000, 500000,
                                                1000000, 0, 19, 1234)])
        bad = bytearray(response)
        bad[-4] = ord("0") if bad[-4] != ord("0") else ord("1")
        self.assertEqual(parser.feed(bytes(bad)), [])
        self.assertEqual(parser.rejected, 1)
        self.assertEqual(ControlParser().feed(response + self.rows[0] + response), frames*2)

    def test_c_control_state_and_python_command_round_trip(self):
        folder = Path(self.temporary.name)
        exe = folder/"control.exe"
        compile_host([SRC.parent/"tests/test_beam_control_protocol.c", SRC/"beam_control_protocol.c"], exe)
        self.assertIn(b"PASS_BEAM_CONTROL_PROTOCOL", subprocess.check_output([str(exe)]))
        line = encode_level(15, (1 << 64)-1,
                            {"point": [1234.567, 700.125], "direction": [-.6, .8]}, 0xffffffff)
        frame = ControlParser().feed(subprocess.check_output([str(exe), line.decode().strip()]))[0]
        self.assertEqual((frame.level_id, frame.generation, frame.nonce), (15, (1 << 64)-1, 0xffffffff))
        self.assertEqual((frame.x_milli, frame.y_milli, frame.dx_micro, frame.dy_micro),
                         (1234567, 700125, -600000, 800000))
        exe = folder/"control_state.exe"
        names = ("beam_control_state", "beam_control_protocol", "game_beam", "vision_stabilizer",
                 "ray_game", "vision_ps", "green_target_detector", "vision_overlay")
        compile_host([SRC.parent/"tests/test_beam_control_state.c", *(SRC/(n+".c") for n in names)], exe)
        self.assertIn(b"PASS_BOARD_HANDSHAKE", subprocess.check_output([str(exe)]))


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

    def test_level_two_portal_b_exit_uses_board_normal_for_both_entry_sides(self):
        self.assertEqual(self.config["board_game"]["portal_b_exit_side"],
                         self.config["real_scene"]["beam"]["portal_b_exit_side"])
        emitter = self.config["board_game"]["levels"][1]["emitter"]
        px, py = emitter["point"]
        dx, dy = emitter["direction"]
        for index, (entry_side, rotation) in enumerate(
                (side, angle) for side in (-1, 1) for angle in (0, math.pi/2, math.pi, 3*math.pi/2)):
            now = 900000 + index*1000
            generation = self.core.command(f"select {now} 2")["generation"]
            axis = [math.cos(rotation), math.sin(rotation)]
            normal = [-axis[1], axis[0]]
            models = (
                dict(type="TARGET", center=[1200, 650], axis=[1, 0], size=[64, 64]),
                dict(type="PORTAL_A", center=[px+200*dx, py+200*dy],
                     axis=[entry_side*-dy, entry_side*dx], size=[164, 56]),
                dict(type="PORTAL_B", center=[500, 500], axis=axis, size=[164, 56]))
            frame = PoseFrame(index+1, 1, index+1, now+1, now+2, True, "OK", 14, 0, 0, models)
            state = self.core.frame(now+10, generation, frame, now+1)
            self.assertTrue(state["valid"])
            self.assertEqual(len(state["segments"]), 2)
            x, y, ex, ey = state["segments"][1]
            length = math.hypot(ex-x, ey-y)
            self.assertGreater(((ex-x)*normal[0]+(ey-y)*normal[1])/length, .9999)
            self.assertGreater((x-500)*normal[0]+(y-500)*normal[1], 0)

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

    def test_presenter_filters_only_unrelated_types_and_preserves_raw_observation(self):
        presenter = BoardGamePresenter(self.core,self.config)
        presenter.epoch = 1
        presenter.select(1,300000)
        clock = ClockBounds(300000,300002,1000)
        original = self.frame(10,1010)
        extras = (dict(type='PORTAL_A',center=[20,20],axis=[1,0],size=[164,56]),
                  dict(type='PORTAL_B',center=[220,20],axis=[1,0],size=[164,56]),
                  dict(type='WALL',center=[1100,100],axis=[1,0],size=[160,30]))
        full = dataclasses.replace(original,models=original.models+extras,raw_mask=47)
        # The C authority still refuses an unadapted extra-object scene.
        direct = self.core.frame(300030,self.core.state['generation'],full,300010)
        self.assertFalse(direct['valid'])
        view = presenter.update(full,1,True,clock,300031)
        self.assertTrue(view['valid'])
        self.assertEqual({o['type'] for o in view['models']},{'SOURCE','MIRROR','TARGET'})
        self.assertEqual(view['board_frame'],full.record())
        self.assertEqual(len(full.models),5)
        self.assertEqual(view['captured_ms'],clock.map(full.captured_ms,300031)[1])
        # Missing and duplicate required objects are never repaired by filtering.
        for seq,models in ((11,(original.models[0],)+extras),
                           (12,original.models+(original.models[0],)+extras)):
            bad = dataclasses.replace(full,sequence=seq,tx=seq,captured_ms=1020+seq,
                                      published_ms=1040+seq,models=models)
            rejected = presenter.update(bad,1,True,clock,300100)
            self.assertFalse(rejected['valid'])
            self.assertFalse(self.core.state['valid'])
            self.assertEqual(self.core.state['stars'],0)

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
        expired = 220100+self.config["board_game"]["scene_max_age_ms"]+1
        state = self.core.frame(expired, generation, self.frame(2, 220100, hit=True), 220100)
        self.assertEqual(state["status"], 9)

    def test_serial_open_failure_keeps_start_locked_and_explains_port(self):
        class Transport:
            port = "COM5"
            def queue_level(self, *args):
                pass
            def queue_start(self, *args):
                raise AssertionError("A serial failure must never send START2")

        presenter = BoardGamePresenter(self.core, self.config, Transport())
        presenter.epoch = 1
        presenter.select(1, 100)
        errors = (("could not open port 'COM5': FileNotFoundError(2, 'not found')", "未找到"),
                  ("PermissionError(13, 'Access is denied')", "占用"))
        for now, (error, hint) in enumerate(errors, 110):
            snapshot = presenter.update(None, 1, False, None, now, error)
            self.assertIn("COM5", snapshot["display_status"])
            self.assertIn(hint, snapshot["display_status"])
            self.assertEqual(snapshot["serial_error"], error)
            self.assertFalse(snapshot["serial_connected"])
            self.assertFalse(snapshot["board_ready"])
            self.assertFalse(snapshot["board_started"])
            self.assertEqual(snapshot["models"], [])
            self.assertEqual(self.core.state["game_state"], 1)
            presenter.action({"action": "start"}, now, False)
        # Opening the port alone also does not authorize start before READY2.
        snapshot = presenter.update(None, 2, True, None, 120)
        self.assertEqual(snapshot["board_phase"], "CONFIGURING")
        self.assertFalse(snapshot["board_ready"])
        presenter.action({"action": "start"}, 121, True)
        self.assertEqual(self.core.state["game_state"], 1)

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

    def test_running_scene_survives_hand_occlusion_until_atomic_replacement(self):
        presenter = BoardGamePresenter(self.core, self.config)
        presenter.epoch = 1
        presenter.select(1, 600000)
        clock = ClockBounds(600000, 600002, 1000)
        presenter.update(self.frame(10, 1010), 1, True, clock, 600030)
        presenter.action({"action": "start"}, 600031, True)
        observed = presenter.update(self.frame(11, 1040), 1, True, clock, 600060)
        self.assertEqual(observed["game_state"], 2)
        pending = dataclasses.replace(self.frame(12, 1100, hit=True), valid=False,
            models=(), status="PENDING", raw_mask=0, pending_mask=9, missing_mask=9)
        for now in (600120, 600500, 607000, 620000):
            held = presenter.update(pending if now == 600120 else None, 1, True, clock, now)
            for key in ("models", "segments", "sequence", "captured_ms", "board_frame", "captured_bounds_ms"):
                self.assertEqual(held[key], observed[key])
            self.assertTrue(held["display_held"])
            self.assertFalse(held["valid"])
            self.assertFalse(held["success"])
            self.assertGreater(held["display_age_ms"], observed["display_age_ms"])
            self.assertEqual(self.core.state["game_state"], 2)
            self.assertFalse(self.core.state["valid"])
            self.assertEqual(self.core.state["stars"], 0)
        # A real pose outside the clock/freshness window still cannot score or
        # replace the retained picture, even if its target would be hit.
        stale = presenter.update(self.frame(13, 1200, hit=True), 1, True, clock, 620001)
        self.assertEqual(stale["models"], observed["models"])
        self.assertEqual(self.core.state["game_state"], 2)
        new_clock = ClockBounds(620100, 620102, 2500)
        moved = self.frame(20, 2510)
        moved = dataclasses.replace(moved, models=(dict(moved.models[0], center=[1000, 600]), moved.models[1]))
        replacement = presenter.update(moved, 1, True, new_clock, 620130)
        self.assertEqual(replacement["state"], "LIVE")
        self.assertFalse(replacement["display_held"])
        self.assertEqual(replacement["board_frame"]["sequence"], 20)
        self.assertEqual(replacement["models"][0]["center"], [1000, 600])
        self.assertNotEqual(replacement["sequence"], observed["sequence"])
        self.assertEqual(replacement["models"], self.core.state["models"])
        self.assertEqual(replacement["segments"], self.core.state["segments"])

    def test_running_picture_survives_reconnect_but_clears_on_selection_and_menu(self):
        presenter = BoardGamePresenter(self.core, self.config)
        presenter.epoch = 1
        presenter.select(1, 700000)
        clock = ClockBounds(700000, 700002, 1000)
        observed = presenter.update(self.frame(1, 1010), 1, True, clock, 700030)
        presenter.action({"action": "start"}, 700031, True)
        disconnected = presenter.update(None, 1, False, None, 700100)
        self.assertEqual(disconnected["state"], "DISCONNECTED")
        self.assertEqual(disconnected["models"], observed["models"])
        self.assertFalse(disconnected["valid"])
        resumed = presenter.update(None, 2, True, None, 710000)
        self.assertTrue(resumed["display_held"])
        self.assertEqual(resumed["models"], observed["models"])
        self.assertEqual(resumed["board_frame"], observed["board_frame"])
        self.assertEqual(self.core.state["game_state"], 2)
        self.assertEqual(self.core.state["elapsed_ms"], 9969)
        presenter.select(2, 710001)
        selected = presenter.update(None, 2, True, None, 710002)
        self.assertEqual(selected["models"], [])
        self.assertIsNone(presenter.retained)
        presenter.action({"action": "menu"}, 710003, True)
        menu = presenter.update(None, 2, True, None, 710004)
        self.assertEqual(menu["screen"], "menu")
        self.assertEqual(menu["models"], [])

    def test_start_ack_is_applied_before_processing_same_poll_pose(self):
        class Transport:
            def queue_level(self, *args):
                pass
            def queue_start(self, *args):
                pass

        presenter = BoardGamePresenter(self.core, self.config, Transport())
        presenter.epoch = 1
        presenter.select(1, 800000)
        generation = self.core.state["generation"]
        emitter, nonce = presenter.selected_emitter, presenter.level_nonce
        ready = ControlFrame("READY2", level_id=1, generation=generation, nonce=nonce,
            x_milli=round(emitter["point"][0]*1000), y_milli=round(emitter["point"][1]*1000),
            dx_micro=round(emitter["direction"][0]*1000000), dy_micro=round(emitter["direction"][1]*1000000))
        presenter.update(None, 1, True, None, 800010, controls=[ready])
        presenter.action({"action": "start"}, 800020, True)
        started = ControlFrame("STARTED2", level_id=1, generation=generation, nonce=nonce)
        clock = ClockBounds(800000, 800002, 1000)
        snapshot = presenter.update(self.frame(1, 1040), 1, True, clock, 800040, controls=[started])
        self.assertEqual(presenter.phase, "RUNNING")
        self.assertEqual(presenter.last_frame.sequence, 1)
        self.assertFalse(snapshot["valid"])  # Bounds cross the acknowledged start.
        # A following capture definitely after start is immediately presented.
        snapshot = presenter.update(self.frame(2, 1050), 1, True, clock, 800060)
        self.assertEqual(snapshot["state"], "LIVE")
        self.assertTrue(snapshot["models"])
        self.assertEqual(snapshot["board_frame"]["sequence"], 2)

    def test_live_handshake_gates_start_and_pose_until_board_ack(self):
        class Transport:
            def __init__(self):
                self.levels, self.starts, self.resets = [], [], []
            def queue_level(self, level_id, generation, emitter, nonce):
                self.levels.append((level_id, generation, emitter, nonce))
            def queue_start(self, generation, nonce):
                self.starts.append((generation, nonce))
            def queue_reset(self, generation, nonce):
                self.resets.append((generation, nonce))

        transport = Transport()
        presenter = BoardGamePresenter(self.core, self.config, transport)
        presenter.epoch = 1
        self.assertTrue(presenter.select(2, 100))
        self.assertEqual(presenter.phase, "CONFIGURING")
        self.assertEqual(len(transport.levels), 1)
        generation = self.core.state["generation"]
        nonce = presenter.level_nonce
        before = presenter.update(None, 1, True, None, 110)
        self.assertFalse(before["board_ready"])
        self.assertEqual(before["models"], [])
        # The historical direct-start route still requires a preparation scene.
        self.assertNotEqual(self.core.command("start 111")["status"], 0)
        presenter.action({"action": "start"}, 112, True)
        self.assertEqual(transport.starts, [])
        ignored = presenter.update(self.frame(1, 100), 1, True, ClockBounds(100, 102, 90), 115)
        self.assertEqual(ignored["models"], [])
        self.assertFalse(self.core.state["valid"])
        emitter = presenter.selected_emitter
        ready = ControlFrame("READY2", level_id=2, generation=generation, nonce=nonce,
            x_milli=round(emitter["point"][0]*1000), y_milli=round(emitter["point"][1]*1000),
            dx_micro=round(emitter["direction"][0]*1000000), dy_micro=round(emitter["direction"][1]*1000000))
        presenter.apply_control(ready, 120)
        self.assertEqual(presenter.phase, "READY")
        self.assertTrue(presenter.board_ready)
        presenter.action({"action": "start"}, 130, True)
        self.assertEqual(presenter.phase, "STARTING")
        self.assertEqual(len(transport.starts), 1)
        self.assertEqual(self.core.state["game_state"], 1)
        waiting = presenter.update(None, 1, True, None, 135)
        self.assertEqual(waiting["models"], [])
        presenter.apply_control(ControlFrame("STARTED2", level_id=2, generation=generation,
                                             nonce=nonce, board_ms=140), 145)
        self.assertEqual(presenter.phase, "RUNNING")
        self.assertTrue(presenter.board_started)
        self.assertEqual(self.core.state["game_state"], 2)
        presenter.apply_control(ready, 150)  # Delayed READY never stops a running stream.
        self.assertEqual(presenter.phase, "RUNNING")
        presenter.update(None, 1, False, None, 160)
        presenter.update(None, 2, True, None, 170)
        self.assertEqual(presenter.phase, "CONFIGURING")
        presenter.apply_control(ready, 180)
        self.assertEqual(presenter.phase, "STARTING")
        presenter.apply_control(ControlFrame("STARTED2", level_id=2, generation=generation,
                                             nonce=nonce, board_ms=140), 190)
        self.assertEqual(presenter.phase, "RUNNING")
        presenter.update(None, 2, True, None, 190)
        self.assertEqual(self.core.state["elapsed_ms"], 45)
        presenter.select(2, 200)
        presenter.apply_control(ready, 201)  # Old PC generation is ignored.
        self.assertEqual(presenter.phase, "CONFIGURING")
        presenter.update(None, 2, True, None, 2200)
        presenter.update(None, 2, True, None, 4200)
        queued = presenter.update(None, 2, True, None, 6200)
        self.assertEqual(presenter.phase, "CONFIGURING")
        self.assertIsNone(queued["control_sent_ms"])
        self.assertEqual(queued["control_attempts"], 0)
        generation = self.core.state["generation"]
        for attempt, sent_ms in enumerate((7000, 9000, 11000), 1):
            presenter.apply_transport_event(ControlTransportEvent(
                "SENT", "LEVEL2", generation, nonce, 2, 2, sent_ms, sent_ms, attempt))
            self.assertEqual(presenter.phase, "CONFIGURING")
            self.assertFalse(presenter.board_ready)
        presenter.apply_transport_event(ControlTransportEvent(
            "TIMEOUT", "LEVEL2", generation, nonce, 2, 2, 13000, 11000, 3))
        timeout = presenter.update(None, 2, True, None, 13000)
        self.assertEqual(presenter.phase, "ERROR")
        self.assertFalse(timeout["board_ready"])
        self.assertEqual(self.core.state["game_state"], 1)
        self.assertEqual(self.core.state["elapsed_ms"], 0)
        presenter.action({"action": "menu"}, 13010, True)
        self.assertTrue(transport.resets)
        self.assertEqual(presenter.phase, "IDLE")

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
