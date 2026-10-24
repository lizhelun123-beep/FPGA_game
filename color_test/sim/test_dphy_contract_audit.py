"""Offline parser/gate regression; no Vivado, RTL simulation or board access."""
import importlib.util
from itertools import product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "dphy_contract", Path(__file__).resolve().parents[1] / "tools/audit_dphy_contract.py"
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
TOPOLOGY = "production_BUFIO_c0_d12"

# Reduced real lane0/Fast/fall setup report. Preserve signed primitive arcs.
PATH = """Slack (VIOLATED) : -0.234ns
  Source: dphy_data_hs_n[0]
    (input port clocked by mipi_hs_clk {rise@0.000ns fall@1.786ns period=3.571ns})
  Destination: system_i/U0/DataLaneGen[0].DPHY_LaneSFEN_X/HSDeserializerX/Deserializer/DDLY
  Path Type: Setup (Max at Fast Process Corner)
  Requirement: 1.786ns (mipi_hs_clk fall@1.786ns - mipi_hs_clk rise@0.000ns)
  Data Path Delay: 1.820ns
  Input Delay: 1.518ns
  Clock Path Skew: 1.409ns
  Clock Uncertainty: 0.035ns
    (clock mipi_hs_clk rise edge)
    W11 IBUFDS (Prop_ibufds_IB_O) 0.464 1.982 r data/O
    IDELAY_X0Y14 IDELAYE2 (Prop_idelaye2_IDATAIN_DATAOUT)
      1.356 3.338 r data/InputDelay/DATAOUT
    ILOGIC_X0Y14 ISERDESE2 r system_i/U0/DataLaneGen[0].DPHY_LaneSFEN_X/HSDeserializerX/Deserializer/DDLY
    (clock mipi_hs_clk fall edge)
    Y7 IBUFDS (Prop_ibufds_I_O) 0.409 2.195 f clock/O
    IDELAY_X0Y24 IDELAYE2 (Prop_idelaye2_IDATAIN_DATAOUT)
      0.244 2.439 f clock/InputDelay/DATAOUT
    BUFIO_X0Y1 BUFIO (Prop_bufio_I_O) 0.483 3.101 f clock/BUFIO/O
    ILOGIC_X0Y14 ISERDESE2 (Setup_iserdese2_CLKB_DDLY)
      -0.056 3.104 data/Deserializer
"""


def complete_rows():
    """A known consistent positive eye; physical/startup evidence stays absent."""
    rows = []
    base = AUDIT.paths_from_text(PATH, TOPOLOGY, "fixture")[0]
    for lane, polarity, corner, edge, transition, check in product(
        range(2), ("p", "n"), ("Fast", "Slow"), ("rise", "fall"),
        ("rise", "fall"), ("Setup", "Hold")
    ):
        row = dict(base, lane=lane, polarity=polarity, corner=corner,
                   capture_edge=edge, data_transition=transition, check=check,
                   source=f"dphy_data_hs_{polarity}[{lane}]",
                   internal_data_ns=0.9, clock_skew_ns=0.9,
                   data_ibufds_ns=0.45, data_idelaye2_ns=0.45,
                   clock_ibufds_ns=0.4, clock_idelaye2_ns=0.2,
                   clock_bufio_ns=0.3, clock_residual_ns=0.0)
        if check == "Setup":
            row.update(requirement_ns=AUDIT.UI, input_delay_ns=AUDIT.DMAX,
                       aperture_ns=0.056, launch_edge="fall" if edge == "rise" else "rise",
                       launch_ns=AUDIT.UI if edge == "rise" else 0.0,
                       capture_ns=AUDIT.PERIOD if edge == "rise" else AUDIT.UI,
                       slack_ns=AUDIT.UI-AUDIT.DMAX-0.035-0.056)
        else:
            row.update(requirement_ns=0.0, input_delay_ns=AUDIT.DMIN,
                       aperture_ns=0.132, launch_edge=edge,
                       launch_ns=0.0 if edge == "rise" else AUDIT.UI,
                       capture_ns=0.0 if edge == "rise" else AUDIT.UI,
                       slack_ns=AUDIT.DMIN-0.035-0.132)
        rows.append(row)
    return rows


