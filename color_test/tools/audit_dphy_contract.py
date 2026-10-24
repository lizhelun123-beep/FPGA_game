"""Audit existing D-PHY reports offline; never invoke Vivado or alter constraints."""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PERIOD = 3.571
UI = PERIOD / 2
DMIN, DMAX = 0.268, 1.518
UG471 = "https://docs.amd.com/api/khub/documents/IbGcnPFe6eF19RHma_Y~IA/content"
UG903 = "https://download.amd.com/docnav/documents/UG903_2023.1_English.pdf"
BOARD = "https://github.com/alinxalinx/AX7Z020B_2023.1/blob/master/RSTdocxs/7Z020UserManual_CN/AX7Z020UserManual.rst"


def paths_from_report(path, topology):
    """Retain reported source/capture edges, data transition and limiting corner."""
    content = path.read_text(encoding="utf-8", errors="strict")
    return paths_from_text(content, topology, path.name)


def path_components(block, data_total, clock_skew, direct=False):
    """Split input/clock primitive increments; retain signed MMCM arcs.

    Clock residual includes routing, source latency and CPR. It is not an
    independent jitter budget and must not be added to the reported skew.
    """
    markers = list(re.finditer(r"(?m)^[ \t]*\(clock [^\n]+ edge\)[ \t]*$", block))
    if len(markers) != 2:
        raise ValueError("Expected separate input-data and destination-clock sections")
    data = block[markers[0].end():markers[1].start()]
    clock = block[markers[1].end():]

    def increment(section, primitive):
        values = re.findall(
            rf"\b{primitive} \(Prop_[^\n)]+\)[ \t]*\n?[ \t]*([-\d.]+)", section
        )
        return sum(float(value) for value in values)

    result = {}
    for name, section, primitives in (
        ("data", data, ("IBUFDS", "IDELAYE2")),
        ("clock", clock, ("IBUFDS", "IDELAYE2", "BUFIO", "BUFG", "BUFH", "MMCME2_ADV", "PLLE2_ADV")),
    ):
        for primitive in primitives:
            result[f"{name}_{primitive.lower()}_ns"] = increment(section, primitive)
    if result["data_ibufds_ns"] <= 0 or (not direct and result["data_idelaye2_ns"] <= 0):
        raise ValueError("Missing expected input IBUFDS/IDELAYE2 increments")
    if result["clock_ibufds_ns"] <= 0:
        raise ValueError("Missing expected clock IBUFDS increment")
    result["data_residual_ns"] = data_total - sum(
        value for name, value in result.items() if name.startswith("data_")
    )
    result["clock_residual_ns"] = clock_skew - sum(
        value for name, value in result.items() if name.startswith("clock_")
    )
    return {name: round(value, 6) for name, value in result.items()}


def paths_from_text(content, topology, report_name):
    rows = []
    vendor = topology in {"vendor_unplaced_ALINX2023_1", "vendor_routed_AMD_FIXED"}
    leaf = r"dl[01]_[^/\s]+" if vendor else "Deserializer"
    for block in re.split(r"(?=^Slack \()", content, flags=re.M)[1:]:
        destination = re.search(rf"Destination:\s+([^\n]+/{leaf}/(DDLY|D))\b", block)
        if not destination:
            continue
        endpoint = destination[1].strip()
        endpoint_port = destination[2]
        lane = re.search(r"/dl([01])_" if vendor else r"(?:DataLaneGen|lanes)\[(\d+)\]", endpoint)
        kind = re.search(r"Path Type:\s+(Setup|Hold) \((Max|Min) at (\w+) Process Corner\)", block)
        pairing = re.search(
            r"Requirement:\s+([-\d.]+)ns\s+\(\S+ (rise|fall)@([-\d.]+)ns - "
            r"\S+ (rise|fall)@([-\d.]+)ns\)", block
        )
        if not lane or not kind or not pairing:
            raise ValueError(f"Incomplete input-path metadata in {report_name}")
        source_period = re.search(r"input port clocked by [^\n]+period=([\d.]+)ns", block)
        if not source_period or abs(float(source_period[1])-PERIOD) > 0.0005:
            raise ValueError("Report source period changed; review the external budget")
        def number(label):
            found = re.search(label + r"\s+([-\d.]+)ns", block)
            if not found:
                raise ValueError(f"Missing {label} in {report_name}")
            return float(found[1])
        slack = number(r"Slack \([^\n]+?\)\s*:")
        requirement = float(pairing[1])
        clock = number(r"Clock Path Skew:")
        data = number(r"Data Path Delay:")
        external = number(r"Input Delay:")
        uncertainty = number(r"Clock Uncertainty:")
        arc = re.search(
            rf"ISERDESE2 \({kind[1]}_iserdese2_\w+_{endpoint_port}\)\s*\n\s*([-\d.]+)", block
        )
        transition = re.search(rf"ISERDESE2\s+([rf])\s+[^\n]+/{leaf}/{endpoint_port}\b", block)
        if not arc or not transition:
            raise ValueError(f"Missing DDLY data transition or timing arc in {report_name}")
        # A setup arc can be positive: preserve its signed contribution to
        # required time instead of treating every aperture as an absolute value.
        aperture = -float(arc[1]) if kind[1] == "Setup" else float(arc[1])
        expected_input = DMAX if kind[1] == "Setup" else DMIN
        if abs(external - expected_input) > 0.0005:
            raise ValueError("Report input contract changed; audit constants must be reviewed")
        calculated = (requirement + clock - external - data - uncertainty - aperture
                      if kind[1] == "Setup" else
                      external + data - requirement - clock - uncertainty - aperture)
        if abs(calculated - slack) > 0.004:
            raise ValueError(f"Slack reconstruction mismatch: {calculated} vs {slack}")
        source = re.search(r"Source:\s+([^\n]+)", block)[1].strip()
        source_pattern = (r"data_hs_rx([pn])\[(\d+)\]$" if topology == "vendor_unplaced_ALINX2023_1"
                          else r"_([pn])\[(\d+)\]$")
        polarity = re.search(source_pattern, source)
        if not polarity or int(polarity[2]) != int(lane[1]):
            raise ValueError(f"Input source/lane mismatch: {source}")
        row = dict(
            topology=topology, lane=int(lane[1]), check=kind[1], corner=kind[3],
            capture_edge=pairing[2], capture_ns=float(pairing[3]),
            launch_edge=pairing[4], launch_ns=float(pairing[5]),
            data_transition="rise" if transition[1] == "r" else "fall",
            source=source, polarity=polarity[1], source_report=report_name, endpoint_port=endpoint_port,
            slack_ns=slack, requirement_ns=requirement, clock_skew_ns=clock,
            internal_data_ns=data, input_delay_ns=external,
            uncertainty_ns=uncertainty, aperture_ns=aperture,
            capture_shift_bound_ns=-slack if kind[1] == "Setup" else slack,
            **path_components(block, data, clock, direct=endpoint_port == "D"),
        )
        row["bit_association"] = (production_pairing(row) if topology.startswith("production_")
                                  else "STA_ONLY_UNPROVEN")
        rows.append(row)
    if not rows:
        raise ValueError(f"No input paths found in {report_name}")
    return rows


def read_corner_report(path):
    text = path.read_text(encoding="utf-8", errors="strict")
    if not text.startswith("# DPHY_CORNER_QUERY_V1\n") or not text.rstrip().endswith(
        "# DPHY_CORNER_QUERY_COMPLETE requests=32"
    ):
        raise ValueError("Incomplete/unrecognized corner query; do not use partial evidence")
    settings = re.findall(r"(?m)^# delay: (.+) taps=(\d+)$", text)
    if (len(settings) != 3 or
        sum("HSClockingX/InputDelay" in name and taps == "0" for name, taps in settings) != 1 or
        sum("HSDeserializerX/InputDelay" in name and taps == "12" for name, taps in settings) != 2):
        raise ValueError("Corner query is not the fixed production clock/data taps=0/12")
    return paths_from_text(text, "production_BUFIO_c0_d12", path.name)


def production_pairing_ok(row):
    """Check absolute association after ONLY the explicitly configured phase.

    A fixed phase is subtracted once; no modulo, UI or period adjustment is used.
    Historical reports have zero phase. Raw edge timestamps remain in every row.
    """
    phase = row.get("configured_capture_phase_ns", 0.0)
    if row["check"] == "Setup":
        return (row["launch_edge"] != row["capture_edge"] and
                abs(row["capture_ns"] - row["launch_ns"] - phase - UI) <= 0.001 and
                abs(row["requirement_ns"] - phase - UI) <= 0.001)
    return (row["launch_edge"] == row["capture_edge"] and
            abs(row["capture_ns"] - row["launch_ns"] - phase) <= 0.001 and
            abs(row["requirement_ns"] - phase) <= 0.001)


def production_pairing(row):
    """Retain weaker DDR cross-edge checks without reassigning the sampled bit."""
    if production_pairing_ok(row):
        return "PRIMARY_ADJACENT"
    expected = PERIOD if row["check"] == "Setup" else -UI
    phase = row.get("configured_capture_phase_ns", 0.0)
    same_edge = row["capture_edge"] == row["launch_edge"]
    if (same_edge == (row["check"] == "Setup") and
        abs(row["capture_ns"] - row["launch_ns"] - phase - expected) <= 0.001 and
        abs(row["requirement_ns"] - phase - expected) <= 0.001):
        return "ADDITIONAL_STA"
    return "UNPROVEN"


