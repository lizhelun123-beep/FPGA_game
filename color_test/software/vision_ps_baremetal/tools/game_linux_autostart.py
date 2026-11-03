"""Cold-boot orchestration of the canonical native C HDMI menu, build5 only.

No camera, photograph injection, BIT download or automatic error retry. Kernel,
BOOT, paired PL and ownership gates precede clock/reset/device initialization.
"""
from pathlib import Path
import fcntl
import importlib.util
import json
import os
import select
import signal
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parent
stopping = False


def request_stop(number, frame):
    global stopping
    stopping = True


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def open_display_lease(path='/run/lock/game_linux_display.lock'):
    # Match linux_acquire's 0600 contract even with systemd's default umask022.
    # Preserve the inode: replacing/unlinking a flock file permits two owners.
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
                st.st_uid != os.geteuid() or st.st_mode & 0o077):
            raise ValueError('Unsafe display lease; existing inode left unchanged')
        lease = os.fdopen(fd, 'r+')
    except BaseException:
        os.close(fd)
        raise
    return lease


def find_mouse():
    # Existing native evdev parser accepts relative mouse/left click, not touch.
    # Resolve enumeration at this boot instead of assuming event0 forever.
    deadline = time.monotonic() + 20
    while not stopping:
        for event in sorted(Path('/sys/class/input').glob('event*')):
            try:
                caps = event / 'device/capabilities'
                def bitmap(path):
                    # Linux prints one native unsigned-long word per token.
                    # On this ARM32 kernel each token is a separate 32-bit
                    # limb; concatenating the text loses the word positions.
                    value = 0
                    for index, token in enumerate(reversed(path.read_text().split())):
                        word = int(token, 16)
                        if word > 0xffffffff:
                            raise ValueError('input capability word exceeds ARM32')
                        value |= word << (32 * index)
                    return value
                rel = bitmap(caps / 'rel')
                keys = bitmap(caps / 'key')
                dev = Path('/dev/input') / event.name
                usb = (event / 'device/id/bustype').read_text().strip() == '0003'
                if usb and rel & 3 == 3 and keys & (1 << 272) and dev.is_char_device():
                    return str(dev)
            except OSError:
                continue
        if time.monotonic() >= deadline:
            raise RuntimeError('No relative USB mouse available; no hardware initialized')
        time.sleep(.2)
    raise RuntimeError('Stopped before initialization')


