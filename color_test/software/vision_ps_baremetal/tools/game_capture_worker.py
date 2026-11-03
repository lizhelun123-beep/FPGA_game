"""Single live-game sensor/VDMA worker; C owns all image allocations.

Staged as capture_worker.py by the existing live bundle builder. No Overlay,
libcma, second detector, image files, or independent capture allocation.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import sys
import time
from types import SimpleNamespace


def commands(fd, stopping):
    """Unbuffered pipe parser: coalesced ACK/START must not strand a line."""
    pending = bytearray()
    while not stopping[0]:
        if b'\n' in pending:
            line, _, rest = pending.partition(b'\n')
            if len(line) > 128:
                raise RuntimeError('oversized capture command')
            pending[:] = rest
            yield line.decode('ascii').strip()
            continue
        if len(pending) > 128:
            raise RuntimeError('oversized capture command')
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            yield None
            continue
        data = os.read(fd, 4096)
        if not data:
            if pending:
                raise RuntimeError('truncated capture command')
            return
        pending.extend(data)


class EvidenceSink:
    """First-write evidence in this round's existing root-owned capture tree."""
    def __init__(self, root, boot_id, filename):
        self.path = Path(root) / filename
        self.boot_id = boot_id

    def exists(self):
        # A symlink, including a broken one, is an existing record, never a
        # license to follow it or replace the retained evidence.
        return os.path.lexists(str(self.path))

    def __call__(self, record):
        evidence = dict(record)
        evidence.update(boot_id=self.boot_id, monotonic=time.monotonic())
        data = json.dumps(evidence, sort_keys=True, indent=2) + '\n'
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
                fd = None
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        finally:
            if fd is not None:
                os.close(fd)
        return str(self.path)


def _preserve_existing(sink, record, field):
    check = getattr(sink, 'exists', None)
    if not callable(check):
        return False
    try:
        if not check():
            return False
        record[field + '_preserved'] = str(getattr(sink, 'path', 'existing evidence'))
    except BaseException as exc:
        record[field + '_check_failure'] = type(exc).__name__ + ': ' + str(exc)
        # Uncertain file identity must not trigger a new freeze/write attempt.
    return True


def _save_evidence(sink, record, field):
    if sink is None or _preserve_existing(sink, record, field):
        return
    try:
        path = sink(record)
        if path is not None:
            record[field] = str(path)
    except BaseException as exc:
        record[field + '_failure'] = type(exc).__name__ + ': ' + str(exc)


def _emit_evidence(diagnostics, prefix, record):
    try:
        diagnostics.write(prefix + json.dumps(record, sort_keys=True) + '\n')
        diagnostics.flush()
    except BaseException:
        # A broken diagnostic channel must not replace the capture fault or
        # change the original shutdown path. The exclusive evidence file may
        # already contain the complete record.
        pass


