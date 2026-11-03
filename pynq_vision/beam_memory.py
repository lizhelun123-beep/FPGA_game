"""Checked noncached xlnk mapping for the identified legacy PYNQ kernel.

Uses the same 88-byte ioctl ABI as the existing checked native C owner, not
libcma/PynqBuffer destructors or XRT. Import performs no device operations.
Python owns both allocations; all release decisions require actual DMA halt.
"""
import ctypes as C
import mmap
import os
import struct

SPAN = 5760 * 720


class XlnkBuffer:
    def __init__(self, halted, barrier):
        self.halted, self.barrier = halted, barrier
        self.fd, self.mapping = None, None
        self.identifier, self.physical, self.virtual = 0, 0, 0
        self.uncertain = False
        self.span = 3 * SPAN

    def allocate(self):
        import fcntl
        if self.fd is not None or not self.halted():
            raise RuntimeError("allocation requires a new owner and actual DMA halt")
        self.fd = os.open('/dev/xlnk', os.O_RDWR | os.O_CLOEXEC)
        argument = bytearray(88)
        struct.pack_into('<I', argument, 0, self.span)  # cacheable=0
        self.uncertain = True
        if fcntl.ioctl(self.fd, 0xc0045802, argument, True) != 0:
            raise RuntimeError("uncertain xlnk allocation; owner retained")
        length, identifier, physical, cacheable = struct.unpack_from('<IIII', argument)
        if (length != self.span or not 0 < identifier < 4096 or not physical or
                physical & 4095 or physical + self.span > 0x40000000 or cacheable):
            raise RuntimeError("untrusted xlnk allocation receipt; owner retained")
        self.identifier, self.physical = identifier, physical
        self.uncertain = False
        self.mapping = mmap.mmap(self.fd, self.span, flags=mmap.MAP_SHARED,
                                 prot=mmap.PROT_READ | mmap.PROT_WRITE,
                                 offset=identifier * 65536)
        view = C.c_uint8.from_buffer(self.mapping)
        self.virtual = C.addressof(view)
        del view
        return self

    def sync(self):
        if self.mapping is None or self.uncertain or self.barrier() != 0:
            raise RuntimeError("noncached mapping/barrier unavailable")

    def close(self):
        import fcntl
        if self.uncertain:
            raise RuntimeError("uncertain allocator state; do not retry global-ID operations")
        if self.identifier:
            if not self.halted():
                raise RuntimeError("buffer retained: actual DMA RS/HALTED not confirmed")
            self.sync() if self.mapping is not None else None
            if self.mapping is not None:
                self.mapping.close()
                self.mapping = None
                self.virtual = 0
            argument = bytearray(88)
            struct.pack_into('<I', argument, 0, self.identifier)
            self.uncertain = True
            if fcntl.ioctl(self.fd, 0xc0045803, argument, True) != 0:
                raise RuntimeError("uncertain xlnk free; do not retry")
            self.uncertain = False
            self.identifier, self.physical = 0, 0
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)

    def can_exit(self):
        return self.fd is None and not self.identifier and self.mapping is None and not self.uncertain


class Slot:
    def __init__(self, allocation, index):
        self.nbytes = SPAN
        self.device_address = allocation.physical + index * SPAN
