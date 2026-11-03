"""Shared OpenCV detector used by both PC and PYNQ front ends."""

from .config import load_config
from .detector import Detection, Detector, Result

__all__ = ["Detection", "Detector", "Result", "load_config"]
