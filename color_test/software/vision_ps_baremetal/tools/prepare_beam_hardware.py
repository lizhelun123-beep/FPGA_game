"""Generate the fixed v14 hardware handoff from frozen XSA and canonical C.

Not a second game configuration. Reads the original image and never changes
it. Does not load PL, open devices, generate an admission receipt or run tools.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import sys
import zipfile
import operator
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]


def sha(data): return hashlib.sha256(data).hexdigest()


def sensor_table(source, name):
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    body = re.search(r'\b' + re.escape(name) + r'\s*\[\]\s*=\s*\{(.*?)\};', clean, re.S).group(1)
    operations = {ast.RShift: operator.rshift, ast.LShift: operator.lshift,
                  ast.BitAnd: operator.and_, ast.BitOr: operator.or_,
                  ast.Add: operator.add, ast.Sub: operator.sub}
    def integer(text):
        node = ast.parse(text.strip(), mode='eval').body
        def visit(item):
            if isinstance(item, ast.Constant) and type(item.value) is int:
                return item.value
            if isinstance(item, ast.BinOp) and type(item.op) in operations:
                return operations[type(item.op)](visit(item.left), visit(item.right))
            raise ValueError('unsupported sensor constant: ' + text)
        return visit(node)
    pairs = []
    for a, b in re.findall(r'\{\s*([^,{}]+),\s*([^{}]+)\}', body):
        if a.strip() == 'SEQUENCE_END': break
        register, value = integer(a), integer(b)
        if not 0 <= register <= 0xffff or not 0 <= value <= 255:
            raise ValueError('sensor register/value outside ABI')
        if register == 0xffff: break
        pairs.append((register, value))
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--reader-deps', type=Path)
    parser.add_argument('--simulation-pass', action='store_true',
                        help='用已完成的 PYNQ 主机仿真作为交付门槛')
    args = parser.parse_args()
    if args.output.exists(): raise RuntimeError('preserve previous output; select a fresh directory')
    if args.reader_deps: sys.path.insert(0, str(args.reader_deps.resolve()))
    sys.path.insert(0, str(ROOT))
    from dissect.extfs.extfs import ExtFS
    from dissect.util.stream import RangeStream
    from pynq_vision.prepare_kernel_sdk import IMAGE_SHA256, root_partition
    from pynq_vision.constants import ADDRESS_MAP, FCLK_MHZ
    xsa = ROOT / 'color_test/build/beam_standalone/restored_binary_v3_1/inputs/hardware.xsa'
    inputs = json.loads((xsa.parent / 'inputs.json').read_bytes())
    if sha(xsa.read_bytes()) != inputs['xsa_sha256']: raise RuntimeError('frozen XSA differs')
    with zipfile.ZipFile(xsa) as z:
        bit = z.read(next(n for n in z.namelist() if n.endswith('.bit')))
        hwh = z.read(next(n for n in z.namelist() if n.endswith('.hwh')))
    if sha(bit) != inputs['bit_sha256'] or sha(hwh) != inputs['hwh_sha256']:
        raise RuntimeError('mixed frozen Overlay pair')
    tree = ET.fromstring(hwh)
    addresses = {n.get('INSTANCE'): [int(n.get('BASEVALUE'),0),
                 int(n.get('HIGHVALUE'),0)-int(n.get('BASEVALUE'),0)+1]
                 for n in tree.iter('MEMRANGE') if n.get('MEMTYPE') == 'REGISTER'}
    if any(addresses.get(name) != list(value) for name,value in ADDRESS_MAP.items()):
        raise RuntimeError('address map differs from matched HWH')
    ps = next(n for n in tree.iter('MODULE') if n.get('MODTYPE') == 'processing_system7')
    parameters = {n.get('NAME'):n.get('VALUE') for n in ps.iter('PARAMETER')}
    reference_hz = round(float(parameters['PCW_CRYSTAL_PERIPHERAL_FREQMHZ']) * 1000000)
    if reference_hz != 33333333: raise RuntimeError('PS reference clock differs')
    sources = {}
    with args.image.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''): digest.update(block)
        if digest.hexdigest() != IMAGE_SHA256: raise RuntimeError('target image differs')
        offset, span = root_partition(stream, args.image.stat().st_size)
        fs = ExtFS(RangeStream(stream, offset, span))
        node = fs.get('/home/xilinx/pynq')
        package = node.link if node.filetype == stat.S_IFLNK else '/home/xilinx/pynq'
        if not package.startswith('/'): raise RuntimeError('unexpected package symlink')
        for name in ('__init__.py', 'xlnk.py', 'ps.py', 'overlay.py', 'pl_server/device.py'):
            sources[name] = sha(fs.get(package + '/' + name).open().read())
    sensor_raw = (ROOT / 'color_test/software/vision_ps_baremetal/src/ov5640.c').read_bytes()
    sensor = sensor_raw.decode('utf-8')
    record = dict(schema='beam-pynq-hardware-v1', version=14,
        board_gate='PASS_BY_SIMULATION' if args.simulation_pass else 'INPUTS_ONLY',
        bit_sha256=sha(bit), hwh_sha256=sha(hwh), xsa_sha256=inputs['xsa_sha256'],
        library_sha256=sha(args.library.read_bytes()), csi_version=0x10001,
        frame=dict(width=1280, height=720, row=3840, stride=5760, stores=3),
        addresses=ADDRESS_MAP, fclk_mhz=FCLK_MHZ, ps_reference_hz=reference_hz,
        kernel_release='5.4.0-xilinx-v2020.1',
        kernel_build_id='83e702eeb9e31cc76bef7e013bae379fd2de4f93',
        kernel_config_sha256='f2fa6d9b7e7b86b7b1210db2d299835543e08822ef05d8dce3d23445946c80a5',
        fit_sha256='07132df1bf965dee030141712c686937004bae88f5aea7bff1ceca184158b797',
        image_sha256=IMAGE_SHA256, pynq_sources=sources,
        sensor_init=sensor_table(sensor, 'sensor_init_data'),
        sensor_mode=sensor_table(sensor, 'cfg_720p_60fps'),
        sensor_expected=sensor_table(sensor, 'expected'),
        source_sensor_sha256=sha(sensor_raw), hardware_operations=0)
    if not record['sensor_init'] or not record['sensor_mode'] or not record['sensor_expected']:
        raise RuntimeError('canonical sensor tables unresolved')
    args.output.mkdir(parents=True)
    (args.output / 'system_wrapper.bit').write_bytes(bit)
    (args.output / 'system_wrapper.hwh').write_bytes(hwh)
    shutil.copy2(args.library, args.output / 'libbeam_pynq.so')
    (args.output / 'hardware.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS_BY_SIMULATION' if args.simulation_pass else 'HARDWARE_INPUTS_READY', output=str(args.output),
                         sensor_entries=[len(record[k]) for k in ('sensor_init','sensor_mode','sensor_expected')],
                         library_sha256=record['library_sha256'])))


if __name__ == '__main__': main()
