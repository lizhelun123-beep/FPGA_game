"""Strict host checks of the restored C path; no hardware or ARM execution."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

APP = Path(__file__).resolve().parents[1]


def main():
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
        for name in ('test_restored_scene', 'test_game_beam', 'test_ray_game', 'test_vision_stabilizer_timed'):
            exe = work/(name+'.exe')
            subprocess.run([compiler, '/nologo', '/std:c11', '/O2', '/W4', '/WX',
                '/I'+str(APP/'src'), *(str(APP/'src'/(s+'.c')) for s in sources),
                str(APP/'tests'/(name+'.c')), '/Fe:'+str(exe)],
                cwd=work, env=env, check=True, timeout=90)
            subprocess.run([str(exe)], cwd=work, env=env, check=True, timeout=60)
        print('PASS: four strict MSVC host C checks; no board operations')


if __name__ == '__main__':
    main()
