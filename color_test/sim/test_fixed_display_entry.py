"""Offline parser/Tcl contract tests; no Vivado or device calls."""
import importlib.util
from pathlib import Path
import tkinter
import unittest
import subprocess
import sys
import os
import copy
import tempfile
import zipfile
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fixed_display_audit', ROOT / 'color_test/tools/fixed_display_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def good_timing():
    checks = ('no_clock constant_clock pulse_width_clock unconstrained_internal_endpoints '
              'no_input_delay no_output_delay multiple_clock generated_clocks loops '
              'partial_input_delay partial_output_delay latch_loops').split()
    return ('Design Timing Summary\nWNS(ns) TNS(ns) other fields\n'
            '0.1 0 0 20 0.2 0 0 20 0.3 0 0 20\n' +
            '\n'.join(f'{i}. checking {name} (0)' for i, name in enumerate(checks, 1)))


class Contracts(unittest.TestCase):
    def rejects(self, function, *args):
        with self.assertRaises(ValueError):
            function(*args)

    def test_summary_and_explicit_default_group(self):
        self.assertEqual(audit.timing_metrics(good_timing())['THS'], 0)
        self.rejects(audit.timing_metrics, good_timing().replace('0.2 0 0 20', '-0.2 -0.2 1 20'))
        self.rejects(audit.timing_metrics, good_timing() + '\nPath Group: **default**\nSlack (VIOLATED) : -0.1ns')
        self.rejects(audit.timing_metrics, good_timing().replace('checking no_clock (0)', 'checking no_clock (1)'))
        self.rejects(audit.timing_metrics, good_timing().replace('checking loops (0)', 'checking unknown (0)'))
        self.rejects(audit.timing_metrics, '')

    def test_timing_separator_is_not_a_number_and_summary_is_unique(self):
        separator = ' '.join(['-------'] * 12) + '\n'
        text = good_timing().replace('0.1 0 0 20', separator + '0.1 0 0 20', 1)
        self.assertEqual(audit.timing_metrics(text)['WHS'], 0.2)
        self.rejects(audit.timing_metrics, text.replace('0.1 0 0 20 0.2 0 0 20 0.3 0 0 20', ''))
        self.rejects(audit.timing_metrics, text + '\n0.1 0 0 20 0.2 0 0 20 0.3 0 0 20')
        for bad in ('NaN', 'Inf', '--0.1', '0..1'):
            self.rejects(audit.timing_metrics, text.replace('0.1 0 0 20', bad + ' 0 0 20', 1))

    def test_real_frozen_reports_still_reject_negative_hold(self):
        for state in ('startup', 'runtime'):
            text = (audit.BASE / 'fixed_build_4/synth' / f'{state}_timing.rpt').read_text()
            with self.assertRaisesRegex(ValueError, 'Detailed/default-group timing violation'):
                audit.timing_metrics(text)

    def test_headerless_compile_provenance_requires_exact_frozen_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'synth').mkdir()
            frozen = out / 'synth/compile_order.rpt'
            frozen.write_text('Source compile order; no physical report banner\n')
            current = out / 'compile_order.rpt'
            current.write_bytes(frozen.read_bytes())
            audit.save(out / 'implementation_input.json', {})
            audit.save(out / 'synth_gate.json', {'report_sha256': {'compile_order.rpt': audit.sha(frozen)}})
            audit.report_identity(out, 'compile_order.rpt', current.read_text())
            current.write_text('changed source graph\n')
            self.rejects(audit.report_identity, out, 'compile_order.rpt', current.read_text())
            self.rejects(audit.report_identity, out, 'timing.rpt', 'missing version/top')

    def implementation_interpreter(self, fail_at=''):
        tcl = tkinter.Tcl()
        tcl.call('source', str(ROOT / 'color_test/tools/fixed_display.tcl'))
        tcl.setvar('fail_at', fail_at)
        tcl.eval('''
            set calls {}
            proc record {name} {
                lappend ::calls $name
                if {$::fail_at eq $name} {error "injected $name failure"}
            }
            proc version {args} {return 2023.1}
            proc exec {args} {record [lindex $args 3]}
            proc open_project {args} {record open_project}
            proc open_checkpoint {args} {record open_checkpoint; set ::opened [lindex $args 0]}
            proc opt_design {args} {record opt_design}
            proc place_design {args} {record place_design}
            proc route_design {args} {record route_design}
            proc close_project {args} {record close_project}
            proc close_design {args} {record close_design}
            proc fd::reports {args} {record reports}
            foreach command {launch_runs synth_design write_bitstream write_hw_platform} {
                proc $command {args} {error "forbidden operation"}
            }
        ''')
        return tcl

    def test_implementation_executes_frozen_route_only_even_when_gate_passes(self):
        tcl = self.implementation_interpreter()
        tcl.call('fixed_display_main', '-implement', '-out', str(audit.BASE / 'fixed_build_4'))
        self.assertEqual(tcl.splitlist(tcl.getvar('calls')), (
            'claim_implementation', 'open_project', 'open_checkpoint', 'opt_design',
            'place_design', 'route_design', 'reports', 'close_project', 'gate'))
        self.assertEqual(Path(tcl.getvar('opened')).resolve(),
                         (audit.BASE / 'fixed_build_4/synth/synthesized.dcp').resolve())

    def test_implementation_errors_never_fall_through_to_export_or_synthesis(self):
        sequence = ('claim_implementation', 'open_project', 'open_checkpoint', 'opt_design',
                    'place_design', 'route_design', 'reports', 'close_project', 'gate')
        for at in ('claim_implementation', 'opt_design', 'place_design', 'route_design', 'reports', 'gate'):
            tcl = self.implementation_interpreter(at)
            with self.assertRaises(tkinter.TclError):
                tcl.call('fixed_display_main', '-implement', '-out', str(audit.BASE / 'fixed_build_4'))
            self.assertEqual(tcl.splitlist(tcl.getvar('calls')), sequence[:sequence.index(at) + 1])

    def test_mixed_modes_rejected_before_any_operation(self):
        for modes in (('-implement', '-finalize'), ('-report-synth', '-implement'),
                      ('-prepare-only', '-implement'), ('-finalize', '-implement')):
            tcl = self.implementation_interpreter()
            with self.assertRaises(tkinter.TclError):
                tcl.call('fixed_display_main', *modes, '-out', str(audit.BASE / 'fixed_build_4'))
            self.assertEqual(tcl.splitlist(tcl.getvar('calls')), ())

    def test_readonly_report_mode_never_implements_or_writes_checkpoint(self):
        tcl = self.implementation_interpreter()
        tcl.eval('proc fd::reports {args} {record reports;set ::report_args $args}')
        tcl.call('fixed_display_main', '-report-implementation', '-out', str(audit.BASE / 'fixed_build_4'))
        self.assertEqual(tcl.splitlist(tcl.getvar('calls')), (
            'implementation_report_inputs', 'open_checkpoint', 'reports', 'close_design', 'gate'))
        report_args = tcl.splitlist(tcl.getvar('report_args'))
        self.assertEqual(report_args[-2], 'routed')
        self.assertEqual(int(report_args[-1]), 0)

    def test_export_requires_separate_quota_before_any_file_write(self):
        tcl = self.implementation_interpreter('claim_export')
        with self.assertRaises(tkinter.TclError):
            tcl.call('fd::publish', str(audit.BASE / 'fixed_build_4'), 'audit.py')
        self.assertEqual(tcl.splitlist(tcl.getvar('calls')), ('claim_export',))
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            out = base / 'current'
            out.mkdir()
            ledger = base / 'ledger.json'
            audit.save(ledger, {'fixed_build_claim': {'attempt': 4, 'out': 'current'},
                                'fixed_build_4_stages': {'export': {'limit': 0, 'used': 0}}})
            before = audit.sha(ledger)
            with mock.patch.object(audit, 'ROOT', base), mock.patch.object(audit, 'LEDGER', ledger):
                self.rejects(audit.claim_export, out)
            self.assertEqual(audit.sha(ledger), before)
            self.assertEqual(list(out.iterdir()), [])

    def export_interpreter(self, fail_at=''):
        tcl = self.implementation_interpreter(fail_at)
        tcl.eval('''
            proc current_design {} {return frozen_routed_design}
            proc get_property {name object} {
                if {$name ne "PART" || $object ne "frozen_routed_design"} {error "wrong metadata context"}
                return xc7z020clg400-2
            }
            proc write_bitstream {args} {record write_bitstream;set ::bit_args $args}
            proc write_hw_platform {args} {record write_hw_platform;set ::xsa_args $args}
            rename file original_file
            proc file {action args} {
                if {$action eq "copy"} {record copy_hwh;return}
                if {$action eq "exists" && [string match *.bit [lindex $args 0]]} {return 0}
                return [original_file $action {*}$args]
            }
        ''')
        return tcl

    def test_export_uses_embedded_checkpoint_metadata_without_project_run_or_rebuild(self):
        tcl = self.export_interpreter()
        tcl.call('fixed_display_main', '-finalize', '-out', str(audit.BASE / 'fixed_build_4'))
        self.assertEqual(tcl.splitlist(tcl.getvar('calls')), (
            'gate', 'open_checkpoint', 'claim_export', 'write_hw_platform',
            'extract_export', 'export', 'close_project'))
        self.assertEqual(tcl.splitlist(tcl.getvar('xsa_args'))[:2], ('-fixed', '-include_bit'))
        self.assertEqual(Path(str(tcl.getvar('opened'))).resolve(), (audit.BASE / 'fixed_build_4/routed.dcp').resolve())

    def test_export_failures_stop_without_regeneration_or_fallback(self):
        sequence = ('gate', 'open_checkpoint', 'claim_export', 'write_hw_platform',
                    'extract_export', 'export', 'close_project')
        for at in ('gate', 'claim_export', 'write_hw_platform', 'extract_export', 'export'):
            tcl = self.export_interpreter(at)
            with self.assertRaises(tkinter.TclError):
                tcl.call('fixed_display_main', '-finalize', '-out', str(audit.BASE / 'fixed_build_4'))
            self.assertEqual(tcl.splitlist(tcl.getvar('calls')), sequence[:sequence.index(at) + 1])

    def test_artifacts_require_consumed_identity_bound_export_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            with mock.patch.object(audit, 'export_inputs') as verify:
                audit.export_artifact_policy(out)
                verify.assert_not_called()
                (out / 'system_wrapper.bit').write_bytes(b'not a valid BIT')
                verify.side_effect = ValueError('unclaimed or changed hardware')
                self.rejects(audit.export_artifact_policy, out)
                verify.assert_called_once_with(out, consumed=True)

    @staticmethod
    def bit_fixture(time='12:00:00', payload=b'configuration'):
        data = b'\x00\x09' + bytes.fromhex('0ff00ff00ff00ff000') + b'\x00\x01'
        for tag, value in zip(b'abcd', ('system_wrapper;COMPRESS=TRUE;UserID=0XFFFFFFFF;Version=2023.1',
                                        '7z020clg400', '2026/10/22', time)):
            value = value.encode('ascii') + b'\0'
            data += bytes([tag]) + len(value).to_bytes(2, 'big') + value
        return data + b'e' + len(payload).to_bytes(4, 'big') + payload

    def test_bit_container_rejects_wrong_part_and_incomplete_or_trailing_payload(self):
        data = self.bit_fixture()
        self.assertEqual(audit.bit_identity(data)['payload_bytes'], len(b'configuration'))
        for bad in (data[:-1], data + b'junk', data.replace(b'7z020', b'7z010'),
                    data.replace(b'2023.1', b'2022.1')):
            self.rejects(audit.bit_identity, bad)

    def test_pairing_repairs_timestamp_only_and_preserves_original_but_rejects_hardware_mismatch(self):
        for same_hardware in (True, False):
            with tempfile.TemporaryDirectory() as folder:
                out = Path(folder)
                (out / 'export_1').mkdir()
                (out / 'hw_handoff').mkdir()
                (out / 'hw_handoff/system.hwh').write_bytes(b'canonical metadata')
                old = self.bit_fixture('12:00:00')
                new = self.bit_fixture('12:00:10', b'configuration' if same_hardware else b'changed')
                (out / 'system_wrapper.bit').write_bytes(old)
                with zipfile.ZipFile(out / 'system.xsa', 'w') as archive:
                    archive.writestr('system.bit', new)
                    archive.writestr('system.hwh', b'canonical metadata')
                with mock.patch.object(audit, 'export_inputs'), mock.patch.object(audit, 'BD', out / 'system.bd'):
                    if same_hardware:
                        audit.extract_export(out)
                        self.assertEqual((out / 'system_wrapper.bit').read_bytes(), new)
                        self.assertEqual((out / 'export_1/initial_system_wrapper.bit').read_bytes(), old)
                    else:
                        self.rejects(audit.extract_export, out)
                        self.assertEqual((out / 'system_wrapper.bit').read_bytes(), old)
                        self.assertFalse((out / 'export_1/initial_system_wrapper.bit').exists())

    def test_cdc_missing_unknown_critical(self):
        text = 'CDC Report\nID Severity Count Description\nCDC-3 Info 2 synchronizer\n'
        audit.cdc_metrics(text)
        self.rejects(audit.cdc_metrics, text + 'CDC-7 Critical 1 unknown reset\n')
        self.rejects(audit.cdc_metrics, 'CDC Report\nSeverity\nunrecognized format')
        self.rejects(audit.cdc_metrics, '')
        self.rejects(audit.cdc_metrics, (ROOT / 'color_test/reports/post_impl_cdc.rpt').read_text())

    def test_drc_unknown_unaccounted_and_error(self):
        text = 'report_drc\nViolations found: 1\n| RULE-1 | Warning | example | 1 |\n'
        audit.drc_metrics(text, 'drc')
        self.rejects(audit.drc_metrics, text.replace('Warning', 'Error'), 'drc')
        self.rejects(audit.drc_metrics, text.replace('found: 1', 'found: 2'), 'drc')
        self.rejects(audit.drc_metrics, text.replace('Warning', 'UNKNOWN'), 'drc')
        self.rejects(audit.drc_metrics, '', 'drc')

    def test_bus_skew_fail_closed(self):
        audit.bus_skew('report_bus_skew\nNo bus skew constraints found', False)
        audit.bus_skew('report_bus_skew\nSlack (MET) : 0.1ns', True)
        for text, applicable in [('', False), ('report_bus_skew\nunknown', False),
                                  ('report_bus_skew\nNo paths found', True),
                                  ('report_bus_skew\nSlack (VIOLATED) : -0.1ns', True),
                                  ('report_bus_skew\nSlack (MET) : 0.1ns', False)]:
            self.rejects(audit.bus_skew, text, applicable)

    def test_synthesis_physical_checks_remain_pending_and_route_stays_strict(self):
        text = 'report_drc\nViolations found: 2\n| UNPL-1 | Error | Unplaced Cell | 1 |\n| RTSTAT-12 | Error | No Routing | 1 |\n'
        self.assertEqual(len(audit.synth_drc(text)['physical_pending']), 2)
        self.rejects(audit.drc_metrics, text, 'drc')
        self.rejects(audit.synth_drc, text.replace('UNPL-1', 'OTHER-1'))

    def test_resource_budget(self):
        text = (ROOT / 'color_test/reports/post_impl_utilization.rpt').read_text()
        audit.utilization(text)
        self.rejects(audit.utilization, '')
        rows = '\n'.join(f'| {name} | 1 | 0 | 0 | 10 | {percent} |' for name, percent in {
            'Slice LUTs': 70, 'Slice Registers': 0, 'Slice': 0, 'Block RAM Tile': 0,
            'DSPs': 0, 'Bonded IOB': 0, 'BUFGCTRL': 0, 'BUFIO': 0, 'BUFR': 0, 'MMCME2_ADV': 0}.items())
        self.rejects(audit.utilization, rows)

    def test_clock_manifest_cannot_accept_missing_startup_or_extra_alias(self):
        rows = {'clk_fpga_0': 10, 'clk_fpga_1': 7, 'hdmi_serial_startup': 2,
                'hdmi_pixel_startup': 10, 'hdmi_serial_runtime': 35/13, 'hdmi_pixel_runtime': 175/13}
        text = '\n'.join(f'{k}\t{v}' for k,v in rows.items())
        audit.clock_manifest(text)
        self.rejects(audit.clock_manifest, '\n'.join(line for line in text.splitlines() if 'startup' not in line))
        self.rejects(audit.clock_manifest, text+'\nextra_alias\t10')

    def test_tcl_native_clock_context_and_no_vacuous_reset_exception(self):
        tcl = tkinter.Tcl()
        for path in ('color_test/tools/build_bitstream.tcl', 'color_test/tools/fixed_display.tcl',
                     'color_test/color_test.srcs/constrs_1/new/display720.xdc'):
            self.assertEqual(tcl.call('info', 'complete', (ROOT / path).read_text()), 1)
        tcl.eval('proc current_design {} {return mock}; proc get_pins {args} {return [lindex $args end]}; proc get_ports {args} {return [lindex $args end]}; proc get_clocks {args} {return [lindex $args end]}')
        tcl.eval('set clocks {}; set groups {}; set falsepaths {}; proc set_property {args} {}; proc create_generated_clock {args} {lappend ::clocks $args}; proc set_clock_groups {args} {lappend ::groups $args}; proc set_false_path {args} {lappend ::falsepaths $args}')
        tcl.call('source', str(ROOT / 'color_test/color_test.srcs/constrs_1/new/display720.xdc'))
        clocks = tcl.splitlist(tcl.getvar('clocks'))
        self.assertEqual(len(clocks), 0)
        self.assertEqual(len(tcl.splitlist(tcl.getvar('groups'))), 0)
        self.assertEqual(len(tcl.splitlist(tcl.getvar('falsepaths'))), 0)
        body = (ROOT / 'color_test/tools/fixed_display.tcl').read_text()
        self.assertIn('reset_timing -invalid -clock_reservation', body)
        self.assertIn('write_xdc -type timing -force', body)
        self.assertIn('read_xdc $context', body)
        self.assertIn('clock_state startup $context', body)

    def test_native_clock_waveform_and_parent_are_mandatory(self):
        text = 'serial\tI\t2.000\t0.000 1.000\tclk_fpga_0\npixel\tP\t10.000\t0.000 4.000\tI\n'
        audit.native_clock_identity(text, 'startup')
        for bad in (text.replace('0.000 4.000', '0.000 5.000'),
                    text.replace('\tI\n', '\tclk_fpga_0\n'),
                    text.splitlines()[0], text + text.splitlines()[0]):
            self.rejects(audit.native_clock_identity, bad, 'startup')

    def test_two_state_reports_cannot_be_omitted(self):
        with tempfile.TemporaryDirectory() as temp:
            self.rejects(audit.state_evidence, Path(temp), False)
        for state in ('startup', 'runtime'):
            for kind in ('timing.rpt', 'cdc.rpt', 'drc.rpt', 'methodology.rpt',
                         'exceptions.rpt', 'ignored_exceptions.rpt', 'bus_skew.rpt'):
                self.assertIn(f'{state}_{kind}', audit.REPORTS)

    def test_shared_lock_source_and_registered_ready(self):
        base = ROOT / 'color_test/repo/ip/axi_dynclk_v1_0/src'
        guard = (base / 'display_clock_guard.vhd').read_text()
        top = (base / 'axi_dynclk.vhd').read_text()
        drp = (base / 'mmcme2_drp.v').read_text()
        self.assertIn('ready <= qualified;', guard)
        self.assertNotIn('qualified and', guard)
        self.assertIn('synchronized_locked <= lock_sync(1);', guard)
        self.assertIn('LOCKED_SYNC_I => synchronized_locked', top)
        self.assertIn("if (synchronized_locked = '1')", top)
        self.assertIn('if(LOCKED_SYNC_I)', drp)
        self.assertNotIn('if(LOCKED)', drp)

    def test_helper_is_inert_when_sourced(self):
        tcl = tkinter.Tcl()
        tcl.call('source', str(ROOT / 'color_test/tools/fixed_display.tcl'))
        self.assertEqual(tcl.call('fd::one', 'a', 'test'), 'a')
        for objects in ('', 'a b'):
            with self.assertRaises(tkinter.TclError):
                tcl.call('fd::one', objects, 'test')
        with self.assertRaises(tkinter.TclError):
            tcl.call('fixed_display_main', '-out')

    def test_manifest_dependencies_exist(self):
        files = audit.source_files()
        self.assertTrue(all(p.is_file() for p in files))
        self.assertTrue(any(p.name == 'display_clock_guard.vhd' for p in files))

    def test_unbuilt_artifacts_cannot_gate_or_consume_budget(self):
        before = audit.sha(audit.LEDGER)
        out = audit.BASE / 'fixed_entry_1'
        result = subprocess.run([sys.executable, str(ROOT / 'color_test/tools/fixed_display_audit.py'),
                                 'gate', '--out', str(out)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No matching fixed-build claim', result.stderr)
        self.assertEqual(audit.sha(audit.LEDGER), before)
        self.assertFalse((out / 'system_wrapper.bit').exists())

    def test_isolated_helper_ignores_foreign_python_runtime(self):
        environment = dict(os.environ, PYTHONHOME='not_the_host_python_runtime',
                           PYTHONPATH='D:/Xilinx/Vivado/2023.1/tps/win64/python-3.8.3/lib')
        result = subprocess.run([sys.executable, '-I', str(ROOT / 'color_test/tools/fixed_display_audit.py'),
                                 'gate', '--out', str(audit.BASE / 'fixed_entry_1')],
                                env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No matching fixed-build claim', result.stderr)
        self.assertNotIn('SRE module mismatch', result.stderr)

    def test_installed_user_bounds_are_distinct_from_model(self):
        ns = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
        r = ET.parse('D:/Xilinx/Vivado/2023.1/data/ip/xilinx/proc_sys_reset_v5_0/component.xml').getroot()
        def maximum(query):
            p = next(p for p in r.findall(query, ns) if p.findtext('s:name', namespaces=ns) == 'C_AUX_RST_WIDTH')
            return int(p.find('s:value', ns).get('{' + ns['s'] + '}maximum'))
        self.assertEqual(maximum('s:parameters/s:parameter'), 16)
        self.assertEqual(maximum('s:model/s:modelParameters/s:modelParameter'), 32)

    def test_prepared_partition_is_validated_without_deleting_again(self):
        tcl = tkinter.Tcl()
        tcl.call('source', str(ROOT / 'color_test/tools/fixed_display.tcl'))
        tcl.eval('set root_cells [concat $fd::keep {display_irq_zero display_rst_axis display_rst_pixel}]; set verified 0; proc get_bd_cells {args} {return $::root_cells}; proc delete_bd_objs {args} {error "unexpected second deletion"}; rename fd::validate_partition fd::real_validate_partition; proc fd::validate_partition {} {incr ::verified}')
        tcl.call('fd::partition')
        self.assertEqual(tcl.getvar('verified'), 1)
        tcl.eval('set root_cells [lrange $root_cells 1 end]')
        with self.assertRaises(tkinter.TclError):
            tcl.call('fd::partition')

    def test_delete_interface_owner_before_scalar_ports(self):
        tcl = tkinter.Tcl()
        tcl.call('source', str(ROOT / 'color_test/tools/fixed_display.tcl'))
        body = tcl.call('info', 'body', 'fd::partition')
        self.assertLess(body.index('get_bd_intf_ports -quiet dphy_hs_clock'), body.index('get_bd_ports -quiet dphy_*'))
        self.assertNotIn('CONFIG.C_EXT_RESET_HIGH', body)

    def test_hwh_reset_contract_rejects_old_width_and_wrong_polarity(self):
        path = ROOT / 'color_test/software/vision_ps_baremetal/tools/game_display_qualify.py'
        spec = importlib.util.spec_from_file_location('display_contract', path)
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        modules = {'axi_dynclk_0': ET.fromstring('<MODULE COREREVISION="4"><PORT NAME="DISPLAY_READY_O"/></MODULE>')}
        for name in ('display_rst_axis', 'display_rst_pixel'):
            modules[name] = ET.fromstring('<MODULE COREREVISION="13"><PARAMETER NAME="C_AUX_RST_WIDTH" VALUE="16"/><PARAMETER NAME="C_EXT_RESET_HIGH" VALUE="0"/><PARAMETER NAME="C_AUX_RESET_HIGH" VALUE="0"/></MODULE>')
        package = {'display_reset_contract': 'guard1_dual_psr13_aux16', 'dynclk_status_mask': 3}
        contract.verify_reset_contract(package, modules)
        for parameter, value in [('C_AUX_RST_WIDTH', '32'), ('C_EXT_RESET_HIGH', '1'), ('C_AUX_RESET_HIGH', '1')]:
            broken = copy.deepcopy(modules)
            broken['display_rst_pixel'].find(f'.//PARAMETER[@NAME="{parameter}"]').set('VALUE', value)
            self.rejects(contract.verify_reset_contract, package, broken)
        self.rejects(contract.verify_reset_contract, {**package, 'display_reset_contract': 'guard1_dual_psr13_aux32'}, modules)
        self.rejects(contract.verify_reset_contract, {**package, 'dynclk_status_mask': 1}, modules)

    def test_cumulative_quota_requires_an_explicit_added_limit(self):
        self.assertEqual(audit.next_build_attempt({'used': 0, 'limit': 1}), 1)
        self.rejects(audit.next_build_attempt, {'used': 1, 'limit': 1})
        self.assertEqual(audit.next_build_attempt({'used': 1, 'limit': 2}), 2)
        self.rejects(audit.next_build_attempt, {'used': False, 'limit': 1})

    def test_spent_build_quota_stays_closed_without_any_mutation(self):
        # Isolated exhausted ledger: the real ledger may hold a newly authorized
        # unused attempt. A negative test must never claim that real allowance.
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            ledger = base / 'ledger.json'
            audit.save(ledger, {'budget': {'fixed_build': {'used': 2, 'limit': 2}}})
            before = audit.sha(ledger)
            with mock.patch.object(audit, 'BASE', base), mock.patch.object(audit, 'LEDGER', ledger):
                self.rejects(audit.claim, base / 'never_created')
            self.assertEqual(audit.sha(ledger), before)
            self.assertFalse((base / 'never_created').exists())

    def test_cache_calls_are_individual_and_preparation_never_launches(self):
        tcl = tkinter.Tcl()
        tcl.call('source', str(ROOT / 'color_test/tools/fixed_display.tcl'))
        tcl.eval('set cache_calls {}; proc get_ips {args} {return [lindex $args end]}; proc config_ip_cache {flag ip} {if {$flag ne "-disable_for_ip" || [llength $ip] != 1} {error "wrong cache signature"}; lappend ::cache_calls $ip}')
        self.assertEqual(tcl.call('fd::disable_ip_caches'), 2)
        self.assertEqual(len(tcl.splitlist(tcl.getvar('cache_calls'))), 2)
        self.assertNotIn('launch_runs', tcl.call('info', 'body', 'fd::prepare_full'))
        body = tcl.call('info', 'body', 'fixed_display_main')
        self.assertIn('synth_gate', body)
        self.assertIn('claim_implementation', body)

    def test_real_prepared_bd_without_scalar_port_section(self):
        design = audit.load(audit.BD)['design']
        audit.validate_partition(design)
        broken = copy.deepcopy(design)
        broken.setdefault('ports', {})['dphy_unexpected'] = {'direction': 'I'}
        self.rejects(audit.validate_partition, broken)
        broken = copy.deepcopy(design)
        broken['components'].pop('display_rst_pixel')
        self.rejects(audit.validate_partition, broken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
