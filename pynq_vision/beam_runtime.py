"""Python 3.6 entry for the migrated v14 board C core; no PC/web imports.

Import/--check do not import PYNQ, open UART, allocate DMA or load PL.
The real capture/display owner is deliberately supplied by the hardware layer;
the old unqualified CameraPipeline is NOT an automatic fallback.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import time
import sys

WIDTH, HEIGHT, ROW = 1280, 720, 3840
FRAME_BYTES, PACKET_BYTES = ROW * HEIGHT, 174
BytePointer = C.POINTER(C.c_uint8)
Clock = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(C.c_uint64))


class DisplayFault(RuntimeError):
    """显示提交或退休短暂失败时使用的可重试异常。"""


class Result(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        "ticket", "generation", "sequence", "captured_ms", "shown_generation",
        "shown_sequence", "shown_captured_ms")]
    _fields_ += [(name, C.c_uint32) for name in (
        "struct_size", "status", "detections", "valid", "display_stale",
        "pose_bytes", "ray_segments", "raw_mask", "pending_mask", "missing_mask")]


class CapturedFrame:
    """Independent CPU bytes AFTER full-frame retirement/cache synchronization.

    Constructing this value grants no DMA ownership. The hardware owner must
    perform the actual proof before copying bytes; ndarray/PynqBuffer/device
    views are not accepted as an alternative to that copy.
    """
    def __init__(self, bgr, generation, sequence, captured_ms, stride=ROW):
        if type(bgr) not in (bytes, bytearray):
            raise TypeError("capture must supply independent CPU bytes")
        for value in (generation, sequence, captured_ms):
            if type(value) is not int or not 0 < value < (1 << 64):
                raise ValueError("original nonzero 64-bit capture identity required")
        if type(stride) is not int or stride < ROW or len(bgr) < (HEIGHT - 1) * stride + ROW:
            raise ValueError("truncated BGR frame/stride")
        self.bgr, self.generation, self.sequence = bgr, generation, sequence
        self.captured_ms, self.stride = captured_ms, stride


def load_library(path):
    lib = C.CDLL(str(Path(path).resolve()))
    specs = {
        "beam_pynq_abi": (C.c_uint, []),
        "beam_pynq_result_size": (C.c_size_t, []),
        "beam_pynq_open": (C.c_void_p, [C.c_uint64, Clock, C.c_void_p]),
        "beam_pynq_close": (None, [C.c_void_p]),
        "beam_pynq_receive": (C.c_int, [C.c_void_p, C.c_uint, BytePointer, C.c_size_t]),
        "beam_pynq_frame": (C.c_int, [C.c_void_p, BytePointer, C.c_uint, C.c_uint,
            C.c_size_t, C.c_size_t, C.c_uint64, C.c_uint64, C.c_uint64,
            C.POINTER(Result), BytePointer, C.c_size_t]),
        "beam_pynq_canvas": (BytePointer, [C.c_void_p]),
        "beam_pynq_submitted": (C.c_int, [C.c_void_p, C.c_uint64]),
        "beam_pynq_retired": (C.c_int, [C.c_void_p, C.c_uint64, BytePointer, C.c_size_t]),
        "beam_pynq_clock_ms": (C.c_int, [C.c_void_p, C.POINTER(C.c_uint64)]),
        "beam_pynq_uart_open": (C.c_int, [C.c_char_p]),
        "beam_pynq_uart_read": (C.c_int, [C.c_int, BytePointer, C.c_size_t]),
        "beam_pynq_uart_write": (C.c_int, [C.c_int, BytePointer, C.c_size_t]),
        "beam_pynq_uart_close": (C.c_int, [C.c_int]),
    }
    for name, (result, arguments) in specs.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = result, arguments
    if lib.beam_pynq_abi() != 1 or lib.beam_pynq_result_size() != C.sizeof(Result):
        raise RuntimeError("board C ABI/layout mismatch")
    return lib


class Beam:
    def __init__(self, library, generation, clock_ms=None):
        self.lib = load_library(library)
        self.handle = None
        self._callback_error = None
        if type(generation) is not int or not 0 < generation < (1 << 64):
            raise ValueError("capture owner must provide its generation")
        if clock_ms is None:
            self._clock = Clock(("beam_pynq_clock_ms", self.lib))
        else:
            # Explicit clock injection is for CPU fixtures or an owner whose
            # original capture stamps use this exact same monotonic clock.
            def sample(unused, output):
                try:
                    value = clock_ms()
                    if type(value) is not int or not 0 <= value < (1 << 64):
                        raise ValueError("invalid monotonic clock")
                    output[0] = value
                    return 0
                except Exception as error:
                    self._callback_error = error
                    return -1
            self._clock = Clock(sample)
        self.handle = self.lib.beam_pynq_open(generation, self._clock, None)
        if not self.handle:
            raise RuntimeError("C core initialization rejected (clock/config/single owner)")

    def _live(self):
        if not self.handle:
            raise RuntimeError("C core closed")

    def close(self):
        if self.handle:
            self.lib.beam_pynq_close(self.handle)
            self.handle = None

    def receive(self, data):
        self._live()
        replies = []
        output = (C.c_uint8 * PACKET_BYTES)()
        for byte in data:
            length = self.lib.beam_pynq_receive(self.handle, byte, output, len(output))
            if length < 0:
                raise RuntimeError("serial service outside scene boundary or clock failure")
            if length:
                replies.append(bytes(output[:length]))
        return replies

    def frame(self, captured):
        self._live()
        if not isinstance(captured, CapturedFrame):
            raise TypeError("CapturedFrame required")
        bgr = captured.bgr
        if type(bgr) is bytearray:
            storage = (C.c_uint8 * len(bgr)).from_buffer(bgr)
        else:
            storage = C.cast(C.c_char_p(bgr), BytePointer)
        pose = (C.c_uint8 * PACKET_BYTES)()
        result = Result()
        code = self.lib.beam_pynq_frame(self.handle, storage, WIDTH, HEIGHT,
            captured.stride, len(bgr), captured.generation, captured.sequence,
            captured.captured_ms, C.byref(result), pose, len(pose))
        if code:
            raise RuntimeError("C frame rejected: geometry/time/identity/lifecycle")
        canvas = self.lib.beam_pynq_canvas(self.handle)
        if not canvas:
            raise RuntimeError("complete CPU canvas unavailable")
        return result, C.string_at(canvas, FRAME_BYTES), bytes(pose[:result.pose_bytes])

    def submitted(self, ticket):
        self._live()
        if self.lib.beam_pynq_submitted(self.handle, ticket):
            raise RuntimeError("display submission ticket rejected")

    def retired(self, ticket):
        self._live()
        output = (C.c_uint8 * PACKET_BYTES)()
        length = self.lib.beam_pynq_retired(self.handle, ticket, output, len(output))
        if length < 0:
            raise RuntimeError("display retirement ticket rejected")
        return bytes(output[:length])


class SerialPort:
    """Explicit POSIX UART owner. No pyserial or Python>=3.9 dependency."""
    def __init__(self, library, path):
        self.lib = load_library(library)
        self.fd = self.lib.beam_pynq_uart_open(str(path).encode("utf-8"))
        if self.fd < 0:
            raise RuntimeError("UART rejected: path/console/exclusivity/termios; no service changed")

    def read(self):
        storage = (C.c_uint8 * 64)()
        n = self.lib.beam_pynq_uart_read(self.fd, storage, len(storage))
        if n < 0:
            raise RuntimeError("UART read failed")
        return bytes(storage[:n])

    def write_packet(self, packet):
        if not packet:
            return
        storage = (C.c_uint8 * len(packet)).from_buffer_copy(packet)
        if self.lib.beam_pynq_uart_write(self.fd, storage, len(packet)):
            raise RuntimeError("bounded UART packet write failed")

    def close(self):
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            if self.lib.beam_pynq_uart_close(fd):
                raise RuntimeError("UART close/restore failed")


def run(owner, beam, uart, stopping, teaching=None):
    """Run against ONE reviewed PYNQ capture/display owner, all calls serial.

    Required owner methods: prepare(), capture_cpu()->CapturedFrame,
    check_capture(), submit_cpu(bytes,result), display_retired(ticket)->bool,
    stop(), can_exit()->bool. prepare/stop cover partial-start failures too.
    submit_cpu must copy the COMPLETE CPU canvas before returning. Retirement
    must prove the existing display fence. stop must confirm DMA HALTED before
    releasing any buffer; can_exit covers capture+display+all allocations.
    No get-current-pointer shortcut, default CameraPipeline or force flag.
    """
    try:
        owner.prepare()
        while not stopping():
            for response in beam.receive(uart.read()):
                uart.write_packet(response)
            captured = owner.capture_cpu()
            owner.check_capture()
            compose_started = time.monotonic()
            result, canvas, pose = beam.frame(captured)
            if teaching is not None:
                # 教学读取独立CPU副本；画布只用于显示，原检测输入和C票据不变。
                teaching.update(captured)
                canvas = teaching.compose(captured.bgr, captured.stride)
            if hasattr(owner, 'record_cost'):
                owner.record_cost('compose_ms', (time.monotonic() - compose_started) * 1000)
            uart.write_packet(pose)
            owner.check_capture()
            while True:
                try:
                    owner.submit_cpu(canvas, result)
                    break
                except DisplayFault:
                    # 提交失败时 C 票据仍未进入退休阶段，重试同一完整画布，
                    # 不重新采集、不重复生成姿态，也不释放显示缓冲。
                    owner.check_capture()
                    time.sleep(.001)
            beam.submitted(result.ticket)
            deadline = time.monotonic() + .5
            while True:
                try:
                    retired = owner.display_retired(result.ticket)
                except DisplayFault:
                    # 显示硬件的瞬时读回错误不应终止采集；保留当前票据，
                    # 继续等待同一帧退休，直到所有权者确认真实栅栏完成。
                    owner.check_capture()
                    time.sleep(.001)
                    continue
                if retired is True:
                    break
                if retired is not False:
                    raise RuntimeError("display owner must return an explicit retirement boolean")
                owner.check_capture()
                if time.monotonic() >= deadline:
                    raise RuntimeError("display retirement exceeded original 500ms bound")
                time.sleep(.001)
            uart.write_packet(beam.retired(result.ticket))
            if teaching is not None:
                # 每帧最多一个小侧带分包，先完成v3控制/姿态/显示退休。
                uart.write_packet(teaching.pop_packet())
            owner.check_capture()
    except BaseException as error:
        if hasattr(owner, 'first_fault') and owner.first_fault is None:
            owner.first_fault = dict(stage='runtime', error=repr(error),
                                     sample=getattr(error, 'snapshot', None))
        raise
    finally:
        # Keep owner, library, frames and UART alive until actual safe stop.
        # Catchable exit requests do not release uncertain DMA buffers. As with
        # existing owner_drain, SIGKILL/OOM/power loss are not solved here.
        drain_owner(owner)
        try:
            uart.close()
        finally:
            beam.close()


def drain_owner(owner):
    previous = None
    while True:
        try:
            owner.stop()
            if owner.can_exit() is True:
                return
        except BaseException as error:
            detail = repr(error)
            if detail != previous:
                print('BEAM_OWNER_RETAINED ' + detail, file=sys.stderr, flush=True)
                previous = detail
        try:
            time.sleep(.1)
        except BaseException:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="CPU ABI/init only; no hardware")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("CPU entry requires --check; use pynq_vision.beam_launcher for the hardware runner")
    beam = Beam(args.library, 1, lambda: int(time.monotonic() * 1000))
    beam.close()
    print(json.dumps(dict(status="C_BOARD_CORE_READY", abi=1, wire_protocol=3,
                          board_backend="NOT_RUN_CPU_CHECK_ONLY", hardware_operations=0)))


if __name__ == "__main__":
    main()
