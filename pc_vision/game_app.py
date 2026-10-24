"""Photo/video/replay and explicit UART input for the canonical game view."""
from collections import deque
import json
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from .game_scene import GameController, PlaneMapper, load_game_config
from .game_view import GameView
from .native import NativeVision, NativeGame
from .scene_protocol import Scene, SceneOrder, StreamParser


def read_photo(path):
    frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Cannot decode photo: {path}")
    return frame


def save_png(path, image):
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    data.tofile(str(path))


class SceneInput:
    def __init__(self, args, native, output=None):
        self.args, self.native, self.output = args, native, output
        self.stop = threading.Event()
        self.condition = threading.Condition()
        self.events = deque()
        self.request = None
        self.generation = 0
        self.index = 0
        self.status = "STARTING"
        self.error = None
        self.started = time.monotonic()
        self.metrics = dict(input="offline", recognized_frames=0, recognition_ms=[], scene_frames=0)
        self.photos = ([args.image] if args.image else
                       sorted(p for p in args.photos.iterdir()
                              if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg"))
                       if args.photos else [])
        if (args.image or args.photos) and not self.photos:
            raise ValueError("No reference photos found")
        if self.photos and args.start_photo:
            self.index = next((i for i, p in enumerate(self.photos) if p.name == args.start_photo), 0)
        self.thread = threading.Thread(target=self.run, name="scene-input", daemon=True)

    def start(self):
        if self.photos:
            self.select(self.index)
        self.thread.start()

    def select(self, index):
        if not self.photos:
            return
        with self.condition:
            self.index = index % len(self.photos)
            self.generation += 1
            self.request = (self.index, self.generation)
            self.condition.notify()

    def poll(self):
        with self.condition:
            result = list(self.events)
            self.events.clear()
        return result

    def publish(self, scene, frame, name, persistent, independent):
        elapsed = time.monotonic()-self.started
        event = (scene, frame, name, persistent, independent, time.monotonic())
        self.metrics["scene_frames"] += 1
        if self.log:
            self.log.write(json.dumps(dict(elapsed=elapsed, source=name, persistent=persistent,
                                          independent=independent, scene=scene.record()), allow_nan=False)+"\n")
            self.log.flush()
        with self.condition:
            # File processing waits for UI consumption; no complete scene is lost.
            self.events.append(event)
        self.status = "PHOTO READY" if persistent else "FILE REPLAY"

    def detect(self, frame, sequence):
        started = time.perf_counter()
        scene = self.native.detect(frame, sequence)
        self.metrics["recognition_ms"].append((time.perf_counter()-started)*1000)
        self.metrics["recognized_frames"] += 1
        return scene

    def run(self):
        self.log = None
        capture = None
        try:
            if self.output:
                self.log = (self.output / "scenes.jsonl").open("x", encoding="utf-8")
            if self.photos:
                sequence = 0
                while not self.stop.is_set():
                    with self.condition:
                        self.condition.wait_for(lambda: self.request is not None or self.stop.is_set(), timeout=.5)
                        if self.stop.is_set():
                            break
                        if self.request is None:
                            continue
                        index, generation = self.request
                        self.request = None
                    path = self.photos[index]
                    frame = read_photo(path)
                    sequence += 1
                    scene = self.detect(frame, sequence)
                    with self.condition:
                        if generation != self.generation:
                            continue
                    self.publish(scene, frame, path.name, True, True)
            elif self.args.replay:
                previous = -1.0
                anchor = time.monotonic()
                with self.args.replay.open(encoding="utf-8") as stream:
                    for line in stream:
                        record = json.loads(line)
                        elapsed = float(record["elapsed"])
                        if not np.isfinite(elapsed) or elapsed < previous or elapsed < 0:
                            raise ValueError("Replay elapsed times must be finite and monotonic")
                        previous = elapsed
                        delay = anchor+elapsed/self.args.replay_speed-time.monotonic()
                        if self.stop.wait(max(0, delay)):
                            break
                        scene = Scene.from_record(record["scene"])
                        self.publish(scene, None, record.get("source", "record"),
                                     bool(record.get("persistent", False)), bool(record.get("independent", False)))
                        self.wait_consumed()
                self.status = "REPLAY EOF"
            else:
                capture = cv2.VideoCapture(str(self.args.video))
                if not capture.isOpened():
                    raise ValueError("Cannot open offline video")
                sequence = 0
                while not self.stop.is_set():
                    started = time.monotonic()
                    ok, frame = capture.read()
                    if not ok:
                        if not sequence:
                            raise ValueError("Video contains no decodable frames")
                        break
                    sequence += 1
                    self.publish(self.detect(frame, sequence), frame, self.args.video.name, False, False)
                    self.wait_consumed()
                    self.stop.wait(max(0, 1/self.args.input_hz-(time.monotonic()-started)))
                self.status = "VIDEO EOF"
        except Exception as error:
            self.error = str(error)
            self.status = "INPUT ERROR"
        finally:
            if capture:
                capture.release()
            if self.log:
                self.log.close()

    def wait_consumed(self):
        while not self.stop.is_set():
            with self.condition:
                if not self.events:
                    return
            self.stop.wait(.01)

    def close(self):
        self.stop.set()
        with self.condition:
            self.condition.notify()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)


