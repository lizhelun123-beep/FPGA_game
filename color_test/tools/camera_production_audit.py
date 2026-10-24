"""Provenance and one-build claim for the canonical live-camera restoration."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = sys.argv[2] if len(sys.argv) == 3 and sys.argv[2] in {'2','3','4','5'} else '2'
OUT = ROOT / ('color_test/build/pl_rate93_production/build_' + BUILD)
REARM_REVIEW = ROOT / 'color_test/build/camera_crc_link/rx_fault_1/rearm_1/review.json'
REARM_GATES = {
    'real_short_gap': ('model_2/fixed/result.json', 'PASS_REAL_SHORT_GAP_ALL9_PACKETS_ALL3_REF_PHASES_EXACT_CRC_TAILS'),
    'serial_crc': ('serial_integration/result.json', 'PASS_SERIAL_PHY_CSI_ALL8_PHASES_10240_PIXELS_CRC_7GOOD_1BAD'),
    'startup_reset': ('startup_reset/result.json', 'PASS_FUNCTIONAL_MODEL_ONLY'),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value, exclusive=False):
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def llp_authorization(stage='build'):
    """Build5 binds the repaired LLP and actual offline counterexample/regressions."""
    authorization = json.loads((OUT / 'authorization.json').read_text(encoding='utf-8'))
    for key in ('production_builds', 'full_builds', 'syntheses', 'implementations', 'gated_paired_exports'):
        require(type(authorization.get(key)) is int and authorization[key] == 1,
                'Build5 requires exactly one authorized ' + key)
    if stage == 'load':
        for key in ('temporary_loads', 'health_streams'):
            require(type(authorization.get(key)) is int and authorization[key] == 1,
                    'Build5 requires exactly one authorized ' + key)
        seconds = authorization.get('board_plan', {}).get('live_validation_wall_max_seconds')
        require(type(seconds) in {int, float} and math.isfinite(seconds) and 0 < seconds <= 90,
                'Build5 qualification must remain within the authorized90-second wall bound')
    repair = ROOT / 'color_test/build/csi_frame_boundary_1/review.json'
    require(authorization.get('repair_review') == repair.relative_to(ROOT).as_posix() and
            authorization.get('repair_review_sha256') == sha(repair), 'Missing/stale build5 LLP repair grant')
    review = json.loads(repair.read_text(encoding='utf-8'))
    require(review.get('status') == 'PASS_OFFLINE_LLP_FRAME_BOUNDARY_FIX_NOT_BUILT_OR_BOARD_QUALIFIED',
            'Offline LLP boundary gate closed')
    inputs = {repair}
    candidates = [run for run in review.get('runs', []) if run.get('mode') == 'candidate']
    require(len(candidates) == 1 and candidates[0].get('status') == 'PASS_OFFLINE',
            'Missing actual passing canonical LLP regression')
    candidate = candidates[0]
    for name, digest in candidate.get('source_sha256', {}).items():
        path = ROOT / name
        require(path.is_file() and sha(path) == digest, 'LLP functional source changed: ' + name)
        inputs.add(path)
    require('color_test\\repo\\ip\\MIPI_CSI_2_RX\\hdl\\LLP.vhd' in candidate['source_sha256'] or
            'color_test/repo/ip/MIPI_CSI_2_RX/hdl/LLP.vhd' in candidate['source_sha256'], 'LLP source identity missing')
    recovery = review.get('existing_recovery', {})
    require(recovery.get('status') == 'PASS_OFFLINE', 'LLP reset/recovery gate closed')
    for name, digest in recovery.get('source_sha256', {}).items():
        path = ROOT / name
        require(path.is_file() and sha(path) == digest, 'Recovery source changed: ' + name)
        inputs.add(path)
    for command in candidate.get('commands', []) + recovery.get('commands', []):
        require(command.get('returncode') == 0, 'Offline tool did not complete successfully')
        path = repair.parent / command['log']
        require(path.is_file(), 'Missing actual offline tool log: ' + str(path))
        inputs.add(path)
    validation = review.get('actual_validation', {})
    require(validation.get('fixed_full720') == dict(frames=2, pixels=1843200, raw10_packets=1440,
            pixel_or_sideband_errors=0, crc_errors=0, fifo_overflow=0), 'Full720 functional contract missing')
    require(validation.get('fixed_tail_case') == dict(pixels=20480, raw10_packets=16,
            pixel_or_sideband_errors=0, crc_errors=0, fifo_overflow=0), 'Stalled-tail functional contract missing')
    for key, success in (('simulate_tail', 'BOUNDARY_PASS'), ('simulate_full720', 'BOUNDARY_PASS')):
        logs = [c for c in candidate['commands'] if c['stage'] == key]
        require(len(logs) == 1, 'Missing unique actual simulation: ' + key)
        text = (repair.parent / logs[0]['log']).read_text(encoding='utf-8')
        require(success in text and not re.search(r'BOUNDARY_ERROR|BOUNDARY_FAIL|Failure:|Fatal:|ERROR:', text),
                'Actual LLP functional log rejected: ' + key)
    require(authorization.get('retained_rearm_review') == REARM_REVIEW.relative_to(ROOT).as_posix() and
            authorization.get('retained_rearm_review_sha256') == sha(REARM_REVIEW), 'Missing retained PHY review grant')
    retained = json.loads(REARM_REVIEW.read_text(encoding='utf-8'))
    require(retained.get('status') == 'PASS_OFFLINE_INTERBURST_REARM_AND_REAL_CRC_TAIL_REGRESSION',
            'Retained PHY gate closed')
    inputs.add(REARM_REVIEW)
    for key, base in (('source_sha256', ROOT), ('evidence_sha256', REARM_REVIEW.parent)):
        require(isinstance(retained.get(key), dict) and retained[key], 'Missing retained PHY ' + key)
        for name, digest in retained[key].items():
            path = base / name
            require(path.is_file() and sha(path) == digest, 'Retained PHY evidence changed: ' + name)
            inputs.add(path)
    for relative, expected in REARM_GATES.values():
        path = REARM_REVIEW.parent / relative
        require(json.loads(path.read_text(encoding='utf-8')).get('status') == expected,
                'Retained PHY functional gate closed: ' + relative)
        inputs.add(path)
    return inputs


def rearm_authorization(stage='build'):
    """Build4 has its own grant and immutable, same-source functional evidence."""
    if BUILD == '5':
        return llp_authorization(stage)
    if BUILD != '4':
        return set()
    authorization = json.loads((OUT / 'authorization.json').read_text(encoding='utf-8'))
    for key in ('production_builds', 'full_builds', 'syntheses', 'implementations', 'gated_paired_exports'):
        require(type(authorization.get(key)) is int and authorization[key] == 1,
                'Build4 requires exactly one authorized ' + key)
    if stage == 'load':
        require(type(authorization.get('temporary_loads')) is int and authorization['temporary_loads'] == 1,
                'Build4 requires exactly one authorized temporary load')
        require(type(authorization.get('health_streams')) is int and authorization['health_streams'] == 1,
                'Build4 requires exactly one authorized health stream')
        seconds = authorization.get('board_plan', {}).get('CRC_health_stream_max_seconds')
        require(type(seconds) in {int, float} and math.isfinite(seconds) and 0 < seconds <= 2,
                'Build4 reception/CRC observation must be bounded to at most 2 seconds')
    require(authorization.get('repair_review') == REARM_REVIEW.relative_to(ROOT).as_posix() and
            authorization.get('repair_review_sha256') == sha(REARM_REVIEW), 'Missing/stale build4 repair review grant')
    review = json.loads(REARM_REVIEW.read_text(encoding='utf-8'))
    require(review.get('status') == 'PASS_OFFLINE_INTERBURST_REARM_AND_REAL_CRC_TAIL_REGRESSION',
            'Offline rearm repair gate closed')
    inputs = {REARM_REVIEW}
    for key, base in (('source_sha256', ROOT), ('evidence_sha256', REARM_REVIEW.parent)):
        require(isinstance(review.get(key), dict) and review[key], 'Missing repair ' + key)
        for name, digest in review[key].items():
            path = base / name
            require(path.is_file() and sha(path) == digest, 'Repair evidence/source changed: ' + name)
            inputs.add(path)
    gates = authorization.get('functional_gates')
    require(isinstance(gates, dict) and set(gates) == set(REARM_GATES), 'All three build4 functional gates required')
    for name, (relative, expected) in REARM_GATES.items():
        path = REARM_REVIEW.parent / relative
        require(gates[name] == {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)},
                'Missing/stale functional authorization: ' + name)
        result = json.loads(path.read_text(encoding='utf-8'))
        require(result.get('status') == expected, 'Functional gate closed: ' + name)
    return inputs


def prepared():
    require((OUT / 'native_prepared.txt').is_file(), 'Native preparation incomplete')
    compiled = [Path(line) for line in (OUT / 'compile_sources.tsv').read_text().splitlines()]
    canonical = {}
    inputs = set(compiled)
    for folder in ('MIPI_D_PHY_RX', 'MIPI_CSI_2_RX', 'AXI_BayerToRGB', 'axi_dynclk_v1_0', 'rgb2dvi_v1_3'):
        base = ROOT / 'color_test/repo/ip' / folder
        inputs.add(base / 'component.xml')
        for path in base.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.vhd', '.v', '.sv', '.xdc', '.tcl', '.xci'}:
                inputs.add(path)
                if path.suffix.lower() in {'.vhd', '.v', '.sv'}:
                    canonical.setdefault(path.name, []).append(path)
    matched = {}
    for actual in compiled:
        candidates = canonical.get(actual.name, [])
        if candidates:
            require(len(candidates) == 1, 'Ambiguous canonical source: ' + actual.name)
            require(sha(actual) == sha(candidates[0]), 'Consumed HDL differs: ' + actual.name)
            matched[actual.name] = str(actual)
    required = {'MIPI_DPHY_Receiver.vhd', 'HS_Clocking.vhd', 'HS_Deserializer.vhd',
                'InputBuffer.vhd', 'DphySyncAsync.vhd', 'DphySyncAsyncReset.vhd',
                'DphyDebugLib.vhd', 'CsiSyncAsync.vhd', 'CsiSyncAsyncReset.vhd',
                'CsiDebugLib.vhd', 'LLP.vhd', 'MIPI_CSI2_Rx.vhd', 'MIPI_CSI2_RxTop.vhd',
                'CSIStatusBridge.vhd', 'MIPI_CSI_2_RX_v1_0_S_AXI_LITE.vhd',
                'display_clock_guard.vhd', 'axi_dynclk.vhd', 'rgb2dvi.vhd'}
    if BUILD in {'4', '5'}:
        required.add('DPHY_LaneSFEN.vhd')
    require(required <= matched.keys(), 'Missing canonical consumed HDL: ' + str(required - matched.keys()))
    log = (OUT / 'native_prepare.log').read_text()
    require('CAMERA_NATIVE_PREPARATION_COMPLETE_NO_BUILD' in log, 'Native entry not complete')
    require('CRITICAL WARNING:' not in log and 'ERROR:' not in log, 'Unresolved native preparation critical/error')
    inputs.update(ROOT / 'color_test/color_test.srcs/constrs_1/new' / name for name in
                  ('system.xdc', 'mipi.xdc', 'display720.xdc', 'hdmi_out.xdc'))
    inputs.update(ROOT / name for name in ('color_test/color_test.xpr',
                  'color_test/color_test.srcs/sources_1/bd/system/system.bd'))
    inputs.update(ROOT / 'color_test/tools' / name for name in
                  ('camera_production.tcl', 'camera_production_build.tcl',
                   'camera_production_audit.py', 'fixed_display.tcl', 'fixed_display_audit.py'))
    if BUILD in {'4', '5'}:
        inputs.update(ROOT / 'color_test/tools' / name for name in
                      ('camera_production_physical.tcl', 'camera_production_export.tcl', 'camera_input_model.tcl'))
    inputs.update(OUT / name for name in ('compile_sources.tsv', 'native_parameters.tsv',
                                        'authorization.json', 'native_prepare.log'))
    inputs.update(rearm_authorization())
    result = {'status': 'PASS_NATIVE_PREPARATION_AND_CONSUMED_HDL_IDENTITY',
              'scope': 'No synthesis/netlist/timing/board qualification',
              'matched_canonical_HDL': matched,
              'sha256': {str(path): sha(path) for path in sorted(inputs)}}
    save(OUT / 'source_identity.json', result, True)
    return {'status': result['status'], 'matched_HDL': len(matched), 'inputs': len(inputs)}


def verify():
    record = json.loads((OUT / 'source_identity.json').read_text())
    require(all(Path(path).is_file() and sha(Path(path)) == digest
                for path, digest in record['sha256'].items()), 'Prepared source changed; do not launch build')


def claim_synth():
    verify()
    rearm_authorization()
    value = {'production_build_claims': 1, 'synthesis': 'claimed_before_launch',
             'implementation': 0, 'exports': 0, 'production_loads': 0, 'live_runs': 0,
             'authorization': json.loads((OUT/'authorization.json').read_text(encoding='utf-8')),
             'historical_builds_used': int(BUILD) - 1,
             'source_identity_sha256': sha(OUT / 'source_identity.json')}
    save(OUT / 'package_ledger.json', value, True)
    return {'status': 'ONE_PRODUCTION_BUILD_CLAIMED_NO_RETRY'}


def display_audit():
    spec = importlib.util.spec_from_file_location('fixed_display_audit', ROOT / 'color_test/tools/fixed_display_audit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_hardware():
    record = json.loads((OUT / 'source_identity.json').read_text())
    # Project run metadata changes on execution. Stage/report tool additions
    # are bound separately; every prepared hardware/generated input stays fixed.
    skipped = {str(ROOT / 'color_test/color_test.xpr')}
    for path, digest in record['sha256'].items():
        if path in skipped or Path(path).parent == ROOT / 'color_test/tools':
            continue
        require(Path(path).is_file() and sha(Path(path)) == digest, 'Hardware input changed: ' + path)


def report_hashes(stage):
    return {p.name: sha(p) for p in sorted(stage.iterdir()) if p.is_file()}


def basic_structure(stage):
    rows = [line.split('\t') for line in (stage / 'netlist_cells.tsv').read_text().splitlines()]
    require(all(len(row) == 4 for row in rows), 'Unknown netlist inventory')
    require(not any(prim == '0' and black == '1' for _, _, prim, black in rows), 'Unbound nonprimitive')
    bridges = [(name, ref) for name, ref, _, _ in rows if '/MIPI_' in name and 'ResetBridge' in ref]
    require(len(bridges) == 11, 'Missing/extra camera reset bridges')
    require(all(ref.startswith('CsiResetBridge' if '/MIPI_CSI_' in name else 'DphyResetBridge') for name, ref in bridges), 'Cross-IP reset binding')
    domain = [line.split('\t') for line in (stage / 'status_domain.tsv').read_text().splitlines()]
    require(domain == [['counters', '64', 'clk_fpga_1'], ['snapshot_held', '64', 'clk_fpga_1']], 'Status producer/held clock mismatch')
    cdc = (stage / 'cdc.rpt').read_text()
    require(not any('CDC-' in line and 'StatusSnapshot/held_reg[' in line for line in cdc.splitlines()), 'Unprotected snapshot input CDC')
    return {'camera_reset_bridges': bridges, 'counter_and_snapshot_clock': 'clk_fpga_1;64 bits each'}


def tcl_pin_list(text):
    """Accept Vivado's plain/braced scalar pin list; reject unknown quoting."""
    values = []
    position = 0
    for match in re.finditer(r'\{([^{}\s"\\]+)\}|([^{}\s"\\]+)', text):
        gap = text[position:match.start()]
        require(not gap.strip() and (not values or bool(gap)), 'Unknown Tcl pin-list format')
        values.append(match[1] or match[2])
        position = match.end()
    require(not text[position:].strip(), 'Unknown Tcl pin-list format')
    return values


