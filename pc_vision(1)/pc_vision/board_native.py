"""Compatibility exports from the single repository C game build/transport."""
from .shared_runtime import canonical_module

_native = canonical_module("board_native")
ROOT = _native.ROOT
SRC = _native.SRC
NativeBoardGame = _native.NativeBoardGame
build_board_host = _native.build_board_host
compile_host = _native.compile_host
