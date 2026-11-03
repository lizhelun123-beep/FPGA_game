import hashlib
import io
import json
import tarfile
from pathlib import Path

BASE = Path('output/build/game_app/park_boundary_first_fault_1/live075_first_fault.tar.gz')
OUT_DIR = Path('output/build/game_app/park_boundary_first_frame_1')
OUT = OUT_DIR / 'live075_first_frame.tar.gz'

needle = "def serve(session, incoming, output, diagnostics):\n    def checked(operation, call):\n"
replacement = """def serve(session, incoming, output, diagnostics):
    def fault_csi_snapshot():
        # Same-owner diagnostic: complete the existing CSI snapshot handshake
        # before main() enters sensor/DMA cleanup. No second observer process
        # touches the CSI snapshot registers.
        try:
            result = dict(session.csi.snapshot())
            result['observation'] = 'same_owner_before_cleanup'
            return result
        except Exception as snapshot_error:
            direct = {}
            try:
                direct = {hex(offset): session.csi.regs.read(offset)
                          for offset in (0x00, 0x04, 0x08, 0x0c, 0x10, 0x14)}
            except Exception as direct_error:
                direct = {'error': repr(direct_error)}
            return {'snapshot_error': repr(snapshot_error), 'direct': direct,
                    'observation': 'same_owner_direct_fallback'}

    def checked(operation, call):
"""
worker_fault_marker = "                'first_sample': getattr(exc, 'snapshot', None),\n"
worker_fault_replacement = (
    "                'first_sample': getattr(exc, 'snapshot', None),\n"
    "                'fault_csi': fault_csi_snapshot(),\n")

def sha(data):
    return hashlib.sha256(data).hexdigest()

OUT_DIR.mkdir(parents=True, exist_ok=True)
with tarfile.open(str(BASE), 'r:gz') as source:
    members = {}
    for member in source.getmembers():
        if member.isfile():
            members[member.name] = (member, source.extractfile(member).read())

worker_member, worker = members['capture_worker.py']
worker_text = worker.decode('utf-8')
if needle not in worker_text or worker_fault_marker not in worker_text:
    raise RuntimeError('unexpected worker diagnostic source')
worker_text = worker_text.replace(needle, replacement, 1)
worker_text = worker_text.replace(worker_fault_marker, worker_fault_replacement, 1)
worker = worker_text.encode('utf-8')
members['capture_worker.py'] = (worker_member, worker)

manifest_member, manifest_bytes = members['capture_package.json']
manifest = json.loads(manifest_bytes.decode('utf-8'))
manifest['files']['capture_worker.py'] = sha(worker)
manifest['diagnostic_contract'] = 'first_failed_CR_SR_PARK_and_same_owner_CSI_snapshot_before_cleanup;poll_acquire_ack_context;no_acceptance_change'
manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8')
members['capture_package.json'] = (manifest_member, manifest_bytes)

with tarfile.open(str(OUT), 'w:gz') as target:
    for name in sorted(members):
        member, data = members[name]
        info = tarfile.TarInfo(name)
        info.mode = member.mode
        info.uid = member.uid
        info.gid = member.gid
        info.mtime = member.mtime
        info.size = len(data)
        target.addfile(info, io.BytesIO(data))

print(json.dumps({'output': str(OUT), 'bytes': OUT.stat().st_size,
                  'sha256': sha(OUT.read_bytes()),
                  'worker_sha256': sha(worker)}, sort_keys=True))

