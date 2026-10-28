"""Build the canonical C menu and SD companion files; never contact the board."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

REPO = Path(__file__).resolve().parents[4]
TOOLS = Path(__file__).resolve().parent
APP = TOOLS.parent
BUILD = REPO / 'color_test/build/pl_rate93_production/build_5'
WORK = REPO / 'output/build/game_app/sd_autostart_1'
DEST = REPO / 'output/sd_autostart'
BIN = Path('D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, name):
    value = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120)
    (WORK / (name + '.log')).write_bytes(value.stdout)
    if value.returncode:
        raise RuntimeError(name + ' failed; see saved log; no board access')
    return value.stdout.decode('utf-8', errors='replace')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    # Verify the existing same-source PL gate; do not rebuild or re-export PL.
    gate_check = json.loads(run([sys.executable, '-I', REPO / 'color_test/tools/camera_production_audit.py',
                                'export_inputs', '5'], 'existing_PL_identity'))
    boot = REPO / 'output/sd_card/BOOT.BIN'
    manifest = json.loads((BUILD / 'boot_package/boot_manifest.json').read_text())
    assert sha(boot) == manifest['sha256']
    run([sys.executable, TOOLS / 'generate_game_config.py', '--output', WORK / 'game_config.h'], 'config')
    modules = ['game_session', 'ray_game', 'game_scene_adapter', 'game_app', 'game_input',
               'game_evdev', 'game_loop', 'game_pump', 'game_render', 'vision_overlay',
               'game_linux_display', 'game_linux_io', 'game_photo_input', 'vision_ps',
               'green_target_detector']
    sources = [APP / 'src' / (name + '.c') for name in modules]
    sources += [WORK / 'game_config.c', TOOLS / 'game_linux_static_menu.c']
    flags = ['-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
             '-I' + str(APP / 'src'), '-I' + str(WORK)]
    cpu = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
    run([BIN / 'arm-linux-gnueabihf-gcc.exe', *flags, '-static', *cpu, *sources,
         '-lm', '-o', WORK / 'display.elf'], 'ARM_menu_build')
    run([BIN / 'arm-linux-gnueabihf-gcc.exe', '-std=c11', '-Wall', '-Wextra', '-Werror',
         '-O2', *cpu, '-nostdlib', '-shared', '-fPIC',
         REPO / 'color_test/tools/dphy_observer_mmio.c', '-o', WORK / 'libdphy_observer_mmio.so'], 'ARM_mmio_build')
    elf = run([BIN / 'arm-linux-gnueabihf-readelf.exe', '-h', '-l', '-A', '-d', WORK / 'display.elf'], 'ARM_menu_readelf')
    assert 'ARM' in elf and 'hard-float' in elf and 'Tag_ABI_VFP_args: VFP registers' in elf
    assert 'INTERP' not in elf and 'NEEDED' not in elf
    library = run([BIN / 'arm-linux-gnueabihf-readelf.exe', '-h', '-d', '-Ws', WORK / 'libdphy_observer_mmio.so'], 'ARM_mmio_readelf')
    assert 'NEEDED' not in library and 'dphy_mmio_write32' in library
    # CPU renderer/ownership tests use existing fake platforms, never a device.
    compiler = shutil.which('gcc.exe')
    assert compiler
    host_flags = [compiler, *flags]
    run([*host_flags, *sources, '-lm', '-o', WORK / 'menu_host.exe'], 'host_menu_build')
    check = run([WORK / 'menu_host.exe', '--check'], 'host_menu_check')
    assert 'hash=1f497c09' in check and 'snapshot_unchanged=1' in check
    unit_sources = [p for p in sources if p.name != 'game_linux_static_menu.c']
    run([*host_flags, *unit_sources, APP / 'tests/test_game_linux_display.c', '-lm',
         '-o', WORK / 'display_unit.exe'], 'host_display_unit_build')
    run([WORK / 'display_unit.exe'], 'host_display_unit')
    reference = REPO / 'output/build/game_app/boot5_menu_1'
    paths = {
        'display.elf': WORK / 'display.elf',
        'libdphy_observer_mmio.so': WORK / 'libdphy_observer_mmio.so',
        'game_assets.bin': REPO / 'output/sd_card/ray_game_assets/game_assets.bin',
        'environment_support.py': reference / 'environment_support.py',
        'dphy_observer.py': REPO / 'color_test/tools/dphy_observer.py',
        'qualify.py': TOOLS / 'game_display_qualify.py',
        'autostart.py': TOOLS / 'game_linux_autostart.py',
        'display.hwh': BUILD / 'export/system.hwh',
        'artifacts.json': BUILD / 'export/artifacts.json',
        'gate.json': BUILD / 'declared_model_gate.json',
        'boot_manifest.json': BUILD / 'boot_package/boot_manifest.json',
    }
    for path in paths.values():
        if path.suffix == '.py':
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    package = dict(part='xc7z020clg400-2', software_scope='boot5_menu_only',
                   display_reset_contract='guard1_dual_psr13_aux16', dynclk_status_mask=3,
                   files={name: sha(path) for name, path in paths.items()})
    files = {name: path.read_bytes() for name, path in paths.items()}
    files['package.json'] = (json.dumps(package, indent=2) + '\n').encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name == 'display.elf' else 0o644
            archive.addfile(info, io.BytesIO(data))
    payload = gzip.compress(buffer.getvalue(), mtime=0)
    payload_sha = hashlib.sha256(payload).hexdigest()
    (DEST / 'ray_game_autostart.tar.gz').write_bytes(payload)
    entry = (TOOLS / 'game_sd_boot.py').read_text().replace('__PAYLOAD_SHA256__', payload_sha).replace('__BOOT_SHA256__', sha(boot))
    compile(entry, 'boot.py', 'exec')
    (DEST / 'boot.py').write_text(entry, encoding='utf-8', newline='\n')
    shutil.copyfile(boot, DEST / 'BOOT.BIN')
    # Preserve the diagnosed original LED example for a simple SD rollback.
    old = json.loads((BUILD / 'hdmi_boot_check_1/startup_details.json').read_text())['files']['/boot/boot.py']
    (DEST / 'boot.py.original').write_text(old, encoding='utf-8', newline='\n')
    instructions = '''将本目录 BOOT.BIN、boot.py、ray_game_autostart.tar.gz 一起复制到 SD 卡启动分区根目录，替换同名文件。先备份卡上原文件；其余 image.ub、boot.scr、Linux 分区及素材目录保留。
在已确认启用 bootpy.service 的当前 PYNQ 镜像中，重新上电后由 boot.py 自动启动现有中文 HDMI 菜单，无需另敲 Linux 启动命令。接好 HDMI 和 USB HOST 有线鼠标。
本包自动启动的是菜单，不启摄像头、无照片注入；实时识别定位和游戏闭环尚待实板验收。输出 1280×720，既有 1280×800 逻辑画布等比放入画面。
BOOT.BIN 保持 build5 合格 PL 和原 PYNQ FSBL/U-Boot/DTB；自启动由配套 boot.py 和程序包提供，不能只复制 BOOT.BIN。
本轮仅完成离线编译/打包，未执行冷启动实测。若准入失败则停止，不自动重新加载 FPGA 或重试。
可选串口诊断：systemctl status ray-game-autostart.service；journalctl -b -u bootpy.service -u ray-game-autostart.service；cat /run/game_single_image_720p/continuous/autostart_receipt.json。
安全停止：sudo systemctl stop ray-game-autostart.service。保留 SendSIGKILL=no 和无限停机等待，不能强杀尚未确认 DMA 停机的进程。
恢复旧启动入口：将 boot.py.original 复制回卡根目录并改名 boot.py；如需恢复原 FPGA 启动内容，使用原备份 BOOT.BIN。不要在程序运行时更换启动文件。
'''
    (DEST / '使用说明.txt').write_text(instructions, encoding='utf-8-sig')
    evidence = dict(status='OFFLINE_PACKAGE_READY_NOT_COLD_BOOT_QUALIFIED', FPGA_builds=0,
                    board_operations=0, BOOT_repack_runs=0, BOOT_preserved=True,
                    expected_BOOT_sha256=sha(boot), gate_sha256=gate_check['gate_sha256'],
                    package=package, service='RAM transient service via existing enabled PYNQ bootpy.service',
                    tests=['ARM static hard-float link/ELF audit', 'MMIO no-libc ELF audit',
                           'existing host menu check', 'existing host display ownership tests'],
                    files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in DEST.iterdir() if p.is_file()},
                    source_sha256={str(p.relative_to(REPO)): sha(p) for p in sources +
                                   list((APP / 'src').glob('*.h')) +
                                   [TOOLS / n for n in ('game_sd_boot.py', 'game_linux_autostart.py',
                                                         'game_display_qualify.py', 'package_game_autostart.py')] +
                                   [REPO / 'pc_vision/game_config.json']})
    (WORK / 'review.json').write_text(json.dumps(evidence, indent=2) + '\n')
    archive_path = REPO / 'output/ray_game_SD_autostart.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in DEST.iterdir():
            if path.is_file():
                archive.write(path, path.name)
    print(json.dumps(dict(status=evidence['status'], folder=str(DEST), zip=str(archive_path),
                          BOOT_sha256=sha(boot), payload_bytes=len(payload))))


if __name__ == '__main__':
    main()
