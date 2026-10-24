"""One bounded canonical low-rate XSim round; audit mode never launches tools."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import csv
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT/'color_test/build/dphy_observer_140/shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/finite_observation/budget_probe/rate93_qualified_reset'
WORK = ROOT/'color_test/build/dphy_rate93_qualified/sim'
BIN = Path('D:/Xilinx/Vivado/2023.1/bin')
UI = 10_714_286
COMPLETE = [0, *range(1,17), 18, 20, 22]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(a):
    (RECORD/'attempt.json').write_text(json.dumps(a,indent=2)+'\n')


def run(a):
    assert not a['closed'] and a['functional_rounds_used']==0, 'One functional round already used'
    assert not WORK.exists(), 'Refuse stale simulation output'
    for name,v in a['protected_sha256'].items():
        assert sha(ROOT/name)==v, 'Source/evidence changed: '+name
    for name,v in a['execution_source_sha256'].items():
        assert sha(ROOT/name)==v, 'Frozen execution source changed: '+name
    WORK.mkdir()
    a.update(status='STARTED',functional_rounds_used=1,work_directory=str(WORK.relative_to(ROOT)),
             started_utc=datetime.now(timezone.utc).isoformat(),commands=[])
    save(a)
    ip=ROOT/'color_test/repo/ip/MIPI_D_PHY_RX/hdl'
    commands=[('compile','xvhdl',['--2008',*[ip/(n+'.vhd') for n in a['source_names']], ROOT/'color_test/sim/tb_dphy_rate93.vhd']),
              ('elaborate','xelab',['work.tb_dphy_rate93','-debug','all','-s','dphy_rate93','-L','unisim','-timescale','1ns/1fs','-timeprecision_vhdl','1fs']),
              ('simulate','xsim',['dphy_rate93','-wdb','rate93.wdb','-tclbatch',(ROOT/'color_test/sim/check_dphy_rate93.tcl').as_posix()])]
    for stage,tool,args in commands:
        command=[str(BIN/(tool+'.bat')),*map(str,args)]
        item=dict(stage=stage,command=command,status='STARTED')
        a['commands'].append(item); a['tool_start_attempts']+=1; save(a)
        print('RATE93_'+stage.upper()+'_START',flush=True)
        with (WORK/(stage+'.log')).open('w') as f:
            p=subprocess.run(command,cwd=WORK,stdout=f,stderr=subprocess.STDOUT,timeout=600)
        item.update(status='PASS' if p.returncode==0 else 'FAIL',exit_code=p.returncode,
                    log_sha256=sha(WORK/(stage+'.log'))); save(a)
        if p.returncode:
            raise RuntimeError(f'{stage} tool/report failure rc={p.returncode}; inspect {WORK/(stage+".log")}')
        print('RATE93_'+stage.upper()+'_COMPLETE',flush=True)
    a['simulation_completed']=True; save(a)


def audit(a, failure_evidence_only=False):
    assert failure_evidence_only or a.get('simulation_completed'), 'No completed simulation to audit'
    log=(WORK/a.get('effective_simulation_log','simulate.log')).read_text(errors='strict')
    assert 'DPHY_RATE93_STIMULUS_DONE' in log, 'Incomplete stimulus'
    native_complete='DPHY_RATE93_OBSERVATION_COMPLETE' in log
    assert native_complete or failure_evidence_only, 'Incomplete native observation/report'
    errors=[s for s in log.splitlines() if re.match(r'(?i)^(Fatal|Error|Failure):',s)]
    assert not errors, 'Primitive/simulator error: '+str(errors[:4])
    events=defaultdict(list); traces=defaultdict(list)
    for line in (WORK/'stimulus.txt').read_text().splitlines():
        t,unit,kind,case,bits=line.split(); assert unit=='fs'
        events[int(case)].append((int(t),kind,bits))
    for line in (WORK/'trace.txt').read_text().splitlines():
        t,unit,case,lane,ready,valid,data,sync,active,err,soft=line.split(); assert unit=='fs'
        traces[int(case),int(lane)].append(dict(t=int(t),ready=ready,valid=valid,data=data,
                                              sync=sync,active=active,err=err,soft=soft))
    assert any(k=='DONE' for _,k,_ in events[22]), 'No final stimulus marker'
    allclock=[]; byterises=[]; prev='0'
    for line in (WORK/'clocks.txt').read_text().splitlines():
        t,unit,tx,byte=line.split(); assert unit=='fs'
        if byte=='1' and prev=='0': byterises.append(int(t))
        prev=byte
        if tx in ('0','1'): allclock.append((int(t),tx))
    # The actual byte waveform is derived by UNISIM BUFR, not a second oscillator.
    period_rows=[r['t'] for r in traces[0,0]]
    assert len(period_rows)>10 and all(y-x==8*UI for x,y in zip(period_rows,period_rows[1:])), 'Noninteger byte/source-clock relationship'
    per_case=[]; failures=[]
    for case in COMPLETE:
        ev=events[case]
        def time(kind):
            times=[t for t,k,_ in ev if k==kind]; assert len(times)==1,(case,kind,times)
            return times[0]
        st,pt,tt,xt=time('SOT'),time('PAYLOAD'),time('TRAIL'),time('EXIT')
        tx=[(t,b) for t,k,b in ev if k=='BIT' and pt<=t<tt]
        sot=[b for t,k,b in ev if k=='BIT' and st<=t<pt]
        assert len(tx)==256 and len(sot)==8,(case,'incomplete transmitted packet')
        assert all(y[0]-x[0]==UI for x,y in zip(tx,tx[1:])), 'Bad serial stimulus cadence'
        # All actual data launches in the active HS epoch satisfy the declared
        # pin-delay interval, referenced to the independent source-clock edges.
        pin_times=[t for t,k,_ in ev if k=='BIT']
        clk_edges=sorted(set(t for t,_ in allclock if st-2*UI<=t<=tt+120*UI))
        # clocks.txt also contains byte-only events; isolate true source changes.
        source_edges=[]; last=None
        for t,v in allclock:
            if last is not None and v!=last: source_edges.append(t)
            last=v
        import bisect
        offsets=[t-source_edges[bisect.bisect_right(source_edges,t)-1] for t in pin_times]
        assert min(offsets)>=1_607_142 and max(offsets)<=9_107_143,(case,'pin timing outside declared model',min(offsets),max(offsets))
        pair_times=[]
        for lane in (0,1):
            assert sum(int(b[1-lane])<<i for i,b in enumerate(sot))==0xB8
            stream=''.join(bits[1-lane] for _,bits in tx)
            expected=[sum(int(stream[i+j])<<j for j in range(8)) for i in range(0,256,8)]
            rows=traces[case,lane]; out=[v for v in rows if v['valid']=='1']; problem=[]
            if len(out)<32: problem.append(f'short payload {len(out)}/32')
            mismatch=[dict(index=i,time_fs=v['t'],actual=v['data'],expected=f'{e:02X}')
                      for i,(v,e) in enumerate(zip(out,expected)) if v['data'].upper()!=f'{e:02X}']
            if mismatch: problem.append('first/whole payload mismatch')
            if any(v['data'].upper()!='FF' for v in out[32:]): problem.append('non-trail bytes after payload')
            if any(v['ready']!='1' for v in out): problem.append('valid without ready')
            if any(v['err']!='0' or v['soft']!='0' for v in rows): problem.append('SoT error/soft flag')
            if sum(v['sync']=='1' for v in rows)!=1: problem.append('sync pulse count !=1')
            if any(y['t']-x['t']!=8*UI for x,y in zip(out[:32],out[1:32])): problem.append('payload valid gap')
            if any(v['valid']=='1' for v in rows if v['t']>=xt+1_500_000_000): problem.append('valid failed to exit')
            pair_times.append([v['t'] for v in out[:32]])
            item=dict(case=case,lane=lane,SoT_fs=st,entry_to_SoT_fs=st-time('LP00'),payload_first_pin_fs=pt,
                      first_PPI_fs=out[0]['t'] if out else None,valid_bytes=len(out),
                      expected_payload=expected,first_observed=[v['data'] for v in out[:36]],
                      mismatches=mismatch[:8],errors=problem)
            per_case.append(item)
            if problem: failures.append(item)
        if pair_times[0]!=pair_times[1]: failures.append(dict(case=case,error='lane valid/byte epoch skew'))
    internal=list(csv.DictReader((WORK/'internal.tsv').open(),delimiter='\t'))
    assert internal and {'time','case','lane','d_reset','d_logic_reset','raw','align'}<=internal[0].keys()
    def fs(s):
        m=re.fullmatch(r'\s*([0-9.]+)\s*(fs|ps|ns|us|ms)\s*',s); assert m,s
        return round(float(m[1])*{'fs':1,'ps':1000,'ns':1000000,'us':1000000000,'ms':1000000000000}[m[2]])
    snapshots=[]
    fault_preconditions=[]
    for kind in ('SHORT_PAUSE_BEFORE','SHORT_PAUSE_STOPPED','SHORT_PAUSE_RECOVERED'):
        assert sum(k==kind for _,k,_ in events[25]) == 1, ('missing short-pause stimulus',kind)
    for case,kind in ((19,'ABORT'),(21,'CLOCK_STOP')):
        fault_times=[t for t,k,_ in events[case] if k==kind]
        assert len(fault_times)==1
        for lane in (0,1):
            before=[r for r in traces[case,lane] if r['t']<=fault_times[0]]
            assert before and before[-1]['valid']=='1' and before[-1]['active']=='1', 'Fault injection was not during active reception'
            fault_preconditions.append(dict(case=case,lane=lane,active_before_fault=True))
    for case,ev in events.items():
        for t,kind,_ in ev:
            if kind not in ('RESET_STOPPED','RELEASE_STOPPED','FAULT_BOUND','FAULT_HOLD','NO_CLOCK_EPOCH','CLOCK_ONLY_EPOCH','INIT_WAIT_COMPLETE','SHORT_PAUSE_BEFORE','SHORT_PAUSE_STOPPED','SHORT_PAUSE_RECOVERED'): continue
            rows=[v for v in internal if int(v['case'])==case and abs(fs(v['time'])-t)<=2000]
            assert len(rows)>=2,(case,kind,'missing internal snapshot')
            snapshots.append(dict(case=case,kind=kind,time_fs=t,rows=rows))
            if kind.startswith('SHORT_PAUSE_') and any(v['ready']!='1' or int(v['ppi_data'],16)!=0
                     or int(v['ppi_active'],2)!=0 or int(v['ppi_sync'],2)!=0
                     or int(v['ppi_error'],2)!=0 or int(v['ppi_soft'],2)!=0 or v['valid']!='0' for v in rows):
                failures.append(dict(case=case,kind=kind,error='short-pause qualification/idle isolation failed',rows=rows))
            if kind in ('RESET_STOPPED','RELEASE_STOPPED') and any(v['d_reset']!='1' or v['d_logic_reset']!='1' for v in rows):
                failures.append(dict(case=case,kind=kind,error='reset released without source clock',rows=rows))
            if kind in ('FAULT_BOUND','FAULT_HOLD','NO_CLOCK_EPOCH') and any(v['ready']!='0' for v in rows):
                failures.append(dict(case=case,kind=kind,error='clock activity/status not invalidated during fault',rows=rows))
            if kind in ('FAULT_BOUND','FAULT_HOLD','NO_CLOCK_EPOCH','CLOCK_ONLY_EPOCH'):
                if any(v['valid']!='0' or v['hard']!='0' or v['soft']!='0' or v['err']!='0'
                       or int(v['ppi_data'],16)!=0 or int(v['ppi_active'],2)!=0
                       or int(v['ppi_sync'],2)!=0 or int(v['ppi_error'],2)!=0
                       or int(v['ppi_soft'],2)!=0 or v['d_reset']!='1' for v in rows):
                    failures.append(dict(case=case,kind=kind,error='PPI/epoch isolation failed',rows=rows))
            if kind=='CLOCK_ONLY_EPOCH' and any(v['ready']!='1' for v in rows):
                failures.append(dict(case=case,kind=kind,error='Clock failed to qualify after fresh clock LP entry',rows=rows))
            if kind=='INIT_WAIT_COMPLETE' and any(v['state']=='stInitCountDown' for v in rows):
                failures.append(dict(case=case,kind=kind,error='Reenable T_INIT deadline not met',rows=rows))
    return dict(status=('FAIL_FUNCTIONAL' if failures else
                        'STOP_INCOMPLETE_NATIVE_OBSERVATION' if failure_evidence_only else
                        'PASS_FUNCTIONAL_MODEL_ONLY'),
                native_observation_completed=native_complete, failure_evidence_only=failure_evidence_only,
                scope='Canonical fixed low-rate production PHY/UNISIM; no capture RAM/CSI/frame/board signoff',
                UI_fs=UI,measured_byte_period_fs=8*UI,complete_lane_cases=len(per_case),cases=per_case,
                failures=failures,snapshots=snapshots,fault_preconditions=fault_preconditions,primitive_warnings=[s for s in log.splitlines() if 'Warning' in s or 'WARNING' in s],
                earliest_limit=a['plan']['earliest_limit'])


def retry_simulator_start(a):
    assert a['status']=='FIXTURE_RETRY_PREPARED' and a['functional_rounds_used']==1
    assert a['actual_stimulus_runs']==0 and a['xsim_startup_retries']==0
    assert not (WORK/'internal.tsv').exists(), 'Do not retry an advanced simulation'
    command=list(a['commands'][-1]['command'])
    assert Path(command[0]).name=='xsim.bat' and '-tclbatch' in command
    command[command.index('-tclbatch')+1]=(ROOT/'color_test/sim/check_dphy_rate93.tcl').as_posix()
    a['xsim_startup_retries']=1
    a['tool_start_attempts']+=1
    item=dict(stage='simulate_startup_retry1',command=command,status='STARTED')
    a['commands'].append(item)
    a['effective_simulation_log']='simulate_retry1.log'
    save(a)
    print('RATE93_SIMULATE_STARTUP_RETRY1',flush=True)
    with (WORK/'simulate_retry1.log').open('w') as f:
        p=subprocess.run(command,cwd=WORK,stdout=f,stderr=subprocess.STDOUT,timeout=300)
    item.update(status='PASS' if p.returncode==0 else 'FAIL',exit_code=p.returncode,
                log_sha256=sha(WORK/'simulate_retry1.log'))
    a['effective_simulation_log']='simulate_retry1.log'
    a['simulation_completed']=p.returncode==0
    save(a)
    assert p.returncode==0, 'XSim startup retry failed; no more retries'


def replay_corrected_init_fixture(a):
    assert a['status']=='FIXTURE_INIT_REPLAY_READY' and a['functional_rounds_used']==1
    assert a['fixture_validation_replays']==0 and a['design_failures']==0
    for name,v in {**a['protected_sha256'],**a['execution_source_sha256']}.items():
        assert sha(ROOT/name)==v, 'Frozen source/evidence changed: '+name
    original_commands=list(a['commands'][:3])
    assert [c['stage'] for c in original_commands]==['compile','elaborate','simulate']
    a.update(fixture_validation_replays=1,simulation_completed=False)
    save(a)
    for original in original_commands:
        stage=original['stage']; command=list(original['command'])
        if stage=='simulate':
            command[command.index('-wdb')+1]='rate93_fixture2.wdb'
            a['effective_simulation_log']='simulate_fixture2.log'
            a['current_native_simulation_invocations']=2
        item=dict(stage=stage+'_fixture2',command=command,status='STARTED')
        a['commands'].append(item);a['tool_start_attempts']+=1;save(a)
        print('RATE93_FIXTURE2_'+stage.upper()+'_START',flush=True)
        with (WORK/(stage+'_fixture2.log')).open('w') as f:
            p=subprocess.run(command,cwd=WORK,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        item.update(status='PASS' if p.returncode==0 else 'FAIL',exit_code=p.returncode,
                    log_sha256=sha(WORK/(stage+'_fixture2.log')));save(a)
        assert p.returncode==0, 'Corrected fixture tool failure; no automatic replay'
    a['simulation_completed']=True;save(a)


def main():
    mode=sys.argv[1] if len(sys.argv)==2 else 'invalid'
    assert mode in ('run','fixture-replay','retry-sim','audit','evidence-audit'), 'Use bounded run/fixture repair, or offline audit'
    a=json.loads((RECORD/'attempt.json').read_text())
    try:
        if mode=='run': run(a)
        if mode=='retry-sim': retry_simulator_start(a)
        if mode=='fixture-replay': replay_corrected_init_fixture(a)
        if mode=='evidence-audit':
            assert a['closed'] and a['actual_stimulus_runs']==1 and a['report_evidence_audits']<2
            a['report_evidence_audits']+=1; save(a)
        result=audit(a, failure_evidence_only=mode=='evidence-audit')
    except Exception as e:
        result=dict(status='STOP_TOOL_OR_FIXTURE',error=type(e).__name__+': '+str(e))
    for name,value in a['protected_sha256'].items():
        if sha(ROOT/name)!=value:
            result=dict(status='STOP_SOURCE_CHANGED',error=name)
    for name,value in a['execution_source_sha256'].items():
        if sha(ROOT/name)!=value:
            result=dict(status='STOP_SOURCE_CHANGED',error=name)
    result['artifact_sha256']={p.relative_to(ROOT).as_posix():sha(p) for p in WORK.iterdir() if p.is_file()}
    result['frozen_compiled_sources_unchanged']=True
    result['no_implementation_BIT_or_board']=True
    (RECORD/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    a.update(status=result['status'],closed=True,finished_utc=datetime.now(timezone.utc).isoformat(),
             design_failures=int(result['status']=='FAIL_FUNCTIONAL'),result_sha256=sha(RECORD/'result.json'))
    save(a)
    print(json.dumps(dict(status=result['status'],failure_count=len(result.get('failures',[])),
                         error=result.get('error'),result=str(RECORD/'result.json'))),flush=True)
    return 0 if result['status']=='PASS_FUNCTIONAL_MODEL_ONLY' else 1


if __name__=='__main__':
    sys.exit(main())
