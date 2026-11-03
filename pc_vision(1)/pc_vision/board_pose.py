"""Compatibility exports from the current board POSE2 protocol parser."""
from .shared_runtime import canonical_module

_pose = canonical_module("board_pose")
TYPES = _pose.TYPES
HEADER = _pose.HEADER
OBJECT = _pose.OBJECT
PREFIX = _pose.PREFIX
SUFFIX = _pose.SUFFIX
MAX_LINE = _pose.MAX_LINE
STATUSES = _pose.STATUSES
PoseFrame = _pose.PoseFrame
decode_pose = _pose.decode_pose
PoseParser = _pose.PoseParser
PoseOrder = _pose.PoseOrder
ClockBounds = _pose.ClockBounds
