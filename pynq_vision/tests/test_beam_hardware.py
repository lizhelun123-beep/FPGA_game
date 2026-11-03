"""Offline register/allocator fault models, not board/PYNQ validation."""
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import types
import unittest
import tempfile
from unittest.mock import patch

from pynq_vision.beam_admission import (inspect_bundle, validate_receipt,
    check_uart_available, getty_targets_device)
from pynq_vision.beam_hardware import PynqOwner, DisplayTiming, LegacyCsi, capture_class
from pynq_vision.beam_memory import XlnkBuffer, SPAN
from pynq_vision.beam_runtime import FRAME_BYTES, BytePointer, load_library

ROOT = Path(__file__).resolve().parents[2]
HOST = os.environ.get('BEAM_PYNQ_HOST_LIBRARY')
BUNDLE = os.environ.get('BEAM_PYNQ_HARDWARE_DIR')


class Registers:
    def __init__(self, dma=False, clock=False):
        self.values = {0: 0, 4: 1 if dma else 0}
        self.dma, self.clock = dma, clock
        self.history = []
        self.events = 0

    def read(self, offset):
        self.history.append(('read', offset))
        if self.dma and offset == 4 and self.values[0] & 1:
            self.events += 1
            return 0x1000 if self.events % 2 else 0
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.history.append(('write', offset, value))
        self.values[offset] = value
        if self.dma and offset == 0:
            self.values[4] = 0 if value & 1 else 1
        if self.dma and offset == 0x28:
            self.values[offset] = value | ((value & 31) << 16)
        if self.clock and offset == 0:
            self.values[4] = value & 1


class FakeAllocation:
    releases = []

    def __init__(self, halted, barrier):
        self.halted, self.barrier = halted, barrier
        self.span = 3 * SPAN
        self.physical = 0x20000000
        self.virtual = 0

    def allocate(self):
        self.storage = C.create_string_buffer(self.span + 64)
        self.virtual = (C.addressof(self.storage) + 63) & ~63
        return self

    def sync(self):
        if self.barrier(): raise RuntimeError('barrier')

    def close(self):
        if not self.halted(): raise RuntimeError('release while DMA active')
        self.releases.append('halted_release')
        self.storage = None
        self.virtual = 0


