"""Camera-image overlay. Geometry, complete rays and game state come from C."""
import json
from dataclasses import dataclass
from pathlib import Path
import threading
import time
from types import MappingProxyType

import cv2
import numpy as np

from .native import NativeRealScene
from .scene_protocol import TYPES

COLORS = ((255, 255, 255), (255, 210, 30), (30, 160, 255),
          (70, 240, 70), (0, 240, 255), (80, 80, 255))
STATES = ("SELECT", "PREPARING", "RUNNING", "CLEARED", "TIMEOUT")


def render_overlay(frame, snapshot, tags, config, *, label="PHOTO", stale=False,
                   observations=None, name=""):
    """Only draw supplied coordinates. No tracing, template completion or hits."""
    if frame.shape != (720, 1280, 3):
        raise ValueError("Overlay requires unscaled 1280x720 BGR")
    out = frame.copy()
    factor = .35 if stale else 1

    def point(value):
        return tuple(np.rint(value).astype(int))

    def line(a, b, color, width=2):
        cv2.line(out, point(a), point(b), tuple(int(v*factor) for v in color), width, cv2.LINE_AA)

    for row in snapshot.get("objects", []):
        kind = int(row[0])
        center, axis = np.array(row[1:3]), np.array(row[3:5])
        length, width = row[5:7]
        normal = np.array([-axis[1], axis[0]])
        color = COLORS[kind]
        if kind in (1, 2, 5):
            for side in (-1, 1):
                shift = side*normal*width/2
                line(center-axis*length/2+shift, center+axis*length/2+shift, color)
            if kind == 5:
                for side in (-1, 1):
                    tip = center+side*axis*length/2
                    line(tip-normal*width/2, tip+normal*width/2, color)
        elif kind == 0:
            line(center-axis*length/2, center+axis*length/2, color, 3)
        elif kind == 3:
            cv2.circle(out, point(center), round(length/2), tuple(int(v*factor) for v in color), 2, cv2.LINE_AA)
        else:
            cv2.circle(out, point(center), 7, tuple(int(v*factor) for v in color), 2, cv2.LINE_AA)
            line(center, center+axis*24, color)
        cv2.drawMarker(out, point(center), tuple(int(v*factor) for v in color), cv2.MARKER_CROSS, 10, 1)
    # Each solver segment is independent. Never connect the teleport gap or
    # continue beyond a solver endpoint, even if an effect would look smoother.
    for segment in snapshot.get("segments", []):
        line(segment[:2], segment[2:], (20, 90, 90), 6)
        line(segment[:2], segment[2:], (40, 255, 255), 2)

    # The configured emitter remains visible when observations are incomplete;
    # this icon is level data, not a detected SOURCE or a fabricated scene.
    level = next(l for l in config["board_game"]["levels"] if l["id"] == snapshot["level"])
    origin = np.asarray(level["emitter"]["point"])
    direction = np.asarray(level["emitter"]["direction"])
    cv2.circle(out, point(origin), 8, (0, 230, 255), 2, cv2.LINE_AA)
    cv2.arrowedLine(out, point(origin), point(origin+direction*26), (0, 230, 255), 2, cv2.LINE_AA, tipLength=.3)

    tag_counts = [sum(t["id"]//10 == n for t in tags) for n in (1, 2)]
    for tag in tags:
        corners = np.rint(tag["corners"]).astype(np.int32)
        color = (0, 220, 255) if tag_counts[tag["id"]//10-1] < 2 else (100, 255, 100)
        cv2.polylines(out, [corners], True, color, 1, cv2.LINE_AA)
        for corner in corners:
            cv2.circle(out, tuple(corner), 2, color, -1, cv2.LINE_AA)
        cv2.putText(out, str(tag["id"]), tuple(corners[0]+[2, -4]), cv2.FONT_HERSHEY_SIMPLEX, .4, color, 1, cv2.LINE_AA)
    if observations is not None and not snapshot.get("valid"):
        for obj in observations.objects:
            center = np.asarray(obj.center)
            axis = np.asarray(obj.axis)
            cv2.drawMarker(out, point(center), COLORS[TYPES.index(obj.type)], cv2.MARKER_CROSS, 12, 1)
            cv2.putText(out, "RAW "+obj.type, point(center+8), cv2.FONT_HERSHEY_SIMPLEX, .4,
                        COLORS[TYPES.index(obj.type)], 1, cv2.LINE_AA)
            line(center, center+axis*20, COLORS[TYPES.index(obj.type)], 1)

    cv2.rectangle(out, (0, 0), (1279, 53), (20, 24, 28), -1)
    status = "STALE / LAST OBSERVATION" if stale else label
    cv2.putText(out, f"{status} | UNCALIBRATED CAMERA PIXELS | LEVEL {snapshot['level']} | {name}",
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, .52, (200, 230, 255), 1, cv2.LINE_AA)
    valid = bool(snapshot.get("valid")) and not stale
    text = f"{STATES[snapshot['state']]}  {'COMPLETE' if valid else 'NEED RELIABLE OBJECTS'}  "
    text += f"TAGS A:{tag_counts[0]}/3 B:{tag_counts[1]}/3  SEQ {snapshot.get('sequence', 0)}"
    if 1 in tag_counts:
        text += "  SINGLE TAG: RESTRICTED"
    if snapshot["state"] >= 2:
        text += f"  {snapshot['remaining_ms']/1000:.1f}s  STARS {snapshot['stars']}"
    cv2.putText(out, text, (10, 43), cv2.FONT_HERSHEY_SIMPLEX, .48, (130, 220, 150), 1, cv2.LINE_AA)
    cv2.rectangle(out, (0, 680), (1279, 719), (20, 24, 28), -1)
    for i in range(3):
        cv2.rectangle(out, (10+i*100, 685), (100+i*100, 714), (80, 105, 110), 1)
        cv2.putText(out, f"LEVEL {i+1}", (19+i*100, 705), cv2.FONT_HERSHEY_SIMPLEX, .48, (230, 230, 230), 1)
    cv2.putText(out, "SPACE: START (stream) | LEFT/RIGHT: PHOTO | S: SAVE | Q: EXIT", (330, 705),
                cv2.FONT_HERSHEY_SIMPLEX, .47, (200, 210, 220), 1, cv2.LINE_AA)
    return out


class OverlayRetention:
    """Display retention only; the C session always sees the actual new frame."""
    def __init__(self, config):
        self.config = config
        self.clear()

    def clear(self):
        self.last = None
        self.captured_ms = 0
        self.explicit_invalid = False

    def update(self, snapshot):
        if snapshot.get("valid"):
            self.last = snapshot
            self.captured_ms = snapshot["captured_ms"]
            self.explicit_invalid = False
        else:
            self.explicit_invalid = True

    def display(self, current, now_ms, photo=False):
        if photo:
            return current, False
        if self.last is None:
            return current, False
        age = now_ms-self.captured_ms
        limit = self.config["dropout_seconds"] if self.explicit_invalid else self.config["timeout_seconds"]
        if age > limit*1000:
            return dict(current, valid=0, objects=[], segments=[]), False
        stale = self.explicit_invalid or age > self.config["stale_seconds"]*1000
        # Only geometry is retained. Timers, level state and results continue
        # to come from the newest C tick, including while capture.read blocks.
        shown = dict(current, objects=self.last["objects"], segments=self.last["segments"],
                     captured_ms=self.captured_ms)
        if "sequence" in self.last:
            shown["sequence"] = self.last["sequence"]
        return shown, stale


def _freeze(value):
    """Publish a complete value, never a mutable native-response dictionary."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class StreamFrame:
    epoch: int
    generation: int
    sequence: int
    captured_ms: int
    pixels: np.ndarray


@dataclass(frozen=True)
class OverlayUpdate:
    epoch: int
    snapshot: object
    frame: object
    tags: tuple
    observations: object
    sequence: int
    captured_ms: int
    processed: int
    observed: bool


class OverlayStreamWorker:
    """Bounded latest input/output, following SerialSceneInput's mailbox model.

    One thread alone owns the native pipe, pose commit and C session. Another
    thread owns this PC/file VideoCapture; a blocked read cannot stop C ticks or
    UI events. The frame stamp is frozen before read dispatch, conservatively
    including any blocking read time. It is not an exposure timestamp.
    """
    def __init__(self, native_factory, capture_factory, clock, level=1,
                 algorithm="B", interval=0, on_observation=None):
        self.native_factory = native_factory
        self.capture_factory = capture_factory
        self.clock = clock
        self.level = level
        self.algorithm = algorithm
        self.interval = interval
        self.on_observation = on_observation
        self.condition = threading.Condition()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.latest_input = self.latest_output = None
        self.pending_select = self.pending_start = None
        self.requested_epoch = self.owner_epoch = self.generation = 0
        self.source_done = self.finished = False
        self.error = None
        self.processed = self.overwritten = self.rejected_old = 0
        self.native = None
        self.last_capture_ms = 0
        self.capture_thread = None
        self.thread = threading.Thread(target=self._run, name="overlay-native-owner", daemon=True)

    def start(self):
        self.thread.start()

    def select(self, level):
        with self.condition:
            self.requested_epoch += 1
            self.pending_select = (level, self.requested_epoch)
            self.pending_start = None
            self.latest_input = self.latest_output = None
            self.condition.notify_all()
            return self.requested_epoch

    def request_start(self):
        with self.condition:
            self.pending_start = self.requested_epoch
            self.condition.notify_all()

    def poll(self):
        with self.condition:
            update, self.latest_output = self.latest_output, None
            if update is not None and update.epoch == self.requested_epoch:
                return update
            return None

    def _publish(self, snapshot, frame, tags, observations, sequence, observed):
        update = OverlayUpdate(self.owner_epoch, _freeze(snapshot), frame,
                               _freeze(tags), observations, sequence,
                               self.last_capture_ms, self.processed, observed)
        with self.condition:
            if self.owner_epoch == self.requested_epoch and not self.stop.is_set():
                self.latest_output = update
                self.condition.notify_all()

    def _capture(self):
        capture = None
        sequence = 0
        try:
            capture = self.capture_factory()
            if not capture.isOpened():
                raise ValueError("Cannot open requested video/camera")
            while not self.stop.is_set():
                with self.condition:
                    epoch, generation = self.owner_epoch, self.generation
                captured_ms = self.clock()
                sequence += 1
                started = time.monotonic()
                ok, pixels = capture.read()
                if self.stop.is_set() or not ok:
                    break
                if pixels.shape != (720, 1280, 3):
                    raise ValueError(f"Expected unscaled 1280x720 BGR, got {pixels.shape}")
                # Backends may reuse their read buffer. Publish our own read-only
                # pixels and never let the next read change the displayed frame.
                pixels = np.array(pixels, dtype=np.uint8, copy=True, order="C")
                pixels.setflags(write=False)
                packet = StreamFrame(epoch, generation, sequence, captured_ms, pixels)
                with self.condition:
                    if self.latest_input is not None:
                        self.overwritten += 1
                    self.latest_input = packet
                    self.condition.notify_all()
                self.stop.wait(max(0, self.interval-(time.monotonic()-started)))
        except Exception as error:
            if not self.stop.is_set():
                with self.condition:
                    self.error = str(error)
        finally:
            # Only this thread calls capture.release(), including after a slow
            # backend finally returns. Do not race release against read().
            if capture is not None:
                capture.release()
            with self.condition:
                self.source_done = True
                self.condition.notify_all()

    def _run(self):
        native = None
        frame = observations = None
        tags = ()
        sequence = 0
        try:
            native = self.native_factory()
            with self.condition:
                self.native = native
            snapshot = native.select(self.level, self.clock())
            with self.condition:
                self.generation = snapshot["generation"]
            self._publish(snapshot, frame, tags, observations, sequence, False)
            self.ready.set()
            self.capture_thread = threading.Thread(target=self._capture, name="overlay-pc-capture", daemon=True)
            self.capture_thread.start()
            while not self.stop.is_set():
                with self.condition:
                    selected, self.pending_select = self.pending_select, None
                    start, self.pending_start = self.pending_start, None
                    packet, self.latest_input = self.latest_input, None
                if selected is not None:
                    self.level, epoch = selected
                    snapshot = native.select(self.level, self.clock())
                    with self.condition:
                        self.owner_epoch = epoch
                        self.generation = snapshot["generation"]
                        self.latest_input = None
                    tags, observations, sequence = (), None, 0
                    self._publish(snapshot, frame, tags, observations, sequence, False)
                if start is not None and start == self.owner_epoch:
                    snapshot = native.start(self.clock())
                    self._publish(snapshot, frame, tags, observations, sequence, False)
                with self.condition:
                    current_epoch = self.requested_epoch
                if packet is not None:
                    if (packet.epoch != self.owner_epoch or packet.epoch != current_epoch or
                            packet.generation != self.generation):
                        self.rejected_old += 1
                    else:
                        observed = native.observe(packet.pixels, packet.generation,
                            packet.sequence, packet.captured_ms, self.algorithm,
                            now_ms=self.clock())
                        with self.condition:
                            still_current = packet.epoch == self.requested_epoch
                        if still_current and not self.stop.is_set():
                            snapshot = native.commit(self.clock())
                            new_tags = native.portal_tags()
                            frame, observations, tags = packet.pixels, observed, new_tags
                            sequence = packet.sequence
                            self.last_capture_ms = packet.captured_ms
                            self.processed += 1
                            if self.on_observation:
                                self.on_observation(packet, observed, snapshot)
                            self._publish(snapshot, frame, tags, observations, sequence, True)
                        else:
                            # A queued select clears C's pending frame before
                            # any commit. An old UI epoch cannot finish a win.
                            self.rejected_old += 1
                snapshot = native.tick(self.clock())
                self._publish(snapshot, frame, tags, observations, sequence, False)
                with self.condition:
                    self.finished = self.source_done and self.latest_input is None
                    self.condition.wait_for(lambda: self.stop.is_set() or
                        self.pending_select is not None or self.pending_start is not None or
                        self.latest_input is not None, timeout=.02)
        except Exception as error:
            if not self.stop.is_set():
                with self.condition:
                    self.error = str(error)
        finally:
            self.ready.set()
            if native is not None:
                native.close()
            with self.condition:
                self.finished = True
                self.condition.notify_all()

    def close(self):
        self.stop.set()
        with self.condition:
            self.condition.notify_all()
        if self.thread.ident is not None:
            self.thread.join(timeout=.5)
        if self.thread.is_alive():
            # Cancellation is an OS process operation, not another C pipe user.
            # A detector stuck in native code must not prevent the UI exiting.
            with self.condition:
                native = self.native
            detector = getattr(native, "detector", None)
            process = getattr(detector, "process", None)
            if process is not None and process.poll() is None:
                process.terminate()
                self.thread.join(timeout=.5)
        if self.capture_thread is not None:
            self.capture_thread.join(timeout=.1)


def run_stream_scene(args):
    from .app import write_image
    config = json.loads(Path(__file__).with_name("game_config.json").read_text(encoding="utf-8"))
    output = args.output
    log = None
    worker = None
    if output:
        output.mkdir(parents=True, exist_ok=False)
        log = (output / "scenes.jsonl").open("w", encoding="utf-8")
    origin = time.monotonic()
    clock = lambda: int((time.monotonic()-origin)*1000)
    name = Path(args.video).name if args.video else f"CAMERA {args.camera}"
    window = "Real scene - C authoritative overlay"
    retention = OverlayRetention(config)
    latest = None
    last_adopted = None
    frames = 0
    rendered = np.zeros((720, 1280, 3), np.uint8)
    try:
        if not np.isfinite(args.input_hz) or args.input_hz <= 0:
            raise ValueError("input-hz must be finite and positive")

        def record(packet, observed, snapshot):
            if log:
                log.write(json.dumps(dict(observed.record(), source=name,
                    generation=packet.generation, original_captured_ms=packet.captured_ms,
                    input_kind="video" if args.video else "camera", native=snapshot), ensure_ascii=False)+"\n")
                log.flush()

        worker = OverlayStreamWorker(lambda: NativeRealScene(args.cc),
            lambda: cv2.VideoCapture(str(args.video) if args.video else args.camera),
            clock, args.level, args.stability,
            interval=1/args.input_hz if args.video else 0, on_observation=record)
        if not args.headless:
            cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

            def click(event, x, y, flags, param):
                if event == cv2.EVENT_LBUTTONDOWN and 685 <= y <= 714:
                    for i in range(3):
                        if 10+i*100 <= x <= 100+i*100:
                            worker.select(i+1)
                            retention.clear()
            cv2.setMouseCallback(window, click)
        worker.start()
        while True:
            update = worker.poll()
            if update is not None:
                latest = update
                identity = (update.epoch, update.sequence)
                if update.frame is not None and identity != last_adopted:
                    retention.update(update.snapshot)
                    last_adopted = identity
                    frames += 1
                    new_frame = True
                else:
                    new_frame = False
            else:
                new_frame = False
            if latest is not None and latest.epoch == worker.requested_epoch:
                image = latest.frame if latest.frame is not None else np.zeros((720, 1280, 3), np.uint8)
                shown, stale = retention.display(latest.snapshot, clock())
                diagnostic_fresh = clock()-latest.captured_ms <= config["stale_seconds"]*1000
                rendered = render_overlay(image, shown, latest.tags if diagnostic_fresh else (), config,
                    label=("FILE VIDEO" if args.video else "CAMERA")+" / READ DISPATCH CLOCK",
                    stale=stale, observations=latest.observations if diagnostic_fresh else None, name=name)
            else:
                # A select request invalidates the old presentation immediately,
                # even while its C detection call is still finishing.
                rendered = (latest.frame.copy() if latest is not None and latest.frame is not None
                            else np.zeros((720, 1280, 3), np.uint8))
                cv2.putText(rendered, "WAITING FOR C SESSION / LEVEL SELECTION", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (200, 230, 255), 1, cv2.LINE_AA)
            if new_frame and args.save_frames:
                write_image(output / f"frame_{frames:06d}.png", rendered)
            if worker.error:
                raise RuntimeError(worker.error)
            if args.max_frames and worker.processed >= args.max_frames:
                break
            if worker.finished and worker.source_done and update is None:
                break
            if not args.headless:
                cv2.imshow(window, rendered)
                key = cv2.waitKey(20) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break
                if key in (ord("1"), ord("2"), ord("3")):
                    worker.select(key-ord("0"))
                    retention.clear()
                elif key == 32:
                    worker.request_start()
                elif key in (ord("s"), ord("S")) and output:
                    write_image(output / f"snapshot_{clock()}.png", rendered)
            else:
                worker.stop.wait(.01)
        print(f"Real-scene overlay: {worker.processed} processed stream frames; uncalibrated preview; no board validation")
        return 0
    finally:
        if worker:
            worker.close()
        if log:
            log.close()
        if not args.headless:
            cv2.destroyAllWindows()


def run_real_scene(args):
    if args.image is None and args.photos is None:
        return run_stream_scene(args)
    from .app import read_image, write_image
    config = json.loads(Path(__file__).with_name("game_config.json").read_text(encoding="utf-8"))
    output = args.output
    log = None
    if output:
        output.mkdir(parents=True, exist_ok=False)
        log = (output / "scenes.jsonl").open("w", encoding="utf-8")
    native = None
    capture = None
    origin_clock = time.monotonic()
    now = lambda: int((time.monotonic()-origin_clock)*1000)
    photos = []
    index = sequence = processed = 0
    photo = args.image is not None or args.photos is not None
    window = "Real scene - C authoritative overlay"
    level_request = None
    image = rendered = observations = None
    tags = []
    retention = OverlayRetention(config)
    try:
        native = NativeRealScene(args.cc)
        snapshot = native.select(args.level, now())
        if args.image:
            photos = [args.image]
        elif args.photos:
            photos = sorted(p for p in args.photos.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"))
            if not photos:
                raise ValueError("Photo directory is empty")
            index = next((i for i, p in enumerate(photos) if p.name == args.start_photo), 0)
            if args.headless:
                index = 0
        else:
            capture = cv2.VideoCapture(str(args.video) if args.video else args.camera)
            if not capture.isOpened():
                raise ValueError("Cannot open requested video/camera")
        dirty = True
        if not args.headless:
            cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

            def click(event, x, y, flags, param):
                nonlocal level_request
                if event == cv2.EVENT_LBUTTONDOWN and 685 <= y <= 714:
                    for i in range(3):
                        if 10+i*100 <= x <= 100+i*100:
                            level_request = i+1
            cv2.setMouseCallback(window, click)

        while True:
            if level_request is not None:
                snapshot = native.select(level_request, now())
                level_request = None
                retention.clear()
                dirty = True
            new_frame = not photo or dirty
            if new_frame:
                if photo:
                    image = read_image(photos[index])
                    name = photos[index].name
                else:
                    ok, image = capture.read()
                    if not ok:
                        break
                    name = Path(args.video).name if args.video else f"CAMERA {args.camera}"
                if image.shape != (720, 1280, 3):
                    raise ValueError(f"{name}: expected unscaled 1280x720 BGR, got {image.shape}")
                sequence += 1
                captured_ms = now()  # processing dispatch, never exposure time
                observations = native.observe(image, snapshot["generation"], sequence,
                                              captured_ms, None if photo else args.stability)
                snapshot = native.commit(now())
                tags = native.portal_tags()
                retention.update(snapshot)
                dirty = False
                processed += 1
                if log:
                    log.write(json.dumps(dict(observations.record(), source=name,
                        generation=snapshot["generation"], original_captured_ms=captured_ms,
                        input_kind="photo" if photo else "stream", native=snapshot), ensure_ascii=False)+"\n")
                    log.flush()
            elif not photo:
                snapshot = native.tick(now())
            shown, stale = retention.display(snapshot, now(), photo)
            rendered = render_overlay(image, shown, tags, config,
                label="PHOTO / NO SCORING" if photo else "STREAM / DISPATCH CLOCK",
                stale=stale, observations=observations, name=name)
            if new_frame and args.save_frames:
                write_image(output / f"frame_{processed:06d}.png", rendered)
            if args.headless:
                if args.max_frames and processed >= args.max_frames:
                    break
                if photo:
                    index += 1
                    if index >= len(photos):
                        break
                    dirty = True
                continue
            cv2.imshow(window, rendered)
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if key in (ord("1"), ord("2"), ord("3")):
                level_request = key-ord("0")
            elif key == 32 and not photo:
                snapshot = native.start(now())
            elif key in (81, 83, ord("n"), ord("p")) and photo:
                index = (index+(1 if key in (83, ord("n")) else -1)) % len(photos)
                retention.clear()
                dirty = True
            elif key in (ord("s"), ord("S")) and output:
                write_image(output / f"snapshot_{sequence:06d}_{now()}.png", rendered)
            if args.max_frames and processed >= args.max_frames:
                break
        print(f"Real-scene overlay: {processed} file/stream frames; uncalibrated preview; no board validation")
        return 0
    finally:
        if native:
            native.close()
        if capture:
            capture.release()
        if log:
            log.close()
        if not args.headless:
            cv2.destroyAllWindows()
