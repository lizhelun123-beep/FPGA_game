"""Version 1 scene envelope, also used for deterministic offline recordings."""
from dataclasses import dataclass, asdict
import struct
import zlib

TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
HEADER = struct.Struct("<BBBBIIIHH")
OBJECT = struct.Struct("<BBBBhhhhHHhhhh")
PREFIX = b"@SCN1:"
SUFFIX = b":END\r\n"
MAX_LINE = 828


@dataclass(frozen=True)
class Observation:
    type: str
    center: tuple
    axis: tuple
    axis_valid: bool
    reference_size: tuple
    confidence: int
    source_tip: tuple
    source_direction: tuple
    direction_valid: bool


@dataclass(frozen=True)
class Scene:
    frame: int
    tx_sequence: int
    capture_ms: int
    valid: bool
    image_size: tuple
    objects: tuple

    def record(self):
        return {"schema": "scene-v1", **asdict(self)}

    @classmethod
    def from_record(cls, record):
        if record.get("schema") != "scene-v1":
            raise ValueError("Replay requires scene-v1 records, not legacy debug detections")
        # Round-trip through the protocol validator rather than trusting JSON.
        scene = cls(record["frame"], record["tx_sequence"], record["capture_ms"],
                    record["valid"], tuple(record["image_size"]),
                    tuple(Observation(**o) for o in record["objects"]))
        return decode(encode(scene))


def decode(line):
    if not line.startswith(PREFIX) or not line.endswith(SUFFIX) or len(line) > MAX_LINE:
        raise ValueError("Invalid scene envelope")
    text = line[len(PREFIX):-len(SUFFIX)]
    if len(text) % 2 or any(c not in b"0123456789abcdefABCDEF" for c in text):
        raise ValueError("Invalid hex payload")
    data = bytes.fromhex(text.decode("ascii"))
    if len(data) < HEADER.size + 4:
        raise ValueError("Short scene header")
    if zlib.crc32(data[:-4]) != struct.unpack_from("<I", data, len(data)-4)[0]:
        raise ValueError("Scene CRC mismatch")
    version, flags, count, reserved, frame, tx, ms, w, h = HEADER.unpack_from(data)
    if (version != 1 or flags not in (0, 1) or reserved or count > 16 or
            not 2 <= w <= 2048 or not 2 <= h <= 2048 or
            len(data) != HEADER.size + OBJECT.size*count + 4 or (not flags and count)):
        raise ValueError("Invalid scene header/length")
    objects = []
    for i in range(count):
        kind, oflags, conf, pad, x, y, ax, ay, length, width, txp, typ, dx, dy = OBJECT.unpack_from(data, HEADER.size+i*OBJECT.size)
        if (kind >= len(TYPES) or oflags & ~3 or pad or conf > 100 or
                max(abs(ax), abs(ay), abs(dx), abs(dy)) > 10000 or
                not 0 <= x/16 <= w-1 or not 0 <= y/16 <= h-1 or
                (oflags & 1 and not .8 <= (ax*ax+ay*ay)**.5/10000 <= 1.2) or
                (oflags & 2 and (kind != 4 or not .8 <= (dx*dx+dy*dy)**.5/10000 <= 1.2))):
            raise ValueError("Invalid scene object")
        objects.append(Observation(TYPES[kind], (x/16, y/16), (ax/10000, ay/10000),
            bool(oflags & 1), (length/16, width/16), conf, (txp/16, typ/16),
            (dx/10000, dy/10000), bool(oflags & 2)))
    return Scene(frame, tx, ms, bool(flags), (w, h), tuple(objects))


def encode(scene):
    data = bytearray(HEADER.pack(1, int(scene.valid), len(scene.objects), 0,
        scene.frame, scene.tx_sequence, scene.capture_ms, *scene.image_size))
    for o in scene.objects:
        data.extend(OBJECT.pack(TYPES.index(o.type), int(o.axis_valid) | 2*int(o.direction_valid),
            o.confidence, 0, *(round(v*16) for v in o.center),
            *(round(v*10000) for v in o.axis), *(round(v*16) for v in o.reference_size),
            *(round(v*16) for v in o.source_tip), *(round(v*10000) for v in o.source_direction)))
    data.extend(struct.pack("<I", zlib.crc32(data)))
    return PREFIX + data.hex().upper().encode("ascii") + SUFFIX


PERF_STAGES = (
    "capture_wait", "invalidate", "pixel_check", "copy", "detect_six", "ray",
    "overlay", "flush", "display_wait", "publish", "encode", "uart_service",
    "poll_gap", "queue_age", "fifo_span", "wire_idle_upper", "process",
    "loop", "recovery", "retry", "sleep", "report", "capture_fail",
    "process_fail", "hold")