def coverage_rows(rows, topology, verified_sta_pairing=False):
    selected = [row for row in rows if row["topology"] == topology]
    coverage = []
    for lane, polarity, corner, edge, transition, check in product(
        range(2), ("p", "n"), ("Fast", "Slow"), ("rise", "fall"),
        ("rise", "fall"), ("Setup", "Hold")
    ):
        matches = [row for row in selected if (
            row["lane"], row["polarity"], row["corner"], row["capture_edge"],
            row["data_transition"], row["check"]
        ) == (lane, polarity, corner, edge, transition, check)]
        associations = [production_pairing(row) for row in matches] if (
            topology.startswith("production_") or verified_sta_pairing) else []
        primary = associations.count("PRIMARY_ADJACENT")
        additional = associations.count("ADDITIONAL_STA")
        pairing = ("MISSING" if not matches else "OK" if primary and
                   "UNPROVEN" not in associations else "UNPROVEN")
        coverage.append(dict(
            topology=topology, lane=lane, polarity=polarity, corner=corner,
            capture_edge=edge, data_transition=transition, check=check,
            paths=len(matches), primary_paths=primary, additional_sta_paths=additional, pairing=pairing,
            worst_slack_ns=min(row["slack_ns"] for row in matches) if matches else "UNKNOWN",
        ))
    return coverage


def window_row(rows, coverage, topology, lane, corner, capture_edge="ALL"):
    selected = [row for row in rows if row["topology"] == topology and
                (not topology.startswith("production_") or production_pairing_ok(row)) and
                (lane == "ALL" or row["lane"] == lane) and
                (corner == "ALL" or row["corner"] == corner) and
                (capture_edge == "ALL" or row["capture_edge"] == capture_edge)]
    required = [row for row in coverage if row["topology"] == topology and
                (lane == "ALL" or row["lane"] == lane) and
                (corner == "ALL" or row["corner"] == corner) and
                (capture_edge == "ALL" or row["capture_edge"] == capture_edge)]
    complete = all(row["paths"] > 0 and (not topology.startswith("production_") or
                                         row["pairing"] == "OK") for row in required)
    setup = [row for row in selected if row["check"] == "Setup"]
    hold = [row for row in selected if row["check"] == "Hold"]
    result = dict(topology=topology, lane=lane, corner=corner, capture_edge=capture_edge,
                  coverage="COMPLETE" if complete else "INCOMPLETE",
                  lower_ns="UNKNOWN", upper_ns="UNKNOWN", width_ns="UNKNOWN",
                  status="UNKNOWN")
    fields = ("setup_source", "setup_corner", "setup_capture_edge", "setup_transition",
              "hold_source", "hold_corner", "hold_capture_edge", "hold_transition",
              "pin_eye_ns", "pairing_adjustment_ns", "relative_delay_loss_ns",
              "aperture_uncertainty_ns", "reconstructed_width_ns")
    result.update(dict.fromkeys(fields, "UNKNOWN"))
    for prefix in ("data", "clock"):
        primitives = ("ibufds", "idelaye2", "residual") if prefix == "data" else (
            "ibufds", "idelaye2", "bufio", "bufg", "mmcme2_adv", "residual")
        result.update({f"loss_{prefix}_{primitive}_ns": "UNKNOWN" for primitive in primitives})
    if not setup or not hold:
        return result
    s = min(setup, key=lambda row: row["slack_ns"])
    h = min(hold, key=lambda row: row["slack_ns"])
    lower, upper = -s["slack_ns"], h["slack_ns"]
    result.update(lower_ns=lower, upper_ns=upper, width_ns=round(upper-lower, 6),
                  status=("EMPTY" if complete else "REJECTED_BY_OBSERVED_PATHS")
                  if lower > upper else "DIAGNOSTIC_SHIFT_EXISTS" if complete else "UNKNOWN")
    for prefix, row in (("setup", s), ("hold", h)):
        for output, field in (("source", "source"), ("corner", "corner"),
                              ("capture_edge", "capture_edge"), ("transition", "data_transition")):
            result[f"{prefix}_{output}"] = row[field]
    pin_eye = UI + DMIN - DMAX
    pairing_adjustment = s["requirement_ns"] - h["requirement_ns"] - UI
    relative_loss = (h["clock_skew_ns"] - s["clock_skew_ns"] -
                     (h["internal_data_ns"] - s["internal_data_ns"]))
    aperture = s["aperture_ns"] + h["aperture_ns"] + s["uncertainty_ns"] + h["uncertainty_ns"]
    width = pin_eye + pairing_adjustment - relative_loss - aperture
    if abs(width - (upper-lower)) > 0.008:
        raise ValueError("Window component budget does not reconstruct reported slack bounds")
    result.update(pin_eye_ns=round(pin_eye, 6), pairing_adjustment_ns=round(pairing_adjustment, 6),
                  relative_delay_loss_ns=round(relative_loss, 6),
                  aperture_uncertainty_ns=round(aperture, 6), reconstructed_width_ns=round(width, 6))
    for field in s:
        if field.startswith(("data_", "clock_")) and field.endswith("_ns") and field != "clock_skew_ns":
            result[f"loss_{field}"] = round(s[field]-h[field] if field.startswith("data_")
                                            else h[field]-s[field], 6)
    return result


def evidence_summary(rows):
    coverage, windows, gates = [], [], []
    for topology in sorted({row["topology"] for row in rows}):
        matrix = coverage_rows(rows, topology)
        coverage.extend(matrix)
        for lane in range(2):
            for corner in ("Fast", "Slow", "ALL"):
                for edge in ("rise", "fall", "ALL"):
                    windows.append(window_row(rows, matrix, topology, lane, corner, edge))
        windows.append(window_row(rows, matrix, topology, "ALL", "ALL"))
        selected = [row for row in rows if row["topology"] == topology]
        gates.append(dict(
            topology=topology, covered=sum(row["paths"] > 0 for row in matrix), required=len(matrix),
            complete=all(row["paths"] > 0 and (not topology.startswith("production_") or
                                               row["pairing"] == "OK") for row in matrix),
            sta_pairing_verified=all(row["pairing"] == "OK" for row in matrix),
            fixed_setting_timing_pass=all(row["slack_ns"] >= 0 for row in selected),
            physical_budget_verified=False, startup_bit_identity_verified=False,
            candidate_eligible=False,
        ))
    return coverage, windows, gates


def write_csv(name, rows):
    with (REPORTS / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def alignment_check():
    """Check chronological bit ordering across all eight raw-word boundaries.

    This is a host algebra check, not an RTL, primitive, LP or reset simulation.
    """
    def reverse(byte):
        return int(f"{byte:08b}"[::-1], 2)
    assert reverse(0xB8) == 0x1D
    payload = [0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x80, 0x96, 0x69]
    for offset in range(8):
        bits = [0] * offset
        for byte in [0xB8] + payload + [0]:
            bits.extend((byte >> index) & 1 for index in range(8))
        bits += [0] * ((-len(bits)) % 8)
        raw = [sum(bits[start + index] << (7-index) for index in range(8))
               for start in range(0, len(bits), 8)]
        alignment = 0 if offset == 0 else 8-offset
        first = 1 if offset == 0 else 2
        # Match the sync word at the documented raw-word boundary.
        sync_end = first-1
        window = (raw[sync_end-1] << 8 | raw[sync_end]) if sync_end else raw[0]
        assert (window >> alignment) & 255 == 0x1D
        for index, byte in enumerate(payload):
            newer = raw[first+index]
            older = raw[first+index-1]
            aligned = newer if alignment == 0 else (
                ((older & ((1 << alignment)-1)) << (8-alignment)) | (newer >> alignment)
            )
            assert reverse(aligned) == byte
    return len(payload) * 8


def sampling_structure_budget(report):
    """Decompose the rejected 180/45 seed, without predicting new RTL timing.

    Only setup=UI/hold=0 paths are paired. In particular, the extra DDR STA
    checks cannot fill missing primary paths. Routing-only counterfactuals
    freeze all old primitive arcs; they are never candidate acceptance.
    """
    rows = paths_from_report(report, "candidate_BUFH_DDIRECT_M3")
    primary = [r for r in rows if abs(r["requirement_ns"] -
               (UI if r["check"] == "Setup" else 0.0)) < 0.001]
    keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
             r["data_transition"], r["check"]) for r in primary]
    expected = set(product(range(2), ("p", "n"), ("Fast", "Slow"),
                           ("rise", "fall"), ("rise", "fall"), ("Setup", "Hold")))
    if len(keys) != 64 or set(keys) != expected:
        raise ValueError("Budget requires exactly 64 unique adjacent seed paths")
    if any(abs(r["capture_ns"]-r["launch_ns"]-r["requirement_ns"]) > 0.001 or
           ((r["capture_edge"] == r["launch_edge"]) != (r["check"] == "Setup"))
           for r in primary):
        raise ValueError("Budget seed bit identity changed; do not reduce modulo a period")
    topology = primary[0]["topology"]
    coverage = coverage_rows(primary, topology)
    windows = [window_row(primary, coverage, topology, "ALL", corner)
               for corner in ("Fast", "Slow", "ALL")]
    for window in windows:
        clock = sum(value for key, value in window.items()
                    if key.startswith("loss_clock_") and key.endswith("_ns"))
        data = sum(value for key, value in window.items()
                   if key.startswith("loss_data_") and key.endswith("_ns"))
        # Keep the literal 1.7855 ns UI. The printed 1.786 ns setup requirement
        # introduces a 0.5 ps reconstruction residual, not extra input budget.
        allowance = window["pin_eye_ns"] - data - window["aperture_uncertainty_ns"]
        window.update(clock_difference_ns=round(clock, 6),
                      data_difference_ns=round(data, 6),
                      allowed_clock_difference_if_other_old_terms_frozen_ns=round(allowance, 6),
                      clock_primitive_difference_ns=round(clock-window["loss_clock_residual_ns"], 6),
                      literal_input_model_width_ns=round(allowance-clock, 6),
                      frozen_old_arcs_zero_clock_residual_width_ns=round(
                          allowance-clock+window["loss_clock_residual_ns"], 6))
    return dict(scope="HISTORICAL_FIXED_SEED_BUDGET_ONLY", source_report=str(report.resolve()),
                source_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                primary_paths=len(primary), additional_sta_paths=len(rows)-len(primary),
                new_structure_timing_measured=False, current_rtl_acceptance=False,
                new_structure_clock_uncertainty_ns="UNKNOWN",
                new_structure_aperture_ns="UNKNOWN", windows=windows)


