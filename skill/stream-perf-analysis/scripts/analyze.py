"""Read-only cumulative snapshot analysis; Python 3.8+, standard library only."""

import argparse
import json
import sys
from pathlib import Path


KINDS = {"leaf", "envelope", "span", "event", "meta"}


def uint(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return value


def validate_contract(contract):
    if type(contract.get("version")) is not int or contract["version"] != 1:
        raise ValueError("unsupported contract version")
    stages = contract.get("stages")
    if not isinstance(stages, dict) or not stages:
        raise ValueError("contract.stages must be a nonempty mapping")
    if any(not isinstance(k, str) or not k or v not in KINDS
           for k, v in stages.items()):
        raise ValueError("invalid stage name or kind")
    if all(kind == "meta" for kind in stages.values()):
        raise ValueError("contract needs at least one measured stage")
    marker = contract.get("boot_marker")
    if marker is not None:
        if (not isinstance(marker, dict)
                or stages.get(marker.get("stage")) != "meta"
                or marker.get("field") not in ("n", "total", "maximum")):
            raise ValueError("boot_marker must select an integer field of a meta stage")
    return stages


def reports_from_lines(lines, stages):
    """Keep contiguous report groups; do not merge reused IDs across restarts."""
    reports = []
    current = None
    row_count = 0
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("row must be an object")
            connection = row["connection"]
            if type(connection) not in (int, str):
                raise ValueError("connection must be an integer or string")
            report = uint(row["report"], "report")
            stage = row["stage"]
            if not isinstance(stage, str) or not stage:
                raise ValueError("stage must be a nonempty string")
            for field in ("n", "total", "maximum"):
                uint(row[field], field)
            kind = stages.get(stage)
            if kind and kind != "meta":
                if row.get("unit") != "us":
                    raise ValueError("measured stage unit must be us")
                if row["maximum"] > row["total"]:
                    raise ValueError("maximum exceeds total")
                if row["n"] == 0 and (row["total"] or row["maximum"]):
                    raise ValueError("nonzero duration with zero samples")
                if row["total"] > row["n"] * row["maximum"]:
                    raise ValueError("total exceeds count times maximum")
                if kind == "event" and (row["total"] or row["maximum"]):
                    raise ValueError("event duration must be zero")
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("line {}: {}".format(line_number, exc)) from exc
        key = (connection, report)
        if current is None or current["key"] != key:
            current = {"key": key, "rows": {}, "duplicates": set()}
            reports.append(current)
        if stage in current["rows"]:
            current["duplicates"].add(stage)
        current["rows"][stage] = row
        row_count += 1
    return reports, row_count


def boundary_reason(before, after, stages, marker):
    if before["key"][0] != after["key"][0]:
        return "connection_changed"
    if after["key"][1] <= before["key"][1]:
        return "report_not_increasing"
    if marker:
        stage, field = marker["stage"], marker["field"]
        if after["rows"][stage][field] < before["rows"][stage][field]:
            return "boot_marker_decreased"
    for stage, kind in stages.items():
        if kind == "meta":
            continue
        first, last = before["rows"][stage], after["rows"][stage]
        if any(last[f] < first[f] for f in ("n", "total", "maximum")):
            return "counter_decreased:" + stage
        if last["n"] == first["n"] and (
                last["total"] != first["total"]
                or last["maximum"] != first["maximum"]):
            return "duration_changed_without_samples:" + stage
        count = last["n"] - first["n"]
        if last["total"] - first["total"] > count * last["maximum"]:
            return "window_total_exceeds_maximum:" + stage
    return None


def compare(before, after, stages):
    metrics = {}
    for stage, kind in stages.items():
        if kind == "meta":
            continue
        first, last = before["rows"][stage], after["rows"][stage]
        count = last["n"] - first["n"]
        total = last["total"] - first["total"]
        metrics[stage] = {
            "kind": kind,
            "delta_n": count,
            "delta_total_us": total,
            "mean_ms": total / count / 1000 if count and kind != "event" else None,
            "cumulative_max_us": last["maximum"],
        }
    return {
        "connection": after["key"][0],
        "from_report": before["key"][1],
        "to_report": after["key"][1],
        "stages": metrics,
    }


def analyze(lines, contract):
    stages = validate_contract(contract)
    reports, row_count = reports_from_lines(lines, stages)
    result = {
        "schema": "cumulative-analysis-v1",
        "rows": row_count,
        "report_groups": len(reports),
        "complete_reports": 0,
        "valid_windows": 0,
        "discarded_reports": [],
        "boundaries": [],
        "last_window": None,
        "limitations": [
            "Caller must segment known boot epochs; counters cannot prove boot identity.",
            "Maximum is cumulative, not the maximum of the selected window.",
            "CPU durations, envelopes and spans are not automatically additive.",
            "No exposure, physical-wire or display latency is inferred.",
        ],
    }
    previous = None
    for report in reports:
        rows = report["rows"]
        missing = sorted(set(stages) - set(rows))
        extra = sorted(set(rows) - set(stages))
        duplicates = sorted(report["duplicates"])
        if missing or extra or duplicates:
            result["discarded_reports"].append({
                "connection": report["key"][0], "report": report["key"][1],
                "missing": missing, "extra": extra, "duplicates": duplicates,
            })
            previous = None
            continue
        result["complete_reports"] += 1
        if previous is not None:
            reason = boundary_reason(previous, report, stages, contract.get("boot_marker"))
            if reason:
                result["boundaries"].append({
                    "connection": report["key"][0], "report": report["key"][1],
                    "reason": reason,
                })
            else:
                result["last_window"] = compare(previous, report, stages)
                result["valid_windows"] += 1
        previous = report
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with args.contract.open(encoding="utf-8-sig") as stream:
            contract = json.load(stream)
        if not isinstance(contract, dict):
            raise ValueError("contract must be an object")
        with args.input.open(encoding="utf-8-sig") as stream:
            result = analyze(stream, contract)
    except (OSError, ValueError, TypeError) as exc:
        print("analysis failed: {}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["valid_windows"] else 2


if __name__ == "__main__":
    sys.exit(main())