class StreamParser:
    """Bounded buffering; resync at the next prefix after damage or logs."""
    def __init__(self, on_diagnostic=None):
        self.buffer = bytearray()
        self.accepted = self.rejected = 0
        self.on_diagnostic = on_diagnostic
        self.diagnostic_tail = bytearray()
        self.diagnostic_discard = False

    def disconnect(self):
        self.buffer.clear()  # A partial frame never survives a new session.
        self.diagnostic_tail.clear()
        self.diagnostic_discard = False

    def _diagnostics(self, chunk):
        # A second bounded line recognizer in the SAME receiver, never another
        # port or backlog. Only exact 61-byte firmware rows reach the callback.
        for part in chunk.split(b"\n")[:-1]:
            self._diagnostic_part(part + b"\n")
        self._diagnostic_part(chunk.rsplit(b"\n", 1)[-1])

    def _diagnostic_part(self, part):
        complete = part.endswith(b"\n")
        if len(self.diagnostic_tail) + len(part) > 64:
            self.diagnostic_tail.clear()
            self.diagnostic_discard = True
        if not self.diagnostic_discard:
            self.diagnostic_tail.extend(part)
        if not complete:
            return
        row = bytes(self.diagnostic_tail)
        self.diagnostic_tail.clear()
        discard, self.diagnostic_discard = self.diagnostic_discard, False
        if discard or len(row) != 61 or not row.startswith(b"@PF1 ") or row[-2:] != b"\r\n":
            return
        fields = row[5:-2].split(b" ")
        if ([len(f) for f in fields] != [8, 2, 8, 16, 16] or
                any(c not in b"0123456789abcdef" for f in fields for c in f)):
            return
        report, stage, n, total, maximum = (int(f, 16) for f in fields)
        if stage >= len(PERF_STAGES) and stage not in range(0xf0, 0xf6):
            return
        record = dict(schema="perf-v1", report=report, stage_id=stage, n=n,
                      total=total, maximum=maximum)
        if stage < len(PERF_STAGES):
            record.update(stage=PERF_STAGES[stage], unit="us")
        else:
            record.update(stage=f"meta_{stage:02x}", unit="see firmware README")
        self.on_diagnostic(record)

    def feed(self, chunk):
        scenes = []
        # Bound even a huge chunk without dropping valid concatenated packets.
        for start in range(0, len(chunk), 512):
            if self.on_diagnostic is not None:
                self._diagnostics(chunk[start:start+512])
            self.buffer.extend(chunk[start:start+512])
            while True:
                begin = self.buffer.find(PREFIX)
                if begin < 0:
                    self.buffer[:] = self.buffer[-(len(PREFIX)-1):]
                    break
                del self.buffer[:begin]
                end = self.buffer.find(SUFFIX)
                next_begin = self.buffer.find(PREFIX, len(PREFIX))
                if next_begin >= 0 and (end < 0 or next_begin < end):
                    self.rejected += 1
                    del self.buffer[:next_begin]
                    continue
                if end < 0:
                    if len(self.buffer) > MAX_LINE:
                        self.rejected += 1
                        del self.buffer[:len(PREFIX)]
                        continue
                    break
                length = end + len(SUFFIX)
                line = bytes(self.buffer[:length])
                del self.buffer[:length]
                try:
                    scenes.append(decode(line))
                    self.accepted += 1
                except ValueError:
                    self.rejected += 1
        return scenes


def newer32(value, previous):
    return 0 < ((value-previous) & 0xffffffff) < 0x80000000


class SceneOrder:
    """Per-connection sequence gate. Timeout alone never admits old packets.

    Firmware announces boot with an invalid zero frame/tx/time scene. If that
    announcement was damaged, require three coherent low-uptime observations
    before adopting a restarted epoch. scene-v1 has no globally unique boot ID.
    """
    def __init__(self):
        self.last = self.anchor = self.candidate = None
        self.candidates = self.rejected = self.restarts = 0
        self.reset_next = True
        self.boot_pending = False
        self.last_received = self.candidate_started = None

    def accept(self, scene, now):
        if (not scene.valid and not scene.objects and
                scene.frame == scene.tx_sequence == scene.capture_ms == 0):
            self.last = self.anchor = self.candidate = None
            self.candidates = 0
            self.reset_next = True
            self.boot_pending = True
            self.restarts += 1
            return True, True
        reset = self.reset_next
        if self.boot_pending and scene.tx_sequence >= 128:
            self.rejected += 1
            return False, False
        if self.last is not None:
            old = self.last
            forward = (newer32(scene.tx_sequence, old.tx_sequence) and
                       newer32(scene.frame, old.frame) and
                       ((scene.capture_ms-old.capture_ms) & 0xffffffff) < 0x80000000)
            if not forward:
                reboot = (self.last_received is not None and now-self.last_received >= 1 and
                          scene.tx_sequence < 128 and scene.capture_ms < 60000 and
                          scene.tx_sequence < old.tx_sequence and scene.frame < old.frame and
                          scene.capture_ms < old.capture_ms)
                if reboot:
                    prior = self.candidate
                    coherent = (prior is not None and newer32(scene.tx_sequence, prior.tx_sequence)
                                and newer32(scene.frame, prior.frame) and
                                scene.capture_ms >= prior.capture_ms)
                    self.candidates = self.candidates+1 if coherent else 1
                    if not coherent:
                        self.candidate_started = now
                    self.candidate = scene
                    if self.candidates >= 3 and now-self.candidate_started >= .1:
                        self.last = self.anchor = None
                        self.restarts += 1
                        reset = True
                    else:
                        self.rejected += 1
                        return False, False
                else:
                    self.rejected += 1
                    return False, False
        # Capture clock may lag a reader, but cannot advance seconds ahead of
        # wall time. This also rejects a delayed packet from a retired epoch.
        if self.anchor is not None:
            ms, received = self.anchor
            delta = (scene.capture_ms-ms) & 0xffffffff
            if delta > (now-received)*1000+2000:
                self.rejected += 1
                return False, False
        else:
            self.anchor = (scene.capture_ms, now)
        self.last = scene
        self.last_received = now
        self.candidate = None
        self.candidates = 0
        self.reset_next = False
        self.boot_pending = False
        return True, reset
