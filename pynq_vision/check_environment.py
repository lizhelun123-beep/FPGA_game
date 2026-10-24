"""Read-only PYNQ/Python dependency report for the first SD boot."""

import importlib
import json
import platform
import sys


def module_version(name):
    try:
        module = importlib.import_module(name)
        return {"ok": True, "version": getattr(module, "__version__", "unknown")}
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}


def report():
    result = {
        "python": sys.version,
        "platform": platform.platform(),
        "pynq": module_version("pynq"),
        "numpy": module_version("numpy"),
        "opencv": module_version("cv2"),
        "dataclasses": module_version("dataclasses"),
    }
    return result


def main():
    print(json.dumps(report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
