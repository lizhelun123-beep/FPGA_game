"""Standalone restored poses -> one C game session -> existing Godot art.

Run with --serial an explicitly confirmed port. --check only builds the host;
it never opens UART. TCP binds loopback and accepts presentation commands only.
"""
import argparse
from collections import deque
from dataclasses import replace
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

from .board_native import NativeBoardGame, ROOT
from .board_pose import TYPES, PoseOrder, ClockBounds
from .board_control import ControlCommand, ControlFrame, ControlTransportEvent
from .board_wire import BinaryParser, encode_level, encode_reset, encode_start, encode_sync
from .teaching import TeachingReceiver

CONTROL_TIMEOUT_MS = 2000
CONTROL_MAX_ATTEMPTS = 3
SYNC_TIMEOUT_MS = 1500
SYNC_INTERVAL_MS = 1500
BRIDGE_BUILD = "20261101-pc-teaching-2"


def now_ms():
    return time.monotonic_ns()//1_000_000


def serial_connection_message(port, error=""):
    device = f"串口 {port}" if port else "设备串口"
    if not error or error == "等待串口连接":
        return f"正在连接{device}"
    text = str(error).lower()
    if any(part in text for part in ("filenotfounderror", "no such file", "not found", "找不到")):
        return f"未找到{device}，请检查端口选择"
    if any(part in text for part in ("permissionerror", "access is denied", "permission denied",
                                     "resource busy", "拒绝访问", "另一个程序")):
        return f"{device}无法打开，请检查串口助手占用或访问权限"
    return f"{device}连接失败，请检查设备连接"


