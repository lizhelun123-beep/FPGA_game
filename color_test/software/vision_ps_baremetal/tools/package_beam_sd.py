"""Build a self-contained SD deployment package for the Linux beam720 test.

This is file-only packaging. It does not mount, modify, or write an SD card.
The existing PYNQ boot.scr/image.ub are copied from a caller-selected reference
card; BOOT.BIN is taken from the same-source build5 package as the current HWH.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import zipfile


REPO = Path(__file__).resolve().parents[4]
TOOLS = Path(__file__).resolve().parent
BOOT = REPO / 'output/sd_card/BOOT.BIN'
BEAM = REPO / 'output/build/game_app/beam_display_arm_2/game_linux_static_menu.exe'
CAPTURE = TOOLS / 'game_capture_worker.py'
LIVE = REPO / 'pynq_vision'
OUT = REPO / 'output/beam_sd_deployment_1'
ZIP = REPO / 'output/beam_SD_deployment.zip'


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def copy_checked(source, target):
    if not source.is_file():
        raise FileNotFoundError(str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(source), str(target))


def capture_files():
    names = ['__init__.py', 'constants.py', 'hardware.py', 'live_capture.py',
             'ov5640.py', 'registers.py', 'vdma.py', 'video.py']
    result = {
        'capture_worker.py': CAPTURE,
        'dphy_observer.py': REPO / 'color_test/tools/dphy_observer.py',
        'libdphy_observer_mmio.so': REPO / 'output/build/game_app/live_board_1/stage/libdphy_observer_mmio.so',
    }
    for name in names:
        result['pynq_vision/' + name] = LIVE / name
    return result


def make_manifest(files):
    return {
        'scope': 'beam720_sd_deployment_1',
        'production_directory': '/run/game_live_camera/capture',
        'files': {name: digest(path) for name, path in files.items()},
        'format': {'width': 1280, 'height': 720, 'stride': 5760,
                   'frame_span': 4147200, 'stores': 3},
        'bridge_protocol': 'FRAME sequence captured_ms slot writer; FRAME_DONE',
    }


def make_payload(files, manifest):
    data = {name: path.read_bytes() for name, path in files.items()}
    data['capture_package.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    data['beam_runtime.py'] = (TOOLS / 'beam_runtime.py').read_bytes()
    data['beam720'] = BEAM.read_bytes()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, value in sorted(data.items()):
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mode = 0o755 if name in ('beam720', 'beam_runtime.py') else 0o644
            archive.addfile(info, io.BytesIO(value))
    return gzip.compress(buffer.getvalue(), mtime=0), data


def generate_boot(boot_sha, payload_sha):
    template = (TOOLS / 'beam_sd_boot.py').read_text(encoding='utf-8')
    return template.replace('__BOOT_SHA256__', boot_sha).replace('__PAYLOAD_SHA256__', payload_sha)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-sd', type=Path, required=True,
                        help='directory containing the unchanged PYNQ boot.scr and image.ub')
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    reference = args.reference_sd
    if not (reference / 'boot.scr').is_file() or not (reference / 'image.ub').is_file():
        raise SystemExit('reference SD must contain boot.scr and image.ub')
    if not BOOT.is_file() or not BEAM.is_file():
        raise SystemExit('matched BOOT.BIN or ARM beam executable is missing')
    if args.output.exists() or ZIP.exists():
        raise SystemExit('refusing to overwrite an existing deployment output')
    if BOOT.stat().st_size != 2587144 or digest(BOOT) != '1cbbc1c7f54623bb7683ee82d1e19e2f54626320c7ce50237faea6ca168e2fab':
        raise SystemExit('BOOT.BIN is not the verified build5 PYNQ/PL package')
    files = capture_files()
    for path in files.values():
        if not path.is_file():
            raise SystemExit('missing capture package file: ' + str(path))
    manifest = make_manifest(files)
    payload, payload_data = make_payload(files, manifest)
    args.output.mkdir(parents=True)
    copy_checked(BOOT, args.output / 'BOOT.BIN')
    copy_checked(reference / 'boot.scr', args.output / 'boot.scr')
    copy_checked(reference / 'image.ub', args.output / 'image.ub')
    (args.output / 'beam_runtime.tar.gz').write_bytes(payload)
    boot_text = generate_boot(digest(BOOT), digest_bytes(payload))
    compile(boot_text, 'beam_boot.py', 'exec')
    (args.output / 'boot.py').write_text(boot_text, encoding='utf-8', newline='\n')
    report = {
        'status': 'OFFLINE_BEAM_SD_PACKAGE_READY_NOT_BOARD_QUALIFIED',
        'boot_scr_replaced': False,
        'image_ub_replaced': False,
        'files': {path.name: {'bytes': path.stat().st_size, 'sha256': digest(path)}
                  for path in args.output.iterdir() if path.is_file()},
        'reference': {name: {'bytes': (reference / name).stat().st_size,
                             'sha256': digest(reference / name)}
                      for name in ('boot.scr', 'image.ub')},
        'beam': {'source': str(BEAM), 'bytes': len(payload_data['beam720']),
                 'sha256': digest_bytes(payload_data['beam720'])},
        'capture_manifest': manifest,
        'boot_identity': digest(BOOT),
        'payload_identity': digest_bytes(payload),
    }
    report['files']['boot.py'] = {'bytes': (args.output / 'boot.py').stat().st_size,
                                  'sha256': digest(args.output / 'boot.py')}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    instructions = '''本包用于固定逻辑光源的 PYNQ 实景 beam720 测试。

复制到 SD 启动分区根目录：BOOT.BIN、boot.scr、image.ub、boot.py、beam_runtime.tar.gz。
boot.scr 和 image.ub 沿用当前 PYNQ 2.6.2 基线；BOOT.BIN 为与当前 build5 HWH/PL 配套的版本。
上电后 boot.py 会做哈希检查，把采集运行包放入 RAM，并启动 ray-game-beam720，默认运行 180 秒。
停止时使用 sudo systemctl stop ray-game-beam720，等待程序确认 DMA HALTED 后再拔卡或重启。
本包只完成离线打包，尚未执行板端冷启动、实时摄像头、HDMI 或 DMA 验收。
'''
    (args.output / '使用说明.txt').write_text(instructions, encoding='utf-8-sig')
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    print(json.dumps({'folder': str(args.output), 'zip': str(ZIP),
                      'BOOT_sha256': digest(BOOT), 'payload_sha256': digest_bytes(payload)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
