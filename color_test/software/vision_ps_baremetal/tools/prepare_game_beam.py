"""Prepare standalone beam inputs from one explicit XSA. Never compiles or loads PL."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[4]
LIVE_PLATFORM = Path('color_test/build/vision_ps_baremetal/vision_ps_platform')
LIVE_OUTPUT = Path('color_test/build/vision_ps_baremetal/output/live')
LIVE_XSA_SHA256 = '03ae58ac8483359101e5286931effb0d84544f4b9b6c215572ff88653011e0c8'
LIVE_BIT_SHA256 = 'a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55'
LIVE_ELF_SHA256 = '50391dab817447b9248e36e2596a8a0a6943360c52a81ee0df49c46e5e7d9698'
LIVE_BOOT_SHA256 = 'f1200d4c4cc0ae4bb245e9193a1e9fc57c4e75687bf350b22ff4bb4e99bde47b'
LIVE_VALIDATION_SHA256 = '0c3cb69acc30073efb8855ed03c88745073c24d20d2463a2bdaf8ad6777e2dfe'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_live_baseline(root=ROOT):
    """Verify preserved inputs/outputs, not today's already changed app sources."""
    root = Path(root).resolve()
    manifest = root/LIVE_OUTPUT/'validation.json'
    raw = manifest.read_bytes()
    if digest(raw) != LIVE_VALIDATION_SHA256:
        raise ValueError('Historical live validation manifest changed')
    validation = json.loads(raw.decode('utf-8'))
    verified = {}
    for item in validation['matched_inputs'] + validation['outputs']:
        relative = Path(item['path'])
        target = (root/relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError('Baseline path escaped the repository')
        data = target.read_bytes()
        if len(data) != item['bytes'] or digest(data) != item['sha256']:
            raise ValueError('Historical live artifact changed: ' + item['path'])
        verified[item['path']] = item['sha256']
    required = {
        (LIVE_PLATFORM/'hw/color_test.xsa').as_posix(): LIVE_XSA_SHA256,
        (LIVE_PLATFORM/'hw/color_test.bit').as_posix(): LIVE_BIT_SHA256,
        (LIVE_OUTPUT/'vision_ps_baremetal.elf').as_posix(): LIVE_ELF_SHA256,
        (LIVE_OUTPUT/'BOOT.bin').as_posix(): LIVE_BOOT_SHA256,
    }
    if any(verified.get(k) != v for k, v in required.items()):
        raise ValueError('Manifest is not the recorded historical live baseline')
    return dict(profile='historical_live_20261026', verified_files=len(verified),
                validation_sha256=digest(raw), platform=str(root/LIVE_PLATFORM),
                runtime_evidence='output/build/game_app/jtag_camera_pc_20261026_1/status_live.log',
                runtime_evidence_scope='historical 1442 submissions; not a new application pass')


def inspect_xsa(path, allow_historical_live=False):
    """Check the declared handoff; this is not timing/CDC or board acceptance."""
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(path) as archive:
        hwh = [n for n in archive.namelist() if n.endswith('.hwh')]
        bit = [n for n in archive.namelist() if n.endswith('.bit')]
        if len(hwh) != 1 or len(bit) != 1:
            raise ValueError('Need one HWH and one embedded BIT from the same XSA')
        hwh_data, bit_data = archive.read(hwh[0]), archive.read(bit[0])
    root = ET.fromstring(hwh_data)
    identity = root.find('SYSTEMINFO')
    if identity is None or any(identity.get(k) != v for k, v in
                               {'ARCH': 'zynq', 'DEVICE': '7z020', 'PACKAGE': 'clg400', 'SPEEDGRADE': '-2'}.items()):
        raise ValueError('Standalone target must be xc7z020clg400-2')
    modules = {m.get('INSTANCE'): m for m in root.iter('MODULE')}

    def params(name):
        if name not in modules:
            raise ValueError('Missing hardware module: ' + name)
        return {p.get('NAME'): p.get('VALUE') for p in modules[name].iter('PARAMETER')}

    for name, required in {
        'axi_vdma_0': {'C_INCLUDE_MM2S': '1', 'C_INCLUDE_S2MM': '0', 'C_NUM_FSTORES': '3',
                       'C_M_AXIS_MM2S_TDATA_WIDTH': '24', 'C_ENABLE_VIDPRMTR_READS': '1'},
        'axi_vdma_1': {'C_INCLUDE_MM2S': '0', 'C_INCLUDE_S2MM': '1', 'C_NUM_FSTORES': '3',
                       'C_S_AXIS_S2MM_TDATA_WIDTH': '24', 'C_ENABLE_VIDPRMTR_READS': '1'},
        'MIPI_D_PHY_RX_0': {'kNoOfDataLanes': '2'},
        'MIPI_CSI_2_RX_0': {'kVersionMajor': '1',
                            'kTargetDT': 'RAW10', 'C_M_AXIS_COMPONENT_WIDTH': '10', 'C_M_AXIS_TDATA_WIDTH': '40'},
        'axis_color_highlight_0': {'ENABLE_HIGHLIGHT': '0'},
    }.items():
        actual = params(name)
        if any(actual.get(k) != v for k, v in required.items()):
            raise ValueError('Unsupported hardware contract: ' + name)
    csi = params('MIPI_CSI_2_RX_0')
    historical = csi.get('kVersionMinor') == '1'
    if csi.get('C_S_AXI_LITE_ADDR_WIDTH') != ('4' if historical else '5'):
        raise ValueError('CSI register aperture does not match its status ABI')
    if historical:
        if (not allow_historical_live or digest(raw) != LIVE_XSA_SHA256 or
                digest(bit_data) != LIVE_BIT_SHA256):
            raise ValueError('CSI1.1 is permitted only for the exact historical live XSA/BIT')
    elif csi.get('kVersionMinor') not in ('2', '3'):
        raise ValueError('Unsupported CSI status ABI')
    params('AXI_GammaCorrection_0')
    params('vtg')
    params('axi_dynclk_0')
    ready = [p for p in modules['axi_dynclk_0'].iter('PORT') if p.get('NAME') == 'DISPLAY_READY_O']
    if bool(ready) == historical:
        raise ValueError('Display clock ABI does not match the selected hardware profile')
    stream_clocks = []
    for name, port, frequency in (('MIPI_CSI_2_RX_0', 'video_aclk', 142857132),
                                  ('axi_vdma_1', 's_axis_s2mm_aclk', 142857132),
                                  ('axi_vdma_0', 'm_axis_mm2s_aclk', 142857132),
                                  ('axi_dynclk_0', 'REF_CLK_I', 100000000)):
        ports = [p for p in modules[name].iter('PORT') if p.get('NAME') == port]
        if len(ports) != 1 or abs(int(ports[0].get('CLKFREQUENCY', '0'))-frequency) > 2:
            raise ValueError('Unsupported declared clock: ' + name + '/' + port)
        if frequency == 142857132:
            stream_clocks.append(ports[0].get('SIGNAME'))
    if len(set(stream_clocks)) != 1 or stream_clocks[0] != 'processing_system7_0_FCLK_CLK1':
        raise ValueError('Stream clocks must share the declared FCLK1 net')
    # Check actual stream identity at the sink, not an adjacent upstream tap.
    def bus(name, interface):
        return next((b.get('BUSNAME') for b in modules[name].iter('BUSINTERFACE')
                     if b.get('NAME') == interface), None)
    stream = bus('axi_vdma_1', 'S_AXIS_S2MM')
    if not stream or stream != bus('axis_color_highlight_0', 'M_AXIS'):
        raise ValueError('Capture sink does not match the inspected 24-bit stream')
    return dict(xsa_sha256=digest(raw), bit_sha256=digest(bit_data),
                hwh_sha256=digest(hwh_data), csi_minor=int(csi['kVersionMinor']),
                csi_counters_coherent=not historical,
                display_status_mask=1 if historical else 3), bit_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xsa', type=Path)
    parser.add_argument('--baseline', choices=('live', 'xsa'), default='live')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = None
    if args.baseline == 'live':
        baseline = inspect_live_baseline()
        if args.xsa is None:
            args.xsa = ROOT/LIVE_PLATFORM/'hw/color_test.xsa'
    elif args.xsa is None:
        parser.error('--baseline xsa requires --xsa')
    metadata, bit = inspect_xsa(args.xsa, allow_historical_live=baseline is not None)
    if baseline is not None and metadata['xsa_sha256'] != LIVE_XSA_SHA256:
        raise ValueError('The live baseline cannot be paired with a different XSA')
    if args.output.exists():
        parser.error('Output already exists; select a fresh build directory')
    generator_path = Path(__file__).with_name('generate_game_config.py')
    spec = importlib.util.spec_from_file_location('beam_config_generator', generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    config_data = (ROOT/'pc_vision/game_config.json').read_bytes()
    source = generator.generate_beam(json.loads(config_data.decode('utf-8')))
    header = '''/* GENERATED; one measured config and one explicit XSA. */
#ifndef GENERATED_GAME_BEAM_CONFIG_H
#define GENERATED_GAME_BEAM_CONFIG_H
#include "game_beam.h"
#include "vision_portal.h"
extern const GameBeamConfig game_beam_default_config;
extern const VisionPortalTemplate game_beam_portals[2];
extern const VisionRealSceneGeometry game_beam_marker_geometry;
#define GAME_BEAM_XSA_SHA256 "%s"
#define GAME_BEAM_CSI_VERSION 0x%08xU
#define GAME_BEAM_DISPLAY_STATUS_MASK %dU
#define GAME_BEAM_COUNTERS_COHERENT %d
#define GAME_BEAM_BASELINE_LIVE %d
#endif
''' % (metadata['xsa_sha256'], 0x10000 + metadata['csi_minor'],
       metadata['display_status_mask'], metadata['csi_counters_coherent'], baseline is not None)
    xsa_data = args.xsa.read_bytes()
    if digest(xsa_data) != metadata['xsa_sha256']:
        raise RuntimeError('XSA changed during preparation')
    args.output.mkdir(parents=True)
    (args.output/'hardware.xsa').write_bytes(xsa_data)
    if baseline is not None:
        # Freeze the already matched platform; never update/regenerate the
        # historical Vitis workspace or relink its FSBL with current drivers.
        platform = ROOT/LIVE_PLATFORM
        bsp = platform/'ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0'
        shutil.copytree(str(bsp/'include'), str(args.output/'bsp/include'))
        (args.output/'bsp/lib').mkdir()
        shutil.copyfile(str(bsp/'lib/libxil.a'), str(args.output/'bsp/lib/libxil.a'))
        for original, target in ((platform/'zynq_fsbl/fsbl.elf', args.output/'fsbl.elf'),
                                 (platform/'hw/ps7_init.tcl', args.output/'ps7_init.tcl')):
            shutil.copyfile(str(original), str(target))
        inspect_live_baseline()  # Fail if the source set changed while copied.
        for original, target in ((bsp/'include/xparameters.h', args.output/'bsp/include/xparameters.h'),
                                 (bsp/'lib/libxil.a', args.output/'bsp/lib/libxil.a'),
                                 (platform/'zynq_fsbl/fsbl.elf', args.output/'fsbl.elf'),
                                 (platform/'hw/ps7_init.tcl', args.output/'ps7_init.tcl')):
            if original.read_bytes() != target.read_bytes():
                raise RuntimeError('Frozen baseline copy differs: ' + str(target))
    (args.output/'game_beam_config.c').write_text(source, encoding='utf-8')
    (args.output/'game_beam_config.h').write_text(header, encoding='utf-8')
    (args.output/'system_wrapper.bit').write_bytes(bit)
    metadata['game_config_sha256'] = digest(config_data)
    metadata['baseline'] = baseline or {'profile': 'explicit_xsa_not_historical_live'}
    # A build identity file, not a runtime pass/board receipt.
    (args.output/'inputs.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    print('BEAM_STANDALONE_INPUTS_READY xsa=' + metadata['xsa_sha256'])


if __name__ == '__main__':
    main()
