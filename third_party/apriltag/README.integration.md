This is the detector/common C source subset of AprilTag v3.4.5.
`UPSTREAM` pins the exact revision; retain `LICENSE.md` when distributing it.
Only tag36h11 is included. No Python/OpenCV detector runs in the game path.

`pc_vision/native.py:build_bridge(real_scene=True)` compiles these sources and
the existing C detector, pose stabilizer, session and ray solver. The Windows
target is Windows 7 or later; Linux uses pthreads. The host bridge also links
with the repository's ARM hard-float Linux compiler. Neither build accesses
hardware. This source subset is not a standalone upstream CMake project.

The optional `APRILTAG_STANDALONE` branch in `common/pthreads_cross.h` supplies
detector-local locks for the single-core synchronous port. The standalone
build excludes upstream workerpool/time/POSIX sources and uses
`color_test/software/vision_ps_baremetal/src/standalone/apriltag_port.c` for
one-worker task execution and XTime profiling. Quad extraction, tag decoding,
tag36h11 data and joint Portal fitting remain shared with the host build.
This port cannot be called from an ISR or a second core. It does not imply
an ARM link or camera-performance pass.

`vision_portal.c` selects one decoding correction bit, original-resolution
quad detection and one worker. ID/corner/rigid-shape checks are enforced before
publishing a Portal pose. A single tag remains diagnostic only.