class BoardInput:
    def __init__(self, port, baud, trace=None):
        self.port, self.baud = port, baud
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.epoch = 0
        self.connected = False
        self.clock = None
        self.error = "等待串口连接"
        self.command_lock = threading.Lock()
        self.commands = deque()
        self.controls = deque()
        self.transport_events = deque()
        self.trace = trace
        self.teaching = TeachingReceiver()
        self.thread = threading.Thread(target=self.run, daemon=True, name="board-pose-uart")

    def poll(self):
        with self.lock:
            latest, self.latest = self.latest, None
            return latest, self.epoch, self.connected, self.clock, self.error

    def poll_controls(self):
        with self.lock:
            result = list(self.controls)
            self.controls.clear()
            return result

    def teaching_snapshot(self):
        with self.lock:
            return dict(document=self.teaching.snapshot(), connected=self.connected,
                        rejected=self.teaching.rejected+self.teaching.parser.rejected)

    def receive_teaching(self, data):
        # 同一个UART读块分别交给v3和教学解析器，不另开串口。
        with self.lock:
            changed = self.teaching.feed(data)
        if changed: self.changed.set()
        return changed

    def poll_transport_events(self):
        with self.lock:
            result = list(self.transport_events)
            self.transport_events.clear()
            return result

    def _record(self, event, **fields):
        record = dict(event=event, time_ms=now_ms(), port=self.port, epoch=self.epoch, **fields)
        if event in ("TX_SENT", "CONTROL_RX"):
            record.update(wire_protocol=3, wire_name=fields["command"].replace("2", "3"))
        if self.trace is not None:
            self.trace(record)
        elif event != "RX_BYTES":
            print("UART_TRACE " + json.dumps(record, ensure_ascii=False), flush=True)

    def _transport_event(self, kind, flight, now):
        command = flight["command"]
        with self.lock:
            self.transport_events.append(ControlTransportEvent(
                kind, command.kind, command.generation, int(command.nonce), command.level_id,
                self.epoch, now, flight["sent_ms"], flight["attempt"]))
        self.changed.set()

    def queue_level(self, level_id, generation, emitter, nonce):
        line = encode_level(level_id, generation, emitter, nonce)
        with self.command_lock:
            # A newer selection supersedes unsent START/RESET from old levels.
            self.commands.clear()
            self.commands.append(ControlCommand("LEVEL2", line, generation, nonce, level_id))

    def queue_start(self, generation, nonce):
        line = encode_start(generation, nonce)
        with self.command_lock:
            self.commands.clear()
            self.commands.append(ControlCommand("START2", line, generation, nonce))

    def queue_reset(self, generation, nonce):
        line = encode_reset(generation, nonce)
        with self.command_lock:
            self.commands.clear()
            self.commands.append(ControlCommand("RESET2", line, generation, nonce))

    def run(self):
        import serial
        reported_error = None
        while not self.stop.is_set():
            stream = None
            try:
                stream = serial.Serial(port=None, baudrate=self.baud, timeout=.02,
                                       xonxoff=False, rtscts=False, dsrdtr=False, write_timeout=.1)
                stream.dtr = stream.rts = False
                stream.port = self.port
                stream.open()
                stream.reset_input_buffer()
                reported_error = None
                parser, order = BinaryParser(), PoseOrder()
                next_sync, last_board_ms = 0, None
                in_flight, pending = None, None
                sync_requests = {}
                with self.lock:
                    self.connected, self.clock, self.latest = True, None, None
                    self.teaching = TeachingReceiver()
                    self.controls.clear()
                    self.transport_events.clear()
                    self.epoch += 1
                    self.error = ""
                self._record("CONNECTED", baud=self.baud, build=BRIDGE_BUILD, wire_protocol=3, required_boot=14)
                self.changed.set()
                while not self.stop.is_set():
                    # Consume an already-arrived acknowledgement before testing
                    # its deadline. This is the only serial reader/writer.
                    data = stream.read(min(4096, max(1, stream.in_waiting)))
                    received = now_ms()
                    if data:
                        self._record("RX_BYTES", data_hex=data.hex(), ascii=data.decode("ascii", "backslashreplace"))
                    rejected = parser.rejected
                    self.receive_teaching(data)
                    incoming = parser.feed(data)
                    for control in (item for item in incoming if isinstance(item, ControlFrame)):
                        matched = bool(in_flight and in_flight["command"].accepts(control))
                        self._record("CONTROL_RX", command=control.kind, matched=matched,
                                     generation=control.generation, nonce=control.nonce,
                                     level_id=control.level_id, board_ms=control.board_ms,
                                     emitter=[control.x_milli, control.y_milli, control.dx_micro, control.dy_micro],
                                     error_code=control.error_code)
                        if matched:
                            in_flight = None
                        with self.lock:
                            self.controls.append(control)
                        self.changed.set()
                    if parser.rejected != rejected:
                        self._record("BINARY_RX_REJECTED", wire_protocol=3, count=parser.rejected-rejected)
                    for item in incoming:
                        if isinstance(item, ControlFrame):
                            continue
                        if isinstance(item, tuple):
                            started = sync_requests.pop(item[0], None)
                            matched = bool(in_flight and in_flight["command"].kind == "SYNC2" and
                                           in_flight["command"].nonce == item[0])
                            if matched:
                                in_flight = None
                            if started is not None:
                                if last_board_ms is not None and item[1] < last_board_ms:
                                    order = PoseOrder()
                                    with self.lock:
                                        self.epoch += 1
                                        self.latest = None
                                        self.controls.clear()
                                        self.transport_events.clear()
                                    in_flight = None
                                    sync_requests.clear()
                                    next_sync = 0
                                    self._record("BOARD_RESTART", board_ms=item[1])
                                last_board_ms = item[1]
                                accepted_clock = False
                                with self.lock:
                                    try:
                                        # Clock bounds use the time BEFORE the
                                        # write; control deadlines use completion.
                                        self.clock = ClockBounds(started, received, item[1], item[2])
                                        accepted_clock = True
                                        self.error = ""
                                    except ValueError as error:
                                        if self.clock is not None and received-self.clock.observed_ms > 5000:
                                            self.clock = None
                                        self.error = str(error)
                                self._record("SYNC_RX", nonce=item[0], board_ms=item[1], matched=matched,
                                             board_sent_ms=item[2], round_trip_ms=received-started,
                                             clock_accepted=accepted_clock, wire_protocol=3)
                                self.changed.set()
                            else:
                                self._record("SYNC_RX_UNMATCHED", nonce=item[0], board_ms=item[1])
                            continue
                        with self.lock:
                            accepted, reset = order.accept(item)
                            if not accepted:
                                continue
                            if reset:
                                self.epoch += 1
                                self.clock = None
                                self.transport_events.clear()
                                in_flight = None
                                sync_requests.clear()
                                next_sync = 0
                            self.latest = item
                        self.changed.set()

                    with self.command_lock:
                        queued = list(self.commands)
                        self.commands.clear()
                    for command in queued:
                        if in_flight and command == in_flight["command"] and not in_flight["cancelled"]:
                            continue  # Same queued request must not reset its deadline.
                        if pending == command:
                            continue
                        pending = command
                        if in_flight and in_flight["command"].kind != "SYNC2":
                            in_flight["cancelled"] = True
                        self._record("QUEUED", command=command.kind, generation=command.generation,
                                     nonce=command.nonce, level_id=command.level_id)

                    current, outgoing, attempt = now_ms(), None, 1
                    if in_flight:
                        command = in_flight["command"]
                        limit = SYNC_TIMEOUT_MS if command.kind == "SYNC2" else CONTROL_TIMEOUT_MS
                        if current-in_flight["sent_ms"] >= limit:
                            if command.kind == "SYNC2":
                                self._record("SYNC_TIMEOUT", nonce=command.nonce, sent_ms=in_flight["sent_ms"])
                            elif not in_flight["cancelled"]:
                                if in_flight["attempt"] < CONTROL_MAX_ATTEMPTS:
                                    outgoing, attempt = command, in_flight["attempt"]+1
                                else:
                                    self._transport_event("TIMEOUT", in_flight, current)
                                    self._record("CONTROL_TIMEOUT", command=command.kind,
                                                 generation=command.generation, nonce=command.nonce,
                                                 attempt=in_flight["attempt"], sent_ms=in_flight["sent_ms"])
                            in_flight = None
                    if in_flight is None:
                        # A pending level/start/reset outranks periodic sync,
                        # including immediately after a sync timeout.
                        if pending is not None:
                            outgoing, pending, attempt = pending, None, 1
                        elif outgoing is None and current >= next_sync:
                            nonce = secrets.token_hex(4)
                            outgoing = ControlCommand("SYNC2", encode_sync(nonce), nonce=nonce)
                        if outgoing is not None:
                            if len(outgoing.wire) > 64:
                                raise ValueError("Board command exceeds UART FIFO")
                            started = now_ms()
                            written = stream.write(outgoing.wire)
                            completed = now_ms()
                            if written != len(outgoing.wire):
                                self._record("TX_INCOMPLETE", command=outgoing.kind, written=written,
                                             expected=len(outgoing.wire))
                                raise OSError("Incomplete UART command write")
                            in_flight = dict(command=outgoing, started_ms=started, sent_ms=completed,
                                             attempt=attempt, cancelled=False)
                            self._record("TX_SENT", command=outgoing.kind, generation=outgoing.generation,
                                         nonce=outgoing.nonce, level_id=outgoing.level_id, attempt=attempt,
                                         started_ms=started, sent_ms=completed, byte_count=written,
                                         wire_format="binary-v3", data_hex=outgoing.wire.hex())
                            if outgoing.kind == "SYNC2":
                                sync_requests[str(outgoing.nonce)] = started
                                while len(sync_requests) > 4:
                                    del sync_requests[next(iter(sync_requests))]
                                next_sync = completed+SYNC_INTERVAL_MS
                            else:
                                self._transport_event("SENT", in_flight, completed)
            except (OSError, serial.SerialException) as error:
                if str(error) != reported_error:
                    print(f"BOARD_SERIAL_ERROR port={self.port}: {error}", file=sys.stderr, flush=True)
                    reported_error = str(error)
                with self.lock:
                    self.error = str(error)
                self.changed.set()
            finally:
                if stream is not None:
                    stream.close()
                with self.lock:
                    self.connected, self.clock, self.latest = False, None, None
                self.changed.set()
            self.stop.wait(.5)

    def close(self):
        self.stop.set()
        self.changed.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)


