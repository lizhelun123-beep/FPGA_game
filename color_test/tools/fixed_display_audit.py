"""Fail-closed receipts for the single canonical 720p display candidate.

No Vivado, device, PYNQ, allocator or loader is invoked by this module.
claim/generated/gate/export are called explicitly by the canonical build entry.
A routed structural review is evidence-bearing, hash-bound and cannot waive
negative timing, Critical CDC, DRC errors or an unknown report format.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/build/game_app/single_image_720p'
BD = ROOT / 'color_test/color_test.srcs/sources_1/bd/system/system.bd'
LEDGER = BASE / 'package_ledger.json'
PREP = BASE / 'fixed_entry_1/preparation.json'
STATE_REPORTS = tuple(f'{state}_{suffix}' for state in ('startup', 'runtime') for suffix in
                      ('timing.rpt', 'clock_interaction.rpt', 'bus_skew.rpt', 'drc.rpt',
                       'cdc.rpt', 'methodology.rpt', 'exceptions.rpt',
                       'ignored_exceptions.rpt', 'lock_exception.rpt', 'clock_identity.tsv'))
REPORTS = ('timing.rpt', 'clock_interaction.rpt', 'clocks.rpt', 'exceptions.rpt',
           'cdc.rpt', 'drc.rpt', 'methodology.rpt', 'bus_skew.rpt',
           'utilization.rpt', 'io.rpt', 'compile_order.rpt', 'compile_sources.tsv', 'structure.tsv',
           'connections.tsv', 'clocks.tsv', 'pins.tsv', 'mode_slack.tsv', 'timing_context.xdc') + STATE_REPORTS
REVIEW_CHECKS = ('netlist_source_and_partition', 'reset_domains_and_initialization',
                 'ram_control', 'cdc_noncritical', 'exceptions_and_io_scope',
                 'bus_skew_applicability', 'methodology_and_drc_warnings')
KEEP = {'processing_system7_0', 'axi_vdma_0', 'axi_dynclk_0', 'axi_mem_intercon',
        'ps7_0_axi_periph', 'rst_100M', 'proc_sys_reset_150M',
        'v_axi4s_vid_out_0', 'vtg', 'rgb2dvi_0', 'xlconcat_0',
        'display_irq_zero', 'display_rst_axis', 'display_rst_pixel'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_files():
    files = [ROOT / 'color_test/color_test.xpr', BD]
    for name, cell in load(BD)['design']['components'].items():
        if name in KEEP:
            files.append(BD.parent / cell['xci_path'].replace('\\', '/'))
    for name in ('build_bitstream.tcl', 'fixed_display.tcl', 'fixed_display_audit.py'):
        files.append(ROOT / 'color_test/tools' / name)
    for name in ('display720.xdc', 'hdmi_out.xdc'):
        files.append(ROOT / 'color_test/color_test.srcs/constrs_1/new' / name)
    ns = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    for folder in ('axi_dynclk_v1_0', 'rgb2dvi_v1_3'):
        base = ROOT / 'color_test/repo/ip' / folder
        files.append(base / 'component.xml')
        for f in ET.parse(base / 'component.xml').findall('.//s:file/s:name', ns):
            files.append(base / f.text)
    sw = ROOT / 'color_test/software/vision_ps_baremetal'
    files += [sw / 'src/game_linux_display.c', sw / 'src/game_linux_display.h',
              sw / 'tests/test_game_linux_display.c', sw / 'tools/game_display_qualify.py',
              sw / 'tools/game_linux_static_menu.c']
    files += list((sw / 'src').glob('*.h'))
    command = BASE / 'fixed_entry_1/arm_command.json'
    if command.exists():
        files += [Path(arg) for arg in load(command) if arg.endswith('.c')]
        files += [command, BASE / 'fixed_entry_1/display.arm.elf']
    files += [ROOT / 'color_test/sim' / name for name in
              ('tb_display_clock_guard.vhd', 'tb_display_reset_contract.vhd',
               'tb_axi_dynclk_startup.vhd', 'tb_display_ram_contract.sv',
               'test_fixed_display_entry.py')]
    return sorted(set(files))


def hashes(files):
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}


def unchanged(record):
    for name, digest in record.items():
        require(sha(ROOT / name) == digest, f'Input changed: {name}')


def next_build_attempt(quota):
    require(all(type(quota.get(k)) is int and quota[k] >= 0 for k in ('used', 'limit')), 'Unknown fixed-build quota')
    require(quota['used'] < quota['limit'], 'Fixed build quota exhausted; explicit added authorization required')
    return quota['used'] + 1


def claim(out):
    require(out.parent == BASE and not out.exists(), 'New direct child of the existing package directory required')
    ledger = load(LEDGER)
    quota = ledger['budget']['fixed_build']
    attempt = next_build_attempt(quota)
    relative_prep = Path(ledger.get('active_preparation', 'fixed_entry_1/preparation.json'))
    require(not relative_prep.is_absolute() and '..' not in relative_prep.parts, 'Unsafe preparation receipt path')
    prep = load(BASE / relative_prep)
    require(prep['status'] == 'PASS_OFFLINE_PREPARATION', 'Offline preparation not passed')
    unchanged(prep['source_sha256'])
    for name, digest in prep['evidence_sha256'].items():
        require(sha(BASE / name) == digest, f'Preparation evidence changed: {name}')
    for name, digest in prep['tool_model_sha256'].items():
        require(sha(name) == digest, f'Installed reset/tool model changed: {name}')
    # An explicitly added limit may fund a later attempt; used is never reset.
    # Each immutable claim survives, including the original failed attempt.
    marker = BASE / ('fixed_build.claim' if attempt == 1 else f'fixed_build_{attempt}.claim')
    with marker.open('x', encoding='utf-8') as f:
        f.write(str(out) + '\n')
    out.mkdir()
    save(out / 'input_sha256.json', prep['source_sha256'])
    save(out / 'ledger_before.json', ledger)
    if 'fixed_build_claim' in ledger:
        history = ledger.setdefault('fixed_build_claim_history', [])
        if ledger['fixed_build_claim'] not in history:
            history.append(ledger['fixed_build_claim'])
    quota['used'] = attempt
    ledger['fixed_build_claim'] = {'out': out.relative_to(ROOT).as_posix(), 'attempt': attempt,
                                  'claim_file': marker.name, 'status': 'CLAIMED_BEFORE_VIVADO_MUTATION'}
    save(LEDGER, ledger)
    snapshot(out)


def snapshot(out):
    for p in source_files():
        dst = out / 'before' / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
    # reset_run may remove old evidence: retain reports/checkpoints/artifacts,
    # including OOC runs, before touching the one canonical project.
    for folder in (ROOT / 'color_test/color_test.runs', ROOT / 'color_test/reports'):
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix.lower() in {'.rpt', '.log', '.dcp', '.bit', '.ltx'}:
                dst = out / 'before' / p.relative_to(ROOT)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dst)
    for p in BD.parent.rglob('system.hwh'):
        dst = out / 'before' / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)
    for folder in (BD.parent, ROOT / 'color_test/color_test.gen/sources_1/bd/system/ipshared'):
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix.lower() in {'.bd', '.v', '.vhd', '.xdc', '.xci', '.xml'}:
                dst = out / 'before' / p.relative_to(ROOT)
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)


def prepare(out):
    next_build_attempt(load(LEDGER)['budget']['fixed_build'])
    if out.exists():
        require((out / 'input_before_preparation.json').exists() and
                not (out / 'preparation.json').exists() and not (out / 'synthesis.claim').exists(),
                'Cannot repeat a completed preparation or claimed synthesis')
        # Explicit same-package script correction; the original snapshot stays.
        return
    out.mkdir()
    save(out / 'ledger_before_preparation.json', load(LEDGER))
    save(out / 'input_before_preparation.json', hashes(source_files()))
    snapshot(out)
    before = out / 'before'
    save(out / 'before_snapshot_sha256.json',
         {p.relative_to(before).as_posix(): sha(p) for p in before.rglob('*') if p.is_file()})


def check_compile_sources(out):
    paths = [Path(n) for n in (out / 'compile_sources.tsv').read_text().splitlines()]
    require(paths and all(p.is_file() for p in paths), 'Compile source missing')
    require(not any(p.suffix.lower() == '.dcp' for p in paths), 'Active compile graph imports a checkpoint')
    for name in ('display_clock_guard.vhd', 'axi_dynclk.vhd', 'rgb2dvi.vhd'):
        compiled = [p for p in paths if p.name == name]
        canonical = [p for p in source_files() if p.name == name]
        require(len(compiled) == len(canonical) == 1 and sha(compiled[0]) == sha(canonical[0]),
                'Compiled source identity: ' + name)
    return paths


def prepared(out):
    generated(out)
    paths = check_compile_sources(out)
    properties = dict(line.split('\t', 1) for line in (out / 'prelaunch.tsv').read_text().splitlines())
    expected = {'part': 'xc7z020clg400-2', 'top': 'system_wrapper', 'auto_incremental': '0',
                'incremental_checkpoint': '', 'bd_checkpoint': 'None', 'cache_calls': '2',
                'enabled_user_xdc': 'display720.xdc,hdmi_out.xdc'}
    require(all(properties.get(k) == v for k, v in expected.items()), 'Prelaunch property mismatch')
    model = load(BASE / 'offline_repair_1/preparation.json')['tool_model_sha256']
    for name, digest in model.items():
        require(sha(name) == digest, 'Installed tool model changed: ' + name)
    evidence = ['prelaunch.tsv', 'compile_sources.tsv', 'compile_order.rpt', 'ip_status.rpt',
                'command_help.rpt', 'generated_sha256.json']
    record = {'status': 'PASS_FULL_PRELAUNCH', 'source_sha256': hashes(source_files()),
              'compiled_sha256': {str(p): sha(p) for p in paths},
              'evidence_sha256': {n: sha(out / n) for n in evidence}, 'tool_model_sha256': model,
              'scope': 'entire shared non-synthesis preparation;no launch_runs'}
    save(out / 'preparation.json', record)
    ledger = load(LEDGER)
    ledger['active_preparation'] = (out.relative_to(BASE) / 'preparation.json').as_posix()
    save(LEDGER, ledger)


def verify_prepared(out):
    prep = load(out / 'preparation.json')
    require(prep['status'] == 'PASS_FULL_PRELAUNCH', 'Full preparation not accepted')
    unchanged(prep['source_sha256'])
    for group in ('compiled_sha256', 'tool_model_sha256'):
        for name, digest in prep[group].items():
            require(sha(name) == digest, 'Prepared dependency changed: ' + name)
    for name, digest in prep['evidence_sha256'].items():
        require(sha(out / name) == digest, 'Prepared evidence changed: ' + name)


def claim_prepared(out):
    verify_prepared(out)
    ledger = load(LEDGER)
    attempt = next_build_attempt(ledger['budget']['fixed_build'])
    with (BASE / f'fixed_build_{attempt}.claim').open('x', encoding='utf-8') as f:
        f.write(str(out) + '\n')
    save(out / 'ledger_before_build.json', ledger)
    ledger.setdefault('fixed_build_claim_history', []).append(ledger['fixed_build_claim'])
    ledger['budget']['fixed_build']['used'] = attempt
    ledger['fixed_build_claim'] = {'out': out.relative_to(ROOT).as_posix(), 'attempt': attempt,
                                  'claim_file': f'fixed_build_{attempt}.claim',
                                  'status': 'CLAIMED_AFTER_FULL_PREPARATION_BEFORE_SYNTHESIS'}
    ledger[f'fixed_build_{attempt}_stages']['synthesis']['used'] = 1
    save(LEDGER, ledger)
    with (out / 'synthesis.claim').open('x', encoding='utf-8') as f:
        f.write(str(attempt) + '\n')


def synth_gate(out):
    require((out / 'synthesis.claim').is_file(), 'No synthesis claim')
    stage = out / 'synth'
    files = ('synthesized.dcp', 'cdc.rpt', 'structure.tsv', 'connections.tsv',
             'compile_order.rpt', 'compile_sources.tsv', 'netlist_cells.tsv', 'drc.rpt', 'clocks.tsv',
             'methodology.rpt', 'mode_slack.tsv', 'timing_context.xdc') + STATE_REPORTS
    require(all((stage / n).is_file() and (stage / n).stat().st_size for n in files), 'Missing synthesis evidence')
    cdc_metrics((stage / 'cdc.rpt').read_text())
    synth_drc((stage / 'drc.rpt').read_text())
    drc_metrics((stage / 'methodology.rpt').read_text(), 'methodology')
    clock_manifest((stage / 'clocks.tsv').read_text())
    state_evidence(stage, routed=False)
    mode_rows = [line.split('\t') for line in (stage / 'mode_slack.tsv').read_text().splitlines()]
    require(len(mode_rows) == 8 and all(len(row) == 4 and math.isfinite(float(row[3])) for row in mode_rows) and {tuple(row[:3]) for row in mode_rows} ==
            {(s, d, t) for s in ('startup', 'runtime') for d in ('from', 'to') for t in ('max', 'min')},
            'Incomplete synthesis clock-state coverage')
    check_compile_sources(stage)
    bound = {n: sha(stage / n) for n in files}
    require((out / 'synth_review.json').exists(), 'SYNTH_REVIEW_REQUIRED;no implementation launched')
    review = load(out / 'synth_review.json')
    require(review['report_sha256'] == bound, 'Stale synthesis review')
    for name in ('netlist_source_and_partition', 'reset_domains_and_initialization', 'ram_control', 'cdc_noncritical'):
        item = review['checks'][name]
        require(item['pass'] is True and len(item['evidence']) >= 24, 'Synthesis review missing: ' + name)
    save(out / 'synth_gate.json', {'status': 'PASS_SYNTH_STRUCTURE_CDC', 'report_sha256': bound,
                                  'review_sha256': sha(out / 'synth_review.json')})


def implementation_inputs(out):
    """Bind an implementation-only run to the audited DCP and unchanged HDL."""
    item = load(out / 'implementation_input.json')
    authority = load(out / 'implementation_1/authorization.json')
    require(item.get('scope') == 'IMPLEMENTATION_ONLY_NO_EXPORT' and
            item.get('export_authorized') is False, 'Wrong implementation scope')
    baseline = load(out / 'source_after_refresh.json')
    require(sha(out / 'source_after_refresh.json') == authority['frozen_source_manifest_sha256'],
            'Frozen source baseline changed')
    expected = set(baseline) - {'color_test/color_test.xpr'}
    require(set(item['source_sha256']) == expected, 'Incomplete implementation source binding')
    tool_edits = {'color_test/tools/fixed_display.tcl', 'color_test/tools/fixed_display_audit.py',
                  'color_test/sim/test_fixed_display_entry.py'}
    require(all(item['source_sha256'][n] == baseline[n] for n in expected - tool_edits),
            'Hardware/configuration changed since synthesis')
    unchanged(item['source_sha256'])
    # XPR run-state metadata is mutable; the actual P&R input is this exact DCP.
    require(sha(out / 'synth/synthesized.dcp') == item['checkpoint_sha256'] ==
            authority['frozen_checkpoint_sha256'] ==
            load(out / 'synth_gate.json')['report_sha256']['synthesized.dcp'],
            'Implementation checkpoint identity changed')
    manifest = out / 'compiled_source_snapshot.json'
    require(sha(manifest) == authority['compiled_source_manifest_sha256'], 'Compiled manifest changed')
    for name, record in load(manifest).items():
        require(sha(name) == record['sha256'] == sha(out / record['snapshot']),
                'Frozen compiled source changed: ' + name)
    export_artifact_policy(out)
    return item


def export_artifact_policy(out):
    # The original implementation-only boundary stays closed until a separate,
    # identity-bound export claim has actually been consumed.
    if any((out / n).exists() for n in ('system_wrapper.bit', 'system.hwh', 'system.xsa')):
        export_inputs(out, consumed=True)


def export_inputs(out, consumed=False):
    ledger = load(LEDGER)
    claim = ledger['fixed_build_claim']
    require(claim['out'] == out.relative_to(ROOT).as_posix(), 'Wrong export build')
    quota = ledger[f"fixed_build_{claim['attempt']}_stages"].get('export')
    require(quota == {'limit': 1, 'used': int(consumed)}, 'Export not authorized or quota exhausted')
    grant = load(out / 'export_1/authorization.json')
    require(grant['limits'] == {'BIT_generation': 1, 'new_synthesis': 0,
                               'new_implementation': 0, 'board': 0}, 'Wrong export limits')
    for name, key in (('routed.dcp', 'routed_DCP_sha256'),
                      ('synth/synthesized.dcp', 'synthesized_DCP_sha256'),
                      ('routed_review.json', 'routed_review_sha256')):
        require(sha(out / name) == grant[key], 'Export frozen identity changed: ' + name)
    marker = out / 'export.claim'
    if consumed:
        require(marker.is_file() and marker.read_text(encoding='utf-8').strip() == str(claim['attempt']),
                'No matching consumed export claim')
    else:
        require(not marker.exists(), 'Export already claimed')
    receipt = load(out / 'export_1/metadata.json')
    require(receipt['status'] == 'PASS_DCP_EMBEDDED_METADATA_NO_BIT' and
            receipt['routed_DCP_sha256'] == grant['routed_DCP_sha256'], 'Wrong metadata context')
    probe = out / 'export_1/metadata_probe.xsa'
    require(sha(probe) == receipt['probe_XSA_sha256'], 'Metadata probe changed')
    canonical = BD.parent / 'hw_handoff/system.hwh'
    require(sha(canonical) == receipt['HWH_sha256'] ==
            load(out / 'generated_sha256.json')[canonical.relative_to(ROOT).as_posix()],
            'Canonical HWH changed since generation')
    with zipfile.ZipFile(probe) as archive:
        names = archive.namelist()
        hw = [n for n in names if n.endswith('.hwh')]
        require(len(hw) == 1 and len(set(names)) == len(names) and
                not any(n.endswith('.bit') for n in names), 'Invalid metadata-only probe')
        require(archive.read(hw[0]) == canonical.read_bytes(), 'DCP/canonical metadata mismatch')
    hwh = ET.parse(canonical).getroot()
    require(hwh.get('VIVADOVERSION') == '2023.1' and
            hwh.find('SYSTEMINFO').attrib == {'ARCH': 'zynq', 'DEVICE': '7z020', 'NAME': 'system',
                                            'PACKAGE': 'clg400', 'SPEEDGRADE': '-2'}, 'Wrong HWH device/version')
    require({m.get('INSTANCE') for m in hwh.findall('.//MODULE')} == KEEP, 'Wrong HWH partition')
    validate_partition(load(BD)['design'])
    # Content-only host check; Linux root ownership/protection is NOT claimed.
    path = ROOT / 'color_test/software/vision_ps_baremetal/tools/game_display_qualify.py'
    spec = importlib.util.spec_from_file_location('display_export_contract', path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    contract.verify_reset_contract({'display_reset_contract': 'guard1_dual_psr13_aux16',
                                   'dynclk_status_mask': 3},
                                  {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')})
    ranges = {n.get('INSTANCE'): (int(n.get('BASEVALUE'), 0), int(n.get('HIGHVALUE'), 0))
              for n in hwh.findall('.//MEMRANGE')}
    for cell, address in (('axi_dynclk_0', 0x43c00000), ('vtg', 0x43c10000), ('axi_vdma_0', 0x43010000)):
        require(ranges[cell] == (address, address + 0xffff), 'Wrong HWH address: ' + cell)


def claim_implementation(out):
    implementation_inputs(out)
    synth_gate(out)
    ledger = load(LEDGER)
    attempt = ledger['fixed_build_claim']['attempt']
    require(ledger['fixed_build_claim']['out'] == out.relative_to(ROOT).as_posix(), 'Wrong current build')
    quota = ledger[f'fixed_build_{attempt}_stages']['implementation']
    require(quota == {'limit': 1, 'used': 0}, 'Implementation quota exhausted')
    with (out / 'implementation.claim').open('x', encoding='utf-8') as f:
        f.write(str(attempt) + '\n')
    quota['used'] = 1
    save(LEDGER, ledger)


def implementation_report_inputs(out):
    implementation_inputs(out)
    require((out / 'implementation.claim').is_file(), 'No consumed implementation claim')
    record = load(out / 'implementation_1/route_checkpoint.json')
    require(sha(out / 'routed.dcp') == record['sha256'], 'Routed checkpoint changed')


def claim_export(out):
    ledger = load(LEDGER)
    claim = ledger['fixed_build_claim']
    require(claim['out'] == out.relative_to(ROOT).as_posix(), 'Wrong export build')
    quota = ledger[f"fixed_build_{claim['attempt']}_stages"].get('export')
    require(quota == {'limit': 1, 'used': 0}, 'Export not authorized or quota exhausted')
    export_inputs(out)
    gate(out)
    with (out / 'export.claim').open('x', encoding='utf-8') as f:
        f.write(str(claim['attempt']) + '\n')
    quota['used'] = 1
    save(LEDGER, ledger)


def validate_partition(d):
    require(set(d['components']) == KEEP, 'Actual BD partition differs from frozen candidate')
    require(not any('dphy' in n.lower() for k in ('ports', 'interface_ports') for n in d.get(k, {})), 'D-PHY external interface remains')
    segs = d['addressing']['/processing_system7_0']['address_spaces']['Data']['segments']
    require(len(segs) == 3, 'Expected exactly three CPU address segments')
    for cell, address in (('axi_dynclk_0', 0x43c00000), ('vtg', 0x43c10000), ('axi_vdma_0', 0x43010000)):
        s = [v for v in segs.values() if v['address_block'].startswith('/' + cell + '/')]
        require(len(s) == 1 and int(s[0]['offset'], 0) == address and s[0]['range'] == '64K', f'Address ABI: {cell}')


def generated(out):
    d = load(BD)['design']
    validate_partition(d)
    # Same pure XML contract as the Linux preflight; importing this module has
    # only stdlib definitions, no device/PYNQ/allocator side effects.
    path = ROOT / 'color_test/software/vision_ps_baremetal/tools/game_display_qualify.py'
    spec = importlib.util.spec_from_file_location('display_metadata_contract', path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    hwh = ET.parse(BD.parent / 'hw_handoff/system.hwh').getroot()
    modules = {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')}
    contract.verify_reset_contract({'display_reset_contract': 'guard1_dual_psr13_aux16', 'dynclk_status_mask': 3}, modules)
    save(out / 'generated_sha256.json', hashes(source_files() + [BD.parent / 'hw_handoff/system.hwh']))


def timing_metrics(text):
    require('Design Timing Summary' in text and 'WNS(ns)' in text, 'Unknown timing summary')
    tail = text.split('WNS(ns)', 1)[1]
    number = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)'
    rows = [line.split() for line in tail.splitlines()
            if re.fullmatch(r'\s*' + number + r'(?:\s+' + number + r'){11}\s*', line)]
    require(len(rows) == 1, 'Missing/ambiguous twelve-field setup/hold/pulse summary')
    values = [float(v) for v in rows[0]]
    require(not re.search(r'\bVIOLATED\b', text), 'Detailed/default-group timing violation')
    require(all(math.isfinite(v) and v >= 0 for v in values), f'Negative/unknown timing: {values}')
    require(all(values[i] == 0 for i in (1, 2, 5, 6, 9, 10)), 'Timing violations/endpoints present')
    counts = dict(re.findall(r'\d+\. checking ([a-z_]+) \((\d+)\)', text))
    expected = {'no_clock', 'constant_clock', 'pulse_width_clock', 'unconstrained_internal_endpoints',
                'no_input_delay', 'no_output_delay', 'multiple_clock', 'generated_clocks',
                'loops', 'partial_input_delay', 'partial_output_delay', 'latch_loops'}
    require(set(counts) == expected, 'Unknown/incomplete check_timing inventory')
    # no_input/no_output are never silently waived. Exact ports and justification
    # must be reviewed against the hash-bound report, without invented zero delays.
    require(all(int(v) == 0 for k, v in counts.items() if k not in {'no_input_delay', 'no_output_delay'}), 'Clock/internal/unexpected timing coverage failure')
    return dict(zip(('WNS', 'TNS', 'setup_fail', 'setup_total', 'WHS', 'THS', 'hold_fail', 'hold_total', 'WPWS', 'TPWS', 'pulse_fail', 'pulse_total'), values))


def cdc_metrics(text):
    require('CDC Report' in text and 'Severity' in text, 'Unknown CDC report')
    summary = text.split('Source Clock:', 1)[0]
    rows = re.findall(r'^CDC-\d+\s+(Critical|Warning|Info)\s+(\d+)\s+.+$', summary, re.M)
    require(len(re.findall(r'^CDC-\d+\s+', summary, re.M)) == len(rows), 'Unknown CDC summary row')
    require(rows or re.search(r'No CDC (?:paths|violations|issues)', text, re.I), 'Missing CDC inventory')
    require(not any(sev == 'Critical' and int(n) for sev, n in rows), 'Critical CDC present')
    return rows


def drc_inventory(text, label):
    require('report_' + label in text.lower(), f'Unknown {label} command identity')
    counts = re.findall(r'Violations found:\s*(\d+)', text)
    require(len(counts) == 1, f'Unknown {label} violation count')
    rows = re.findall(r'^\|\s*([\w-]+)\s*\|\s*(Error|Critical Warning|Warning|Advisory|Info)\s*\|.*?\|\s*(\d+)\s*\|', text, re.M)
    require(sum(int(n) for _, _, n in rows) == int(counts[0]), f'Incomplete {label} summary')
    return rows


def drc_metrics(text, label):
    rows = drc_inventory(text, label)
    require(not any(sev in {'Error', 'Critical Warning'} and int(n) for _, sev, n in rows), f'{label} error/critical warning')
    return rows


def synth_drc(text):
    # Full raw report is retained, including physical checks that cannot pass
    # before placement/routing. They remain mandatory in the routed gate.
    rows = drc_inventory(text, 'drc')
    pending = {'RTSTAT-12', 'UNPL-1'}
    require(not any(sev in {'Error', 'Critical Warning'} and int(n) and rule not in pending
                    for rule, sev, n in rows), 'Synthesis structural DRC error')
    return {'physical_pending': [r for r in rows if r[0] in pending],
            'structural_inventory': [r for r in rows if r[0] not in pending]}


def utilization(text):
    result = {}
    for line in text.splitlines():
        columns = [x.strip() for x in line.split('|')[1:-1]]
        if len(columns) == 6:
            try:
                result[columns[0].rstrip('*')] = float(columns[-1])
            except ValueError:
                pass
    for name in ('Slice LUTs', 'Slice Registers', 'Slice', 'Block RAM Tile', 'DSPs', 'Bonded IOB', 'BUFGCTRL', 'BUFIO', 'BUFR', 'MMCME2_ADV'):
        require(name in result, f'Resource row missing: {name}')
        require(math.isfinite(result[name]) and 0 <= result[name] < (75 if name == 'Slice' else 70), f'Resource budget: {name}')
    return result


def bus_skew(text, applicable):
    require('report_bus_skew' in text, 'Unknown bus-skew report')
    require(not re.search(r'VIOLATED|ERROR:', text, re.I), 'Bus-skew failure')
    slacks = re.findall(r'Slack\s*\((?:MET|VIOLATED)\)\s*:\s*([-+\d.]+)\s*ns', text)
    if applicable:
        require(slacks and all(math.isfinite(float(v)) and float(v) >= 0 for v in slacks), 'Missing/negative applicable bus-skew slack')
    else:
        require(not slacks and re.search(r'No (?:bus skew constraints|bus skew paths|paths) (?:found|to report)', text, re.I), 'Unknown zero-applicable bus-skew format')


def clock_manifest(text):
    expected = {'clk_fpga_0': 10, 'clk_fpga_1': 7, 'hdmi_serial_startup': 2,
                'hdmi_pixel_startup': 10, 'hdmi_serial_runtime': 35/13, 'hdmi_pixel_runtime': 175/13}
    lines = text.splitlines()
    clocks = dict(line.split('\t') for line in lines)
    require(len(lines) == len(expected) and set(clocks) == set(expected) and
            all(math.isfinite(float(clocks[k])) and abs(float(clocks[k])-v) < .002 for k,v in expected.items()),
            'Clock identity/period mismatch')


def native_clock_identity(text, state):
    rows = [line.split('\t') for line in text.splitlines()]
    require(len(rows) == 2 and all(len(row) == 5 for row in rows) and
            {row[0] for row in rows} == {'serial', 'pixel'}, 'Incomplete native clock identities')
    clocks = {row[0]: row[1:] for row in rows}
    serial_period = {'startup': 2, 'runtime': 35/13}[state]
    for role, factor, duty in (('serial', 1, .5), ('pixel', 5, .4)):
        name, period, waveform, master = clocks[role]
        period = float(period)
        wave = [float(value) for value in waveform.split()]
        require(name and math.isfinite(period) and abs(period - serial_period * factor) < .002 and
                len(wave) == 2 and all(math.isfinite(value) for value in wave) and
                abs(wave[0]) < .002 and abs(wave[1] - duty * period) < .002,
                f'Wrong native {state} {role} waveform')
        require(master == ('clk_fpga_0' if role == 'serial' else clocks['serial'][0]),
                f'Broken native {state} {role} propagation')


def state_evidence(out, routed):
    require(all((out / name).is_file() and (out / name).stat().st_size for name in STATE_REPORTS),
            'Missing complete two-state evidence')
    context = (out / 'timing_context.xdc').read_text()
    require(not re.search(r'create_generated_clock[^\n]*(?:axi_dynclk|hdmi_)', context),
            'Manual HDMI clock override')
    require(not re.search(r'set_false_path[^\n]*DisplayGuard', context),
            'Lock bridge/local READY reset hidden by exception')
    for state in ('startup', 'runtime'):
        native_clock_identity((out / f'{state}_clock_identity.tsv').read_text(), state)
        cdc_metrics((out / f'{state}_cdc.rpt').read_text())
        drc_metrics((out / f'{state}_methodology.rpt').read_text(), 'methodology')
        drc_text = (out / f'{state}_drc.rpt').read_text()
        (drc_metrics(drc_text, 'drc') if routed else synth_drc(drc_text))
        if routed:
            timing_metrics((out / f'{state}_timing.rpt').read_text())
        # Applicability remains explicit in the manual, hash-bound review.
        # Synthesis keeps physical budgets pending; routed signoff is strict.
        skew = (out / f'{state}_bus_skew.rpt').read_text()
        if routed:
            bus_skew(skew, applicable='No bus skew constraints found' not in skew)
        else:
            require('report_bus_skew' in skew and
                    ('No bus skew constraints found' in skew or
                     re.search(r'Slack\s*\((?:MET|VIOLATED)\)\s*:\s*[+-]?[\d.]+\s*ns', skew)),
                    'Missing/unknown synthesis bus-skew report')


def report_identity(out, name, text):
    if name == 'compile_order.rpt' and (out / 'implementation_input.json').exists():
        # report_compile_order has no version/top banner. It is frozen synthesis
        # provenance, not a newly generated physical report from the routed DCP.
        digest = sha(out / name)
        require(digest == sha(out / 'synth' / name) ==
                load(out / 'synth_gate.json')['report_sha256'][name],
                'Frozen compile-order provenance changed')
    elif name.endswith('.rpt'):
        require('Vivado v.2023.1' in text and 'system_wrapper' in text,
                f'Report version/top identity: {name}')


def gate(out):
    ledger = load(LEDGER)
    claim_record = ledger.get('fixed_build_claim', {})
    require(ledger['budget']['fixed_build']['used'] >= 1 and
            claim_record.get('attempt', 1) == ledger['budget']['fixed_build']['used'] and
            claim_record.get('out') == out.relative_to(ROOT).as_posix(),
            'No matching fixed-build claim; cannot qualify old or unbuilt artifacts')
    marker = claim_record.get('claim_file', 'fixed_build.claim')
    require(Path(marker).name == marker, 'Unsafe claim file')
    require((BASE / marker).read_text(encoding='utf-8').strip() == str(out), 'Build claim identity changed')
    if (out / 'implementation_input.json').exists():
        implementation_inputs(out)
    else:
        unchanged(load(out / 'generated_sha256.json'))
    texts = {}
    for name in REPORTS:
        p = out / name
        require(p.is_file() and p.stat().st_size > 0, f'Missing/empty report: {name}')
        texts[name] = p.read_text(encoding='utf-8', errors='strict')
        report_identity(out, name, texts[name])
    require((out / 'routed.dcp').is_file(), 'Missing same-run routed checkpoint')
    metrics = timing_metrics(texts['timing.rpt'])
    cdc_metrics(texts['cdc.rpt'])
    drc_metrics(texts['drc.rpt'], 'drc')
    drc_metrics(texts['methodology.rpt'], 'methodology')
    utilization(texts['utilization.rpt'])
    rows = [line.split('\t') for line in texts['mode_slack.tsv'].splitlines()]
    require({tuple(row[:3]) for row in rows} == {(s, d, t) for s in ('startup', 'runtime') for d in ('from', 'to') for t in ('max', 'min')} and len(rows) == 8, 'Incomplete two-state path coverage')
    require(all(len(r) == 4 and math.isfinite(float(r[3])) and float(r[3]) >= 0 for r in rows), 'Negative/unknown per-state slack')
    clock_manifest(texts['clocks.tsv'])
    state_evidence(out, routed=True)
    report_hashes = {name: sha(out / name) for name in (*REPORTS, 'routed.dcp')}
    review_path = out / 'routed_review.json'
    require(review_path.exists(), 'ROUTED_REVIEW_REQUIRED: inspect actual connections/RAM/init/CDC warnings/IO/skew; no BIT generated')
    review = load(review_path)
    require(review['report_sha256'] == report_hashes, 'Stale/incomplete routed review')
    for name in REVIEW_CHECKS:
        item = review['checks'][name]
        require(item['pass'] is True and len(item['evidence']) >= 24, f'Missing structural evidence: {name}')
    require(type(review['bus_skew_applicable']) is bool, 'Unknown bus-skew applicability')
    bus_skew(texts['bus_skew.rpt'], review['bus_skew_applicable'])
    # Compilation identity must name the newly generated canonical IP sources.
    for file in ('display_clock_guard.vhd', 'axi_dynclk.vhd', 'rgb2dvi.vhd'):
        require(file in texts['compile_order.rpt'], f'Actual compile source absent: {file}')
        compiled = [Path(line) for line in texts['compile_sources.tsv'].splitlines() if Path(line).name == file]
        canonical = [p for p in source_files() if p.name == file]
        require(len(compiled) == len(canonical) == 1 and sha(compiled[0]) == sha(canonical[0]), f'Compiled HDL differs from canonical: {file}')
    result = {'status': 'PASS_PRE_BIT', 'metrics': metrics, 'report_sha256': report_hashes,
              'review_sha256': sha(review_path), 'generated_sha256': sha(out / 'generated_sha256.json')}
    save(out / 'gate.json', result)
    return result


def bit_identity(data):
    """Parse a Xilinx BIT container, retaining the exact configuration identity."""
    position = 0

    def take(size):
        nonlocal position
        require(size >= 0 and position + size <= len(data), 'Truncated BIT container')
        result = data[position:position + size]
        position += size
        return result

    def number(size):
        return int.from_bytes(take(size), 'big')

    require(take(number(2)) == bytes.fromhex('0ff00ff00ff00ff000') and number(2) == 1,
            'Invalid BIT container magic')
    fields = {}
    for tag in (b'a', b'b', b'c', b'd'):
        require(take(1) == tag, 'Invalid BIT header sequence')
        fields[tag.decode()] = take(number(2)).rstrip(b'\0').decode('ascii')
    require(take(1) == b'e', 'Missing BIT configuration payload')
    payload = take(number(4))
    require(position == len(data) and payload, 'Trailing/empty BIT configuration')
    require(fields['a'] == 'system_wrapper;COMPRESS=TRUE;UserID=0XFFFFFFFF;Version=2023.1' and
            fields['b'] == '7z020clg400', 'Wrong BIT design/device/version')
    return {'fields': fields, 'payload_bytes': len(payload),
            'payload_sha256': hashlib.sha256(payload).hexdigest()}


def extract_export(out):
    """Pair existing XSA payloads offline; never invoke Vivado or regenerate BIT."""
    export_inputs(out, consumed=True)
    with zipfile.ZipFile(out / 'system.xsa') as archive:
        names = archive.namelist()
        bits = [n for n in names if n.endswith('.bit')]
        hw = [n for n in names if n.endswith('.hwh')]
        require(len(bits) == len(hw) == 1 and len(set(names)) == len(names), 'Ambiguous XSA payloads')
        bit, hwh = archive.read(bits[0]), archive.read(hw[0])
    identity = bit_identity(bit)
    require(hwh == (BD.parent / 'hw_handoff/system.hwh').read_bytes(), 'XSA/canonical HWH mismatch')
    for name, data in (('system_wrapper.bit', bit), ('system.hwh', hwh)):
        path = out / name
        if path.exists() and path.read_bytes() != data:
            # Bounded repair of the initial packaging error only. Hardware
            # identity differences are fatal; preserve the original BIT first.
            require(name.endswith('.bit'), 'Existing HWH mismatch')
            old = bit_identity(path.read_bytes())
            require(old['payload_sha256'] == identity['payload_sha256'] and
                    old['payload_bytes'] == identity['payload_bytes'] and
                    {k: v for k, v in old['fields'].items() if k != 'd'} ==
                    {k: v for k, v in identity['fields'].items() if k != 'd'},
                    'Existing BIT configuration/header mismatch; stop')
            backup = out / 'export_1/initial_system_wrapper.bit'
            with backup.open('xb') as stream:
                stream.write(path.read_bytes())
        path.write_bytes(data)


def export(out):
    export_inputs(out, consumed=True)
    accepted = gate(out)
    bit, hwh, xsa = (out / n for n in ('system_wrapper.bit', 'system.hwh', 'system.xsa'))
    with zipfile.ZipFile(xsa) as archive:
        bits = [n for n in archive.namelist() if n.endswith('.bit')]
        hw = [n for n in archive.namelist() if n.endswith('.hwh')]
        require(len(bits) == len(hw) == 1 and len(set(archive.namelist())) == len(archive.namelist()),
                'XSA must contain exactly one BIT/HWH without duplicate members')
        require(archive.read(bits[0]) == bit.read_bytes() and archive.read(hw[0]) == hwh.read_bytes(), 'BIT/HWH/XSA payload mismatch')
    require(hwh.read_bytes() == (BD.parent / 'hw_handoff/system.hwh').read_bytes(), 'Exported HWH is not canonical')
    identity = bit_identity(bit.read_bytes())
    save(out / 'artifacts.json', {'status': 'PAIRED_NOT_BOARD_QUALIFIED',
         'part': 'xc7z020clg400-2', 'mode': 'control_720p_only',
         'sha256': {p.name: sha(p) for p in (bit, hwh, xsa)}, 'BIT_identity': identity,
         'gate_sha256': sha(out / 'gate.json')})
    # Preserve the existing Linux qualifier's flat package ABI. This receipt
    # qualifies only file identity; it never creates a boot/owner/load receipt.
    aliases = {'display.bit': bit, 'display.hwh': hwh, 'display.xsa': xsa,
               'display.elf': BASE / 'fixed_entry_1/display.arm.elf',
               'qualify.py': ROOT / 'color_test/software/vision_ps_baremetal/tools/game_display_qualify.py',
               'timing_summary.rpt': out / 'timing.rpt'}
    for name, source in aliases.items():
        shutil.copyfile(source, out / name)
    files = {name: sha(out / name) for name in (*REPORTS, *aliases, 'gate.json', 'routed_review.json', 'artifacts.json')}
    metrics = accepted['metrics']
    save(out / 'package.json', {'part': 'xc7z020clg400-2',
         'mode': 'fixed_control_720p_M52_D7_O2', 'capture_cells': [],
         'display_reset_contract': 'guard1_dual_psr13_aux16', 'dynclk_status_mask': 3,
         'files': files, 'gate': {**metrics, 'critical_cdc': 0, 'drc_errors': 0,
         'unexplained_unconstrained': 0, 'resource_gate': True, 'pins_gate': True,
         'clock_reset_gate': True}, 'board_status': 'NOT_RUN'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('claim', 'generated', 'gate', 'export', 'prepare', 'prepared',
                                          'verify_prepared', 'claim_prepared', 'synth_gate', 'claim_implementation',
                                          'implementation_report_inputs', 'claim_export', 'export_inputs', 'extract_export'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.parent == BASE, 'Output outside canonical package')
    globals()[args.action](out)
    print(args.action.upper() + '_PASS')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, ET.ParseError, zipfile.BadZipFile) as error:
        print('STOP: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
