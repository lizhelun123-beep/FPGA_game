"""Shared internal control types and current binary-v3 command encoders.

ControlFrame kinds retain the shared presenter's historical labels. The
legacy ASCII response parser is kept for offline tools, never live UART.
"""
from .shared_runtime import canonical_module
from .board_wire import encode_level, encode_start, encode_reset

_control = canonical_module("board_control")
ControlFrame = _control.ControlFrame
ControlCommand = _control.ControlCommand
ControlTransportEvent = _control.ControlTransportEvent
ControlParser = _control.ControlParser
LegacyControlParser = _control.ControlParser
