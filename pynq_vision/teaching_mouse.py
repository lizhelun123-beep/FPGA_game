"""Linux相对鼠标独占读取；signed value、SYN_REPORT、丢事件取消笔划。"""
from collections import deque
import os
from pathlib import Path
import select
import stat
import struct
import threading


class LinuxMouse:
    EVENT = struct.Struct('@llHHi')

    def __init__(self, path):
        self.path = str(Path(path).resolve())
        if not self.path.startswith('/dev/input/event'):
            raise ValueError('explicit /dev/input/event mouse required')
        self.fd = -1; self.error = None; self.queue = deque(); self.lock = threading.Lock()
        self.stop = threading.Event(); self.thread = None
        import fcntl
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode): raise ValueError('mouse is not a character device')
            def bits(kind, size):
                result = bytearray(size)
                fcntl.ioctl(self.fd, 0x80004520 | (size << 16) | kind, result, True)
                return result
            rel, key = bits(2, 8), bits(1, 96)
            if rel[0] & 3 != 3 or not key[0x110//8] & (1 << (0x110 % 8)):
                raise ValueError('device must support REL_X/Y and BTN_LEFT')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(self.fd, 0x40044590, 1)  # EVIOCGRAB，不抢占已有所有者
            self.thread = threading.Thread(target=self._run, name='teaching-mouse')
            self.thread.daemon = True; self.thread.start()
        except BaseException:
            self.close(); raise

    def _push(self, report):
        with self.lock:
            if len(self.queue) >= 2048:
                self.queue.clear(); self.queue.append((0, 0, False, True))
            self.queue.append(report)

    def _run(self):
        import fcntl
        buffer = bytearray(); dx = dy = 0; left = False; dropped = False
        # 启动时已按住左键，等释放后才接受下一次按下。
        keys = bytearray(96)
        try:
            fcntl.ioctl(self.fd, 0x80604518, keys, True)
            suppress = bool(keys[0x110//8] & 1)
            while not self.stop.is_set():
                if not select.select([self.fd], [], [], .02)[0]: continue
                try: data = os.read(self.fd, self.EVENT.size*256)
                except BlockingIOError: continue
                if not data: raise OSError('mouse disconnected')
                buffer.extend(data)
                while len(buffer) >= self.EVENT.size:
                    _, _, kind, code, value = self.EVENT.unpack_from(buffer)
                    del buffer[:self.EVENT.size]
                    if kind == 0 and code == 3: dropped = True; dx = dy = 0
                    elif kind == 0 and code == 0:
                        if dropped:
                            fcntl.ioctl(self.fd, 0x80604518, keys, True)
                            left = bool(keys[0x110//8] & 1); suppress = left
                            self._push((0, 0, False, True)); dropped = False
                        else:
                            if not left: suppress = False
                            self._push((dx, dy, left and not suppress, False))
                        dx = dy = 0
                    elif not dropped:
                        if kind == 2 and code == 0: dx += value
                        elif kind == 2 and code == 1: dy += value
                        elif kind == 1 and code == 0x110 and value in (0, 1): left = bool(value)
        except OSError as error:
            self.error = str(error); self._push((0, 0, False, True))

    def poll(self):
        with self.lock:
            result = list(self.queue); self.queue.clear()
        return result

    def close(self):
        self.stop.set()
        if self.thread is not None: self.thread.join(timeout=1)
        if self.fd >= 0:
            import fcntl
            try: fcntl.ioctl(self.fd, 0x40044590, 0)
            except OSError: pass
            os.close(self.fd); self.fd = -1