def main():
    assert os.geteuid() == 0 and str(ROOT) == '/run/game_single_image_720p/continuous'
    for path in (ROOT.parent, ROOT):
        st = path.lstat()
        assert stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022
    q = module('qualify', 'qualify.py')
    q.inspect_package(ROOT)
    q.protected(ROOT / 'boot_start.json', 4096)
    start = json.loads((ROOT / 'boot_start.json').read_text())
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert start['boot_id'] == boot_id and 0 <= time.monotonic() - start['monotonic'] <= 120
    assert start['FPGA_loads'] == 0 and q.sha(Path('/sys/kernel/notes')) == q.NOTES_SHA256
    assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating'
    assert not list(Path('/proc/device-tree/amba_pl').glob('*'))
    beam_mode = (ROOT / 'beam720').is_file()
    mouse = None if beam_mode else find_mouse()
    support = module('support', 'environment_support.py')
    native = module('words', 'dphy_observer.py')
    # Actual ARM/Python ABI proof on RAM BEFORE opening any MMIO mapping.
    native.WordAccess.ram_self_test(ROOT / 'libdphy_observer_mmio.so')

    def region(base, writable=False):
        return native.NativeRegion(base, writable, library=ROOT / 'libdphy_observer_mmio.so')

    support.Registers = region
    record = dict(status='PREPARING', boot_id=boot_id, FPGA_loads=0, camera_starts=0,
                  menu_runs=0, beam_runs=0, mouse=mouse, events=[])

    def event(name, **values):
        record['events'].append(dict(stage=name, monotonic=time.monotonic(), **values))
        (ROOT / 'autostart_receipt.json').write_text(json.dumps(record, indent=2) + '\n')
        print('RAY_GAME ' + name, flush=True)

    coord = lease = child = None
    clocks = False
    tail = ''

    def collect_output(timeout):
        nonlocal tail
        if child is not None and select.select([child.stdout], [], [], timeout)[0]:
            data = os.read(child.stdout.fileno(), 16384)
            if data:
                tail = (tail + data.decode('utf-8', errors='replace'))[-65536:]
                (ROOT / 'menu.log').write_text(tail)
                for line in data.decode('utf-8', errors='replace').splitlines():
                    if line.startswith(('BEAM_', 'LIVE_BOUNDARY_', 'FIXED720_QUALIFICATION_BLOCKED:',
                                         'LIVE_CAPTURE_FIRST_FAULT ')):
                        print(line, flush=True)
            return bool(data)
        return False

    try:
        coord = open('/run/lock/codex_display_single_image.lock', 'a')
        fcntl.flock(coord, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lease = open_display_lease()
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (ROOT / 'cold_boot.claim').open('x') as claim:
            claim.write(boot_id + '\n')
        support.assert_no_active_owner(support.owners())
        server = support.server_state()
        assert not server['bitfile'] and server['timestamp'] is None and not any(server['dictionary_sizes'])
        before = support.ps_snapshot()
        assert before['0xf800700c'] & 4 and before['0xf800010c'] & 4
        assert abs(support.clock_rates(before, 33333333)[0] - 100) < .001
        # Admit only pristine cold boot, not a hot restart or a prior DMA owner.
        summary = support.clock_summary()
        for name in ('fclk1', 'fclk2'):
            line = next(line for line in summary if line.split()[0] == name).split()
            assert line[1:3] == ['0', '0'], 'FCLK already active; cold boot required'
        hp = region(0xf8008000)
        try:
            assert hp.read(0) & 1 == 0
        finally:
            hp.close()
        chips = list(Path('/sys/class/gpio').glob('gpiochip*'))
        assert len(chips) == 1 and (chips[0] / 'base').read_text().strip() == '906'
        gpio = Path('/sys/class/gpio/gpio960')
        if not gpio.exists():
            Path('/sys/class/gpio/export').write_text('960')
        (gpio / 'direction').write_text('low')
        assert (gpio / 'value').read_text().strip() == '0'
        if stopping:
            raise RuntimeError('Stopped before clock initialization')
        event('cold_boot_ownership_sensor_isolation', PS=before)
        ps = region(0xf8000000, True)
        locked = bool(ps.read(0xc) & 1)
        try:
            if locked:
                ps.store(8, 0xdf0d)
                assert ps.read(0xc) & 1 == 0
            ps.write(0x240, ps.read(0x240) | 15)
            ps.write(0x900, (ps.read(0x900) & ~15) | 10)
            for control, divisor in ((0x180, 7), (0x190, 5)):
                ps.write(control + 8, ps.read(control + 8) | 1)
                ps.write(control, (ps.read(control) & ~0x03f03f30) | (1 << 20) | (divisor << 8))
                ps.write(control + 8, ps.read(control + 8) & ~1)
            time.sleep(.01)
            ps.write(0x900, (ps.read(0x900) & ~15) | 15)
            ps.write(0x240, ps.read(0x240) & ~15)
        finally:
            if locked:
                ps.store(4, 0x767b)
            ps.close()
        time.sleep(.05)
        after = support.ps_snapshot()
        rates = support.clock_rates(after, 33333333)
        assert all(abs(a - b) < .001 for a, b in zip(rates, (100, 1000 / 7, 200)))
        assert after['0xf8000240'] & 15 == 0 and after['0xf8000900'] & 15 == 15
        clocks = True
        event('PS_clock_transport_ready', PS=after, FCLK_MHz=rates)
        clk = region(0x43c00000, True)
        try:
            clk.write(0, 0)
            assert clk.read(4) & 3 == 0
            for i, value in enumerate((0x41, 0x69a, 0, 0x20c4, 0xcfafa401, 0x00a300ff)):
                clk.write(8 + 4 * i, value)
            clk.write(0, 1)
            deadline = time.monotonic() + .5
            while clk.read(4) & 3 != 3 and time.monotonic() < deadline:
                time.sleep(.001)
            assert clk.read(4) & 3 == 3
            time.sleep(.001)
            assert clk.read(4) & 3 == 3
        finally:
            clk.close()
        initial = {}
        # VTC access is forbidden until DISPLAY_READY is confirmed above.
        for name, base, offsets in [('display', 0x43010000, (0, 4)),
                                    ('capture', 0x43000000, (0x30, 0x34)),
                                    ('vtc', 0x43c10000, (0,))]:
            reg = region(base)
            try:
                initial[name] = [reg.read(x) for x in offsets]
            finally:
                reg.close()
        for name in ('display', 'capture'):
            cr, sr = initial[name]
            assert not cr & 1 and sr & 1 and not sr & 0x89f0
        assert not initial['vtc'][0] & 5
        live = dict(boot_id=boot_id, monotonic=time.monotonic(), FPGA_loads=0,
                    FCLK_MHz=rates, display_READY=3, capture_halted=True,
                    display_halted=True, initial=initial)
        (ROOT / 'load_receipt.json').write_text(json.dumps(live, indent=2) + '\n')
        q.check_live(ROOT)
        event('native_preparation_gate_pass', initial=initial)
        if stopping:
            raise RuntimeError('Stopped before native menu start')
        fcntl.flock(lease, fcntl.LOCK_UN)
        lease.close()
        lease = None
        if beam_mode:
            command = ['/usr/bin/python3', '-B', '-u', str(ROOT / 'beam_runtime.py'),
                       '--duration', '180']
            record['beam_runs'] = 1
        else:
            command = [str(ROOT / 'display.elf'), '--menu-service720', mouse,
                       str(ROOT / 'game_assets.bin')]
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        if not beam_mode:
            record['menu_runs'] = 1
        record['pid'] = child.pid
        event('beam_started' if beam_mode else 'native_menu_started')
        ready = sent_stop = False
        first_frame = False
        while child.poll() is None:
            collect_output(.25)
            ready_token = 'BEAM_HDMI_STARTED' if beam_mode else 'NATIVE_MENU_720_READY'
            if not ready and ready_token in tail:
                ready = True
                record['status'] = 'BEAM_READY' if beam_mode else 'MENU_READY_NOT_CAMERA_QUALIFIED'
                event('HDMI_beam_backend_ready' if beam_mode else 'HDMI_menu_backend_ready')
            if beam_mode and not first_frame and 'BEAM_FIRST_FRAME' in tail:
                first_frame = True
                event('beam_first_frame_submitted')
            if stopping and not sent_stop:
                child.send_signal(signal.SIGTERM)
                sent_stop = True
                event('graceful_stop_requested')
            # No timeout kill: an uncertain DMA owner must retain its memory.
        while collect_output(0):
            pass
        record['native_returncode'] = child.returncode
        if beam_mode:
            if not ready:
                raise RuntimeError('beam exited before HDMI backend ready')
            if not first_frame:
                raise RuntimeError('beam exited without submitting a first frame')
            if child.returncode != 0:
                raise RuntimeError('beam exited with status {}'.format(child.returncode))
            if ('BEAM_SAFE_STOP result=0' not in tail or
                    'owner_can_exit=1 capture_owner_can_exit=1 session_can_exit=1' not in tail):
                raise RuntimeError('beam exited without confirmed owner/session cleanup')
        else:
            assert ready and child.returncode == 0 and 'stop=0' in tail and 'owner_can_exit=1' in tail
        record['status'] = 'STOPPED_SAFE'
    except BaseException as exc:
        record.update(status='FAIL_STOP_NO_RETRY', error=type(exc).__name__ + ': ' + str(exc))
    finally:
        if lease:
            lease.close()
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            # Retain the supervisor as well until the native owner drains.
            while child.poll() is None:
                collect_output(.25)
        if clocks:
            try:
                support.assert_no_active_owner(support.owners())
                final = {}
                for name, base, offsets in [('display', 0x43010000, (0, 4)),
                                            ('capture', 0x43000000, (0x30, 0x34))]:
                    reg = region(base)
                    try:
                        final[name] = [reg.read(x) for x in offsets]
                    finally:
                        reg.close()
                    record['final_DMA'] = dict(final)
                    record['final_DMA_halted'] = {
                        channel: not (values[0] & 1) and bool(values[1] & 1)
                        for channel, values in final.items()}
                    record['final_DMA_error_masks'] = {
                        channel: values[1] & 0x89f0 for channel, values in final.items()}
                    cr, sr = final[name]
                    if cr & 1 or not sr & 1:
                        raise RuntimeError('{} final DMA halt unconfirmed: CR=0x{:08x} SR=0x{:08x}'.format(
                            name, cr, sr))
                    if sr & 0x89f0:
                        raise RuntimeError('{} DMA halted with retained error_mask=0x{:x}: CR=0x{:08x} SR=0x{:08x}'.format(
                            name, sr & 0x89f0, cr, sr))
                clk = region(0x43c00000, True)
                try:
                    clk.write(0, 0)
                    assert clk.read(4) & 3 == 0
                finally:
                    clk.close()
                record['final_DMA'] = final
                record['display_clock_stopped'] = True
            except BaseException as exc:
                halted = record.get('final_DMA_halted', {})
                errors = record.get('final_DMA_error_masks', {})
                # Preserve the existing error exit before further clock/MMIO
                # writes. Retained errors do not negate an observed RS0/HALTED.
                stopped_fault = (set(halted) == {'display', 'capture'} and
                                 all(halted.values()) and any(errors.values()))
                record.update(status='FAIL_DMA_ERROR_HALTED' if stopped_fault else
                              'FAIL_CLEANUP_UNCONFIRMED', cleanup_error=str(exc))
        event('exit', status=record['status'])
        if coord:
            coord.close()
    return 0 if record['status'] == 'STOPPED_SAFE' else 1


if __name__ == '__main__':
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    raise SystemExit(main())
