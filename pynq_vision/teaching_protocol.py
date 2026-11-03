"""教学侧带协议；纯标准库、Python 3.6，既有 wire v3 保持原样。"""
import json
import math
import struct
import zlib

PREFIX = b'\x00\xfe'
HEADER = struct.Struct('<2sBQIHHI')
CHUNK = 128
MAX_MESSAGE = 32768
MAX_PARTS = (MAX_MESSAGE + CHUNK - 1) // CHUNK


def cobs_encode(data):
    out = bytearray([0]); at = 0; code = 1
    for b in data:
        if b:
            out.append(b); code += 1
        if not b or code == 255:
            out[at] = code; at = len(out); out.append(0); code = 1
    out[at] = code
    return bytes(out)


def cobs_decode(data):
    out = bytearray(); i = 0
    while i < len(data):
        n = data[i]; i += 1
        if not n or i + n - 1 > len(data):
            raise ValueError('bad COBS')
        out.extend(data[i:i+n-1]); i += n-1
        if n != 255 and i < len(data):
            out.append(0)
    return bytes(out)


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite teaching number')
    if isinstance(value, dict):
        for v in value.values(): finite_tree(v)
    elif isinstance(value, list):
        for v in value: finite_tree(v)


def encode_document(document):
    finite_tree(document)
    data = json.dumps(document, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('ascii')
    if not 0 < len(data) <= MAX_MESSAGE:
        raise ValueError('teaching document size exceeded')
    session, revision = int(document['session'], 16), document['revision']
    if not 0 < session < 1 << 64 or type(revision) is not int or not 0 < revision < 1 << 32:
        raise ValueError('bad teaching identity')
    count = (len(data) + CHUNK - 1) // CHUNK
    total_crc = zlib.crc32(data) & 0xffffffff
    packets = []
    for index in range(count):
        raw = HEADER.pack(b'TG', 1, session, revision, index, count, total_crc)
        raw += data[index*CHUNK:(index+1)*CHUNK]
        raw += struct.pack('<I', zlib.crc32(raw) & 0xffffffff)
        packets.append(PREFIX + cobs_encode(raw) + b'\x00')
    return packets


class TeachingParser:
    """顺序重组完整快照；缺包不提交，重复快照可重发，缓冲固定有界。"""
    def __init__(self):
        self.state = 0; self.buffer = bytearray(); self.rejected = 0
        self.key = None; self.parts = []

    def feed(self, data):
        documents = []
        for b in data:
            if self.state == 0:
                if b == 0: self.state = 1
            elif self.state == 1:
                if b == 254: self.state = 2; self.buffer.clear()
                elif b: self.state = 0
            elif b:
                if len(self.buffer) >= HEADER.size + CHUNK + 6:
                    self.state = 0; self.buffer.clear(); self.rejected += 1
                else: self.buffer.append(b)
            else:
                self.state = 1
                try:
                    doc = self._packet(cobs_decode(self.buffer))
                    if doc is not None: documents.append(doc)
                except (ValueError, KeyError, TypeError, OverflowError, struct.error, RecursionError):
                    self.rejected += 1; self.key = None; self.parts = []
                self.buffer.clear()
        return documents

    def _packet(self, raw):
        if not HEADER.size + 4 < len(raw) <= HEADER.size + CHUNK + 4:
            raise ValueError('bad teaching packet size')
        if zlib.crc32(raw[:-4]) & 0xffffffff != struct.unpack('<I', raw[-4:])[0]:
            raise ValueError('bad teaching CRC')
        magic, version, session, revision, index, count, crc = HEADER.unpack_from(raw)
        if magic != b'TG' or version != 1 or not session or not revision or not 0 <= index < count <= MAX_PARTS:
            raise ValueError('bad teaching header')
        key = (session, revision, count, crc)
        if index == 0: self.key = key; self.parts = []
        if key != self.key or index != len(self.parts):
            raise ValueError('missing/out of order teaching chunk')
        chunk = raw[HEADER.size:-4]
        if index < count - 1 and len(chunk) != CHUNK:
            raise ValueError('short teaching chunk')
        self.parts.append(chunk)
        if index != count - 1: return None
        data = b''.join(self.parts); self.key = None; self.parts = []
        if len(data) > MAX_MESSAGE or zlib.crc32(data) & 0xffffffff != crc:
            raise ValueError('bad complete document')
        doc = json.loads(data.decode('ascii')); finite_tree(doc)
        if not isinstance(doc, dict) or doc.get('session') != '{:016x}'.format(session) or doc.get('revision') != revision:
            raise ValueError('teaching identity mismatch')
        return doc
