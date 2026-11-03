"""PC tools; load the legacy detector only when explicitly requested."""

__all__ = ["Detection", "Detector", "Result", "load_config"]


def __getattr__(name):
    # The pose-only serial game must not import OpenCV/NumPy at package startup.
    from importlib import import_module
    if name == "load_config":
        value = import_module(".config", __name__).load_config
    elif name in ("Detection", "Detector", "Result"):
        value = getattr(import_module(".detector", __name__), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