def phy_rearm_structure(stage):
    """Reject unknown synth topology; inspect data, enable and async controls."""
    rows = [line.split('\t') for line in (stage / 'phy_rearm.tsv').read_text().splitlines()]
    require(len(rows) == 12 and all(len(row) == 9 for row in rows), 'Unknown PHY rearm inventory')
    expected = {'logic_reset': (2, 'FDPE', "1'b1"), 'settled': (2, 'FDCE', "1'b0"),
                'settled_sync': (4, 'FDCE', "1'b0"), 'serdes_sync': (4, 'FDPE', "1'b1")}
    require(set(row[0] for row in rows) == set(expected) and len({row[2] for row in rows}) == 12,
            'Missing/duplicate PHY rearm cells')
    for kind, (count, ref, initial) in expected.items():
        group = [row for row in rows if row[0] == kind]
        require(len(group) == count and all(row[3:5] == [ref, initial] for row in group),
                'PHY rearm type/INIT mismatch: ' + kind)
    for lane in (0, 1):
        base = 'system_i/MIPI_D_PHY_RX_0/U0/DataLaneGen[' + str(lane) + '].DPHY_LaneSFEN_X/'
        local = base + 'HSDeserializerX/'
        group = [row for row in rows if row[1] == str(lane)]
        require(len(group) == 6 and all(row[2].startswith(base) for row in group), 'PHY rearm wrong lane')
        actual = {row[2]: row for row in group}
        logic = local + 'dLogicRst_reg'
        settled = base + 'cHSSettled_reg'
        bridges = {kind: [local + branch + '/SyncAsyncx/oSyncStages_reg[' + str(index) + ']'
                          for index in (0, 1)] for kind, branch in
                   (('settled_sync', 'SyncAsyncSettled'), ('serdes_sync', 'UseInternalReset.SerdesReset'))}
        require(set(actual) == {logic, settled, *bridges['settled_sync'], *bridges['serdes_sync']},
                'PHY rearm hierarchy changed; review actual topology')
        for cell, row in actual.items():
            require(row[5] == ('clk_fpga_2' if cell == settled else 'MIPI_D_PHY_RX_0_RxByteClkHS'),
                    'PHY rearm register clock mismatch: ' + cell)
            require(row[6] and row[7], 'Missing PHY rearm control/startpoint evidence: ' + cell)
        # Vivado startpoint inventories identify sequential sources at C, while
        # direct pin inventories can identify Q. Both identify the same FF.
        def source_cells(row):
            values = tcl_pin_list(row[7])
            require(all('/' in value for value in values), 'Unknown PHY rearm startpoint')
            return {value.rsplit('/', 1)[0] for value in values}
        logic_sources = source_cells(actual[logic])
        require(local + 'dDrainBusy_int_reg' in logic_sources and
                bridges['settled_sync'][1] in logic_sources and bridges['serdes_sync'][1] in logic_sources,
                'Logic reset does not consume registered complete drain/final settled/reset stages')
        require(bridges['settled_sync'][0] not in logic_sources and bridges['serdes_sync'][0] not in logic_sources,
                'First reset synchronizer stage feeds receive logic')
        require(not any('/SyncAsyncValid/' in value for value in actual[settled][7:9]),
                'Old drain-qualified settled clear retained')
        require(any('/state_reg[' in value for value in source_cells(actual[settled])),
                'Missing actual state-to-settled clear path')
        for kind, cells in bridges.items():
            parent = settled if kind == 'settled_sync' else base + 'cHSReset_reg'
            for index, cell in enumerate(cells):
                row = actual[cell]
                require(re.search(r'(?:^|\s)ASYNC_REG=(?:1|true)(?:\s|$)', row[6], re.I) is not None,
                        'Unrecognized reset synchronizer: ' + cell)
                sources = source_cells(row)
                require(parent in sources and (index == 0 or cells[0] in sources),
                        'Reset bridge lost async parent or staged release: ' + cell)
                require((index != 0 or cells[1] not in sources), 'Reset synchronizer feedback')
    return '2 settled controls independent of delayed control busy;2 byte reset controls consume complete registered drain;two existing per-lane 2FF reset bridges,recognized polarity/INIT/clock and final-stage consumption'