class ContractAuditTests(unittest.TestCase):
    def test_report_components_and_data_transition(self):
        row = AUDIT.paths_from_text(PATH, TOPOLOGY, "fixture")[0]
        self.assertEqual(row["capture_edge"], "fall")
        self.assertEqual(row["data_transition"], "rise")
        self.assertEqual(row["data_idelaye2_ns"], 1.356)
        self.assertAlmostEqual(row["clock_residual_ns"], 0.273)
        falling = PATH.replace("ISERDESE2 r system_i", "ISERDESE2 f system_i")
        self.assertEqual(AUDIT.paths_from_text(falling, TOPOLOGY, "fixture")[0]["data_transition"], "fall")

    def test_signed_setup_arc(self):
        report = PATH.replace("-0.056 3.104", "0.016 3.176").replace("-0.234ns", "-0.162ns")
        row = AUDIT.paths_from_text(report, TOPOLOGY, "fixture")[0]
        self.assertEqual(row["aperture_ns"], -0.016)

    def test_changed_contract_or_missing_primitive_rejected(self):
        for report in (PATH.replace("1.518ns", "1.500ns"),
                       PATH.replace("IBUFDS (Prop_ibufds_IB_O)", "UNKNOWN (Prop_unknown)")):
            with self.subTest(report=report[:50]), self.assertRaises(ValueError):
                AUDIT.paths_from_text(report, TOPOLOGY, "fixture")

    def test_positive_model_never_implies_physical_or_startup_acceptance(self):
        coverage, windows, gates = AUDIT.evidence_summary(complete_rows())
        self.assertEqual(len(coverage), 64)
        self.assertTrue(gates[0]["complete"])
        self.assertTrue(gates[0]["sta_pairing_verified"])
        self.assertTrue(gates[0]["fixed_setting_timing_pass"])
        self.assertFalse(gates[0]["candidate_eligible"])
        self.assertFalse(gates[0]["physical_budget_verified"])
        self.assertTrue(all(row["status"] == "DIAGNOSTIC_SHIFT_EXISTS" for row in windows))

    def test_missing_any_dimension_blocks_completeness(self):
        for field, value in (("lane", 1), ("polarity", "n"), ("corner", "Slow"),
                             ("capture_edge", "fall"), ("data_transition", "fall"), ("check", "Hold")):
            rows = [row for row in complete_rows() if row[field] != value]
            with self.subTest(field=field):
                _, _, gates = AUDIT.evidence_summary(rows)
                self.assertFalse(gates[0]["complete"])
                self.assertFalse(gates[0]["candidate_eligible"])

    def test_within_corner_window_does_not_imply_cross_corner_window(self):
        rows = complete_rows()
        for row in rows:
            if row["corner"] == "Slow":
                row["clock_skew_ns"] += 0.4
                row["clock_residual_ns"] += 0.4
                row["slack_ns"] += 0.4 if row["check"] == "Setup" else -0.4
        _, windows, _ = AUDIT.evidence_summary(rows)
        self.assertTrue(all(row["width_ns"] > 0 for row in windows if row["corner"] != "ALL"))
        self.assertTrue(all(row["status"] == "EMPTY" for row in windows if row["corner"] == "ALL"))

    def test_wrong_bit_pairing_cannot_be_fixed_by_modulo_period(self):
        rows = complete_rows()
        rows[0]["capture_ns"] += AUDIT.PERIOD
        _, _, gates = AUDIT.evidence_summary(rows)
        self.assertFalse(gates[0]["sta_pairing_verified"])

    def test_additional_ddr_checks_do_not_replace_or_obscure_primary_pairing(self):
        rows = complete_rows()
        additional = []
        for row in rows:
            extra = dict(row, slack_ns=row["slack_ns"] + AUDIT.UI)
            if row["check"] == "Setup":
                launch = 0.0 if row["capture_edge"] == "rise" else AUDIT.UI
                extra.update(launch_edge=row["capture_edge"], launch_ns=launch,
                             capture_ns=launch+AUDIT.PERIOD, requirement_ns=AUDIT.PERIOD)
            else:
                capture = 0.0 if row["capture_edge"] == "rise" else AUDIT.UI
                extra.update(launch_edge="fall" if row["capture_edge"] == "rise" else "rise",
                             capture_ns=capture, launch_ns=capture+AUDIT.UI, requirement_ns=-AUDIT.UI)
            additional.append(extra)
        coverage, windows, gates = AUDIT.evidence_summary(rows + additional)
        self.assertTrue(gates[0]["sta_pairing_verified"])
        self.assertTrue(all(row["primary_paths"] == row["additional_sta_paths"] == 1 for row in coverage))
        self.assertTrue(all(row["width_ns"] > 0 for row in windows))
        _, windows, gates = AUDIT.evidence_summary(additional)
        self.assertFalse(gates[0]["sta_pairing_verified"])
        self.assertTrue(all(row["status"] == "UNKNOWN" for row in windows))

    def test_interrupted_query_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "corners.rpt"
            report.write_text("# DPHY_CORNER_QUERY_V1\n" + PATH, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                AUDIT.read_corner_report(report)

    def test_completed_local_corner_evidence(self):
        report = AUDIT.REPORTS / "dphy_sampling_corners.rpt"
        if not report.exists():
            self.skipTest("local generated corner report is optional; no Vivado is launched")
        rows = AUDIT.read_corner_report(report)
        coverage, windows, gates = AUDIT.evidence_summary(rows)
        self.assertEqual(len(rows), 128)
        self.assertEqual(sum(row["primary_paths"] for row in coverage), 64)
        self.assertEqual(sum(row["additional_sta_paths"] for row in coverage), 64)
        self.assertTrue(gates[0]["complete"])
        self.assertTrue(gates[0]["sta_pairing_verified"])
        self.assertFalse(gates[0]["candidate_eligible"])
        expected = {(0, "Fast"): -0.222, (1, "Fast"): -0.222,
                    (0, "Slow"): -0.365, (1, "Slow"): -0.365,
                    ("ALL", "ALL"): -1.358}
        for row in windows:
            if row["capture_edge"] == "ALL" and (row["lane"], row["corner"]) in expected:
                self.assertAlmostEqual(row["width_ns"], expected[row["lane"], row["corner"]])
            self.assertAlmostEqual(sum(value for name, value in row.items() if name.startswith("loss_")),
                                   row["relative_delay_loss_ns"], places=3)


class DirectInputReportTests(unittest.TestCase):
    def sampling_report(self):
        report = AUDIT.REPORTS / "dphy_sampling_ooc/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("historical local D-direct report is optional")
        return report

    def test_historical_structure_budget_keeps_cross_corner_and_primitive_loss(self):
        budget = AUDIT.sampling_structure_budget(self.sampling_report())
        self.assertEqual(budget["primary_paths"], 64)
        self.assertFalse(budget["new_structure_timing_measured"])
        self.assertFalse(budget["current_rtl_acceptance"])
        slow, joint = budget["windows"][1:]
        self.assertAlmostEqual(slow["width_ns"], -.407)
        self.assertAlmostEqual(joint["width_ns"], -.932)
        self.assertAlmostEqual(slow["clock_difference_ns"], .501)
        self.assertAlmostEqual(slow["loss_clock_residual_ns"], .404)
        self.assertAlmostEqual(slow["clock_primitive_difference_ns"], .097)
        self.assertAlmostEqual(slow["allowed_clock_difference_if_other_old_terms_frozen_ns"], .0935)
        self.assertAlmostEqual(slow["frozen_old_arcs_zero_clock_residual_width_ns"], -.0035)

    def test_budget_rejects_missing_primary_even_with_extra_sta_paths(self):
        report = self.sampling_report()
        rows = AUDIT.paths_from_report(report, "candidate_BUFH_DDIRECT_M3")
        with patch.object(AUDIT, "paths_from_report", return_value=rows[1:]):
            with self.assertRaisesRegex(ValueError, "64 unique"):
                AUDIT.sampling_structure_budget(report)

    def test_budget_rejects_duplicate_primary(self):
        report = self.sampling_report()
        rows = AUDIT.paths_from_report(report, "candidate_BUFH_DDIRECT_M3")
        with patch.object(AUDIT, "paths_from_report", return_value=rows+[rows[0]]):
            with self.assertRaisesRegex(ValueError, "64 unique"):
                AUDIT.sampling_structure_budget(report)

    def test_budget_rejects_whole_period_bit_reassignment(self):
        report = self.sampling_report()
        rows = AUDIT.paths_from_report(report, "candidate_BUFH_DDIRECT_M3")
        rows[0]["capture_ns"] += AUDIT.PERIOD
        with patch.object(AUDIT, "paths_from_report", return_value=rows):
            with self.assertRaisesRegex(ValueError, "bit identity"):
                AUDIT.sampling_structure_budget(report)

    def test_d_port_without_idelay_and_signed_aperture(self):
        direct = PATH[:PATH.index("    IDELAY_X0Y14 IDELAYE2")] + PATH[PATH.index("    ILOGIC_X0Y14 ISERDESE2 r"):]
        direct = direct.replace("/DDLY", "/D").replace("_DDLY)", "_D)")
        direct = direct.replace("-0.234ns", "1.122ns").replace("1.820ns", "0.464ns")
        row = AUDIT.paths_from_text(direct, "candidate_BUFH_DDIRECT_M3", "fixture_D")[0]
        self.assertEqual(row["data_idelaye2_ns"], 0)
        self.assertAlmostEqual(row["data_ibufds_ns"], .464)
        self.assertAlmostEqual(row["slack_ns"], 1.122)
        self.assertAlmostEqual(row["aperture_ns"], .056)


class VendorReferenceBudgetTests(unittest.TestCase):
    def vendor_report(self):
        report = AUDIT.ROOT.parent / "build/dphy_sampling/vendor_reference/unplaced_sampling_corners.rpt"
        if not report.exists():
            self.skipTest("locally generated vendor reference is optional; never launch Vivado")
        return report

    def test_native_vendor_names_preserve_lane_and_edges(self):
        native = PATH.replace("dphy_data_hs_n[0]", "data_hs_rxn[0]").replace(
            "system_i/U0/DataLaneGen[0].DPHY_LaneSFEN_X/HSDeserializerX/Deserializer",
            "inst/slave_rx.rx_ioi/dl0_iserdese2_master")
        row = AUDIT.paths_from_text(native, "vendor_unplaced_ALINX2023_1", "fixture_vendor")[0]
        self.assertEqual(row["source"], "data_hs_rxn[0]")
        self.assertEqual((row["lane"], row["polarity"], row["capture_edge"]), (0, "n", "fall"))
        self.assertAlmostEqual(row["slack_ns"], -.234)
        mismatched = native.replace("data_hs_rxn[0]", "data_hs_rxn[1]")
        with self.assertRaisesRegex(ValueError, "source/lane mismatch"):
            AUDIT.paths_from_text(mismatched, "vendor_unplaced_ALINX2023_1", "fixture_vendor")

    def test_generated_vendor_budget_does_not_promote_unplaced_estimates(self):
        budget = AUDIT.vendor_sampling_budget(self.vendor_report())
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertFalse(budget["routed_timing_measured"])
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual([w["width_ns"] for w in budget["windows"]], [.093, -.055, -.704])
        self.assertEqual([w["width_ns"] for w in budget["frozen_primitive_zero_network_windows"]],
                         [.111, -.017, -.371])

    def test_vendor_budget_rejects_missing_or_duplicate_primary(self):
        report = self.vendor_report()
        rows = AUDIT.paths_from_report(report, "vendor_unplaced_ALINX2023_1")
        for changed in (rows[1:], rows+[rows[0]]):
            with self.subTest(count=len(changed)), patch.object(AUDIT, "paths_from_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "64 unique"):
                    AUDIT.vendor_sampling_budget(report)

    def test_vendor_budget_rejects_period_reassignment(self):
        report = self.vendor_report()
        rows = AUDIT.paths_from_report(report, "vendor_unplaced_ALINX2023_1")
        rows[0]["capture_ns"] += AUDIT.PERIOD
        with patch.object(AUDIT, "paths_from_text", return_value=rows):
            with self.assertRaisesRegex(ValueError, "bit identity"):
                AUDIT.vendor_sampling_budget(report)

    def test_vendor_budget_rejects_routed_or_unidentified_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "reference.rpt"
            for content in (PATH, "# Vendor fixed calibration, actual tap=5;\n"
                            "Design State : Routed\nnet (fo=2, routed)\n"+PATH):
                report.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unplaced"):
                    AUDIT.vendor_sampling_budget(report)


class HPCInternalBudgetTests(unittest.TestCase):
    def probe_report(self):
        report = AUDIT.ROOT / "build/dphy_sampling/hpc_internal_probe/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("fixed local HPC probe is optional; never launch Vivado")
        return report

    def test_new_routed_budget_keeps_own_arcs_and_absolute_edges(self):
        budget = AUDIT.hpc_internal_budget(self.probe_report())
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertTrue(budget["routed_timing_measured"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertFalse(budget["budget_positive"])
        self.assertEqual([w["width_ns"] for w in budget["windows"]], [0.0, -.275, -2.175])
        # Sub-ps component reconstruction is not positive budget evidence;
        # the reported Fast interval is exactly zero at its printed precision.
        self.assertAlmostEqual(budget["windows"][0]["literal_input_model_width_ns"], .0005)
        self.assertEqual(budget["windows"][0]["width_ns"], 0)
        slow, joint = budget["windows"][1:]
        self.assertAlmostEqual(slow["clock_difference_ns"], .369)
        self.assertAlmostEqual(joint["clock_difference_ns"], 2.725)
        self.assertAlmostEqual(joint["signed_aperture_sum_ns"], .117)
        self.assertAlmostEqual(joint["uncertainty_sum_ns"], .284)
        self.assertAlmostEqual(joint["loss_clock_mmcme2_adv_ns"], .027)
        for w in budget["windows"]:
            for path in (w["limiting_setup"], w["limiting_hold"]):
                self.assertEqual(len(path["clock_routed_segments"]), 3)
                self.assertLessEqual(abs(path["clock_routed_print_residual_ns"]), .002)

    def test_probe_rejects_missing_or_duplicate_primary(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_HPC_INTERNAL_M3")
        for changed in (rows[1:], rows+[rows[0]]):
            with self.subTest(count=len(changed)), patch.object(AUDIT, "paths_from_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "64 unique"):
                    AUDIT.hpc_internal_budget(report)

    def test_probe_rejects_whole_period_reassignment(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_HPC_INTERNAL_M3")
        rows[0]["capture_ns"] += AUDIT.PERIOD
        with patch.object(AUDIT, "paths_from_text", return_value=rows):
            with self.assertRaisesRegex(ValueError, "bit identity"):
                AUDIT.hpc_internal_budget(report)

    def test_probe_rejects_unplaced_or_incomplete_evidence(self):
        content = self.probe_report().read_text(encoding="utf-8")
        for changed in (content.replace("Design State : Routed", "Design State : Synthesized"),
                        content.replace("# HPC_INTERNAL_PROBE_COMPLETE requests=32", "")):
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "probe.rpt"
                report.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "complete routed"):
                    AUDIT.hpc_internal_budget(report)


class BUFGFeedbackBudgetTests(unittest.TestCase):
    def probe_report(self):
        report = AUDIT.ROOT / "build/dphy_sampling/bufg_feedback_probe/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("fixed local BUFG probe is optional; never launch Vivado")
        return report

    def test_own_routed_data_and_signed_compensation(self):
        budget = AUDIT.bufg_feedback_budget(self.probe_report())
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual([w["width_ns"] for w in budget["windows"]], [.550, -.407, -.932])
        self.assertTrue(budget["routed_timing_measured"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertFalse(budget["budget_positive"])
        self.assertEqual(budget["windows"][2]["data_difference_ns"], .517)
        for row in budget["paths"]:
            self.assertEqual(row["endpoint_port"], "D")
            self.assertEqual(row["data_idelaye2_ns"], 0)
            self.assertLess(row["clock_mmcme2_adv_ns"], 0)
            self.assertGreater(row["clock_bufg_ns"], 0)
            self.assertEqual(len(row["clock_routed_segments"]), 3)
            self.assertLessEqual(abs(row["clock_routed_print_residual_ns"]), .002)

    def test_rejects_missing_or_duplicate_adjacent_paths(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_BUFG_FEEDBACK_M3")
        for changed in (rows[1:], rows+[rows[0]]):
            with patch.object(AUDIT, "paths_from_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "64 unique adjacent"):
                    AUDIT.bufg_feedback_budget(report)

    def test_rejects_missing_additional_and_reassigned_bits(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_BUFG_FEEDBACK_M3")
        extra = next(r for r in rows if not AUDIT.production_pairing_ok(r))
        with patch.object(AUDIT, "paths_from_text", return_value=[r for r in rows if r is not extra]):
            with self.assertRaisesRegex(ValueError, "64 unique additional"):
                AUDIT.bufg_feedback_budget(report)
        for selected in (rows[0], extra):
            selected["capture_ns"] += AUDIT.PERIOD
            with patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaisesRegex(ValueError, "bit identity"):
                    AUDIT.bufg_feedback_budget(report)
            selected["capture_ns"] -= AUDIT.PERIOD

    def test_rejects_ddly_and_wrong_buffer(self):
        report = self.probe_report()
        for field, value, message in (("endpoint_port", "DDLY", "actual D"),
                                      ("clock_bufg_ns", 0, "structure mismatch")):
            rows = AUDIT.paths_from_report(report, "probe_BUFG_FEEDBACK_M3")
            rows[0][field] = value
            with patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaisesRegex(ValueError, message):
                    AUDIT.bufg_feedback_budget(report)

    def test_rejects_incomplete_unrouted_and_other_topology(self):
        content = self.probe_report().read_text(encoding="utf-8")
        for changed in (content.replace("Design State : Routed", "Design State : Synthesized"),
                        content.replace("# BUFG_FEEDBACK_PROBE_COMPLETE requests=32", ""),
                        content.replace("# BUFG_FEEDBACK_PROBE_V1", "# HPC_INTERNAL_PROBE_V1")):
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "probe.rpt"
                report.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "complete routed"):
                    AUDIT.bufg_feedback_budget(report)


class SharedFeedbackModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic PARSER fixture only. Historical timing values are never
        # exported as new structure evidence, and do not imply model success.
        cls.directory = tempfile.TemporaryDirectory()
        original = AUDIT.ROOT / "build/dphy_sampling/bufg_feedback_probe/sampling_corners.rpt"
        if not original.exists():
            cls.directory.cleanup()
            raise unittest.SkipTest("historical parser sample absent; never launch Vivado")
        content = original.read_text(encoding="utf-8")
        content = content.replace("# BUFG_FEEDBACK_PROBE_V1 fixed 0/0;", "# SHARED_FB_MODEL_V1 fixed 0/0;")
        content = content.replace("# BUFG_FEEDBACK_PROBE_COMPLETE requests=32", "# SHARED_FB_MODEL_COMPLETE requests=32")
        content = content.replace("Design State : Routed", "Design State : Synthesized")
        content = content.replace(", routed)", ", estimated)")
        content = content.replace("Prop_mmcme2_adv_CLKIN1_CLKOUT0", "Prop_mmcme2_adv_CLKIN1_CLKFBOUT")
        cls.fixture = Path(cls.directory.name) / "synthetic_parser_fixture.rpt"
        cls.fixture.write_text(content, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def model_report(self):
        return self.fixture

    def test_model_has_complete_coverage_but_never_routed_acceptance(self):
        budget = AUDIT.shared_feedback_model_budget(self.model_report())
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual(budget["feedback_family_attempt"], 2)
        self.assertFalse(budget["routed_timing_measured"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertFalse(budget["implementation_authorized_by_budget"])
        for w in budget["windows"]:
            expected = .5355-w["data_difference_ns"]-w["clock_difference_ns"]-w["uncertainty_sum_ns"]-w["signed_aperture_sum_ns"]
            self.assertAlmostEqual(w["literal_input_model_width_ns"], expected)

    def test_missing_additional_or_duplicate_primary_is_rejected(self):
        report = self.model_report()
        rows = AUDIT.paths_from_report(report, "probe_SHARED_FB_MODEL_M3")
        for changed in (rows[1:], rows+[rows[0]]):
            with patch.object(AUDIT, "paths_from_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "64 unique"):
                    AUDIT.shared_feedback_model_budget(report)

    def test_same_requirement_cannot_hide_whole_period_reassignment(self):
        report = self.model_report()
        rows = AUDIT.paths_from_report(report, "probe_SHARED_FB_MODEL_M3")
        rows[0]["capture_ns"] += AUDIT.PERIOD
        with patch.object(AUDIT, "paths_from_text", return_value=rows):
            with self.assertRaisesRegex(ValueError, "bit identity"):
                AUDIT.shared_feedback_model_budget(report)

    def test_routed_or_partial_report_is_rejected(self):
        content = self.model_report().read_text(encoding="utf-8")
        for changed in (content.replace("Design State : Synthesized", "Design State : Routed"),
                        content.replace("# SHARED_FB_MODEL_COMPLETE requests=32", "")):
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "model.rpt"
                report.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "complete unplaced"):
                    AUDIT.shared_feedback_model_budget(report)

    def test_clkout0_arc_cannot_substitute_for_feedback_output(self):
        content = self.model_report().read_text(encoding="utf-8").replace(
            "Prop_mmcme2_adv_CLKIN1_CLKFBOUT", "Prop_mmcme2_adv_CLKIN1_CLKOUT0")
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "wrong_arc.rpt"
            report.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "actual CLKIN1-to-CLKFBOUT"):
                AUDIT.shared_feedback_model_budget(report)

    def test_actual_optimized_report_keeps_new_model_numbers_and_networks(self):
        report = AUDIT.ROOT / "build/dphy_sampling/shared_feedback_model/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("actual same-DCP model query optional; never run Vivado")
        budget = AUDIT.shared_feedback_model_budget(report)
        self.assertEqual(budget["design_state"], "Optimized")
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual([w["width_ns"] for w in budget["windows"]], [.591, -.279, -1.136])
        self.assertEqual([w["literal_input_model_width_ns"] for w in budget["windows"]],
                         [.5915, -.2795, -1.1365])
        self.assertEqual([w["uncertainty_sum_ns"] for w in budget["windows"]], [.272]*3)
        self.assertFalse(budget["budget_positive"])
        self.assertFalse(budget["routed_timing_measured"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertEqual(budget["phase_grid_status"], "NOT_EVALUATED_EMPTY_WINDOW")
        for row in budget["paths"]:
            self.assertEqual(len(row["clock_model_segments"]), 3)
            self.assertLessEqual(abs(row["clock_model_print_residual_ns"]), .002)
        zero = budget["frozen_own_primitive_zero_network_windows"]
        self.assertAlmostEqual(zero[1]["literal_input_model_width_ns"], -.0695)
        self.assertAlmostEqual(zero[2]["literal_input_model_width_ns"], -1.8685)

    def test_mixed_design_states_cannot_masquerade_as_single_model(self):
        content = self.model_report().read_text(encoding="utf-8")
        content = content.replace("Design State : Synthesized", "Design State : Optimized", 1)
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "mixed_states.rpt"
            report.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete unplaced"):
                AUDIT.shared_feedback_model_budget(report)


class LocalClockBudgetTests(unittest.TestCase):
    def probe_report(self):
        report = AUDIT.ROOT / "build/dphy_sampling/local_clock_probe/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("fixed local clock probe optional; never launch Vivado")
        return report

    def test_own_positive_corners_do_not_pass_common_or_reachable_phase(self):
        budget = AUDIT.local_clock_budget(self.probe_report())
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual([w["width_ns"] for w in budget["windows"]], [.128, .068, -1.409])
        self.assertEqual([w["literal_input_model_width_ns"] for w in budget["windows"]],
                         [.1275, .0675, -1.4095])
        self.assertTrue(budget["per_corner_windows_positive"])
        self.assertFalse(budget["budget_positive"])
        self.assertFalse(budget["fixed_seed_sta_pass"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertEqual(budget["calibration_acceptance"], "NOT_ADOPTED")
        for row in budget["coverage"]:
            self.assertEqual((row["primary_paths"], row["additional_sta_paths"], row["pairing"]), (1, 1, "OK"))
        for row in budget["paths"]:
            self.assertEqual(row["endpoint_port"], "D")
            self.assertEqual(row["clock_mmcme2_adv_ns"], 0)
            self.assertEqual(row["data_idelaye2_ns"], 0)
            self.assertGreater(row["clock_idelaye2_ns"], 0)
            self.assertEqual(row["uncertainty_ns"], .035)
        for result in budget["nominal_grid_diagnostic"][:2]:
            self.assertEqual(result["status"], "NO_REACHABLE_NONNEGATIVE_NOMINAL_TAP")
            self.assertLess(result["conservative_upper_ns"], 0)

    def test_missing_any_dimension_rejected(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_LOCAL_CLOCK_tap0")
        for field, value in (("lane", 1), ("polarity", "n"), ("corner", "Slow"),
                             ("capture_edge", "fall"), ("data_transition", "fall"), ("check", "Hold")):
            with self.subTest(field=field), patch.object(AUDIT, "paths_from_text", return_value=[
                    r for r in rows if r[field] != value]):
                with self.assertRaisesRegex(ValueError, "64 unique"):
                    AUDIT.local_clock_budget(report)

    def test_primary_and_additional_bit_identity_not_folded(self):
        report = self.probe_report()
        for association in ("PRIMARY_ADJACENT", "ADDITIONAL_STA"):
            rows = AUDIT.paths_from_report(report, "probe_LOCAL_CLOCK_tap0")
            row = next(r for r in rows if AUDIT.production_pairing(r) == association)
            row["capture_ns"] += AUDIT.PERIOD
            with patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaisesRegex(ValueError, "bit identity"):
                    AUDIT.local_clock_budget(report)

    def test_ddly_missing_clock_delay_and_mmcm_cannot_masquerade_as_local(self):
        report = self.probe_report()
        for field, value, message in (("endpoint_port", "DDLY", "actual D"),
                                      ("clock_idelaye2_ns", 0, "structure mismatch"),
                                      ("data_idelaye2_ns", .5, "structure mismatch"),
                                      ("clock_mmcme2_adv_ns", -.5, "structure mismatch")):
            rows = AUDIT.paths_from_report(report, "probe_LOCAL_CLOCK_tap0")
            rows[0][field] = value
            with self.subTest(field=field), patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaisesRegex(ValueError, message):
                    AUDIT.local_clock_budget(report)

    def test_incomplete_unplaced_or_other_tap_report_rejected(self):
        content = self.probe_report().read_text(encoding="utf-8")
        for changed in (content.replace("Design State : Routed", "Design State : Optimized"),
                        content.replace("# LOCAL_CLOCK_PROBE_COMPLETE requests=32", ""),
                        content.replace("fixed clock_tap=0;", "fixed clock_tap=1;")):
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "probe.rpt"
                report.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "complete routed"):
                    AUDIT.local_clock_budget(report)

    def test_unaccounted_clock_increment_cannot_be_ignored(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_LOCAL_CLOCK_tap0")
        rows[0]["clock_residual_ns"] += .01
        with patch.object(AUDIT, "paths_from_text", return_value=rows):
            with self.assertRaisesRegex(ValueError, "reconstruction mismatch"):
                AUDIT.local_clock_budget(report)


class PLLClockBudgetTests(unittest.TestCase):
    def probe_report(self):
        report = AUDIT.ROOT / "build/dphy_sampling/pll_clock_probe/sampling_corners.rpt"
        if not report.exists():
            self.skipTest("fixed PLL probe optional; never launch Vivado")
        return report

    def test_own_paths_phase_and_negative_common_window(self):
        budget = AUDIT.pll_clock_budget(self.probe_report())
        self.assertEqual((budget["primary_paths"], budget["additional_sta_paths"]), (64, 64))
        self.assertEqual([w["literal_input_model_width_ns"] for w in budget["windows"]],
                         [.0935, .4715, -1.8835])
        self.assertFalse(budget["budget_positive"])
        self.assertFalse(budget["fixed_seed_sta_pass"])
        self.assertFalse(budget["current_rtl_acceptance"])
        self.assertEqual(budget["residual_drift_error"], "UNKNOWN")
        for row in budget["coverage"]:
            self.assertEqual((row["primary_paths"], row["additional_sta_paths"], row["pairing"]), (1, 1, "OK"))
        for row in budget["paths"]:
            self.assertEqual(row["clock_mmcme2_adv_ns"], 0)
            self.assertNotEqual(row["clock_plle2_adv_ns"], 0)
            self.assertEqual(row["configured_capture_phase_ns"], -.89275)
            self.assertEqual(row["uncertainty_ns"], .136)
        self.assertEqual(budget["nominal_grid_diagnostic"][-1]["status"],
                         "NO_FIXED_PHASE_CAN_OPEN_EMPTY_WINDOW")

    def test_missing_any_dimension_rejected(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_PLL_CLOCK_M4")
        for field, value in (("lane", 1), ("polarity", "n"), ("corner", "Slow"),
                             ("capture_edge", "fall"), ("data_transition", "fall"), ("check", "Hold")):
            with self.subTest(field=field), patch.object(AUDIT, "paths_from_text", return_value=[
                    r for r in rows if r[field] != value]), self.assertRaisesRegex(ValueError, "64 unique"):
                AUDIT.pll_clock_budget(report)

    def test_whole_period_cannot_be_hidden_by_fixed_phase(self):
        report = self.probe_report()
        for association in ("PRIMARY_ADJACENT", "ADDITIONAL_STA"):
            rows = AUDIT.paths_from_report(report, "probe_PLL_CLOCK_M4")
            for row in rows:
                row["configured_capture_phase_ns"] = -.89275
            row = next(r for r in rows if AUDIT.production_pairing(r) == association)
            row["capture_ns"] += AUDIT.PERIOD
            with patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaisesRegex(ValueError, "bit identity"):
                    AUDIT.pll_clock_budget(report)

    def test_missing_or_duplicated_extra_checks_rejected(self):
        report = self.probe_report()
        rows = AUDIT.paths_from_report(report, "probe_PLL_CLOCK_M4")
        extra = [r for r in rows if r["check"] == "Setup" and r["requirement_ns"] > 2]
        for changed in ([r for r in rows if r is not extra[0]], rows + [extra[0]]):
            with patch.object(AUDIT, "paths_from_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "64 unique additional"):
                    AUDIT.pll_clock_budget(report)

    def test_wrong_clock_primitive_or_data_endpoint_rejected(self):
        report = self.probe_report()
        for field, value in (("clock_plle2_adv_ns", 0), ("clock_mmcme2_adv_ns", -.5),
                             ("clock_bufg_ns", 0), ("data_idelaye2_ns", .5), ("endpoint_port", "DDLY")):
            rows = AUDIT.paths_from_report(report, "probe_PLL_CLOCK_M4")
            rows[0][field] = value
            with self.subTest(field=field), patch.object(AUDIT, "paths_from_text", return_value=rows):
                with self.assertRaises(ValueError):
                    AUDIT.pll_clock_budget(report)

    def test_wrong_phase_state_or_incomplete_report_rejected(self):
        content = self.probe_report().read_text(encoding="utf-8")
        for changed in (content.replace("serial_phase=-90", "serial_phase=270"),
                        content.replace("Design State : Routed", "Design State : Optimized"),
                        content.replace("# PLL_CLOCK_PROBE_COMPLETE requests=32", "")):
            with patch.object(Path, "read_text", return_value=changed):
                with self.assertRaisesRegex(ValueError, "Expected complete routed"):
                    AUDIT.pll_clock_budget(self.probe_report())

    def test_pll_compensation_cannot_be_silently_dropped_into_residual(self):
        content = self.probe_report().read_text(encoding="utf-8")
        changed = content.replace("PLLE2_ADV (Prop_plle2_adv_", "UNKNOWN_ADV (Prop_plle2_adv_")
        with patch.object(Path, "read_text", return_value=changed):
            with self.assertRaisesRegex(ValueError, "structure mismatch"):
                AUDIT.pll_clock_budget(self.probe_report())


if __name__ == "__main__":
    unittest.main()
