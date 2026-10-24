"""Bounded canonical serial PHY-to-CSI CRC reproduction; no board/build access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'color_test/build/camera_crc_link'
BIN = Path('D:/Xilinx/Vivado/2023.1/bin')
PHY = ROOT / 'color_test/repo/ip/MIPI_D_PHY_RX/hdl'
CSI = ROOT / 'color_test/repo/ip/MIPI_CSI_2_RX/hdl'
PHY_NAMES = 'DPHY_Pkg DphySyncAsync DphySyncAsyncReset DphyDebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver'.split()
CSI_NAMES = 'CsiDebugLib CsiSyncAsync CsiSyncAsyncReset SimpleFIFO ECC CRC16_behavioral LM LLP MIPI_CSI2_Rx'.split()
TB = ROOT / 'color_test/sim/tb_camera_crc_link.vhd'
GEN = ROOT / 'color_test/color_test.srcs/sources_1/bd/system/ip/system_MIPI_CSI_2_RX_0_0/hdl'
VENDOR = [GEN/n/'sim'/(n+'.v') for n in ('cdc_fifo', 'line_buffer')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(record):
    (OUT/'result.json').write_text(json.dumps(record, indent=2)+'\n')


def prepare():
    assert not OUT.exists(), 'Preserve prior attempts'
    sources = [PHY/(n+'.vhd') for n in PHY_NAMES]+[CSI/(n+'.vhd') for n in CSI_NAMES]+VENDOR+[TB, Path(__file__)]
    identities = {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources}
    OUT.mkdir()
    record = dict(status='PREPARED', scope='canonical serial PHY -> CSI, full1600-byte RAW10 lines, exact PPI prefixes/all pixels/CRC positive and negative;not board/full-frame acceptance',
                  design_rounds=0, rounds_max=2, fixture_errors=[], hardware_runs=0,
                  full_builds=0, source_sha256=identities, commands=[])
    save(record)
    print('PREPARED canonical sources and actual generated vendor FIFO models', flush=True)


def run(short_tail=False, repair=False):
    record = json.loads((OUT/'result.json').read_text())
    if repair:
        assert record['status']=='FAIL_STOP' and record['design_rounds']==2 and not record.get('repair_validation')
        assert 'simulate rejected' in record['error']
        record['diagnosis_source_sha256'] = dict(record['source_sha256'])
        allowed = {'color_test/repo/ip/MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd',
                   'color_test/repo/ip/MIPI_D_PHY_RX/hdl/DPHY_LaneSFEN.vhd',
                   str(Path(__file__).relative_to(ROOT)).replace('\\','/')}
        for name,digest in record['source_sha256'].items():
            if name not in allowed:
                assert sha(ROOT/name)==digest,name
        record['source_sha256']={name:sha(ROOT/name) for name in record['source_sha256']}
        record['repair_validation'] = dict(attempt=1,max_attempts=1,status='STARTED',
            diagnosis_cases_retained=2,cause_failures_before=1,
            change='registered pending-byte drain before existing reset feedback CDC;unchanged short-tail stimulus/checkers')
    elif short_tail:
        assert record['status']=='PASS_SCOPED_SERIAL_PHY_TO_CSI_CRC' and record['design_rounds']==1
        record['round1_source_sha256'] = dict(record['source_sha256'])
        for name,digest in record['source_sha256'].items():
            if name not in (str(TB.relative_to(ROOT)).replace('\\','/'),str(Path(__file__).relative_to(ROOT)).replace('\\','/')):
                assert sha(ROOT/name)==digest,name
        record['source_sha256']={name:sha(ROOT/name) for name in record['source_sha256']}
        record['short_tail_UI']=12
    else:
        assert record['status'] == 'PREPARED' and record['design_rounds'] == 0, 'No automatic repeat'
    for name, digest in record['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    work = OUT/('fix1' if repair else 'round2' if short_tail else 'round1')
    work.mkdir()
    (work/'run.tcl').write_text('run all\nquit\n')
    record.update(status='RUNNING', design_rounds=2 if (short_tail or repair) else 1)
    save(record)
    commands = [
        ('vendor','xvlog',VENDOR),
        ('glbl','xvlog',[BIN.parent/'data/verilog/src/glbl.v']),
        ('phy','xvhdl',['--2008',*[PHY/(n+'.vhd') for n in PHY_NAMES]]),
        ('csi','xvhdl',['--2008',*[CSI/(n+'.vhd') for n in CSI_NAMES],TB]),
        ('elaborate','xelab',['work.tb_camera_crc_link','work.glbl','-debug','typical','-s','camera_crc_link',
           '-L','fifo_generator_v13_2_8','-L','axis_data_fifo_v2_0_10','-L','axis_infrastructure_v1_1_0',
           '-L','xpm','-L','unisims_ver','-L','unisim','-L','secureip','-timescale','1ns/1fs','-timeprecision_vhdl','1fs']),
        ('simulate','xsim',['camera_crc_link','-tclbatch','run.tcl']),
    ]
    for stage, tool, args in commands:
        cmd = [str(BIN/(tool+'.bat')),*map(str,args)]
        item = dict(stage=stage, command=cmd, status='STARTED')
        record['commands'].append(item)
        save(record)
        print('CRC_LINK_'+stage.upper()+'_START', flush=True)
        log = work/(stage+'.log')
        try:
            with log.open('w') as stream:
                result = subprocess.run(cmd, cwd=work, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
            item.update(returncode=result.returncode, log_sha256=sha(log))
            content = log.read_text(errors='replace')
            if result.returncode or (stage=='simulate' and 'CAMERA_CRC_LINK_PASS' not in content):
                raise RuntimeError(stage+' rejected; see '+str(log.relative_to(ROOT)))
            item['status'] = 'PASS'
            print('CRC_LINK_'+stage.upper()+'_PASS', flush=True)
        except Exception as exc:
            record.update(status='FAIL_STOP', error=str(exc))
            if repair:
                record['repair_validation']['status']='FAIL_STOP_NO_MORE_ATTEMPTS'
            item['status'] = 'FAIL'
            save(record)
            raise
        save(record)
    record['status'] = 'PASS_SCOPED_SERIAL_PHY_TO_CSI_CRC'
    if repair:
        record['repair_validation']['status']='PASS_SCOPED_SHORT_TAIL'
    save(record)
    print(record['status'], flush=True)


def tail_integration(resume=False,fix2=False,rearm=False):
    work=OUT/('rx_fault_1/rearm_1/serial_integration' if rearm else 'upstream_1/tail_integration_fix2' if fix2 else 'upstream_1/tail_integration');assert work.exists() if resume else not work.exists(),'Preserve prior tail integration'
    key='color_test/repo/ip/MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd'
    if rearm:
        prior=json.loads((OUT/'upstream_1/tail_integration_fix2/result.json').read_text())
        assert prior['status']=='PASS_SERIAL_PHY_CSI_ALL8_PHASES_10240_PIXELS_CRC_7GOOD_1BAD'
        changed={key,'color_test/repo/ip/MIPI_D_PHY_RX/hdl/DPHY_LaneSFEN.vhd',str(Path(__file__).relative_to(ROOT)).replace('\\','/')}
        for name,digest in prior['source_sha256'].items():
            if name not in changed:assert sha(ROOT/name)==digest,name
        assert sha(ROOT/key)!=prior['source_sha256'][key]
    else:
        passed=json.loads((OUT/'upstream_1/tail_fixed/result.json').read_text())
        assert passed['status']=='PASS_SCOPED_REAL_RAW_LP_TAIL_REPLAY_ALL3'
    if fix2:
        baseline=OUT/'upstream_1/tail_candidate1_HS_Deserializer.vhd'
        assert sha(baseline)==passed['source_sha256'][key]
        prior=json.loads((OUT/'upstream_1/tail_integration/result.json').read_text())
        assert prior['status']=='FAIL_STOP' and 'PPI_TRUNCATED' in (OUT/'upstream_1/tail_integration/simulate.log').read_text()
        assert sha(ROOT/key)!=sha(baseline)
    elif not rearm:assert sha(ROOT/key)==passed['source_sha256'][key]
    if not resume:work.mkdir();(work/'run.tcl').write_text('run all\nquit\n')
    sources=[PHY/(n+'.vhd') for n in PHY_NAMES]+[CSI/(n+'.vhd') for n in CSI_NAMES]+VENDOR+[TB,Path(__file__)]
    record=dict(status='RUNNING',scope='actual UNISIM serial PHY plus CSI/vendor FIFOs;all8 byte phases,FS,7good and1bad1600-byte lines;not production/board signoff',source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources},commands=[],full_builds=0,board_operations=0)
    if rearm:record.update(validation_attempt=1,validation_attempts_max=2,fixture_errors=[],prior_pass='upstream_1/tail_integration_fix2/result.json',change='fresh settled epoch for every burst;byte logic waits for complete registered drain before reset;unchanged serial stimulus/static phase wrapper/checkers')
    if fix2:record['revision']=dict(index=2,max=2,cause='117..118.4us trace:short FS SoT reaches byte logic before pending feedback can cross2FF;cHSReset rises before first output',change='existing registered busy asserts from HS bridge before SoT;same delayed LP tail/valid pipeline retained',evidence='../tail_integration/short_FS_timing.tsv',raw_byte_pipeline_regression_reused='../tail_fixed/result.json')
    if resume:
        prior=json.loads((work/'result.json').read_text());assert prior['status']=='FAIL_STOP' and prior['error']=='AssertionError: elaborate failed'
        assert 'Cannot find design unit work.true' in (work/'elaborate.log').read_text() and not prior.get('fixture_retry')
        record['commands']=prior['commands'];record['commands'][-1]['status']='FAIL_FIXTURE_ARGUMENT'
        record['fixture_retry']=dict(count=1,cause='Windows BAT split generic assignment;use static VHDL wrapper',prior_source_sha256=prior['source_sha256'])
        (work/'elaborate.log').rename(work/'elaborate_argument_failure.log')
    def save_tail():(work/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    commands=[('vendor','xvlog',VENDOR),('glbl','xvlog',[BIN.parent/'data/verilog/src/glbl.v']),
      ('phy','xvhdl',['--2008',*[PHY/(n+'.vhd') for n in PHY_NAMES]]),
      ('csi','xvhdl',['--2008',*[CSI/(n+'.vhd') for n in CSI_NAMES],TB]),
      ('elaborate','xelab',['work.tb_camera_crc_link_phases','work.glbl','-debug','typical','-s','camera_crc_link',
        '-L','fifo_generator_v13_2_8','-L','axis_data_fifo_v2_0_10','-L','axis_infrastructure_v1_1_0','-L','xpm','-L','unisims_ver','-L','unisim','-L','secureip','-timescale','1ns/1fs','-timeprecision_vhdl','1fs']),
      ('simulate','xsim',['camera_crc_link','-tclbatch','run.tcl'])]
    save_tail()
    try:
        for stage,tool,args in commands:
            if resume and stage in ('vendor','glbl','phy'):continue
            if resume and stage=='csi':args=['--2008',TB]
            if rearm:
                for name,digest in record['source_sha256'].items():assert sha(ROOT/name)==digest,name+' changed during regression'
            command=[str(BIN/(tool+'.bat')),*map(str,args)];item=dict(stage=stage,command=command,status='STARTED');record['commands'].append(item);save_tail()
            print(('REARM_INTEGRATION_' if rearm else 'TAIL_INTEGRATION_')+stage.upper(),flush=True)
            with (work/(stage+'.log')).open('w') as f:r=subprocess.run(command,cwd=work,stdout=f,stderr=subprocess.STDOUT,timeout=300)
            item.update(exit_code=r.returncode,log_sha256=sha(work/(stage+'.log')))
            assert r.returncode==0,stage+' failed'
            if stage=='simulate':
                import re
                log=(work/'simulate.log').read_text()
                assert 'CAMERA_CRC_LINK_PHASE_PASS' in log and 'CAMERA_CRC_LINK_PASS' in log
                assert not re.findall(r'(?im)^(Fatal|Error|Failure):',log)
                assert set(map(int,re.findall(r'SERIAL_PHASE_UI=(\d+)',log)))==set(range(8))
                assert len(re.findall('PPI_PACKET_OK',log))==9
            item['status']='PASS';save_tail()
        record['status']='PASS_SERIAL_PHY_CSI_ALL8_PHASES_10240_PIXELS_CRC_7GOOD_1BAD'
    except BaseException as exc:
        record.update(status='FAIL_STOP',error=type(exc).__name__+': '+str(exc));save_tail();raise
    save_tail();print(record['status'],flush=True)


def rearm_startup(prepare_only=False):
    """Reuse the unchanged startup/reset stimulus and audit in a fresh scope."""
    import importlib.util
    driver=ROOT/'color_test/sim/run_dphy_rate93.py'
    spec=importlib.util.spec_from_file_location('rearm_rate93_driver',driver)
    rate=importlib.util.module_from_spec(spec);spec.loader.exec_module(rate)
    original=rate.RECORD
    prior=json.loads((original/'attempt.json').read_text())
    assert prior['status']=='PASS_SCOPED_FIXED_RATE_FUNCTION_CDC_ROUTED_BUDGET'
    fixtures=[ROOT/'color_test/sim'/name for name in ('tb_dphy_rate93.vhd','check_dphy_rate93.tcl','run_dphy_rate93.py')]
    for p in fixtures:assert sha(p)==prior['execution_source_sha256'][p.relative_to(ROOT).as_posix()],p
    integrated=OUT/'rx_fault_1/rearm_1/serial_integration/result.json'
    integration=json.loads(integrated.read_text())
    assert integration['status']=='PASS_SERIAL_PHY_CSI_ALL8_PHASES_10240_PIXELS_CRC_7GOOD_1BAD'
    sources=[PHY/(n+'.vhd') for n in PHY_NAMES]
    for p in sources:assert sha(p)==integration['source_sha256'][p.relative_to(ROOT).as_posix()],p
    assert len(rate.COMPLETE)==20
    rate.RECORD=OUT/'rx_fault_1/rearm_1/startup_reset'
    rate.WORK=rate.RECORD/'sim'
    assert not rate.RECORD.exists(),'Preserve prior startup/reset attempts'
    assert rate.RECORD!=original
    assert rate.run.__globals__['RECORD']==rate.RECORD==rate.save.__globals__['RECORD']
    assert rate.run.__globals__['WORK']==rate.WORK==rate.audit.__globals__['WORK']
    assert rate.RECORD.is_relative_to(OUT/'rx_fault_1/rearm_1')
    assert rate.WORK.is_relative_to(rate.RECORD)
    if prepare_only:
        print(json.dumps(dict(status='PASS_READONLY_STARTUP_ROUTING',
            old_record=str(original),new_record=str(rate.RECORD),new_work=str(rate.WORK),
            run_save_audit_globals_match_new_paths=True,writes=0,tool_starts=0),indent=2),flush=True)
        return
    record=dict(status='PREPARED',closed=False,functional_rounds_used=0,tool_start_attempts=0,
        source_names=PHY_NAMES,protected_sha256={integrated.relative_to(ROOT).as_posix():sha(integrated)},
        execution_source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sources+fixtures+[Path(__file__)]},
        plan=prior['plan'],full_builds=0,board_operations=0,
        scope='unchanged existing rate93 UNISIM startup,all8 nominal/early phases,stopped-clock reset,disable/clock-loss relock;20 complete cases on both lanes;not CSI/production/board signoff',
        validation_attempt=1,validation_attempts_max=2,fixture_errors=[])
    rate.RECORD.mkdir();rate.save(record)
    try:
        rate.run(record)
        result=rate.audit(record)
        assert result['complete_lane_cases']==40,'Incomplete startup/reset coverage'
    except Exception as exc:
        result=dict(status='STOP_TOOL_OR_FIXTURE',error=type(exc).__name__+': '+str(exc))
    for group in ('protected_sha256','execution_source_sha256'):
        for name,digest in record[group].items():
            if sha(ROOT/name)!=digest:result=dict(status='STOP_SOURCE_CHANGED',error=name)
    result['artifact_sha256']={p.relative_to(ROOT).as_posix():sha(p) for p in rate.WORK.iterdir() if p.is_file()} if rate.WORK.exists() else {}
    result['no_implementation_BIT_or_board']=True
    (rate.RECORD/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    record.update(status=result['status'],closed=True,actual_stimulus_runs=int((rate.WORK/'stimulus.txt').exists()),
        design_failures=int(result['status']=='FAIL_FUNCTIONAL'),result_sha256=sha(rate.RECORD/'result.json'))
    rate.save(record)
    print(json.dumps(dict(status=result['status'],complete_lane_cases=result.get('complete_lane_cases'),
        failures=len(result.get('failures',[])),error=result.get('error')),indent=2),flush=True)
    if result['status']!='PASS_FUNCTIONAL_MODEL_ONLY':raise RuntimeError('Startup/reset regression rejected; see '+str(rate.RECORD/'result.json'))

if __name__ == '__main__':
    assert len(sys.argv)==2 and sys.argv[1] in ('prepare','run','short-tail','repair','tail-integration','tail-integration-resume','tail-integration-fix2','rearm-integration','rearm-startup','rearm-startup-prepare')
    if sys.argv[1] in ('rearm-startup','rearm-startup-prepare'):rearm_startup(sys.argv[1]=='rearm-startup-prepare')
    elif sys.argv[1]=='rearm-integration':tail_integration(rearm=True)
    elif sys.argv[1].startswith('tail-integration'):tail_integration(sys.argv[1]=='tail-integration-resume',sys.argv[1]=='tail-integration-fix2')
    else:prepare() if sys.argv[1]=='prepare' else run(sys.argv[1]=='short-tail',sys.argv[1]=='repair')
