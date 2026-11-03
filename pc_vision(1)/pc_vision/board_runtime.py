"""Use exactly the same UART owner and presenter as the Godot front end."""
from .shared_runtime import canonical_module

_runtime = canonical_module("godot_bridge")
BoardInput = _runtime.BoardInput
BoardGamePresenter = _runtime.BoardGamePresenter
BRIDGE_BUILD = _runtime.BRIDGE_BUILD
now_ms = _runtime.now_ms
