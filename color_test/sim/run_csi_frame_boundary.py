"""Bounded offline LLP boundary regression, using the existing vendor FIFOs.

The before source is one evidence file, not a second engineering project.
No synthesis, implementation, hardware access, or artifact export is performed.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'color_test/build/csi_frame_boundary_1'
BIN = Path('D:/Xilinx/Vivado/2023.1/bin')
CSI = ROOT / 'color_test/repo/ip/MIPI_CSI_2_RX/hdl'
GEN = ROOT / 'color_test/color_test.srcs/sources_1/bd/system/ip/system_MIPI_CSI_2_RX_0_0/hdl'
TB = ROOT / 'color_test/sim/tb_csi_frame_boundary.vhd'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    mode = sys.argv[1]
    assert mode in ('negative', 'candidate')
    review_path = OUT / 'review.json'
    record = json.loads(review_path.read_text())
    key = 'negative_control' if mode == 'negative' else 'candidate_rounds'
    limit = 1 if mode == 'negative' else 2
    resume_setup = '--resume-setup' in sys.argv[2:]
    resume_fixture = '--resume-fixture' in sys.argv[2:]
    resume_tail = '--resume-tail-capacity' in sys.argv[2:]
    resume = resume_setup or resume_fixture or resume_tail
    if resume:
        attempt = record['runs'][-1]
        assert attempt['mode'] == mode and attempt['status'] == 'FAIL_STOP'
        if resume_setup:
            assert not any(c['stage'].startswith('simulate') for c in attempt['commands'])
            assert not attempt.get('setup_retry_used'), 'Same-method setup retries exhausted'
            attempt['setup_retry_used'] = True
        elif resume_fixture:
            assert not attempt.get('fixture_retry_used'), 'Same-cause fixture retries exhausted'
            previous_log = OUT / attempt['commands'][-1]['log']
            assert 'BOUNDARY_FIXTURE input FIFO capacity exceeded' in previous_log.read_text()
            attempt['fixture_retry_used'] = True
        else:
            assert not attempt.get('tail_capacity_retry_used'), 'Same-cause tail fixture retries exhausted'
            previous_log = OUT / attempt['commands'][-1]['log']
            assert 'BOUNDARY_FIXTURE no held final payload' in previous_log.read_text()
            attempt['tail_capacity_retry_used'] = True
        number = attempt['number']
    else:
        assert record['attempts'][key] < limit, 'Stopped: attempt budget exhausted'
        number = record['attempts'][key] + 1
    work = OUT / f'{mode}_{number}'
    work.mkdir(exist_ok=resume)
    llp = OUT / 'LLP.before.vhd' if mode == 'negative' else CSI / 'LLP.vhd'
    names = 'CsiDebugLib CsiSyncAsync CsiSyncAsyncReset ECC CRC16_behavioral'.split()
    sources = [CSI / (n + '.vhd') for n in names] + [llp, TB]
    vendor = [GEN / n / 'sim' / (n + '.v') for n in ('cdc_fifo', 'line_buffer')]
    identity = {str(p.relative_to(ROOT)): sha(p) for p in sources + vendor + [Path(__file__)]}
    if resume:
        attempt['source_sha256_after_setup_fix'] = identity
        attempt['status'] = 'RUNNING'
    else:
        attempt = dict(mode=mode, number=number, status='RUNNING', source_sha256=identity, commands=[])
        record['attempts'][key] = number
        record.setdefault('runs', []).append(attempt)

    def save():
        review_path.write_text(json.dumps(record, indent=2) + '\n')

    def run(stage, tool, args, expected_failure=False):
        previous = [c for c in attempt['commands'] if c['stage'] == stage]
        if resume and previous and previous[-1].get('returncode') == 0 and stage in ('compile_vendor', 'compile_glbl'):
            return
        suffix = '_tail_capacity_retry' if resume_tail else '_fixture_retry' if resume_fixture else '_setup_retry'
        path = work / (stage + (suffix if previous else '') + '.log')
        command = [str(BIN / (tool + '.bat')), *map(str, args)]
        item = dict(stage=stage, command=command)
        attempt['commands'].append(item)
        save()
        print(stage + '_START', flush=True)
        with path.open('w') as log:
            # cmd's batch argument parsing treats an unquoted '=' as a separator.
            # Quote only these controlled generic tokens in the actual command.
            native_command = subprocess.list2cmdline(command)
            native_command = re.sub(r'\b(HEIGHT=\d+|STRESS_TAIL=(?:true|false))\b', r'"\1"', native_command)
            done = subprocess.run(native_command, cwd=work, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        content = path.read_text(errors='replace')
        item['returncode'] = done.returncode
        item['log'] = str(path.relative_to(OUT))
        item['errors'] = [line for line in content.splitlines()
                          if re.search(r'ERROR:|Fatal:|BOUNDARY_(ERROR|FIXTURE|SUMMARY|FAIL|PASS|TAIL)', line)][-18:]
        save()
        if expected_failure:
            ok = 'BOUNDARY_FAIL clean' in content and 'BOUNDARY_ERROR blocked packet register changed SOF/data' in content
        else:
            ok = done.returncode == 0 and 'ERROR:' not in content and 'Fatal:' not in content
            if tool == 'xsim':
                ok = ok and 'BOUNDARY_PASS' in content and 'BOUNDARY_ERROR' not in content
        if not ok:
            attempt['status'] = 'FAIL_STOP'
            record['status'] = 'OFFLINE_FAIL_STOP'
            save()
            print('\n'.join(item['errors']), flush=True)
            raise SystemExit(1)
        print(stage + '_PASS', flush=True)

    save()
    run('compile_vendor', 'xvlog', vendor)
    run('compile_glbl', 'xvlog', [BIN.parent / 'data/verilog/src/glbl.v'])
    run('compile_vhdl', 'xvhdl', ['--2008', *sources])
    common = ['-debug', 'typical', '-L', 'fifo_generator_v13_2_8', '-L', 'axis_data_fifo_v2_0_10',
              '-L', 'axis_infrastructure_v1_1_0', '-L', 'xpm', '-L', 'unisims_ver', '-L', 'unisim', '-L', 'secureip',
              '-timescale', '1ns/1fs', '-timeprecision_vhdl', '1fs']
    cases = [('tail', 8, True)]
    if mode == 'candidate':
        cases.append(('full720', 720, False))
    (work / 'run.tcl').write_text('run all\nquit\n')
    for case, height, stress in cases:
        snap = 'boundary_' + case
        run('elaborate_' + case, 'xelab', ['work.tb_csi_frame_boundary', 'work.glbl', '-s', snap,
            '-generic_top', f'HEIGHT={height}', '-generic_top', f'STRESS_TAIL={str(stress).lower()}', *common])
        run('simulate_' + case, 'xsim', [snap, '-tclbatch', 'run.tcl'], mode == 'negative')
    attempt['status'] = 'EXPECTED_COUNTEREXAMPLE' if mode == 'negative' else 'PASS_OFFLINE'
    record['status'] = attempt['status']
    save()
    print(attempt['status'], flush=True)


if __name__ == '__main__':
    main()
