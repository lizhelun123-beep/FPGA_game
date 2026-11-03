"""Expose the canonical binary-v3 codec to this web package; no copied parser."""
from .shared_runtime import canonical_module

_wire = canonical_module("board_wire")
VERSION = _wire.VERSION
BinaryParser = _wire.BinaryParser
PacketParser = _wire.PacketParser
encode_level = _wire.encode_level
encode_start = _wire.encode_start
encode_reset = _wire.encode_reset
encode_sync = _wire.encode_sync
encode_control = _wire.encode_control
encode_pose = _wire.encode_pose


def __getattr__(name):
    return getattr(_wire, name)
