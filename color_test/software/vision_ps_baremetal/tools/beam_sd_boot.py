#!/usr/bin/env python3
"""Generated PYNQ boot.py template for the fixed-emitter beam test."""
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


def safe_members(archive):
    members = archive.getmembers()
    names = [member.name for member in members]
    if len(names) != len(set(names)) or not 1 <= len(names) <= 64:
        raise ValueError('invalid beam archive member set')
    total = 0
    for member in members:
        name = member.name.replace('\\', '/')
        parts = Path(name).parts
        if (not member.isfile() or name.startswith('/') or name.endswith('/') or
                any(part in ('', '.', '..') for part in parts) or
                name != member.name or member.size < 0):
            raise ValueError('unsafe beam archive member')
        total += member.size
    if total > 96 * 1024 * 1024:
        raise ValueError('beam archive too large')
    return members


def stage(boot, root, expected_payload, expected_boot):
    if sha((boot / 'BOOT.BIN').read_bytes()) != expected_boot:
        raise ValueError('BOOT identity mismatch; no service/device access')
    payload = (boot / 'beam_runtime.tar.gz').read_bytes()
    if len(payload) > 48 * 1024 * 1024 or sha(payload) != expected_payload:
        raise ValueError('beam payload mismatch; no service/device access')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        members = safe_members(archive)
        data = {member.name: archive.extractfile(member).read() for member in members}
    manifest = json.loads(data['package.json'].decode('utf-8'))
    files = manifest.get('files', {})
    if (set(files) - set(data) or
            any(sha(data[name]) != digest for name, digest in files.items())):
        raise ValueError('capture package hash mismatch')
    extras = set(data) - set(files) - {'package.json'}
    if any(not name.startswith('beam') for name in extras):
        raise ValueError('unexpected beam package member')
    if root.exists() or root.is_symlink():
        raise ValueError('beam runtime already exists; no retry')
    root.mkdir(mode=0o755, parents=True)
    os.chmod(str(root.parent), 0o755)
    os.chmod(str(root), 0o755)
    for name, value in data.items():
        target = root / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(value)
        os.chmod(str(target), 0o755 if name in ('beam720', 'beam_runtime.py') else 0o644)
    return manifest


def main():
    if os.geteuid() != 0:
        raise RuntimeError('beam boot.py must execute as root')
    for path in (ROOT.parent, ROOT):
        if path.exists() or path.is_symlink():
            st = path.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid or st.st_mode & 0o022:
                raise ValueError('unprotected beam runtime directory')
    manifest = stage(Path('/boot'), ROOT, PAYLOAD_SHA256, BOOT_SHA256)
    receipt = dict(status='STAGED', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   monotonic=time.monotonic(), BOOT_sha256=BOOT_SHA256,
                   payload_sha256=PAYLOAD_SHA256, FPGA_loads=0,
                   capture_format=manifest.get('format'))
    (ROOT / 'boot_start.json').write_text(json.dumps(receipt, indent=2) + '\n')
    os.chmod(str(ROOT / 'boot_start.json'), 0o644)
    command = ['/usr/bin/systemd-run', '--unit=ray-game-autostart',
               '--description=Ray game HDMI beam test', '--property=Type=simple',
               '--property=Restart=no', '--property=KillMode=mixed',
               '--property=SendSIGKILL=no', '--property=TimeoutStopSec=infinity',
               '/usr/bin/python3', '-B', '-u', str(ROOT / 'autostart.py')]
    subprocess.check_call(command, timeout=20)
    print('RAY_GAME_AUTOSTART_QUEUED_BEAM720', flush=True)


if __name__ == '__main__':
    main()
