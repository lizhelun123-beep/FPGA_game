"""Restored marker POSE2 transport. No detection, smoothing or ray solving."""
from dataclasses import dataclass, asdict
import math
import re
import struct
import zlib

TYPES = ("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
HEADER = struct.Struct("<BBBBIQQQQHHHHHH")
OBJECT = struct.Struct("<BBHffffff")
PREFIX, SUFFIX = b"@POSE2:", b":END\n"
MAX_LINE = 12 + 2*(HEADER.size + 5*OBJECT.size + 4)
STATUSES = ("OK", "BAD_ARGUMENT", "BAD_CONFIG", "BAD_TIME", "OLD_GENERATION",
            "DUPLICATE_FRAME", "STALE", "UNAVAILABLE", "INVALID_GEOMETRY",
            "RESTRICTED", "PENDING", "NO_FRAME")


@dataclass(frozen=True)
class PoseFrame:
    tx: int
    generation: int
    sequence: int
    captured_ms: int
    published_ms: int
    valid: bool
    status: str
    raw_mask: int
    pending_mask: int
    missing_mask: int
    models: tuple
    wire_version: int = 2
    level_id: int = 0
    session_generation: int = 0
    nonce: int = 0

    def record(self):
        return {"schema": f"board-pose-v{self.wire_version}", **asdict(self)}


def decode_pose(line):
    if not line.startswith(PREFIX) or not line.endswith(SUFFIX) or len(line) > MAX_LINE:
        raise ValueError("Invalid POSE2 envelope")
    encoded = line[len(PREFIX):-len(SUFFIX)]
    if len(encoded) % 2 or not re.fullmatch(b"[0-9A-Fa-f]+", encoded):
        raise ValueError("Invalid POSE2 hex")
    data = bytes.fromhex(encoded.decode("ascii"))
    if len(data) < HEADER.size+4 or zlib.crc32(data[:-4]) != struct.unpack_from("<I", data, len(data)-4)[0]:
        raise ValueError("POSE2 CRC/length mismatch")
    version, flags, count, profile, tx, generation, seq, captured, published, w, h, status, raw, pending, missing = HEADER.unpack_from(data)
    if (version != 2 or flags not in (0, 1) or profile != 2 or count > 5 or
            (w, h) != (1280, 720) or status >= len(STATUSES) or
            not generation or published < captured or (not flags and count) or
            len(data) != HEADER.size + count*OBJECT.size+4 or
            (flags and (status or pending or not seq or not captured)) or
            (raw | pending | missing) & ~0x2f):
        raise ValueError("Invalid POSE2 header")
    models, kinds = [], set()
    for i in range(count):
        kind, effective, reserved, x, y, ax, ay, length, width = OBJECT.unpack_from(data, HEADER.size+i*OBJECT.size)
        if (kind not in (0, 1, 2, 3, 5) or kind in kinds or effective != 1 or reserved or
                not all(math.isfinite(v) for v in (x, y, ax, ay, length, width)) or
                not 0 <= x <= 1279 or not 0 <= y <= 719 or min(length, width) <= 0 or
                max(length, width) > 4096 or abs(math.hypot(ax, ay)-1) > .01):
            raise ValueError("Invalid POSE2 geometry")
        kinds.add(kind)
        models.append(dict(type=TYPES[kind], center=[x, y], axis=[ax, ay], size=[length, width]))
    return PoseFrame(tx, generation, seq, captured, published, bool(flags),
                     STATUSES[status], raw, pending, missing, tuple(models))


class PoseParser:
    """Bounded resynchronization across noise, logs, partial and corrupt packets."""
    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, chunk):
        records = []
        # Each caller read is bounded; process a stream without growing a backlog.
        for start in range(0, len(chunk), 4096):
            self.buffer.extend(chunk[start:start+4096])
            while b"\n" in self.buffer:
                end = self.buffer.index(b"\n")+1
                row = bytes(self.buffer[:end])
                del self.buffer[:end]
                sync = re.search(rb"@SYNC2:([0-9a-f]{8}):([0-9]{1,20})\r*\n$", row)
                if sync:
                    records.append((sync[1].decode("ascii"), int(sync[2])))
                    continue
                offset = row.rfind(PREFIX)
                if offset < 0:
                    continue
                try:
                    records.append(decode_pose(row[offset:]))
                except (ValueError, struct.error):
                    self.rejected += 1
            if len(self.buffer) > MAX_LINE:
                offset = self.buffer.rfind(PREFIX)
                self.buffer = self.buffer[offset:] if offset >= 0 else bytearray()
                if len(self.buffer) > MAX_LINE:
                    self.buffer.clear()
                    self.rejected += 1
        return records


class PoseOrder:
    def __init__(self):
        self.last = None

    def accept(self, frame):
        if frame.tx == frame.sequence == frame.captured_ms == 0 and not frame.valid:
            self.last = None
            return True, True
        if self.last is not None:
            old = self.last
            if (frame.generation != old.generation or frame.sequence <= old.sequence or
                    frame.captured_ms <= old.captured_ms or frame.published_ms < old.published_ms or
                    not 0 < ((frame.tx-old.tx) & 0xffffffff) < 0x80000000):
                return False, False
        self.last = frame
        return True, False


class ClockBounds:
    """Two-way nonce timestamp mapping, retaining the entire round-trip interval.

    Capture is never replaced with receipt time. An interval must fit wholly in
    the game's age/selection window; its upper end is used for conservative
    elapsed-time scoring. This is a bounded software mapping, not exposure time.
    """
    def __init__(self, sent_ms, received_ms, board_ms, board_sent_ms=None):
        board_sent_ms = board_ms if board_sent_ms is None else board_sent_ms
        turnaround = board_sent_ms-board_ms
        if turnaround < 0 or not 0 <= received_ms-sent_ms-turnaround <= 250:
            raise ValueError("Clock round trip exceeds250ms")
        self.low = sent_ms-board_ms
        self.high = received_ms-board_sent_ms
        self.observed_ms = received_ms

    def map(self, captured_ms, now_ms):
        if now_ms < self.observed_ms or now_ms-self.observed_ms > 5000:
            raise ValueError("Clock synchronization expired")
        # Explicit1ms/s clock-drift allowance between short software syncs.
        drift = math.ceil((now_ms-self.observed_ms)/1000)
        return captured_ms+self.low-drift, captured_ms+self.high+drift