def llp_frame_boundary_structure(stage):
    rows = [line.split('\t') for line in (stage / 'llp_frame_boundary.tsv').read_text().splitlines()]
    require(len(rows) == 3 and all(len(row) == 7 for row in rows), 'Unknown LLP frame-boundary inventory')
    require({row[0] for row in rows} == {'pending_fs', 'payload_sof', 'pending_crc'},
            'Missing/duplicate LLP boundary register')
    require(len({row[1] for row in rows}) == 3 and all('/LLP_inst/' in row[1] for row in rows),
            'Wrong LLP boundary hierarchy')
    require(all(row[2:4] == ['FDRE', "1'b0"] and row[4] and row[4] == row[6] for row in rows),
            'LLP pending/SOF register INIT/type/clock differs from CSI counters')
    require(len({row[5] for row in rows}) == 1 and rows[0][5], 'LLP pending/SOF reset differs')
    return dict(registers=3, reference='FDRE', initial=0, clock=rows[0][4], reset=rows[0][5],
                scope='One CSI-video clock domain;synchronous common reset;functional admission order separately gated')


def synth_gate():
    verify_hardware()
    stage = OUT / 'synth'
    module = display_audit()
    structure = basic_structure(stage)
    if BUILD in {'3', '4', '5'}:
        rows=[r.split('\t') for r in (stage/'phy_drain_registers.tsv').read_text().splitlines()]
        require(all(len(r)==8 for r in rows),'Unknown PHY register inventory')
        groups={k:[r for r in rows if r[0]==k] for k in ('stop','busy','sync')}
        require([len(groups[k]) for k in ('stop','busy','sync')]==[2,2,4],'PHY drain register count')
        for group,ref,init in [('stop','FDSE',"1'b1"),('busy','FDRE',"1'b0")]:
            require(all(r[2:4]==[ref,init] and r[4] and r[5] for r in groups[group]),'PHY '+group+' type/INIT/clock mismatch')
        require(all(r[3]=="1'b0" and r[6].lower() in {'1','true'} for r in groups['sync']),'PHY drain2FF INIT/ASYNC_REG mismatch')
        for r in groups['busy']:
            if BUILD == '3':
                require('SyncAsyncValid' in r[7] and r[7].endswith('oSyncStages_reg[0]') and len(r[7].split())==1,'PHY busy feedback bypasses first2FF stage')
            else:
                sinks = r[7].split()
                first_stage = r[1].split('/HSDeserializerX/')[0] + '/SyncAsyncValid/oSyncStages_reg[0]'
                require(first_stage in sinks and all(s == first_stage or s.startswith(r[1].rsplit('/', 1)[0] + '/') for s in sinks),
                        'PHY busy feedback bypasses first2FF stage or local byte control')
        structure['PHY_tail_and_drain']='2 synchronous-set delayed-LP INIT1;2 busy INIT0;4 recognized2FF stages INIT0;direct first-stage feedback'
        if BUILD in {'4', '5'}:
            require(all(r[1].endswith('/dDrainBusy_int_reg') for r in groups['busy']), 'Missing repaired internal drain registers')
            structure['PHY_interburst_rearm'] = phy_rearm_structure(stage)
    if BUILD == '5':
        structure['LLP_frame_boundary'] = llp_frame_boundary_structure(stage)
    module.cdc_metrics((stage / 'cdc.rpt').read_text())
    module.synth_drc((stage / 'drc.rpt').read_text())
    module.drc_metrics((stage / 'methodology.rpt').read_text(), 'methodology')
    module.state_evidence(stage, routed=False)
    module.clock_manifest((stage / 'clocks.tsv').read_text())
    source_clocks = {}
    for name in ('clocked_sources.tsv', 'additional_source_clocks.tsv'):
        for line in (stage / name).read_text().splitlines():
            cell, _, clocks = line.split('\t')
            source_clocks[cell] = set(clocks.split())
    controls = (stage / 'memory_controls.tsv').read_text().splitlines()
    require(len(controls) == 1514, 'Unknown memory control inventory')
    for line in controls:
        pin, _, clocks, starts = line.split('\t')
        require(clocks, 'Missing memory clock: ' + pin)
        for start in re.findall(r'system_i/[^\s{}]+', starts):
            cell = start.rsplit('/', 1)[0]
            require(cell not in source_clocks or source_clocks[cell] <= set(clocks.split()), 'Foreign RAM control clock: ' + pin)
    review = json.loads((OUT / 'synth_review.json').read_text())
    require(review['status'] == 'PASS_SCOPED_PRE_IMPLEMENTATION' and review['report_sha256'] == report_hashes(stage), 'Missing/stale synthesis review')
    result = {'status': 'PASS_SYNTHESIS_STRUCTURE_ALLOW_ONE_IMPLEMENTATION',
              'structure': structure, 'memory_control_pins': len(controls),
              'physical_timing_and_placed_budget': 'Pending route;pre-placement hold is not accepted as final',
              'report_sha256': report_hashes(stage), 'review_sha256': sha(OUT / 'synth_review.json')}
    save(OUT / 'synth_gate.json', result, True)
    return {'status': result['status']}


