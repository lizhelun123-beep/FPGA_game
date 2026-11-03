#!/usr/bin/env python3
"""PYNQ boot.py template: verify/stage files, then queue the existing C menu.

The generated copy belongs on the SD boot partition. No PYNQ import, overlay
download, device access or root-filesystem installation occurs in this entry.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import time

PAYLOAD_SHA256 = '__PAYLOAD_SHA256__'
BOOT_SHA256 = '__BOOT_SHA256__'
ROOT = Path('/run/game_single_image_720p/continuous')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stage(boot, root, expected_payload, expected_boot):
    """File-only preparation; also exercised on a host temporary directory."""
    if sha((boot / 'BOOT.BIN').read_bytes()) != expected_boot:
        raise ValueError('BOOT identity mismatch; no service/device access')
    payload = (boot / 'ray_game_autostart.tar.gz').read_bytes()
    if len(payload) > 32 * 1024 * 1024 or sha(payload) != expected_payload:
        raise ValueError('Autostart payload mismatch; no service/device access')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if (len(names) != len(set(names)) or not 1 <= len(names) <= 32 or
                sum(m.size for m in members) > 64 * 1024 * 1024 or
                any(not m.isfile() or '/' in m.name or '\\' in m.name or
                    m.name in ('', '.', '..') or m.size < 0 for m in members)):
            raise ValueError('Unsafe archive member; nothing extracted')
        data = {m.name: archive.extractfile(m).read() for m in members}
    package = json.loads(data['package.json'].decode('utf-8'))
    if set(data) != set(package['files']) | {'package.json'}:
        raise ValueError('Archive/manifest members differ')
    if any(sha(data[name]) != digest for name, digest in package['files'].items()):
        raise ValueError('Package file mismatch; nothing extracted')
    if root.exists() or root.is_symlink():
        raise ValueError('This boot already has a display attempt; no retry')
    root.mkdir(mode=0o755, parents=True)
    os.chmod(str(root.parent), 0o755)
    os.chmod(str(root), 0o755)
    for name, value in data.items():
        with (root / name).open('xb') as target:
            target.write(value)
        os.chmod(str(root / name), 0o755 if name == 'display.elf' else 0o644)
    return package


def main():
    if os.geteuid() != 0:
        raise RuntimeError('PYNQ boot.py must execute as root')
    for path in (ROOT.parent, ROOT):
        if path.exists() or path.is_symlink():
            st = path.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid or st.st_mode & 0o022:
                raise ValueError('Unprotected runtime directory')
    stage(Path('/boot'), ROOT, PAYLOAD_SHA256, BOOT_SHA256)
    receipt = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   monotonic=time.monotonic(), BOOT_sha256=BOOT_SHA256,
                   payload_sha256=PAYLOAD_SHA256, FPGA_loads=0)
    (ROOT / 'boot_start.json').write_text(json.dumps(receipt, indent=2) + '\n')
    os.chmod(str(ROOT / 'boot_start.json'), 0o644)
    # bootpy.service is oneshot: return promptly, rather than letting its start
    # timeout terminate a long-running DMA owner. Only RAM transient state changes.
    command = ['/usr/bin/systemd-run', '--unit=ray-game-autostart',
               '--description=Ray game HDMI menu', '--property=Type=simple',
               '--property=Restart=no', '--property=KillMode=mixed',
               '--property=SendSIGKILL=no', '--property=TimeoutStopSec=infinity',
               '/usr/bin/python3', '-B', '-u', str(ROOT / 'autostart.py')]
    subprocess.check_call(command, timeout=20)
    print('RAY_GAME_AUTOSTART_QUEUED; readiness is recorded in runtime receipt', flush=True)


if __name__ == '__main__':
    main()