def run_native_game(args):
    """Existing file input + native C loop/canvas. No GameView/Python renderer."""
    started = time.monotonic()
    clock = lambda: int((time.monotonic()-started)*1000)
    shared = {"generation": 0}
    stamps = {}

    class StampedFileInput(SceneInput):
        def detect(self, frame, sequence):
            if len(stamps) > 64:
                stamps.pop(next(iter(stamps)))
            stamps[sequence] = (shared["generation"], clock())
            return super().detect(frame, sequence)

        def publish(self, scene, frame, name, persistent, independent):
            if args.replay:
                stamps[scene.frame] = (shared["generation"], scene.capture_ms)
            super().publish(scene, frame, name, persistent, independent)

    output = args.output
    if output:
        output.mkdir(parents=True, exist_ok=False)
    native = None
    core = None
    worker = None
    actions = deque()
    frames = 0
    accepted = deque(maxlen=512)
    try:
        core = NativeGame(args.assets)
        native = NativeVision(args.cc, recognition=not bool(args.replay))
        worker = StampedFileInput(args, native)
        core.command(f"input {clock()} 1")
        released = False
        def on_mouse(event, x, y, flags, param):
            nonlocal released
            # Feed the existing connect/release handshake from an observed
            # OpenCV button state; never invent a release for a held button.
            if not released and not flags & cv2.EVENT_FLAG_LBUTTON and event in (cv2.EVENT_MOUSEMOVE, cv2.EVENT_LBUTTONUP):
                actions.append(("left", 0))
                released = True
            if event == cv2.EVENT_MOUSEMOVE:
                if actions and actions[-1][0] == "pointer":
                    actions.pop()
                actions.append(("pointer", x, y))
            elif event in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_LBUTTONUP):
                actions.append(("pointer", x, y))
                actions.append(("left", int(event == cv2.EVENT_LBUTTONDOWN)))
        if not args.headless:
            cv2.namedWindow("Light Lab - Native C", cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback("Light Lab - Native C", on_mouse)
        worker.start()
        next_photo = 0
        last_level = 0
        while True:
            while actions:
                action = actions.popleft()
                core.command(" ".join(map(str, (action[0], clock(), *action[1:]))))
                shared["generation"] = int(core.state["generation"])
            level = int(core.state["level"])
            if worker.photos and level != last_level and level:
                reference = f"{74+level:03d}.png"
                index = next((i for i, p in enumerate(worker.photos) if p.name == reference), worker.index)
                worker.select(index)
                last_level = level
            for scene, _, name, _, _, _ in worker.poll():
                generation, captured = stamps.pop(scene.frame, (0, scene.capture_ms))
                core.command(core.scene_command(scene, clock(), generation, captured))
                accepted.append(dict(source=name, frame=scene.frame, captured_ms=captured,
                                     generation=generation, scene=scene.record(), state=dict(core.state)))
            core.command(f"tick {clock()}")
            shared["generation"] = int(core.state["generation"])
            canvas = core.image()
            if args.save_frames and output:
                save_png(output/f"native_{frames:05d}.png", canvas)
            frames += 1
            if not args.headless:
                cv2.imshow("Light Lab - Native C", canvas)
                key = cv2.waitKey(20) & 0xff
                if key in (27, ord("q")) or cv2.getWindowProperty("Light Lab - Native C", cv2.WND_PROP_VISIBLE) < 1:
                    break
                if worker.photos and key in (ord("a"), ord("d")):
                    worker.select(worker.index+(-1 if key == ord("a") else 1))
                    next_photo = clock()+1000/args.input_hz
            else:
                time.sleep(.01)
            # A photo observation is freshly re-detected, never re-stamped from
            # a retained result. Slow detection remains stale and disables start.
            if worker.photos and clock() >= next_photo and not worker.events and worker.request is None:
                worker.select(worker.index)
                next_photo = clock()+1000/args.input_hz
            if worker.error:
                raise RuntimeError(worker.error)
            if args.max_frames and frames >= args.max_frames:
                break
        if output:
            save_png(output/"native_final.png", canvas)
            (output/"events.replay").write_text("\n".join(core.transcript)+"\nquit\n", encoding="ascii")
            (output/"observations.json").write_text(json.dumps(list(accepted), indent=2)+"\n", encoding="utf-8")
            (output/"resources.txt").write_text("\n".join(core.command("resources"))+"\n", encoding="utf-8")
        return 0
    finally:
        if worker:
            worker.close()
        if native:
            native.close()
        if core:
            core.close()
        if not args.headless:
            cv2.destroyAllWindows()


class SerialSceneInput:
    """UART reader owns parsing; UI consumes a single replaceable complete scene.

    Construction does not open a port. Only start(), after explicit --serial,
    starts the reader. Tests inject a byte-stream factory without any hardware.
    """
    photos = ()

    def __init__(self, args, output=None, factory=None):
        self.args, self.output, self.factory = args, output, factory
        self.stop = threading.Event()
        self.condition = threading.Lock()
        self.latest = None
        self.connected = False
        self.error = self.last_error = None
        self.last_rx = self.last_scene = None
        self.times = deque(maxlen=128)
        self.performance_log = None
        self.receive_now = None
        self.parser, self.order = StreamParser(self.save_diagnostic), SceneOrder()
        self.metrics = dict(input="serial", recognized_frames=0, recognition_ms=[], scene_frames=0,
                            overwritten=0, connections=0, crc_or_format_errors=0, rejected_old=0,
                            performance_records=0)
        self.thread = threading.Thread(target=self.run, name="scene-uart", daemon=True)

    def start(self):
        self.thread.start()

    def poll(self):
        with self.condition:
            event, self.latest = self.latest, None
            return [event] if event is not None else []

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        self.receive_now = now
        # read() is capped at 4096; each parser invocation has bounded output.
        rejected_before = self.order.rejected
        for start in range(0, len(data), 4096):
            for scene in self.parser.feed(data[start:start+4096]):
                accepted, reset = self.order.accept(scene, now)
                if not accepted:
                    continue
                with self.condition:
                    if self.latest is not None:
                        self.metrics["overwritten"] += 1
                        reset |= self.latest[4]  # Session reset survives coalescing.
                    self.latest = (scene, None, self.args.serial, False, reset, now)
                    self.last_scene, self.last_rx = scene, now
                    self.times.append(now)
                    self.metrics["scene_frames"] += 1
            self.metrics["crc_or_format_errors"] = self.parser.rejected
        self.metrics["rejected_old"] += self.order.rejected-rejected_before

    def save_diagnostic(self, record):
        self.metrics["performance_records"] += 1
        if self.performance_log is not None:
            self.performance_log.write(json.dumps(dict(record, received_monotonic=self.receive_now,
                connection=self.metrics["connections"])) + "\n")
            self.performance_log.flush()

    def disconnected(self):
        with self.condition:
            self.connected = False
            self.parser.disconnect()
            # A disconnect immediately clears live geometry/rays on the UI.
            invalid = Scene(0, 0, 0, False, (1280, 720), ())
            self.latest = (invalid, None, self.args.serial, False, True, time.monotonic())
            self.times.clear()

    def telemetry(self, now, stale_after):
        with self.condition:
            age = None if self.last_rx is None else max(0, now-self.last_rx)
            status = ("DISCONNECTED" if not self.connected else
                      "STALE" if age is None or age >= stale_after or not self.last_scene.valid else "LIVE")
            # Keep low-rate measurements visible independently of freshness.
            recent = [t for t in self.times if now-t <= 10]
            span = recent[-1]-recent[0] if len(recent) > 1 else 0
            hz = (len(recent)-1)/span if span > 0 and self.connected else 0
            return dict(status=status, hz=hz, age=age,
                        frame=None if self.last_scene is None else self.last_scene.frame)

    @staticmethod
    def open_port(port, baud):
        import serial
        # Set inactive modem lines before opening; never intentionally reset a
        # board and never enumerate/probe other ports. Adapter behavior varies.
        stream = serial.Serial(port=None, baudrate=baud, timeout=.05,
                               xonxoff=False, rtscts=False, dsrdtr=False)
        stream.dtr = stream.rts = False
        stream.port = port
        stream.open()
        return stream

    def run(self):
        try:
            if self.output:
                self.performance_log = (self.output / "performance.jsonl").open("x", encoding="utf-8")
            if self.factory is None:
                try:
                    import serial  # noqa: F401; fail once, without reconnect spam
                except ImportError as error:
                    raise RuntimeError("Serial game requires: python -m pip install pyserial") from error
            while not self.stop.is_set():
                stream = None
                try:
                    stream = (self.factory or self.open_port)(self.args.serial, self.args.baud)
                    stream.reset_input_buffer()  # Discard OS backlog on each connection.
                    self.parser.disconnect()
                    self.order = SceneOrder()
                    with self.condition:
                        self.connected = True
                        self.last_scene = self.last_rx = None
                        self.times.clear()
                        self.metrics["connections"] += 1
                    while not self.stop.is_set():
                        data = stream.read(4096)
                        if data:
                            self.feed(data)
                except OSError as error:
                    self.last_error = str(error)
                finally:
                    if stream is not None:
                        stream.close()
                    self.disconnected()
                self.stop.wait(.5)
        except Exception as error:
            self.error = str(error)
            self.disconnected()
        finally:
            if self.performance_log is not None:
                self.performance_log.close()
                self.performance_log = None

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)


