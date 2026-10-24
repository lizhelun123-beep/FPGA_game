"""Directed Vivado 2023.1 UNISIM tests and explicit, gated fixed-setting OOC.

Usage: python color_test/sim/run_dphy_sampling_test.py [compile|primitive|control|audit|ooc|ooc-synth]
Run in the authorized normal Windows environment (the bundled GCC cannot load
inside the restricted environment). The explicit ooc mode runs only the bounded
candidate after both functional layers pass. ooc-synth stops after synthesis to
verify runtime script access, preserving old routed reports and their rejection.
In Codex, use an approved require_escalated tool invocation for Vivado; a parent
file-read check or synth.maxThreads=1 does not establish helper/runtime access.
Vivado inherits console handles and starts at the repository root; its explicit
-log/-journal files retain evidence without the old Python file redirection.
No project regeneration or hardware.
Generated evidence stays under color_test/build/dphy_sampling.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import importlib.util
import csv
import hashlib
from datetime import datetime, timezone
from itertools import product
from bisect import bisect_right

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/dphy_sampling"
BIN = Path(os.environ.get("XILINX_VIVADO", "D:/Xilinx/Vivado/2023.1")) / "bin"
IP = ROOT / "repo/ip/MIPI_D_PHY_RX/hdl"
NAMES = "DPHY_Pkg DphySyncAsync DphySyncAsyncReset DphyDebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver".split()


def call(name, args, log, native_console=False):
    command = [str(BIN / (name + ".bat")), *map(str, args)]
    print(subprocess.list2cmdline(command), flush=True)
    if native_console:
        # Match the successful direct Windows launcher. Vivado already writes
        # its own explicit -log; avoid a second redirected Windows launch chain.
        result = subprocess.run(command, cwd=ROOT.parent)
        evidence = args[args.index('-log') + 1]
    else:
        with (BUILD / log).open("w") as out:
            result = subprocess.run(command, cwd=BUILD, stdout=out, stderr=subprocess.STDOUT)
        evidence = BUILD / log
    if result.returncode:
        raise RuntimeError(f"{name} failed ({result.returncode}); see {evidence}")


def compile_design():
    call("xvhdl", ["--2008", *[IP / (n + ".vhd") for n in NAMES], ROOT / "sim/tb_dphy_sampling.vhd"], "compile.log")
    call("xelab", ["tb_dphy_sampling", "-debug", "all", "-s", "dphy_sampling", "-L", "unisim", "-timescale", "1ns/1fs", "-timeprecision_vhdl", "1fs"], "elaborate.log")


def primitive():
    script = r'''
open_vcd primitive.vcd
set top /tb_dphy_sampling
log_wave $top/*
log_vcd $top/txclk $top/serial_data $top/clock_lp $top/lp0 $top/lp1 $top/scenario $top/ready $top/byteclk
foreach c {0 1} {
    set p [format {%s/\configs(%d)\/dut} $top $c]
    log_wave $p/ClockLane/*
    if {$c == 1} { log_wave $p/ClockLane/HSClockingX/candidate/* }
    foreach lane {0 1} {
        set d [format {%s/\DataLaneGen(%d)\/DPHY_LaneSFEN_X} $p $lane]
        log_wave $d/* $d/HSDeserializerX/*
        log_vcd $d/HSDeserializerX/dDataIn_int $d/HSDeserializerX/dLogicRst
    }
}
set raw [open primitive_raw.txt w]
set guard [open primitive_guard.txt w]
set p [format {%s/\configs(1)\/dut/ClockLane/HSClockingX/candidate} $top]
proc sample_raw {c} {
    global top raw raw_count
    set case [get_value -radix dec $top/scenario]
    if {![info exists raw_count($c,$case)]} { set raw_count($c,$case) 0 }
    if {$raw_count($c,$case) >= 40} { return }
    incr raw_count($c,$case)
    foreach lane {0 1} {
        set d [format {%s/\configs(%d)\/dut/\DataLaneGen(%d)\/DPHY_LaneSFEN_X/HSDeserializerX} $top $c $lane]
        puts $raw "[current_time] $c $lane $case [get_value -radix bin $d/dDataIn_int] [get_value -radix unsigned $d/dAlignment_int] 1"
    }
}
proc sample_guard {} {
    global p guard
    puts $guard "[current_time] [get_value -radix bin $p/mmcm_reset] [get_value -radix bin $p/locked_raw] [get_value -radix bin $p/ready_ref] [get_value -radix bin $p/capture_reset] [get_value -radix bin $p/lock_ok]"
}
foreach c {0 1} {
    set phy [format {%s/\configs(%d)\/dut} $top $c]
    add_condition -radix unsigned -notrace "$top/audit_tick == 0" [list sample_raw $c]
    add_condition -radix unsigned -notrace "$top/audit_tick == 1" [list sample_raw $c]
}
foreach name {mmcm_reset locked_raw ready_ref capture_reset lock_ok} {
    foreach bit {0 1} {
        add_condition -radix unsigned -notrace "$p/$name == $bit" {sample_guard}
    }
}
run 180 us
close $raw
close $guard
close_vcd
quit
'''
    (BUILD / "primitive.tcl").write_text(script)
    call("xsim", ["dphy_sampling", "-wdb", "primitive.wdb", "-tclbatch", "primitive.tcl"], "primitive.log")
    log = (BUILD / "primitive.log").read_text()
    # A planned stopped input is reported as severity Error by UNISIM. Keep
    # it visible and accept only this exact model diagnostic, with independent
    # reset/ready/relock checks below; every other error is still a failure.
    unexpected = [line for line in log.splitlines() if re.match(r"(?i)^(?:Fatal|Error|Failure):",line)
                  and "[Unisim MMCME2_ADV-164]" not in line]
    if "DPHY_PRIMITIVE_STIMULUS_DONE" not in log or unexpected:
        raise RuntimeError("Primitive stimulus incomplete; inspect primitive.log")
    check_primitive()


def check_primitive():
    events = {}
    for line in (BUILD / "primitive_stimulus.txt").read_text().splitlines():
        t, unit, kind, case, bits = line.split()
        assert unit == "fs"
        events.setdefault(int(case), []).append((int(t)/1000, kind, bits))
    traces = {}
    for line in (BUILD / "primitive_trace.txt").read_text().splitlines():
        t, unit, cfg, lane, case, ready, valid, data, sync, active, err, soft = line.split()
        assert unit == "fs"
        traces.setdefault((int(cfg), int(lane), int(case)), []).append(
            (int(t)/1000, ready, valid, data, sync, active, err, soft))
    assert set(events)==set(range(16))|{17,98}, "incomplete primitive cases"
    assert all(r[1]=="1" for rows in traces.values() for r in rows if r[2]=="1"), "valid without ready"
    for cfg in (0,1):
        for case in events:
            paired=[[r[0] for r in traces[(cfg,lane,case)] if r[2]=='1'][:32] for lane in (0,1)]
            assert paired[0]==paired[1], f"lane byte pairing/valid skew {cfg,case}"
    results, failures = [], []
    for case, ev in events.items():
        payload_t = next(t for t, k, _ in ev if k == "PAYLOAD")
        trail_t = next(t for t, k, _ in ev if k == "TRAIL")
        tx = [(t, bits) for t, k, bits in ev if k == "BIT" and payload_t <= t < trail_t]
        sot_t = next(t for t, k, _ in ev if k == "SOT")
        sot = [bits for t, k, bits in ev if k == "BIT" and sot_t <= t < payload_t]
        for cfg in (0, 1):
            for lane in (0, 1):
                # Text vectors are lane1,lane0. Decode LSB-first independently.
                stream = "".join(bits[1-lane] for _, bits in tx)
                expected = [sum(int(stream[i+b]) << b for b in range(8)) for i in range(0,len(stream),8)]
                assert sum(int(bits[1-lane]) << b for b,bits in enumerate(sot)) == 0xB8
                rows = traces[(cfg,lane,case)]
                out = [r for r in rows if r[2] == "1"]
                errors = []
                if case==98:
                    if out or any(r[4]=='1' for r in rows): errors.append('T_INIT bypassed before 100 us')
                    result=dict(config=cfg,lane=lane,case=case,payload_bytes=0,delay_ps=None,errors=errors)
                    results.append(result)
                    if errors: failures.append(result)
                    continue
                if len(out) < len(expected): errors.append(f"short payload {len(out)}/{len(expected)}")
                for i,(row,value) in enumerate(zip(out,expected)):
                    if row[3].upper() != f"{value:02X}":
                        errors.append(f"byte {i} got {row[3]} expected {value:02X} at {row[0]}ps")
                        break
                if any(row[3].upper()!='FF' for row in out[len(expected):]): errors.append('payload duplicated into trail')
                if any(r[1] != "1" for r in out): errors.append("valid before ready")
                if any(r[6:] != ("0","0") for r in rows): errors.append("SoT error/soft match")
                if sum(r[4] == "1" for r in rows) != 1: errors.append("SoT sync pulse count != 1")
                if out and any(abs(out[i+1][0]-out[i][0]-14284) > 2 for i in range(min(len(out),32)-1)):
                    errors.append("payload valid gap/repetition")
                if out and any(r[2] == "1" for r in rows[-8:]): errors.append("valid failed to exit")
                delay = (out[0][0]-payload_t) if out else None
                result = dict(config=cfg,lane=lane,case=case,payload_bytes=len(expected),
                    first_payload_ps=payload_t,first_ppi_ps=out[0][0] if out else None,
                    delay_ps=delay,delay_UI=delay/1785.5 if delay is not None else None,
                    errors=errors)
                results.append(result)
                if errors: failures.append(result)
    summary = dict(scope="actual UNISIM + full canonical top; no forced LOCKED/data/reset", results=results, failures=failures)
    (BUILD / "primitive_results.json").write_text(json.dumps(summary,indent=2))
    if failures:
        print(json.dumps(failures[:6],indent=2))
        raise RuntimeError(f"Primitive functional FAIL: {len(failures)} lane/case checks; see primitive_results.json and primitive.wdb")
    audit=check_raw_and_guard(events)
    summary['raw_and_guard']=audit
    (BUILD / "primitive_results.json").write_text(json.dumps(summary,indent=2))
    print(f"DPHY_PRIMITIVE_PASS lane_cases={len(results)} payload_bytes={sum(r['payload_bytes'] for r in results)}; raw Q8-first, 8 alignments, R/F, reset/relock")


def check_raw_and_guard(events):
    scale={'fs':.001,'ps':1,'ns':1000,'us':1000000}
    raw={}
    for line in (BUILD/'primitive_raw.txt').read_text().splitlines():
        t,u,c,l,case,bits,alignment,valid=line.split()
        if int(case)<0: continue
        raw.setdefault((int(c),int(l),int(case)),[]).append((float(t)*scale[u],bits,int(alignment)))
    coverage={}; checked=0
    for cfg in (0,1):
        for lane in (0,1):
            aligns=set()
            for case,ev in events.items():
                if case==98: continue
                st=next(t for t,k,_ in ev if k=='SOT')
                stream=''.join(bits[1-lane] for t,k,bits in ev if k=='BIT' and t>=st)
                rows=raw.get((cfg,lane,case),[])
                assert len(rows)>=32, f"raw capture missing {cfg,lane,case}"
                anchor=None
                for i in range(len(rows)-4):
                    chunk=''.join(r[1] for r in rows[i:i+5])
                    pos=stream.find(chunk)
                    if pos>=0:
                        anchor=i,pos
                        break
                assert anchor is not None, f"Q8-first raw sequence mismatch {cfg,lane,case}"
                i,pos=anchor
                for j,row in enumerate(rows[i:]):
                    off=pos+8*j
                    if off+8<=len(stream):
                        assert row[1]==stream[off:off+8], f"raw bit drop/reversal/repetition {cfg,lane,case,j}"
                        checked+=8
                assert len({r[2] for r in rows[-8:]})==1, "unstable WordAlignment"
                if case<16: aligns.add(rows[-1][2])
            assert aligns==set(range(8)), f"alignment coverage {cfg,lane}: {aligns}"
            coverage[f'{cfg}:{lane}']=sorted(aligns)
    # Source clock and actual launch-edge identity, independent of schedule labels.
    edges=[]; tick=0; vcd_scale=1; clock_id=None
    for line in (BUILD/'primitive.vcd').read_text().splitlines():
        if line.startswith('$timescale'): continue
        if line.strip() in ('1fs','1ps'): vcd_scale=1 if line.strip()=='1fs' else 1000
        if line.startswith('$var') and line.split()[4]=='txclk': clock_id=line.split()[3]
        if line.startswith('#'): tick=int(line[1:])*vcd_scale
        elif clock_id and line in ('0'+clock_id,'1'+clock_id): edges.append((tick,line[0]))
    rises=[t for t,v in edges if v=='1']
    periods={b-a for a,b in zip(rises,rises[1:]) if b-a<10000000}
    assert periods=={3571000}, f"source period changed: {periods} fs"
    times=[t for t,_ in edges]; rf=set()
    for case,ev in events.items():
        if case>=16: continue
        pt=next(t for t,k,_ in ev if k=='PAYLOAD')
        target=round((pt-800)*1000)
        idx=bisect_right(times,target)-1
        assert abs(times[idx]-target)<=1, "payload launch not related to actual source edge"
        rf.add('R' if edges[idx][1]=='1' else 'F')
    assert rf=={'R','F'}, "missing payload R/F relation"
    states={}
    for line in (BUILD/'primitive_guard.txt').read_text().splitlines():
        t,u,*bits=line.split()
        if set(''.join(bits))<=set('01'): states[float(t)*scale[u]]=bits
    assert len(states)>8, "guard transitions missing"
    pulses=[]; start=None; last=None
    for t,b in sorted(states.items()):
        rst,locked,ready,capture,ok=b
        if capture=='0': assert ready==locked==ok=='1', f"capture escaped unqualified lock at {t}ps"
        if rst=='1' and last!='1': start=t
        if rst=='0' and last=='1':
            pulses.append(t-start)
            assert t-start>=40000, "MMCM reset shorter than 40 ns"
        last=rst
    assert len(pulses)>=2, "no startup and stopped-clock reset"
    assert list(sorted(states.items()))[-1][1][2:4]==['1','0'], "did not relock/release capture"
    log=(BUILD/'primitive.log').read_text()
    assert log.count('Error:  Warning : [Unisim MMCME2_ADV-164]')==1, "unexpected clock-stop diagnostics"
    assert '[Unisim MMCME2_ADV-163]' not in log, "invalid feedback delay"
    assert 'No matching HDL' not in log, "incomplete waveform capture"
    return dict(raw_bits_compared=checked,alignments=coverage,source_period_fs=3571000,
                first_payload_edges=sorted(rf),reset_widths_ps=pulses,
                planned_unisim_clock_stop_messages=1,forced_locked=False)


def control(rebuild=True):
    if rebuild:
        call("xvhdl", ["--2008", ROOT / "sim/tb_dphy_sampling.vhd"], "control_compile.log")
        call("xelab", ["tb_dphy_sampling_control", "-debug", "all",
                       "-s", "dphy_sampling_control", "-L", "unisim", "-timeprecision_vhdl", "1fs"], "control_elaborate.log")
    else:
        exe=BUILD/'xsim.dir/dphy_sampling_control/xsimk.exe'
        assert exe.exists() and all(exe.stat().st_mtime>=p.stat().st_mtime for p in
            [ROOT/'sim/tb_dphy_sampling.vhd',*[IP/(n+'.vhd') for n in NAMES]]), 'stale controller snapshot'
    call("xsim", ["dphy_sampling_control", "-wdb", "control.wdb", "-tclbatch",
                  (ROOT / "sim/check_dphy_sampling_control.tcl").as_posix()], "control.log")
    log = (BUILD / "control.log").read_text()
    if "DPHY_CONTROL_PASS" not in log or re.search(r"(?im)^(?:ERROR:|Fatal:|Failure:)",log):
        raise RuntimeError("Controller checks incomplete; inspect control.log")
    check_control()


def check_control():
    events = {}
    for line in (BUILD / "control_serial.txt").read_text().splitlines():
        t,unit,kind,case,bits=line.split()
        assert unit == "fs"
        events.setdefault(int(case),[]).append((int(t),kind,bits))
    traces = {}
    for line in (BUILD / "control_trace.txt").read_text().splitlines():
        t,unit,c,l,case,ready,valid,data,sync,active,err,soft=line.split()
        if c == "1": traces.setdefault((int(l),int(case)),[]).append((int(t),ready,valid,data,sync,err,soft))
    results=[]
    for case,ev in events.items():
        accept=any(k=="ACCEPT" for _,k,_ in ev)
        loss=next((t for t,k,_ in ev if k=="LOSS"),None)
        pt=next(t for t,k,_ in ev if k=="PAYLOAD")
        tt=next(t for t,k,_ in ev if k=="TRAIL")
        tx=[bits for t,k,bits in ev if k=="BIT" and pt<=t<tt]
        assert len(tx)==256
        for lane in (0,1):
            out=[r for r in traces[(lane,case)] if r[2]=="1"]
            expected=[sum(int(tx[i+b][1-lane])<<b for b in range(8)) for i in range(0,256,8)]
            errors=[]
            if not accept:
                if out: errors.append("joined unready/mid-burst payload")
                if any(r[4]=="1" for r in traces[(lane,case)]): errors.append("false SoT pulse")
            else:
                if loss is None and len(out)<32: errors.append("short accepted payload")
                if loss is not None and (not out or any(r[0]>=loss for r in out)): errors.append("valid after active loss or missing pre-loss prefix")
                n=min(len(out),32)
                if [r[3].upper() for r in out[:n]] != [f"{v:02X}" for v in expected[:n]]: errors.append("accepted payload corruption/drop/repetition")
                if loss is None and any(r[3].upper()!='FF' for r in out[32:]): errors.append('payload duplicated into trail')
                if any(y[0]-x[0] not in range(14283000,14285001) for x,y in zip(out[:31],out[1:32])): errors.append("accepted valid gap")
                if any(r[1]!="1" for r in out): errors.append("valid without ready")
            results.append(dict(case=case,lane=lane,accept=accept,observed_valid=len(out),errors=errors))
    (BUILD / "control_results.json").write_text(json.dumps(results,indent=2))
    assert len(results)==22, f"incomplete control coverage {len(results)}"
    for case in (100,110,120,130):
        ev=events[case]
        sot=next(t for t,k,_ in ev if k=='SOT')
        ready=next(t for t,k,_ in ev if k=='READY')
        assert (sot<ready if case in (100,130) else sot==ready if case==110 else sot>ready), f"ready/SoT boundary not exercised {case}"
    failures=[r for r in results if r['errors']]
    if failures: raise RuntimeError("Controller payload FAIL: "+json.dumps(failures[:4]))
    print(f"DPHY_CONTROL_PAYLOAD_PASS lane_cases={len(results)}")


def fixed_ooc(synth_only=False):
    primitive=json.loads((BUILD/'primitive_results.json').read_text())
    controller=json.loads((BUILD/'control_results.json').read_text())
    assert not primitive['failures'] and primitive.get('raw_and_guard'), 'unforced primitive gate failed'
    assert len(controller)==22 and not any(r['errors'] for r in controller), 'controller gate failed'
    assert re.search(r'^DPHY_CONTROL_PASS checks=33;', (BUILD/'control.log').read_text(), re.M), 'controller status missing'
    sources=[ROOT/'sim/tb_dphy_sampling.vhd',*[IP/(n+'.vhd') for n in NAMES]]
    oldest=min((BUILD/'primitive_results.json').stat().st_mtime,(BUILD/'control_results.json').stat().st_mtime)
    assert all(p.stat().st_mtime<=oldest for p in sources), 'functional evidence is stale after RTL/fixture change'
    assert (ROOT/'sim/check_dphy_sampling_control.tcl').stat().st_mtime <= (BUILD/'control_results.json').stat().st_mtime
    (BUILD/'functional_gate.txt').write_text('UNFORCED_PRIMITIVE_AND_CONTROLLER_PASS\n')
    out=ROOT/('build/vivado_runtime/dphy_sampling' if synth_only else 'build/dphy_sampling_ooc')
    out.mkdir(parents=True,exist_ok=True)
    status=dict(started_utc=datetime.now(timezone.utc).isoformat(),status='RUNNING',
                scope='synthesis_only' if synth_only else 'fixed_ooc',
                launch_mode='native_console_repository_root',
                launcher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in ooc_sources()})
    receipt=out/'last_run.json'
    receipt.write_text(json.dumps(status,indent=2))
    try:
        args=['-mode','batch','-source',(ROOT/'sim/run_dphy_sampling_ooc.tcl').as_posix(),
              '-log',(out/'vivado.log').as_posix(),'-journal',(out/'vivado.jou').as_posix()]
        if synth_only: args.extend(['-tclargs','--synth-only'])
        call('vivado',args,'runtime_synth.log' if synth_only else 'fixed_ooc.log',native_console=True)
    except RuntimeError as error:
        status.update(status='TOOL_FAILED',error=str(error),current_rtl_covered=False)
        receipt.write_text(json.dumps(status,indent=2))
        raise
    if synth_only:
        if 'DPHY_RUNTIME_SYNTH_PASS;' not in (out/'vivado.log').read_text():
            status.update(status='TOOL_FAILED',error='Missing synthesis-only completion marker',current_rtl_covered=False)
            receipt.write_text(json.dumps(status,indent=2))
            raise RuntimeError(status['error'])
        status.update(status='SYNTH_ONLY_COMPLETE',finished_utc=datetime.now(timezone.utc).isoformat(),
                      implementation_covered=False)
        receipt.write_text(json.dumps(status,indent=2))
        print('DPHY_RUNTIME_SYNTH_PASS; existing OOC rejection unchanged')
        return
    status.update(status='REPORTS_COMPLETE',finished_utc=datetime.now(timezone.utc).isoformat())
    receipt.write_text(json.dumps(status,indent=2))
    audit_ooc()


def ooc_sources():
    return [*[IP/(n+'.vhd') for n in NAMES],
            IP/'MIPI_DPHY_Receiver.xdc',IP/'MIPI_DPHY_Receiver_clocks.xdc',
            ROOT/'sim/dphy_sampling_ooc.vhd',ROOT/'sim/run_dphy_sampling_ooc.tcl']


def audit_ooc():
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('dphy_contract',ROOT/'tools/audit_dphy_contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    reports=ROOT/'reports/dphy_sampling_ooc'
    rows=module.paths_from_report(reports/'sampling_corners.rpt','candidate_BUFH_DDIRECT_M3')
    primary=[]
    for r in rows:
        r['fixed_seed_identity']='ADDITIONAL_STA'
        if abs(r['requirement_ns']-(module.UI if r['check']=='Setup' else 0))<.001:
            r['fixed_seed_identity']='ADJACENT_SETUP_UI_HOLD_0'
            primary.append(r)
    keys={(r['lane'],r['polarity'],r['corner'],r['capture_edge'],r['data_transition'],r['check']) for r in primary}
    expected=set(product(range(2),('p','n'),('Fast','Slow'),('rise','fall'),('rise','fall'),('Setup','Hold')))
    assert keys==expected and len(primary)==64, 'incomplete/duplicate fixed-seed bit association coverage'
    with (reports/'paths.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    windows=[]
    for corner in ('Fast','Slow','ALL'):
        rs=[r for r in primary if corner=='ALL' or r['corner']==corner]
        setup=min((r for r in rs if r['check']=='Setup'),key=lambda r:r['slack_ns'])
        hold=min((r for r in rs if r['check']=='Hold'),key=lambda r:r['slack_ns'])
        lo=-setup['slack_ns'];hi=hold['slack_ns']
        windows.append(dict(corner=corner,lower_shift_ns=lo,upper_shift_ns=hi,width_ns=round(hi-lo,6),
                            limiting_setup=setup,limiting_hold=hold))
    cdc=(reports/'cdc.rpt').read_text()
    critical=sum(int(n) for n in re.findall(r'^CDC-\d+\s+Critical\s+(\d+)',cdc,re.M))
    text=(reports/'timing.rpt').read_text().split('| Design Timing Summary',1)[1]
    values=re.search(r'(?m)^\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)',text)
    assert values, 'missing timing summary'
    summary=dict(zip(('WNS_ns','TNS_ns','WHS_ns','THS_ns'),map(float,values.groups())))
    report_time=min((reports/name).stat().st_mtime
                    for name in ('sampling_corners.rpt','cdc.rpt','timing.rpt'))
    newer_sources=[str(p.relative_to(ROOT)) for p in ooc_sources() if p.stat().st_mtime>report_time]
    summary.update(primary_paths=len(primary),additional_sta_paths=len(rows)-len(primary),
                   fixed_phase_degrees=[180,45],critical_cdc=critical,windows=windows,
                   current_rtl_covered=not newer_sources,newer_sources=newer_sources,
                   report_time_utc=datetime.fromtimestamp(report_time,timezone.utc).isoformat(),
                   eligible=False,phase_revision=None,
                   boundary='fixed 12 HS/LP pins, actual canonical receiver; virtual RefClk/PPI boundary; not full production signoff')
    summary['eligible']=not newer_sources and windows[-1]['width_ns']>=0 and critical==0 and summary['WNS_ns']>=0 and summary['WHS_ns']>=0
    (reports/'audit.json').write_text(json.dumps(summary,indent=2))
    print('DPHY_FIXED_OOC_AUDIT '+json.dumps({k:v for k,v in summary.items() if k!='windows'}))
    print('DPHY_D_PORT_WINDOWS '+json.dumps([{k:v for k,v in w.items() if not k.startswith('limiting_')} for w in windows]))
    if not summary['eligible']:
        raise RuntimeError('Fixed OOC not accepted; inspect source freshness, CDC and common window in reports/dphy_sampling_ooc/audit.json')


if __name__ == "__main__":
    BUILD.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv)>1 else "all"
    if mode not in ("all","compile","primitive","control","control-reuse","ooc","ooc-synth","audit","ooc-audit"):
        raise SystemExit("Expected compile, primitive, control, control-reuse, ooc, ooc-synth, audit, ooc-audit, or no argument")
    (BUILD / "tool.txt").write_text(str(BIN) + "\n")
    try:
        if mode in ("all","compile"): compile_design()
        if mode in ("all","primitive"): primitive()
        if mode in ("all","control"): control()
        if mode=="control-reuse": control(False)
        if mode=="ooc": fixed_ooc()
        if mode=="ooc-synth": fixed_ooc(synth_only=True)
        if mode=="audit": check_primitive(); check_control()
        if mode=="ooc-audit": audit_ooc()
    except (RuntimeError, AssertionError) as e:
        print(str(e),file=sys.stderr)
        raise SystemExit(1)