def claim_implementation():
    verify_hardware()
    rearm_authorization()
    gate = json.loads((OUT / 'synth_gate.json').read_text())
    require(gate['status'] == 'PASS_SYNTHESIS_STRUCTURE_ALLOW_ONE_IMPLEMENTATION', 'Synthesis gate closed')
    require(gate['report_sha256'] == report_hashes(OUT / 'synth'), 'Synthesis reports changed')
    ledger = json.loads((OUT / 'package_ledger.json').read_text())
    require(ledger['implementation'] == 0 and ledger['exports'] == 0, 'No implementation retry')
    ledger['implementation'] = 'claimed_before_opt_place_route'
    ledger['synthesis'] = 'complete_structure_gate_pass'
    save(OUT / 'package_ledger.json', ledger)
    save(OUT / 'implementation_input.json', {'synth_gate_sha256': sha(OUT / 'synth_gate.json'),
         'checkpoint_sha256': sha(OUT / 'synth/synthesized.dcp'),
         'stage_tools_sha256': {p.name: sha(p) for p in (ROOT / 'color_test/tools').glob('camera_production*') if p.is_file()}}, True)
    return {'status': 'ONE_IMPLEMENTATION_CLAIMED'}


def rebound_gate():
    """Qualify the declared model on the exact, unchanged build2 hardware."""
    verify_hardware()
    gate = json.loads((OUT / 'synth_gate.json').read_text(encoding='utf-8'))
    require(gate['report_sha256'] == report_hashes(OUT / 'synth'), 'Synthesis evidence changed')
    stage = OUT / 'declared_model_replay_endpoints'
    physical = OUT / 'model_physical_review_flat'
    baseline = OUT / 'model_physical_review'
    module = display_audit()
    module.state_evidence(stage, routed=True)
    module.clock_manifest((stage / 'clocks.tsv').read_text())
    resources = module.utilization((stage / 'utilization.rpt').read_text())
    module.cdc_metrics((stage / 'cdc.rpt').read_text())
    module.drc_metrics((stage / 'drc.rpt').read_text(), 'drc')
    module.drc_metrics((stage / 'methodology.rpt').read_text(), 'methodology')
    require('CAMERA_MODEL_ENTRY_AND_PHYSICAL_INVENTORIES_COMPLETE_NO_BUILD_EXPORT' in
            (OUT / 'model_physical_review_flat.log').read_text(), 'Repaired entry not completed natively')
    physical_proof = {}
    def stream_sha(path):
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()
    original_edif = (baseline / 'original/design.edf')
    # The initial failed preparation used the original root-level EDIF path.
    if not original_edif.exists():
        original_edif = baseline / 'original.edf'
    def canonical_edif(path):
        # Native checkpoint serialization can reorder properties and add an
        # empty methodology annotation. Preserve all hardware/configuration
        # values and all non-property list ordering; ignore only that empty
        # report annotation and creation timestamp.
        tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', path.read_text())
        pos = 0
        def parse():
            nonlocal pos
            require(pos < len(tokens), 'Incomplete EDIF')
            token = tokens[pos]
            pos += 1
            if token != '(':
                require(token != ')', 'Unexpected EDIF close')
                return token
            children = []
            while pos < len(tokens) and tokens[pos] != ')':
                children.append(parse())
            require(pos < len(tokens), 'Unclosed EDIF list')
            pos += 1
            if children and children[0] == 'timeStamp':
                return ['timeStamp', 'CREATION_TIME']
            if (children[:2] == ['property', 'METHODOLOGY_DRC_VIOS'] and
                    children[2:] == [['string', '""']]):
                return None
            children = [v for v in children if v is not None]
            properties = [v for v in children if isinstance(v, list) and v[:1] == ['property']]
            ordinary = [v for v in children if not (isinstance(v, list) and v[:1] == ['property'])]
            return ordinary + sorted(properties, key=lambda v: json.dumps(v, separators=(',', ':')))
        tree = parse()
        require(pos == len(tokens), 'Trailing EDIF content')
        return hashlib.sha256(json.dumps(tree, separators=(',', ':')).encode()).hexdigest()
    normalized = canonical_edif(original_edif)
    for label in ('repaired_entry', 'accepted_checkpoint'):
        require(canonical_edif(physical / label / 'design.edf') == normalized,
                'Logical/primitive configuration differs: ' + label)
        physical_proof[label] = {'EDIF_semantics_sha256': normalized,
                                'normalization': 'Creation timestamp,property ordering,empty METHODOLOGY_DRC_VIOS report annotation only'}
        for kind in ('placement', 'routes'):
            old = baseline / f'original_{kind}.tsv'
            current = physical / f'{label}_{kind}.tsv'
            digest = stream_sha(old)
            require(stream_sha(current) == digest, 'Physical inventory differs: ' + label + '/' + kind)
            physical_proof[label][kind + '_sha256'] = digest
    binding = (physical / 'input_model_binding.tsv').read_text()
    require('obsolete_IP_commands_removed\t8\n' in binding and
            'canonical_board_bounds\t4\n' in binding, 'Repaired model entry did not remove exact known commands')
    metrics = {}
    sampling = []
    for state in ('startup', 'runtime'):
        text = (stage / f'{state}_timing.rpt').read_text()
        metrics[state] = module.timing_metrics(text)
        for marker, expected in (
            ('5. checking no_input_delay (6)', {'dphy_clk_lp_n', 'dphy_clk_lp_p',
                'dphy_data_lp_n[0]', 'dphy_data_lp_n[1]', 'dphy_data_lp_p[0]', 'dphy_data_lp_p[1]'}),
            ('6. checking no_output_delay (4)', {'TMDS_clk_p', 'TMDS_data_p[0]', 'TMDS_data_p[1]', 'TMDS_data_p[2]'})):
            section = text.rsplit(marker, 1)[1].split('\n7. checking', 1)[0]
            if marker.startswith('5.'):
                section = section.split('\n6. checking', 1)[0]
            ports = {line.strip() for line in section.splitlines()
                     if re.fullmatch(r'[A-Za-z_][\w\[\]]*', line.strip())}
            require(ports == expected, 'Unexpected unmodeled IO ports: ' + state)
        samples = []
        for block in re.split(r'(?=Slack \()', text)[1:]:
            if '/HSDeserializerX/Deserializer/DDLY' not in block:
                continue
            lane = re.search(r'DataLaneGen\[(\d)\]', block)
            kind = re.search(r'Path Type:\s*(Setup|Hold)', block)
            delay = re.search(r'Input Delay:\s*([\d.]+)ns', block)
            slack = re.search(r'Slack \(MET\)\s*:\s*([\d.]+)ns', block)
            require(all((lane, kind, delay, slack)), 'Unknown detailed sampling-path format')
            value = float(delay[1])
            require(abs(value - {'Setup': 9.107, 'Hold': 1.607}[kind[1]]) < .001,
                    'Unexpected effective sampling input delay')
            samples.append({'lane': int(lane[1]), 'kind': kind[1], 'input_ns': value, 'slack_ns': float(slack[1])})
        require({(v['lane'], v['kind']) for v in samples} ==
                {(lane, kind) for lane in (0, 1) for kind in ('Setup', 'Hold')}, 'Missing both-lane setup/hold evidence')
        sampling.append({'state': state, 'paths': samples})
    slack_rows = [line.split('\t') for line in (stage / 'mode_slack.tsv').read_text().splitlines()]
    require(len(slack_rows) == 8 and all(math.isfinite(float(row[3])) and float(row[3]) >= 0
            for row in slack_rows), 'HDMI directional timing failure')
    result = {'status': 'PASS_DECLARED_MODEL_ROUTED_GATES_ALLOW_ONE_EXPORT',
              'scope': 'Same build2 routed physical design;declared fixed93 input model;no board qualification',
              'timing': metrics, 'sampling': sampling, 'physical_equivalence': physical_proof,
              'resource_percent': resources, 'report_sha256': report_hashes(stage),
              'repaired_entry_tools': {name: sha(ROOT / 'color_test/tools' / name) for name in
                  ('camera_input_model.tcl', 'camera_production_build.tcl', 'camera_production_physical.tcl',
                   'camera_model_physical_review.tcl')},
              'prior_raw_failure_retained': 'route_gate.json',
              'limits': 'Reviewed LP/TMDS IO scope and scoped CDC warnings retained;no TTL,full-PVT or hardware eye guarantee'}
    save(OUT / 'declared_model_gate.json', result, True)
    return {'status': result['status'], 'timing': metrics}


