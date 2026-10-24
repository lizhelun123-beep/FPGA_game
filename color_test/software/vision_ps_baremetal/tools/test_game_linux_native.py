"""Explicitly authorized COM-console diagnostic, not a production app launcher.

Requires an already logged-in Linux shell, existing native gcc/Python3 and host
pyserial. Transfers selected test sources only. Never discovers devices, installs
packages, loads PL, or accesses camera/display. Run stages separately so the user
can prepare for real mouse input. Artifacts stay in output/build/game_app.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import sys
import tarfile
import time
import uuid

import serial


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "color_test/software/vision_ps_baremetal"
OUTPUT = ROOT / "output/build/game_app"
MANIFEST = OUTPUT / "game_linux_native_session.json"
MODULES = ("game_linux_io", "game_pump", "game_evdev", "game_loop", "game_input",
           "game_app", "game_scene_adapter", "game_session", "ray_game")
DISPLAY_MODULES = ("game_linux_display", "game_render", "vision_overlay", "game_photo_input", "vision_ps", "green_target_detector", "game_loop",
                   "game_linux_io", "game_pump", "game_evdev",
                   "game_input", "game_app", "game_scene_adapter", "game_session", "ray_game")
DISPLAY_ABI = """#include <libxlnk_cma.h>
void *(*owned_allocate)(uint32_t, uint32_t) = cma_alloc;
unsigned long (*owned_physical)(void *) = cma_get_phy_addr;
void (*owned_release)(void *) = cma_free;
void (*owned_flush)(void *, unsigned int, int) = cma_flush_cache;
int main(void) { return !owned_allocate || !owned_physical || !owned_release || !owned_flush; }
"""

class Console:
    def __init__(self, port, stage, credential=None):
        self.log = OUTPUT / ("game_linux_native_" + stage + "_" + uuid.uuid4().hex[:8] + ".log")
        self.raw = bytearray()
        self.progress = set()
        self.sent_password = False
        self.credential = credential
        self.shell_confirmed = False
        self.foreground_owned = False
        self.port = serial.Serial(port=None, baudrate=115200, timeout=0.2,
                                  write_timeout=3, xonxoff=False,
                                  rtscts=False, dsrdtr=False)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.port.open()

    def send(self, text):
        self.port.write(text.encode("ascii"))
        self.port.flush()

    def confirm_shell(self):
        # A timeout here must NEVER interrupt an unknown foreground program.
        self.send("\r")
        deadline = time.monotonic() + 8
        start = len(self.raw)
        while time.monotonic() < deadline:
            self.raw.extend(self.port.read(min(max(self.port.in_waiting, 1), 4096)))
            if re.search(rb"(?:^|[\r\n])xilinx@pynq:~\$ $", bytes(self.raw[start:])):
                self.shell_confirmed = True
                print("Confirmed actual xilinx@pynq:~$ prompt", flush=True)
                return
        raise RuntimeError("Expected shell prompt not observed; no upload or Ctrl-C sent")

    def until(self, pattern, seconds):
        start = len(self.raw)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data = self.port.read(min(max(self.port.in_waiting, 1), 4096))
            self.raw.extend(data)
            recent = bytes(self.raw[start:])
            for line in re.findall(rb"(?:^|\n)(NATIVE_(?:ABI|IDLE|INTERACTIVE_READY|MENU)[^\r\n]*)\r?\n", recent):
                if line not in self.progress:
                    self.progress.add(line)
                    print(line.decode("ascii", errors="replace"), flush=True)
            if b"Sorry, try again." in recent:
                self.send("\x03")
                raise RuntimeError("sudo rejected the confirmed credential; stopped")
            if b"[sudo] password for xilinx:" in recent and not self.sent_password:
                if not self.credential:
                    self.send("\x03")
                    raise RuntimeError("sudo requires an authorized credential via --sudo-password-stdin")
                self.port.write(self.credential + b"\r")
                self.port.flush()
                self.sent_password = True
            match = re.search(pattern, recent)
            if match:
                return match
        if self.foreground_owned:
            self.send("\x03")  # Interrupt only this foreground diagnostic.
        raise TimeoutError("Serial stage timed out; foreground diagnostic interrupted, no automatic retry")

    def command(self, command, seconds=60, allow_failure=False):
        if not self.shell_confirmed:
            raise RuntimeError("Shell has not been confirmed")
        token = "CODEX_DONE_" + uuid.uuid4().hex
        self.foreground_owned = True
        self.send(command + "; printf '\\n" + token + ":%s\\n' \"$?\"\r")
        result = self.until((token + r":([0-9]+)\r?\n").encode(), seconds)
        self.foreground_owned = False
        if int(result.group(1)) and not allow_failure:
            raise RuntimeError("Board command returned " + result.group(1).decode())
        return int(result.group(1))

    def close(self):
        self.port.close()
        transcript = bytes(self.raw)
        if self.credential:
            transcript = transcript.replace(self.credential, b"<redacted>")
        self.log.write_bytes(transcript)


def python_command(program):
    encoded = base64.b64encode(program.encode()).decode()
    return "python3 -u -c " + shlex.quote("import base64;exec(base64.b64decode('" + encoded + "'))")


def bundle(display=False):
    modules = DISPLAY_MODULES if display else MODULES
    files = [APP / "src" / (name + ext) for name in modules for ext in (".c", ".h")]
    files += [APP / "src" / name for name in
              ("vision_ps.h", "vision_ps_config.h", "game_render.h", "vision_overlay.h")]
    files += [OUTPUT / name for name in ("game_config.h", "game_config.c")]
    if display:
        files += [APP / "src" / name for name in ("game_font.h", "game_pump.h", "game_evdev.h")]
        files += [APP / "tools/game_linux_static_menu.c", APP / "tests/test_game_linux_display.c"]
    else:
        files += [APP / "tests" / name for name in
                  ("game_linux_native_probe.c", "test_game_linux_io.c")]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for path in dict.fromkeys(files):
            archive.add(path, arcname=path.name, recursive=False)
    return stream.getvalue()


def prepare(console, display=False, resources=False):
    if not console.shell_confirmed:
        raise RuntimeError("Shell has not been confirmed; no upload sent")
    payload = bundle(display)
    digest = hashlib.sha256(payload).hexdigest()
    program = '''import base64,hashlib,io,json,os,shutil,subprocess,sys,tarfile,tempfile,termios
state=termios.tcgetattr(0)
quiet=termios.tcgetattr(0);quiet[3]&=~termios.ECHO
termios.tcsetattr(0,termios.TCSANOW,quiet)
chunks=[]
try:
 print('CODEX_UPLOAD_READY',flush=True)
 for line in sys.stdin:
  if line.strip()=='END':break
  chunks.append(line.strip());print('CODEX_CHUNK '+str(len(chunks)),flush=True)
finally:termios.tcsetattr(0,termios.TCSANOW,state)
data=base64.b64decode(''.join(chunks),validate=True)
assert hashlib.sha256(data).hexdigest()==DIGEST
directory=tempfile.mkdtemp(prefix=PREFIX)
success=False
try:
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
  for member in archive:
   assert member.isfile() and member.name==os.path.basename(member.name) and member.name not in ('.','..')
   with open(os.path.join(directory,member.name),'xb') as target:target.write(archive.extractfile(member).read())
 flags=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I',directory]
 sources=MODULES+['game_config.c']
 entry=ENTRY
 unit=UNIT
 unit_sources=[s for s in sources if s!='game_linux_display.c'] if __IS_RESOURCES__ else sources
 unit_flags=flags+['-DGAME_DISPLAY_NATIVE_RESOURCES_TEST'] if __IS_RESOURCES__ else flags
 for stage,args in [
  ('static',flags+['-fsyntax-only']+sources+[entry+'.c',unit+'.c']),
  ('link_probe',flags+['-O2']+sources+[entry+'.c','-lm','-o',entry]),
  ('link_unit',unit_flags+['-O2']+unit_sources+[unit+'.c','-lm','-o',unit])]:
  run=subprocess.run(args,cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True,timeout=60)
  print('NATIVE_STAGE '+stage+' status='+str(run.returncode),flush=True)
  print(run.stdout,flush=True)
  if run.returncode:sys.exit(run.returncode)
 if __IS_DISPLAY__:
  # Inspect BEFORE executing either CPU binary. readelf does not load libcma.
  for executable in [entry,unit]:
   dynamic=subprocess.check_output(['readelf','-W','-d',executable],cwd=directory,universal_newlines=True)
   symbols=subprocess.check_output(['readelf','-W','--dyn-syms',executable],cwd=directory,universal_newlines=True)
   import re
   assert not re.search(r'NEEDED.*libcma',dynamic,re.I)
   forbidden=r'cma_\\w+|xlnk\\w+|dlopen|dlmopen|dlsym|ioctl' if __IS_RESOURCES__ else r'cma_\\w+|xlnk\\w+|dlopen|dlmopen|dlsym|open|open64|mmap|mmap64|ioctl'
   assert not re.search(r'UND.*\\b('+forbidden+r')(?:@|\\s|$)',symbols)
   print('NATIVE_IMPORTS '+executable+' no CMA/loader/ioctl imports',flush=True)
 if __IS_RESOURCES__:
  subprocess.run(['strace','-f','-e','trace=open,openat,mmap,mmap2,munmap,close,flock,ioctl','-o','resources.strace','./'+unit,'--native-resources'],cwd=directory,check=True,timeout=60)
  with open(os.path.join(directory,'resources.strace'),'rb') as f:trace=f.read()
  assert not re.search(rb'/dev/(?:mem|xlnk|uio|dri|fb)',trace)
  print('NATIVE_RESOURCE_TRACE '+base64.b64encode(trace).decode('ascii'),flush=True)
  assert subprocess.run(['./'+entry,'--display'],cwd=directory,timeout=10).returncode==3
 else:subprocess.run(['./'+unit],cwd=directory,check=True,timeout=60)
 if __IS_DISPLAY__ and not __IS_RESOURCES__:
  subprocess.run(['./'+entry,'--check'],cwd=directory,check=True,timeout=10)
  blocked=subprocess.run(['./'+entry,'--display'],cwd=directory,timeout=10)
  assert blocked.returncode==3
  # Compile/link-only ABI probe. NEVER execute it or load libcma before its
  # installed constructor/initialization/cache implementation is qualified.
  abi=ABI_SOURCE
  with open(os.path.join(directory,'libcma_abi.c'),'x') as target:target.write(abi)
  subprocess.run(flags+['-fsyntax-only','libcma_abi.c'],cwd=directory,check=True,timeout=30)
  subprocess.run(flags+['libcma_abi.c','-lcma','-pthread','-o','libcma_abi'],cwd=directory,check=True,timeout=30)
  for args in [['readelf','-d','libcma_abi'],['readelf','--version-info','libcma_abi']]:
   subprocess.run(args,cwd=directory,check=True,timeout=10)
 for args in [['gcc','--version'],['file',entry],['readelf','-h',entry],
              ['readelf','-l',entry],['readelf','--version-info',entry]]:
  subprocess.run(args,cwd=directory,check=True,timeout=10)
 versions=subprocess.check_output(['readelf','--version-info',entry],cwd=directory,universal_newlines=True)
 import re
 assert all(tuple(map(int,v.split('.')))<=(2,27) for v in re.findall(r'GLIBC_([0-9.]+)',versions))
 success=True
 if __IS_RESOURCES__:shutil.rmtree(directory)
 print('NATIVE_PREP '+json.dumps({'directory':directory,'sha256':DIGEST,'cleaned':__IS_RESOURCES__}),flush=True)
finally:
 if not success:
  if __IS_RESOURCES__:print('NATIVE_FAILED_DIRECTORY '+directory,flush=True)
  else:shutil.rmtree(directory)
'''.replace("DIGEST", repr(digest)).replace("MODULES", repr([n + ".c" for n in
    (DISPLAY_MODULES if display else MODULES)])).replace("ENTRY", repr(
    "game_linux_static_menu" if display else "game_linux_native_probe")).replace("UNIT", repr(
    "test_game_linux_display" if display else "test_game_linux_io")).replace("__IS_DISPLAY__", repr(display)).replace(
    "ABI_SOURCE", repr(DISPLAY_ABI)).replace("__IS_RESOURCES__",repr(resources)).replace("PREFIX", repr(
    "codex_game_display_resources_" if resources else "codex_game_display_" if display else "codex_game_native_"))
    # Use an upload receiver (one short canonical terminal line per chunk).
    token = "CODEX_PREP_DONE_" + uuid.uuid4().hex
    console.foreground_owned = True
    console.send(python_command(program) + "; printf '\\n" + token + ":%s\\n' \"$?\"\r")
    console.until(rb"CODEX_UPLOAD_READY\r?\n", 10)
    encoded = base64.b64encode(payload).decode()
    for count, offset in enumerate(range(0, len(encoded), 768), 1):
        console.send(encoded[offset:offset + 768] + "\r")
        console.until(("CODEX_CHUNK " + str(count) + r"\r?\n").encode(), 5)
    console.send("END\r")
    result = console.until((token + r":([0-9]+)\r?\n").encode(), 90)
    console.foreground_owned = False
    if int(result.group(1)):
        raise RuntimeError("Native compile/test failed; see " + str(console.log))
    match = re.search(rb"NATIVE_PREP (\{[^\r\n]+\})", console.raw)
    manifest = json.loads(match.group(1))
    manifest["port"] = console.port.port
    manifest["prepare_log"] = console.log.name
    if resources:
        trace = re.search(rb"NATIVE_RESOURCE_TRACE ([A-Za-z0-9+/=]+)", console.raw)
        if not trace: raise RuntimeError("Missing native resource syscall trace")
        trace_path=console.log.with_suffix(".strace")
        trace_path.write_bytes(base64.b64decode(trace.group(1),validate=True))
        manifest["trace"]=trace_path.name
    manifest_path = OUTPUT / "game_linux_display_resources_session.json" if resources else OUTPUT / "game_linux_display_native_session.json" if display else MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("PASS native strict compile/link and " + (
        "ordinary-file resource syscall test" if resources else "fake-syscall unit test"), flush=True)


def session(port, display=False):
    manifest_path = OUTPUT / "game_linux_display_native_session.json" if display else MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directory = manifest["directory"]
    prefix = "codex_game_display_" if display else "codex_game_native_"
    if manifest.get("cleaned") or manifest["port"] != port or not re.fullmatch(r"/tmp/" + prefix + r"[a-zA-Z0-9_]+", directory):
        raise ValueError("Invalid native session manifest")
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "display-prepare", "display-resources", "run", "cleanup", "display-cleanup"))
    parser.add_argument("--port", required=True)
    parser.add_argument("--device", default="/dev/input/event0")
    parser.add_argument("--seconds", type=int, default=35, choices=range(5, 46))
    parser.add_argument("--clicks-only", action="store_true",
                        help="require three real click pairs/two selections; no motion requirement; stop on success")
    parser.add_argument("--sudo-password-stdin", action="store_true",
                        help="read an explicitly authorized sudo credential from stdin; never log it")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    credential = sys.stdin.buffer.readline().rstrip(b"\r\n") if args.sudo_password_stdin else None
    console = Console(args.port, args.stage, credential)
    try:
        console.confirm_shell()
        if args.stage in ("prepare", "display-prepare", "display-resources"):
            prepare(console, display=args.stage != "prepare", resources=args.stage == "display-resources")
        elif args.stage == "run":
            executable = session(args.port) + "/game_linux_native_probe"
            command = "sudo " + shlex.quote(executable) + " " + shlex.quote(args.device) + " " + str(args.seconds)
            if args.clicks_only:
                command += " clicks"
            status = console.command(command, args.seconds + 30, allow_failure=True)
            summary = re.search(rb"NATIVE_SUMMARY ([^\r\n]+)", console.raw)
            if not summary:
                raise RuntimeError("Missing native summary")
            print(summary.group(0).decode(), flush=True)
            result = dict(item.split("=", 1) for item in summary.group(1).decode().split())
            result["log"] = console.log.name
            report = json.dumps(result, indent=2) + "\n"
            console.log.with_suffix(".json").write_text(report, encoding="utf-8")
            (OUTPUT / "game_linux_native_result.json").write_text(report, encoding="utf-8")
            if status or result["pass"] != "1":
                raise RuntimeError("Native interaction did not pass; summary preserved")
        else:
            display = args.stage == "display-cleanup"
            manifest_path = OUTPUT / "game_linux_display_native_session.json" if display else MANIFEST
            directory = session(args.port, display)
            program = "import shutil;shutil.rmtree(" + repr(directory) + ")"
            console.command(python_command(program), 10)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cleaned"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print("Removed this test's board /tmp bundle; COM port released on exit", flush=True)
    finally:
        console.close()


if __name__ == "__main__":
    main()