def capture_boundary_final(observer, diagnostics, final_sink, fault_sink):
    """Freeze once on normal worker return, before any cleanup changes state."""
    record = {'operation': 'passive_observer_final',
              'source': 'normal_worker_return_before_cleanup', 'first_sample': None}
    if _preserve_existing(final_sink, record, 'boundary_final_file'):
        _emit_evidence(diagnostics, 'LIVE_BOUNDARY_FINAL ', record)
        return record
    if _preserve_existing(fault_sink, record, 'first_fault_file'):
        record['boundary_snapshot_skipped'] = 'first fault evidence is already retained'
    else:
        record['boundary_freeze_requested_monotonic_s'] = time.monotonic()
        try:
            record['boundary_snapshot'] = observer.freeze()
            snapshot = record['boundary_snapshot']
            if (snapshot.get('frozen') and snapshot.get('first_reason', 0) and
                    snapshot.get('freeze_origin') == 'first_observer_fault'):
                # A passive geometry fault can precede a software/DMA error.
                # Preserve it without inventing a VDMA register sample.
                _save_evidence(fault_sink, record, 'first_fault_file')
        except BaseException as exc:
            record['boundary_snapshot_failure'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            record['boundary_snapshot_completed_monotonic_s'] = time.monotonic()
    _save_evidence(final_sink, record, 'boundary_final_file')
    _emit_evidence(diagnostics, 'LIVE_BOUNDARY_FINAL ', record)
    return record


def serve(session, incoming, output, diagnostics, observer=None, fault_sink=None):
    def checked(operation, call):
        try:
            return call()
        except RuntimeError as exc:
            # Preserve the driver's original register sample. New1.3 hardware
            # adds a passive snapshot before sensor/drain/DMA-stop cleanup;
            # observing it never acknowledges or clears the original DMA fault.
            fault = {
                'operation': operation, 'stage': session.stage,
                'next_sequence': session.sequence + 1,
                'writer_before_lease': session.writer, 'held': session.held,
                # This may be the initial, not-yet-validated baseline.
                'previous_csi': session.previous,
                'first_sample': getattr(exc, 'snapshot', None),
                'error': str(exc)}
            preserved = _preserve_existing(fault_sink, fault, 'first_fault_file')
            if observer is not None and not preserved:
                fault['boundary_freeze_requested_monotonic_s'] = time.monotonic()
                try:
                    fault['boundary_snapshot'] = observer.freeze()
                except BaseException as observation_error:
                    # Observation failure must not replace the triggering fault.
                    fault['boundary_snapshot_failure'] = (
                        type(observation_error).__name__ + ': ' + str(observation_error))
                finally:
                    fault['boundary_snapshot_completed_monotonic_s'] = time.monotonic()
            elif preserved:
                fault['boundary_snapshot_skipped'] = 'first fault evidence is already retained'
            if not preserved:
                _save_evidence(fault_sink, fault, 'first_fault_file')
            _emit_evidence(diagnostics, 'LIVE_CAPTURE_FIRST_FAULT ', fault)
            raise

    for command in incoming:
        checked('poll', session.poll)
        if command is None:
            continue
        if command == 'STOP':
            return
        if command == 'FRAME_DONE':
            checked('acknowledge', session.acknowledge)
        elif command == 'START':
            frame = checked('acquire', session.acquire)
            diagnostics.write('LIVE_CSI sequence=%d packets=%d crc_errors=%d control=0x%08x slot=%d writer=%d\n' % (
                frame['sequence'], frame['health']['packet_delta'], frame['health']['crc_delta'],
                frame['csi']['control'], frame['slot'], frame['writer']))
            diagnostics.flush()
            output.write('FRAME %d %d %d %d\n' % (
                frame['sequence'], frame['captured_ms'], frame['slot'], frame['writer']))
            output.flush()
        else:
            raise RuntimeError('unexpected capture command: ' + repr(command))


def module(name, source):
    spec = importlib.util.spec_from_file_location(name, str(source))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-bridge', required=True, action='store_true')
    parser.add_argument('--bridge-physical', type=int, required=True)
    parser.add_argument('--bridge-span', type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    package = json.loads((root / 'capture_package.json').read_text())
    source = Path(package['production_directory'])
    if (args.bridge_span != 5760 * 720 or args.bridge_physical <= 0 or
            args.bridge_physical & 4095 or
            args.bridge_physical + 3 * args.bridge_span > 0x40000000):
        raise RuntimeError('invalid C-owned capture allocation')
    if os.geteuid() != 0:
        raise RuntimeError('capture coordinator requires its admitted root owner')
    from pynq_vision.hardware import CsiReceiver
    from pynq_vision.live_capture import ContinuousCapture
    from pynq_vision.ov5640 import LinuxI2C, OV5640, RAW10_EXPECTED
    from pynq_vision.vdma import AxiVdma, HALTED, RUNSTOP, ERRORS, S2MM_CONTROL

    native = module('bridge_native', source / 'dphy_observer.py')
    gpio = Path('/sys/class/gpio/gpio960')
    if not gpio.is_dir() or (gpio / 'direction').read_text().strip() != 'out':
        raise RuntimeError('camera reset ownership missing')
    regions = []
    bus = dma = csi = session = observer = None
    stopping = [False]
    def stop_requested(signum, frame):
        stopping[0] = True
    def own(base):
        region = native.NativeRegion(base, True, library=source / 'libdphy_observer_mmio.so')
        regions.append(region)
        return SimpleNamespace(read=region.read, write=region.store)
    signal.signal(signal.SIGINT, stop_requested)
    signal.signal(signal.SIGTERM, stop_requested)
    try:
        dma = AxiVdma(own(0x43000000))
        if not dma.status(True) & HALTED or dma.status(True) & ERRORS:
            raise RuntimeError('capture channel is not initially halted and healthy')
        (gpio / 'value').write_text('0')
        csi = CsiReceiver(own(0x43c30000))
        csi.regs.write(0, 0)
        own(0x43c40000).write(0, 3)
        (gpio / 'value').write_text('1')
        time.sleep(1)
        bus = LinuxI2C('/dev/i2c-0').open()
        sensor = OV5640(bus)
        sensor.configure_raw10_720p()
        bus.write_register(0x3035, 0x61)
        bus.write_register(0x4837, 0x6c)
        expected = dict(RAW10_EXPECTED)
        expected.update({0x3035: 0x61, 0x4837: 0x6c, 0x3008: 0x42})
        if {r: bus.read_register(r) for r in expected} != expected:
            raise RuntimeError('fixed RAW10 sensor mode readback mismatch')
        version = csi.regs.read(0x0C)
        if version == 0x00010003:
            # Legacy1.2 capture bundles do not need to carry the new reader.
            from pynq_vision.boundary_observer import BoundaryObserver
            observer = BoundaryObserver(csi.regs)
            armed = observer.arm()
            sys.stderr.write('LIVE_BOUNDARY_ARMED arm_sequence={} snapshot_sequence={}\n'.format(
                armed['arm_sequence'], armed['snapshot_sequence']))
            sys.stderr.flush()
        elif version == 0x00010002:
            sys.stderr.write('LIVE_BOUNDARY_UNSUPPORTED version=0x00010002\n')
            sys.stderr.flush()
        else:
            raise RuntimeError('unsupported CSI snapshot version 0x{:08x}'.format(version))
        buffers = [SimpleNamespace(device_address=args.bridge_physical + i * args.bridge_span,
                                   nbytes=args.bridge_span) for i in range(3)]
        session = ContinuousCapture(dma, csi, sensor, buffers)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        fault_sink = EvidenceSink(root, boot, 'first_fault.json')
        final_sink = EvidenceSink(root, boot, 'boundary_final.json')
        sys.stdout.write('BRIDGE_READY ' + boot + ' CONTINUOUS_PARK_V1\n')
        sys.stdout.flush()
        serve(session, commands(sys.stdin.fileno(), stopping), sys.stdout, sys.stderr,
              observer, fault_sink)
        if observer is not None:
            capture_boundary_final(observer, sys.stderr, final_sink, fault_sink)
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            # Keep mappings and all clocks alive on uncertain halt. The C
            # parent waits for us and retains its allocation; no global reset.
            if dma is not None:
                warned = False
                while not dma.status(True) & HALTED or dma.regs.read(S2MM_CONTROL) & RUNSTOP:
                    if not warned:
                        sys.stderr.write('CAPTURE_RETAINED: waiting for actual RS0/HALTED; no reset/free\n')
                        sys.stderr.flush()
                        warned = True
                    time.sleep(0.1)
            if csi is not None:
                csi.regs.write(0, 0)
            (gpio / 'value').write_text('0')
            if bus is not None:
                bus.close()
            for region in reversed(regions):
                region.close()


if __name__ == '__main__':
    main()
