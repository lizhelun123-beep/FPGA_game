"""One frozen negative control and one candidate;actual byte HDL plus serial regression."""
import hashlib,importlib.util,json,re,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CASE=ROOT/'color_test/build/camera_crc_link'
OUT=CASE/'upstream_1'
PHY=ROOT/'color_test/repo/ip/MIPI_D_PHY_RX/hdl'
BIN=Path('D:/Xilinx/Vivado/2023.1/bin')
PATH_RESUME=sys.argv[1:]==['baseline-path-fix']
MODE='baseline' if PATH_RESUME else sys.argv[1]
assert sys.argv[1:] in (['baseline'],['fixed'],['baseline-path-fix'])
WORK=OUT/('tail_'+MODE)
assert WORK.exists() if PATH_RESUME else not WORK.exists(),'Preserve prior native attempt'
if not PATH_RESUME:WORK.mkdir()
spec=importlib.util.spec_from_file_location('upstream',CASE/'analyze_upstream.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
samples=u.load_samples()
record=dict(status='RUNNING',scope='real raw/LP replay,canonical HS byte logic;primitive output forced;not electrical/full-PHY/board acceptance',mode=MODE,commands=[],full_builds=0,board_operations=0)
if PATH_RESUME:
    record=json.loads((WORK/'result.json').read_text());assert record['status']=='FAIL_STOP' and record['observed_counts']==[]
    assert 'No such HDL object /tb_camera_crc_tail/lanes(0)/dut/dDataIn_int' in (WORK/'simulate.log').read_text()
    assert not record.get('fixture_path_retry')
    record['fixture_path_retry']=dict(count=1,cause='XSim requires escaped VHDL generate-instance names;no simulation ran',prior_error=record.pop('error'))
    (WORK/'simulate.log').rename(WORK/'simulate_path_failure.log');(WORK/'run.tcl').rename(WORK/'run_path_failure.tcl')
    record['status']='RUNNING'
def save():(WORK/'result.json').write_text(json.dumps(record,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=PHY/'HS_Deserializer.vhd'
record['source_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [source,ROOT/'color_test/sim/tb_camera_crc_tail.vhd',Path(__file__),OUT/'packet_analysis.json']}
if MODE=='baseline' and not PATH_RESUME:
    with (OUT/'tail_before_HS_Deserializer.vhd').open('xb') as f:f.write(source.read_bytes())
elif MODE=='fixed':
    prior=json.loads((OUT/'tail_baseline/result.json').read_text())
    assert prior['status']=='PASS_NEGATIVE_CONTROL_REPRODUCED_1604_BYTES_ALL3'
    assert sha(source)!=sha(OUT/'tail_before_HS_Deserializer.vhd')
controls=[];raw=[[],[]];expected=[]
def cycle(reset,lp,case,a=0,b=0):
    controls.append(f'{reset} {lp:02x} {case}\n');raw[0].append(a);raw[1].append(b)
for case,(start,end) in enumerate(u.runs(samples,lambda s:s[2]&3==3)[:3],1):
    for _ in range(20):cycle(1,0,0)
    for _ in range(10):cycle(0,0,case)
    for i in range(start-7,end+11):cycle(0,255 if i>=end-2 else samples[i][3],case,samples[i][0]&255,samples[i][0]>>8)
    for _ in range(10):cycle(0,255,case)
    expected.extend(f'{b:02x}\n' for b in (OUT/f'raw_packet_{case}.bin').read_bytes())
(WORK/'replay_control.txt').write_text(''.join(controls));(WORK/'replay_expected.txt').write_text(''.join(expected))
tcl=[]
for lane in range(2):
    values=['{00 0fs}'];last=0
    for i,value in enumerate(raw[lane]):
        if value!=last:values.append('{%02x %dfs}'%(value,(i+1)*85_714_288));last=value
    tcl.append('add_force -radix hex {/tb_camera_crc_tail/\\lanes(%d)\\/dut/dDataIn_int} '%lane+' '.join(values))
(WORK/'run.tcl').write_text('\n'.join(tcl)+'\nrun all\nquit\n')
names='DPHY_Pkg DphySyncAsync DphySyncAsyncReset DphyDebugLib HS_Deserializer'.split()
commands=[('glbl','xvlog',[BIN.parent/'data/verilog/src/glbl.v']),
 ('compile','xvhdl',['--2008',*[PHY/(n+'.vhd') for n in names],ROOT/'color_test/sim/tb_camera_crc_tail.vhd']),
 ('elaborate','xelab',['work.tb_camera_crc_tail','work.glbl','-debug','all','-s','camera_crc_tail','-L','unisim','-L','unisims_ver','-timescale','1ns/1fs','-timeprecision_vhdl','1fs']),
 ('simulate','xsim',['camera_crc_tail','-tclbatch','run.tcl'])]
save()
try:
    for stage,tool,args in commands:
        if PATH_RESUME and stage!='simulate':continue
        command=[str(BIN/(tool+'.bat')),*map(str,args)]
        item=dict(stage=stage,command=command,status='STARTED');record['commands'].append(item);save()
        print('TAIL_'+MODE.upper()+'_'+stage.upper(),flush=True)
        with (WORK/(stage+'.log')).open('w') as f:r=subprocess.run(command,cwd=WORK,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        log=(WORK/(stage+'.log')).read_text();item.update(exit_code=r.returncode,log_sha256=sha(WORK/(stage+'.log')))
        assert stage=='simulate' or r.returncode==0,stage+' tool failure'
        if stage=='simulate':
            counts=[(int(a),int(b)) for a,b in re.findall(r'TAIL_REPLAY_COUNT case=(\d+) bytes=(\d+)',log)]
            record['observed_counts']=counts
            if MODE=='baseline':
                assert counts==[(1,1604),(2,1604),(3,1604)] and 'TAIL_REPLAY_TRUNCATED' in log
                assert 'TAIL_REPLAY_BYTE_MISMATCH' not in log and 'TAIL_REPLAY_EXCESS' not in log
            else:assert counts==[(1,1606),(2,1606),(3,1606)] and 'TAIL_REPLAY_PASS' in log and 'Fatal:' not in log
        item['status']='PASS_EXPECTED_NEGATIVE_CONTROL' if stage=='simulate' and MODE=='baseline' else 'PASS';save()
    record['status']='PASS_NEGATIVE_CONTROL_REPRODUCED_1604_BYTES_ALL3' if MODE=='baseline' else 'PASS_SCOPED_REAL_RAW_LP_TAIL_REPLAY_ALL3'
except BaseException as exc:
    record.update(status='FAIL_STOP',error=type(exc).__name__+': '+str(exc));save();raise
save();print(record['status'],flush=True)