class HardwareContractTests(unittest.TestCase):
    def test_getty_commandline_is_rejected_by_target_uart_only(self):
        device = Path('/dev/ttyPS0')
        self.assertTrue(getty_targets_device(b'/sbin/agetty\0--keep-baud\0ttyPS0\0', device))
        self.assertTrue(getty_targets_device('/usr/sbin/serial-getty /dev/ttyPS0', device))
        self.assertFalse(getty_targets_device('/sbin/agetty ttyPS1', device))
        self.assertFalse(getty_targets_device('/usr/bin/login ttyPS0', device))

    def test_kernel_console_uart_rejected_without_device_open(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / 'consoles').write_text('ttyFAKE -W- (EC p a) 204:64\n')
            with self.assertRaises(RuntimeError): check_uart_available('/dev/ttyFAKE', proc)
    def capture_fixture(self, fault=False):
        from pynq_vision.vdma import AxiVdma
        class CaptureRegisters(Registers):
            def __init__(inner):
                super().__init__()
                inner.values.update({0x30:0, 0x34:1, 0x28:0})
                inner.status_reads = 0
                inner.first_park_reads = None
            def read(inner, offset):
                if offset == 0x34 and inner.values[0x30] & 1:
                    inner.status_reads += 1
                    return (0x1000 if inner.status_reads % 2 else 0) | (0x90 if fault else 0)
                return super().read(offset)
            def write(inner, offset, value):
                super().write(offset, value)
                if offset == 0x28:
                    if inner.first_park_reads is None: inner.first_park_reads = inner.status_reads
                    inner.values[0x28] = value | (((value >> 8) & 31) << 24)
        sensor = types.SimpleNamespace(running=False)
        sensor.start = lambda: setattr(sensor, 'running', True)
        sensor.stop = lambda: setattr(sensor, 'running', False)
        class Csi(LegacyCsi):
            def __init__(inner): inner.packets = 0
            def reset_enable(inner): inner.packets = 0
            def snapshot(inner):
                if sensor.running: inner.packets += 1440
                return dict(control=2,long_packets=inner.packets,crc_errors=0,version=0x10001)
        regs = CaptureRegisters()
        buffers = [types.SimpleNamespace(nbytes=SPAN,device_address=0x10000000+i*SPAN) for i in range(3)]
        capture = capture_class()(AxiVdma(regs), Csi(), sensor, buffers)
        return capture, regs

    def test_v14_startup_proves_three_starts_before_first_park(self):
        capture, regs = self.capture_fixture()
        receipt = capture.acquire()
        self.assertGreaterEqual(regs.first_park_reads, 7)
        self.assertEqual(receipt['sequence'], 1)
        self.assertEqual((receipt['slot'],receipt['writer']), (0,1))
        self.assertGreater(receipt['captured_ms'], 0)
        capture.acknowledge()

    def test_circular_fault_with_zero_crc_never_grants_frame(self):
        capture, regs = self.capture_fixture(fault=True)
        with self.assertRaises(RuntimeError) as error: capture.acquire()
        self.assertEqual(error.exception.snapshot['error_mask'], 0x90)
        self.assertIsNone(regs.first_park_reads)
        self.assertIsNone(capture.held)

    def test_startup_packet_window_below720_does_not_park_or_grant(self):
        capture, regs = self.capture_fixture()
        capture.csi.validate_window = lambda before, after: dict(packet_delta=719,crc_delta=0)
        with self.assertRaises(RuntimeError): capture.acquire()
        self.assertIsNone(regs.first_park_reads)
        self.assertIsNone(capture.held)

    def test_old_boot_or_mixed_receipt_rejected(self):
        record = dict(bit_sha256='a', hwh_sha256='b', ps_reference_hz=33333333)
        receipt = dict(schema='beam-pynq-mmio-admission-v1', boot_id='current',
            bit_sha256='a', hwh_sha256='b', ps_reference_hz=33333333,
            evidence_path='round.log', evidence_sha256='c'*64)
        self.assertEqual(validate_receipt(receipt, 'current', record), receipt)
        with self.assertRaises(RuntimeError): validate_receipt(receipt, 'other-boot', record)
        with self.assertRaises(RuntimeError): validate_receipt(dict(qualified=True), 'current', record)

    def test_csi11_only_uses_four_actual_csrs(self):
        io = Registers()
        io.values.update({0: 2, 4: 1440, 8: 0, 12: 0x10001})
        csi = LegacyCsi(io)
        self.assertFalse(csi.snapshot()['coherent'])
        self.assertEqual({item[1] for item in io.history}, {0, 4, 8, 12})
        self.assertFalse(any(item[0] == 'write' for item in io.history))
        io.values[12] = 0x10002
        with self.assertRaises(RuntimeError): csi.snapshot()

    def test_sensor_tables_include_all_c_integer_expressions(self):
        path = ROOT / 'color_test/software/vision_ps_baremetal/tools/prepare_beam_hardware.py'
        spec = importlib.util.spec_from_file_location('beam_hw_generator_test', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        source = (ROOT / 'color_test/software/vision_ps_baremetal/src/ov5640.c').read_text()
        pairs = module.sensor_table(source, 'cfg_720p_60fps')
        self.assertEqual(len(pairs), 38)
        self.assertEqual([dict(pairs)[x] for x in (0x3808,0x3809,0x380a,0x380b)], [5,0,2,208])
        self.assertEqual(dict(pairs)[0x380c] * 256 + dict(pairs)[0x380d], 1896)
        with self.assertRaises(ValueError):
            module.sensor_table('int sample[]={ {1, function()}, {SEQUENCE_END,0} };', 'sample')

    def test_failed_allocation_retains_without_free_or_retry(self):
        calls = []
        def ioctl(*args): calls.append(args[1]); raise OSError('injected copy_to_user failure')
        fake = types.SimpleNamespace(ioctl=ioctl)
        buffer = XlnkBuffer(lambda: True, lambda: 0)
        with patch.dict(sys.modules, fcntl=fake), patch('os.open', return_value=81), \
                patch.object(os, 'O_CLOEXEC', 0x80000, create=True):
            with self.assertRaises(OSError): buffer.allocate()
            with self.assertRaises(RuntimeError): buffer.close()
        self.assertEqual(calls, [0xc0045802])
        self.assertFalse(buffer.can_exit())

    def test_buffer_release_requires_halt_and_uncertain_free_is_not_retried(self):
        calls = []
        halted = [True]
        def ioctl(fd, operation, argument, mutate):
            calls.append(operation)
            if operation == 0xc0045802:
                struct.pack_into('<IIII', argument, 0, 3*SPAN, 7, 0x10000000, 0)
                return 0
            raise OSError('injected uncertain free')
        class Mapping(bytearray):
            def close(inner): pass
        buffer = XlnkBuffer(lambda: halted[0], lambda: 0)
        with patch.dict(sys.modules, fcntl=types.SimpleNamespace(ioctl=ioctl)), \
                patch('os.open', return_value=81), patch('mmap.mmap', return_value=Mapping(3*SPAN)), \
                patch.object(os, 'O_CLOEXEC', 0x80000, create=True), \
                patch.multiple('mmap', MAP_SHARED=1, PROT_READ=1, PROT_WRITE=2, create=True):
            buffer.allocate()
            halted[0] = False
            with self.assertRaises(RuntimeError): buffer.close()
            self.assertEqual(calls, [0xc0045802])
            halted[0] = True
            with self.assertRaises(OSError): buffer.close()
            with self.assertRaises(RuntimeError): buffer.close()
        self.assertEqual(calls, [0xc0045802, 0xc0045803])


@unittest.skipUnless(HOST and BUNDLE, 'set host library and hardware bundle paths')
class DisplayCallbackTests(unittest.TestCase):
    def setUp(self):
        bundle = Path(BUNDLE)
        self.owner = PynqOwner(bundle/'hardware.json', bundle/'system_wrapper.bit',
            bundle/'libbeam_pynq.so', '/never/read/in/host/fixture', '/dev/i2c-FAKE')
        self.owner.lib = load_library(HOST)
        self.owner._bind_display()
        self.clock = 1000
        def now(context, output): self.clock += 1; output[0] = self.clock; return 0
        self.owner.lib.beam_pynq_clock_ms = now  # explicit CPU fixture only
        self.dma, self.clk, self.vtc = Registers(dma=True), Registers(clock=True), Registers()
        self.owner.mmio = {'axi_vdma_0': self.dma, 'axi_dynclk_0': self.clk}
        self.owner.qualified, self.owner.lock_fd = True, 123  # model, no real fd
        self.owner.timing = DisplayTiming(self.clk, self.vtc, lambda: self.owner._halted(False))
        self.owner.display = self.owner.lib.beam_pynq_display_new()
        self.owner.platform = self.owner._display_platform()
        FakeAllocation.releases = []
        self.allocator_patch = patch('pynq_vision.beam_hardware.XlnkBuffer', FakeAllocation)
        self.allocator_patch.start()

    def tearDown(self):
        self.owner.lib.beam_pynq_display_stop(self.owner.display)
        self.owner.lib.beam_pynq_display_free(self.owner.display)
        self.allocator_patch.stop()

    def test_actual_c_display_callbacks_submit_and_retire_two_fresh_starts(self):
        owner = self.owner
        self.assertEqual(owner.lib.beam_pynq_display_prepare(owner.display, C.byref(owner.platform)), 0,
                         repr(owner.callback_error))
        canvas = bytes([42]) * FRAME_BYTES
        owner.submit_cpu(canvas, types.SimpleNamespace(ticket=9))
        with self.assertRaises(RuntimeError): owner.display_retired(10)
        completed = False
        for _ in range(12):
            if owner.display_retired(9): completed = True; break
        self.assertTrue(completed)
        clears = [v for op, *v in self.dma.history if op == 'write' and v[0] == 4]
        self.assertGreaterEqual(len(clears), 2)
        self.assertEqual(FakeAllocation.releases, [])
        self.assertEqual(owner.lib.beam_pynq_display_stop(owner.display), 0)
        self.assertEqual(FakeAllocation.releases, ['halted_release'])

    def test_mixed_bundle_hash_rejected_before_pynq_import(self):
        bundle = Path(BUNDLE)
        with self.assertRaises(RuntimeError):
            inspect_bundle(bundle/'hardware.json', bundle/'system_wrapper.bit', HOST)

    def test_non_arm_prepare_rejects_before_any_device_open(self):
        bundle = Path(BUNDLE)
        owner = PynqOwner(bundle/'hardware.json', bundle/'system_wrapper.bit',
            bundle/'libbeam_pynq.so', '/never/read/in/host/fixture', '/dev/i2c-FAKE')
        with patch('pynq_vision.beam_admission.platform.machine', return_value='x86_64'), \
                patch('os.open', side_effect=AssertionError('unexpected device open')):
            with self.assertRaises(RuntimeError): owner.prepare()
        self.assertTrue(owner.can_exit())

    def test_display_callback_exception_returns_error_not_implicit_success(self):
        self.owner.qualified = False
        code = self.owner.lib.beam_pynq_display_prepare(self.owner.display, C.byref(self.owner.platform))
        self.assertEqual(code, 3)  # GAME_DISPLAY_UNQUALIFIED
        self.assertIsNotNone(self.owner.callback_error)
        original_error, original_fault = self.owner.callback_error, self.owner.first_fault
        def cleanup_failure(): raise RuntimeError('later cleanup fault')
        self.assertEqual(self.owner._guard(cleanup_failure)(), -1)
        self.assertIs(self.owner.callback_error, original_error)
        self.assertIs(self.owner.first_fault, original_fault)


if __name__ == '__main__': unittest.main()
