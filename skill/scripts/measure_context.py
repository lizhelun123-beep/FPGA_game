"""统计技能发现信息和入口体积；字符、字节不伪称模型实际 token。"""
import argparse
import json
from pathlib import Path
import re
import zipfile


def measure(text):
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if front is None:
        raise ValueError("missing YAML frontmatter")
    fields = dict(re.findall(r"^(name|description):\s*(.+)$", front.group(1), re.M))
    metadata = fields["name"] + "\n" + fields["description"]
    return {"utf8_bytes": len(text.encode("utf-8")), "characters": len(text),
            "lines": len(text.splitlines()),
            "discovery_characters": len(metadata)}


def report(root, baseline=None):
    current = {p.parent.name: measure(p.read_text(encoding="utf-8"))
               for p in sorted(root.glob("*/SKILL.md"))}
    result = {"measurement": "UTF-8 bytes and Unicode characters; not measured inference tokens",
              "skills": current, "entry_bytes": sum(v["utf8_bytes"] for v in current.values()),
              "discovery_characters": sum(v["discovery_characters"] for v in current.values())}
    if baseline:
        with zipfile.ZipFile(baseline) as archive:
            old = {Path(n).parent.name: measure(archive.read(n).decode("utf-8-sig").replace("\r\n", "\n"))
                   for n in archive.namelist() if n.endswith("/SKILL.md")}
        shared = sorted(set(old) & set(current))
        before = sum(old[k]["utf8_bytes"] for k in shared)
        after = sum(current[k]["utf8_bytes"] for k in shared)
        result["comparison"] = {"same_skills": shared, "before_bytes": before,
                                "after_bytes": after, "reduction_percent": round(100 * (before - after) / before, 1)}
        discovery_before = sum(v["discovery_characters"] for v in old.values())
        result["discovery_comparison"] = {
            "before_skills": len(old), "after_skills": len(current),
            "before_characters": discovery_before,
            "after_characters": result["discovery_characters"],
            "reduction_percent": round(100 * (discovery_before - result["discovery_characters"]) / discovery_before, 1)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.skill, args.baseline), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
