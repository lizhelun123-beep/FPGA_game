"""Wire v3: bounded COBS binary packets for all board/PC messages.

Legacy ControlFrame kind labels are an internal API shared by Godot/web and
the existing handshake state machine. They are never serialized as text.
"""
import math
import struct
import zlib

from .board_control import ControlFrame, LEVEL_PAYLOAD
from .board_pose import PoseFrame, STATUSES, TYPES

VERSION = 3
MAX_PAYLOAD = 160
MAX_ENCODED = MAX_PAYLOAD + 11
PREFIX = b"\x00\xff"
SYNC, SYNC_REPLY, LEVEL, READY, START, STARTED, RESET, RESET_ACK, ERROR, POSE = range(1, 11)
NAMES = {SYNC: "SYNC3", SYNC_REPLY: "SYNC3_REPLY", LEVEL: "LEVEL3", READY: "READY3",
         START: "START3", STARTED: "STARTED3", RESET: "RESET3", RESET_ACK: "RESET3ACK",
         ERROR: "ERROR3", POSE: "POSE3"}
POSE_HEADER = struct.Struct("<BQIIQQQQBBBBBBB")
OBJECT = struct.Struct("<BBHHHHH")


def cobs_encode(data):
    if len(data) > MAX_PAYLOAD+10:
        raise ValueError("Packet exceeds bound")
    output = bytearray(b"\x00")
    code_at, code = 0, 1
    for value in data:
        if value == 0:
            output[code_at] = code
            code_at, code = len(output), 1
            output.append(0)
        else:
            output.append(value)
            code += 1
    output[code_at] = code
    return bytes(output)


def cobs_decode(data):
    result, offset = bytearray(), 0
    while offset < len(data):
        code = data[offset]
        offset += 1
        if not code or offset+code-1 > len(data):
            raise ValueError("Invalid COBS block")
        result.extend(data[offset:offset+code-1])
        offset += code-1
        if code != 255 and offset < len(data):
            result.append(0)
        if len(result) > MAX_PAYLOAD+10:
            raise ValueError("Decoded packet exceeds bound")
    return bytes(result)


def encode_packet(kind, payload):
    if kind not in NAMES or len(payload) > MAX_PAYLOAD:
        raise ValueError("Invalid packet type/length")
    body = b"RG" + bytes((VERSION, kind)) + struct.pack("<H", len(payload)) + payload
    return PREFIX + cobs_encode(body+struct.pack("<I", zlib.crc32(body))) + b"\x00"


def decode_packet(encoded):
    data = cobs_decode(encoded)
    if len(data) < 10 or data[:3] != b"RG\x03" or data[3] not in NAMES:
        raise ValueError("Invalid wire magic/version/type")
    size = struct.unpack_from("<H", data, 4)[0]
    if size > MAX_PAYLOAD or len(data) != size+10:
        raise ValueError("Invalid wire length")
    if zlib.crc32(data[:-4]) != struct.unpack_from("<I", data, len(data)-4)[0]:
        raise ValueError("Wire CRC mismatch")
    return data[3], data[6:-4]


class PacketParser:
    """Ignore text outside 00 FF ... 00; reject bounded incomplete/corrupt packets."""
    def __init__(self):
        self.state = 0
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, chunk):
        packets = []
        for byte in chunk:
            if self.state == 0:
                if byte == 0:
                    self.state = 1
            elif self.state == 1:
                if byte == 255:
                    self.state = 2
                    self.buffer.clear()
                elif byte:
                    self.state = 0
            elif byte:
                if len(self.buffer) < MAX_ENCODED:
                    self.buffer.append(byte)
                else:
                    self.rejected += 1
                    self.state = 0
                    self.buffer.clear()
            else:
                self.state = 1
                try:
                    packets.append(decode_packet(self.buffer))
                except (ValueError, struct.error):
                    self.rejected += 1
                self.buffer.clear()
        return packets


def _identity(generation, nonce):
    if not 0 < generation < 1 << 64 or not 0 < nonce <= 0xffffffff:
        raise ValueError("Invalid session identity")


def encode_level(level_id, generation, emitter, nonce):
    _identity(generation, nonce)
    values = (int(level_id), int(generation),
              *(round(float(v)*scale) for field, scale in (("point", 1000), ("direction", 1000000))
                for v in emitter[field]), int(nonce))
    if (not 1 <= values[0] <= 15 or not 0 <= values[2] <= 1279000 or not 0 <= values[3] <= 719000 or
            not all(-1000000 <= v <= 1000000 for v in values[4:6]) or not any(values[4:6])):
        raise ValueError("Invalid level emitter")
    return encode_packet(LEVEL, LEVEL_PAYLOAD.pack(*values))


def encode_start(generation, nonce):
    _identity(generation, nonce)
    return encode_packet(START, struct.pack("<QI", generation, nonce))


def encode_reset(generation, nonce):
    _identity(generation, nonce)
    return encode_packet(RESET, struct.pack("<QI", generation, nonce))


def encode_sync(nonce):
    return encode_packet(SYNC, struct.pack("<I", int(nonce, 16)))


