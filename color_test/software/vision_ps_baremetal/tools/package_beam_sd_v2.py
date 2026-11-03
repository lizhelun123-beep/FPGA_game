"""Build the matched PYNQ SD package for the Linux fixed-emitter beam test."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile


REPO = Path(__file__).resolve().parents[4]
TOOLS = Path(__file__).resolve().parent
APP = TOOLS.parent
BUILD = REPO / 'color_test/build/pl_rate93_production/build_5'
BEAM_BUILD = REPO / 'output/build/game_app/beam_sd_2'
BEAM = BEAM_BUILD / 'beam720'
BOOT = REPO / 'output/sd_card/BOOT.BIN'
REFERENCE = REPO / 'output/build/game_app/boot5_menu_1'
OLD_BUILD = REPO / 'output/build/game_app/sd_autostart_1'
OUT = REPO / 'output/beam_sd_deployment_6'
ZIP = REPO / 'output/beam_SD_deployment_v6.zip'
BIN = Path('D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def run(command, log):
    BEAM_BUILD.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(item) for item in command], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    (BEAM_BUILD / log).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(log + ' failed; see saved log')
    return result.stdout.decode('utf-8', errors='replace')


def build_beam():
    config = BEAM_BUILD / 'game_config.h'
    run(['python', TOOLS / 'generate_game_config.py', '--output', config], 'config.log')
    source = APP / 'src'
    names = ['game_session.c', 'ray_game.c', 'game_beam.c', 'vision_stabilizer.c',
             'game_scene_adapter.c', 'game_app.c', 'game_input.c', 'game_evdev.c',
             'game_loop.c', 'game_pump.c', 'game_render.c', 'vision_overlay.c',
             'game_linux_io.c', 'game_linux_display.c', 'game_photo_input.c',
             'game_linux_capture.c', 'scene_protocol.c', 'vision_ps.c',
             'green_target_detector.c']
    sources = [source / name for name in names]
    sources += [BEAM_BUILD / 'game_config.c', TOOLS / 'game_linux_static_menu.c']
    flags = ['-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
             '-DGAME_CAMERA_CAPTURE_CHECKER', '-I' + str(source),
             '-I' + str(BEAM_BUILD), '-mcpu=cortex-a9', '-mfpu=vfpv3',
             '-mfloat-abi=hard', '-static']
    run([BIN / 'arm-linux-gnueabihf-gcc.exe', *flags, *sources, '-lm', '-o', BEAM],
        'beam_arm_build.log')
    try:
        elf = run([BIN / 'arm-linux-gnueabihf-readelf.exe', '-h', '-l', '-A', '-d', BEAM],
                  'beam_arm_readelf.log')
    except OSError as error:
        (BEAM_BUILD / 'beam_arm_readelf.log').write_text(
            'readelf unavailable on host: ' + str(error) + '\n', encoding='utf-8')
        elf = ''
    raw = BEAM.read_bytes()
    if elf:
        if ('ARM' not in elf or 'Tag_ABI_VFP_args: VFP registers' not in elf or
                'INTERP' in elf or 'NEEDED' in elf):
            raise RuntimeError('beam ELF ABI audit failed')
    elif raw[:4] != b'\x7fELF' or raw[4] != 1 or raw[18:20] != b'(\x00':
        raise RuntimeError('beam raw ELF identity failed')
    return BEAM


def q_paths():
    return {
        'display.elf': OLD_BUILD / 'display.elf',
        'libdphy_observer_mmio.so': OLD_BUILD / 'libdphy_observer_mmio.so',
        'game_assets.bin': REPO / 'output/sd_card/ray_game_assets/game_assets.bin',
        'environment_support.py': REFERENCE / 'environment_support.py',
        'dphy_observer.py': REPO / 'color_test/tools/dphy_observer.py',
        'qualify.py': TOOLS / 'game_display_qualify.py',
        'autostart.py': TOOLS / 'game_linux_autostart.py',
        'display.hwh': BUILD / 'export/system.hwh',
        'artifacts.json': BUILD / 'export/artifacts.json',
        'gate.json': BUILD / 'declared_model_gate.json',
        'boot_manifest.json': BUILD / 'boot_package/boot_manifest.json',
    }


def capture_paths():
    paths = {
        'capture_worker.py': TOOLS / 'game_capture_worker.py',
        'dphy_observer.py': REPO / 'color_test/tools/dphy_observer.py',
        'libdphy_observer_mmio.so': OLD_BUILD / 'libdphy_observer_mmio.so',
    }
    for name in ('__init__.py', 'constants.py', 'hardware.py', 'live_capture.py', 'boundary_observer.py',
                 'ov5640.py', 'registers.py', 'vdma.py', 'video.py'):
        paths['pynq_vision/' + name] = REPO / 'pynq_vision' / name
    return paths


def make_q_manifest(paths):
    return {'part': 'xc7z020clg400-2', 'software_scope': 'boot5_menu_only',
            'display_reset_contract': 'guard1_dual_psr13_aux16', 'dynclk_status_mask': 3,
            'files': {name: sha(path) for name, path in paths.items()}}


def make_capture_manifest(paths):
    return {'scope': 'beam720_capture_2',
            'production_directory': '/run/game_live_camera/capture',
            'files': {name: sha(path) for name, path in paths.items()},
            'format': {'width': 1280, 'height': 720, 'stride': 5760,
                       'frame_span': 4147200, 'stores': 3},
            'bridge_protocol': 'FRAME sequence captured_ms slot writer; FRAME_DONE'}


def tar_gz(data):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, value in sorted(data.items()):
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mode = 0o755 if name in ('beam720', 'beam_runtime.py') else 0o644
            archive.addfile(info, io.BytesIO(value))
    return gzip.compress(buffer.getvalue(), mtime=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-sd', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    if not (args.reference_sd / 'boot.scr').is_file() or not (args.reference_sd / 'image.ub').is_file():
        raise SystemExit('reference SD must contain boot.scr and image.ub')
    if args.output.exists() or ZIP.exists():
        raise SystemExit('refusing to overwrite an existing beam SD output')
    if sha(BOOT) != '1cbbc1c7f54623bb7683ee82d1e19e2f54626320c7ce50237faea6ca168e2fab':
        raise SystemExit('BOOT.BIN is not the verified build5 package')
    beam = build_beam()
    q = q_paths()
    capture = capture_paths()
    for path in list(q.values()) + list(capture.values()):
        if not path.is_file():
            raise SystemExit('missing package input: ' + str(path))
    q_manifest = make_q_manifest(q)
    capture_manifest = make_capture_manifest(capture)
    q_data = {name: path.read_bytes() for name, path in q.items()}
    capture_data = {name: path.read_bytes() for name, path in q.items()}
    capture_data.update({name: path.read_bytes() for name, path in capture.items()})
    capture_data['package.json'] = (json.dumps(q_manifest, indent=2) + '\n').encode()
    capture_data['capture_package.json'] = (json.dumps(capture_manifest, indent=2) + '\n').encode()
    capture_payload = tar_gz(capture_data)
    outer = dict(q_data)
    outer['package.json'] = (json.dumps(q_manifest, indent=2) + '\n').encode()
    outer['beam720'] = beam.read_bytes()
    outer['beam_runtime.py'] = (TOOLS / 'beam_runtime.py').read_bytes()
    outer['beam_capture.tar.gz'] = capture_payload
    payload = tar_gz(outer)
    args.output.mkdir(parents=True)
    shutil.copyfile(str(BOOT), str(args.output / 'BOOT.BIN'))
    shutil.copyfile(str(args.reference_sd / 'boot.scr'), str(args.output / 'boot.scr'))
    shutil.copyfile(str(args.reference_sd / 'image.ub'), str(args.output / 'image.ub'))
    (args.output / 'beam_runtime.tar.gz').write_bytes(payload)
    boot_text = (TOOLS / 'beam_sd_boot.py').read_text(encoding='utf-8')
    boot_text = boot_text.replace('__PAYLOAD_SHA256__', sha_bytes(payload)).replace('__BOOT_SHA256__', sha(BOOT))
    compile(boot_text, 'beam_sd_boot.py', 'exec')
    (args.output / 'boot.py').write_text(boot_text, encoding='utf-8', newline='\n')
    report = {'status': 'OFFLINE_BEAM_SD_PACKAGE_READY_NOT_BOARD_QUALIFIED',
              'preflight': 'game_linux_autostart.py reused; beam selected by beam720 marker',
              'boot_scr_replaced': False, 'image_ub_replaced': False,
              'boot_identity': sha(BOOT), 'payload_identity': sha_bytes(payload),
              'beam': {'source': str(beam), 'bytes': beam.stat().st_size, 'sha256': sha(beam),
                       'compile_define': 'GAME_CAMERA_CAPTURE_CHECKER'},
              'qualification_manifest': q_manifest, 'capture_manifest': capture_manifest,
              'files': {path.name: {'bytes': path.stat().st_size, 'sha256': sha(path)}
                        for path in args.output.iterdir() if path.is_file()}}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    instructions = '''本包用于固定逻辑光源的 PYNQ 实景 beam720 测试。

复制到 SD 启动分区根目录：BOOT.BIN、boot.scr、image.ub、boot.py、beam_runtime.tar.gz。
boot.py 先进入现有 game_linux_autostart.py 的冷启动准入、FCLK、复位、所有权和 load_receipt 流程，再启动 beam720。
beam720 使用 GAME_CAMERA_CAPTURE_CHECKER 编译，并通过 beam_runtime.py 部署相机采集包。
串口应出现 BEAM_DISPLAY_PREPARED、BEAM_HDMI_STARTED、BEAM_FIRST_FRAME 和 BEAM_SAFE_STOP。
默认运行 180 秒；停止使用 sudo systemctl stop ray-game-autostart，等待 BEAM_SAFE_STOP 后再拔卡或重启。
boot.scr 和 image.ub 沿用当前 PYNQ 2.6.2 基线；本包只完成离线编译/打包，尚未执行板端冷启动、HDMI、DMA 或摄像头验收。
'''
    (args.output / '使用说明.txt').write_text(instructions, encoding='utf-8-sig')
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    print(json.dumps({'folder': str(args.output), 'zip': str(ZIP),
                      'BOOT_sha256': sha(BOOT), 'payload_sha256': sha_bytes(payload)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
