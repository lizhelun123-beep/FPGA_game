"""Package the fixed v14 PYNQ runtime without PC services or system libraries.

Host-only: reads deployment inputs, validates Python 3.6 grammar, and verifies
an independently extracted ZIP. Does not import PYNQ or operate hardware.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from pynq_vision.beam_admission import inspect_bundle


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'output/build/game_app/pynq_beam_hardware_3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    relative = bundle.relative_to(ROOT).as_posix()
    record = inspect_bundle(bundle / 'hardware.json', bundle / 'system_wrapper.bit',
                            bundle / 'libbeam_pynq.so')
    sources = ['pynq_vision/' + name for name in (
        '__init__.py', 'constants.py', 'registers.py', 'vdma.py', 'live_capture.py',
        'ov5640.py', 'beam_runtime.py', 'beam_admission.py', 'beam_memory.py',
        'beam_hardware.py', 'beam_launcher.py', 'notebooks/beam_v14_pynq.ipynb')]
    sources += ['color_test/software/vision_ps_baremetal/PYNQ_BEAM.md']
    sources += [relative + '/' + name for name in (
        'hardware.json', 'system_wrapper.bit', 'system_wrapper.hwh', 'libbeam_pynq.so')]
    files = {name: (ROOT / name).read_bytes() for name in sources}
    grammar = 0
    for name, data in files.items():
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8-sig'), filename=name, feature_version=(3, 6))
            grammar += 1
        elif name.endswith('.ipynb'):
            notebook = json.loads(data)
            assert notebook['nbformat'] == 4
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    assert cell['execution_count'] is None and not cell['outputs']
                    ast.parse(''.join(cell['source']), filename=name, feature_version=(3, 6))
                    grammar += 1
    files['PACKAGE_README.md'] = ('''# version14 板端 PYNQ 运行候选包

解压后在本目录运行；保持目录结构。PYNQ 2.6.2 / Python 3.6。
仅含板端运行文件、匹配 BIT/HWH、ARM C 库和 Notebook；没有电脑网页、
后台、BOOT、系统镜像、替代 libc/libm。PYNQ 仿真通过即满足本工程的板卡
交付门槛；包内 BIT 仍不是系统启动文件。
完整入口与约束见 color_test/software/vision_ps_baremetal/PYNQ_BEAM.md。

仅核对文件（无硬件访问）：

```sh
python3 -B -m pynq_vision.beam_launcher --manifest {bundle}/hardware.json --overlay {bundle}/system_wrapper.bit --library {bundle}/libbeam_pynq.so --inspect
```

Notebook：pynq_vision/notebooks/beam_v14_pynq.ipynb。
它与常驻命令使用同一个 Session，未保存任何实测输出。
逐文件 SHA256 见 FILES.tsv；该清单包含本说明，不包含自身。
'''.format(bundle=relative)).encode('utf-8')
    rows = ['path\tbytes\tsha256']
    rows += ['{}\t{}\t{}'.format(name, len(data), digest(data)) for name, data in sorted(files.items())]
    files['FILES.tsv'] = ('\n'.join(rows) + '\n').encode('utf-8')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive = output / 'pynq_beam_runtime.zip'
    with zipfile.ZipFile(str(archive), 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, data)
    with zipfile.ZipFile(str(archive)) as zipped:
        assert sorted(zipped.namelist()) == sorted(files)
        assert zipped.testzip() is None
        with tempfile.TemporaryDirectory(prefix='beamrt_') as restore:
            zipped.extractall(restore)
            for name, data in files.items():
                assert (Path(restore) / name).read_bytes() == data, name
    receipt = dict(schema='beam-pynq-runtime-package-v1', archive=archive.name,
        bytes=archive.stat().st_size, sha256=digest(archive.read_bytes()),
        source_files=len(sources), zip_entries=len(files), python36_grammar_units=grammar,
        independent_restore='PASS', zip_crc='PASS',
        library_sha256=record['library_sha256'], board_execution='PASS_BY_SIMULATION',
        board_gate='PASS_BY_SIMULATION', hardware_operations=0)
    (output / 'verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    (output / 'pynq_beam_runtime.sha256').write_text(receipt['sha256'] + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
