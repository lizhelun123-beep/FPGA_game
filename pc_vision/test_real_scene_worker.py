"""Fake-source/thread checks only; no camera, native executable or board."""
import copy
import queue
import threading
import time
import unittest

import numpy as np

from .real_scene import OverlayRetention, OverlayStreamWorker
from .scene_protocol import Scene


class Clock:
    def __init__(self):
        self.value = 1000
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.value

    def set(self, value):
        with self.lock:
            self.value = value


class QueueCapture:
    def __init__(self):
        self.queue = queue.Queue()
        self.read_count = 0
        self.owner = None
        self.released = threading.Event()

    def isOpened(self):
        self.owner = threading.get_ident()
        return True

    def read(self):
        assert threading.get_ident() == self.owner
        self.read_count += 1
        value = self.queue.get()
        return (False, None) if value is None else (True, value)

    def release(self):
        assert threading.get_ident() == self.owner
        self.released.set()

    def put(self, value):
        self.queue.put(np.full((720, 1280, 3), value, np.uint8))


class FakeNative:
    def __init__(self, gate=None):
        self.owner = threading.get_ident()
        self.calls = []
        self.generation = 0
        self.selects = self.commits = self.ticks = 0
        self.observed = []
        self.observing = threading.Event()
        self.gate = gate
        self.started = None

    def check(self, operation):
        assert threading.get_ident() == self.owner, "native pipe changed owners"
        self.calls.append(operation)

    def select(self, level, now):
        self.check("select")
        self.generation += 1
        self.selects += 1
        self.started = None
        self.state = dict(status=0, state=1, level=level, generation=self.generation,
            sequence=0, captured_ms=0, valid=0, ready=0, elapsed_ms=0,
            remaining_ms=180000, stars=0, objects=[], segments=[])
        return copy.deepcopy(self.state)

    def observe(self, pixels, generation, sequence, captured_ms, algorithm, now_ms):
        self.check("observe")
        value = int(pixels[0, 0, 0])
        self.observed.append((generation, sequence, captured_ms, now_ms, value))
        self.observing.set()
        if self.gate is not None:
            self.gate.wait(2)
        assert int(pixels[0, 0, 0]) == value, "capture reused a published buffer"
        self.pending = (generation, sequence, captured_ms)
        return Scene(sequence, sequence, captured_ms, True, (1280, 720), ())

    def commit(self, now):
        self.check("commit")
        self.commits += 1
        generation, sequence, captured = self.pending
        assert generation == self.generation
        self.state.update(valid=1, ready=1, sequence=sequence, captured_ms=captured,
            objects=[[0, 100, 100, 1, 0, 20, 2]], segments=[[0, 0, 50, 50]])
        return copy.deepcopy(self.state)

    def portal_tags(self):
        self.check("tags")
        return []

    def tick(self, now):
        self.check("tick")
        self.ticks += 1
        if self.started is not None:
            self.state.update(elapsed_ms=now-self.started,
                remaining_ms=max(0, 180000-(now-self.started)))
        if self.state["valid"] and now-self.state["captured_ms"] > 250:
            self.state.update(valid=0, ready=0, objects=[], segments=[])
        return copy.deepcopy(self.state)

    def start(self, now):
        self.check("start")
        self.started = now
        self.state["state"] = 2
        return copy.deepcopy(self.state)

    def close(self):
        self.check("close")


def wait_for(predicate, timeout=2):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.005)
    raise AssertionError("Worker condition was not reached")