def vendor_sampling_budget(report, routed=False):
    """Screen the legally synthesized vendor core, never sign off unplaced STA.

    Native vendor endpoint/source names are retained. Only the zero-phase
    adjacent-bit pairing is used; no phase, tap, or period-folding search.
    """
    content = report.read_text(encoding="utf-8")
    if routed:
        if (not content.startswith("# AMD_PHY_FIXED_PROBE_V1 fixed data_tap=1;") or
                not content.rstrip().endswith("# AMD_PHY_FIXED_PROBE_COMPLETE requests=32") or
                set(re.findall(r"Design State\s*:\s*(\w+)", content)) != {"Routed"} or
                ", routed)" not in content):
            raise ValueError("Expected the complete own routed AMD FIXED tap1 probe")
    elif (not content.startswith("# Vendor fixed calibration, actual tap=5;") or
            set(re.findall(r"Design State\s*:\s*(\w+)", content)) != {"Synthesized"} or
            "net (fo=" not in content or ", routed)" in content):
        raise ValueError("Expected the unplaced vendor tap=5 reference, not acceptance evidence")
    topology = "vendor_routed_AMD_FIXED" if routed else "vendor_unplaced_ALINX2023_1"
    rows = paths_from_text(content, topology, report.name)
    primary = [r for r in rows if abs(r["requirement_ns"] -
               (UI if r["check"] == "Setup" else 0.0)) < 0.001]
    keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
             r["data_transition"], r["check"]) for r in primary]
    expected = set(product(range(2), ("p", "n"), ("Fast", "Slow"),
                           ("rise", "fall"), ("rise", "fall"), ("Setup", "Hold")))
    if len(keys) != 64 or set(keys) != expected:
        raise ValueError("Vendor budget requires 64 unique adjacent paths")
    if not all(production_pairing_ok(r) for r in primary):
        raise ValueError("Vendor bit identity changed; no period folding allowed")
    if any(r["clock_idelaye2_ns"] or r["clock_mmcme2_adv_ns"] or r["clock_plle2_adv_ns"] or
           r["clock_bufio_ns"] <= 0 or r["data_idelaye2_ns"] <= 0 for r in primary):
        raise ValueError("Vendor clock bypass/data-delay structure mismatch")
    if routed:
        extra = [r for r in rows if r not in primary]
        extra_keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
                       r["data_transition"], r["check"]) for r in extra]
        if len(extra_keys) != 64 or set(extra_keys) != expected:
            raise ValueError("AMD fixed probe requires 64 unique additional STA paths")
        if any(production_pairing(r) != "ADDITIONAL_STA" for r in extra):
            raise ValueError("AMD additional bit identity changed; no period folding")
        blocks = re.split(r"(?=^Slack \()", content, flags=re.M)[1:]
        if len(blocks) != len(rows) or any(r["endpoint_port"] != "DDLY" for r in rows):
            raise ValueError("AMD fixed routed block/DDLY path mismatch")
        for row, block in zip(rows, blocks):
            markers = list(re.finditer(r"(?m)^[ \t]*\(clock [^\n]+ edge\)[ \t]*$", block))
            segments = re.findall(r"net \(fo=\d+, routed\)\s+([-\d.]+)\s+[-\d.]+\s+(\S+)",
                                  block[markers[1].end():])
            if len(segments) != 2:
                raise ValueError("Expected own two-segment IBUFDS/BUFIO routed clock")
            row["clock_routed_segments"] = [dict(net=net, delay_ns=float(d)) for d, net in segments]
            row["clock_routed_print_residual_ns"] = round(
                row["clock_residual_ns"]-sum(float(d) for d, _ in segments), 6)
            if abs(row["clock_routed_print_residual_ns"]) > .004:
                raise ValueError("AMD routed clock reconstruction mismatch")
            row["bit_association"] = production_pairing(row)

    def describe(selected):
        coverage = coverage_rows(selected, topology)
        windows = []
        for corner in ("Fast", "Slow", "ALL"):
            group = [r for r in selected if corner == "ALL" or r["corner"] == corner]
            s = min((r for r in group if r["check"] == "Setup"), key=lambda r: r["slack_ns"])
            h = min((r for r in group if r["check"] == "Hold"), key=lambda r: r["slack_ns"])
            w = window_row(selected, coverage, topology, "ALL", corner)
            w.update(limiting_setup=s, limiting_hold=h,
                     data_difference_ns=round(s["internal_data_ns"]-h["internal_data_ns"], 6),
                     clock_difference_ns=round(h["clock_skew_ns"]-s["clock_skew_ns"], 6),
                     uncertainty_sum_ns=round(s["uncertainty_ns"]+h["uncertainty_ns"], 6),
                     signed_aperture_sum_ns=round(s["aperture_ns"]+h["aperture_ns"], 6))
            if routed:
                w["literal_input_model_width_ns"] = round(
                    w["pin_eye_ns"]-w["data_difference_ns"]-w["clock_difference_ns"]-
                    w["uncertainty_sum_ns"]-w["signed_aperture_sum_ns"], 6)
                w["report_rounding_residual_ns"] = round(
                    w["width_ns"]-w["literal_input_model_width_ns"], 6)
            windows.append(w)
        return windows

    ideal = []
    for row in primary:
        # Remove ALL estimated network increments in both data and clock,
        # retaining this structure's measured primitive arcs and uncertainty.
        delta = row["data_residual_ns"] - row["clock_residual_ns"]
        ideal.append(dict(row, data_residual_ns=0.0, clock_residual_ns=0.0,
                          internal_data_ns=row["internal_data_ns"]-row["data_residual_ns"],
                          clock_skew_ns=row["clock_skew_ns"]-row["clock_residual_ns"],
                          slack_ns=row["slack_ns"]+(delta if row["check"] == "Setup" else -delta)))
    result = dict(scope="UNPLACED_VENDOR_REFERENCE_BUDGET_ONLY", source_report=str(report.resolve()),
                source_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                primary_paths=len(primary), additional_sta_paths=len(rows)-len(primary),
                current_rtl_acceptance=False, routed_timing_measured=False,
                bit_identity="STA_ADJACENT_ONLY; vendor functional identity NOT_TESTED",
                windows=describe(primary), frozen_primitive_zero_network_windows=describe(ideal))
    if routed:
        result.update(scope="ROUTED_AMD_RX_FIXED_TAP1_FAMILY_ROUND2_BUDGET_ONLY",
                      routed_timing_measured=True, current_rtl_acceptance=False,
                      fixed_seed_sta_pass=all(r["slack_ns"] >= 0 for r in rows),
                      bit_identity="ABSOLUTE_STA_ADJACENT; new complete receiver function NOT_TESTED",
                      budget_positive=all(min(w["width_ns"], w["literal_input_model_width_ns"]) > 0
                                          for w in result["windows"]),
                      coverage=coverage_rows(rows, topology, verified_sta_pairing=True), paths=rows,
                      fixed_setting="data tap1; zero programmed clock phase; not a phase/tap scan",
                      residual_quantization_and_drift_bound="UNKNOWN; no section14 25ps bound adopted")
    return result


def hpc_internal_budget(report):
    return routed_probe_budget(report, bufg=False)


def bufg_feedback_budget(report):
    return routed_probe_budget(report, bufg=True)