def run_game(args):
    cfg = load_game_config(args.game_config)
    if args.scene_timeout is not None:
        if args.scene_timeout <= cfg["dropout_seconds"]:
            raise ValueError("Scene timeout must exceed dropout_seconds")
        cfg["timeout_seconds"] = args.scene_timeout
    mapper = PlaneMapper.load(args.calibration) if args.calibration else PlaneMapper()
    serial_mode = bool(args.serial)
    native = NativeVision(args.cc, recognition=not serial_mode)
    controller = GameController(native, mapper, cfg)
    output = args.output
    try:
        if output:
            output.mkdir(parents=True, exist_ok=False)
            (output / "game_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            if mapper.calibration:
                mapper.save(output / "calibration.json")
        worker = SerialSceneInput(args, output) if serial_mode else SceneInput(args, native, output)
    except Exception:
        native.close()
        raise
    view = GameView()
    actions = deque()
    reference = None
    current_scene = None
    name = ""
    note = ""
    points = []
    calibrating = False
    reference_open = False
    accepted = 0
    renders = 0
    screenshot = 0
    records = deque(maxlen=256) if serial_mode else []
    serial_log = None
    started = time.monotonic()
    canvas = None

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            action = view.action_at(x, y)
            if action:
                actions.append(action)

    def on_reference(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and calibrating and len(points) < 4:
            points.append((x, y))
            if len(points) == 4:
                actions.append("Apply calibration")

    try:
        if serial_mode and output:
            serial_log = (output / "scenes.jsonl").open("x", encoding="utf-8")
        if not args.headless:
            cv2.namedWindow("Light Lab", cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback("Light Lab", on_click)
        worker.start()
        while True:
            now = time.monotonic()
            for scene, frame, event_name, persistent, independent, received in worker.poll():
                current_scene, reference, name = scene, frame, event_name
                controller.accept(scene, received, persistent, independent)
                if serial_log:
                    serial_log.write(json.dumps(dict(elapsed=received-started, source=name,
                        persistent=False, independent=independent, scene=scene.record()))+"\n")
                    serial_log.flush()
                accepted += 1
                records.append(dict(frame=scene.frame, source=name, objects=[o.type for o in controller.live],
                                    ray=controller.ray))
                if args.headless and worker.photos:
                    limit = min(args.max_frames or len(worker.photos), len(worker.photos))
                    if accepted < limit:
                        worker.select(worker.index+1)
            controller.tick(now)
            while actions:
                action = actions.popleft()
                if action == "Start/Pause":
                    controller.pause()
                elif action == "Lock":
                    note = "Scene locked" if controller.lock(now) else "Lock needs a fresh valid scene with exactly one SOURCE and no held objects"
                elif action == "Unlock":
                    controller.unlock(now)
                    note = "Unlocked; latest input adopted when running"
                elif action == "Reset":
                    controller.reset()
                    current_scene = None
                    points.clear()
                    calibrating = False
                    note = "Reset; waiting for a new scene"
                    if worker.photos:
                        worker.select(worker.index)
                elif action in ("Next", "Previous"):
                    if worker.photos:
                        points.clear()
                        calibrating = False
                        worker.select(worker.index+(1 if action == "Next" else -1))
                elif action == "Calibrate":
                    if reference is None:
                        note = "Calibration needs an unscaled reference photo; replay carries no image"
                    elif args.plane_size is None:
                        note = "Calibration needs --plane-size WIDTH HEIGHT in measured mm; preview continues"
                    elif args.headless:
                        note = "Use --calibration FILE for headless mapping"
                    else:
                        points.clear()
                        calibrating = True
                        reference_open = True
                        cv2.namedWindow("Calibration reference", cv2.WINDOW_AUTOSIZE)
                        cv2.setMouseCallback("Calibration reference", on_reference)
                        note = "Click known plane corners TL -> TR -> BR -> BL in the unscaled reference"
                elif action == "Apply calibration":
                    calibration = dict(schema="plane-v1", unit="mm", image_size=[1280, 720],
                                       image_points=points, plane_size=args.plane_size)
                    try:
                        new_mapper = PlaneMapper(calibration)
                        target = args.calibration_out or Path("pc_vision/output/calibration.json")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("x", encoding="utf-8") as stream:
                            json.dump(calibration, stream, indent=2)
                        controller.mapper = new_mapper
                        controller.reset()
                        if current_scene:
                            controller.accept(current_scene, now, bool(worker.photos), True)
                        calibrating = False
                        note = f"Calibration saved: {target} / model dimensions now in mm"
                    except (ValueError, OSError) as error:
                        points.clear()
                        note = str(error)+"; existing calibration files are preserved"
                elif action == "Snapshot":
                    if output and canvas is not None:
                        screenshot += 1
                        save_png(output / f"game_snapshot_{screenshot:04d}.png", canvas)
                        note = f"Snapshot saved ({screenshot})"
                    else:
                        note = "Snapshot requires --output NEW_DIRECTORY"
            telemetry = worker.telemetry(now, cfg["dropout_seconds"]) if serial_mode else None
            canvas = view.render(controller, telemetry["status"] if serial_mode else worker.status,
                                 now, name, note, telemetry)
            renders += 1
            if args.save_frames and output and accepted and len(records) > 0:
                record = records[-1]
                path = output / f"game_{accepted:06d}.png"
                if not record.get("saved"):
                    save_png(path, canvas)
                    record["saved"] = True
            if args.headless:
                if ((args.max_frames and accepted >= args.max_frames) or
                        (worker.photos and accepted >= min(args.max_frames or len(worker.photos), len(worker.photos))) or
                        (not worker.photos and not worker.thread.is_alive())):
                    break
                worker.stop.wait(.01)
            else:
                cv2.imshow("Light Lab", canvas)
                if reference_open and reference is not None:
                    preview = reference.copy()
                    for i, p in enumerate(points):
                        cv2.circle(preview, p, 6, (0, 255, 255), 2)
                        GameView.text(preview, str(i+1), (p[0]+8, p[1]), .6)
                    GameView.text(preview, "Unscaled pixels. TL -> TR -> BR -> BL. Esc cancels calibration.", (10, 24), .5)
                    cv2.imshow("Calibration reference", preview)
                key = cv2.waitKeyEx(20)
                if key in (ord("q"), ord("Q")) or cv2.getWindowProperty("Light Lab", cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key == 27:
                    if calibrating:
                        calibrating = False
                        points.clear()
                        note = "Calibration cancelled"
                    else:
                        break
                bindings = {32: "Start/Pause", ord("l"): "Lock", ord("u"): "Unlock",
                            ord("r"): "Reset", ord("c"): "Calibrate", ord("s"): "Snapshot",
                            ord("n"): "Next", ord("p"): "Previous",
                            2555904: "Next", 2424832: "Previous", 65363: "Next", 65361: "Previous"}
                if key in bindings:
                    actions.append(bindings[key])
                if args.max_frames and accepted >= args.max_frames:
                    break
            if worker.error:
                raise RuntimeError(worker.error)
        if worker.error:
            raise RuntimeError(worker.error)
    finally:
        worker.close()
        if serial_log:
            serial_log.close()
        native.close()
        if not args.headless:
            cv2.destroyAllWindows()
        elapsed = time.monotonic()-started
        metrics = dict(worker.metrics, accepted_scenes=accepted, render_iterations=renders,
                       elapsed_seconds=elapsed, native_executable=str(native.path),
                       hardware_connected=bool(worker.metrics.get("connections")), calibration=controller.mapper.calibration,
                       error=worker.error)
        durations = metrics.pop("recognition_ms")
        metrics["recognition_ms_mean"] = float(np.mean(durations)) if durations else None
        metrics["recognition_ms_max"] = max(durations, default=None)
        metrics["offline_scenes_per_second"] = accepted/elapsed if elapsed else 0
        if serial_mode:
            metrics["adopted_scenes_per_second"] = metrics.pop("offline_scenes_per_second")
        if output:
            (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            (output / "game_results.json").write_text(json.dumps(list(records), indent=2), encoding="utf-8")
            if canvas is not None:
                save_png(output / "game.png", canvas)
        print(json.dumps(metrics, ensure_ascii=False))