class PresentationSocket:
    """One partial send plus one latest snapshot; no old-state output queue."""
    def __init__(self, port):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", port))
        self.server.listen(1)
        self.server.setblocking(False)
        self.port = self.server.getsockname()[1]
        self.client = None
        self.input = bytearray()
        self.pending = b""
        self.latest = None

    def publish(self, record):
        self.latest = (json.dumps(record, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")

    def drop(self):
        if self.client:
            self.client.close()
        self.client, self.pending, self.input = None, b"", bytearray()

    def poll(self):
        commands = []
        try:
            new, _ = self.server.accept()
            self.drop()
            new.setblocking(False)
            self.client = new
        except BlockingIOError:
            pass
        if self.client is None:
            return commands
        try:
            try:
                part = self.client.recv(4096)
                if not part:
                    self.drop()
                    return commands
                self.input.extend(part)
                if len(self.input) > 8192:
                    raise OSError("Presentation command exceeds bound")
            except BlockingIOError:
                pass
            while b"\n" in self.input:
                end = self.input.index(b"\n")
                row = bytes(self.input[:end])
                del self.input[:end+1]
                try:
                    command = json.loads(row)
                    if isinstance(command, dict) and command.get("action") in ("select", "start", "skip", "menu"):
                        commands.append(command)
                except (ValueError, UnicodeError):
                    pass
            if not self.pending and self.latest:
                self.pending, self.latest = self.latest, None
            if self.pending:
                try:
                    sent = self.client.send(self.pending)
                    self.pending = self.pending[sent:]
                except BlockingIOError:
                    pass
        except OSError:
            self.drop()
        return commands

    def close(self):
        self.drop()
        self.server.close()


class BoardGamePresenter:
    """Maps clocks/admission and atomically presents complete C snapshots.

    Positional filtering lives only on the board. C remains the sole PC game
    authority; a retained image is never submitted back to C for scoring.
    """
    def __init__(self, core, config, transport=None):
        self.core, self.config = core, config
        self.transport = transport
        self.levels = config["board_game"]["levels"]
        self.selected = 0
        self.selected_ms = self.started_ms = 0
        self.epoch = None
        self.retained = None
        self.provenance = None
        self.last_frame = None
        self.message = "选择关卡，摆放实物后开始"
        self.phase = "IDLE"
        self.board_ready = False
        self.board_started = False
        self.level_nonce = secrets.randbits(32) or 1
        self.start_requested_ms = 0
        self.selected_emitter = None
        self.control_sent_ms = None
        self.control_attempts = 0

    def _level(self):
        return next(level for level in self.levels if level["id"] == self.selected)

    def _queue_level(self, now):
        if self.transport is None:
            # Offline C/Godot fixtures do not have a board to acknowledge.
            # Live mode always takes the explicit LEVEL2 -> READY2 path.
            self.phase = "RUNNING"
            self.board_ready = self.board_started = True
            self.message = "挑战开始"
            return
        if self.selected:
            self.transport.queue_level(self.selected, self.core.state["generation"],
                                       self.selected_emitter, self.level_nonce)
        self.phase = "CONFIGURING"
        self.board_ready = self.board_started = False
        self.control_sent_ms, self.control_attempts = None, 0
        self.message = "正在准备场景"

    def select(self, level, now):
        if level not in [item["id"] for item in self.levels]:
            self.message = "请选择关卡"
            return False
        state = self.core.command(f"select {now} {level}")
        self.selected, self.selected_ms, self.started_ms = level, now, 0
        self.selected_emitter = self._level()["emitter"]
        self.retained = self.provenance = None
        self.last_frame = None
        self._queue_level(now)
        return True

    def action(self, command, now, connected):
        action = command.get("action")
        if action == "menu":
            if self.transport is not None and self.selected:
                self.transport.queue_reset(self.core.state["generation"], self.level_nonce or 1)
            self.selected, self.retained, self.provenance = 0, None, None
            self.last_frame = None
            self.phase = "IDLE"
            self.board_ready = self.board_started = False
            self.control_sent_ms, self.control_attempts = None, 0
        elif action == "select":
            level = command.get("level_id")
            if type(level) is int:
                self.select(level, now)
        elif action == "skip" and self.selected:
            ids = [item["id"] for item in self.levels]
            self.select(ids[(ids.index(self.selected)+1) % len(ids)], now)
        elif action == "start" and self.selected and connected:
            if self.transport is not None and (self.phase != "READY" or not self.board_ready):
                self.message = "场景准备完成后即可开始"
            elif self.transport is None:
                self.phase = "RUNNING"
                self.board_started = True
                self.started_ms = now
                self.core.command(f"start {now}")
                self.message = "挑战开始"
            else:
                self.transport.queue_start(self.core.state["generation"], self.level_nonce)
                self.phase = "STARTING"
                self.start_requested_ms = now
                self.board_ready = False
                self.control_sent_ms, self.control_attempts = None, 0
                self.message = "挑战即将开始"

    def apply_control(self, control: ControlFrame, now):
        if self.selected == 0:
            return
        generation = self.core.state["generation"]
        if control.kind == "READY2" and self.phase == "CONFIGURING" and (control.level_id, control.generation, control.nonce) == \
                (self.selected, generation, self.level_nonce):
            emitter = self.selected_emitter
            expected = [round(float(v)*scale) for values, scale in
                        ((emitter["point"], 1000), (emitter["direction"], 1000000)) for v in values]
            if [control.x_milli, control.y_milli, control.dx_micro, control.dy_micro] != expected:
                self.message = "场景准备失败，请重新选择关卡"
                self.phase = "ERROR"
                return
            self.phase = "READY"
            self.board_ready = True
            self.board_started = False
            self.message = "场景已准备，可以开始"
            if self.core.state["game_state"] == 2:
                # Reconnect resumes pose delivery with the existing C timer.
                self.action({"action": "start"}, now, True)
        elif control.kind == "STARTED2" and self.phase == "STARTING" and (control.level_id, control.generation, control.nonce) == \
                (self.selected, generation, self.level_nonce):
            self.phase = "RUNNING"
            self.board_started = True
            self.started_ms = now
            state = self.core.state if self.core.state["game_state"] == 2 else self.core.command(f"start_board {now}")
            if state["status"] != 0:
                self.phase = "READY"
                self.board_started = False
                self.message = "请调整物块后再开始"
            else:
                self.message = "挑战开始"
            self.board_ready = False
        elif control.kind == "ERROR2" and self.phase in ("CONFIGURING", "STARTING") and control.generation == generation and \
                control.nonce == self.level_nonce:
            self.phase = "ERROR"
            self.board_ready = self.board_started = False
            self.message = "场景准备失败，请重新选择关卡"

    def apply_transport_event(self, event: ControlTransportEvent):
        expected = {"CONFIGURING": "LEVEL2", "STARTING": "START2"}.get(self.phase)
        if (not self.selected or event.epoch != self.epoch or event.command != expected or
                (event.generation, event.nonce) != (self.core.state["generation"], self.level_nonce) or
                (event.command == "LEVEL2" and event.level_id != self.selected)):
            return
        if event.kind == "SENT":
            self.control_sent_ms = event.sent_ms
            self.control_attempts = event.attempt
        elif event.kind == "TIMEOUT":
            self.control_sent_ms = event.sent_ms
            self.control_attempts = event.attempt
            self.phase = "ERROR"
            self.board_ready = self.board_started = False
            self.message = "设备响应超时，请重新选择关卡"

    def update(self, frame, epoch, connected, clock, now, error="", *, controls=(), transport_events=()):
        if epoch != self.epoch:
            self.epoch = epoch
            # A camera restart must not reset/pause a running180s timer or
            # replace a frozen result. Invalidate C without blanking the last
            # complete picture of the running level.
            if self.core.state["game_state"] not in (3, 4):
                if self.core.state["game_state"] != 2:
                    self.retained = None
                self.provenance = self.last_frame = None
                if self.selected:
                    self.core.command(f"clear {now}")
            self.board_ready = self.board_started = False
            if self.selected and connected:
                self._queue_level(now)
        if not connected:
            if self.core.state["game_state"] != 2:
                self.retained = None
            if self.core.state["game_state"] not in (3, 4):
                self.provenance = None
            if self.selected:
                self.core.command(f"clear {now}")
            self.phase = "DISCONNECTED" if self.selected else "IDLE"
            self.board_ready = self.board_started = False
            self.message = serial_connection_message(getattr(self.transport, "port", ""), error)
        # A STARTED2 and its first POSE2 may arrive in the same serial read.
        # Evaluate that pose after its ACK under the normal freshness window.
        for event in transport_events:
            self.apply_transport_event(event)
        if connected:
            for control in controls:
                self.apply_control(control, now)
        if connected and frame is not None:
            if self.phase != "RUNNING" or not self.board_started or self.core.state["game_state"] in (3, 4):
                frame = None
        if not connected:
            frame = None
        if frame is not None and frame.wire_version == 3 and (
                frame.level_id != self.selected or frame.session_generation != self.core.state["generation"] or
                frame.nonce != self.level_nonce):
            frame = None  # Never admit a valid-looking pose from another session/level.
        if frame is not None:
            self.last_frame = frame
            if self.selected and frame.sequence:
                if not 0 <= epoch < 65536 or frame.sequence >= 1 << 48:
                    raise ValueError("Board epoch/sequence exceeds the C session namespace")
                # Explicit source namespace mapping across serial reconnects.
                # The complete unmodified board identity remains in board_frame.
                sequence = (epoch << 48) | frame.sequence
                lower, upper = -1, 0
                try:
                    if clock is None:
                        raise ValueError("正在连接设备，请稍候")
                    lower, upper = clock.map(frame.captured_ms, now)
                    valid = (lower >= max(self.selected_ms, self.started_ms) and upper <= now and
                             now-lower <= self.config["board_game"]["scene_max_age_ms"])
                except ValueError as reason:
                    self.message, valid = str(reason), False
                # UART describes every physical detection. C constrains the
                # selected level's exact roster; unrelated pieces must not
                # invalidate an otherwise complete observation of that level.
                # Missing/duplicate required types still fail the same C check.
                required = {obj["type"] for obj in self._level()["objects"]}
                game_frame = replace(frame, models=tuple(obj for obj in frame.models if obj["type"] in required))
                state = self.core.frame(now, self.core.state["generation"], game_frame, max(0, upper), valid,
                                        session_sequence=sequence)
                if (state["valid"] and state["status"] == 0 and
                        state["sequence"] == sequence and state["captured_ms"] == upper):
                    self.provenance = frame.record()
                    self.retained = dict(state, board_frame=frame.record(), display_received_ms=now,
                                         captured_bounds_ms=[lower, upper])
                    self.message = ("转动物块，点亮目标" if state["game_state"] == 2 else
                                    "准备就绪 · 点击开始计时" if state["ready"] else
                                    "请将光线移出目标，再开始挑战")
                elif not valid:
                    self.message = "正在更新物块位置"
                else:
                    self.message = "请摆齐本关物块，保持标记清晰可见"
        if self.selected:
            self.core.command(f"tick {now}")
        if error and connected and self.phase != "ERROR":
            self.message = "正在同步设备时间，请稍候"
        state = self.core.state
        snapshot = dict(state, origin="board_pose_v2_c_game", screen="game" if self.selected else "menu")
        snapshot["state"] = "LIVE" if state["valid"] and connected else "STALE"
        snapshot["display_status"] = self.message
        snapshot["board_frame"] = self.provenance
        snapshot["sequence_space"] = "pc_connection_epoch_16_board_sequence_48"
        snapshot["capture_clock"] = "pc_monotonic_mapped_interval_upper"
        snapshot["board_phase"] = self.phase
        snapshot["board_ready"] = self.board_ready
        snapshot["board_started"] = self.board_started
        snapshot["serial_port"] = getattr(self.transport, "port", "")
        snapshot["serial_connected"] = connected
        snapshot["serial_error"] = error
        snapshot["serial_protocol"] = 3
        snapshot["scene_max_age_ms"] = self.config["board_game"]["scene_max_age_ms"]
        snapshot["control_sent_ms"] = self.control_sent_ms
        snapshot["control_attempts"] = self.control_attempts
        snapshot["display_held"] = False
        snapshot["display_age_ms"] = None
        if not self.selected:
            snapshot.update(models=[], segments=[], level_id=0, ready=False, valid=False, state="MISSING")
        elif not state["valid"] or self.phase != "RUNNING" or not connected:
            snapshot.update(models=[], segments=[], valid=False, success=False)
            limit = self.config["timeout_seconds"]*1000
            if self.last_frame:
                required = sum(1 << TYPES.index(o["type"])
                               for o in next(l for l in self.levels if l["id"] == self.selected)["objects"])
                if self.last_frame.raw_mask & required != required:
                    limit = self.config["dropout_seconds"]*1000
            same_scene = (self.retained and self.retained["generation"] == state["generation"] and
                          self.retained["level_id"] == self.selected)
            # Once timing has started, keep one complete scene until its next
            # accepted replacement, even through hand occlusion/reconnection.
            # Never resubmit retained geometry to C or renew its capture stamps.
            keep_running = state["game_state"] == 2
            keep_preparation = (state["game_state"] == 1 and connected and self.phase == "RUNNING" and
                                same_scene and now-self.retained["captured_bounds_ms"][0] < limit)
            if same_scene and (keep_running or keep_preparation):
                for key in ("models", "segments", "sequence", "captured_ms", "board_frame"):
                    snapshot[key] = self.retained[key]
                snapshot["state"] = "HELD"
                snapshot["display_held"] = True
        if self.retained and snapshot["models"]:
            snapshot["captured_bounds_ms"] = list(self.retained["captured_bounds_ms"])
            snapshot["display_age_ms"] = max(0, now-self.retained["captured_bounds_ms"][0])
        snapshot["ready"] = self.board_ready
        if not connected:
            snapshot["state"] = "DISCONNECTED"
        if self.selected and state["game_state"] in (3, 4):
            snapshot["screen"] = "result"
            snapshot["result"] = dict(stars=state["stars"], elapsed_ms=state["elapsed_ms"],
                                      outcome="目标已点亮" if state["game_state"] == 3 else "时间到")
        return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Explicit board USB-UART port; never scanned")
    parser.add_argument("--list-ports", action="store_true", help="List port names/descriptions without opening a UART")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--port", type=int, default=47632, help="Loopback presentation port")
    parser.add_argument("--godot", type=Path, help="Optional Godot executable to launch")
    parser.add_argument("--cc")
    parser.add_argument("--serial-log", type=Path, help="New JSONL trace file; includes actual TX and raw RX, never overwrites")
    parser.add_argument("--check", action="store_true", help="Build/check C only; no UART, TCP or GUI")
    args = parser.parse_args(argv)
    if args.list_ports:
        try:
            from serial.tools import list_ports
        except ImportError:
            parser.error("Install pyserial: python -m pip install pyserial")
        for port in list_ports.comports():
            print(f"{port.device}\t{port.description}")
        return 0
    if not args.check and not args.serial:
        parser.error("--serial is required for live mode")
    if args.baud <= 0 or not 0 <= args.port <= 65535:
        parser.error("Invalid baud/port")
    core = NativeBoardGame(args.cc)
    if args.check:
        print("C_GAME_READY", core.path, "NO_UART_NO_HARDWARE")
        core.close()
        return 0
    try:
        import serial  # noqa: F401
    except ImportError:
        core.close()
        parser.error("Install pyserial: python -m pip install pyserial")
    trace_file = None

    def record_serial(event):
        row = json.dumps(event, ensure_ascii=False, allow_nan=False)
        if trace_file is not None:
            trace_file.write(row+"\n")
            trace_file.flush()
        if event["event"] != "RX_BYTES":
            print("UART_TRACE "+row, flush=True)

    worker, server, godot = BoardInput(args.serial, args.baud, trace=record_serial), None, None
    try:
        if args.serial_log:
            args.serial_log.parent.mkdir(parents=True, exist_ok=True)
            trace_file = args.serial_log.open("x", encoding="utf-8")
        server = PresentationSocket(args.port)
        config = json.loads((ROOT/"pc_vision/game_config.json").read_text(encoding="utf-8"))
        presenter = BoardGamePresenter(core, config, worker)
        poll_interval = max(.001, min(.01, config["board_game"].get("pump_tick_ms", 10)/1000))
        if args.godot:
            godot = subprocess.Popen([str(args.godot.resolve()), "--path", str(ROOT/"pc_vision/godot"),
                                      "--", f"--bridge=127.0.0.1:{server.port}"])
        worker.thread.start()
        print(f"GODOT_BRIDGE 127.0.0.1:{server.port} serial={args.serial} baud={args.baud} build={BRIDGE_BUILD}")
        while godot is None or godot.poll() is None:
            worker.changed.clear()
            now = now_ms()
            frame, epoch, connected, clock, error = worker.poll()
            # Connection epoch, acknowledgements and the received pose are
            # handled in that order within one complete presentation update.
            snapshot = presenter.update(frame, epoch, connected, clock, now, error,
                transport_events=worker.poll_transport_events(), controls=worker.poll_controls())
            for command in server.poll():
                presenter.action(command, now, connected)
            server.publish(snapshot)
            # New poses/ACKs wake presentation immediately; the bounded tick
            # also services timer and Godot input without a 20ms fixed wait.
            worker.changed.wait(poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()
        if server:
            server.close()
        if trace_file is not None:
            trace_file.close()
        core.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
