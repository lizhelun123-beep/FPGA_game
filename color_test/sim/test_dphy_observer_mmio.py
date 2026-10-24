"""Local RAM/readonly-buffer and serial-exit fixtures. No board/device imports."""
import ctypes
import importlib.util
import mmap
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ENTRY=Path(__file__).resolve().parents[1]/'tools/dphy_observer.py'
spec=importlib.util.spec_from_file_location('observer',ENTRY)
observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
BINDING_ONLY=True
LIBRARY=Path('unused-binding-backend')


class Function:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)


class BindingBackend:
    """RAM-only fake C ABI; never claimed to execute the native access code."""
    def __init__(self):
        self.dphy_mmio_abi=Function(lambda:1)
        def read(base,span,offset,result):
            ctypes.cast(result,ctypes.POINTER(ctypes.c_uint32))[0]=int.from_bytes(ctypes.string_at(base+offset,4),'little')
            return 0
        def write(base,span,offset,value):
            ctypes.memmove(base+offset,value.to_bytes(4,'little'),4);return 0
        self.dphy_mmio_read32=Function(read);self.dphy_mmio_write32=Function(write)


class MMIOContract(unittest.TestCase):
    def setUp(self):
        self.backend_patch=patch.object(observer.ctypes,'CDLL',side_effect=lambda _:BindingBackend()) if BINDING_ONLY else None
        if self.backend_patch:self.backend_patch.start()
        self.memory=mmap.mmap(-1,32)
        self.memory[:]=bytes(range(32))
        self.word=observer.WordAccess(self.memory,LIBRARY,True)
    def tearDown(self):
        self.word.close();self.memory.close()
        if self.backend_patch:self.backend_patch.stop()
    def test_exact_word_and_adjacent_canaries(self):
        original=self.memory[:]
        self.word.write(12,0x91a2b3c4)
        self.assertEqual(self.word.read(12),0x91a2b3c4)
        self.assertEqual(self.memory[:],original[:12]+b'\xc4\xb3\xa2\x91'+original[16:])
    def test_board_ram_gate_uses_no_device_mapping(self):
        with patch.object(mmap,'mmap',side_effect=AssertionError('device map forbidden')):
            self.assertEqual(observer.WordAccess.ram_self_test(LIBRARY),
                             {'native_abi':1,'word_bytes':4,'ram_canaries_intact':True})
    def test_every_valid_offset_and_full_uint32(self):
        for offset in range(0,32,4):
            for value in (0,1,0x80000000,0xffffffff):
                self.word.write(offset,value);self.assertEqual(self.word.read(offset),value)
    def test_reject_offsets_without_touching_ram(self):
        before=self.memory[:]
        for offset in (-4,-1,1,2,3,29,32,0x100000000,False,1.0):
            with self.assertRaises(ValueError):self.word.write(offset,0)
            with self.assertRaises(ValueError):self.word.read(offset)
        self.assertEqual(self.memory[:],before)
    def test_reject_value_without_truncation(self):
        before=self.memory[:]
        for value in (-1,0x100000000,True,1.0):
            with self.assertRaises(ValueError):self.word.write(0,value)
        self.assertEqual(self.memory[:],before)
    def test_pin_lifetime_and_close(self):
        with self.assertRaises(BufferError):self.memory.close()
        self.word.close()
        with self.assertRaises(RuntimeError):self.word.read(0)
        self.word.close()
    def test_logical_readonly_view(self):
        other=observer.WordAccess(self.memory,LIBRARY,False)
        try:
            self.assertEqual(other.read(0),0x03020100)
            with self.assertRaises(PermissionError):other.write(0,0)
        finally:other.close()
    def test_actual_readonly_mapping(self):
        with tempfile.TemporaryFile() as file:
            file.write(struct.pack('<8I',*range(8)));file.flush()
            mapping=mmap.mmap(file.fileno(),32,access=mmap.ACCESS_READ)
            view=observer.WordAccess(mapping,LIBRARY,False)
            try:
                self.assertEqual(view.read(28),7)
                with self.assertRaises(PermissionError):view.write(28,1)
                with self.assertRaises(PermissionError):observer.WordAccess(mapping,LIBRARY,True)
            finally:view.close();mapping.close()
    def test_native_invalid_arguments_fail_before_access(self):
        if BINDING_ONLY:self.skipTest('Native guards executed in32-bit C RAM fixture, not duplicated by mock')
        lib=self.word._lib;address=self.word._view.buf;result=ctypes.c_uint32(0xf00d)
        for base,span,offset in [(0,32,0),(address+1,32,0),(address,0,0),
                                 (address,3,0),(address,31,0),(address,32,2),(address,32,32)]:
            self.assertEqual(lib.dphy_mmio_write32(base,span,offset,0),-1)
            self.assertEqual(lib.dphy_mmio_read32(base,span,offset,ctypes.byref(result)),-1)
            self.assertEqual(result.value,0xf00d)
        self.assertEqual(lib.dphy_mmio_read32(address,32,0,None),-1)


class FakeConsole:
    def __init__(self,data):self.data=data;self.foreground_owned=True;self.calls=0
    def until(self,pattern,seconds):
        self.calls+=1;match=re.search(pattern,self.data)
        if match is None:raise TimeoutError('no fixture marker')
        return match


class ExitReceipt(unittest.TestCase):
    def test_sigbus_exit_is_reported_immediately(self):
        console=FakeConsole(b'Bus error\r\n\r\nFINISH:135\r\nxilinx@pynq:~$ ')
        with self.assertRaisesRegex(RuntimeError,'status 135'):
            observer.observer_marker_or_exit(console,rb'DPHY_EXPORT_BEGIN ([0-9]+) ([0-9a-f]{64})\r?\n','FINISH',75)
        self.assertFalse(console.foreground_owned);self.assertEqual(console.calls,1)
    def test_marker_and_coalesced_first_frame_keep_groups(self):
        console=FakeConsole(b'DPHY_EXPORT_BEGIN 12 '+b'a'*64+b'\r\nDPHY_DATA 1 QUJD\r\n')
        match=observer.observer_marker_or_exit(console,rb'DPHY_EXPORT_BEGIN ([0-9]+) ([0-9a-f]{64})\r?\n','FINISH',75)
        self.assertEqual(match.group(1),b'12');self.assertEqual(match.group(2),b'a'*64)
        self.assertTrue(console.foreground_owned)
    def test_clean_exit_without_required_artifact_still_fails(self):
        console=FakeConsole(b'\nFINISH:0\n')
        with self.assertRaisesRegex(RuntimeError,'status 0'):
            observer.observer_marker_or_exit(console,rb'DPHY_EXPORT_BEGIN','FINISH',75)


if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit('Use --binding-only or an explicitly built host-native DLL')
    argument=sys.argv.pop(1);BINDING_ONLY=argument=='--binding-only'
    if not BINDING_ONLY:LIBRARY=Path(argument).resolve()
    unittest.main(verbosity=2)
