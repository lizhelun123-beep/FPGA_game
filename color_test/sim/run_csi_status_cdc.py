"""Directed native XSIM gate for the production counter/AXI wrapper change."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'color_test/build/pl_rate93_production/status_cdc_1'
VIVADO = Path('D:/Xilinx/Vivado/2023.1')


def main():
    global OUT
    if sys.argv[1:] == ['--resume-script-path']:
        OUT = OUT.with_name('status_cdc_2')
        prior = json.loads((OUT / 'result.json').read_text())
        text = (OUT / 'simulation.log').read_text(errors='replace')
        assert prior['error'] == 'AssertionError: Coverage/completion marker absent'
        assert "couldn't read file" in text and '# run all' not in text
        for name, expected in prior['source_sha256'].items():
            if Path(name).resolve() != Path(__file__).resolve():
                assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
        receipt = OUT / 'script_path_retry.json'
        assert not receipt.exists(), 'Only one same-path script correction'
        result = {'status': 'STARTED', 'reuse': 'same elaborated snapshot;HDL/vendor/fixture hashes unchanged',
                  'previous': 'result.json', 'simulator_process_starts': 1, 'actual_design_simulations': 0}
        receipt.write_text(json.dumps(result, indent=2) + '\n')
        try:
            command = [str(VIVADO / 'bin/xsim.bat'), 'status_cdc', '-tclbatch', 'run.tcl', '-log', 'simulation_path_retry.log']
            with (OUT / 'simulate_path_retry.log').open('w') as log:
                p = subprocess.run(command, cwd=OUT, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            text = (OUT / 'simulation_path_retry.log').read_text(errors='replace')
            result['actual_design_simulations'] = int('# run all' in text)
            assert p.returncode == 0
            assert 'PASS CSI_STATUS_CDC snapshots=19 reset_offsets=6 stopped_source=1 atomic_pair=1 AXI_registers=1' in text
            assert not re.search(r'\b(?:ERROR|FATAL|CRITICAL WARNING):|severity failure|\[XPM_CDC.*(?:Warning|Error)|(?:Warning|Error):.*\[XPM_CDC', text, re.I)
            result['status'] = 'PASS_STATUS_CDC_AXI_RESET_SOURCE_STOP'
            print(result['status'], flush=True)
        except BaseException as exc:
            result.update(status='FAILED_STOP_NO_RETRY', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            receipt.write_text(json.dumps(result, indent=2) + '\n')
        return
    corrected_video_domain = sys.argv[1:] == ['--video-domain-correction']
    if corrected_video_domain:
        prior = json.loads((OUT.with_name('status_cdc_2') / 'script_path_retry.json').read_text())
        assert prior['status'] == 'PASS_STATUS_CDC_AXI_RESET_SOURCE_STOP'
        OUT = OUT.with_name('status_cdc_video_1')
    elif sys.argv[1:] == ['--retry-glbl']:
        prior = json.loads((OUT / 'result.json').read_text())
        assert prior['actual_simulations'] == 0 and prior['error'].startswith('AssertionError: elaborate failed')
        assert "'glbl' is not declared" in (OUT / 'elaborate.log').read_text()
        OUT = OUT.with_name('status_cdc_2')
    else:
        assert not sys.argv[1:]
    OUT.mkdir(exist_ok=True)
    assert not (OUT / 'result.json').exists(), 'Preserve previous native attempt'
    core = ROOT / 'color_test/repo/ip/MIPI_CSI_2_RX/hdl'
    if corrected_video_domain:
        top = (core / 'MIPI_CSI2_RxTop.vhd').read_text()
        engine = (core / 'MIPI_CSI2_Rx.vhd').read_text()
        llp = (core / 'LLP.vhd').read_text()
        assert re.search(r'StatusSnapshot:.*?SourceClk\s*=>\s*video_aclk\s*,', top, re.S)
        assert re.search(r'video_aclk\s*=>\s*video_aclk', top)
        assert re.search(r'MAxisClk\s*=>\s*video_aclk', engine)
        assert re.search(r'PacketStatistics:\s*process\s*\(MAxisClk\)', llp)
        for folder in ('MIPI_CSI_2_RX', 'MIPI_D_PHY_RX'):
            for path in (core.parent.parent / folder / 'hdl').glob('*.vhd'):
                assert not re.search(r'\b(?:entity|of|work\.)\s*ResetBridge\b', path.read_text()), path
    vhdl = [core / (n + '.vhd') for n in ['CsiDebugLib', 'CsiSyncAsync', 'CsiSyncAsyncReset',
        'SimpleFIFO', 'ECC', 'CRC16_behavioral', 'LM', 'LLP', 'MIPI_CSI2_Rx',
        'CSIStatusBridge', 'MIPI_CSI_2_RX_v1_0_S_AXI_LITE', 'MIPI_CSI2_RxTop']]
    test = ROOT / 'color_test/sim/tb_csi_status_cdc.vhd'
    source = vhdl + [test, Path(__file__), VIVADO / 'data/verilog/src/glbl.v',
        VIVADO / 'data/ip/xpm/xpm_VCOMP.vhd', VIVADO / 'data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv']
    result = {'status': 'STARTED', 'scope': 'counter bridge/actual AXI registers plus full wrapper compilation;not full CSI/PHY/top/board',
              'design_rounds': 2 if corrected_video_domain else 1, 'actual_simulations': 0,
              'preparation_correction': 'Removed unused generated FIFO source dependency;this fixture does not elaborate the CSI image core. No native tool launched in initial preparation.',
              'commands': [], 'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source}}
    (OUT / 'run.tcl').write_text('run all\nquit\n')
    commands = [
        ('xpm_vhdl', 'xvhdl', ['--2008', '--work', 'xpm', VIVADO / 'data/ip/xpm/xpm_VCOMP.vhd']),
        ('xpm_verilog', 'xvlog', ['--sv', '--work', 'xpm', VIVADO / 'data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv']),
        ('glbl', 'xvlog', [VIVADO / 'data/verilog/src/glbl.v']),
        ('wrapper', 'xvhdl', ['--2008', '--work', 'csi'] + vhdl),
        ('fixture', 'xvhdl', ['--2008', test]),
        ('elaborate', 'xelab', ['tb_csi_status_cdc', 'glbl', '-L', 'xpm', '-L', 'fifo_generator_v13_2_8',
                               '-L', 'unisims_ver', '--timescale', '1ns/1ps', '-debug', 'typical', '-s', 'status_cdc']),
        ('simulate', 'xsim', ['status_cdc', '-tclbatch', 'run.tcl', '-log', 'simulation.log'])]
    if corrected_video_domain:
        result['source_domain'] = 'video_aclk period7ns;AXI10ns;static wrapper->engine->PacketStatistics binding verified'
        result['not_covered'] = 'No new production synthesis/implementation;full wrapper compiled,not elaborated'
    try:
        for name, tool, args in commands:
            command = [str(VIVADO / 'bin' / (tool + '.bat'))] + [v.as_posix() if isinstance(v, Path) else str(v) for v in args]
            entry = {'stage': name, 'command': command, 'status': 'STARTED'}
            result['commands'].append(entry)
            if name == 'simulate': result['actual_simulations'] += 1
            (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            with (OUT / (name + '.log')).open('w') as log:
                p = subprocess.run(command, cwd=OUT, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            entry.update(exit_code=p.returncode, status='PASS' if p.returncode == 0 else 'FAILED')
            assert p.returncode == 0, name + ' failed;inspect stage log'
        text = (OUT / 'simulation.log').read_text(errors='replace')
        required = 'PASS CSI_STATUS_CDC snapshots=19 reset_offsets=6 stopped_source=1 atomic_pair=1 AXI_registers=1'
        assert required in text, 'Coverage/completion marker absent'
        assert not re.search(r'\b(?:ERROR|FATAL|CRITICAL WARNING):|severity failure|\[XPM_CDC.*(?:Warning|Error)|(?:Warning|Error):.*\[XPM_CDC', text, re.I), 'Simulation/primitive warning'
        result['status'] = 'PASS_STATUS_CDC_AXI_RESET_SOURCE_STOP'
        print(result['status'], flush=True)
    except BaseException as exc:
        result.update(status='FAILED_STOP_NO_RETRY', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