def fresh_gate():
    require(BUILD in {'3','4','5'},'Fresh route gate belongs to build3/4/5')
    rearm_authorization()
    verify_hardware();stage=OUT/'route';module=display_audit()
    gate=json.loads((OUT/'synth_gate.json').read_text())
    require(gate['report_sha256']==report_hashes(OUT/'synth'),'Synthesis evidence changed')
    module.state_evidence(stage,routed=True);module.clock_manifest((stage/'clocks.tsv').read_text())
    resources=module.utilization((stage/'utilization.rpt').read_text())
    metrics={s:module.timing_metrics((stage/(s+'_timing.rpt')).read_text()) for s in ('startup','runtime')}
    sampling=[]
    for state in ('startup','runtime'):
        text=(stage/(state+'_timing.rpt')).read_text();paths=[]
        for marker,expected in [('5. checking no_input_delay',{'dphy_clk_lp_n','dphy_clk_lp_p','dphy_data_lp_n[0]','dphy_data_lp_n[1]','dphy_data_lp_p[0]','dphy_data_lp_p[1]'}),('6. checking no_output_delay',{'TMDS_clk_p','TMDS_data_p[0]','TMDS_data_p[1]','TMDS_data_p[2]'})]:
            require(marker in text,'Missing check_timing IO section')
            section=text.rsplit(marker,1)[1].split('\n7. checking',1)[0]
            if marker.startswith('5.'):section=section.split('\n6. checking',1)[0]
            ports={l.strip() for l in section.splitlines() if re.fullmatch(r'[A-Za-z_][\w\[\]]*',l.strip())}
            require(ports==expected,'Unexpected unconstrained IO in '+state)
        for block in re.split(r'(?=Slack \()',text)[1:]:
            if '/HSDeserializerX/Deserializer/DDLY' not in block:continue
            lane=re.search(r'DataLaneGen\[(\d)\]',block);kind=re.search(r'Path Type:\s*(Setup|Hold)',block);delay=re.search(r'Input Delay:\s*([\d.]+)ns',block);slack=re.search(r'Slack \(MET\)\s*:\s*([\d.]+)ns',block)
            require(all((lane,kind,delay,slack)),'Unknown sampling-path report')
            require(abs(float(delay[1])-{'Setup':9.107,'Hold':1.607}[kind[1]])<.001,'Changed camera input model')
            paths.append(dict(lane=int(lane[1]),kind=kind[1],input_ns=float(delay[1]),slack_ns=float(slack[1])))
        require({(v['lane'],v['kind']) for v in paths}=={(l,k) for l in (0,1) for k in ('Setup','Hold')},'Missing both-lane sampling coverage')
        sampling.append(dict(state=state,paths=paths))
    require(sorted((stage/'pins.tsv').read_text().splitlines())==sorted((OUT.parent/'build_2/route/pins.tsv').read_text().splitlines()),'Changed board I/O')
    slack=[r.split('\t') for r in (stage/'mode_slack.tsv').read_text().splitlines()]
    require(len(slack)==8 and all(math.isfinite(float(r[3])) and float(r[3])>=0 for r in slack),'HDMI directional timing failure')
    review=json.loads((OUT/'route_review.json').read_text())
    require(review['status']=='PASS_SCOPED_ROUTED_REVIEW' and review['report_sha256']==report_hashes(stage),'Missing/stale actual routed CDC/DRC review')
    result=dict(status='PASS_DECLARED_MODEL_ROUTED_GATES_ALLOW_ONE_EXPORT',scope='Fresh same-source repaired production build'+BUILD+';no old checkpoint transfer',timing=metrics,sampling=sampling,resource_percent=resources,report_sha256=report_hashes(stage),repaired_entry_tools={n:sha(ROOT/'color_test/tools'/n) for n in ('camera_input_model.tcl','camera_production_build.tcl','camera_production_physical.tcl','camera_production_export.tcl','camera_production_audit.py')})
    save(OUT/'declared_model_gate.json',result,True)
    return dict(status=result['status'],timing=metrics)


