"""Validate declared independent linear DMA buffers; no device access, Python 3.8+."""

import argparse
import json
import sys
from pathlib import Path


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(label + " must be an integer >= " + str(minimum))
    return value


def check_layout(document):
    if not isinstance(document, dict) or type(document.get("version")) is not int:
        raise ValueError("root requires integer version")
    if document["version"] != 1:
        raise ValueError("unsupported version")
    channels = document.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError("channels must be a nonempty list")
    names, ranges, results = set(), [], []
    expected_access = {"idle": "none", "device_read": "none",
                       "device_write": "none", "cpu_read": "read", "cpu_write": "write"}
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("channel must be an object")
        name = channel.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("channel name must be nonempty and unique")
        names.add(name)
        values = {key: integer(channel.get(key), name + "." + key, 1)
                  for key in ("width", "height", "bytes_per_pixel", "stride", "span", "cache_line")}
        row_bytes = values["width"] * values["bytes_per_pixel"]
        if values["stride"] < row_bytes:
            raise ValueError(name + ": stride smaller than active row")
        if values["span"] < values["stride"] * values["height"]:
            raise ValueError(name + ": span smaller than padded rows")
        alignment = values["cache_line"]
        if alignment & (alignment - 1):
            raise ValueError(name + ": cache_line must be a power of two")
        if values["span"] % alignment:
            raise ValueError(name + ": span not cache-line aligned")
        buffers = channel.get("buffers")
        if not isinstance(buffers, list) or not buffers:
            raise ValueError(name + ": buffers must be a nonempty list")
        for index, buffer in enumerate(buffers):
            label = "{}[{}]".format(name, index)
            if not isinstance(buffer, dict):
                raise ValueError(label + ": buffer must be an object")
            start = integer(buffer.get("address"), label + ".address")
            end = start + values["span"]
            if start >= (1 << 64) or end > (1 << 64):
                raise ValueError(label + ": address range exceeds 64 bits")
            if start % alignment:
                raise ValueError(label + ": address not cache-line aligned")
            owner, access = buffer.get("owner"), buffer.get("cpu_access")
            if not isinstance(owner, str) or owner not in expected_access:
                raise ValueError(label + ": unknown ownership")
            if access != expected_access[owner]:
                raise ValueError(label + ": owner/CPU access conflict")
            ranges.append((start, end, label))
        results.append({"name": name, "row_bytes": row_bytes,
                        "stride": values["stride"], "span": values["span"], "buffers": len(buffers)})
    ordered = sorted(ranges)
    for before, after in zip(ordered, ordered[1:]):
        if after[0] < before[1]:
            raise ValueError("overlap: " + before[2] + " and " + after[2])
    return {"status": "PASS_STATIC_DESCRIPTION", "channels": results, "buffers": len(ranges),
            "not_proven": ["Actual DMA completion/retirement and runtime ownership",
                           "Platform cache APIs, coherency and bus ordering",
                           "Actual HALTED state and safe resource release"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_layout(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
