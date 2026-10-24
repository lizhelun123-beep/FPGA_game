"""One fixed lower-rate measurement using the retained diagnostic loader.

No DMA, raw sampling, phase scan, production build or BOOT change. The original
control load/word-access gates run before the single bounded sensor stream.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path


def measure_frequency_board():
    import fcntl
    import importlib.util
    import multiprocessing
    import time
    from functools import partial
    from pathlib import Path

    root = Path(__file__).resolve().parent
    config = json.loads((root / 'config.json').read_text())
    control = json.loads((root / 'control_receipt.json').read_text())
    result = dict(control)
    result.update(status='FREQUENCY_PENDING', pass_in_frequency=False,
                  stream_starts=0, frequency_only=True, DMA_operations=0,
                  phase_scans=0, stream_seconds_limit=2, sensor_changes={'0x3035': 0x61, '0x4837': 0x6c})

    def save(name, value):
        temporary = root / (name + '.pending')
        with temporary.open('w') as file:
            json.dump(value, file, sort_keys=True, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(str(temporary), str(root / name))

    if not control['pass']:
        result.update(status='STOP_CONTROL_GATE', **{'pass': False})
        save('frequency_receipt.json', result)
        return

    def module(name, filename):
        spec = importlib.util.spec_from_file_location(name, str(root / filename))
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value

    gpio = Path('/sys/class/gpio/gpio960')
    Region = partial(NativeRegion, library=root / 'libdphy_observer_mmio.so')
    support = module('frequency_support', 'environment_support.py')
    support.Registers = Region
    context = multiprocessing.get_context('fork')
    stopped = context.Event()

    def reset_guard(start):
        fired = not stopped.wait(max(0, start + 1.25 - time.monotonic()))
        if fired:
            (gpio / 'value').write_text('0')
        save('frequency_guard.json', {'fired': fired, 'monotonic': time.monotonic(),
                                     'GPIO960': (gpio / 'value').read_text().strip()})

    def sample():
        data = {'pass': False, 'samples': []}
        regs = None
        try:
            regs = Region(0x43c00000, False)
            assert regs.read(0) == 0x44504859 and regs.read(4) == 0x10002
            assert regs.read(0x24) == 0, 'Raw observer must remain disabled'
            window = regs.read(0x1c)
            assert window == 100000
            for unused in range(8):
                time.sleep(0.025)
                data['samples'].append({'count': regs.read(0x18),
                                        'monotonic': time.monotonic()})
            data.update(window_cycles=window, final_status=regs.read(8),
                        observation_enable=regs.read(0x24), actual_taps=regs.read(12))
            assert data['observation_enable'] == 0 and data['actual_taps'] == 396
            assert data['final_status'] & 1
            data['pass'] = True
        except BaseException as exc:
            data['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            if regs is not None:
                regs.close()
            save('frequency_samples.json', data)

    lock = None
    bus = None
    sensor = None
    guard = None
    worker = None
    stream_start = None
    reset_release = None
    result['pass'] = False
    try:
        assert os.geteuid() == 0
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == config['boot_id']
        lock = open('/run/lock/codex_camera_environment.lock', 'a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        support.assert_no_active_owner(support.owners())
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating'
        assert (gpio / 'direction').read_text().strip() == 'out'
        assert (gpio / 'value').read_text().strip() == '0'
        assert os.path.realpath('/sys/class/i2c-adapter/i2c-0/device/of_node').endswith('/i2c@e0004000')
        assert not Path('/sys/bus/i2c/devices/0-003c/driver').exists()
        ps = support.ps_snapshot()
        reference = [int(line.split()[4]) for line in support.clock_summary() if line.split()[0] == 'ps_clk']
        assert reference == [33333333]
        rates = support.clock_rates(ps, reference[0])
        assert abs(rates[0] - 100) < 0.01 and abs(rates[2] - 200) < 0.01
        assert ps['0xf8000240'] == 0 and ps['0xf8000900'] & 15 == 15
        result.update(clock_mhz=rates, reference_hz=rates[0] * 1000000,
                      physical_reference_tolerance='UNKNOWN; nominal PS register-derived reference')
        sensor_module = module('frequency_sensor', 'ov5640.py')
        bus = sensor_module.LinuxI2C('/dev/i2c-0').open()
        sensor = sensor_module.OV5640(bus)
        reset_release = time.monotonic()
        (gpio / 'value').write_text('1')
        time.sleep(0.02)
        bus.write_register(0x3008, 0x42)
        sensor.configure_raw10_720p()
        bus.write_register(0x3035, 0x61)
        bus.write_register(0x4837, 0x6c)
        expected = dict(sensor_module.SENSOR_INIT + sensor_module.MODE_720P_RAW10)
        expected.update({0x3008: 0x42, 0x3035: 0x61, 0x4837: 0x6c})
        fields = (0x3008, 0x3034, 0x3035, 0x3036, 0x3037, 0x3108,
                  0x3808, 0x3809, 0x380a, 0x380b, 0x380c, 0x380d,
                  0x380e, 0x380f, 0x3820, 0x3821, 0x4300, 0x4800,
                  0x4837, 0x5000, 0x5001, 0x501f, 0x300e)
        actual = {address: bus.read_register(address) for address in fields}
        assert actual == {address: expected[address] for address in fields}, 'Fixed sensor readback differs'
        result['sensor_standby'] = {hex(address): value for address, value in actual.items()}
        result['stream_starts'] = 1
        save('frequency_receipt.json', result)
        stream_start = time.monotonic()
        guard = context.Process(target=reset_guard, args=(stream_start,))
        guard.start()
        sensor.start()
        worker = context.Process(target=sample)
        worker.start()
        worker.join(0.6)
        assert not worker.is_alive() and worker.exitcode == 0, 'Frequency worker timeout/fault'
        samples = json.loads((root / 'frequency_samples.json').read_text())
        result['samples'] = samples
        assert samples['pass'] and len(samples['samples']) == 8
        hz = [row['count'] * result['reference_hz'] / samples['window_cycles'] for row in samples['samples']]
        expected_hz = 93333333.33333333 / 8
        result.update(byte_hz=hz, lane_bps=[value * 8 for value in hz])
        assert all(abs(value / expected_hz - 1) <= 0.01 for value in hz), 'Measured rate outside fixed93.333Mb/s +/-1%'
        result['pass_in_frequency'] = True
    except BaseException as exc:
        result.update(status='STOP_FREQUENCY_GATE', error=type(exc).__name__ + ': ' + str(exc))
    finally:
        if bus is not None:
            try:
                bus.write_register(0x3008, 0x42)
                result['standby_final'] = bus.read_register(0x3008)
            except BaseException as exc:
                result['standby_error'] = repr(exc)
        if reset_release is not None:
            (gpio / 'value').write_text('0')
            low = time.monotonic()
            result['reset_release_to_low_s'] = low - reset_release
            if stream_start is not None:
                result['stream_window_s'] = low - stream_start
        stopped.set()
        if guard is not None:
            guard.join(0.5)
        if worker is not None and worker.is_alive():
            worker.terminate()
            worker.join(0.5)
            result['worker_timeout'] = True
        if bus is not None:
            bus.close()
        result['GPIO960'] = {name: (gpio / name).read_text().strip() for name in ['direction', 'value']}
        result['owners'] = support.owners()
        try:
            support.assert_no_active_owner(result['owners'])
        except BaseException as exc:
            result['owner_error'] = repr(exc)
        result['pass'] = bool(result['pass_in_frequency'] and result.get('standby_final') == 0x42
                              and result['GPIO960'] == {'direction': 'out', 'value': '0'}
                              and result.get('stream_window_s', 3) <= 2
                              and not any(key.endswith('_error') for key in result)
                              and not result.get('worker_timeout')
                              and (guard is None or not guard.is_alive()))
        result['status'] = 'PASS_FIXED_RATE_FREQUENCY_ONLY' if result['pass'] else 'STOP_FREQUENCY_GATE'
        if lock is not None:
            lock.close()
        save('frequency_receipt.json', result)
        print('FREQUENCY_RESULT_JSON ' + json.dumps({key: result.get(key) for key in
              ['status', 'pass', 'stream_starts', 'stream_window_s', 'lane_bps', 'GPIO960', 'error']}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'run', 'resume-sudo'])
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('retained_observer', project / 'tools/dphy_observer.py')
    retained = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = retained
    spec.loader.exec_module(retained)
    retained.OUT = retained.BASE / 'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/frequency_20261022'
    retained.OUT.mkdir(exist_ok=True)
    if args.stage == 'resume-sudo':
        attempt = retained.OUT / 'run_attempt.json'
        prior = json.loads(attempt.read_text())
        assert prior['status'] == 'HOST_STOPPED' and prior.get('loads_used') == 0
        assert prior.get('PL_control_writes_used') == 0
        assert prior['error'] == 'RuntimeError: Root/current-boot receiver guard failed before upload; no device work'
        raw = Path(prior['uart_log']).read_bytes()
        assert b'sudo: a password is required' in raw
        for name in ['run_attempt', 'authorization']:
            original = retained.OUT / (name + '.json')
            preserved = retained.OUT / (name + '.before_sudo.json')
            assert not preserved.exists(), 'Only one environmental retry'
            original.rename(preserved)
    assert not (retained.OUT / 'run_attempt.json').exists(), 'One attempt only;inspect retained failure'
    preflight = json.loads((project.parent / 'output/build/game_app/live_camera_1/preflight.resume1.json').read_text())
    assert preflight['status'] == 'PASS_READONLY_NOT_CAPTURE_QUALIFIED'
    derived = {'status': 'READY', 'boot_id': preflight['identity']['boot_id'],
               'stages': [preflight[key] for key in ['identity', 'ownership', 'ps_state']]}
    (retained.OUT / 'preflight.json').write_text(json.dumps(derived, indent=2) + '\n')
    authorization = retained.OUT / 'authorization.json'
    if authorization.exists():
        prior = json.loads(authorization.read_text())
        assert not prior['closed'] and prior['loads_used'] == 0
    else:
        authorization.write_text(json.dumps({'closed': False, 'loads_allowed': 1, 'loads_used': 0,
            'stream_starts_allowed': 1, 'stream_seconds_limit': 2, 'builds_allowed': 0,
            'source': '2026-10-22 explicit user package;reuse review confirmed;no scan/retry'}, indent=2) + '\n')
    retained.reload_control_run(args.stage == 'prepare', frequency_board=measure_frequency_board)


if __name__ == '__main__':
    main()