class StreamWorkerTests(unittest.TestCase):
    def make_worker(self, gate=None):
        self.clock = Clock()
        self.capture = QueueCapture()
        self.holder = {}

        def factory():
            self.holder["native"] = FakeNative(gate)
            return self.holder["native"]
        self.worker = OverlayStreamWorker(factory, lambda: self.capture, self.clock)
        self.worker.start()
        self.assertTrue(self.worker.ready.wait(2))
        self.native = self.holder["native"]
        return self.worker

    def tearDown(self):
        if hasattr(self, "worker"):
            if self.native.gate is not None:
                self.native.gate.set()
            self.worker.close()
            self.capture.queue.put(None)
            self.capture.released.wait(1)

    def test_blocked_read_keeps_native_timer_and_display_expiry_running(self):
        worker = self.make_worker()
        self.capture.put(1)
        wait_for(lambda: self.native.commits == 1)
        good = wait_for(lambda: (u if (u := worker.poll()) is not None and u.snapshot["valid"] else None))
        hold = OverlayRetention(dict(dropout_seconds=.25, stale_seconds=.25, timeout_seconds=6))
        hold.update(good.snapshot)
        wait_for(lambda: self.capture.read_count >= 2)  # blocked indefinitely
        worker.request_start()
        wait_for(lambda: self.native.started is not None)
        self.clock.set(1301)
        stale = wait_for(lambda: (u if (u := worker.poll()) is not None and not u.snapshot["valid"] else None))
        self.assertLess(stale.snapshot["remaining_ms"], 180000)
        shown, dim = hold.display(stale.snapshot, self.clock())
        self.assertTrue(dim)
        self.assertEqual(shown["captured_ms"], 1000)
        self.assertEqual(shown["remaining_ms"], stale.snapshot["remaining_ms"])
        self.assertEqual(shown["state"], 2)
        self.clock.set(7001)
        cleared, _ = hold.display(stale.snapshot, self.clock())
        self.assertEqual(cleared["segments"], [])
        ticks = self.native.ticks
        wait_for(lambda: self.native.ticks > ticks)
        started = time.monotonic()
        worker.close()
        self.assertLess(time.monotonic()-started, 1)
        self.assertFalse(self.capture.released.is_set())  # no unsafe release/read race

    def test_select_discards_capture_dispatched_for_old_generation(self):
        worker = self.make_worker()
        self.capture.put(1)
        wait_for(lambda: self.native.commits == 1 and self.capture.read_count >= 2)
        epoch = worker.select(2)
        wait_for(lambda: self.native.selects == 2)
        self.clock.set(1100)
        self.capture.put(2)  # read had already frozen generation 1
        wait_for(lambda: self.capture.read_count >= 3)
        self.clock.set(1101)
        self.capture.put(3)
        wait_for(lambda: self.native.commits == 2)
        update = wait_for(lambda: (u if (u := worker.poll()) is not None and u.sequence == 3 else None))
        self.assertEqual(update.epoch, epoch)
        self.assertEqual(update.snapshot["level"], 2)
        self.assertEqual([row[:2] for row in self.native.observed], [(1, 1), (2, 3)])
        self.assertGreaterEqual(worker.rejected_old, 1)
        self.assertEqual(self.native.observed[-1][2], 1100)  # never re-stamped at delivery
        self.assertEqual(self.native.observed[-1][3], 1101)
        with self.assertRaises(TypeError):
            update.snapshot["level"] = 3
        with self.assertRaises(ValueError):
            update.frame[0, 0, 0] = 5

    def test_select_during_slow_detection_cannot_commit_old_result(self):
        gate = threading.Event()
        worker = self.make_worker(gate)
        self.capture.put(1)
        self.assertTrue(self.native.observing.wait(1))
        started = time.monotonic()
        epoch = worker.select(2)
        self.assertLess(time.monotonic()-started, .05)
        self.assertIsNone(worker.poll())
        gate.set()
        wait_for(lambda: self.native.selects == 2)
        update = wait_for(lambda: worker.poll())
        self.assertEqual(update.epoch, epoch)
        self.assertEqual(self.native.commits, 0)
        self.assertFalse(update.snapshot["valid"])

    def test_latest_input_slot_is_bounded_under_backpressure(self):
        gate = threading.Event()
        worker = self.make_worker(gate)
        self.capture.put(1)
        self.assertTrue(self.native.observing.wait(1))
        for value in range(2, 22):
            self.capture.put(value)
        wait_for(lambda: self.capture.read_count >= 22)
        with worker.condition:
            packet = worker.latest_input
            self.assertEqual(packet.sequence, 21)
            self.assertEqual(int(packet.pixels[0, 0, 0]), 21)
            self.assertGreaterEqual(worker.overwritten, 19)
        gate.set()
        wait_for(lambda: self.native.commits == 2)
        self.assertEqual([row[1] for row in self.native.observed], [1, 21])


if __name__ == "__main__":
    unittest.main()