def shared_feedback_model_budget(report):
    """Screen the feedback-output/serial shared net using its OWN unplaced arcs.

    No routing cancellation or transfer of previous probe values is assumed.
    Both adjacent and additional checks must retain their absolute bit identity.
    """
    content = report.read_text(encoding="utf-8")
    if (not content.startswith("# SHARED_FB_MODEL_V1 fixed 0/0;") or
            not content.rstrip().endswith("# SHARED_FB_MODEL_COMPLETE requests=32") or
            set(re.findall(r"Design State\s*:\s*(\w+)", content)) not in
            ({"Synthesized"}, {"Optimized"}) or
            ", routed)" in content):
        raise ValueError("Expected complete unplaced shared-feedback model")
    topology = "probe_SHARED_FB_MODEL_M3"
    rows = paths_from_text(content, topology, report.name)
    primary = [r for r in rows if abs(r["requirement_ns"] -
               (UI if r["check"] == "Setup" else 0.0)) < 0.001]
    additional = [r for r in rows if r not in primary]
    expected = set(product(range(2), ("p", "n"), ("Fast", "Slow"),
                           ("rise", "fall"), ("rise", "fall"), ("Setup", "Hold")))
    for label, group in (("adjacent", primary), ("additional", additional)):
        keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
                 r["data_transition"], r["check"]) for r in group]
        if len(keys) != 64 or set(keys) != expected:
            raise ValueError(f"Shared model requires 64 unique {label} paths")
        association = "PRIMARY_ADJACENT" if label == "adjacent" else "ADDITIONAL_STA"
        if any(production_pairing(r) != association for r in group):
            raise ValueError("Shared model bit identity changed; no period folding")
    if any(r["endpoint_port"] != "D" or r["data_idelaye2_ns"] or
           r["clock_idelaye2_ns"] or r["clock_bufg_ns"] <= 0 or
           r["clock_bufio_ns"] or r["clock_mmcme2_adv_ns"] == 0 for r in rows):
        raise ValueError("Shared model direct-data/MMCM/BUFG structure mismatch")
    arcs = re.findall(r"MMCME2_ADV \((Prop_mmcme2_adv_[^)]+)\)", content)
    if not arcs or set(arcs) != {"Prop_mmcme2_adv_CLKIN1_CLKFBOUT"}:
        raise ValueError("Shared model must use its actual CLKIN1-to-CLKFBOUT arc")
    blocks = re.split(r"(?=^Slack \()", content, flags=re.M)[1:]
    if len(blocks) != len(rows):
        raise ValueError("Shared model report block/path mismatch")
    for row, block in zip(rows, blocks):
        markers = list(re.finditer(r"(?m)^[ \t]*\(clock [^\n]+ edge\)[ \t]*$", block))
        segments = re.findall(r"net \(fo=\d+, (unplaced|estimated)\)\s+([-\d.]+)\s+[-\d.]+\s+(\S+)",
                              block[markers[1].end():])
        if len(segments) != 3:
            raise ValueError("Expected three explicitly unplaced/estimated clock-network segments")
        row["clock_model_segments"] = [dict(state=state, delay_ns=float(delay), net=net)
                                       for state, delay, net in segments]
        row["clock_model_print_residual_ns"] = round(row["clock_residual_ns"]-
                                                       sum(float(d) for _, d, _ in segments), 6)
        if abs(row["clock_model_print_residual_ns"]) > .004:
            raise ValueError("Shared model network reconstruction mismatch")
    coverage = coverage_rows(primary, topology)

    def describe(model_rows):
        result = []
        for corner in ("Fast", "Slow", "ALL"):
            group = [r for r in model_rows if corner == "ALL" or r["corner"] == corner]
            setup = min((r for r in group if r["check"] == "Setup"), key=lambda r:r["slack_ns"])
            hold = min((r for r in group if r["check"] == "Hold"), key=lambda r:r["slack_ns"])
            w = window_row(model_rows, coverage, topology, "ALL", corner)
            w.update(limiting_setup=setup, limiting_hold=hold,
                     data_difference_ns=round(setup["internal_data_ns"]-hold["internal_data_ns"], 6),
                     clock_difference_ns=round(hold["clock_skew_ns"]-setup["clock_skew_ns"], 6),
                     uncertainty_sum_ns=round(setup["uncertainty_ns"]+hold["uncertainty_ns"], 6),
                     signed_aperture_sum_ns=round(setup["aperture_ns"]+hold["aperture_ns"], 6))
            w["literal_input_model_width_ns"] = round(w["pin_eye_ns"]-w["data_difference_ns"]-
                w["clock_difference_ns"]-w["uncertainty_sum_ns"]-w["signed_aperture_sum_ns"], 6)
            w["report_rounding_residual_ns"] = round(w["width_ns"]-w["literal_input_model_width_ns"], 6)
            w["clock_difference_zero_width_limit_ns"] = round(w["pin_eye_ns"]-
                w["data_difference_ns"]-w["uncertainty_sum_ns"]-w["signed_aperture_sum_ns"], 6)
            result.append(w)
        return result

    windows = describe(primary)
    # Diagnostic counterfactual only: MMCM compensation arcs also depend on
    # feedback routing. Freezing those arcs is NOT a physical topology bound.
    zero_network = []
    for original in primary:
        row = dict(original, clock_skew_ns=original["clock_skew_ns"]-original["clock_residual_ns"],
                   clock_residual_ns=0, clock_model_print_residual_ns=0,
                   clock_model_segments=[dict(segment, delay_ns=0, state="COUNTERFACTUAL_ZERO")
                                         for segment in original["clock_model_segments"]])
        row["slack_ns"] = round(row["requirement_ns"]+row["clock_skew_ns"]-row["input_delay_ns"]-
            row["internal_data_ns"]-row["uncertainty_ns"]-row["aperture_ns"] if row["check"] == "Setup"
            else row["input_delay_ns"]+row["internal_data_ns"]-row["requirement_ns"]-
            row["clock_skew_ns"]-row["uncertainty_ns"]-row["aperture_ns"], 6)
        row["capture_shift_bound_ns"] = -row["slack_ns"] if row["check"] == "Setup" else row["slack_ns"]
        zero_network.append(row)
    positive = all(min(w["width_ns"], w["literal_input_model_width_ns"]) > 0 for w in windows)
    return dict(scope="UNPLACED_SHARED_FEEDBACK_MODEL_ONLY", source_report=str(report.resolve()),
                source_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                design_state=next(iter(set(re.findall(r"Design State\s*:\s*(\w+)", content)))),
                feedback_family_attempt=2, primary_paths=len(primary), additional_sta_paths=len(additional),
                routed_timing_measured=False, current_rtl_acceptance=False,
                bit_identity="ABSOLUTE_STA_ADJACENT; receiver functional identity NOT_TESTED",
                budget_positive=positive, implementation_authorized_by_budget=False,
                phase_grid_status="REQUIRED_IF_ROUTED_WINDOW_POSITIVE" if positive else "NOT_EVALUATED_EMPTY_WINDOW",
                coverage=coverage, windows=windows, paths=rows,
                frozen_own_primitive_zero_network_windows=describe(zero_network),
                counterfactual_scope="OWN_FROZEN_ARCS_ONLY_NOT_PHYSICAL_OR_ACCEPTANCE_BOUND")


