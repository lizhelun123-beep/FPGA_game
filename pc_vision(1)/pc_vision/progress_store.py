"""Per-account best scores and a durable, coalescing cloud upload queue."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class ProgressStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS progress (
                user_id TEXT NOT NULL,
                level_id INTEGER NOT NULL CHECK(level_id BETWEEN 1 AND 3),
                best_stars INTEGER NOT NULL CHECK(best_stars BETWEEN 1 AND 3),
                best_elapsed_ms INTEGER NOT NULL CHECK(best_elapsed_ms >= 0 AND best_elapsed_ms < 180000),
                revision INTEGER NOT NULL,
                synced_revision INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, level_id))''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def validate(user_id, level_id, stars, elapsed_ms):
        if not isinstance(user_id, str) or not user_id or len(user_id) > 255:
            raise ValueError('Invalid account identity')
        if type(level_id) is not int or not 1 <= level_id <= 3:
            raise ValueError('Only playable levels have progress')
        if type(stars) is not int or not 1 <= stars <= 3:
            raise ValueError('Only cleared C results have best scores')
        if type(elapsed_ms) is not int or not 0 <= elapsed_ms < 180000:
            raise ValueError('Invalid cleared time')
        expected = 3 if elapsed_ms < 60000 else 2 if elapsed_ms < 120000 else 1
        if stars != expected:
            raise ValueError('Score does not match the current C time thresholds')

    def save_cleared(self, user_id, level_id, stars, elapsed_ms):
        self.validate(user_id, level_id, stars, elapsed_ms)
        with self.connection() as db:
            db.execute('''INSERT INTO progress
                (user_id, level_id, best_stars, best_elapsed_ms, revision)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(user_id,level_id) DO UPDATE SET
                    best_stars=MAX(progress.best_stars,excluded.best_stars),
                    best_elapsed_ms=MIN(progress.best_elapsed_ms,excluded.best_elapsed_ms),
                    revision=progress.revision+1
                WHERE excluded.best_stars>progress.best_stars
                   OR excluded.best_elapsed_ms<progress.best_elapsed_ms''',
                (user_id, level_id, stars, elapsed_ms))

    def records(self, user_id):
        with self.connection() as db:
            return [dict(row) for row in db.execute('''SELECT level_id,best_stars,best_elapsed_ms,
                revision,synced_revision FROM progress WHERE user_id=? ORDER BY level_id''', (user_id,))]

    def pending(self, user_id):
        return [row for row in self.records(user_id) if row['revision'] > row['synced_revision']]

    def mark_synced(self, user_id, level_id, revision):
        # An old upload acknowledgement cannot clear a newer unsynced result.
        with self.connection() as db:
            db.execute('''UPDATE progress SET synced_revision=revision
                WHERE user_id=? AND level_id=? AND revision=?''', (user_id, level_id, revision))

    def merge_remote(self, user_id, records):
        for remote in records:
            level, stars, elapsed = remote['level_id'], remote['best_stars'], remote['best_elapsed_ms']
            self.validate(user_id, level, stars, elapsed)
            self.save_cleared(user_id, level, stars, elapsed)
            local = next(row for row in self.records(user_id) if row['level_id'] == level)
            if (local['best_stars'], local['best_elapsed_ms']) == (stars, elapsed):
                self.mark_synced(user_id, level, local['revision'])
