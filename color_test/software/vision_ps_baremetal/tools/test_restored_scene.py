"""Strict host checks of the restored C path; no hardware or ARM execution."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import argparse

APP = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo', action='append', default=[], help='Offline1280x720 image, includes any pre-existing overlay')
    parser.add_argument('--only-overlap', action='store_true')
    args=parser.parse_args()
    # Use the repository's established MSVC host route; the legacy MinGW GCC
    # cannot start on this Windows host (DLL relocation failure).
    vswhere = Path(r'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe')
    installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
        '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
        '-property', 'installationPath'], text=True, timeout=15).strip()
    if not installation:
        raise RuntimeError('MSVC C tools unavailable')
    vcvars = Path(installation)/'VC/Auxiliary/Build/vcvars64.bat'
    with tempfile.TemporaryDirectory(prefix='restored_scene_') as temporary:
        work = Path(temporary)
        script = work/'environment.cmd'
        script.write_text(f'@echo off\ncall "{vcvars}" >nul\n'
                          'if errorlevel 1 exit /b %errorlevel%\nset\n', encoding='utf-8')
        data = subprocess.check_output(['cmd.exe', '/d', '/c', str(script)],
                                       cwd=work, text=True, timeout=30)
        env = dict(line.split('=', 1) for line in data.splitlines() if '=' in line and not line.startswith('='))
        compiler = shutil.which('cl.exe', path=next(v for k, v in env.items() if k.lower() == 'path'))
        if not compiler:
            raise RuntimeError('No cl.exe from vcvars64')
        sources = ['vision_ps', 'green_target_detector', 'vision_stabilizer',
                   'ray_game', 'vision_overlay', 'game_beam']
        for name in (() if args.only_overlap else ('test_hsv_exact', 'test_restored_scene', 'test_game_beam', 'test_ray_game', 'test_vision_stabilizer_timed')):
            exe = work/(name+'.exe')
            subprocess.run([compiler, '/nologo', '/std:c11', '/O2', '/W4', '/WX',
                '/I'+str(APP/'src'), *(str(APP/'src'/(s+'.c')) for s in sources),
                str(APP/'tests'/(name+'.c')), '/Fe:'+str(exe)],
                cwd=work, env=env, check=True, timeout=90)
            subprocess.run([str(exe)], cwd=work, env=env, check=True, timeout=60)
        if not args.only_overlap:
            print('PASS: exactHSV and four strict MSVC host C checks; no board operations')
        exe=work/'test_display_overlap.exe'
        subprocess.run([compiler,'/nologo','/std:c11','/O2','/W4','/WX',
            '/I'+str(APP/'src'),str(APP/'src/game_linux_display.c'),str(APP/'src/vision_overlay.c'),
            str(APP/'src/beam_uart_log.c'),str(APP/'tests/test_display_overlap.c'),
            '/Fe:'+str(exe)],cwd=work,env=env,check=True,timeout=90)
        subprocess.run([str(exe)],cwd=work,env=env,check=True,timeout=60)
        if not args.only_overlap:
            # Exercise the complete three-store fake platform as well as the
            # small overlap contract.  In particular, a transient retirement
            # timeout must return to SCANNING without a stop/configure/release.
            subprocess.run([os.sys.executable, str(APP/'tools/generate_game_config.py'),
                '--output', str(work/'game_config.h')], cwd=work, env=env,
                check=True, timeout=60)
            display_sources = [
                'game_session.c', 'ray_game.c', 'game_beam.c', 'vision_stabilizer.c',
                'game_scene_adapter.c', 'game_app.c', 'game_input.c', 'game_evdev.c',
                'game_loop.c', 'game_pump.c', 'game_render.c', 'vision_overlay.c',
                'game_linux_display.c', 'game_linux_io.c', 'game_photo_input.c',
                'game_linux_capture.c', 'scene_protocol.c', 'vision_ps.c',
                'green_target_detector.c']
            exe=work/'test_game_linux_display.exe'
            subprocess.run([compiler,'/nologo','/std:c11','/O2','/W3','/utf-8',
                '/D_CRT_SECURE_NO_WARNINGS',
                '/I'+str(APP/'src'),'/I'+str(work),
                *(str(APP/'src'/name) for name in display_sources),
                str(work/'game_config.c'),str(APP/'tests/test_game_linux_display.c'),
                '/Fe:'+str(exe)],cwd=work,env=env,check=True,timeout=120)
            subprocess.run([str(exe),'--continuous-checks'],cwd=work,env=env,
                           check=True,timeout=60)
        if args.photo:
            import cv2
            import numpy as np
            exe=work/'restored_probe.exe'
            subprocess.run([compiler,'/nologo','/std:c11','/O2','/W4','/WX','/D_CRT_SECURE_NO_WARNINGS','/DVISION_TRACE',
                '/I'+str(APP/'src'),str(APP/'src/vision_ps.c'),str(APP/'src/green_target_detector.c'),str(APP/'src/ray_game.c'),
                str(APP/'tests/restored_detection_probe.c'),'/Fe:'+str(exe)],cwd=work,env=env,check=True,timeout=90)
            for photo in args.photo:
                frame=cv2.imdecode(np.fromfile(photo,dtype=np.uint8),cv2.IMREAD_COLOR)
                if frame is None or frame.shape!=(720,1280,3):
                    raise ValueError('Expected720p image: '+photo)
                raw=work/'photo.bgr'
                raw.write_bytes(frame.tobytes())
                print('OFFLINE_SCREEN_REFERENCE (overlay retained, not raw/board acceptance):',photo,flush=True)
                subprocess.run([str(exe),str(raw)],cwd=work,env=env,check=True,timeout=60)


if __name__ == '__main__':
    main()
