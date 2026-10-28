"""File-only autostart package acceptance and fail-closed staging fixtures."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('boot_entry', Path(__file__).resolve().parents[1] / 'tools/game_sd_boot.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
SD = REPO / 'output/sd_autostart'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tar(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data, link in members:
            info = tarfile.TarInfo(name)
            if link:
                info.type = tarfile.SYMTYPE
                info.linkname = '/dev/mem'
            else:
                info.size = len(data)
            archive.addfile(info, None if link else io.BytesIO(data))
    return buffer.getvalue()


class BootStaging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.boot = self.base / 'boot'
        self.boot.mkdir()
        self.root = self.base / 'run' / 'continuous'
        self.binary = (SD / 'BOOT.BIN').read_bytes()
        self.payload = (SD / 'ray_game_autostart.tar.gz').read_bytes()
        (self.boot / 'BOOT.BIN').write_bytes(self.binary)
        (self.boot / 'ray_game_autostart.tar.gz').write_bytes(self.payload)

    def stage(self, payload=None):
        if payload is not None:
            (self.boot / 'ray_game_autostart.tar.gz').write_bytes(payload)
        return entry.stage(self.boot, self.root, sha(self.payload if payload is None else payload), sha(self.binary))

    def test_real_package_and_no_second_attempt(self):
        package = self.stage()
        self.assertEqual(set(p.name for p in self.root.iterdir()), set(package['files']) | {'package.json'})
        for name, digest in package['files'].items():
            self.assertEqual(sha((self.root / name).read_bytes()), digest)
        self.assertEqual(package['software_scope'], 'boot5_menu_only')
        with self.assertRaisesRegex(ValueError, 'already has a display attempt'):
            self.stage()

    def test_wrong_boot_rejected_before_creating_runtime(self):
        (self.boot / 'BOOT.BIN').write_bytes(self.binary + b'x')
        with self.assertRaisesRegex(ValueError, 'BOOT identity'):
            self.stage()
        self.assertFalse(self.root.exists())

    def test_corrupted_archive_rejected_before_creating_runtime(self):
        (self.boot / 'ray_game_autostart.tar.gz').write_bytes(self.payload + b'x')
        with self.assertRaisesRegex(ValueError, 'payload mismatch'):
            entry.stage(self.boot, self.root, sha(self.payload), sha(self.binary))
        self.assertFalse(self.root.exists())

    def test_unsafe_members_rejected_before_any_extraction(self):
        cases = [[('../escape', b'x', False)], [('/absolute', b'x', False)],
                 [('nested/file', b'x', False)], [('link', b'', True)],
                 [('duplicate', b'a', False), ('duplicate', b'b', False)]]
        for members in cases:
            with self.subTest(members=members):
                with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                    self.stage(tar(members))
                self.assertFalse(self.root.exists())

    def test_inner_hash_mismatch_rejected_before_extraction(self):
        package = json.dumps({'files': {'program': sha(b'good')}}).encode()
        payload = tar([('package.json', package, False), ('program', b'bad', False)])
        with self.assertRaisesRegex(ValueError, 'Package file mismatch'):
            self.stage(payload)
        self.assertFalse(self.root.exists())

    def test_generated_boot_entry_and_zip_match(self):
        source = (SD / 'boot.py').read_text()
        compile(source, 'generated_boot.py', 'exec')
        self.assertNotIn('__PAYLOAD_SHA256__', source)
        self.assertIn(sha(self.payload), source)
        self.assertIn(sha(self.binary), source)
        with zipfile.ZipFile(REPO / 'output/ray_game_SD_autostart.zip') as archive:
            self.assertIsNone(archive.testzip())
            for name in ('BOOT.BIN', 'boot.py', 'ray_game_autostart.tar.gz'):
                self.assertEqual(archive.read(name), (SD / name).read_bytes())

    def test_arm32_capability_word_positions(self):
        # Real board value from cold_boot_1/input_details.json.
        words = '70000 0 0 0 0 0 0 0 0'.split()
        value = 0
        for index, token in enumerate(reversed(words)):
            value |= int(token, 16) << (32 * index)
        self.assertTrue(value & (1 << 272))
        self.assertFalse(int(''.join(words), 16) & (1 << 272))


if __name__ == '__main__':
    unittest.main()
