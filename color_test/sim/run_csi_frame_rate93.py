"""Bounded full-frame gate before production IP refresh/build; actual vendor FIFOs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "color_test/build/pl_rate93_production"
BIN = Path("D:/Xilinx/Vivado/2023.1/bin")
PREVIOUS = ROOT / ("color_test/build/dphy_observer_140/shared_reset_audit/fixture_package/"
    "fixed_implementation/mmio_contract/finite_observation/budget_probe/rate93_qualified_reset")
NAMES = "CsiDebugLib CsiSyncAsync CsiSyncAsyncReset SimpleFIFO ECC CRC16_behavioral LM LLP MIPI_CSI2_Rx".split()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(a):
    (OUT / "attempt.json").write_text(json.dumps(a, indent=2) + "\n")


def prepare():
    assert not OUT.exists(), "New package already exists; inspect ledger before continuation"
    previous = json.loads((PREVIOUS / "attempt.json").read_text())
    final_source = json.loads((PREVIOUS / "result.json").read_text())['source']
    checked = {}
    for group in (previous['protected_sha256'], final_source['canonical_functional_sha256'],
                  final_source['synthesis_hdl_sha256'], final_source['dependencies_sha256']):
        for name, expected in group.items():
            assert sha(ROOT/name) == expected, "Previous frozen evidence/source changed: " + name
            checked[name] = expected
    OUT.mkdir()
    (OUT / "PROJECT_STATE.before.md").write_bytes((ROOT/"PROJECT_STATE.md").read_bytes())
    status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT)
    (OUT / "git_status.before.txt").write_bytes(status)
    csi = ROOT/"color_test/repo/ip/MIPI_CSI_2_RX/hdl"
    generated = ROOT/"color_test/color_test.srcs/sources_1/bd/system/ip/system_MIPI_CSI_2_RX_0_0/hdl"
    sources = [csi/(n+".vhd") for n in NAMES]
    sources += [generated/n/"sim"/(n+".v") for n in ("cdc_fifo", "line_buffer")]
    sources += [ROOT/"color_test/sim/tb_csi_frame_rate93.vhd", Path(__file__)]
    a = dict(status="PREPARED", closed=False, authorization="2026-10-21 current user: production receiver integration, full CSI/startup recovery, IP generation, production builds and board tests authorized; preserve gates/stopped routes",
        previous_result_sha256=sha(PREVIOUS/"result.json"), previous_frozen_identity_count=len(checked),
        previous_checked_sha256=checked, configuration="fixed93.333333Mb/s c0/d12 two lanes 1280x720 RAW10/BGGR; sensor proposed3035=61,4837=6C; same board/front-end/pins/Bank supply",
        scope="first cheapest production CSI gate: PPI-level complete images and explicit reset recovery using existing actual generated vendor FIFOs; not PHY/full-top/board signoff",
        source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources},
        limits=dict(design_rounds=2, same_cause_failures=2, candidate_scan=False, build_requires_functional_gate=True, board_requires_same_generation_production_gates=True),
        functional_rounds_used=0, synthesis_used=0, implementation_used=0, bit_generated=0, board_connections=0, temporary_loads=0, sensor_stream_seconds=0,
        commands=[], setup_errors=["Initial preparation compared historical synthesis entry hash to the later report-only entry; no native tool launched. Corrected to final result canonical HDL/dependency identities and immutable evidence."], design_failures=[], created_utc=now())
    save(a)
    print("PREPARED frozen prior identity and actual FIFO simulation wrappers", flush=True)


def run(a):
    assert not a['closed'] and not a.get('simulation_completed'), "Closed/completed package cannot be rerun"
    for name, expected in a['source_sha256'].items():
        assert sha(ROOT/name) == expected, "Execution identity changed: " + name
    revision = a.get('active_revision', 1)
    work = OUT / ('sim' if revision == 1 else 'sim' + str(revision))
    work.mkdir(exist_ok=True)
    csi = ROOT/"color_test/repo/ip/MIPI_CSI_2_RX/hdl"
    gen = ROOT/"color_test/color_test.srcs/sources_1/bd/system/ip/system_MIPI_CSI_2_RX_0_0/hdl"
    (work/"run.tcl").write_text('''run all
set report [open final_internal.txt w]
foreach name {stage rstn en epoch frames pixels crc_count packet_count ovf bc byte_run vv vl vu vd ready} {
  puts $report "$name=[get_value -radix hex /tb_csi_frame_rate93/$name]"
}
foreach name {mIsHeader mECC_Valid mECC_Error mDT mWordCount mCountPacket mPacketEndPending mCRC_Out mCRC_Sent mFIFO_Tlast mFIFO_Tvalid mFIFO_Tready mRst sRst} {
  puts $report "$name=[get_value -radix hex /tb_csi_frame_rate93/dut/LLP_inst/$name]"
}
close $report
quit
''')
    commands = [
      ("compile_vendor", "xvlog", [gen/n/"sim"/(n+".v") for n in ("cdc_fifo","line_buffer")]),
      ("compile_glbl", "xvlog", [BIN.parent/"data/verilog/src/glbl.v"]),
      ("compile_csi", "xvhdl", ["--2008", *[csi/(n+".vhd") for n in NAMES], ROOT/"color_test/sim/tb_csi_frame_rate93.vhd"]),
      ("elaborate", "xelab", ["work.tb_csi_frame_rate93", "work.glbl", "-debug", "typical", "-s", "csi_frame93", "-L", "fifo_generator_v13_2_8", "-L", "axis_data_fifo_v2_0_10", "-L", "axis_infrastructure_v1_1_0", "-L", "xpm", "-L", "unisims_ver", "-L", "unisim", "-L", "secureip", "-timescale", "1ns/1fs", "-timeprecision_vhdl", "1fs"]),
      ("simulate", "xsim", ["csi_frame93", "-tclbatch", "run.tcl"]),
    ]
    a['status'] = 'FUNCTIONAL_RUNNING'
    save(a)
    for stage, tool, args in commands:
        completed = [c for c in a['commands'] if c['stage']==stage and c.get('revision',1)==revision and c.get('status')=='PASS']
        if completed:
            continue
        if stage=='simulate':
            assert a['functional_rounds_used'] < a['limits']['design_rounds'], 'Design round limit'
            a['functional_rounds_used'] += 1
        tries = sum(c['stage']==stage for c in a['commands'])
        log = work / f"{stage}_{tries+1}.log"
        command = [str(BIN/(tool+".bat")), *map(str,args)]
        item = dict(stage=stage, revision=revision, command=command, started_utc=now(), status='RUNNING', log=str(log.relative_to(OUT)))
        a['commands'].append(item); save(a)
        print(stage.upper()+"_START", flush=True)
        with log.open('w') as f:
            try:
                p = subprocess.run(command, cwd=work, stdout=f, stderr=subprocess.STDOUT, timeout=1800)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = -1
                item['timeout'] = True
        item.update(status='PASS' if rc==0 else 'FAIL', exit_code=rc, completed_utc=now(), log_sha256=sha(log))
        save(a)
        print(stage.upper()+"_EXIT="+str(rc), flush=True)
        if rc:
            a['status']='NATIVE_STAGE_FAILED'; save(a)
            raise SystemExit(rc)
    log = (OUT/a['commands'][-1]['log']).read_text(errors='replace')
    failures = [s for s in log.splitlines() if s.startswith(('Failure:', 'Fatal:', 'Error:'))]
    if failures or 'CSI_FRAME_OBSERVATION_COMPLETE' not in log:
        a['status']='FUNCTIONAL_DESIGN_FAIL' if failures else 'FUNCTIONAL_INCOMPLETE'
        a['design_failures'].append(dict(round=a['functional_rounds_used'], kind='real_design' if failures else 'incomplete', evidence=a['commands'][-1]['log'], failures=failures))
        save(a)
        raise SystemExit('Functional gate failed; retained native logs/internal snapshot; no build or board escalation')
    a['simulation_completed']=True; a['status']='CSI_ENGINE_FULL_FRAME_PASS'; save(a)
    print(a['status'], flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'run':
        run(json.loads((OUT/'attempt.json').read_text()))
    else:
        raise SystemExit('prepare or run required')
