"""Offline review of the single fixed-rate synthesis; never launches Vivado."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'color_test/build/dphy_rate93_qualified/synth'
PACK = ROOT / ('color_test/build/dphy_observer_140/shared_reset_audit/fixture_package/'
               'fixed_implementation/mmio_contract/finite_observation/budget_probe/'
               'rate93_qualified_reset')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(value):
    # Vivado object names in this design contain no spaces or literal braces.
    return value.replace('{', '').replace('}', '').split()


def checkpoint_graph_proof():
    proof=OUT.parent/'proof'
    assert (proof/'structure_proof_completed.txt').exists()
    assert json.loads((proof/'launch_exit.json').read_text(encoding='utf-8-sig'))['exit_code']==0
    evidence={}
    for name in ('cells.tsv','nets.tsv','primitive_config.tsv'):
        signatures=[]
        for stage in ('synth','ready'):
            path=proof/stage/name
            if name=='primitive_config.tsv':
                canonical='\n'.join(sorted(path.read_text().splitlines()))
            else:
                rows=list(csv.DictReader(path.open(),delimiter='\t'))
                for row in rows:
                    if name=='cells.tsv':
                        row['clocks']=' '.join(sorted(tokens(row['clocks'])))
                    else:
                        for key in ('input_pins','output_pins','ports'):
                            row[key]=' '.join(sorted(tokens(row[key])))
                canonical=json.dumps(sorted(rows,key=lambda r:next(iter(r.values()))),sort_keys=True)
            signatures.append(hashlib.sha256(canonical.encode()).hexdigest())
            evidence[path.relative_to(ROOT).as_posix()]=sha(path)
        assert signatures[0]==signatures[1], ('Actual primitive/config/connection difference',name)
        evidence[name+'_canonical_signature']=signatures[0]
    return evidence


def main():
    attempt = json.loads((PACK / 'attempt.json').read_text())
    required = ['synthesis_started.txt', 'synthesis_completed.txt', 'reports_completed.txt',
                'repaired_synth.dcp', 'repaired_synth.v', 'effective.xdc', 'cdc.rpt',
                'utilization.rpt', 'clocks.rpt', 'clock_interaction.rpt', 'timing_synth.rpt',
                'check_timing.rpt', 'exceptions.rpt', 'drc.rpt', 'cells.tsv', 'nets.tsv',
                'focused_properties.rpt', 'tool_version.txt', 'consumed_sources.tsv',
                'console.log', 'launch_exit.json', 'ip_status.rpt', 'compile_order.rpt']
    assert all((OUT / name).is_file() and (OUT / name).stat().st_size for name in required)
    assert json.loads((OUT / 'launch_exit.json').read_text(encoding='utf-8-sig'))['exit_code'] == 0
    for p,h in attempt['synthesis_source_sha256'].items():
        actual = ROOT / p
        if p == attempt.get('synth_entry_at_execution',{}).get('path'):
            actual = ROOT / attempt['synth_entry_at_execution']['snapshot']
        assert sha(actual) == h, p
    assert all(sha(ROOT / p) == h for p, h in attempt['dependency_sha256'].items())
    assert all(sha(ROOT / p) == h for p, h in attempt['protected_sha256'].items())
    consumed = list(csv.DictReader((OUT / 'consumed_sources.tsv').open(), delimiter='\t'))
    consumed_paths = {str(Path(row['path']).relative_to(ROOT)).replace('\\', '/') for row in consumed}
    assert consumed_paths == {p for p in attempt['synthesis_source_sha256'] if p.endswith('.vhd')}
    version = (OUT / 'tool_version.txt').read_text()
    assert '2023.1' in version and '3865809' in version
    cells = {row['cell']: row for row in csv.DictReader((OUT / 'cells.tsv').open(), delimiter='\t')}
    drivers, sinks, inputs, portdrivers = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    for row in csv.DictReader((OUT / 'nets.tsv').open(), delimiter='\t'):
        ds, ss = tokens(row['output_pins']), tokens(row['input_pins'])
        for pin in ss:
            drivers[pin].update(ds)
            inputs[pin.rsplit('/', 1)[0]].add(pin)
        for pin in ds:
            sinks[pin].update(ss)
        for port in tokens(row['ports']):
            portdrivers[port].update(ds)

    def driver(pin):
        assert len(drivers[pin]) == 1, (pin, sorted(drivers[pin]))
        return next(iter(drivers[pin]))

    def starts(pin, visited=None):
        visited = set() if visited is None else visited
        if pin in visited:
            return set()
        visited.add(pin)
        result = set()
        for dp in drivers[pin]:
            cell = dp.rsplit('/', 1)[0]
            ref = cells.get(cell, {}).get('ref', 'BLACKBOX')
            if ref.startswith(('FD', 'RAM', 'ISERDES')) or ref == 'BLACKBOX':
                result.add(dp)
            elif ref not in ('GND', 'VCC'):
                for ip in inputs[cell]:
                    result.update(starts(ip, visited))
        return result

    clock = 'phy/ClockLane/HSClockingX/'
    watch = clock + 'Legacy.GenNoMMCM.WatchHeartbeat/oSyncStages_reg'
    heartbeat = clock + 'Legacy.GenNoMMCM.dByteHeartbeat_reg'
    recent = clock + 'Legacy.GenNoMMCM.cByteRecent_reg'
    shared = 'phy/ClockLane/RxClkActiveHSResetBridge/SyncAsyncx/oSyncStages_reg'
    hb_first, hb_second = watch + '[0]', watch + '[1]'
    assert cells[heartbeat]['ref'] == 'FDRE' and cells[heartbeat]['init'] == "1'b0"
    assert driver(heartbeat + '/C') == clock + 'Legacy.DivClkBuffer/O'
    assert cells[clock + 'Legacy.DivClkBuffer']['ref'] == 'BUFR'
    assert driver(hb_first + '/D') == heartbeat + '/Q'
    assert driver(hb_second + '/D') == hb_first + '/Q'
    assert sinks[hb_first + '/Q'] == {hb_second + '/D'}
    assert all(cells[x]['async_reg'] == '1' and cells[x]['clocks'] == 'clk_fpga_2'
               for x in (hb_first, hb_second))
    assert cells[recent]['ref'] == 'FDRE' and cells[recent]['init'] == "1'b0"
    assert cells[recent]['clocks'] == 'clk_fpga_2'
    assert sum('WatchHeartbeat/oSyncStages_reg[0]' in n for n in cells) == 1
    assert driver(shared + '[1]/D') == shared + '[0]/Q'
    assert sinks[shared + '[0]/Q'] == {shared + '[1]/D'}
    assert all(cells[shared + f'[{i}]']['async_reg'] == '1' and
               cells[shared + f'[{i}]']['clocks'] == 'clk_fpga_2' for i in (0, 1))
    clr = driver(shared + '[0]/CLR')
    assert driver(shared + '[1]/CLR') == clr
    clr_cell = clr.rsplit('/', 1)[0]
    shared_clear = dict(cell=clr_cell, ref=cells[clr_cell]['ref'],
                        init=cells[clr_cell]['init'],
                        inputs={pin: sorted(drivers[pin]) for pin in sorted(inputs[clr_cell])})
    raw = clock + 'Legacy.SyncAsyncLocked/oSyncStages_reg[1]'
    assert shared_clear['ref'] == 'LUT1' and shared_clear['init'] == "2'h1"
    assert driver(clr_cell + '/I0') == raw + '/Q'
    assert sinks[raw+'/Q'] == {clr_cell+'/I0'}
    assert len(portdrivers['clk_active']) == 1
    qualified = next(iter(portdrivers['clk_active'])).rsplit('/',1)[0]
    assert cells[qualified]['ref']=='LUT2' and cells[qualified]['init']=="4'h8"
    assert {driver(p) for p in inputs[qualified]} == {shared+'[1]/Q',recent+'/Q'}
    for pin in ['phy/ClockLane/SyncAsyncLocked/oSyncStages_reg[0]/D',
                'phy/DataLaneGen[0].DPHY_LaneSFEN_X/cHSReset_reg/PRE',
                'phy/DataLaneGen[1].DPHY_LaneSFEN_X/cHSReset_reg/PRE']:
        assert starts(pin) == {shared+'[1]/Q',recent+'/Q'}, (pin,sorted(starts(pin)))
    lanes = {}
    for lane in (0, 1):
        prefix = f'phy/DataLaneGen[{lane}].DPHY_LaneSFEN_X/HSDeserializerX/'
        regs = [n for n, c in cells.items() if n.startswith(prefix) and
                re.search(r'/(dDataOut8_reg\[\d+\]|dValid_reg|dSync(?:Hard|Soft|Err)_int_reg)$', n)]
        assert len(regs) == 12, regs
        rb = prefix + 'UseInternalReset.SerdesReset/SyncAsyncx/oSyncStages_reg'
        assert all(cells[rb + f'[{i}]']['ref'] == 'FDPE' and
                   cells[rb + f'[{i}]']['async_reg'] == '1' and
                   cells[rb + f'[{i}]']['init'] == "1'b1" and
                   cells[rb + f'[{i}]']['clocks'] == 'byte_clk' for i in (0, 1))
        assert driver(rb + '[1]/D') == rb + '[0]/Q'
        assert sinks[rb + '[0]/Q'] == {rb + '[1]/D'}
        for reg in regs:
            assert cells[reg]['ref'] == 'FDCE' and cells[reg]['init'] == "1'b0"
            assert cells[reg]['clocks'] == 'byte_clk'
            assert driver(reg + '/CLR') == rb + '[1]/Q'
        reset_source = driver(rb + '[0]/PRE')
        assert reset_source.endswith('/cHSReset_reg/Q'), reset_source
        lanes[str(lane)] = dict(async_cleared_ppi_ffs=len(regs), init=0,
                               clear_driver=rb + '[1]/Q', reset_source=reset_source,
                               reset_release_stages=2)
    assert not any(c['blackbox'] == '1' for c in cells.values()), 'Real FIFO binding failed'
    # Audit the retained deskew RAM and the actual generated FIFO BRAM controls.
    ram = {n: c for n, c in cells.items() if c['ref'] in ('RAMD32', 'RAMS32')}
    assert ram and all(n.startswith('csi_rx/') for n in ram)
    ram_controls = {}
    for n in ram:
        assert driver(n + '/CLK') == clock + 'Legacy.DivClkBuffer/O'
        relevant = [pin for pin in inputs[n] if re.search(r'/(CLK|WCLK|WE|I|RADR\d|WADR\d)$', pin)]
        assert relevant
        assert not any(pin.rsplit('/', 1)[1] in ('RST', 'CLR', 'PRE', 'SR') for pin in inputs[n])
        for pin in relevant:
            if pin.endswith('/CLK'):
                ram_controls[pin] = [driver(pin)]
                continue
            sources = starts(pin)
            # RAM32X1D's unused SP read port has the write address; only its DP
            # output feeds the read pipeline. Keep both role-specific checks.
            used_fifo_read = '/DataFIFO/' in n and '/RADR' in pin and bool(sinks[n+'/O'])
            expected_clock = 'clk_fpga_1' if used_fifo_read else 'byte_clk'
            assert all(cells[s.rsplit('/', 1)[0]]['clocks'] == expected_clock for s in sources
                       if cells.get(s.rsplit('/', 1)[0], {}).get('ref', '').startswith('FD')), (pin,expected_clock,sorted(sources))
            ram_controls[pin] = sorted(sources)
    brams = {n:c for n,c in cells.items() if c['ref'] in ('RAMB18E1','RAMB36E1')}
    assert brams, 'Real FIFO BRAM optimized away or not bound'
    bram_controls = {}
    for n in brams:
        for port, cp, control in [('A','CLKARDCLK',r'(ADDRARDADDR|ENARDEN|REGCEAREGCE|RSTRAMARSTRAM|RSTREGARSTREG|WEA)'),
                                  ('B','CLKBWRCLK',r'(ADDRBWRADDR|ENBWREN|REGCEB|RSTRAMB|RSTREGB|WEBWE)')]:
            clock_driver = driver(n + '/' + cp)
            assert cells[clock_driver.rsplit('/',1)[0]]['ref'] in ('BUFR','BUFG')
            clock_map = {'VideoGlobal/O':'clk_fpga_1','RefGlobal/O':'clk_fpga_2','AxiGlobal/O':'clk_fpga_0',
                         clock+'Legacy.DivClkBuffer/O':'byte_clk'}
            clocks = {clock_map[clock_driver]}
            for pin in inputs[n]:
                if not re.match(control, pin.rsplit('/',1)[1]):
                    continue
                ss = starts(pin)
                foreign = [s for s in ss if cells.get(s.rsplit('/',1)[0],{}).get('ref','').startswith('FD')
                           and not set(tokens(cells[s.rsplit('/',1)[0]]['clocks'])) <= clocks]
                assert not foreign, ('BRAM control foreign clock',pin,foreign)
                bram_controls[pin] = sorted(ss)
    cdc = (OUT / 'cdc.rpt').read_text()
    cdc_counts = {i: dict(severity=sev, count=int(count)) for i, sev, count in
                  re.findall(r'^(CDC-\d+)\s+(Info|Warning|Critical)\s+(\d+)\s', cdc, re.M)}
    critical_rows = [line.strip() for line in cdc.splitlines() if re.match(r'\s*\d+\s+CDC-\d+\s+Critical', line)]
    # Vendor FIFO output bus is released by read-domain CE, not by synchronizing
    # each data bit. Check the full37-bit bus and the real Gray pointer chains.
    fifo_out = [n for n in cells if '/DataFIFO/' in n and re.search(r'gpr1.dout_i_reg\[\d+\]$', n)]
    assert len(fifo_out) == 37
    for n in fifo_out:
        assert cells[n]['clocks'] == 'clk_fpga_1'
        assert all(cells[s.rsplit('/',1)[0]]['clocks'] == 'clk_fpga_1'
                   for s in starts(n+'/CE') if cells.get(s.rsplit('/',1)[0],{}).get('ref','').startswith('FD'))
    gray_pairs = []
    for n,c in cells.items():
        if '/DataFIFO/' not in n or 'dest_graysync_ff_reg[0]' not in n:
            continue
        assert c['async_reg'] == '1'
        second = n.replace('dest_graysync_ff_reg[0]', 'dest_graysync_ff_reg[1]')
        assert driver(second+'/D') == n+'/Q' and cells[second]['async_reg']=='1'
        assert sinks[n+'/Q'] == {second+'/D'}
        gray_pairs.append([driver(n+'/D'),n,second])
    assert len(gray_pairs) == 10
    for prefix in ['csi_rx/SyncAsyncEnable', 'phy/CoreAsyncReset/SyncAsyncx']:
        f0=prefix+'/oSyncStages_reg[0]';f1=prefix+'/oSyncStages_reg[1]'
        assert cells[f0]['async_reg']=='1' and cells[f1]['async_reg']=='1'
        assert driver(f1+'/D')==f0+'/Q' and sinks[f0+'/Q']=={f1+'/D'}
    timing = (OUT / 'timing_synth.rpt').read_text()
    timing_row = re.search(r'^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+', timing, re.M)
    assert timing_row
    ready = OUT.parent/'ready'
    ready_required = ['budget_constraints_completed.txt','budget_ready.dcp','budget_ready.v',
                      'gray_budget.tsv','cdc.rpt','cdc_no_waiver.rpt','bus_skew.rpt','exceptions.rpt','effective.xdc','launch_exit.json']
    assert all((ready/n).is_file() and (ready/n).stat().st_size for n in ready_required)
    assert json.loads((ready/'launch_exit.json').read_text(encoding='utf-8-sig'))['exit_code']==0
    budgets=list(csv.DictReader((ready/'gray_budget.tsv').open(),delimiter='\t'))
    assert len(budgets)==2
    for row in budgets:
        assert float(row['bus_skew_ns'])==6.667 and int(row['bits'])==5
        assert float(row['max_delay_ns'])=={'clk_fpga_1':6.667,'byte_clk':85.716}[row['source_clock']]
    unwaived=(ready/'cdc_no_waiver.rpt').read_text()
    assert not re.search(r'CDC-\d+\s+Critical',unwaived)
    assert set(cdc_counts) == {'CDC-3','CDC-9','CDC-15','CDC-26'}
    assert cdc_counts['CDC-15']['count']==37 and cdc_counts['CDC-26']['count']==2
    # Only constraint metadata changed between these checkpoints, not logic.
    structure_proof=checkpoint_graph_proof()
    result = dict(status='FAIL_CDC_STOP' if critical_rows else 'PASS_STRUCTURE_AND_BUDGET_ENTRY', synthesis='COMPLETE_1_OF_1', source_identity='PASS_DIRECT_CANONICAL_HDL_AND_EXISTING_REAL_FIFO',
                  tool=version.strip(), cdc=cdc_counts, critical_rows=critical_rows,
                  heartbeat=dict(clock_driver=driver(heartbeat + '/C'), stages=2, first_stage_exclusive=True,
                                 second_stage_endpoints=sorted(sinks[hb_second + '/Q']), init=0),
                  shared_activity_clear=shared_clear, ppi_isolation=lanes,
                  qualified_activity=dict(gate=qualified,inputs=[shared+'[1]/Q',recent+'/Q'],
                                          consumers='External clk_active,clock-lane local history and both data-lane reset controls checked'),
                  warning_structure=dict(cdc15_output_ce_bus_bits=len(fifo_out),gray_two_stage_chains=gray_pairs,
                                         cdc26='Two input-port boundary cases retain actual exclusive2FF ASYNC_REG chains;no LUTRAM involved at these endpoints'),
                  ram=dict(scope='Retained CSI LM deskew RAM and actual generated DataFIFO/LineBufferFIFO BRAM',
                           leaf_ram_primitives=len(ram), refs=dict(Counter(c['ref'] for c in ram.values())),
                           write_clock_driver=clock + 'Legacy.DivClkBuffer/O',
                           asynchronous_reset_pins=0, controls=ram_controls,bram_count=len(brams),bram_controls=bram_controls),
                  resources=dict(scope='Bounded OOC including actual FIFO netlists;see utilization.rpt',
                                 placed_slices='UNKNOWN_NOT_PLACED'),
                  timing=dict(zip(('wns_ns','tns_ns','whs_ns','ths_ns'), map(float, timing_row.groups()))),
                  constraints=dict(scope='OOC internal paths and12fixed MIPI pads;logical PS/interface borders are not production signoff',
                                   precision='Explicit half-period;inspect clocks.rpt for native rounding',gray_budgets=budgets,
                                   correction='Exact installed2023.1 helper formula reapplied after clocks exist;1000ns no-clock fallback retained in original synth report',
                                   logic_equivalent_after_constraint_rebind=True,
                                   checkpoint_primitive_graph_proof=structure_proof,
                                   ready_artifact_sha256={n:sha(ready/n) for n in ready_required}),
                  drc=dict(report='drc.rpt;no blackboxes permitted',scope='Bounded OOC,not production top'),
                  ip_packaging='Direct canonical files consumed. No local packaged-IP catalog/target refresh; production generated sources not signed.',
                  stop_reason='Critical CDC remains' if critical_rows else None,
                  next='Review every warning and boundary,then use conditional implementation only if gate passes.',
                  implementation=0, bit=0, board=0,
                  artifact_sha256={name:sha(OUT/name) for name in required})
    (PACK / 'synthesis_result.json').write_text(json.dumps(result, indent=2) + '\n')
    attempt.update(status=result['status'], actual_synthesis_started=True, actual_synthesis_completed=True,
                   confirmed_design_failures=int(bool(critical_rows)), synthesis_result_sha256=sha(PACK / 'synthesis_result.json'),
                   frozen_and_protected_inputs_unchanged=True,
                   offline_review_executions=attempt.get('offline_review_executions', 0) + 1)
    (PACK / 'attempt.json').write_text(json.dumps(attempt, indent=2) + '\n')
    if result['status']=='PASS_STRUCTURE_AND_BUDGET_ENTRY':
        (OUT.parent/'synthesis_gate.txt').write_text('PASS_CURRENT_SOURCE_CDC_STRUCTURE\n')
    print(json.dumps({k:result[k] for k in ('status','synthesis','cdc','timing','implementation','bit','board')}))


if __name__ == '__main__':
    main()
