"""Package an existing inspected XSA and capture adapter; never build hardware."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .constants import (BIT_SHA256, CAPTURE_CONTRACT, HWH_SHA256,
                        MANIFEST_VERSION, XSA_SHA256)
from .hardware import inspect_display_hwh, validate_hwh_contract


def digest(data):
    return hashlib.sha256(data).hexdigest().upper()


def _read_checked_xsa(xsa_path):
    xsa = Path(xsa_path).read_bytes()
    if digest(xsa) != XSA_SHA256:
        raise RuntimeError("XSA is not the selected, inspected handoff")
    with zipfile.ZipFile(io.BytesIO(xsa)) as archive:
        metadata = json.loads(archive.read("xsa.json").decode("utf-8"))
        if (metadata.get("topModuleName") != "system_wrapper" or
                metadata.get("generatedVersion") != "2023.1"):
            raise RuntimeError("unexpected XSA top module or Vivado version")
        bit = archive.read("color_test.bit")
        hwh = archive.read("system.hwh")
    if digest(bit) != BIT_SHA256 or digest(hwh) != HWH_SHA256:
        raise RuntimeError("embedded BIT/HWH do not match the selected handoff")
    return xsa, metadata, bit, hwh


def inspect_display_handoff(xsa_path):
    """Read one matched XSA/BIT/HWH; never extract, copy, load or approve it."""
    xsa, metadata, bit, hwh = _read_checked_xsa(xsa_path)
    report = inspect_display_hwh(hwh)
    report["artifacts"] = {"xsa": str(xsa_path), "xsa_sha256": digest(xsa),
                           "bit_member": "color_test.bit", "bit_sha256": digest(bit),
                           "hwh_member": "system.hwh", "hwh_sha256": digest(hwh)}
    report["generation"] = {k: metadata.get(k) for k in
                            ("topModuleName", "generatedVersion", "generatedTimestamp")}
    report["generation"]["part"] = metadata["devices"][0]["part"]["name"]
    return report


def prepare(xsa_path, output, archive_path=None):
    xsa_path = Path(xsa_path)
    output = Path(output)
    if output.exists() or (archive_path is not None and Path(archive_path).exists()):
        raise FileExistsError("refusing to overwrite an existing diagnostic bundle")
    xsa, metadata, bit, hwh = _read_checked_xsa(xsa_path)
    addresses, clocks = validate_hwh_contract(hwh)
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "purpose": "Linux single-frame capture diagnostic; offline prepared",
        "source_xsa": "color_test.xsa",
        "source_xsa_sha256": digest(xsa),
        "vivado": metadata.get("generatedVersion"),
        "generated": metadata.get("generatedTimestamp"),
        "top": metadata.get("topModuleName"),
        "bit_sha256": digest(bit),
        "hwh_sha256": digest(hwh),
        "addresses": addresses,
        "clocks": clocks,
        "capture_contract": CAPTURE_CONTRACT,
        "display_enabled": False,
        "production_pl_qualified": False,
        "board_capture_verified": False,
    }
    payloads = {"color_test.xsa": xsa, "system_wrapper.bit": bit,
                "system_wrapper.hwh": hwh,
                "manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")}
    # Distribution copies live only in generated output, never as alternate sources.
    source_dir = Path(__file__).resolve().parent
    for source in sorted(source_dir.glob("*.py")):
        payloads["pynq_vision/" + source.name] = source.read_bytes()
    payloads["pynq_vision/README.md"] = (source_dir / "README.md").read_bytes()
    payloads["SHA256SUMS"] = "".join(
        "{}  {}\n".format(digest(data).lower(), name)
        for name, data in sorted(payloads.items())).encode("ascii")
    # All identity/XML/clock checks precede the first output write or mkdir.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if archive_path is not None:
        with zipfile.ZipFile(str(archive_path), "x", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payloads.items()):
                archive.writestr(output.name + "/" + name, data)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--xsa", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--display-report", type=Path,
                      help="Write a NEW offline display contract JSON only; no bundle or hardware")
    parser.add_argument("--archive", type=Path, help="Optional new ZIP; never overwrites")
    args = parser.parse_args(argv)
    if args.display_report:
        if args.archive:
            parser.error("--archive cannot be combined with --display-report")
        report = inspect_display_handoff(args.xsa)
        with args.display_report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(json.dumps(prepare(args.xsa, args.output, args.archive), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
