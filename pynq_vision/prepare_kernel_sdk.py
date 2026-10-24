"""Read-only image extraction and ABI binding for an external-module SDK.

No PYNQ, serial, device access, mount, kernel build or module load. Linux file
names and symlinks stay inside a tar archive, preserving case on Windows.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import posixpath
import stat
import struct
import tarfile

KERNEL_RELEASE = "5.4.0-xilinx-v2020.1"
KERNEL_ROOT = "/lib/modules/" + KERNEL_RELEASE + "/build"
IMAGE_SHA256 = "bcee01b865196f8f433e4d17dc8d854d428c1c0a462c6080ba29c022524f1edd"
MODULE_SHA256 = "a923c535d807917b733611bc26f440fb07a0aec757954bc5436086e809584bee"
EXPECTED_INPUTS = {
    ".config": "f2fa6d9b7e7b86b7b1210db2d299835543e08822ef05d8dce3d23445946c80a5",
    "Module.symvers": "91f20404644673d2dc550d3cdf1691d2e49fd0a4a121b18fe56fbc3e5eebb664",
    "include/generated/autoconf.h": "f97226090bbb4597a261addf454557d7c6e7cbcbfade3561eafeb1f8b1765797",
    "include/generated/compile.h": "101cea820c3df2781ac4f5ecfb6ef4fe7d1f89ee787add580184ff8e3d4e387a",
    "include/generated/asm-offsets.h": "07738752894260b279fde54af09b431e7314fd8b2149c026f3100e6d061d2997",
    "include/generated/bounds.h": "bad62d10facd799e4e6232c11b56ba69117a193e56ed5eefe330efff70479653",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def elf_sections(data):
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ValueError("expected little-endian ELF32")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    if header[1] != 40 or header[10] != 40:
        raise ValueError("expected ARM ELF32 section ABI")
    section_offset, count, strings_index = header[5], header[11], header[12]
    if not count or strings_index >= count or section_offset + count * 40 > len(data):
        raise ValueError("invalid ELF section range")
    headers = [struct.unpack_from("<IIIIIIIIII", data, section_offset + index * 40) for index in range(count)]
    strings_header = headers[strings_index]
    if strings_header[4] + strings_header[5] > len(data):
        raise ValueError("invalid ELF string table")
    strings = data[strings_header[4]:strings_header[4] + strings_header[5]]
    result = {}
    for entry in headers:
        if entry[0] >= len(strings):
            raise ValueError("invalid ELF section name")
        name = strings[entry[0]:].split(b"\0", 1)[0].decode("ascii")
        if entry[1] != 8 and entry[4] + entry[5] > len(data):
            raise ValueError("invalid ELF section data")
        result[name] = data[entry[4]:entry[4] + entry[5]] if entry[1] != 8 else b""
    return result


def module_versions(data):
    section = elf_sections(data).get("__versions", b"")
    if not section or len(section) % 64:
        raise ValueError("missing or invalid ARM modversions records")
    result = {}
    for offset in range(0, len(section), 64):
        crc = struct.unpack_from("<I", section, offset)[0]
        name = section[offset + 4:offset + 64].split(b"\0", 1)[0].decode("ascii")
        if not name or name in result:
            raise ValueError("invalid/duplicate symbol version")
        result[name] = crc
    return result


def check_symbol_versions(module, symvers):
    symbols = {}
    for line in symvers.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 3:
            symbols[fields[1]] = int(fields[0], 16)
    versions = module_versions(module)
    failures = {name: {"module_crc": crc, "kernel_crc": symbols.get(name)}
                for name, crc in versions.items() if symbols.get(name) != crc}
    if failures or "module_layout" not in versions:
        raise ValueError("module/current-symbol-table mismatch: {!r}".format(failures))
    return {"imports": len(versions), "all_match": True,
            "module_layout_crc": "0x{:08x}".format(versions["module_layout"]),
            "versions": {name: "0x{:08x}".format(crc) for name, crc in sorted(versions.items())}}


def root_partition(stream, size):
    stream.seek(0)
    mbr = stream.read(512)
    if mbr[510:512] != b"\x55\xaa":
        raise ValueError("invalid MBR")
    candidates = []
    for index in range(4):
        entry = mbr[446 + index * 16:462 + index * 16]
        start, sectors = struct.unpack_from("<II", entry, 8)
        if entry[4] == 0x83 and sectors:
            offset, span = start * 512, sectors * 512
            if offset + span > size:
                raise ValueError("partition exceeds image")
            candidates.append((offset, span))
    if len(candidates) != 1:
        raise ValueError("expected one Linux root partition")
    return candidates[0]


def extract_inputs(image, output):
    from dissect.extfs.extfs import ExtFS
    from dissect.util.stream import RangeStream

    image, output = Path(image), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / "kernel-inputs.tar.gz"
    report_path = output / "kernel-inputs.json"
    if archive_path.exists() or report_path.exists():
        raise FileExistsError("preserve existing SDK input evidence; refusing overwrite")
    with image.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != IMAGE_SHA256:
            raise ValueError("image SHA256 differs from audited image")
        offset, span = root_partition(stream, image.stat().st_size)
        fs = ExtFS(RangeStream(stream, offset, span))
        critical = {name: fs.get(KERNEL_ROOT + "/" + name).open().read() for name in EXPECTED_INPUTS}
        for name, wanted in EXPECTED_INPUTS.items():
            if sha256(critical[name]) != wanted:
                raise ValueError("current-board-bound kernel input mismatch: " + name)
        module = fs.get("/lib/modules/" + KERNEL_RELEASE + "/extra/zocl.ko").open().read()
        if sha256(module) != MODULE_SHA256:
            raise ValueError("image module differs from observed loaded module")
        abi = check_symbol_versions(module, critical["Module.symvers"])
        entries = []

        def add(archive, node, relative):
            name = "kernel-build" + ("/" + relative if relative else "")
            info = tarfile.TarInfo(name)
            info.mode = node.inode.i_mode & 0o777
            info.mtime = 0
            item = {"path": name, "inode": node.inum, "mode": info.mode, "source_mtime_ns": node.mtime_ns}
            if node.filetype == stat.S_IFDIR:
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
                entries.append(dict(item, type="directory"))
                for child in sorted(node.iterdir(), key=lambda value: value.filename):
                    if child.filename not in (".", ".."):
                        if "/" in child.filename or child.filename in ("", ".", ".."):
                            raise ValueError("unsafe image path")
                        add(archive, child, relative + "/" + child.filename if relative else child.filename)
            elif node.filetype == stat.S_IFLNK:
                link = node.open().read().decode("utf-8")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                if link.startswith("/") or not resolved.startswith("kernel-build/"):
                    raise ValueError("symlink escapes kernel input package: " + name)
                info.type = tarfile.SYMTYPE
                info.linkname = link
                archive.addfile(info)
                entries.append(dict(item, type="symlink", target=link))
            elif node.filetype == stat.S_IFREG:
                data = node.open().read()
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
                entries.append(dict(item, type="file", bytes=len(data), sha256=sha256(data)))
            else:
                raise ValueError("unexpected special node in kernel headers")

        with archive_path.open("xb") as raw, tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
            add(archive, fs.get(KERNEL_ROOT), "")
            info = tarfile.TarInfo("reference/zocl.ko")
            info.mode, info.size = 0o644, len(module)
            archive.addfile(info, io.BytesIO(module))
        report = {
            "scope": "OFFLINE_IMAGE_INPUTS_BOUND_NOT_SDK_BUILD_QUALIFICATION",
            "image": str(image.resolve()), "image_sha256": digest.hexdigest(),
            "image_bytes": image.stat().st_size, "root_partition": [offset, span],
            "kernel_release": KERNEL_RELEASE,
            "critical_inputs": {name: sha256(data) for name, data in critical.items()},
            "reference_module_sha256": sha256(module), "reference_module_versions": abi,
            "archive_sha256": sha256(archive_path.read_bytes()), "archive_bytes": archive_path.stat().st_size,
            "entries": entries, "image_writes": 0, "board_access": False,
        }
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def prepare_linux(inputs, destination, toolchain, host_tools):
    """Prepare helpers only; never run prepare/oldconfig/syncconfig or build zocl.

    Requires a reviewed, privately installed Yocto 3.0.4 GCC9.2.0 SDK and private
    host compiler/make packages. All generated target layouts use external M=
    Kbuild against frozen inputs. Host helpers are static x86-64 executables.
    """
    import os
    import re
    import subprocess

    if os.name != "posix":
        raise RuntimeError("Linux case-sensitive filesystem required")
    inputs, destination, toolchain, host_tools = map(
        lambda value: Path(value).resolve(), (inputs, destination, toolchain, host_tools))
    if destination.exists():
        raise FileExistsError("preserve existing preparation evidence")
    destination.mkdir(parents=True)
    log_path = destination / "preparation.json"
    records = []
    env = dict(os.environ, LC_ALL="C", KCONFIG_NOSILENTUPDATE="1")
    for key in ("CC", "CFLAGS", "CPPFLAGS", "LDFLAGS", "ARCH", "CROSS_COMPILE",
                "KBUILD_OUTPUT", "KCONFIG_CONFIG", "LD_LIBRARY_PATH", "MAKEFLAGS"):
        env.pop(key, None)
    native = toolchain / "sysroots/x86_64-pokysdk-linux"
    cross = native / "usr/bin/arm-poky-linux-gnueabi/arm-poky-linux-gnueabi-"
    make = host_tools / "usr/bin/make"
    env["PATH"] = str(cross.parent) + ":" + str(native / "usr/bin") + ":/usr/bin:/bin"
    host_env = dict(env, LD_LIBRARY_PATH=str(host_tools / "usr/lib/x86_64-linux-gnu"))
    host_cc = [str(host_tools / "usr/bin/x86_64-linux-gnu-gcc-15"),
               "--sysroot=" + str(host_tools), "-std=gnu11", "-O2", "-static"]

    def run(args, cwd=None, input=None, host=False):
        result = subprocess.run(list(map(str, args)), cwd=cwd, env=host_env if host else env,
                                input=input, capture_output=True)
        records.append({"args": list(map(str, args)), "cwd": str(cwd),
                        "returncode": result.returncode,
                        "stdout": result.stdout.decode(errors="replace"),
                        "stderr": result.stderr.decode(errors="replace")})
        log_path.write_text(json.dumps(records, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("SDK preparation stopped: " + str(args) + "\n" +
                               result.stderr.decode(errors="replace")[-2000:])
        return result.stdout

    version = run([str(cross) + "gcc", "-dumpfullversion"]).decode().strip()
    if version != "9.2.0":
        raise ValueError("target compiler must be GCC9.2.0")
    with tarfile.open(inputs) as archive:
        archive.extractall(destination, filter="data")
    kernel = destination / "kernel-build"
    original = {str(path.relative_to(kernel)): sha256(path.read_bytes())
                for path in kernel.rglob("*") if path.is_file() and not path.is_symlink()}
    for name, wanted in EXPECTED_INPUTS.items():
        if original.get(name) != wanted:
            raise ValueError("frozen ABI input mismatch: " + name)
    for generated, generic in (("arch/arm/include/generated/uapi/asm", "include/uapi/asm-generic"),
                               ("arch/arm/include/generated/asm", "include/asm-generic")):
        run([make, "-f", "scripts/Makefile.asm-generic", "srctree=.", "SRCARCH=arm",
             "obj=" + generated, "generic=" + generic], cwd=kernel)
    # generic-y wrappers deliberately exclude generated-y. ARM's syscall and
    # machine headers must also be emitted from the exact packaged tables.
    # This standalone Kbuild rule does not include auto.conf.cmd or sync config.
    run([make, "-f", "scripts/Makefile.build", "srctree=.", "obj=arch/arm/tools",
         "ARCH=arm", "CONFIG_SHELL=/bin/sh", "AWK=awk", "kapi", "uapi"], cwd=kernel)
    run(host_cc + ["scripts/basic/fixdep.c", "-o", "scripts/basic/fixdep"], cwd=kernel, host=True)
    gen = "scripts/genksyms/"
    run([native / "usr/bin/bison", "-o", gen + "parse.tab.c", "--defines=" + gen + "parse.tab.h",
         "-t", "-l", gen + "parse.y"], cwd=kernel)
    run([native / "usr/bin/flex", "-o" + gen + "lex.lex.c", "-L", gen + "lex.l"], cwd=kernel)
    gen_objects = []
    for name in ("genksyms", "parse.tab", "lex.lex"):
        obj = gen + name + ".o"
        run(host_cc + ["-I" + gen, "-c", gen + name + ".c", "-o", obj], cwd=kernel, host=True)
        gen_objects.append(obj)
    run(host_cc + gen_objects + ["-o", gen + "genksyms"], cwd=kernel, host=True)
    helper = destination / "helper-input"
    helper.mkdir()
    (helper / "Makefile").write_text("obj-m := devicetable-offsets.o\n")
    (helper / "devicetable-offsets.c").symlink_to(kernel / "scripts/mod/devicetable-offsets.c")
    run([make, "-C", kernel, "M=" + str(helper), "ARCH=arm", "CROSS_COMPILE=" + str(cross),
         "HOSTCC=false", "devicetable-offsets.s"], cwd=destination)
    assembly = (helper / "devicetable-offsets.s").read_text()
    # The same .ascii ->NAME VALUE expression emitted by filechk_offsets in
    # scripts/Makefile.lib. Keep ARM target output, never host sizeof values.
    definitions = []
    for line in assembly.splitlines():
        match = re.match(r'\s*\.ascii\s+"->([^ ]+) [\$#]*([^ ]+) (.*)"', line)
        if match:
            definitions.append("#define {} {} /* {} */".format(*match.groups()))
    if len(definitions) < 100:
        raise ValueError("missing ARM devicetable layout definitions")
    mod = "scripts/mod/"
    (kernel / mod / "devicetable-offsets.h").write_text(
        "#ifndef __DEVICETABLE_OFFSETS_H__\n#define __DEVICETABLE_OFFSETS_H__\n" +
        "\n".join(definitions) + "\n#endif\n")
    run([str(cross) + "gcc", "-c", mod + "empty.c", "-o", mod + "empty.o"], cwd=kernel)
    run(host_cc + [mod + "mk_elfconfig.c", "-o", mod + "mk_elfconfig"], cwd=kernel, host=True)
    (kernel / mod / "elfconfig.h").write_bytes(run(
        [kernel / mod / "mk_elfconfig"], input=(kernel / mod / "empty.o").read_bytes()))
    objects = []
    for name in ("modpost", "file2alias", "sumversion"):
        obj = mod + name + ".o"
        run(host_cc + ["-I" + mod, "-c", mod + name + ".c", "-o", obj], cwd=kernel, host=True)
        objects.append(obj)
    run(host_cc + objects + ["-o", mod + "modpost"], cwd=kernel, host=True)
    changed = [name for name, wanted in original.items() if sha256((kernel / name).read_bytes()) != wanted]
    if changed:
        raise ValueError("original kernel inputs modified: " + repr(changed))
    result = {"scope": "OFFLINE_PREPARED_INPUTS_NOT_MODULE_RUNTIME_QUALIFICATION",
              "compiler": version, "original_files_checked": len(original),
              "original_files_changed": changed, "arm_device_layout_definitions": len(definitions),
              "critical_inputs": EXPECTED_INPUTS, "board_access": False}
    (destination / "prepared.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-inputs", type=Path, help="Linux-only: extracted kernel-inputs.tar.gz")
    parser.add_argument("--toolchain", type=Path, help="reviewed private Yocto 3.0.4 SDK prefix")
    parser.add_argument("--host-tools", type=Path, help="private host GCC/make package root")
    parser.add_argument("--reader-path", type=Path, help="task-private pinned Dissect dependency directory")
    args = parser.parse_args()
    if args.reader_path:
        import sys
        sys.path.insert(0, str(args.reader_path.resolve()))
    if args.prepare_inputs:
        if args.image or not args.toolchain or not args.host_tools:
            parser.error("--prepare-inputs needs --toolchain/--host-tools and excludes --image")
        print(json.dumps(prepare_linux(args.prepare_inputs, args.output, args.toolchain, args.host_tools)))
        return
    if not args.image:
        parser.error("--image or --prepare-inputs is required")
    report = extract_inputs(args.image, args.output)
    print(json.dumps({"critical_inputs_match": True,
                      "original_module_import_crcs_match": report["reference_module_versions"]["imports"],
                      "archive_bytes": report["archive_bytes"], "entries": len(report["entries"]),
                      "board_access": False}, sort_keys=True))


if __name__ == "__main__":
    main()
