#!/usr/bin/env python3
"""Stage the capture bridge and run the static fixed-emitter beam binary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

SOURCE = Path(__file__).resolve().parent
CAPTURE = Path('/run/game_live_camera/capture')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def stage_capture():
    with tarfile.open(str(SOURCE / 'beam_capture.tar.gz'), 'r:gz') as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if (len(names) != len(set(names)) or
                any(not member.isfile() or member.name.startswith('/') or
                    '..' in Path(member.name).parts for member in members)):
            raise RuntimeError('unsafe beam capture archive')
        data = {member.name: archive.extractfile(member).read() for member in members}
    manifest = json.loads(data['capture_package.json'].decode('utf-8'))
    files = manifest['files']
    if CAPTURE.exists():
        raise RuntimeError('capture runtime already exists; stop the previous owner first')
    print('BEAM_CAPTURE_STAGE_BEGIN', flush=True)
    CAPTURE.mkdir(mode=0o755, parents=True)
    for name, digest in files.items():
        if name not in data:
            raise RuntimeError('capture package hash mismatch: ' + name)
        if hashlib.sha256(data[name]).hexdigest() != digest:
            raise RuntimeError('capture package hash mismatch: ' + name)
    for name, value in data.items():
        target = CAPTURE / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(value)
        os.chmod(str(target), 0o644)
    for name in ('boot_start.json', 'load_receipt.json'):
        source = SOURCE / name
        target = CAPTURE / name
        if not source.is_file():
            raise RuntimeError('missing fresh qualification receipt: ' + name)
        with target.open('xb') as output:
            output.write(source.read_bytes())
        os.chmod(str(target), 0o644)
    print('BEAM_CAPTURE_STAGE_READY', flush=True)
    os.chmod(str(CAPTURE), 0o755)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=180)
    args = parser.parse_args()
    if os.geteuid() != 0 or not 5 <= args.duration <= 180:
        raise SystemExit(2)
    stage_capture()
    os.execv(str(SOURCE / 'beam720'), ['beam720', '--beam720', str(args.duration)])


if __name__ == '__main__':
    main()