def routed_probe_budget(report, bufg=False, local_clock=False, pll=False):
    """One routed fixed seed; keep absolute adjacent-bit identities and own arcs.

    The two explicit modes share the parser, never their path numbers. Vivado
    2023.1 reports at most three decimals; retain rounding, not extra eye margin.
    BUFG evidence must include all weaker checks as well as the adjacent checks.
    """
    if sum((bufg, local_clock, pll)) > 1:
        raise ValueError("Local and MMCM/BUFG probe modes are exclusive")
    tag = "LOCAL_CLOCK" if local_clock else "BUFG_FEEDBACK" if bufg else "HPC_INTERNAL"
    label = "LOCAL_CLOCK" if local_clock else "BUFG" if bufg else "HPC"
    setting = "clock_tap=0" if local_clock else "0/0"
    if pll:
        tag, label = "PLL_CLOCK", "PLL_CLOCK"
        setting = "serial_phase=-90 byte_phase=-22.5"
    content = report.read_text(encoding="utf-8")
    if (not content.startswith(f"# {tag}_PROBE_V1 fixed {setting};") or
            not content.rstrip().endswith(f"# {tag}_PROBE_COMPLETE requests=32") or
            set(re.findall(r"Design State\s*:\s*(\w+)", content)) != {"Routed"} or
            ", routed)" not in content):
        raise ValueError(f"Expected complete routed fixed {setting} {label} probe")
    topology = f"probe_{tag}_tap0" if local_clock else f"probe_{tag}_M3"
    if pll:
        topology = "probe_PLL_CLOCK_M4"
    rows = paths_from_text(content, topology, report.name)
    phase = -PERIOD / 4 if pll else 0.0
    if pll:
        for row in rows:
            row["configured_capture_phase_ns"] = phase
    primary = [r for r in rows if abs(r["requirement_ns"] -
               phase - (UI if r["check"] == "Setup" else 0.0)) < 0.001]
    expected = set(product(range(2), ("p", "n"), ("Fast", "Slow"),
                           ("rise", "fall"), ("rise", "fall"), ("Setup", "Hold")))
    keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
             r["data_transition"], r["check"]) for r in primary]
    if len(keys) != 64 or set(keys) != expected:
        raise ValueError(f"{label} budget requires 64 unique adjacent paths")
    if not all(production_pairing_ok(r) for r in primary):
        raise ValueError(f"{label} bit identity changed; no period folding allowed")
    if local_clock:
        if any(r["data_idelaye2_ns"] or r["clock_idelaye2_ns"] <= 0 or
               r["clock_bufio_ns"] <= 0 or r["clock_bufg_ns"] or r["clock_bufh_ns"] or
               r["clock_mmcme2_adv_ns"] for r in rows):
            raise ValueError("Local direct-data/clock-IDELAY/BUFIO structure mismatch")
    elif pll:
        if any(r["data_idelaye2_ns"] or r["clock_idelaye2_ns"] or
               r["clock_bufio_ns"] or r["clock_bufh_ns"] or r["clock_mmcme2_adv_ns"] or
               r["clock_bufg_ns"] <= 0 or r["clock_plle2_adv_ns"] == 0 for r in rows):
            raise ValueError("PLL direct-data/actual-PLL/BUFG structure mismatch")
    elif any(r["data_idelaye2_ns"] or r["clock_idelaye2_ns"] or
           (r["clock_bufg_ns"] <= 0 or r["clock_bufio_ns"] != 0 if bufg else
            r["clock_bufio_ns"] <= 0) or r["clock_mmcme2_adv_ns"] == 0 for r in primary):
        raise ValueError(f"{label} direct-data/MMCM/buffer structure mismatch")
    if bufg or local_clock or pll:
        extra = [r for r in rows if r not in primary]
        extra_keys = [(r["lane"], r["polarity"], r["corner"], r["capture_edge"],
                       r["data_transition"], r["check"]) for r in extra]
        if len(extra_keys) != 64 or set(extra_keys) != expected:
            raise ValueError(f"{label} budget requires 64 unique additional STA paths")
        if not all(production_pairing(r) == "ADDITIONAL_STA" for r in extra):
            raise ValueError(f"{label} additional bit identity changed")
        for r in rows:
            if r["endpoint_port"] != "D":
                raise ValueError(f"{label} budget requires actual D endpoints")
    blocks = re.split(r"(?=^Slack \()", content, flags=re.M)[1:]
    if len(blocks) != len(rows):
        raise ValueError(f"{label} routed block/path mismatch")
    for row, block in zip(rows, blocks):
        markers = list(re.finditer(r"(?m)^[ \t]*\(clock [^\n]+ edge\)[ \t]*$", block))
        segments = re.findall(r"net \(fo=\d+, routed\)\s+([-\d.]+)\s+[-\d.]+\s+(\S+)",
                              block[markers[1].end():])
        if len(segments) != 3:
            raise ValueError("Expected three routed clock segments through input, clock element and serial buffer")
        row["clock_routed_segments"] = [dict(net=net, delay_ns=float(delay)) for delay, net in segments]
        row["clock_routed_print_residual_ns"] = round(row["clock_residual_ns"]-
                                                      sum(float(d) for d, _ in segments), 6)
        if abs(row["clock_routed_print_residual_ns"]) > .004:
            raise ValueError("Routed clock segment reconstruction mismatch")
    if local_clock or pll:
        for row in rows:
            row["bit_association"] = production_pairing(row)
    coverage = coverage_rows(rows if local_clock or pll else primary, topology,
                             verified_sta_pairing=local_clock or pll)
    windows = []
    for corner in ("Fast", "Slow", "ALL"):
        group = [r for r in primary if corner == "ALL" or r["corner"] == corner]
        s = min((r for r in group if r["check"] == "Setup"), key=lambda r: r["slack_ns"])
        h = min((r for r in group if r["check"] == "Hold"), key=lambda r: r["slack_ns"])
        w = window_row(primary, coverage, topology, "ALL", corner)
        w.update(limiting_setup=s, limiting_hold=h,
                 data_difference_ns=round(s["internal_data_ns"]-h["internal_data_ns"], 6),
                 clock_difference_ns=round(h["clock_skew_ns"]-s["clock_skew_ns"], 6),
                 uncertainty_sum_ns=round(s["uncertainty_ns"]+h["uncertainty_ns"], 6),
                 signed_aperture_sum_ns=round(s["aperture_ns"]+h["aperture_ns"], 6))
        # Do not count the printed 1.786 ns requirement's 0.5 ps excess as eye.
        w["literal_input_model_width_ns"] = round(
            w["pin_eye_ns"]-w["data_difference_ns"]-w["clock_difference_ns"]-
            w["uncertainty_sum_ns"]-w["signed_aperture_sum_ns"], 6)
        w["report_rounding_residual_ns"] = round(
            w["width_ns"]-w["literal_input_model_width_ns"], 6)
        windows.append(w)
    return dict(scope=f"ROUTED_FIXED_{label}_BUDGET_PROBE_ONLY", source_report=str(report.resolve()),
                source_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                primary_paths=len(primary), additional_sta_paths=len(rows)-len(primary),
                routed_timing_measured=True, current_rtl_acceptance=False,
                bit_identity="ABSOLUTE_STA_ADJACENT; new receiver functional identity NOT_TESTED",
                budget_positive=all(min(w["width_ns"], w["literal_input_model_width_ns"]) > 0
                                    for w in windows),
                phase_grid_status=("REQUIRED_BEFORE_ACCEPTANCE" if all(w["width_ns"] > 0 for w in windows)
                                   else "NOT_EVALUATED_EMPTY_OR_ZERO_WINDOW"),
                coverage=coverage, windows=windows, paths=rows)


def local_clock_budget(report):
    """Own routed clock-tap0 evidence. Nominal grid arithmetic is not a tap sweep."""
    budget = routed_probe_budget(report, local_clock=True)
    primary = [r for r in budget["paths"] if r["bit_association"] == "PRIMARY_ADJACENT"]
    reach = []
    for window in budget["windows"]:
        group = [r for r in primary if window["corner"] == "ALL" or r["corner"] == window["corner"]]
        result = dict(corner=window["corner"],
                      seed_worst_setup_ns=min(r["slack_ns"] for r in group if r["check"] == "Setup"),
                      seed_worst_hold_ns=min(r["slack_ns"] for r in group if r["check"] == "Hold"),
                      nominal_tap_step_ns=.078125, tap_range=[0, 31],
                      scope="NOMINAL_ARITHMETIC_ONLY_NOT_OTHER_TAP_STA", residual_drift_error="UNKNOWN")
        if min(window["width_ns"], window["literal_input_model_width_ns"]) <= 0:
            result.update(status="NOT_EVALUATED_EMPTY_WINDOW")
        else:
            # Do not count the printed requirement's sub-ps excess as margin.
            lower = window["lower_ns"]
            upper = window["upper_ns"]-max(0, window["report_rounding_residual_ns"])
            low, high = max(0, math.ceil(lower/.078125)), min(31, math.floor(upper/.078125))
            result.update(lower_ns=lower, conservative_upper_ns=upper,
                          nominal_k_low=low, nominal_k_high=high,
                          status="NO_REACHABLE_NONNEGATIVE_NOMINAL_TAP" if low > high else
                                 "NOMINAL_TAP_EXISTS_REQUIRES_OWN_SETTING_STA_AND_ERROR_BOUND")
        reach.append(result)
    budget.update(clock_tap=0, clock_compensation_mode="NOT_APPLICABLE_NO_MMCM",
                  calibration_controller="NOT_IMPLEMENTED", calibration_acceptance="NOT_ADOPTED",
                  fixed_seed_sta_pass=all(r["slack_ns"] >= 0 for r in budget["paths"]),
                  per_corner_windows_positive=all(min(w["width_ns"], w["literal_input_model_width_ns"]) > 0
                                                 for w in budget["windows"] if w["corner"] != "ALL"),
                  nominal_grid_diagnostic=reach)
    return budget


def pll_clock_budget(report):
    """One PLL setting's own paths; static phase arithmetic never scans STA."""
    budget = routed_probe_budget(report, pll=True)
    phase, quantum = -PERIOD / 4, PERIOD / 32
    reach = []
    for window in budget["windows"]:
        result = dict(corner=window["corner"], fixed_seed_phase_ns=phase,
                      nominal_quantum_ns=quantum, seed_quantum_index=-8,
                      residual_drift_error="UNKNOWN_NOT_A_PROVED_25PS_BOUND")
        if min(window["width_ns"], window["literal_input_model_width_ns"]) <= 0:
            result["status"] = "NO_FIXED_PHASE_CAN_OPEN_EMPTY_WINDOW"
        else:
            low = window["lower_ns"]
            high = window["upper_ns"] - max(0, window["report_rounding_residual_ns"])
            # Absolute programmed phase range; never wrap a bound by T or UI.
            first = max(-32, math.ceil((phase + low) / quantum))
            last = min(32, math.floor((phase + high) / quantum))
            result.update(absolute_phase_lower_ns=phase + low, absolute_phase_upper_ns=phase + high,
                          first_quantum_index=first, last_quantum_index=last,
                          status="NO_NOMINAL_STATIC_GRID_POINT" if first > last else
                          "NOMINAL_GRID_ONLY_OTHER_SETTINGS_NOT_TIMED",
                          fixed_seed_lower_margin_ns=-low, fixed_seed_upper_margin_ns=high)
        reach.append(result)
    budget.update(configured_phase_ns=phase, vco_mhz=4000 / PERIOD,
                  serial_phase_deg=-90.0, byte_phase_deg=-22.5,
                  clock_primitive="PLLE2_ADV", clock_compensation_mode="SEE_OWN_ROUTED_PROPERTIES",
                  fixed_seed_sta_pass=all(r["slack_ns"] >= 0 for r in budget["paths"]),
                  nominal_grid_diagnostic=reach, residual_drift_error="UNKNOWN",
                  current_rtl_acceptance=False, calibration_acceptance="NOT_ADOPTED")
    return budget


