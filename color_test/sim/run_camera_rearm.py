"""One frozen negative control and one canonical interburst repair regression.

The byte raw/LP window is real and contiguous. Ref LP timing is reconstructed:
after a legal startup preamble, latest LP bits lead the byte observation by two
byte clocks; an unsampled 11->01->00 request has one fixed 50ns LP01 segment.
The three RefClk phases (0/2/4ns) are fixed coverage, not an optimization scan.
No synthesis, device access, or modification of recorded data occurs here.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT/'color_test/build/camera_crc_link'
CAPTURE = CASE/'rx_fault_1'
BASE = CAPTURE/'rearm_1'
OUT = BASE
PHY = ROOT/'color_test/repo/ip/MIPI_D_PHY_RX/hdl'
BIN = Path('D:/Xilinx/Vivado/2023.1/bin')
PERIOD = 85_714_288
PREAMBLE = 1400
START, END = 359, 3585  # three complete LS/RAW/LE groups; fourth partial excluded
TB = ROOT/'color_test/sim/tb_camera_rearm.vhd'
NAMES = 'DPHY_Pkg DphySyncAsync DphySyncAsyncReset DphyDebugLib HS_Deserializer GlitchFilter DPHY_LaneSFEN'.split()
WIDTHS = (16, 16, 6, 8, 2, 18, 32, 4, 3, 18, 4)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, record):
    path.write_text(json.dumps(record, indent=2)+'\n')


def upstream():
    spec = importlib.util.spec_from_file_location('upstream', CASE/'analyze_upstream.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ecc(header):
    # Independent parity equations for the 24 transmitted CSI-2 header bits.
    equations = ((0,1,2,4,5,7,10,11,13,16,20,21,22,23),
                 (0,1,3,4,6,8,10,12,14,17,20,21,22,23),
                 (0,2,3,5,6,9,11,12,15,18,20,21,22),
                 (1,2,3,7,8,9,13,14,15,19,20,21,23),
                 (4,5,6,7,8,9,16,17,18,19,20,22,23),
                 (10,11,12,13,14,15,16,17,18,19,21,22,23))
    word = int.from_bytes(header[:3], 'little')
    return sum((sum(word >> bit & 1 for bit in eq) & 1) << p
               for p, eq in enumerate(equations))


def samples_and_packets():
    u = upstream()
    samples = u.load_samples(CAPTURE/'receiver_byte_ila.csv', CAPTURE/'hardware_probe_map.tsv',
                             WIDTHS, 4096, 'receiver_byte_ila', 0)
    packets = []
    for first, phase, count, kind in ((361,2,2,'LS'), (379,6,803,'RAW10'), (1197,0,2,'LE'),
                                      (1546,2,2,'LS'), (1564,6,803,'RAW10'), (2382,0,2,'LE'),
                                      (2731,2,2,'LS'), (2749,6,803,'RAW10'), (3567,0,2,'LE')):
        lanes = [[u.aligned(samples, lane, i, phase) for i in range(first, first+count)] for lane in (0,1)]
        packet = bytes(value for pair in zip(*lanes) for value in pair)
        assert packet[0] == {'LS':2, 'RAW10':43, 'LE':3}[kind]
        assert packet[3] == ecc(packet), (first, 'independent header ECC')
        assert all(u.aligned(samples, lane, first-1, phase) == 0xb8 for lane in (0,1))
        if kind == 'RAW10':
            assert packet[:4] == bytes.fromhex('2b40063b') and len(packet) == 1606
            assert u.crc16(packet[4:-2]) == int.from_bytes(packet[-2:], 'little')
        trailers = [u.aligned(samples, lane, first+count, phase) for lane in (0,1)]
        assert all(value in (0,255) for value in trailers)
        packets.append(dict(kind=kind, first=first, phase=phase, lanes=lanes, trailer=trailers,
                            header=packet[:4].hex(), bytes=len(packet),
                            crc=packet[-2:].hex() if kind == 'RAW10' else None))
    return u, samples, packets


def prepare():
    assert OUT.is_dir() and (BASE/'before_HS_Deserializer.vhd').is_file()
    assert (BASE/'before_DPHY_LaneSFEN.vhd').is_file()
    assert not (OUT/'fixture.json').exists(), 'Preserve prior fixture preparation'
    _, samples, packets = samples_and_packets()
    controls = [(-1,255,0) for _ in range(PREAMBLE)]
    controls += [(i,samples[i][3],samples[i][0]) for i in range(START,END+1)]
    controls += [(END+1+i,255,0) for i in range(40)]
    (OUT/'replay_control.txt').write_text(''.join(f'{index} {lp:02x}\n' for index,lp,_ in controls))
    # Ref reconstruction starts legally and is settled before the first real SoT.
    # Nothing is forced in the control FSM, reset bridge, settled bridge, or drain.
    events = [(0,15),(110_000_000_000,5),(110_060_000_000,0)]
    previous = 0
    for i in range(START,END+1):
        # Primitive LP outputs during reset/recovery are not physical LP.
        # Derive idle-to-HS entry from the measured reset bridge release,
        # two byte edges after control reset deassertion. Keep byte inputs
        # unchanged, including the recorded reset-recovery ffff word.
        if MODEL == 2:
            reset = (samples[i][9] >> 4) & 1
            prior_reset = (samples[i-1][9] >> 4) & 1
            if prior_reset and not reset:
                when = (PREAMBLE+1+i-START-2)*PERIOD
                assert previous == 15, 'Idle restart requires preceding physical stop'
                events += [(when-60_000_000,5),(when,0)]
                previous = 0
            if samples[i][4] != 0:
                continue
        lp = samples[i][3]
        current = sum((((lp >> (4*lane)) & 1) | (((lp >> (4*lane+2)) & 1) << 1)) << (2*lane) for lane in (0,1))
        if current != previous:
            when = (PREAMBLE+1+i-START-2)*PERIOD
            if all((previous >> (2*lane) & 3) == 3 and (current >> (2*lane) & 3) == 0 for lane in (0,1)):
                events.append((when-50_000_000,5))
            events.append((when,current))
            previous = current
    events.append(((len(controls)-30)*PERIOD,15))
    assert all(a[0] < b[0] for a,b in zip(events,events[1:]))
    (OUT/'ref_lp_control.txt').write_text(''.join(f'{when} fs {lp:x}\n' for when,lp in events))
    tcl = []
    witness = []
    for replica in range(3):
        for lane in range(2):
            base = '/tb_camera_rearm/\\clocks(%d)\\/\\lanes(%d)\\/dut/HSDeserializerX' % (replica,lane)
            values = ['{00 0fs}']; last = 0
            for i,(_,_,raw) in enumerate(controls):
                value = raw >> (8*lane) & 255
                if value != last:
                    values.append('{%02x %dfs}' % (value,(i+1)*PERIOD)); last = value
            tcl.append('add_force -radix hex {'+base+'/dDataIn_int} '+' '.join(values))
            for signal in ('dLogicRst','dSerdesRst','dSettled','dDrainBusy','dSyncHard_int','dSyncSoft_int','dSyncErr_int','dAlignment_int','dLPStop_q'):
                witness.append('{'+base+'/'+signal+'}')
    tcl += ['open_vcd internal_witness.vcd', 'log_vcd '+' '.join(witness), 'run all', 'close_vcd', 'quit']
    (OUT/'run.tcl').write_text('\n'.join(tcl)+'\n')
    identities = [CAPTURE/'receiver_byte_ila.csv', CAPTURE/'hardware_probe_map.tsv',
                  CASE/'analyze_upstream.py', TB, Path(__file__),
                  BASE/'before_HS_Deserializer.vhd', BASE/'before_DPHY_LaneSFEN.vhd',
                  OUT/'replay_control.txt', OUT/'ref_lp_control.txt', OUT/'run.tcl']
    record = dict(status='PREPARED', raw_window=[START,END], real_byte_cycles=END-START+1,
        fixed_ref_phases_ns=[0,2,4], model=MODEL, Ref_LP_model='legal startup preamble;valid byte-LP leads by2byte cycles;missed11->00 request has fixed50ns01;model2 ignores reset-invalid LP and derives new idle entry from measured Serdes reset release minus2byte edges with60ns01',
        scope='actual canonical byte HDL and full lane RefFSM/reset/drain path; primitive data forced, LP byte outputs supplied; reconstructed Ref timing is not simultaneous captured Ref waveform or electrical acceptance',
        full_builds=0,board_operations=0,packets=packets,
        source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in identities})
    save(OUT/'fixture.json',record)
    print('REARM_PREPARED 9 physical packets,3 exact RAW10 CRC fields,3 fixed Ref phases',flush=True)


def decode_output(path):
    replicas = [[[] for _ in range(2)] for _ in range(3)]
    rows = [[[] for _ in range(2)] for _ in range(3)]
    for line in path.read_text().splitlines():
        fields = line.split(); assert len(fields) == 18
        replica,index = map(int,fields[:2]); assert 0 <= replica < 3
        for lane in (0,1):
            segment = fields[2+lane*8:10+lane*8]
            valid = int(segment[0]); value = int(segment[1],16)
            status = list(map(int,segment[2:]))
            assert valid in (0,1) and 0 <= value < 256
            rows[replica][lane].append((index,valid,value,*status))
    for replica in range(3):
        for lane in (0,1):
            active = None
            for index,valid,value,*_ in rows[replica][lane]:
                if valid:
                    if active is None: active = dict(first=index,last=index,data=[])
                    active['last']=index;active['data'].append(value)
                elif active is not None:
                    replicas[replica][lane].append(active);active=None
            assert active is None, 'No output run may be cut by fixture end'
    return replicas,rows


def check(mode,work,record):
    u,samples,packets = samples_and_packets()
    observed,rows = decode_output(work/'ppi_observed.txt')
    record['runs'] = observed
    checks=[]
    if mode == 'baseline':
        for replica in range(3):
            for lane in (0,1):
                runs=observed[replica][lane]
                assert runs and runs[0]['data'][:2] == packets[0]['lanes'][lane], 'Negative control must first acquire correct LS'
                long_runs=[run for run in runs if len(run['data']) >= 800]
                assert len(long_runs)==3, 'Negative control must reproduce all3 bad long bursts'
                for run,expected in zip(long_runs,[p for p in packets if p['kind']=='RAW10']):
                    assert run['data'][:2] != expected['lanes'][lane][:2], 'Old RAW10 header unexpectedly valid'
                    fits=[]
                    for phase in range(8):
                        for delay in range(2,7):
                            if all(0 <= run['first']+j-delay < len(samples) and
                                   u.aligned(samples,lane,run['first']+j-delay,phase)==value
                                   for j,value in enumerate(run['data'])): fits.append([phase,delay])
                    assert len(fits)==1 and fits[0][0]==2, ('Negative stale alignment not reproduced',replica,lane,fits)
                    checks.append(dict(replica=replica,lane=lane,kind='negative_stale_phase2',whole_run_fit=fits[0],bytes=len(run['data'])))
        record['status']='PASS_NEGATIVE_CONTROL_REPRODUCED_STALE_PHASE2_ALL3_RAW_ALL3_REF_PHASES'
    else:
        for replica in range(3):
            for lane in (0,1):
                runs=observed[replica][lane]
                assert len(runs)==9, ('Candidate must produce exactly9 whole physical bursts',replica,lane,len(runs))
                for number,(run,expected) in enumerate(zip(runs,packets),1):
                    want=expected['lanes'][lane];got=run['data']
                    assert got[:len(want)]==want, ('REARM_BYTE_MISMATCH',replica,lane,number,
                        next((i for i,(a,b) in enumerate(zip(got,want)) if a!=b),min(len(got),len(want))))
                    assert len(want)<=len(got)<=len(want)+1, ('REARM_TRUNCATED_OR_EXCESS',replica,lane,number,len(got),len(want))
                    assert not got[len(want):] or got[len(want):]==[expected['trailer'][lane]], 'Only first exact physical literal HStrail byte may be emitted'
                    scored=[row for row in rows[replica][lane] if run['first']<=row[0]<=run['last']]
                    assert all(row[6]==1 and row[7]==0 and row[8]==0 for row in scored), 'Every emitted packet requires fresh hard SoT without soft/error flags'
                    if number>1:
                        previous=runs[number-2]
                        gap=[row for row in rows[replica][lane] if previous['last'] < row[0] < run['first']]
                        assert any(row[3]==0 for row in gap), ('SoT not cleared between bursts',replica,lane,number)
                        assert any(row[5]==0 for row in gap), ('Settled did not clear between bursts',replica,lane,number)
                    checks.append(dict(replica=replica,lane=lane,packet=number,kind=expected['kind'],phase=expected['phase'],
                                       expected_bytes=len(want),observed_bytes=len(got),whole_packet_exact=True))
        record['status']='PASS_REAL_SHORT_GAP_ALL9_PACKETS_ALL3_REF_PHASES_EXACT_CRC_TAILS'
    record['checks']=checks


def run(mode):
    assert mode in ('baseline','fixed')
    fixture=json.loads((OUT/'fixture.json').read_text())
    for name,digest in fixture['source_sha256'].items():
        assert sha(ROOT/name)==digest, 'Fixture identity changed: '+name
    if mode=='fixed':
        prior=json.loads((OUT/'baseline/result.json').read_text())
        assert prior['status']=='PASS_NEGATIVE_CONTROL_REPRODUCED_STALE_PHASE2_ALL3_RAW_ALL3_REF_PHASES'
        assert sha(PHY/'HS_Deserializer.vhd') != sha(BASE/'before_HS_Deserializer.vhd')
    work=OUT/mode; assert not work.exists(), 'Preserve prior native attempt'
    work.mkdir()
    for name in ('replay_control.txt','ref_lp_control.txt','run.tcl'):
        (work/name).write_bytes((OUT/name).read_bytes())
    source_paths=[]
    for name in NAMES:
        path=BASE/('before_'+name+'.vhd') if mode=='baseline' and name in ('HS_Deserializer','DPHY_LaneSFEN') else PHY/(name+'.vhd')
        source_paths.append(path)
    record=dict(status='RUNNING',mode=mode,scope=fixture['scope'],commands=[],full_builds=0,board_operations=0,
                source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in source_paths+[TB,Path(__file__)]})
    commands=[('glbl','xvlog',[BIN.parent/'data/verilog/src/glbl.v']),
        ('compile','xvhdl',['--2008',*source_paths,TB]),
        ('elaborate','xelab',['work.tb_camera_rearm','work.glbl','-debug','all','-s','camera_rearm',
            '-L','unisim','-L','unisims_ver','-timescale','1ns/1fs','-timeprecision_vhdl','1fs']),
        ('simulate','xsim',['camera_rearm','-tclbatch','run.tcl'])]
    save(work/'result.json',record)
    try:
        for stage,tool,args in commands:
            command=[str(BIN/(tool+'.bat')),*map(str,args)]
            item=dict(stage=stage,command=command,status='STARTED');record['commands'].append(item);save(work/'result.json',record)
            print('REARM_'+mode.upper()+'_'+stage.upper(),flush=True)
            with (work/(stage+'.log')).open('w') as f:
                result=subprocess.run(command,cwd=work,stdout=f,stderr=subprocess.STDOUT,timeout=180)
            item.update(exit_code=result.returncode,log_sha256=sha(work/(stage+'.log')))
            text=(work/(stage+'.log')).read_text(errors='replace')
            assert result.returncode==0, stage+' native tool failure'
            if stage=='simulate':
                assert 'REARM_REPLAY_COMPLETED' in text and 'Fatal:' not in text
                assert (work/'internal_witness.vcd').stat().st_size > 1000
            item['status']='PASS';save(work/'result.json',record)
        check(mode,work,record)
    except BaseException as exc:
        record.update(status='FAIL_STOP',error=type(exc).__name__+': '+str(exc));save(work/'result.json',record);raise
    save(work/'result.json',record);print(record['status'],flush=True)


if __name__=='__main__':
    assert len(sys.argv)==2 and sys.argv[1] in ('prepare','baseline','fixed','prepare-v2','baseline-v2','fixed-v2')
    MODE = sys.argv[1].removesuffix('-v2')
    MODEL = 2 if sys.argv[1].endswith('-v2') else 1
    if MODEL == 2:
        OUT = BASE/'model_2'
        if MODE == 'prepare': OUT.mkdir()
    if MODE=='prepare': prepare()
    else: run(MODE)
