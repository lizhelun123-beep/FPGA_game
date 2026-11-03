"""Build/transport the existing C game authority for a pose-only PC runtime."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "color_test/software/vision_ps_baremetal/src"


def build_board_host(compiler=None):
    sources = [ROOT/"pc_vision/board_game_host.c", SRC/"game_session.c", SRC/"ray_game.c"]
    generator_path = SRC.parent/"tools/generate_game_config.py"
    inputs = [*sources, *sorted(SRC.glob("*.h")), generator_path,
              ROOT/"pc_vision/game_config.json", Path(__file__)]
    digest = hashlib.sha256(b"board-game-v1")
    for path in inputs:
        digest.update(path.read_bytes())
    digest.update(str(compiler).encode())
    folder = ROOT/"pc_vision/output/board_native"/digest.hexdigest()[:16]
    executable = folder/("board_game.exe" if os.name == "nt" else "board_game")
    if executable.exists():
        return executable
    folder.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("board_config_generator", generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generated = folder/"game_config.c"
    generated.write_text(generator.generate(json.loads(inputs[-2].read_text(encoding="utf-8"))), encoding="utf-8")
    sources.append(generated)
    compile_host(sources, executable, compiler)
    return executable


def compile_host(sources, executable, compiler=None):
    executable = Path(executable).resolve()
    folder = executable.parent
    vcvars = Path(os.environ.get("ProgramFiles", "C:/Program Files"))/"Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat"
    if os.name == "nt" and compiler is None and vcvars.exists():
        # Use the established MSVC host route; the installed MinGW fails before
        # compilation on this machine with Windows DLL relocation error623.
        batch = folder/"build.cmd"
        arguments = ["cl.exe", "/nologo", "/std:c11", "/O2", "/W4", "/WX", "/D_CRT_SECURE_NO_WARNINGS",
                     "/I"+str(SRC), *(str(p) for p in sources), "/Fe:"+str(executable)]
        batch.write_text('@echo off\ncall "'+str(vcvars)+'" >nul\n'+subprocess.list2cmdline(arguments)+'\n', encoding="utf-8")
        subprocess.run(["cmd.exe", "/d", "/c", str(batch)], cwd=executable.parent, check=True, timeout=90,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        compiler = compiler or shutil.which("gcc")
        if not compiler:
            raise RuntimeError("A C compiler is required for the existing game_session/ray_game")
        subprocess.run([str(compiler), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-I"+str(SRC), *(str(p) for p in sources), "-lm", "-o", str(executable)],
                       cwd=executable.parent, check=True, timeout=60)


class NativeBoardGame:
    def __init__(self, compiler=None):
        self.path = build_board_host(compiler)
        self.process = subprocess.Popen([str(self.path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.state = self._read()

    def _read(self):
        row = self.process.stdout.readline(16384)
        if not row.endswith(b"\n"):
            raise RuntimeError("Incomplete C game snapshot")
        return json.loads(row)

    def command(self, text):
        self.process.stdin.write((text+"\n").encode("ascii"))
        self.process.stdin.flush()
        self.state = self._read()
        return self.state

    def frame(self, now, generation, frame, captured, valid=True, session_sequence=None):
        from .board_pose import TYPES
        rows = [" ".join(str(v) for v in (TYPES.index(o["type"]), *o["center"], *o["axis"], *o["size"]))
                for o in frame.models]
        sequence = frame.sequence if session_sequence is None else session_sequence
        return self.command("\n".join([
            f"frame {now} {generation} {sequence} {captured} {int(valid and frame.valid)} {len(rows)}", *rows]))

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b"quit 0\n")
                self.process.stdin.flush()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
