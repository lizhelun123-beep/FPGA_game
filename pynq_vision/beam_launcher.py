"""Shared foreground/notebook runner for the PYNQ board, never a web server."""
import argparse
import json
from pathlib import Path
import signal
import statistics
import time

from .beam_admission import inspect_bundle
from .beam_runtime import Beam, SerialPort, drain_owner, run


class Session:
    def __init__(self, manifest, overlay, library, uart, i2c_device,
                 admission='/run/beam_pynq/admission.json'):
        self.arguments = dict(manifest=manifest, overlay=overlay, library=library,
                              admission=admission, i2c_device=i2c_device)
        self.uart_path = uart
        self.stopping = False
        self.owner = None

    def inspect(self):
        record = inspect_bundle(self.arguments['manifest'], self.arguments['overlay'], self.arguments['library'])
        return dict(version=record['version'], csi_version=record['csi_version'],
                    frame=record['frame'], bit_sha256=record['bit_sha256'],
                    library_sha256=record['library_sha256'], hardware_operations=0)

    def request_stop(self, *unused):
        self.stopping = True

    def run(self, max_frames=0, teaching_mouse=None):
        if type(max_frames) is not int or max_frames < 0:
            raise ValueError('max_frames must be a nonnegative integer')
        if (not isinstance(self.uart_path, str) or not self.uart_path.startswith('/dev/') or
                not isinstance(self.arguments['i2c_device'], str) or
                not self.arguments['i2c_device'].startswith('/dev/i2c-')):
            raise ValueError('explicit UART and I2C device paths required before hardware preparation')
        if self.owner is not None and not self.owner.can_exit():
            raise RuntimeError('previous hardware owner retained')
        from .beam_hardware import PynqOwner
        self.owner = PynqOwner(uart_path=self.uart_path, **self.arguments)
        beam = uart = teaching = None
        self.stopping = False
        stage = 'prepare'
        try:
            self.owner.prepare()
            beam = Beam(self.arguments['library'], self.owner.generation)
            uart = SerialPort(self.arguments['library'], self.uart_path)
            if teaching_mouse is not None:
                from .teaching_mouse import LinuxMouse
                from .teaching_mode import TeachingSession
                teaching = TeachingSession(LinuxMouse(teaching_mouse))
            stage = 'runtime'
            run(self.owner, beam, uart, lambda: self.stopping or
                bool(max_frames and self.owner.metrics['frames'] >= max_frames), teaching=teaching)
        except BaseException as error:
            if self.owner.first_fault is None:
                self.owner.first_fault = dict(stage=stage, error=repr(error),
                                              sample=getattr(error, 'snapshot', None))
            raise
        finally:
            try:
                if teaching is not None: teaching.close()
            finally:
                drain_owner(self.owner)
                try:
                    if uart is not None: uart.close()
                finally:
                    if beam is not None: beam.close()
        return self.report()

    def report(self):
        if self.owner is None:
            return dict(status='NOT_RUN')
        report = dict(frames=self.owner.metrics['frames'], can_exit=self.owner.can_exit(),
                      window='last up to 256 actual samples; milliseconds', stages={},
                      first_fault=self.owner.first_fault)
        for name, values in self.owner.metrics.items():
            if name != 'frames' and values:
                ordered = sorted(values)
                report['stages'][name] = dict(samples=len(ordered), mean=statistics.mean(ordered),
                    median=statistics.median(ordered), maximum=max(ordered))
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--inspect', action='store_true', help='file hashes only; no PYNQ import/device')
    action.add_argument('--run', action='store_true', help='actual board operation; current-boot admission required')
    parser.add_argument('--uart', help='explicit board UART; no console/service changes')
    parser.add_argument('--i2c-device', help='explicit PS I2C0 device')
    parser.add_argument('--admission', default='/run/beam_pynq/admission.json')
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--teaching-mouse', help='enable teaching with one explicit /dev/input/event* mouse')
    args = parser.parse_args(argv)
    if args.run and (not args.uart or not args.i2c_device):
        parser.error('--run needs explicit --uart and --i2c-device')
    session = Session(args.manifest, args.overlay, args.library, args.uart,
                      args.i2c_device, args.admission)
    if args.inspect:
        print(json.dumps(session.inspect()))
        return
    previous = {sig: signal.signal(sig, session.request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        print(json.dumps(session.run(args.frames, teaching_mouse=args.teaching_mouse)))
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)


if __name__ == '__main__': main()
