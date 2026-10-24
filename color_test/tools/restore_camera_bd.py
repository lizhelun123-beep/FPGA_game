"""Restore camera cells from this repository into its canonical display BD.

Preserve the qualified display cells/reset nets. No second project, foreign BD,
XDC, driver or BOOT is created. Native Vivado validation is the next gate.
"""
from pathlib import Path
import copy
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'color_test/build/pl_rate93_production'
RELATIVE = 'color_test/color_test.srcs/sources_1/bd/system/system.bd'


def main():
    out = OUT / 'restore_20261022'
    out.mkdir(exist_ok=False)
    status = json.loads((OUT / 'status_cdc_2/script_path_retry.json').read_text())
    assert status['status'] == 'PASS_STATUS_CDC_AXI_RESET_SOURCE_STOP'
    frequency = ROOT / ('color_test/build/dphy_observer_140/shared_reset_audit/fixture_package/'
        'fixed_implementation/mmio_contract/frequency_20261022/board_receipts/frequency_receipt.json')
    assert json.loads(frequency.read_text())['pass']
    path = ROOT / RELATIVE
    before = path.read_bytes()
    original = subprocess.check_output(['git', 'show', 'HEAD:' + RELATIVE], cwd=ROOT)
    old = json.loads(original)['design']
    doc = json.loads(before)
    current = doc['design']
    added = [n for n in old['components'] if n not in current['components']]
    assert set(added) == {'AXI_BayerToRGB_0', 'AXI_GammaCorrection_0', 'MIPI_D_PHY_RX_0',
        'axi_mem_intercon_1', 'axi_vdma_1', 'proc_sys_reset_200M', 'MIPI_CSI_2_RX_0',
        'axis_subset_converter_0', 'axis_color_highlight_0'}
    assert all(n in current['components'] for n in ['display_rst_axis', 'display_rst_pixel', 'axi_dynclk_0'])
    (out / 'system.bd.before').write_bytes(before)
    for name in added + ['ps7_0_axi_periph', 'xlconcat_0']:
        current['components'][name] = copy.deepcopy(old['components'][name])
        current['design_tree'][name] = copy.deepcopy(old['design_tree'][name])
    current['components'].pop('display_irq_zero')
    current['design_tree'].pop('display_irq_zero')
    # Restore full AXI address allocation and camera connections. Display-only
    # M00/M01/M02 numbering differs; use the old full interconnect consistently.
    current['interface_ports'].update(copy.deepcopy(old['interface_ports']))
    current['ports'] = copy.deepcopy(old['ports'])
    current['interface_nets'] = copy.deepcopy(old['interface_nets'])
    current['addressing'] = copy.deepcopy(old['addressing'])
    current['components']['processing_system7_0']['addressing'] = copy.deepcopy(old['components']['processing_system7_0']['addressing'])
    nets = copy.deepcopy(old['nets'])
    for name, net in list(current['nets'].items()):
        endpoints = [p for p in net['ports'] if p != 'xlconcat_0/In2' and not p.startswith('display_irq_zero/')]
        if not endpoints:
            continue
        for target in nets.values():
            target['ports'] = [p for p in target['ports'] if p not in endpoints]
        remaining = nets.get(name, {}).get('ports', [])
        nets[name] = dict(net, ports=list(dict.fromkeys(remaining + endpoints)))
    current['nets'] = {name: net for name, net in nets.items() if len(net['ports']) >= 2}
    endpoints = [p for net in current['nets'].values() for p in net['ports']]
    assert len(endpoints) == len(set(endpoints)), 'Multiple scalar net ownership'
    assert any('xlconcat_0/In2' in net['ports'] and 'axi_vdma_1/s2mm_introut' in net['ports'] for net in current['nets'].values())
    for name, values in {
        'MIPI_D_PHY_RX_0': {'kDebug': 'false', 'kPPISharedEnable': 'true', 'kLPFromLane0': 'false',
                          'kAddDelayClk_ps': '0', 'kAddDelayData0_ps': '0', 'kAddDelayData1_ps': '0'},
        'MIPI_CSI_2_RX_0': {'kDebug': 'false', 'C_S_AXI_LITE_ADDR_WIDTH': '5'},
    }.items():
        for key, value in values.items():
            current['components'][name]['parameters'][key] = {'value': value}
    current['components']['MIPI_CSI_2_RX_0']['vlnv'] = old['components']['MIPI_CSI_2_RX_0']['vlnv'].rsplit(':', 1)[0] + ':1.2'
    current['design_info']['validated'] = 'false'
    for n in ['display_rst_axis', 'display_rst_pixel', 'axi_dynclk_0', 'rgb2dvi_0']:
        assert current['components'][n] == json.loads(before)['design']['components'][n]
    constraint = ROOT / 'color_test/color_test.srcs/constrs_1/new/system.xdc'
    pins = ROOT / 'color_test/color_test.srcs/constrs_1/new/mipi.xdc'
    (out / 'system.xdc.before').write_bytes(constraint.read_bytes())
    (out / 'mipi.xdc.before').write_bytes(pins.read_bytes())
    pin_text = pins.read_text()
    removed = [line for line in pin_text.splitlines() if line.startswith('set_false_path')]
    assert len(removed) == 2 and all('Count_reg' in line for line in removed)
    # Binary counter crossings no longer exist. No counter false-path waiver.
    pins.write_text('\n'.join(line for line in pin_text.splitlines() if line not in removed) + '\n')
    constraint.write_text('''# Measured fixed93.333Mb/s configuration:3035=61,4837=6c.
# Same declared15%/85%UI input model as the qualified fixed-rate OOC.
# No claim of physical-reference tolerance/full-PVT sensor guarantee.
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
create_clock -name mipi_hs_clk -period 21.428571429 -waveform {0 10.714285714} [get_ports dphy_hs_clock_clk_p]
set_input_delay -clock mipi_hs_clk -min -add_delay 1.607142 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -max -add_delay 9.107143 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -min -add_delay 1.607142 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -max -add_delay 9.107143 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
''')
    path.write_text(json.dumps(doc, indent=2) + '\n')
    record = {'status': 'SOURCE_RESTORED_NOT_NATIVE_VALIDATED', 'repository_HEAD': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'BD_before_sha256': hashlib.sha256(before).hexdigest(), 'BD_after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'restored_cells': added, 'preserved_display': ['axi_dynclk_0', 'rgb2dvi_0', 'display_rst_axis', 'display_rst_pixel'],
              'inputs': {'frequency': str(frequency.relative_to(ROOT)), 'status_cdc': 'status_cdc_2/script_path_retry.json'},
              'native_validation': 'NOT_RUN', 'synthesis': 0, 'implementation': 0, 'exports': 0}
    (out / 'restoration.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Canonical camera BD restored from repository;display/reset cells preserved;native validation pending.')


if __name__ == '__main__':
    main()
