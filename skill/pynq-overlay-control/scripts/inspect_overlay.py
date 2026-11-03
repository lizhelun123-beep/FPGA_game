"""离线提取 Overlay 元数据，不导入 PYNQ 或访问设备。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def fingerprint(path):
    data = path.read_bytes()
    if not data:
        raise ValueError("empty input: " + str(path))
    return {"name": path.name, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def inspect(bit, hwh=None, ip=None, limit=20):
    bit = Path(bit)
    hwh = Path(hwh) if hwh is not None else bit.with_suffix(".hwh")
    if bit.suffix.lower() != ".bit" or hwh.suffix.lower() != ".hwh":
        raise ValueError("expected .bit and .hwh files")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    identity = {"bit": fingerprint(bit), "hwh": fingerprint(hwh)}
    tree = ET.parse(hwh)
    modules = list(tree.iter("MODULE"))
    names = sorted({m.get("FULLNAME") or m.get("INSTANCE") for m in modules
                    if m.get("FULLNAME") or m.get("INSTANCE")})
    result = {"scope": "STATIC_METADATA_ONLY", "files": identity,
              "same_stem": bit.stem == hwh.stem,
              "build_pair_proven": False, "ip_count": len(names)}
    if ip is None:
        result.update(ips=names[:limit], omitted=max(0, len(names) - limit))
        return result
    # 短名称可能在层级设计中重复，歧义时要求完整路径。
    matches = [m for m in modules if ip in (m.get("FULLNAME"), m.get("INSTANCE"))]
    if len(matches) != 1:
        raise ValueError("IP must identify exactly one module: " + ip)
    module = matches[0]
    aliases = {name for name in (module.get("FULLNAME"), module.get("INSTANCE")) if name}
    ranges = set()
    for item in tree.iter("MEMRANGE"):
        if item.get("INSTANCE") not in aliases:
            continue
        if item.get("MEMTYPE") not in (None, "REGISTER"):
            continue
        # 地址记录的短名也必须唯一，完整模块路径不能消除记录自身的歧义。
        owner = item.get("INSTANCE")
        owners = [m for m in modules if owner in (m.get("FULLNAME"), m.get("INSTANCE"))]
        if len(owners) != 1:
            raise ValueError("ambiguous register range owner: " + owner)
        if item.get("BASEVALUE") is None or item.get("HIGHVALUE") is None:
            raise ValueError("incomplete register range")
        base, high = int(item.get("BASEVALUE"), 0), int(item.get("HIGHVALUE"), 0)
        if not 0 <= base <= high < (1 << 64):
            raise ValueError("invalid register range")
        ranges.add((base, high - base + 1))
    registers = sorted({r.get("NAME") for r in module.iter("REGISTER") if r.get("NAME")})
    result["ip"] = {"name": ip, "type": module.get("MODTYPE"),
                    "vlnv": module.get("VLNV"),
                    "ranges": [{"base": base, "span": span} for base, span in sorted(ranges)],
                    "register_count": len(registers), "registers": registers[:limit],
                    "omitted": max(0, len(registers) - limit)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bit", type=Path)
    parser.add_argument("--hwh", type=Path)
    parser.add_argument("--ip", help="HWH 中的 INSTANCE 或 FULLNAME")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.bit, args.hwh, args.ip, args.limit)
    except (OSError, ValueError, ET.ParseError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
