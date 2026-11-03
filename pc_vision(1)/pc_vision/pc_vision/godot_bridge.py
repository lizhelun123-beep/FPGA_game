"""Standalone restored poses -> one C game session -> existing Godot art.

Run with --serial an explicitly confirmed port. --check only builds the host;
it never opens UART. TCP binds loopback and accepts presentation commands only.
"""
import argparse
import json
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time

from .board_native import NativeBoardGame, ROOT
from .board_pose import TYPES, PoseOrder, PoseParser, ClockBounds


def now_ms():
    return time.monotonic_ns()//1_000_000


class BoardInput:
    def __init__(self, port, baud):
        self.port, self.baud = port, baud
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.epoch = 0
        self.connected = False
        self.clock = None
        self.error = "等待串口连接"
        self.thread = threading.Thread(target=self.run, daemon=True, name="board-pose-uart")

    def poll(self):
        with self.lock:
            latest, self.latest = self.latest, None
            return latest, self.epoch, self.connected, self.clock, self.error

    def run(self):
        import serial
        while not self.stop.is_set():
            stream = None
            try:
                stream = serial.Serial(port=None, baudrate=self.baud, timeout=.02,
                                       xonxoff=False, rtscts=False, dsrdtr=False, write_timeout=.1)
                stream.dtr = stream.rts = False
                stream.port = self.port
                stream.open()
                stream.reset_input_buffer()
                parser, order = PoseParser(), PoseOrder()
                nonce, sync_sent, next_sync = None, 0, 0
                with self.lock:
                    self.connected, self.clock, self.latest = True, None, None
                    self.epoch += 1
                    self.error = "等待 POSE2 与板端校时"
                while not self.stop.is_set():
                    current = now_ms()
                    if current >= next_sync:
                        nonce, sync_sent = secrets.token_hex(4), current
                        stream.write(("@SYNC2:"+nonce+"\n").encode("ascii"))
                        next_sync = current+1500
                    data = stream.read(min(4096, max(1, stream.in_waiting)))
                    received = now_ms()
                    for item in parser.feed(data):
                        with self.lock:
                            if isinstance(item, tuple):
                                if item[0] == nonce:
                                    try:
                                        self.clock = ClockBounds(sync_sent, received, item[1])
                                        self.error = ""
                                    except ValueError as error:
                                        self.clock, self.error = None, str(error)
                                continue
                            accepted, reset = order.accept(item)
                            if not accepted:
                                continue
                            if reset:
                                self.epoch += 1
                                self.clock = None
                                next_sync = 0
                            self.latest = item
            except (OSError, serial.SerialException) as error:
                with self.lock:
                    self.error = str(error)
            finally:
                if stream is not None:
                    stream.close()
                with self.lock:
                    self.connected, self.clock, self.latest = False, None, None
            self.stop.wait(.5)

    def close(self):
        self.stop.set()
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
    """Maps clocks/admission, transports C snapshots and bounds display hold.

    Positional filtering lives only on the board. C remains the sole PC game
    authority; a retained image is never submitted back to C for scoring.
    """
    def __init__(self, core, config):
        self.core, self.config = core, config
        self.levels = config["board_game"]["levels"]
        self.selected = 0
        self.selected_ms = self.started_ms = 0
        self.epoch = None
        self.retained = None
        self.provenance = None
        self.last_frame = None
        self.message = "选择关卡，摆放实物后开始"

    def select(self, level, now):
        if level not in [item["id"] for item in self.levels]:
            self.message = "此关尚未配置"
            return False
        self.core.command(f"select {now} {level}")
        self.selected, self.selected_ms, self.started_ms = level, now, 0
        self.retained = self.provenance = None
        self.message = "摆放本关物体 · 等待板端确认"
        return True

    def action(self, command, now, connected):
        action = command.get("action")
        if action == "menu":
            self.selected, self.retained, self.provenance = 0, None, None
        elif action == "select":
            level = command.get("level_id")
            if type(level) is int:
                self.select(level, now)
        elif action == "skip" and self.selected:
            ids = [item["id"] for item in self.levels]
            self.select(ids[(ids.index(self.selected)+1) % len(ids)], now)
        elif action == "start" and self.selected and connected:
            state = self.core.command(f"start {now}")
            if state["status"] == 0:
                self.started_ms = now
            else:
                self.message = "开始需要新鲜、完整、尚未命中目标的场景"

    def update(self, frame, epoch, connected, clock, now, error=""):
        if epoch != self.epoch:
            self.epoch = epoch
            # A camera restart must not reset/pause a running180s timer or
            # replace a frozen result. Clear geometry without selecting a level.
            if self.core.state["game_state"] not in (3, 4):
                self.retained = self.provenance = self.last_frame = None
                if self.selected:
                    self.core.command(f"clear {now}")
        if not connected:
            self.retained = None
            if self.core.state["game_state"] not in (3, 4):
                self.provenance = None
            if self.selected:
                self.core.command(f"clear {now}")
        elif frame is not None:
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
                        raise ValueError("等待板端校时")
                    lower, upper = clock.map(frame.captured_ms, now)
                    valid = (lower >= max(self.selected_ms, self.started_ms) and upper <= now and
                             now-lower <= self.config["board_game"]["scene_max_age_ms"])
                except ValueError as reason:
                    self.message, valid = str(reason), False
                state = self.core.frame(now, self.core.state["generation"], frame, max(0, upper), valid,
                                        session_sequence=sequence)
                if (state["valid"] and state["status"] == 0 and
                        state["sequence"] == sequence and state["captured_ms"] == upper):
                    self.provenance = frame.record()
                    self.retained = dict(state, board_frame=frame.record(), display_received_ms=now,
                                         captured_bounds_ms=[lower, upper])
                    self.message = ("场景已确认" if state["game_state"] == 2 else
                                    "场景就绪 · 点击开始计时" if state["ready"] else
                                    "准备场景已命中 · 请先调整物块再开始")
                elif not valid:
                    self.message = "定位待更新 / 校时或帧龄未满足250ms"
                else:
                    self.message = "等待完整定位 · " + frame.status
        if self.selected:
            self.core.command(f"tick {now}")
        if error:
            self.message = error
        state = self.core.state
        snapshot = dict(state, origin="board_pose_v2_c_game", screen="game" if self.selected else "menu")
        snapshot["state"] = "LIVE" if state["valid"] and connected else "STALE"
        snapshot["display_status"] = self.message
        snapshot["board_frame"] = self.provenance
        snapshot["sequence_space"] = "pc_connection_epoch_16_board_sequence_48"
        snapshot["capture_clock"] = "pc_monotonic_mapped_interval_upper"
        if not self.selected:
            snapshot.update(models=[], segments=[], level_id=0, ready=False, valid=False, state="MISSING")
        elif not state["valid"]:
            snapshot.update(models=[], segments=[])
            limit = self.config["timeout_seconds"]*1000
            if self.last_frame:
                required = sum(1 << TYPES.index(o["type"])
                               for o in next(l for l in self.levels if l["id"] == self.selected)["objects"])
                if self.last_frame.raw_mask & required != required:
                    limit = self.config["dropout_seconds"]*1000
            if connected and self.retained and now-self.retained["captured_bounds_ms"][0] < limit:
                for key in ("models", "segments", "sequence", "captured_ms", "board_frame"):
                    snapshot[key] = self.retained[key]
                snapshot["state"] = "HELD"
            snapshot["success"] = False
        if not connected:
            snapshot["state"] = "DISCONNECTED"
            snapshot["models"], snapshot["segments"] = [], []
        if self.selected and state["game_state"] in (3, 4):
            snapshot["screen"] = "result"
            snapshot["result"] = dict(stars=state["stars"], elapsed_ms=state["elapsed_ms"],
                                      outcome="目标已点亮" if state["game_state"] == 3 else "时间到")
        return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Explicit board USB-UART port; never scanned")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--port", type=int, default=47632, help="Loopback presentation port")
    parser.add_argument("--godot", type=Path, help="Optional Godot executable to launch")
    parser.add_argument("--cc")
    parser.add_argument("--check", action="store_true", help="Build/check C only; no UART, TCP or GUI")
    args = parser.parse_args(argv)
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
    worker, server, godot = BoardInput(args.serial, args.baud), None, None
    try:
        server = PresentationSocket(args.port)
        config = json.loads((ROOT/"pc_vision/game_config.json").read_text(encoding="utf-8"))
        presenter = BoardGamePresenter(core, config)
        if args.godot:
            godot = subprocess.Popen([str(args.godot.resolve()), "--path", str(ROOT/"pc_vision/godot"),
                                      "--", f"--bridge=127.0.0.1:{server.port}"])
        worker.thread.start()
        print(f"GODOT_BRIDGE 127.0.0.1:{server.port} serial={args.serial} baud={args.baud}")
        while godot is None or godot.poll() is None:
            now = now_ms()
            frame, epoch, connected, clock, error = worker.poll()
            # Admission precedes actions so start cannot use a stale/invalid
            # observation when both arrive during this iteration.
            snapshot = presenter.update(frame, epoch, connected, clock, now, error)
            for command in server.poll():
                presenter.action(command, now, connected)
            server.publish(snapshot)
            worker.stop.wait(.02)
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()
        if server:
            server.close()
        core.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
