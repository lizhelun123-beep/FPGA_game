"""Small dependency-free MMIO helpers, suitable for fake-register tests."""

import time


class RegisterTimeout(RuntimeError):
    pass


class RegisterBlock:
    def __init__(self, io):
        self.io = io

    def read(self, offset):
        return int(self.io.read(offset)) & 0xFFFFFFFF

    def write(self, offset, value):
        self.io.write(offset, int(value) & 0xFFFFFFFF)

    def wait(self, offset, mask, expected, timeout=1.0, interval=0.001):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.read(offset)
            if value & mask == expected:
                return value
            time.sleep(interval)
        value = self.read(offset)
        raise RegisterTimeout(
            "register 0x{:x} mask 0x{:08x}: got 0x{:08x}, expected 0x{:08x}".format(
                offset, mask, value & mask, expected))
