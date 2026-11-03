"""生成独立技能提交包，保留既有输出并验证解包后的完整性。"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from verify_package import SKILLS, source_files, digest
from measure_context import report


def write_manifest(package):
    rows = [{"path": p.relative_to(package).as_posix(), "size": p.stat().st_size,
             "sha256": digest(p)} for p in source_files(package) if p.name != "manifest.json"]
    record = {"schema": "skill-package-manifest-v2", "package": "pynq-baremetal-skills",
              "version": "2026-11-01", "skills": list(SKILLS), "files": rows}
    (package / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")


def verify(package):
    process = subprocess.run([sys.executable, "-B", str(package / "skill/scripts/verify_package.py"),
                              str(package / "skill")], capture_output=True, text=True,
                             encoding="utf-8", timeout=120)
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)
    return process.stdout


def build(source, destination, baseline=None):
    source, destination = source.resolve(), destination.resolve()
    archive = destination.with_suffix(".zip")
    checksum = destination.with_suffix(".sha256")
    if destination == source or source in destination.parents:
        raise ValueError("destination must be outside skill/")
    if any(path.exists() for path in (destination, archive, checksum)):
        raise FileExistsError("preserving existing package; choose a new destination")
    destination.mkdir(parents=True)
    for path in source_files(source):
        if path.is_symlink() or source not in path.resolve().parents:
            raise ValueError("source link outside package: " + str(path))
        target = destination / "skill" / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    template = source / "references/package-root-readme.md"
    (destination / "README.md").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    (destination / "context-size.json").write_text(
        json.dumps(report(source, baseline), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "verification.txt").write_text("", encoding="utf-8")
    write_manifest(destination)
    output = verify(destination)
    (destination / "verification.txt").write_text(output, encoding="utf-8")
    write_manifest(destination)
    if verify(destination) != output:
        raise RuntimeError("verification output changed after recording")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in source_files(destination):
            info = zipfile.ZipInfo(path.relative_to(destination).as_posix(), (2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, path.read_bytes())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise RuntimeError("ZIP CRC failure")
        with tempfile.TemporaryDirectory(prefix="skillrestore_") as temporary:
            zipped.extractall(temporary)
            if verify(Path(temporary)) != output:
                raise RuntimeError("independent restore verification differs")
    checksum.write_text(digest(archive) + "  " + archive.name + "\n", encoding="ascii")
    return archive, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, help="旧技能 ZIP，仅用于比较入口体积")
    args = parser.parse_args()
    try:
        archive, output = build(args.source, args.destination, args.baseline)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    print(output, end="")
    print("ZIP=" + str(archive))
    print("SHA256=" + digest(archive))
    return 0


if __name__ == "__main__":
    sys.exit(main())