def hardware_contract(data):
    root = ET.fromstring(data)
    require(root.get('VIVADOVERSION') == '2023.1', 'Wrong HWH tool version')
    part = root.find('.//SYSTEMINFO')
    require(part is not None and all(part.get(k) == v for k, v in
            {'ARCH': 'zynq', 'DEVICE': '7z020', 'PACKAGE': 'clg400', 'SPEEDGRADE': '-2'}.items()), 'Wrong HWH device')
    modules = {m.get('INSTANCE'): m for m in root.findall('.//MODULE')}
    expected = {
        'MIPI_D_PHY_RX_0': {'kNoOfDataLanes': '2', 'kPPISharedEnable': 'true',
                          'kLPFromLane0': 'false', 'kDebug': 'false'},
        'MIPI_CSI_2_RX_0': {'C_S_AXI_LITE_ADDR_WIDTH': '5', 'kVersionMajor': '1',
                           'kVersionMinor': '2', 'kDebug': 'false'},
        'axi_vdma_0': {'C_INCLUDE_MM2S': '1', 'C_INCLUDE_S2MM': '0', 'C_NUM_FSTORES': '3'},
        'axi_vdma_1': {'C_INCLUDE_MM2S': '0', 'C_INCLUDE_S2MM': '1', 'C_NUM_FSTORES': '3'},
        'processing_system7_0': {'PCW_FPGA0_PERIPHERAL_FREQMHZ': '100',
                               'PCW_FPGA1_PERIPHERAL_FREQMHZ': '150',
                               'PCW_FPGA2_PERIPHERAL_FREQMHZ': '200'}}
    for name, wanted in expected.items():
        require(name in modules, 'Missing HWH module: ' + name)
        params = {p.get('NAME'): p.get('VALUE') for p in modules[name].findall('./PARAMETERS/PARAMETER')}
        require(all(params.get(k) == v for k, v in wanted.items()), 'HWH parameter mismatch: ' + name)
    addresses = {'axi_vdma_1': 0x43000000, 'axi_vdma_0': 0x43010000,
                 'axi_dynclk_0': 0x43c00000, 'vtg': 0x43c10000,
                 'MIPI_D_PHY_RX_0': 0x43c20000, 'MIPI_CSI_2_RX_0': 0x43c30000,
                 'AXI_GammaCorrection_0': 0x43c40000}
    for name, base in addresses.items():
        ranges = [r for r in root.findall('.//MEMRANGE') if r.get('INSTANCE') == name]
        require(len(ranges) == 1 and int(ranges[0].get('BASEVALUE'), 0) == base and
                int(ranges[0].get('HIGHVALUE'), 0) == base + 65535, 'HWH address/span mismatch: ' + name)
    clocks = {p.get('NAME'): int(p.get('CLKFREQUENCY'))
              for p in modules['processing_system7_0'].findall('./PORTS/PORT')
              if p.get('NAME', '').startswith('FCLK_CLK')}
    require(clocks == {'FCLK_CLK0': 100000000, 'FCLK_CLK1': 142857132, 'FCLK_CLK2': 200000000}, 'Actual HWH FCLK mismatch')
    spec = importlib.util.spec_from_file_location('display_contract', ROOT /
                'color_test/software/vision_ps_baremetal/tools/game_display_qualify.py')
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    contract.verify_reset_contract({'display_reset_contract': 'guard1_dual_psr13_aux16', 'dynclk_status_mask': 3}, modules)
    return {'part': 'xc7z020clg400-2', 'parameters': expected, 'addresses': addresses,
            'span_bytes': 65536, 'actual_FCLK_Hz': clocks,
            'CSI_register_ABI': {'version': '1.2', 'control': 0, 'completed_long_packets': 4,
                                 'CRC_errors': 8, 'version_register': 12, 'snapshot_sequence': 16, 'busy': 20},
            'limits': 'Snapshot sequence is not a frame ID;native capture backend/ABI and board startup remain unqualified'}


