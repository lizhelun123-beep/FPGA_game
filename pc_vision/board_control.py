"""Bounded LEVEL2/START2 handshake used by the PC and Standalone board."""
from dataclasses import dataclass
import base64
import re
import struct
import zlib


MAX_LINE = 192
LEVEL_PAYLOAD = struct.Struct("<BQiiiiI")
_HEX = re.compile(r"^[0-9A-Fa-f]{8}$")


@dataclass(frozen=True)
class ControlFrame:
    kind: str
    level_id: int = 0
    generation: int = 0
    x_milli: int = 0
    y_milli: int = 0
    dx_micro: int = 0
    dy_micro: int = 0
    nonce: int = 0
    board_ms: int = 0
    error_code: int = 0


@dataclass(frozen=True)
class ControlCommand:
    kind: str
    wire: bytes
    generation: int = 0
    nonce: int | str = 0
    level_id: int = 0

    @property
    def identity(self):
        return self.kind, self.generation, self.nonce, self.level_id

    def accepts(self, frame):
        expected = {"LEVEL2": "READY2", "START2": "STARTED2", "RESET2": "RESET2ACK"}
        return (self.kind in expected and frame.generation == self.generation and
                frame.nonce == self.nonce and
                (frame.kind == "ERROR2" or
                 (frame.kind == expected[self.kind] and
                  (not self.level_id or frame.level_id == self.level_id))))


@dataclass(frozen=True)
class ControlTransportEvent:
    kind: str  # SENT or TIMEOUT, emitted only by the UART owner.
    command: str
    generation: int
    nonce: int
    level_id: int
    epoch: int
    at_ms: int
    sent_ms: int
    attempt: int


def _line(body):
    crc = zlib.crc32(body.encode("ascii")) & 0xffffffff
    return ("@%s:%08X\r\n" % (body, crc)).encode("ascii")


def encode_level(level_id, generation, emitter, nonce):
    point = emitter["point"]
    direction = emitter["direction"]
    fields = (int(level_id), int(generation), round(float(point[0]) * 1000),
              round(float(point[1]) * 1000), round(float(direction[0]) * 1000000),
              round(float(direction[1]) * 1000000), int(nonce))
    if (not 1 <= fields[0] <= 15 or not 0 < fields[1] < 1 << 64 or
            not 0 < fields[-1] <= 0xffffffff):
        raise ValueError("invalid LEVEL2 identity")
    if (not 0 <= fields[2] <= 1279000 or not 0 <= fields[3] <= 719000 or
            not all(-1000000 <= value <= 1000000 for value in fields[4:6]) or
            not any(fields[4:6])):
        raise ValueError("invalid LEVEL2 emitter")
    # 29 bytes become 40 base64 characters: the complete command is 59 bytes,
    # fitting the PS UART's 64-byte RX FIFO while detection is busy.
    packed = LEVEL_PAYLOAD.pack(*fields)
    line = _line("LEVEL2:" + base64.b64encode(packed).decode("ascii"))
    assert len(line) <= 64
    return line


def encode_start(generation, nonce):
    if not 0 < generation < 1 << 64 or not 0 < nonce <= 0xffffffff:
        raise ValueError("invalid START2 identity")
    return _line("START2:%d,%d" % (int(generation), int(nonce)))


def encode_reset(generation, nonce):
    if not 0 < generation < 1 << 64 or not 0 < nonce <= 0xffffffff:
        raise ValueError("invalid RESET2 identity")
    return _line("RESET2:%d,%d" % (int(generation), int(nonce)))


def _integer(value, minimum=0, maximum=(1 << 64) - 1):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("invalid control integer")
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ValueError("control integer out of range")
    return parsed


def _signed(value, minimum=-2000000, maximum=2000000):
    if not re.fullmatch(r"-?[0-9]+", value):
        raise ValueError("invalid control signed integer")
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ValueError("control signed integer out of range")
    return parsed


class ControlParser:
    """Parse only complete, CRC-checked control acknowledgements."""
    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, chunk):
        rows = []
        self.buffer.extend(chunk)
        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n") + 1
            row = bytes(self.buffer[:end])
            del self.buffer[:end]
            if not (row.startswith(b"@READY2:") or row.startswith(b"@STARTED2:") or
                    row.startswith(b"@RESET2ACK:") or row.startswith(b"@ERROR2:")):
                continue
            try:
                rows.append(self._decode(row))
            except (ValueError, UnicodeError):
                self.rejected += 1
        if len(self.buffer) > MAX_LINE:
            offset = self.buffer.rfind(b"@")
            self.buffer = self.buffer[offset:] if offset >= 0 else bytearray()
            if len(self.buffer) > MAX_LINE:
                self.buffer.clear()
                self.rejected += 1
        return rows

    @staticmethod
    def _decode(row):
        if len(row) > MAX_LINE or not row.startswith(b"@"):
            raise ValueError("invalid control envelope")
        text = row.decode("ascii").rstrip("\r\n")
        if ":" not in text:
            raise ValueError("missing control CRC")
        body, crc_text = text[1:].rsplit(":", 1)
        if not _HEX.fullmatch(crc_text):
            raise ValueError("invalid control CRC")
        if (zlib.crc32(body.encode("ascii")) & 0xffffffff) != int(crc_text, 16):
            raise ValueError("control CRC mismatch")
        kind, fields = body.split(":", 1)
        values = fields.split(",")
        if kind == "READY2" and len(values) == 8:
            return ControlFrame(kind, _integer(values[0], 1, 15), _integer(values[1], 1),
                                _signed(values[2]), _signed(values[3]), _signed(values[4]),
                                _signed(values[5]), _integer(values[6], 1, 0xffffffff),
                                _integer(values[7]))
        if kind == "STARTED2" and len(values) == 4:
            return ControlFrame(kind, _integer(values[0], 1, 15), _integer(values[1], 1),
                                nonce=_integer(values[2], 1, 0xffffffff),
                                board_ms=_integer(values[3]))
        if kind == "RESET2ACK" and len(values) == 3:
            return ControlFrame(kind, generation=_integer(values[0], 1),
                                nonce=_integer(values[1], 1, 0xffffffff),
                                board_ms=_integer(values[2]))
        if kind == "ERROR2" and len(values) == 3:
            return ControlFrame(kind, generation=_integer(values[1], 1),
                                nonce=_integer(values[2], 1, 0xffffffff),
                                error_code=_integer(values[0], 0, 0xffffffff))
        raise ValueError("unexpected control frame")
