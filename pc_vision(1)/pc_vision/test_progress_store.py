"""No cloud or real player data; temporary databases stay under project output."""
from pathlib import Path
import tempfile
import unittest

from .progress_store import ProgressStore


class ProgressTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent / 'output/progress_tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.temp.name) / 'scores.sqlite3'
        self.store = ProgressStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_best_only_idempotent_and_account_isolation(self):
        self.store.save_cleared('alice', 1, 1, 150000)
        self.store.save_cleared('alice', 1, 3, 45000)
        self.store.save_cleared('alice', 1, 2, 90000)
        self.store.save_cleared('alice', 1, 3, 45000)
        self.store.save_cleared('bob', 1, 2, 70000)
        alice = self.store.records('alice')[0]
        self.assertEqual((alice['best_stars'], alice['best_elapsed_ms'], alice['revision']), (3, 45000, 2))
        self.assertEqual(self.store.records('bob')[0]['best_elapsed_ms'], 70000)
        self.assertEqual(len(self.store.records('alice')), 1)

    def test_stale_ack_and_restart_preserve_pending(self):
        self.store.save_cleared('alice', 2, 2, 100000)
        revision = self.store.pending('alice')[0]['revision']
        self.store.save_cleared('alice', 2, 3, 20000)
        self.store.mark_synced('alice', 2, revision)
        reopened = ProgressStore(self.path)
        self.assertEqual(reopened.pending('alice')[0]['best_elapsed_ms'], 20000)
        reopened.mark_synced('alice', 2, reopened.pending('alice')[0]['revision'])
        self.assertEqual(reopened.pending('alice'), [])

    def test_cloud_merge_keeps_better_local_and_remote_scores(self):
        self.store.save_cleared('alice', 1, 3, 20000)
        self.store.merge_remote('alice', [dict(level_id=1, best_stars=2, best_elapsed_ms=80000),
                                         dict(level_id=2, best_stars=3, best_elapsed_ms=30000)])
        self.assertEqual([row['level_id'] for row in self.store.pending('alice')], [1])
        self.store.merge_remote('alice', [dict(level_id=1, best_stars=3, best_elapsed_ms=10000)])
        self.assertEqual(self.store.pending('alice'), [])
        self.assertEqual(self.store.records('alice')[0]['best_elapsed_ms'], 10000)

    def test_previews_timeouts_and_invalid_scores_rejected(self):
        for level, stars, elapsed in [(4,3,10000),(1,0,180000),(1,3,70000),(True,3,10000)]:
            with self.subTest(level=level, stars=stars):
                with self.assertRaises(ValueError):
                    self.store.save_cleared('alice', level, stars, elapsed)
        self.assertEqual(self.store.records('alice'), [])


if __name__ == '__main__':
    unittest.main()