def export_inputs():
    verify_hardware()
    rearm_authorization()
    gate = json.loads((OUT / 'declared_model_gate.json').read_text(encoding='utf-8'))
    require(gate['status'] == 'PASS_DECLARED_MODEL_ROUTED_GATES_ALLOW_ONE_EXPORT', 'Routed gate closed')
    require(gate['report_sha256'] == report_hashes(OUT / ('route' if BUILD in {'3','4','5'} else 'declared_model_replay_endpoints')), 'Routed evidence changed')
    require(all(sha(ROOT / 'color_test/tools' / name) == digest
                for name, digest in gate['repaired_entry_tools'].items()), 'Model/physical entry changed after gate')
    canonical = ROOT / 'color_test/color_test.srcs/sources_1/bd/system/hw_handoff/system.hwh'
    contract = hardware_contract(canonical.read_bytes())
    return {'gate_sha256': sha(OUT / 'declared_model_gate.json'),
            'HWH_sha256': sha(canonical), 'hardware_contract': contract}


def platform_admission():
    checked = export_inputs()
    archive_path = OUT / 'export/system_pre_bit.xsa'
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        hw = [n for n in names if n.endswith('.hwh')]
        require(len(names) == len(set(names)) and len(hw) == 1 and
                not any(n.endswith('.bit') for n in names), 'Invalid pre-BIT platform')
        data = archive.read(hw[0])
    require(hashlib.sha256(data).hexdigest() == checked['HWH_sha256'], 'Checkpoint/canonical HWH mismatch before BIT')
    checked.update(status='PASS_PLATFORM_BEFORE_BIT', pre_bit_XSA_sha256=sha(archive_path))
    save(OUT / 'export/platform_admission.json', checked, True)
    return {'status': checked['status']}


