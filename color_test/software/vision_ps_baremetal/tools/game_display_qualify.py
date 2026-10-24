"""Read-only gate for the fixed single-image diagnostic; no PYNQ/device import.

Installed by this task under a root-owned /run directory only AFTER build/load
gates. No force option or caller-supplied pass flag. The game800 backend remains
closed. A receipt is meaningful only for its measured boot and temporary load.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
NOTES_SHA256 = '1314f84a71c899f3ddd1207bd97a4540047276a7c0899737bedfc99e4efa9762'
IMAGE_SHA256 = '4fe608a98915d8b5ad0c9e5f3bd477ebf08b9f35574e39da704143fb96ea4719'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def protected(path, maximum):
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and
            not s.st_mode & 0o022 and s.st_size <= maximum,
            'unprotected/oversize file: ' + str(path))


def verify_reset_contract(package, modules):
    """Pure metadata contract shared with offline tests; no resource access."""
    require(package['display_reset_contract'] == 'guard1_dual_psr13_aux16' and
            package['dynclk_status_mask'] == 3, 'unqualified display reset/status ABI')
    require(modules['axi_dynclk_0'].get('COREREVISION') == '4' and
            modules['axi_dynclk_0'].find(".//PORT[@NAME='DISPLAY_READY_O']") is not None,
            'old dynclk interface')
    for name in ('display_rst_axis', 'display_rst_pixel'):
        require(name in modules and modules[name].get('COREREVISION') == '13',
                'reset IP identity')
        parameters = {p.get('NAME'): p.get('VALUE') for p in modules[name].findall('.//PARAMETER')}
        require(parameters.get('C_AUX_RST_WIDTH') == '16' and
                parameters.get('C_AUX_RESET_HIGH') == '0' and
                parameters.get('C_EXT_RESET_HIGH') == '0', 'reset parameter contract')


def inspect_package(root):
    """Pure file audit. Hashes bind raw reports and paired export payloads."""
    protected(root / 'package.json', 1024 * 1024)
    package = json.loads((root / 'package.json').read_text())
    require(package['part'] == 'xc7z020clg400-2', 'wrong part')
    require(package['mode'] == 'fixed_control_720p_M52_D7_O2', 'wrong mode')
    require(package['capture_cells'] == [], 'capture still present')
    scope = package.get('software_scope', 'control_bmp720')
    require(scope in ('control_bmp720', 'menu720_stopped_update', 'menu720_continuous'), 'unknown software scope')
    if scope in ('menu720_stopped_update', 'menu720_continuous'):
        require(package.get('logical_canvas') == [1280, 800] and
                package.get('display_viewport') == [64, 0, 1152, 720] and
                package.get('camera_input') == 'isolated' and
                package.get('update_contract') == ('park_current_two_fresh_events' if scope == 'menu720_continuous' else 'halt_finish_copy_restart') and
                'game_assets.bin' in package['files'], 'menu720 scope contract')
    if package.get('input_mode') == 'reference_photo_C_detector':
        require(scope == 'menu720_continuous' and
                package.get('photo_layout') == [1280, 720, 3840] and
                package.get('photo_files') == ['075.bgr', '076.bgr', '077.bgr'] and
                'photos.json' in package['files'], 'photo input contract')
        for name in package['photo_files']:
            require(name in package['files'] and (root/name).stat().st_size == 2764800,
                    'photo size/identity: '+name)

    for name, digest in package['files'].items():
        require(Path(name).name == name and name not in ('.', '..'), 'unsafe filename')
        p = root / name
        protected(p, 64 * 1024 * 1024)
        require(sha(p) == digest, 'file identity: ' + name)
    for name in ['display.bit', 'display.hwh', 'display.xsa', 'display.elf',
                 'timing_summary.rpt', 'cdc.rpt', 'drc.rpt', 'qualify.py']:
        require(name in package['files'], 'missing evidence: ' + name)
    with zipfile.ZipFile(str(root / 'display.xsa')) as z:
        for suffix, name in [('.bit', 'display.bit'), ('.hwh', 'display.hwh')]:
            members = [n for n in z.namelist() if n.endswith(suffix)]
            require(len(members) == 1, 'ambiguous XSA payload')
            require(hashlib.sha256(z.read(members[0])).hexdigest() ==
                    package['files'][name], 'XSA payload mismatch')
    hwh = ET.parse(str(root / 'display.hwh')).getroot()
    modules = {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')}
    require('axi_vdma_0' in modules and 'axi_vdma_1' not in modules and
            not any('MIPI' in n for n in modules if n), 'HWH display partition')
    verify_reset_contract(package, modules)
    if scope == 'menu720_continuous':
        parameters = {p.get('NAME'): p.get('VALUE') for p in modules['axi_vdma_0'].findall('.//PARAMETER')}
        require(parameters.get('C_NUM_FSTORES') == '3' and parameters.get('C_USE_MM2S_FSYNC') == '0' and
                parameters.get('C_INCLUDE_MM2S') == '1' and parameters.get('C_INCLUDE_S2MM') == '0',
                'unreviewed free-run three-store VDMA configuration')
    ranges = {}
    for m in hwh.findall('.//MODULE'):
        for r in m.findall('.//MEMRANGE'):
            ranges[r.get('INSTANCE')] = (r.get('BASEVALUE'), r.get('HIGHVALUE'))
    for name, base in [('axi_vdma_0', 0x43010000), ('axi_dynclk_0', 0x43c00000),
                       ('vtg', 0x43c10000)]:
        require(name in ranges, 'missing HWH address ' + name)
        low, high = ranges[name]
        require(int(low, 0) == base and int(high, 0) == base + 0xffff,
                'wrong HWH address ' + name)
    # The host gate stores numeric observations AND hashes the original reports.
    # Requiring both prevents a filename/old PASS marker qualifying a new export.
    g = package['gate']
    require(all(g[k] >= 0 for k in ['WNS', 'TNS', 'WHS', 'THS']), 'negative timing')
    require(g['critical_cdc'] == 0 and g['drc_errors'] == 0 and
            g['unexplained_unconstrained'] == 0 and g['resource_gate'] and
            g['pins_gate'] and g['clock_reset_gate'], 'implementation gate')
    return package


def check_live(root=ROOT):
    s = root.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
            'unprotected task directory')
    package = inspect_package(root)
    protected(root / 'load_receipt.json', 1024 * 1024)
    live = json.loads((root / 'load_receipt.json').read_text())
    require(live['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'boot changed')
    require(0 <= time.monotonic() - live['monotonic'] <= 120, 'stale load/owner receipt')
    require(sha(Path('/sys/kernel/notes')) == NOTES_SHA256, 'unreviewed running kernel')
    require(live['bit_sha256'] == package['files']['display.bit'] and
            live['temporary_load_count'] == 1, 'wrong temporary load')
    require(live['fclk0_hz'] == 100000000 and live['fclk1_hz'] == 142857143,
            'clock readback not the fixed profile')
    require(live['hp0_enabled'] and live['fclk_reset_released'], 'PS transport not ready')
    gpio = Path(live['camera_gpio_value_path'])
    require(str(gpio).startswith('/sys/class/gpio/gpio') and gpio.name == 'value',
            'wrong camera isolation path')
    require(gpio.read_text().strip() == '0' and
            (gpio.parent / 'direction').read_text().strip() == 'out', 'camera not held reset')
    image = Path(live['image_path']).resolve()
    require(image.is_file() and sha(image) == IMAGE_SHA256, 'SD control-image identity')
    # The host's current-board preflight records the actual SD mount, not a
    # hard-coded /dev/root guess. Verify it remains mounted for this image.
    mount = live['sd_mount']
    matches = [v.split() for v in Path('/proc/mounts').read_text().splitlines()
               if v.split()[0] == mount['device'] and v.split()[1] == mount['path']]
    require(matches and (str(image) + '/').startswith(mount['path'].rstrip('/') + '/'),
            'control image not on the verified SD mount')
    require(mount['block_parent'] == 'mmcblk0', 'unverified SD device')
    if package.get('software_scope') in ('menu720_stopped_update', 'menu720_continuous'):
        asset = Path(live['assets_path']).resolve()
        protected(asset, 64 * 1024 * 1024)
        require(sha(asset) == package['files']['game_assets.bin'] and
                (str(asset) + '/').startswith(mount['path'].rstrip('/') + '/'),
                'resident game assets not on qualified SD mount')
    if package.get('input_mode') == 'reference_photo_C_detector':
        directory = Path(live['photos_path']).resolve()
        require((str(directory)+'/').startswith(mount['path'].rstrip('/')+'/'),
                'photo input not on qualified SD mount')
        for name in package['photo_files']:
            photo = directory/name
            protected(photo, 2764800)
            require(sha(photo) == package['files'][name], 'SD photo identity: '+name)

    check_owners([(0x43010000, 0x43020000), (0x43c00000, 0x43c20000)])
    print('FIXED720_QUALIFICATION_OK boot=' + live['boot_id'])


def check_owners(ranges):
    # Read-only current owner exclusion. Idle services are not stopped/changed.
    own = {os.getpid(), os.getppid()}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) in own:
            continue
        try:
            maps = (proc / 'maps').read_text()
            for line in maps.splitlines():
                fields = line.split()
                if len(fields) >= 6 and fields[-1] == '/dev/mem':
                    a, b = (int(x, 16) for x in fields[0].split('-'))
                    offset = int(fields[2], 16)
                    require(not any(offset < hi and offset + b - a > lo for lo, hi in ranges),
                            'competing video mapping PID ' + proc.name)
            for fd in (proc / 'fd').iterdir():
                try:
                    target = os.readlink(str(fd))
                except FileNotFoundError:
                    continue
                require(target != '/dev/xlnk', 'competing allocator owner PID ' + proc.name)
        except (FileNotFoundError, ProcessLookupError):
            continue


def check_capture_legacy(root=Path('/run/game_live_camera/capture')):
    """Current task's capture-only native allocation; never grants display."""
    s = root.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
            'unprotected capture directory')
    protected(root / 'capture_package.json', 1024 * 1024)
    package = json.loads((root / 'capture_package.json').read_text())
    require(package['scope'] in ('native_hardware_one_shot_720_capture_only',
                                'native_hardware_720_capture_only'), 'wrong capture scope')
    for name, digest in package['files'].items():
        rel = Path(name)
        require(not rel.is_absolute() and '..' not in rel.parts and
                (len(rel.parts) == 1 or (len(rel.parts) == 2 and rel.parts[0] == 'pynq_vision')),
                'unsafe capture filename')
        protected(root / name, 32 * 1024 * 1024)
        require(sha(root / name) == digest, 'capture file identity: ' + name)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    source = Path('/run/codex_live_camera_' + boot[:8])
    require(str(source) == package['production_directory'], 'wrong current production directory')
    for name in ('camera.bit', 'camera.hwh', 'artifacts.json', 'startup_receipt.json'):
        protected(source / name, 32 * 1024 * 1024)
    artifacts = json.loads((source / 'artifacts.json').read_text())
    startup = json.loads((source / 'startup_receipt.json').read_text())
    require(artifacts['status'] == 'PASS_PAIRED_ENGINEERING_ARTIFACTS_NOT_BOARD_QUALIFIED' and
            sha(source / 'camera.bit') == artifacts['sha256']['system_wrapper.bit'] and
            sha(source / 'camera.hwh') == artifacts['sha256']['system.hwh'], 'production pair changed')
    require(startup['status'] == 'PASS_PRODUCTION_STARTUP_NO_CAPTURE' and
            startup['production_loads'] == 1 and startup['boot_id'] == boot,
            'missing same-boot production startup')
    require(sha(source / 'startup_receipt.json') == package['startup_receipt_sha256'], 'startup evidence changed')
    require(sha(Path('/sys/kernel/notes')) == NOTES_SHA256, 'unreviewed running kernel')
    check_capture_admission(root, boot)