def encode_control(frame):
    _identity(frame.generation, frame.nonce)
    if frame.kind == "READY2":
        payload = LEVEL_PAYLOAD.pack(frame.level_id, frame.generation, frame.x_milli, frame.y_milli,
                                     frame.dx_micro, frame.dy_micro, frame.nonce) + struct.pack("<Q", frame.board_ms)
        return encode_packet(READY, payload)
    if frame.kind == "STARTED2":
        return encode_packet(STARTED, struct.pack("<BQIQ", frame.level_id, frame.generation, frame.nonce, frame.board_ms))
    if frame.kind == "RESET2ACK":
        return encode_packet(RESET_ACK, struct.pack("<QIQ", frame.generation, frame.nonce, frame.board_ms))
    if frame.kind == "ERROR2":
        return encode_packet(ERROR, struct.pack("<IQI", frame.error_code, frame.generation, frame.nonce))
    raise ValueError("Not a response")


def decode_control(kind, payload):
    if kind == READY and len(payload) == 37:
        level, generation, x, y, dx, dy, nonce = LEVEL_PAYLOAD.unpack(payload[:29])
        frame = ControlFrame("READY2", level, generation, x, y, dx, dy, nonce, struct.unpack_from("<Q", payload, 29)[0])
        if not 0 <= x <= 1279000 or not 0 <= y <= 719000 or not all(-1000000 <= v <= 1000000 for v in (dx, dy)) or not (dx or dy):
            raise ValueError("Invalid echoed emitter")
    elif kind == STARTED and len(payload) == 21:
        level, generation, nonce, board_ms = struct.unpack("<BQIQ", payload)
        frame = ControlFrame("STARTED2", level_id=level, generation=generation, nonce=nonce, board_ms=board_ms)
    elif kind == RESET_ACK and len(payload) == 20:
        generation, nonce, board_ms = struct.unpack("<QIQ", payload)
        frame = ControlFrame("RESET2ACK", generation=generation, nonce=nonce, board_ms=board_ms)
    elif kind == ERROR and len(payload) == 16:
        code, generation, nonce = struct.unpack("<IQI", payload)
        frame = ControlFrame("ERROR2", generation=generation, nonce=nonce, error_code=code)
    else:
        raise ValueError("Unexpected control type/length")
    _identity(frame.generation, frame.nonce)
    if kind in (READY, STARTED) and not 1 <= frame.level_id <= 15:
        raise ValueError("Invalid response level")
    return frame


def decode_pose(payload):
    if len(payload) < POSE_HEADER.size:
        raise ValueError("Short pose")
    level, pc_generation, nonce, tx, generation, seq, captured, published, valid, status, raw, pending, missing, count, geometry = POSE_HEADER.unpack_from(payload)
    _identity(pc_generation, nonce)
    if (not 1 <= level <= 15 or not generation or published < captured or valid not in (0, 1) or
            status >= len(STATUSES) or count > 5 or geometry != 1 or
            len(payload) != POSE_HEADER.size+count*OBJECT.size or
            (not valid and count) or (valid and (status or pending or not seq or not captured)) or
            (raw | pending | missing) & ~0x2f):
        raise ValueError("Invalid pose metadata")
    models, kinds = [], set()
    for i in range(count):
        kind, flags, x, y, angle, length, width = OBJECT.unpack_from(payload, POSE_HEADER.size+i*OBJECT.size)
        if kind not in (0, 1, 2, 3, 5) or kind in kinds or flags != 1 or x > 1279*16 or y > 719*16 or not 0 < length <= 4096*8 or not 0 < width <= 4096*8:
            raise ValueError("Invalid pose geometry")
        kinds.add(kind)
        radians = angle*math.tau/65536
        models.append(dict(type=TYPES[kind], center=[x/16, y/16], axis=[math.cos(radians), math.sin(radians)], size=[length/8, width/8]))
    return PoseFrame(tx, generation, seq, captured, published, bool(valid), STATUSES[status], raw, pending, missing,
                     tuple(models), VERSION, level, pc_generation, nonce)


def encode_pose(frame, level_id, generation, nonce):
    """Offline replay/fixtures use the same compact complete-snapshot encoding."""
    _identity(generation, nonce)
    models = frame.models if frame.valid else ()
    payload = POSE_HEADER.pack(level_id, generation, nonce, frame.tx, frame.generation, frame.sequence,
                              frame.captured_ms, frame.published_ms, int(frame.valid), STATUSES.index(frame.status),
                              frame.raw_mask, frame.pending_mask, frame.missing_mask & 0x2f, len(models), 1)
    for model in models:
        x, y = model['center']
        length, width = model['size']
        angle = math.atan2(model['axis'][1], model['axis'][0]) % math.tau
        payload += OBJECT.pack(TYPES.index(model['type']), 1, math.floor(x*16+.5), math.floor(y*16+.5),
                               math.floor(angle*65536/math.tau+.5) & 65535,
                               math.floor(length*8+.5), math.floor(width*8+.5))
    decode_pose(payload)  # Refuse semantically invalid fixture packets.
    return encode_packet(POSE, payload)


class BinaryParser:
    def __init__(self):
        self.framing = PacketParser()
        self.invalid_messages = 0

    @property
    def rejected(self):
        return self.framing.rejected+self.invalid_messages

    def feed(self, chunk):
        messages = []
        for kind, payload in self.framing.feed(chunk):
            try:
                if kind == POSE:
                    messages.append(decode_pose(payload))
                elif kind == SYNC_REPLY and len(payload) == 20:
                    nonce, received, sent = struct.unpack("<IQQ", payload)
                    if sent < received:
                        raise ValueError("Invalid sync times")
                    messages.append((f"{nonce:08x}", received, sent))
                else:
                    messages.append(decode_control(kind, payload))
            except (ValueError, struct.error):
                self.invalid_messages += 1
        return messages