def claim_export():
    checked = export_inputs()
    admission = json.loads((OUT / 'export/platform_admission.json').read_text(encoding='utf-8'))
    require(admission['status'] == 'PASS_PLATFORM_BEFORE_BIT' and
            admission['gate_sha256'] == checked['gate_sha256'] and
            admission['HWH_sha256'] == checked['HWH_sha256'] and
            admission['pre_bit_XSA_sha256'] == sha(OUT / 'export/system_pre_bit.xsa'), 'Stale platform admission')
    ledger = json.loads((OUT / 'package_ledger.json').read_text(encoding='utf-8'))
    require(ledger['exports'] == 0, 'Export quota already consumed')
    save(OUT / 'export/export.claim.json', {'gate_sha256': checked['gate_sha256'],
         'checkpoint_sha256': sha(OUT / ('route/routed.dcp' if BUILD in {'3','4','5'} else 'declared_model_replay_endpoints/routed.dcp')),
         'native_entry_sha256': sha(ROOT / 'color_test/tools/camera_production_export.tcl'),
         'authorization': json.loads((OUT/'authorization.json').read_text(encoding='utf-8'))}, True)
    ledger['exports'] = 1
    ledger['export_status'] = 'CLAIMED_BEFORE_SINGLE_INCLUDE_BIT'
    save(OUT / 'package_ledger.json', ledger)
    return {'status': 'ONE_GATED_EXPORT_CLAIMED_NO_BITGEN_RETRY'}


def export_result():
    checked = export_inputs()
    export = OUT / 'export'
    require((export / 'export.claim.json').is_file(), 'No export claim')
    with zipfile.ZipFile(export / 'system.xsa') as archive:
        names = archive.namelist()
        bits = [n for n in names if n.endswith('.bit')]
        hw = [n for n in names if n.endswith('.hwh')]
        require(len(names) == len(set(names)) and len(bits) == len(hw) == 1, 'Ambiguous BIT/HWH in XSA')
        bit, hwh = archive.read(bits[0]), archive.read(hw[0])
    identity = display_audit().bit_identity(bit)
    require(hashlib.sha256(hwh).hexdigest() == checked['HWH_sha256'], 'Final XSA/canonical HWH mismatch')
    for name, data in (('system_wrapper.bit', bit), ('system.hwh', hwh)):
        path = export / name
        if path.exists():
            require(path.read_bytes() == data, 'Existing payload differs from XSA: ' + name)
        else:
            path.write_bytes(data)
    value = {'status': 'PASS_PAIRED_ENGINEERING_ARTIFACTS_NOT_BOARD_QUALIFIED',
             'part': 'xc7z020clg400-2', 'display_mode': '1280x720_current_stage',
             'sensor_model': '2lane RAW10 BGGR;declared/measured93.333Mb/s per lane',
             'sha256': {name: sha(export / name) for name in ('system_wrapper.bit', 'system.hwh', 'system.xsa')},
             'BIT_identity': identity, 'gate_sha256': checked['gate_sha256'],
             'hardware_contract': checked['hardware_contract'],
             'board_operations_this_task': 0, 'new_full_builds_this_task': 1 if BUILD in {'4','5'} else 0,
             'limits': 'No production load,live localization/freshness/occlusion or capture-DMA acceptance;legacy CameraPipeline guard remains closed'}
    save(export / 'artifacts.json', value, True)
    ledger = json.loads((OUT / 'package_ledger.json').read_text(encoding='utf-8'))
    ledger['export_status'] = value['status']
    save(OUT / 'package_ledger.json', ledger)
    return {'status': value['status'], 'sha256': value['sha256']}


def claim_load():
    require(BUILD in {'3','4'},'Current production load grant belongs to build3/4')
    rearm_authorization('load')
    checked=export_inputs();art=json.loads((OUT/'export/artifacts.json').read_text());live=json.loads((OUT/'board_preload_gate.json').read_text())
    require(art['status']=='PASS_PAIRED_ENGINEERING_ARTIFACTS_NOT_BOARD_QUALIFIED','No paired export')
    require(all(sha(OUT/'export'/n)==h for n,h in art['sha256'].items()),'Changed exported artifact')
    require(0<=time.time()-live['time_unix']<=120 and live['lock_held'] and live['PS_PL_reset_held'],'Fresh locked reset-held preload gate required')
    require(live['bit_sha256']==art['sha256']['system_wrapper.bit'],'Preload BIT identity')
    identity_path=OUT/('board_identity_current.json' if BUILD=='4' else 'board_identity.json')
    require(live['boot_id']==json.loads(identity_path.read_text(encoding='utf-8'))['boot_id'],'Wrong boot')
    if BUILD=='4':
        require(live.get('identity_file')==identity_path.name and live.get('identity_sha256')==sha(identity_path),'Current UART identity changed or missing')
    ledger=json.loads((OUT/'package_ledger.json').read_text());require(ledger['production_loads']==0,'Temporary load already claimed')
    value=dict(live,hwh_sha256=art['sha256']['system.hwh'],gate_sha256=checked['gate_sha256'],scope='One actual temporary production JTAG replacement;no BOOT/SD/PS7 init')
    save(OUT/'load_claim.json',value,True);ledger['production_loads']=1;save(OUT/'package_ledger.json',ledger)
    return dict(status='ONE_TEMPORARY_PRODUCTION_LOAD_CLAIMED')


def record_program():
    require(BUILD in {'3','4'},'Wrong production program scope')
    claim=json.loads((OUT/'load_claim.json').read_text());raw=(OUT/'jtag_program_done.txt').read_text().splitlines()
    require(raw==['localhost:3121/xilinx_tcf/Digilent/210512180081','xc7z020_1','1','1','0'],'Actual JTAG target/DONE/EOS/CRC proof failed')
    result=dict(status='PASS_ONE_JTAG_PROGRAM_DONE',boot_id=claim['boot_id'],program_done=1,EOS=1,configuration_CRC_error=0,bit_sha256=claim['bit_sha256'],hwh_sha256=claim['hwh_sha256'],target=raw[0],device=raw[1],evidence='jtag_program_done.txt;native program_hw_devices executed once')
    save(OUT/'program_result.json',result,True);return dict(status=result['status'])


if __name__ == '__main__':
    require(len(sys.argv) == 3 and sys.argv[2] in {'2','3','4','5'} and sys.argv[1] in {'prepared', 'verify', 'claim_synth', 'synth_gate', 'claim_implementation', 'rebound_gate', 'fresh_gate', 'export_inputs', 'platform_admission', 'claim_export', 'export_result', 'claim_load', 'record_program'}, 'Unknown stage/build index')
    print(json.dumps(globals()[sys.argv[1]]()))
