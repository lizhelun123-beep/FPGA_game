"""离线验证技能结构、独立目录和脚本行为，仅使用标准库。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote

SKILLS = ("pynq-overlay-control", "pynq-dma-contract", "pynq-c-runtime",
          "baremetal-runtime", "ray-game-integration", "stream-perf-analysis",
          "fpga-verification-gates", "xilinx-project-flow")
ENTRY_BYTE_LIMIT = 1800


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(root):
    result = []
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result.append(path)
    return sorted(result)


def links(path):
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            yield from re.findall(r"\[[^\]]*\]\(([^)]+)\)", line)


def check_documents(root, files, skip_template=True):
    allowed = re.compile(r"^[a-z0-9_-]+(?:\.[a-z0-9_-]+)*$")
    for path in files:
        require(not path.is_symlink(), "symlink not allowed: " + str(path))
        for part in path.relative_to(root).parts:
            require(part in ("README.md", "SKILL.md") or allowed.fullmatch(part),
                    "invalid package name: " + part)
        if path.suffix != ".md" or (skip_template and path.name == "package-root-readme.md"):
            continue
        for target in links(path):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            destination = (path.parent / target).resolve()
            require(destination == root or root in destination.parents,
                    "reference leaves its package: " + target)
            require(destination.is_file(), "broken reference: " + str(path) + " -> " + target)


def check_skill(folder):
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    require(front is not None, "invalid frontmatter: " + folder.name)
    fields = dict(re.findall(r"^([a-z-]+):\s*(.+)$", front.group(1), re.M))
    name = fields.get("name", "")
    require(name == folder.name and len(name) <= 64 and
            re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), "invalid name: " + name)
    require(0 < len(fields.get("description", "").strip()) <= 1024,
            "invalid description: " + name)
    require(len(text.encode("utf-8")) <= ENTRY_BYTE_LIMIT, "entry budget exceeded: " + name)
    require("[TODO" not in text, "unfinished scaffold: " + name)
    metadata = (folder / "agents/openai.yaml").read_text(encoding="utf-8")
    require("$" + name in metadata, "invocation missing: " + name)


def run_python(args, expected=0):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    process = subprocess.run([sys.executable, "-B", *map(str, args)], env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=90)
    require(process.returncode == expected,
            "command failed: {}\n{}\n{}".format(args, process.stdout[-4000:], process.stderr[-4000:]))
    return process


def check_examples(root):
    suites = (("pynq-dma-contract", "test_check_layout.py"),
              ("stream-perf-analysis", "test_analyze.py"),
              ("pynq-overlay-control", "test_inspect_overlay.py"))
    for name, pattern in suites:
        process = run_python(["-m", "unittest", "discover", "-s", root / name / "scripts", "-p", pattern])
        count = re.search(r"Ran (\d+) tests?", process.stderr)
        require(count is not None and "skipped=" not in process.stderr, "suite incomplete: " + name)
        print("PASS suite={} tests={}".format(name, count.group(1)))
    perf = root / "stream-perf-analysis"
    data = json.loads(run_python([perf / "scripts/analyze.py",
        perf / "examples/audio-performance.jsonl", "--contract",
        perf / "examples/audio-contract.json"]).stdout)
    require(data["valid_windows"] == 1 and all(v["mean_ms"] == 3.0
            for v in data["last_window"]["stages"].values()), "audio reuse mismatch")
    data = json.loads(run_python([perf / "scripts/analyze.py",
        perf / "examples/performance.jsonl", "--contract",
        perf / "references/project-perf-contract.json"]).stdout)
    require(data["valid_windows"] == 1 and len(data["last_window"]["stages"]) == 25,
            "cumulative fixture mismatch")


def check_standalone(root):
    # 单独复制每项技能，防止其参考和工具暗中依赖父目录或原工程。
    with tempfile.TemporaryDirectory(prefix="skillcheck_") as temporary:
        for name in SKILLS:
            origin = root / name
            target = Path(temporary) / name
            for path in source_files(root):
                if origin not in path.parents:
                    continue
                destination = target / path.relative_to(origin)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
            check_skill(target)
            check_documents(target, source_files(target))
            if name == "pynq-dma-contract":
                data = json.loads(run_python([target / "scripts/check_layout.py",
                                             target / "examples/layout.json"]).stdout)
                require(data["status"] == "PASS_STATIC_DESCRIPTION", "isolated layout failed")
            elif name == "stream-perf-analysis":
                data = json.loads(run_python([target / "scripts/analyze.py",
                    target / "examples/audio-performance.jsonl", "--contract",
                    target / "examples/audio-contract.json"]).stdout)
                require(data["valid_windows"] == 1, "isolated performance failed")
            elif name == "pynq-overlay-control":
                run_python(["-m", "unittest", "discover", "-s", target / "scripts",
                            "-p", "test_inspect_overlay.py"])
    print("PASS independent_skill_folders=" + str(len(SKILLS)))


def check_manifest(root):
    manifest = root.parent / "manifest.json"
    if not manifest.is_file():
        print("SKIP manifest (source tree)")
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require(data.get("schema") == "skill-package-manifest-v2", "unknown manifest schema")
    actual = {p.relative_to(root.parent).as_posix(): p for p in source_files(root.parent) if p != manifest}
    declared = {r["path"]: r for r in data["files"]}
    require(len(declared) == len(data["files"]) and set(actual) == set(declared), "manifest inventory mismatch")
    for name, path in actual.items():
        row = declared[name]
        require(row["size"] == path.stat().st_size and row["sha256"] == digest(path),
                "manifest hash mismatch: " + name)
    print("PASS manifest_files=" + str(len(actual)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args(argv)
    root = args.skill.resolve()
    try:
        require(root.is_dir(), "skill root missing")
        files = source_files(root)
        before = {str(p.relative_to(root)): digest(p) for p in files}
        check_documents(root, files)
        for name in SKILLS:
            check_skill(root / name)
        print("PASS metadata={} local_links=all entry_byte_limit={}".format(len(SKILLS), ENTRY_BYTE_LIMIT))
        if not args.structure_only:
            check_examples(root)
            check_standalone(root)
        check_manifest(root)
        after = {str(p.relative_to(root)): digest(p) for p in source_files(root)}
        require(before == after, "verification modified inputs")
        print("PASS unchanged_inputs=1 environment=host_offline")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
