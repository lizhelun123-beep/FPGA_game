"""Explicit board-only 4 KiB PYNQ/xlnk diagnostic; never starts DMA.

Run only with current-task board/allocator authorization. No PYNQ import occurs
when this module is imported. The optional run requires the observed boot ID and
the reviewed installed implementation; it is not a qualified DMA allocator.
Use external strace to retain syscall status discarded by the public void API.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import signal


EXPECTED = {
    "/home/xilinx/pynq/buffer.py": "42c51463b8c02ebcb24f5f2d92252d83fd265bed4f877c9054cebe758c71b62f",
    "/home/xilinx/pynq/xlnk.py": "43607b40eeaf35b6c00fd7cf81ae24ce33afb3775edd8688bd617bb17f81bdfa",
    "/usr/lib/libcma.so": "126301f9575d119f3b12e41bc2ce26df79a0fdae210169da3bf4b6548dd1fdd3",
}


def emit(stage, **values):
    values["stage"] = stage
    print("MEMORY_TEST " + json.dumps(values, sort_keys=True), flush=True)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(expected_boot):
    require(os.geteuid() == 0, "Root is required by the reviewed Xlnk API")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(boot == expected_boot, "Boot changed; inspect before another test")
    for name, expected in EXPECTED.items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected,
                "Installed implementation changed: " + name)

    import pynq
    # The installed xlnk import installs a SIGSEGV handler calling SYSTEMWIDE
    # reset. Restore the default fatal signal action before any allocator call;
    # never install that handler again, including during interpreter teardown.
    previous = signal.getsignal(signal.SIGSEGV)
    signal.signal(signal.SIGSEGV, signal.SIG_DFL)
    import numpy as np
    from pynq import Xlnk, allocate

    emit("preflight", boot_id=boot, pynq_version=pynq.__version__,
         default_segv_restored=True, prior_segv_handler=str(previous),
         bytes=4096, cacheable=True, dma_started=False)
    # Explicit target consumes the exact Xlnk default-memory implementation
    # without discovering XRT devices or creating a PL-server fallback.
    allocator = Xlnk()
    require(len(allocator.bufmap) == 0, "Unexpected task-owned allocations")
    before = allocator.cma_stats()
    buffer = None
    try:
        buffer = allocate(shape=(4096,), dtype=np.uint8, target=allocator,
                          cacheable=1)
        physical = int(buffer.physical_address)
        emit("allocated", physical_address=physical,
             virtual_address=int(buffer.virtual_address), bytes=int(buffer.nbytes),
             coherent=bool(buffer.coherent), task_buffers=len(allocator.bufmap))
        require(buffer.nbytes == 4096 and buffer.flags.c_contiguous,
                "Unexpected allocation geometry")
        require(physical > 0 and physical % 64 == 0 and
                physical + buffer.nbytes <= 2 ** 32, "Invalid 32-bit DMA span")
        require(not buffer.coherent, "Test expects cacheable buffer")
        pattern = ((np.arange(4096, dtype=np.uint32) * 37 + 11) % 256).astype(np.uint8)
        buffer[...] = pattern
        require(np.array_equal(buffer, pattern), "CPU pattern mismatch")
        to_device = buffer.sync_to_device()
        from_device = buffer.sync_from_device()
        require(np.array_equal(buffer, pattern), "CPU pattern mismatch after sync")
        emit("cpu_pattern_and_sync_calls", pattern_sha256=hashlib.sha256(buffer.tobytes()).hexdigest(),
             sync_to_device_return=to_device, sync_from_device_return=from_device,
             public_sync_status_observable=False, device_transfer_verified=False)
    finally:
        if buffer is not None:
            buffer.freebuffer()
            # In this actual version freebuffer drops pointer, while ndarray's
            # backing buffer can retain the cffi owner until the array dies.
            emit("after_freebuffer", pointer_cleared=buffer.pointer == 0,
                 task_buffers=len(allocator.bufmap))
            del buffer
            gc.collect()
            emit("after_array_collection", task_buffers=len(allocator.bufmap))
    after = allocator.cma_stats()
    require(len(allocator.bufmap) == 0, "Task allocation still recorded after GC")
    emit("complete", result="CPU_API_CHECK_PASS", before=before, after=after,
         task_buffers=0, public_free_status_observable=False,
         dma_or_device_visibility_verified=False, failure_rollback_verified=False,
         safe_dma_backend_qualified=False, global_reset_called=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expect-boot")
    args = parser.parse_args()
    if not args.run or not args.expect_boot:
        parser.error("explicit --run and --expect-boot are required")
    run(args.expect_boot)


if __name__ == "__main__":
    main()
