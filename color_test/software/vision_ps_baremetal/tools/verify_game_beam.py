"""Verify the standalone ARM ELF/BOOT bytes; no vendor executables or board access."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[4]
SYMBOLS = ('main', 'game_beam_submit',
           'vision_detect_bgr888', 'game_beam_display_snapshot',
           'ray_game_trace_from_emitter_policy',
           'game_display_update', 'game_baremetal_capture_copy',
           'game_beam_first_fault', 'sensor_start', 'sensor_stop')


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fingerprint(path):
    data = path.read_bytes()
    return dict(path=path.resolve().relative_to(ROOT).as_posix(), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def verify_elf(path):
    raw = path.read_bytes()
    packet = module('package_live_boot')
    payload, info, symbols = packet.elf_info(path)
    missing = set(SYMBOLS)-symbols
    if missing:
        raise ValueError('Missing standalone beam symbols: '+', '.join(sorted(missing)))
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', raw)
    if header[1] != 2:
        raise ValueError('Require linked ET_EXEC ELF')
    for i in range(header[10]):
        if struct.unpack_from('<I', raw, header[5]+i*header[9])[0] in (2, 3):
            raise ValueError('Standalone ELF has dynamic loader/interpreter segment')
    if (info['load_address'] != 0x100000 or info['entry'] != 0x100000 or
            info['memory_bytes'] < info['file_bytes'] or
            info['load_address']+info['memory_bytes'] > 0x40000000):
        raise ValueError('Standalone DDR load/entry/span mismatch')
    forbidden = {name for name in symbols if name.startswith(('pthread_', 'game_linux_live_session_',
                                                             'apriltag_', 'vision_portal_detect_'))}
    if forbidden:
        raise ValueError('Unexpected OS-backed symbols: '+', '.join(sorted(forbidden)))
    return dict(info, payload_sha256=hashlib.sha256(payload).hexdigest(),
                required_symbols=list(SYMBOLS), no_dynamic_loader=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--boot', type=Path)
    args = parser.parse_args()
    args.inputs = args.inputs.resolve()
    args.elf = args.elf.resolve()
    if args.boot is not None:
        args.boot = args.boot.resolve()
    inputs = json.loads((args.inputs/'inputs.json').read_text(encoding='utf-8'))
    prepare = module('prepare_game_beam')
    historical = inputs['baseline']['profile'] == 'historical_live_20261026'
    actual, bit = prepare.inspect_xsa(args.inputs/'hardware.xsa', allow_historical_live=historical)
    if any(actual[key] != inputs[key] for key in actual):
        raise ValueError('Frozen XSA identity/ABI differs from inputs.json')
    if bit != (args.inputs/'system_wrapper.bit').read_bytes():
        raise ValueError('Frozen BIT differs from the selected XSA')
    if historical:
        prepare.inspect_live_baseline()
        original = ROOT/prepare.LIVE_PLATFORM
        bsp = original/'ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0'
        for a, b in ((original/'zynq_fsbl/fsbl.elf', args.inputs/'fsbl.elf'),
                     (original/'hw/ps7_init.tcl', args.inputs/'ps7_init.tcl'),
                     (bsp/'include/xparameters.h', args.inputs/'bsp/include/xparameters.h'),
                     (bsp/'lib/libxil.a', args.inputs/'bsp/lib/libxil.a')):
            if a.read_bytes() != b.read_bytes():
                raise ValueError('Frozen platform differs: '+str(b))
    elf = verify_elf(args.elf)
    result = dict(status='PASS_STANDALONE_ARM_ELF', scope='offline compiled artifact only; no hardware',
                  inputs=inputs, elf=elf, outputs=[fingerprint(args.elf)], hardware_operated=False)
    if args.boot is not None:
        fsbl = args.inputs/'fsbl.elf' if historical else args.inputs.parent/'beam_platform/zynq_fsbl/fsbl.elf'
        partitions, _ = module('package_live_boot').verify_boot(
            args.boot, fsbl, args.inputs/'system_wrapper.bit', args.elf, required_symbols=SYMBOLS)
        fsbl_end = partitions[0]['load_address'] + partitions[0]['memory_bytes']
        if fsbl_end > elf['load_address']:
            raise ValueError('FSBL and application executable memory overlap')
        result.update(status='PASS_STANDALONE_BOOT_PARTITIONS', partitions=partitions)
        result['memory_layout'] = dict(
            fsbl_start=partitions[0]['load_address'], fsbl_end=fsbl_end,
            application_start=elf['load_address'],
            application_end=elf['load_address']+elf['memory_bytes'],
            executable_regions_disjoint=True,
            pl_partition_destination='configuration device (partition attribute0x20); load_address0 is not executable DDR',
            bootgen_overlap_notice='Same notice as preserved live BOOT; partition bytes/attributes and executable ranges checked')
        result['outputs'].append(fingerprint(args.boot))
        (args.elf.parent/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    else:
        (args.elf.parent/'elf_identity.txt').write_text(json.dumps(elf, indent=2)+'\n', encoding='utf-8')
    print(result['status']+' file_bytes='+str(elf['file_bytes'])+' memory_bytes='+str(elf['memory_bytes']))


if __name__ == '__main__':
    main()
