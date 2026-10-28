"""Host input/handoff rejection checks. No compiler, PYNQ import or device."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import tkinter
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[4]
TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS/(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


GEN = module('generate_game_config')
PREP = module('prepare_game_beam')


class StandaloneBeamInputs(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'pc_vision/game_config.json').read_text(encoding='utf-8'))

    def test_measured_config_has_fixed_emitter_and_no_level_state(self):
        self.config['real_scene']['beam']['detector_profile'] = 'apriltag'
        text = GEN.generate_beam(self.config)
        self.assertIn('{32.0f, 500.0f},{1.0f, 0.0f},0,VISION_STABILITY_B', text)
        self.assertEqual(text.count('.length = 55.0f, .width = 25.0f'), 2)
        self.assertIn('0.8518518519f', text)  #46mm reflective line /54mm marker spacing
        self.assertNotIn('game_default_config', text)
        self.assertNotIn('SOURCE', text)

    def test_age_policy_is_beam_only_and_can_restore_strict_limit(self):
        self.assertEqual(self.config['board_game']['scene_max_age_ms'], 250)
        self.config['real_scene']['beam']['max_age_ms'] = 250
        self.assertIn('{32.0f, 500.0f},{1.0f, 0.0f},250,VISION_STABILITY_B',
                      GEN.generate_beam(self.config))
        for age in (-1, 251, 1500, False, '0'):
            self.config['real_scene']['beam']['max_age_ms'] = age
            with self.subTest(age=age), self.assertRaises(ValueError):
                GEN.generate_beam(self.config)

    def test_restored_config_needs_no_tag_or_strip_measurements(self):
        real = self.config['real_scene']
        del real['portal_templates']
        del real['physical_geometry_mm']
        text = GEN.generate_beam(self.config)
        self.assertIn('VISION_PROFILE_RESTORED,6000,250,1', text)
        self.assertNotIn('VisionPortalTemplate', text)
        self.assertNotIn('SOURCE', text)
        real['beam']['emitter_point'] = [64, 400]
        self.assertIn('{64.0f, 400.0f}', GEN.generate_beam(self.config))

    def test_restored_policy_and_retention_reject_bad_config(self):
        for key, value in (('portal_b_exit_side', 2), ('portal_b_exit_side', True),
                           ('display_timeout_ms', 6001), ('display_dropout_ms', 251),
                           ('emitter_point', [1280, 400]), ('emitter_direction', [0, 0]),
                           ('detector_profile', 'unknown')):
            config = copy.deepcopy(self.config)
            config['real_scene']['beam'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                GEN.generate_beam(config)

    def test_level_art_changes_do_not_change_beam(self):
        other = copy.deepcopy(self.config)
        del other['board_game']
        del other['model_sizes']
        self.assertEqual(GEN.generate_beam(self.config), GEN.generate_beam(other))

    def test_reject_wrong_marker_identity_or_body(self):
        for key, value in (('ids', [10, 11, 22]), ('body_size', [81, 25]),
                           ('effective_size', [90, 25]), ('image_handedness', 0)):
            config = copy.deepcopy(self.config)
            config['real_scene']['beam']['detector_profile'] = 'apriltag'
            config['real_scene']['portal_templates']['PORTAL_A'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                GEN.generate_beam(config)

    def test_reject_degenerate_wall_marker_span(self):
        self.config['real_scene']['beam']['detector_profile'] = 'apriltag'
        self.config['real_scene']['physical_geometry_mm']['WALL']['white_mark_end_gap'] = 100
        with self.assertRaises(ValueError):
            GEN.generate_beam(self.config)

    def handoff(self, mutate=None, extra_bit=False):
        # Reuse the retained declared hardware as fixture data; never execute it.
        path = ROOT/'color_test/build/pl_rate93_production/build_5/export/system.xsa'
        if not path.exists():
            self.skipTest('Retained build5 handoff fixture is unavailable')
        with zipfile.ZipFile(path) as archive:
            hwh_name = next(n for n in archive.namelist() if n.endswith('.hwh'))
            bit_name = next(n for n in archive.namelist() if n.endswith('.bit'))
            hwh = ET.fromstring(archive.read(hwh_name))
            bit = archive.read(bit_name)
        if mutate:
            mutate(hwh)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        target = Path(directory.name)/'fixture.xsa'
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('system.hwh', ET.tostring(hwh))
            archive.writestr('system.bit', bit)
            if extra_bit:
                archive.writestr('other.bit', bit)
        return target

    def test_inspects_embedded_pair_and_supported_counter_abi(self):
        info, bit = PREP.inspect_xsa(self.handoff())
        self.assertEqual(info['csi_minor'], 2)
        self.assertEqual(info['bit_sha256'], PREP.digest(bit))
        self.assertEqual(len(info['xsa_sha256']), 64)

    def test_reject_multiple_bit_candidates(self):
        with self.assertRaises(ValueError):
            PREP.inspect_xsa(self.handoff(extra_bit=True))

    def test_reject_wrong_device(self):
        with self.assertRaises(ValueError):
            PREP.inspect_xsa(self.handoff(lambda root: root.find('SYSTEMINFO').set('DEVICE', '7z010')))

    def test_reject_wrong_clock_even_with_same_declared_rate(self):
        def mutate(root):
            for node in root.iter('MODULE'):
                if node.get('INSTANCE') == 'axi_vdma_1':
                    for port in node.iter('PORT'):
                        if port.get('NAME') == 's_axis_s2mm_aclk':
                            port.set('SIGNAME', 'other_clock')
        with self.assertRaises(ValueError):
            PREP.inspect_xsa(self.handoff(mutate))

    def test_reject_highlight_that_would_replace_camera_colors(self):
        def mutate(root):
            for node in root.iter('MODULE'):
                if node.get('INSTANCE') == 'axis_color_highlight_0':
                    for param in node.iter('PARAMETER'):
                        if param.get('NAME') == 'ENABLE_HIGHLIGHT':
                            param.set('VALUE', '1')
        with self.assertRaises(ValueError):
            PREP.inspect_xsa(self.handoff(mutate))

    def test_verified_historical_live_profile_has_legacy_abi(self):
        info = PREP.inspect_live_baseline()
        self.assertEqual(info['verified_files'], 12)
        hardware, bit = PREP.inspect_xsa(ROOT/PREP.LIVE_PLATFORM/'hw/color_test.xsa',
                                         allow_historical_live=True)
        self.assertEqual(hardware['bit_sha256'], PREP.LIVE_BIT_SHA256)
        self.assertEqual(hardware['csi_minor'], 1)
        self.assertFalse(hardware['csi_counters_coherent'])
        self.assertEqual(hardware['display_status_mask'], 1)
        self.assertEqual(PREP.digest(bit), PREP.LIVE_BIT_SHA256)

    def test_legacy_xsa_not_admitted_as_modern_coherent_hardware(self):
        with self.assertRaisesRegex(ValueError, 'CSI1.1'):
            PREP.inspect_xsa(ROOT/PREP.LIVE_PLATFORM/'hw/color_test.xsa')

    def test_unknown_csi11_not_accepted_by_version_number(self):
        def mutate(root):
            for node in root.iter('MODULE'):
                if node.get('INSTANCE') == 'MIPI_CSI_2_RX_0':
                    for param in node.iter('PARAMETER'):
                        if param.get('NAME') == 'kVersionMinor':
                            param.set('VALUE', '1')
                        if param.get('NAME') == 'C_S_AXI_LITE_ADDR_WIDTH':
                            param.set('VALUE', '4')
        with self.assertRaisesRegex(ValueError, 'exact historical'):
            PREP.inspect_xsa(self.handoff(mutate), allow_historical_live=True)

    def test_modern_hardware_cannot_silently_use_old_display_clock_abi(self):
        def mutate(root):
            for node in root.iter('MODULE'):
                if node.get('INSTANCE') == 'axi_dynclk_0':
                    for port in node.iter('PORT'):
                        if port.get('NAME') == 'DISPLAY_READY_O':
                            port.set('NAME', 'LOCKED_O_ONLY')
        with self.assertRaisesRegex(ValueError, 'Display clock ABI'):
            PREP.inspect_xsa(self.handoff(mutate))

    def baseline_fixture(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        manifest = ROOT/PREP.LIVE_OUTPUT/'validation.json'
        validation = json.loads(manifest.read_text(encoding='utf-8'))
        targets = [manifest.relative_to(ROOT)] + [Path(item['path']) for item in
                                                  validation['matched_inputs'] + validation['outputs']]
        for relative in targets:
            (root/relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT/relative), str(root/relative))
        return root

    def test_baseline_rejects_changed_bsp_fsbl_and_boot(self):
        root = self.baseline_fixture()
        for relative in (PREP.LIVE_PLATFORM/'ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/lib/libxil.a',
                         PREP.LIVE_PLATFORM/'zynq_fsbl/fsbl.elf', PREP.LIVE_OUTPUT/'BOOT.bin'):
            target = root/relative
            raw = target.read_bytes()
            target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            with self.subTest(path=str(relative)), self.assertRaisesRegex(ValueError, 'artifact changed'):
                PREP.inspect_live_baseline(root)
            target.write_bytes(raw)

    def test_baseline_rejects_edited_manifest_even_if_hashes_are_rewritten(self):
        root = self.baseline_fixture()
        manifest = root/PREP.LIVE_OUTPUT/'validation.json'
        validation = json.loads(manifest.read_text(encoding='utf-8'))
        validation['outputs'][0]['sha256'] = '0'*64
        manifest.write_text(json.dumps(validation), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            PREP.inspect_live_baseline(root)

    def test_live_build_plan_never_generates_or_updates_historical_platform(self):
        # Execute Tcl control flow with ALL subprocesses and writes stubbed;
        # no compiler/platform tool or directory creation can occur here.
        tcl = tkinter.Tcl()
        calls = []
        tcl.createcommand('exec', lambda *args: calls.append(args) or
                          ('ARM Tag_ABI_VFP_args: VFP registers' if any('readelf' in a for a in args) else ''))
        tcl.createcommand('platform', lambda *args: self.fail('Unexpected platform operation: '+str(args)))
        tcl.createcommand('setws', lambda *args: self.fail('Unexpected workspace mutation'))
        tcl.createcommand('open', lambda *args: 'stub_file')
        tcl.createcommand('read', lambda *args: 'VISION_PROFILE_RESTORED')
        tcl.createcommand('close', lambda *args: '')
        tcl.createcommand('puts', lambda *args: '')
        tcl.createcommand('exit', lambda *args: self.fail('Unexpected Tcl exit: '+str(args)))
        tcl.eval('rename file real_file; proc file {command args} {if {$command eq "mkdir"} {return}; return [real_file $command {*}$args]}')
        tcl.setvar('env(XILINX_VITIS)', 'STUB_VITIS_ONLY')
        tcl.setvar('argv', ('-baseline', 'live', '-tag', 'host_plan_no_outputs', '-boot', '0'))
        tcl.call('source', str(TOOLS/'build_game_beam.tcl'))
        prepare = calls[0]
        self.assertIn('--baseline', prepare)
        self.assertIn('live', prepare)
        self.assertTrue(any('gcc.exe' in c[0] for c in calls))
        self.assertFalse((ROOT/'color_test/build/beam_standalone/host_plan_no_outputs').exists())

    def test_live_preparation_freezes_matching_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'inputs'
            argv = ['prepare_game_beam.py', '--baseline', 'live', '--output', str(output)]
            with patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
                PREP.main()  # Host copies/config only; never invokes a compiler.
            metadata = json.loads((output/'inputs.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['xsa_sha256'], PREP.LIVE_XSA_SHA256)
            self.assertEqual(metadata['baseline']['profile'], 'historical_live_20261026')
            header = (output/'game_beam_config.h').read_text(encoding='utf-8')
            self.assertIn('#define GAME_BEAM_CSI_VERSION 0x00010001U', header)
            self.assertIn('#define GAME_BEAM_DISPLAY_STATUS_MASK 1U', header)
            self.assertIn('#define GAME_BEAM_COUNTERS_COHERENT 0', header)
            self.assertIn('#define GAME_BEAM_BASELINE_LIVE 1', header)
            self.assertEqual(PREP.digest((output/'system_wrapper.bit').read_bytes()), PREP.LIVE_BIT_SHA256)
            platform = ROOT/PREP.LIVE_PLATFORM
            for original, target in ((platform/'zynq_fsbl/fsbl.elf', output/'fsbl.elf'),
                                     (platform/'hw/ps7_init.tcl', output/'ps7_init.tcl'),
                                     (platform/'ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/lib/libxil.a',
                                      output/'bsp/lib/libxil.a')):
                self.assertEqual(original.read_bytes(), target.read_bytes())
            before = (output/'game_beam_config.c').read_bytes()
            with patch('sys.argv', argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                PREP.main()
            self.assertEqual(before, (output/'game_beam_config.c').read_bytes())


if __name__ == '__main__':
    unittest.main()
