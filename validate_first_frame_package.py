import hashlib
import json
import tarfile

path = 'output/build/game_app/park_boundary_first_frame_1/live075_first_frame.tar.gz'
with tarfile.open(path, 'r:gz') as archive:
    names = archive.getnames()
    assert 'capture_worker.py' in names
    worker = archive.extractfile('capture_worker.py').read()
    compile(worker, 'capture_worker.py', 'exec')
    manifest = json.loads(archive.extractfile('capture_package.json').read())
    worker_sha = hashlib.sha256(worker).hexdigest()
    assert worker_sha == manifest['files']['capture_worker.py']
print(json.dumps({'members': names, 'worker_sha256': worker_sha,
                  'contract': manifest['diagnostic_contract']}, sort_keys=True))