def training_guard_reference(observation):
    """Offline lane1-first reference proof; never infer truth from tested lane0."""
    import struct
    vhdl = ROOT / "repo/ip/MIPI_CSI_2_RX/hdl/ECC.vhd"
    table = re.search(r"constant syndrome.*?:=.*?\((.*?)\);", vhdl.read_text(encoding="utf-8"), re.S)
    syndromes = [int(x, 2) for x in re.findall(r'"([01]{8})"', table[1])]
    if len(syndromes) != 24:
        raise ValueError("Exact existing ECC parity table required")

    def header(dtype, count):
        value = dtype | (count << 8)
        parity = 0
        for bit, mask in enumerate(syndromes):
            if (value >> bit) & 1:
                parity ^= mask
        return bytes((dtype, count & 255, count >> 8, parity))

    def transitions(sequence):
        bits = "".join("".join(str((b >> i) & 1) for i in range(8)) for b in sequence)
        return {str(p): {kind: sum(bits[i-1:i+1] == kind for i in range(1, len(bits)) if i % 2 == p)
                        for kind in ("01", "10")} for p in (0, 1)}

    # Predicate domain0..720 admits both observed numbering conventions; other
    # values reject calibration. It does not assert the sensor's numbering law.
    codebook = {}
    untyped = {}
    for count in range(721):
        for dtype in (2, 3):
            h = header(dtype, count)
            key = (dtype, h[1], h[3])
            if key in codebook:
                raise ValueError("Lane1 parity reference is not unique")
            codebook[key] = h
            untyped[(h[1], h[3])] = h
    long = header(0x2b, 1600)
    root_pair = (long[1], long[3])
    assert root_pair == (0x40, 0x3b) and root_pair not in untyped
    one_bit_aliases = 0
    for key in codebook:
        packed = key[1] | (key[2] << 8)
        for bit in range(16):
            changed = packed ^ (1 << bit)
            one_bit_aliases += (key[0], changed & 255, changed >> 8) in codebook
    assert one_bit_aliases == 0
    # Packet class must come from independent LP duration, not a two-byte match:
    # LS65 has lane1(41,3b), one bit from the known long-header pair(40,3b).
    root_alias = header(2, 65)
    assert (root_alias[1], root_alias[3]) == (0x41, 0x3b)
    assert (root_pair[0] ^ root_alias[1]).bit_count() == 1

    data = json.loads((observation / "raw_analysis.json").read_text(encoding="utf-8"))
    points = []
    total_short = total_long = matching_triplets = 0
    short_lengths, long_lengths = [], []
    for point in data["points"]:
        raw = (observation / "board_receipts" / ("tap_%02d.bin" % point["tap"])).read_bytes()
        if hashlib.sha256(raw).hexdigest() != point["sha256"]:
            raise ValueError("Raw artifact identity changed")
        words = struct.unpack("<8192I", raw)
        lp1 = [(w >> 18) & 3 for w in words]
        bits = "".join(format((w >> 8) & 255, "08b") for w in words)
        refs = []
        bursts = []
        coverage = [{str(p): {kind: 0 for kind in ("01", "10")} for p in (0, 1)} for _ in (0, 1)]
        complete_short = complete_long = 0
        for packet in point["packets"]:
            pos = packet["sot_bit_positions"][1]
            assert bits[pos:pos+8] == "00011101"
            pair = tuple(int(bits[j:j+8][::-1], 2) for j in (pos+8, pos+16))
            start = packet["lp00_entry_word"]
            end = next((j for j in range(start+1, len(lp1)) if lp1[j] != 0), None)
            if end is None:
                continue  # Never train on a trailing partial burst.
            length = end - start
            if 12 <= length <= 16:
                short_lengths.append(length)
                bursts.append(dict(kind="short", pair=pair, oracle=packet["header"]))
            elif 814 <= length <= 818:
                assert pair == root_pair, "Long-class lane1 fixed reference rejected"
                long_lengths.append(length); complete_long += 1
                bursts.append(dict(kind="long", pair=pair, oracle=packet["header"]))
            else:
                raise ValueError("Unknown observed LP burst class: %s" % length)
        typed_short = {}
        for i in range(max(0, len(bursts)-2)):
            if [b["kind"] for b in bursts[i:i+3]] == ["short", "long", "short"]:
                for index, dtype in ((i, 2), (i+2, 3)):
                    if index in typed_short and typed_short[index] != dtype:
                        raise ValueError("Ambiguous LP packet ordering")
                    typed_short[index] = dtype
        for index, burst in enumerate(bursts):
            if burst["kind"] == "short":
                if index not in typed_short:
                    refs.append(None)
                    continue  # Boundary short packet has no independent DT.
                expected = codebook.get((typed_short[index], *burst["pair"]))
                assert expected is not None, "Independently typed short reference rejected"
                complete_short += 1
            else:
                expected = long
            # This comparison is only the regression oracle. No lane0 byte is
            # used to construct expected: pair came solely from raw lane1.
            assert expected.hex() == burst["oracle"]
            refs.append((expected[0], int.from_bytes(expected[1:3], "little")))
            for lane in (0, 1):
                counts = transitions(bytes((0xb8, expected[lane], expected[lane+2])))
                for parity in ("0", "1"):
                    for kind in ("01", "10"):
                        coverage[lane][parity][kind] += counts[parity][kind]
        triplets = sum(refs[i] is not None and refs[i][0] == 2 and refs[i+1] == (0x2b, 1600) and
                       refs[i+2] == (3, refs[i][1]) for i in range(max(0, len(refs)-2)))
        points.append(dict(tap=point["tap"], complete_short=complete_short, complete_long=complete_long,
                           matching_triplets=triplets, expected_transition_coverage=coverage,
                           both_lanes_all_classes=all(n > 0 for lane in coverage for kinds in lane.values() for n in kinds.values())))
        total_short += complete_short; total_long += complete_long; matching_triplets += triplets
    assert total_short == 2*matching_triplets and (total_long, matching_triplets) == (126, 126)
    qualified_points = [p["tap"] for p in points if p["both_lanes_all_classes"]]
    assert qualified_points == [4, 5, 22, 25, 28]
    witnesses = []
    for count in range(256, 260):
        for dtype in (2, 3):
            true = header(dtype, count); alias = header(dtype, count+256)
            assert true[1] == alias[1] and true[3] ^ alias[3] == 3
            assert codebook[(dtype, alias[1], alias[3])] == alias
            witnesses.append(dict(true_header=true.hex(), alias_header=alias.hex(),
                                  changed_lane1_ECC_bits=2, true_count=count, alias_count=count+256))
    return dict(status="REFERENCE_FUNCTION_PROOF_PASS_CONDITIONAL_ON_QUALIFIED_LANE1_AND_LP_CLASSIFIER",
                production_candidate_admitted=False, source_ECC_sha256=hashlib.sha256(vhdl.read_bytes()).hexdigest(),
                root_lane1=dict(sequence="b8403b", transition_coverage=transitions(bytes.fromhex("b8403b"))),
                independent_reference=dict(domain="DT2/3,count0..720; other counts reject, not a claimed camera numbering guarantee",
                    cases=1442, collisions=0, single_bit_mutations_checked=1442*16, single_bit_valid_aliases=one_bit_aliases,
                    construction="Infer DT independently from LP short/long/short ordering, then high-counter from rawlane1 low-counter/ECC; lane0 is an erased/tested symbol",
                    prerequisite="Lane1 must already have qualified timing margin and unexpired validity; no circular use of unqualified lane0"),
                LP_classifier=dict(short_range_words=[12,16], long_range_words=[814,818],
                    observed_short_range=[min(short_lengths),max(short_lengths)], observed_long_range=[min(long_lengths),max(long_lengths)],
                    source="Observed-mode LP-word separation; +/-2word acceptance guard is a proposed classifier, not measured metastability or vendor maximum",
                    prerequisites="Complete LP00 burst bracketed by stable LP11, valid same-epoch clock; prove synchronizer endpoint error<=2words and reject otherstates/lengths/partialbursts in implementation",
                    necessary_counterexample=dict(short_header=root_alias.hex(), short_lane1="413b", long_lane1="403b", distance_bits=1,
                        meaning="Byte match alone cannot distinguish long/short under onebit error; independent LP class is mandatory")),
                actual=dict(short_reference_matches=total_short, long_root_matches=total_long, matching_triplets=matching_triplets,
                    points=points, all_transition_points=qualified_points, inference_not_signed="Only5points exercise every expected lane/DDR/transition class; no current three-guard epoch or production timing inferred"),
                unqualified_anchor_alias=dict(sequence_pairs="256..259 ->512..515 (both legal in reference domain)",
                    witnesses=witnesses, unchanged="SoT, line lowbyte, RAW10 header/payload/CRC; both LS/LE counter sequences remain consecutive and match",
                    meaning="Two ECCbit errors on an unqualified lane1 can select the wrong valid expected lane0 sequence. Packet ECC/CRC/continuity cannot by themselves qualify the reference anchor"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corners-report", type=Path,
                        help="completed fixed-setting report from --corners-only; never auto-use stale reports")
    parser.add_argument("--require-eligible", action="store_true",
                        help="exit 2 when evidence/timing/physical/startup qualification is blocked")
    parser.add_argument("--sampling-budget", type=Path,
                        help="decompose the historical D-direct 180/45 seed; does not refresh acceptance reports")
    parser.add_argument("--vendor-sampling-budget", type=Path,
                        help="screen the generated ALINX/AMD unplaced tap=5 structure; never acceptance")
    parser.add_argument("--amd-phy-fixed-budget", type=Path,
                        help="audit own routed complete AMD RX/FIXED tap1 family round2 probe")
    parser.add_argument("--hpc-internal-budget", type=Path,
                        help="audit the single routed HPC/internal-feedback 0/0 budget probe")
    parser.add_argument("--bufg-feedback-budget", type=Path,
                        help="audit the single routed BUFG-feedback/D-direct 0/0 budget probe")
    parser.add_argument("--shared-feedback-model-budget", type=Path,
                        help="screen shared feedback-output/serial BUFG unplaced model; never acceptance")
    parser.add_argument("--local-clock-budget", type=Path,
                        help="audit ONE routed local clock-IDELAY tap0 / D-direct seed; no calibration")
    parser.add_argument("--pll-clock-budget", type=Path,
                        help="audit ONE own routed PLL M4/D1/O4/O16 negative-phase seed")
    parser.add_argument("--budget-output", type=Path,
                        help="JSON output for --sampling-budget (default: build/dphy_sampling/structure_budget.json)")
    parser.add_argument("--training-contract", type=Path,
                        help="offline lane1-first reference proof over one retained finite-observation directory")
    args = parser.parse_args()
    if args.training_contract:
        if any(getattr(args, key) for key in vars(args) if key not in ("training_contract", "budget_output")):
            parser.error("Training-reference proof is separate from historical budget/acceptance modes")
        result = training_guard_reference(args.training_contract)
        output = args.budget_output or args.training_contract / "training_guard_contract/reference_proof.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "actual_short": result["actual"]["short_reference_matches"],
                          "actual_long": result["actual"]["long_root_matches"], "all_transition_points": result["actual"]["all_transition_points"]}))
        return
    if args.amd_phy_fixed_budget:
        if any((args.pll_clock_budget, args.local_clock_budget, args.shared_feedback_model_budget,
                args.bufg_feedback_budget, args.hpc_internal_budget, args.sampling_budget,
                args.vendor_sampling_budget, args.corners_report, args.require_eligible)):
            parser.error("AMD complete PHY fixed probe is separate from all other modes")
        budget = vendor_sampling_budget(args.amd_phy_fixed_budget, routed=True)
        output = args.budget_output or ROOT / "build/dphy_sampling/amd_phy_fixed_probe/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_AMD_PHY_FIXED_BUDGET: {output}; positive={budget['budget_positive']}; family round2")
        return
    if args.pll_clock_budget:
        if any((args.local_clock_budget, args.shared_feedback_model_budget, args.bufg_feedback_budget,
                args.hpc_internal_budget, args.sampling_budget, args.vendor_sampling_budget,
                args.corners_report, args.require_eligible)):
            parser.error("PLL fixed probe is separate from every historical/acceptance mode")
        budget = pll_clock_budget(args.pll_clock_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/pll_clock_probe/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_PLL_CLOCK_BUDGET: {output}; positive={budget['budget_positive']}; fixed probe only")
        return
    if args.local_clock_budget:
        if (args.shared_feedback_model_budget or args.bufg_feedback_budget or args.hpc_internal_budget or
                args.sampling_budget or args.vendor_sampling_budget or args.corners_report or args.require_eligible):
            parser.error("Local fixed probe is separate from all other budget/acceptance modes")
        budget = local_clock_budget(args.local_clock_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/local_clock_probe/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_LOCAL_CLOCK_BUDGET: {output}; positive={budget['budget_positive']}; calibration NOT_ADOPTED")
        return
    if args.shared_feedback_model_budget:
        if (args.bufg_feedback_budget or args.hpc_internal_budget or args.sampling_budget or
                args.vendor_sampling_budget or args.corners_report or args.require_eligible):
            parser.error("Shared unplaced model is separate from routed/acceptance/history modes")
        budget = shared_feedback_model_budget(args.shared_feedback_model_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/shared_feedback_model/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_SHARED_FEEDBACK_MODEL: {output}; positive={budget['budget_positive']}; NOT_ROUTED")
        return
    if args.bufg_feedback_budget:
        if (args.hpc_internal_budget or args.sampling_budget or args.vendor_sampling_budget or
                args.corners_report or args.require_eligible):
            parser.error("BUFG probe budget is separate from acceptance/history/other probes")
        budget = bufg_feedback_budget(args.bufg_feedback_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/bufg_feedback_probe/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_BUFG_FEEDBACK_BUDGET: {output}; positive={budget['budget_positive']}; probe only")
        return
    if args.hpc_internal_budget:
        if args.sampling_budget or args.vendor_sampling_budget or args.corners_report or args.require_eligible:
            parser.error("HPC probe budget is separate from acceptance/history/vendor modes")
        budget = hpc_internal_budget(args.hpc_internal_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/hpc_internal_probe/budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_HPC_INTERNAL_BUDGET: {output}; positive={budget['budget_positive']}; probe only")
        return
    if args.vendor_sampling_budget:
        if args.sampling_budget or args.corners_report or args.require_eligible:
            parser.error("Vendor reference budget mode is separate from acceptance/history")
        budget = vendor_sampling_budget(args.vendor_sampling_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/vendor_structure_budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_UNPLACED_VENDOR_BUDGET: {output}; not routed or functional acceptance")
        return
    if args.sampling_budget:
        if args.corners_report or args.require_eligible:
            parser.error("Historical budget mode is separate from acceptance")
        budget = sampling_structure_budget(args.sampling_budget)
        output = args.budget_output or ROOT / "build/dphy_sampling/structure_budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(budget, indent=2)+"\n", encoding="utf-8")
        print(f"DPHY_HISTORICAL_STRUCTURE_BUDGET: {output}; not new-structure timing")
        return
    if args.budget_output:
        parser.error("--budget-output requires a sampling/vendor/HPC budget mode")
    rows = (read_corner_report(args.corners_report) if args.corners_report else
            paths_from_report(REPORTS / "dphy_sampling_baseline.rpt", "production_BUFIO_c0_d12"))
    rows += paths_from_report(REPORTS / "dphy_clock_ooc_timing.rpt", "OOC_BUFG_phase60_d12")
    coverage, windows, gates = evidence_summary(rows)
    write_csv("dphy_contract_paths.csv", rows)
    write_csv("dphy_contract_coverage.csv", coverage)
    write_csv("dphy_contract_corner_windows.csv", windows)
    (REPORTS / "dphy_contract_gate.json").write_text(
        json.dumps(dict(schema_version=1, topologies=gates), indent=2) + "\n", encoding="utf-8"
    )
    budget = []
    for lane, pins in enumerate(("W11/Y11", "U9/U8")):
        for edge in ("rise", "fall"):
            budget.append(dict(
                lane=lane, clock_reference_edge=edge, data_p_n_pins=pins,
                clock_p_n_pins="Y7/Y6", period_model_ns=PERIOD,
                half_period_model_ns=UI, input_min_model_ns=DMIN,
                input_max_model_ns=DMAX, modeled_pin_setup_ns=round(UI-DMAX, 6),
                modeled_pin_hold_ns=DMIN, modeled_pin_eye_ns=round(UI+DMIN-DMAX, 6),
                sensor_setup_guarantee_ns="UNKNOWN", sensor_hold_guarantee_ns="UNKNOWN",
                module_pcb_relative_delay_min_ns="UNKNOWN",
                module_pcb_relative_delay_max_ns="UNKNOWN",
                fpc_relative_delay_min_ns="UNKNOWN", fpc_relative_delay_max_ns="UNKNOWN",
                carrier_pcb_relative_delay_min_ns="UNKNOWN",
                carrier_pcb_relative_delay_max_ns="UNKNOWN",
                relative_jitter_bound_ns="UNKNOWN", duty_cycle_bound_ns="UNKNOWN",
                sensor_module_revision="UNKNOWN", physical_status="UNVERIFIED",
                hardware="ALINX 7020B / ALINX kit OV5640 / 15p FPC 15 cm (user supplied)",
            ))
    write_csv("dphy_external_budget.csv", budget)
    # Packet bytes can straddle two primitive output words. Q8->bit0 is
    # true for an aligned byte only; retain all eight possible word offsets.
    mapping = [dict(
        payload_start_offset=offset, word_alignment=(8-offset) % 8,
        chronological_payload_bit=j,
        capture_if_first_rise="rise" if j % 2 == 0 else "fall",
        capture_if_first_fall="fall" if j % 2 == 0 else "rise",
        raw_word_relative=(offset+j)//8,
        iserdes_output=f"Q{8-(offset+j)%8}", captured_raw_bit=7-(offset+j)%8,
        aligned_raw_bit=7-j, aligned_ppi_bit=j,
        status="conditional on valid eye, completed alignment and qualified reset release",
    ) for offset in range(8) for j in range(8)]
    write_csv("dphy_capture_bit_map.csv", mapping)
    checks = alignment_check()
    lines = [
        "# D-PHY 外部契约与 capture/bit 审核", "",
        "本报告仅解析已有报告并核对位序代数；审计器不调用 Vivado，不修改 RTL/XDC，不操作板卡。",
        "数值窗口依据当前输入模型，不能代替尚未闭合的物理预算。", "",
        "## 外部预算", "",
        "用户确认：ALINX 7020B、ALINX 套件 OV5640、15p FPC、15 cm。模组版本未知。",
        f"[ALINX 官方引脚表]({BOARD}) 与生产 HS pins 一致；没有提供可用于本次预算的走线差值。",
        "四项 lane/参考时钟边沿分别列于 `dphy_external_budget.csv`；UNKNOWN 不是零。",
        f"当前 T={PERIOD} ns，UI={UI} ns，dmin={DMIN} ns，dmax={DMAX} ns。",
        f"保证引脚窗口为 [1.518, 2.0535] ns，宽 {UI+DMIN-DMAX:.4f} ns。",
        "此为沿用的 15% UI 接收模型，未证明为实际传感器/板级保证。",
        "",
        "各 lane、各参考边沿需要独立闭合：",
        "- sensor 输出 setup/hold 保证、实际半周期范围、占空比/频率容差；",
        "- 模组 PCB、FPC、底板 PCB 的 data-minus-clock 最小/最大传播差值；",
        "- 相对抖动及测量/供应商保证条件，避免与 clock uncertainty 重复计入。",
        "15 cm 的共模传播时间不能直接作为 data-to-clock 偏斜。",
        "",
        "令边沿 E_n 后建立 b_n，下一边沿为 E_(n+1)。若源端保持 h、建立 s，",
        "外部相对传播差 Δ，则 dmin=h+Δmin，dmax=(E_(n+1)-E_n)-s+Δmax。",
        "这些界限还须包含一次相对抖动预算；当前未取得其物理数值。",
        f"[UG903]({UG903}) 定义输入延时为 FPGA 引脚处相对于外部参考时钟的时间。",
        "内部 IBUF/IDELAY/MMCM 已包含在路径模型中，不加入外部预算。", "",
        "## Capture 与串行 bit", "",
        "固定 bit 身份：b_n 在 [E_n+dmax_n, E_(n+1)+dmin_(n+1)] 内有效。",
        "生产零相位 STA 的 setup 使用 E_n，capture 使用 E_(n+1)，hold 使用 E_(n+1)。",
        "OOC 的 C_1 理想时刻=2.381 ns：setup 关联 E_1=1.786 ns，hold 关联 E_2=3.571 ns；",
        "该默认 STA 配对检查 b_1，零相位生产 C_1 原本检查 b_0。",
        "此为约束中的 bit 关联，不能证明补偿后物理 C_1 真正捕获 b_1；当前无共同窗口。",
        "不得通过改变 bit 身份、减整周期或添加 multicycle 来补齐这个证明。",
        "",
        f"[UG471]({UG471})：1:8 DDR 最早收到的 bit 在 Q8。规范源码 Q8->raw(7)，",
        "Q1->raw(0)，WordAlignment 后 DPHY_LaneSFEN.MakeLSF 反转为 PPI LSB-first。",
        "`dphy_capture_bit_map.csv` 给出 8 种 raw-word 起始偏移 x 8 个 payload bit 的映射；",
        "偏移 a 时 bit j 在相对 raw-word floor((a+j)/8) 的 Q[8-((a+j)%8)]，",
        "拼接后位于 aligned_raw(7-j)，MakeLSF 后为 PPI(j)。首个 payload bit 的绝对 R/F 相位仍未知。",
        "SoT 0xB8 的串行 LSB-first 序列为 0,0,0,1,1,1,0,1，raw 字为 0x1D，",
        "与 kSyncSeq=00011101 相符。alignment=0..7 的跨 raw-word 拼接及反转恢复已做主机代数核对。",
        f"核对 {checks} 个 payload/offset 组合，通过；不包括软匹配、LP、失锁、首帧或原语启动仿真。",
        "ISERDES NETWORKING 延迟、CLKDIV 启动相位及完整 valid 流水线仍须定向 RTL 仿真证明。", "",
        "## 跨角点窗口", "",
        "在 bit 配对不变的前提下，对 lane l、capture edge e、data transition v、corner c：",
        "A_late=E_n+dmax+Dmax；A_early_next=E_(n+1)+dmin+Dmin；",
        "C=K+φ+Cclock；要求 A_late+tSU+U <= C <= A_early_next-tH-U。",
        "相对于当前已报告 capture，设额外共同时间偏移 δ：setup slack S+δ，hold slack H-δ。",
        "因此下界 L=max(-S)，上界 R=min(H)，共同窗口 [L,R]，宽 R-L。",
        "这只是同一 bit 配对下的诊断边界，不是允许任意 δ 的 MMCM 编程区间；角点时钟延时必须保留。",
        "报告中的 skew/uncertainty/原语 aperture 已包含于 S/H，不重复相加；保留原语 timing arc 的符号。", "",
        "| Topology | lane | capture | setup limiting corner | hold limiting corner | L (ns) | R (ns) | R-L (ns) |",
        "|---|---:|---|---|---|---:|---:|---:|",
    ]
    groups = defaultdict(list)
    for row in rows:
        groups[row["topology"], row["lane"], row["capture_edge"]].append(row)
    for (topology, lane, edge), paths in sorted(groups.items()):
        setup = [r for r in paths if r["check"] == "Setup"]
        hold = [r for r in paths if r["check"] == "Hold"]
        if not setup or not hold:
            lines.append(f"| {topology} | {lane} | {edge} | partial | partial | UNKNOWN | UNKNOWN | UNKNOWN |")
            continue
        s = min(setup, key=lambda r: r["slack_ns"])
        h = min(hold, key=lambda r: r["slack_ns"])
        lower, upper = -s["slack_ns"], h["slack_ns"]
        lines.append(f"| {topology} | {lane} | {edge} | {s['corner']} | {h['corner']} | {lower:.3f} | {upper:.3f} | {upper-lower:.3f} |")
    lines.extend([
        "", "production 报告覆盖两 lane、两个 capture 边沿和两种数据跳变；输出详细字段见 `dphy_contract_paths.csv`。",
        "OOC timing summary 仅有 lane1/fall setup 与 lane0/fall hold 的详细路径，不能填造其它边沿/角点。",
        "OOC sweep CSV 仍给出聚合最差 setup/hold（不是每个 capture 边沿的完整详细路径）。", "",
        "| Sweep model | setting | lane | L (ns) | R (ns) | R-L (ns) |",
        "|---|---|---:|---:|---:|---:|",
    ])
    with (REPORTS / "dphy_clock_ooc_window.csv").open(encoding="utf-8", newline="") as stream:
        sweep = list(csv.DictReader(stream))
    for phase, taps in ((0, 0), (60, 12)):
        selected = [r for r in sweep if int(r["serial_phase_degrees"]) == phase and int(r["data_taps"]) == taps]
        if len(selected) != 1:
            raise ValueError("Missing or duplicate selected OOC setting")
        for lane in range(2):
            lower = -float(selected[0][f"lane{lane}_setup"])
            upper = float(selected[0][f"lane{lane}_hold"])
            lines.append(f"| OOC BUFG | phase={phase},tap={taps} | {lane} | {lower:.3f} | {upper:.3f} | {upper-lower:.3f} |")
    for topology in sorted({r['topology'] for r in rows}):
        selected = [r for r in rows if r['topology'] == topology]
        lower = max(-r['slack_ns'] for r in selected if r['check'] == 'Setup')
        upper = min(r['slack_ns'] for r in selected if r['check'] == 'Hold')
        lines.extend(["", f"{topology}：已有详细路径共同必要区间 [{lower:.3f}, {upper:.3f}] ns，宽 {upper-lower:.3f} ns。"])
    lines.extend([
        "", "## 逐角点证据与准入", "",
        "每个拓扑要求 64 个覆盖项：2 lane × 2 P/N 输入 × 2 Fast/Slow 角点 × 2 capture 边沿 × 2 数据跳变 × 2 setup/hold。",
        "rise_to/fall_to 选择 DDLY 数据跳变；capture 边沿另从实际 Requirement 解析，不能混用。",
        "只有限制角点的报告不能证明其它角点也有窗口；缺项保持 UNKNOWN，不准入。",
        "`dphy_contract_coverage.csv` 列出每个覆盖项；`dphy_contract_paths.csv` 保留引脚、位配对及各原语的有符号增量。",
        "`dphy_contract_corner_windows.csv` 同时输出每 lane/capture 边沿/角点、跨角点及全 lane 的诊断区间和限制路径预算。",
        "| Topology | covered/required | complete | zero-phase STA pairing | physical/startup | eligible |",
        "|---|---:|---|---|---|---|",
    ])
    for gate in gates:
        lines.append(f"| {gate['topology']} | {gate['covered']}/{gate['required']} | "
                     f"{gate['complete']} | {gate['sta_pairing_verified']} | UNVERIFIED | False |")
    lines.extend([
        "", "| Topology | lane | corner | capture | coverage | L ns | R ns | width ns | status |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ])
    for window in windows:
        def value(name):
            item = window[name]
            return f"{item:.6f}" if isinstance(item, (int, float)) else item
        lines.append(f"| {window['topology']} | {window['lane']} | {window['corner']} | {window['capture_edge']} | "
                     f"{window['coverage']} | {value('lower_ns')} | {value('upper_ns')} | "
                     f"{value('width_ns')} | {window['status']} |")
    lines.extend([
        "", "窗口分解：width = pin_eye + pairing_adjustment − relative_delay_loss − aperture_uncertainty。",
        "relative_delay_loss = (K_hold−K_setup) − (D_hold−D_setup)；CSV 的 loss_* 为各原语与残余项对此损失的贡献。",
        "clock_residual 包含布线、源延迟与 CPR，不能作为额外抖动再次计入。",
        "角点窗口是相对于已报告 capture 的同一 bit 诊断偏移，不是可编程相位或校准通过证明。",
        "完整查询还保留 DDR 约束产生的较宽松额外检查（setup=T、hold=−UI），标记 ADDITIONAL_STA。",
        "生产同一 bit 窗口仅使用 PRIMARY_ADJACENT（setup=UI、hold=0）；额外检查不替代主配对，也不取模重配。",
        "生产零相位 STA 配对检查通过仍不等于原语启动/首包 bit 身份已证明。",
    ])
    lines.extend([
        "", "结论：所列窗口均为空；已有 sweep 的所有设置也均失败。物理外部预算仍未闭合。",
        "生产 MMCM 仍关闭；不修改输入约束、不增加时序例外、不发布 BIT/XSA，迁移继续暂停。",
        "下一步需要供应商的 lane/edge 保证或另行授权的物理测量，再设计能满足上述交集的采样拓扑。",
        "OOC 仍缺完整角点明细；启动/首字节定向仿真仍未执行。完成查询/解析不等于生产基线通过。",
    ])
    (REPORTS / "dphy_contract_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"DPHY_CONTRACT_AUDIT: paths={len(rows)}, alignment_cases={checks}, physical_budget=UNVERIFIED")
    for gate in gates:
        print(f"DPHY_EVIDENCE_GATE: {gate['topology']} coverage={gate['covered']}/{gate['required']} "
              f"pairing={gate['sta_pairing_verified']} timing={gate['fixed_setting_timing_pass']} eligible=False")
    if args.require_eligible:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