def check_capture_admission(root, boot):
    protected(root / 'capture_admission.json', 1024 * 1024)
    live = json.loads((root / 'capture_admission.json').read_text())
    require(live['boot_id'] == boot and 0 <= time.monotonic() - live['monotonic'] <= 120,
            'stale capture admission')
    require(live['S2MM_HALTED'] and live['S2MM_RS'] == 0 and live['S2MM_errors'] == 0 and
            live['display_READY'] == 0, 'capture/display not isolated at admission')
    require(live['HP1_write_control'] & 1 == 0, 'HP1 write channel is not64-bit')
    require(len(live['FCLK_MHz']) == 3 and all(abs(a-b) < .001 for a,b in
            zip(live['FCLK_MHz'], (100,1000/7,200))), 'wrong physical capture clocks')
    gpio = Path('/sys/class/gpio/gpio960')
    require((gpio / 'direction').read_text().strip() == 'out' and
            (gpio / 'value').read_text().strip() == '0', 'sensor not held reset before allocation')
    check_owners([(0x43000000,0x43020000),(0x43c00000,0x43c50000)])
    print('CAPTURE720_QUALIFICATION_OK boot=' + boot)


def check_capture(root=Path('/run/game_live_camera/capture')):
    """Keep legacy production admission; debug uses its own actual boot/load proof."""
    protected(root / 'capture_package.json', 1024 * 1024)
    package = json.loads((root / 'capture_package.json').read_text())
    production4=package['scope']=='native_hardware_720_camera_production4'
    production=package['scope'] in ('native_hardware_720_camera_production3','native_hardware_720_camera_production4')
    receiver=package['scope']=='native_hardware_720_receiver_fault_diagnostic'
    if not production and not receiver and package['scope'] != 'native_hardware_720_crc_upstream_diagnostic':
        return check_capture_legacy(root)
    state = root.lstat()
    require(stat.S_ISDIR(state.st_mode) and state.st_uid == 0 and not state.st_mode & 0o022,
            'unprotected diagnostic capture directory')
    for name, digest in package['files'].items():
        rel = Path(name)
        require(not rel.is_absolute() and '..' not in rel.parts and
                (len(rel.parts) == 1 or (len(rel.parts) == 2 and rel.parts[0] == 'pynq_vision')),
                'unsafe diagnostic capture filename')
        protected(root / rel, 32 * 1024 * 1024)
        require(sha(root / rel) == digest, 'diagnostic capture file identity: ' + name)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    source = Path(('/run/codex_rx_fault_' if receiver else '/run/codex_camera_prod4_' if production4 else '/run/codex_camera_prod3_' if production else '/run/codex_crc_upstream_') + boot[:8])
    require(str(source) == package['diagnostic_directory'], 'wrong diagnostic directory/boot')
    for name, digest in package['diagnostic_files'].items():
        require(Path(name).name == name, 'unsafe diagnostic evidence name')
        protected(source / name, 4 * 1024 * 1024)
        require(sha(source / name) == digest, 'diagnostic evidence changed: ' + name)
    gate = json.loads((source / 'gate.json').read_text())
    artifacts = json.loads((source / 'artifacts.json').read_text())
    program = json.loads((source / 'program_result.json').read_text())
    startup = json.loads((source / 'startup_receipt.json').read_text())
    require(gate['status'] == ('PASS_DECLARED_MODEL_ROUTED_GATES_ALLOW_ONE_EXPORT' if production else 'PASS_DIAGNOSTIC_ROUTED_GATES_ALLOW_ONE_BIT_LTX_EXPORT') and
            artifacts['part'] == 'xc7z020clg400-2', 'diagnostic top-level gate/part')
    require(program['status'] == 'PASS_ONE_JTAG_PROGRAM_DONE' and
            program['boot_id'] == boot and program['program_done'] == 1 and
            program['bit_sha256'] == artifacts['sha256']['receiver_fault.bit' if receiver else 'system_wrapper.bit' if production else 'upstream_fault.bit'] and
            (program['hwh_sha256'] == artifacts['sha256']['system.hwh'] if production else program['ltx_sha256'] == artifacts['sha256']['receiver_fault.ltx' if receiver else 'upstream_fault.ltx']),
            'missing actual same-boot JTAG program proof')
    if production4:
        require(artifacts['status']=='PASS_PAIRED_ENGINEERING_ARTIFACTS_NOT_BOARD_QUALIFIED' and
                sha(source/'camera.hwh')==artifacts['sha256']['system.hwh'] and
                package['production_directory']==str(source),
                'production4 paired export or HWH identity')
    require(startup['status'] == ('PASS_RECEIVER_FAULT_DIAGNOSTIC_STARTUP_NO_CAPTURE' if receiver else 'PASS_PRODUCTION_STARTUP_NO_CAPTURE' if production else 'PASS_UPSTREAM_DIAGNOSTIC_STARTUP_NO_CAPTURE') and
            startup['boot_id'] == boot and startup['temporary_loads'] == 1 and
            startup['explicit_streams'] == 0 and startup['DMA_arms'] == 0,
            'missing actual diagnostic startup;legacy production receipt is not a substitute')
    if receiver:
        implementation=json.loads((source/'implementation_claim.json').read_text())
        exported=json.loads((source/'export_claim.json').read_text())
        original=json.loads((source/'production_artifacts.json').read_text())
        original_gate=json.loads((source/'production_gate.json').read_text())
        require(implementation['authorization']['source_checkpoint']=='color_test/build/pl_rate93_production/build_3/synth/synthesized.dcp' and
                implementation['source_sha256']==artifacts['source_checkpoint_sha256'] and
                exported['gate_sha256']==sha(source/'gate.json') and exported['checkpoint_sha256']==gate['checkpoint_sha256'],
                'receiver diagnostic source/export provenance')
        require(original['status']=='PASS_PAIRED_ENGINEERING_ARTIFACTS_NOT_BOARD_QUALIFIED' and
                original_gate['status']=='PASS_DECLARED_MODEL_ROUTED_GATES_ALLOW_ONE_EXPORT' and
                sha(source/'camera.hwh')==artifacts['reference_HWH_sha256']==original['sha256']['system.hwh'],
                'receiver diagnostic HWH differs from production3 source platform')
    require(sha(Path('/sys/kernel/notes')) == NOTES_SHA256, 'unreviewed diagnostic kernel')
    check_capture_admission(root, boot)


if __name__ == '__main__':
    try:
        require(sys.argv[1:] == ['--qualify'], 'only --qualify is supported')
        if Path('/run/game_live_camera/capture/capture_package.json').exists() and Path(__file__).resolve() == Path('/run/game_live_camera/capture/qualify.py'):
            check_capture()
        else:
            check_live()
    except Exception as exc:
        print('FIXED720_QUALIFICATION_BLOCKED: ' + str(exc), file=sys.stderr)
        sys.exit(3)
