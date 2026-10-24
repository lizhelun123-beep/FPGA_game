"""One authorized isolated diagnostic build; reuse configured PS leaf and UART transport.

Generated wrapper/stub/XDC stay in the existing build directory. No project copy,
BD edit, production build, boot change, automatic retry or implicit board load.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'build/dphy_observer_140'
OUT = BASE / 'attempt2'
DIAG_API = 0x00010002
STATUS_ARM_READY = 1 << 8
CAPTURE_SAMPLES = 8192
PS = ROOT / 'color_test.srcs/sources_1/bd/system/ip/system_processing_system7_0_0'
DCP = ROOT / 'color_test.runs/system_processing_system7_0_0_synth_1/system_processing_system7_0_0.dcp'
VIVADO = Path(os.environ.get('XILINX_VIVADO', 'D:/Xilinx/Vivado/2023.1'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class _WordBuffer(ctypes.Structure):
    # Public CPython Py_buffer layout, shared by target3.6 and host3.12.
    _fields_ = [('buf',ctypes.c_void_p),('obj',ctypes.c_void_p),
                ('len',ctypes.c_ssize_t),('itemsize',ctypes.c_ssize_t),
                ('readonly',ctypes.c_int),('ndim',ctypes.c_int),
                ('format',ctypes.c_char_p),('shape',ctypes.POINTER(ctypes.c_ssize_t)),
                ('strides',ctypes.POINTER(ctypes.c_ssize_t)),
                ('suboffsets',ctypes.POINTER(ctypes.c_ssize_t)),('internal',ctypes.c_void_p)]


class WordAccess:
    """Typed32 access to an EXISTING buffer; never opens/maps a device itself.

    The native ABI performs one volatile word load/store with ARM barriers.
    Loading it is permitted only after its hash/ELF/constructor audit. The
    exported buffer stays pinned until close(); read-only mappings stay read-only.
    A SIGBUS still kills the accessing process: this is no fault recovery layer.
    """
    def __init__(self,buffer,library,writable=False):
        if sys.implementation.name!='cpython':raise RuntimeError('CPython buffer ABI required')
        self._view=_WordBuffer();self._closed=True;self._buffer=buffer
        self._release=ctypes.pythonapi.PyBuffer_Release
        self._release.argtypes=[ctypes.POINTER(_WordBuffer)];self._release.restype=None
        get=ctypes.pythonapi.PyObject_GetBuffer
        get.argtypes=[ctypes.py_object,ctypes.POINTER(_WordBuffer),ctypes.c_int];get.restype=ctypes.c_int
        get(buffer,ctypes.byref(self._view),0)
        self._closed=False
        try:
            self.span=self._view.len;self.writable=bool(writable)
            if not self._view.buf or self._view.buf%4 or self.span<4 or self.span%4 or self.span>0xffffffff:
                raise ValueError('Aligned, nonempty32-bit contiguous span required')
            if writable and self._view.readonly:raise PermissionError('Mapping is read-only')
            self._lib=ctypes.CDLL(str(library))
            self._lib.dphy_mmio_abi.argtypes=[];self._lib.dphy_mmio_abi.restype=ctypes.c_uint32
            if self._lib.dphy_mmio_abi()!=1:raise RuntimeError('MMIO ABI mismatch')
            self._lib.dphy_mmio_read32.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
            self._lib.dphy_mmio_read32.restype=ctypes.c_int
            self._lib.dphy_mmio_write32.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint32]
            self._lib.dphy_mmio_write32.restype=ctypes.c_int
        except BaseException:
            self.close();raise

    def _offset(self,offset):
        if self._closed:raise RuntimeError('MMIO buffer closed')
        if type(offset) is not int or offset<0 or offset%4 or offset>self.span-4:
            raise ValueError('MMIO requires an in-span aligned32-bit offset')

    def read(self,offset):
        self._offset(offset);value=ctypes.c_uint32()
        if self._lib.dphy_mmio_read32(self._view.buf,self.span,offset,ctypes.byref(value))!=0:
            raise RuntimeError('Native32-bit read argument rejection')
        return value.value

    def write(self,offset,value):
        self._offset(offset)
        if not self.writable:raise PermissionError('Read-only MMIO view')
        if type(value) is not int or not 0<=value<=0xffffffff:raise ValueError('MMIO value must be uint32')
        if self._lib.dphy_mmio_write32(self._view.buf,self.span,offset,value)!=0:
            raise RuntimeError('Native32-bit write argument rejection')

    def close(self):
        if not self._closed:
            self._release(ctypes.byref(self._view));self._closed=True;self._buffer=None

    @staticmethod
    def ram_self_test(library):
        # Must execute on the actual ARM/Python before opening ANY MMIO mapping.
        # It checks the public buffer ABI and native calling convention on RAM.
        words=(ctypes.c_uint32*4)(0xa55aa55a,0,0x01234567,0x89abcdef)
        access=WordAccess(words,library,True)
        try:
            access.write(4,0x91a2b3c4)
            if access.read(4)!=0x91a2b3c4 or list(words)!=[0xa55aa55a,0x91a2b3c4,0x01234567,0x89abcdef]:
                raise RuntimeError('Native RAM/CPython ABI self-test failed; no MMIO permitted')
        finally:access.close()
        return {'native_abi':1,'word_bytes':4,'ram_canaries_intact':True}


class NativeRegion:
    """Explicit device mapping, used ONLY inside authorized board operations."""
    def __init__(self,base,writable=False,span=4096,library=None):
        import mmap
        if library is None:raise ValueError('Audited native library required')
        fd=os.open('/dev/mem',(os.O_RDWR if writable else os.O_RDONLY)|os.O_SYNC)
        try:self.mem=mmap.mmap(fd,span,flags=mmap.MAP_SHARED,
                              prot=mmap.PROT_READ|(mmap.PROT_WRITE if writable else 0),offset=base)
        finally:os.close(fd)
        try:self.word=WordAccess(self.mem,library,writable)
        except BaseException:self.mem.close();raise
        self.base=base
    def read(self,off):return self.word.read(off)
    def store(self,off,value):self.word.write(off,value)
    def write(self,off,value):
        self.store(off,value)
        assert self.read(off)==value,'PS register readback mismatch'
    def close(self):self.word.close();self.mem.close()


def observer_marker_or_exit(console,pattern,token,seconds):
    """Never wait for an export marker after our foreground has already died."""
    terminal=rb'\r?\n'+token.encode()+rb':([0-9]+)\r?\n'
    match=console.until(b'(?:'+pattern+b')|(?:'+terminal+b')',seconds)
    if re.search(terminal,match.group(0)):
        console.foreground_owned=False
        code=int(re.search(terminal,match.group(0)).group(1))
        raise RuntimeError('Owned diagnostic exited before expected marker, status '+str(code))
    return match


def observer_buffered_console(console):
    """Keep unread marker tails, including coalesced UART export frames."""
    import time
    cursor=[len(console.raw)]
    def until(pattern,seconds):
        deadline=time.monotonic()+seconds
        while True:
            match=re.search(pattern,bytes(console.raw[cursor[0]:]))
            if match:cursor[0]+=match.end();return match
            if time.monotonic()>deadline:
                if console.foreground_owned:console.send('\x03')
                raise TimeoutError('Owned diagnostic serial timeout; no retry')
            console.raw.extend(console.port.read(min(max(console.port.in_waiting,1),4096)))
    console.until=until


def prepare(shared=False):
    previous=json.loads((BASE/'build_attempt.json').read_text())
    assert previous['status']=='FAILED' and previous['builds_used']==1 and previous['loads_used']==0
    old=json.loads((BASE/'review.json').read_text())
    assert all(sha(BASE/name)==digest for name,digest in old['evidence'].items())
    if shared:
        prior=json.loads((BASE/'attempt2/package_ledger.json').read_text())
        assert prior['status']=='BUILD_FAILED' and prior['closed']
        assert (OUT/'before_sources.json').is_file() and not (OUT/'package_ledger.json').exists()
    else:
        if OUT.exists(): raise RuntimeError('Attempt2 already reserved; no reset or overwrite')
        OUT.mkdir()
    (OUT/'package_ledger.json').write_text(json.dumps({
        'authorization':'2026-10-20 user continuous diagnostic package; one added verification round, one added build, ONE combined temporary load',
        'previous_build_ledger_sha256':sha(BASE/'build_attempt.json'),
        'historical_builds_used':1,'additional_builds_allowed':1,'additional_builds_used':0,
        'verification_rounds_allowed':1,'verification_rounds_used':0,
        'combined_loads_allowed':1,'combined_loads_used':0,'stream_seconds_limit':60,
        'status':'PREPARED'},indent=2)+'\n')
    if shared:
        ledger=json.loads((OUT/'package_ledger.json').read_text())
        ledger.update(authorization='2026-10-20 explicit shared byte reset repair + directed simulation + ONE SYNTHESIS/CDC audit only',
                      historical_builds_used=2,additional_builds_allowed=0,additional_builds_used=0,
                      synthesis_audits_allowed=1,synthesis_audits_used=0,
                      combined_loads_allowed=0,stream_seconds_limit=0,implementation_authorized=False,
                      prior_attempt2_ledger_sha256=sha(BASE/'attempt2/package_ledger.json'))
        (OUT/'package_ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
    ps_src = PS / 'synth/system_processing_system7_0_0.v'
    declarations = re.findall(r'^(input|output|inout) wire\s*(\[[^\]]+\])?\s*(\w+)\s*;', ps_src.read_text(), re.M)
    assert len(declarations) > 100 and DCP.is_file()
    fixed = {
        'GPIO_I':'cam_gpio_i', 'GPIO_O':'cam_gpio_o', 'GPIO_T':'cam_gpio_t',
        'I2C0_SCL_I':'scl_i','I2C0_SCL_O':'scl_o','I2C0_SCL_T':'scl_t',
        'I2C0_SDA_I':'sda_i','I2C0_SDA_O':'sda_o','I2C0_SDA_T':'sda_t',
        'I2C1_SCL_I':"1'b1",'I2C1_SDA_I':"1'b1",'IRQ_F2P':"3'b0",
        'FCLK_CLK0':'ctrl_clk','FCLK_CLK2':'ref_clk','FCLK_RESET0_N':'resetn',
        'M_AXI_GP0_ACLK':'ctrl_clk','S_AXI_HP0_ACLK':'ctrl_clk','S_AXI_HP1_ACLK':'ctrl_clk',
    }
    top_ports = []
    connections = []
    wires = []
    bus_names = []
    for direction, width, name in declarations:
        width = width or ''
        if direction == 'inout':
            top_ports.append(f'inout wire {width} {name}')
            connection = name
        elif name in fixed:
            connection = fixed[name]
        elif name.startswith('M_AXI_GP0_'):
            short = name.removeprefix('M_AXI_GP0_').lower()
            connection = 'gp_'+short
            wires.append(f'wire {width} {connection};')
            bus_names.append(short)
        elif direction == 'input':
            connection = "'0"
        else:
            connection = ''
        connections.append(f'.{name}({connection})')
    ps_definition = 'system_processing_system7_0_0 ps (\n'+',\n'.join(connections)+'\n);\n'
    # The configured hard PS is linked from its exact retained DCP, not re-created.
    stub = PS / 'system_processing_system7_0_0_stub.v'
    assert stub.is_file()
    body = r'''
    wire ctrl_clk,ref_clk,resetn;
    wire cam_gpio_i,cam_gpio_o,cam_gpio_t,scl_i,scl_o,scl_t,sda_i,sda_o,sda_t;
    IOBUF gpio_pad(.IO(cam_gpio_tri_io[0]),.I(cam_gpio_o),.O(cam_gpio_i),.T(cam_gpio_t));
    IOBUF scl_pad(.IO(cam_i2c_scl_io),.I(scl_o),.O(scl_i),.T(scl_t));
    IOBUF sda_pad(.IO(cam_i2c_sda_io),.I(sda_o),.O(sda_i),.T(sda_t));
    wire hs_clock,delayed_clock,serial_clk,byte_clk,delay_ready,delay_reset,sampler_reset,byte_reset;
    wire [1:0] clock_lp;
    wire [1:0] data_hs;
    wire [3:0] data_lp;
    wire [5:0] lp_byte;
    wire [9:0] taps;
    wire [1:0] ce,inc,hard_match,soft_match,sync_error,valid;
    wire [15:0] raw_data,aligned;
    InputBuffer clock_input(.HS_p(dphy_hs_clock_clk_p),.HS_n(dphy_hs_clock_clk_n),
        .LP_p(dphy_clk_lp_p),.LP_n(dphy_clk_lp_n),.aHS(hs_clock),.aLP(clock_lp));
    (* IODELAY_GROUP="DPHY_OBSERVER" *) IDELAYE2 #(.DELAY_SRC("IDATAIN"),
        .HIGH_PERFORMANCE_MODE("TRUE"),.IDELAY_TYPE("FIXED"),.IDELAY_VALUE(0),
        .REFCLK_FREQUENCY(200.0),.SIGNAL_PATTERN("CLOCK")) clock_delay
        (.IDATAIN(hs_clock),.DATAIN(1'b0),.DATAOUT(delayed_clock),.C(ctrl_clk),
         .CE(1'b0),.INC(1'b0),.LD(1'b0),.LDPIPEEN(1'b0),.REGRST(1'b0),
         .CNTVALUEIN(5'b0),.CNTVALUEOUT(),.CINVCTRL(1'b0));
    BUFIO serial_buffer(.I(delayed_clock),.O(serial_clk));
    BUFR #(.BUFR_DIVIDE("4"),.SIM_DEVICE("7SERIES")) byte_buffer
        (.I(delayed_clock),.O(byte_clk),.CE(1'b1),.CLR(delay_reset));
    (* IODELAY_GROUP="DPHY_OBSERVER" *) IDELAYCTRL delay_control
        (.REFCLK(ref_clk),.RST(delay_reset),.RDY(delay_ready));
    // LP is diagnostic status: independent bits synchronized to the byte domain.
    // It does not claim the production receiver's high-resolution LP timing.
    xpm_cdc_array_single #(.WIDTH(6),.DEST_SYNC_FF(2),.SRC_INPUT_REG(0),.INIT_SYNC_FF(1)) lp_bridge
        (.src_clk(1'b0),.src_in({clock_lp,data_lp}),.dest_clk(byte_clk),.dest_out(lp_byte));
    for(genvar lane=0;lane<2;lane=lane+1) begin: lanes
        InputBuffer data_input(.HS_p(dphy_data_hs_p[lane]),.HS_n(dphy_data_hs_n[lane]),
            .LP_p(dphy_data_lp_p[lane]),.LP_n(dphy_data_lp_n[lane]),
            .aHS(data_hs[lane]),.aLP(data_lp[2*lane+:2]));
        HS_Deserializer #(.kIs8b9b(0),.kBUFH_DDIRECT_M3(0),.kAddDelay_ps(0),.kNoLP(1),.kExternalByteReset(1)) sampler
            (.SerClk(serial_clk),.DivClk(byte_clk),.aHSIn(data_hs[lane]),
             .aLPIn(2'b0),.aLPOut(),.dLP0_in({8{lp_byte[2*lane]}}),
             .dLP1_in({8{lp_byte[2*lane+1]}}),.dLP0_out(),.dLP1_out(),
             .dDataOut8(aligned[8*lane+:8]),.dRawDataOut8(raw_data[8*lane+:8]),.dDataOut9(),
             .dValid(valid[lane]),.dSyncHard(hard_match[lane]),.dSyncSoft(soft_match[lane]),
             .dSyncErr(sync_error[lane]),.CtlClk(ctrl_clk),.cIDLY_LD(1'b0),
             .cIDLY_CE(ce[lane]),.cIDLY_INC(inc[lane]),.cIDLY_CNT(taps[5*lane+:5]),
             .aRst(byte_reset),.aSettled(1'b1));
    end
    // Raw bits[7:0]/[15:8] are ISERDES Q1..Q8 (bit7 was sent first).
    // LP[19:16], lane0 H/S/E/V[23:20], lane1 H/S/E/V[27:24], clockLP[29:28].
    wire [31:0] raw_word={2'b0,lp_byte[5:4],valid[1],sync_error[1],soft_match[1],hard_match[1],
        valid[0],sync_error[0],soft_match[0],hard_match[0],lp_byte[3:0],raw_data};
'''
    core_ports = 'awaddr awid awlen awsize awburst awvalid awready wdata wstrb wid wlast wvalid wready bid bresp bvalid bready araddr arid arlen arsize arburst arvalid arready rdata rid rresp rlast rvalid rready'.split()
    assert all(n in bus_names for n in core_ports)
    core = 'dphy_observer_control control(.clk(ctrl_clk),.resetn(resetn),.byte_clk(byte_clk),\n.idelay_ready(delay_ready),.tap0(taps[4:0]),.tap1(taps[9:5]),.raw_word(raw_word),\n.delay_reset(delay_reset),.sampler_reset(sampler_reset),.byte_reset(byte_reset),.tap_ce(ce),.tap_inc(inc),\n'
    core += ',\n'.join(f'.{n}(gp_{n})' for n in core_ports)+');\n'
    ports = ['inout wire [0:0] cam_gpio_tri_io','inout wire cam_i2c_scl_io,cam_i2c_sda_io',
             'input wire dphy_hs_clock_clk_p,dphy_hs_clock_clk_n,dphy_clk_lp_p,dphy_clk_lp_n',
             'input wire [1:0] dphy_data_hs_p,dphy_data_hs_n,dphy_data_lp_p,dphy_data_lp_n']
    source = '`timescale 1ns/1ps\nmodule dphy_observer_top(\n'+',\n'.join(top_ports+ports)+'\n);\n'
    source += '\n'.join(wires)+'\n'+body+ps_definition+core+'endmodule\n'
    (OUT/'dphy_observer_top.sv').write_text(source)
    pin_xdc = ROOT/'color_test.srcs/constrs_1/new/mipi.xdc'
    # Retain all board pin/electrical constraints. The last two constraints are
    # legacy CSI statistics exceptions whose endpoints do not exist here.
    lines = pin_xdc.read_text().splitlines()
    omitted = [s for s in lines if s.startswith('set_false_path')]
    assert len(omitted)==2 and all('MIPI_CSI2_Rx_inst/LLP_inst/' in s for s in omitted)
    (OUT/'pins.xdc').write_text('\n'.join(s for s in lines if s not in omitted)+'\n')
    inputs = [ps_src,stub,DCP,pin_xdc,ROOT/'rtl/dphy_observer_control.sv',
              ROOT/'tools/build_dphy_observer.tcl',OUT/'dphy_observer_top.sv',OUT/'pins.xdc']
    inputs += [ROOT/'sim/tb_dphy_observer.sv',ROOT/'sim/check_dphy_observer_reports.tcl',Path(__file__)]
    inputs += [ROOT/'repo/ip/MIPI_D_PHY_RX/hdl'/name for name in
               ['DPHY_Pkg.vhd','DphySyncAsync.vhd','DphySyncAsyncReset.vhd','HS_Deserializer.vhd','InputBuffer.vhd']]
    (OUT/'inputs.json').write_text(json.dumps({str(p):sha(p) for p in inputs},indent=2))
    print('PREPARED',OUT)


def resume_prepare(fixture=False):
    previous=OUT.parent/'verification2' if fixture else OUT.parent
    old=json.loads((previous/'review.json').read_text())
    assert all(sha(previous/n)==h for n,h in old['evidence'].items())
    limits=json.loads((previous/'package_ledger.json').read_text())
    assert limits['closed'] and limits['status']=='VERIFICATION_FAILED'
    assert limits['synthesis_audits_allowed']==1 and limits['synthesis_audits_used']==0
    assert not (previous/'synth_attempt.json').exists()
    if OUT.exists():raise RuntimeError('Preserve the already reserved continuation')
    OUT.mkdir()
    inputs=json.loads((previous/'inputs.json').read_text())
    for name in ['dphy_observer_top.sv','pins.xdc']:
        inputs.pop(str(previous/name))
        (OUT/name).write_bytes((previous/name).read_bytes())
        inputs[str(OUT/name)]=sha(OUT/name)
    (OUT/'inputs.json').write_text(json.dumps({p:sha(Path(p)) for p in inputs},indent=2)+'\n')
    (OUT/'package_ledger.json').write_text(json.dumps({
        'authorization':'User authorizes ONE additional corrected directed verification, compiler declaration/type/port repairs within that round; then carried unused minimal synthesis only',
        'prior_ledger_sha256':sha(previous/'package_ledger.json'),
        'prior_review_sha256':sha(previous/'review.json'),
        'historical_builds_used':2,'historical_shared_verification_attempts':1,
        'verification_rounds_allowed':1,'verification_rounds_used':0,'compiler_invocations':0,
        'synthesis_audits_allowed':1,'synthesis_audits_used':0,
        'synthesis_allowance_carried_not_added':True,'synthesis_allowance_id':'shared_reset_min_synthesis_1',
        'implementation_authorized':False,'additional_builds_allowed':0,'additional_builds_used':0,
        'combined_loads_allowed':0,'combined_loads_used':0,'stream_seconds_limit':0,
        'status':'PREPARED','closed':False},indent=2)+'\n')
    if fixture:
        ledger=json.loads((OUT/'package_ledger.json').read_text())
        ledger.update(authorization='User authorizes concentrated fixture/clock/soft-oracle/log/report repairs and reruns in ONE package, then ONE carried minimal synthesis. Stop real design failure/boundary change/budget exhaustion. No implementation/board.',
                      historical_shared_verification_attempts=2,fixture_repairs_allowed=True,
                      fixture_repair_limit=3,fixture_repair_reviews=[],audit_read_attempts=0)
        (OUT/'package_ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
        component=ROOT/'repo/ip/MIPI_D_PHY_RX/component.xml'
        (OUT/'component_before.xml').write_bytes(component.read_bytes())
    print('PREPARED_CONTINUATION',OUT)


def verify(shared=False, resume=False, fixture=False):
    package=OUT/'package_ledger.json'
    ledger=json.loads(package.read_text())
    compiler_retry=resume and ledger['status']=='COMPILATION_FAILED' and not ledger.get('closed',False)
    fixture_retry=fixture and ledger['status']=='FIXTURE_REPAIR_RECORDED' and not ledger['closed'] and 0<len(ledger['fixture_repair_reviews'])<=ledger['fixture_repair_limit']
    if ledger['verification_rounds_used'] and not (compiler_retry or fixture_retry):raise RuntimeError('Verification allowance used; no reviewed in-package fixture repair')
    inputs=json.loads((OUT/'inputs.json').read_text())
    if not (compiler_retry or fixture_retry):assert all(sha(Path(p))==digest for p,digest in inputs.items())
    else:inputs={p:sha(Path(p)) for p in inputs}
    assert f"32'h{DIAG_API:08x}" in (ROOT/'rtl/dphy_observer_control.sv').read_text()
    assert STATUS_ARM_READY==256 and CAPTURE_SAMPLES==8192
    ledger.update(verification_rounds_used=1,status='VERIFICATION_STARTED')
    if resume:
        ledger['compiler_invocations']+=1
        runout=OUT/('compile'+str(ledger['compiler_invocations']))
        runout.mkdir()
        (runout/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        with tarfile.open(runout/'source_snapshot.tar.gz','w:gz') as t:
            for p in inputs:
                path=Path(p)
                if path.suffix in {'.v','.sv','.vhd','.py','.tcl','.xdc'}:
                    t.add(path,arcname=path.relative_to(ROOT.parent).as_posix())
    else:runout=OUT
    package.write_text(json.dumps(ledger,indent=2)+'\n')
    result={'pass':False,'revision':3 if shared else 2,'additional_verification_rounds_used':1,
            'historical_full_simulation_rounds':3 if shared else 2,'control_sha256':sha(ROOT/'rtl/dphy_observer_control.sv'),
            'qualified_control_sha256':sha(ROOT/'rtl/dphy_observer_control.sv'),
            'testbench_sha256':sha(ROOT/'sim/tb_dphy_observer.sv'),
            'raw_source_sha256':sha(ROOT/'repo/ip/MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd'),
            'report_script_sha256':sha(ROOT/'tools/build_dphy_observer.tcl'),
            'report_fixture_sha256':sha(ROOT/'sim/check_dphy_observer_reports.tcl'),'stages':[],
            'functional_simulation_started':False,'compiler_retry_permitted':False,'fixture_package':fixture}
    env=os.environ.copy()
    env['PATH']=str(VIVADO/'lib/win64.o')+os.pathsep+env['PATH']
    env['TCL_LIBRARY']=str(VIVADO/'tps/tcl/tcl8.5')
    def run(name,cmd):
        print('VERIFY_STAGE',name,flush=True)
        with (runout/(name+'.tool.log')).open('w') as f:
            rc=subprocess.run([str(x) for x in cmd],cwd=OUT,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=300).returncode
        result['stages'].append({'stage':name,'returncode':rc})
        if rc:
            result['failure_stage']=name
            log=(runout/(name+'.tool.log')).read_text(errors='replace')
            result['compiler_retry_permitted']=resume and name in {'xvhdl','xvlog','xelab'} and 'ERROR: [VRFC' in log
            raise RuntimeError(name+' failed; inspect and preserve failure')
    try:
        run('report_gates',[VIVADO/'bin/unwrapped/win64.o/tclsh85t.exe',ROOT/'sim/check_dphy_observer_reports.tcl'])
        assert 'DPHY_OBSERVER_REPORT_GATES_PASS' in (runout/'report_gates.tool.log').read_text()
        if shared:
            run('xvhdl',[VIVADO/'bin/xvhdl.bat','--2008',*[ROOT/'repo/ip/MIPI_D_PHY_RX/hdl'/name for name in
                ['DPHY_Pkg.vhd','DphySyncAsync.vhd','DphySyncAsyncReset.vhd','HS_Deserializer.vhd']]])
        run('xvlog',[VIVADO/'bin/xvlog.bat','--sv',VIVADO/'data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv',
                      ROOT/'rtl/dphy_observer_control.sv',ROOT/'sim/tb_dphy_observer.sv',
                      VIVADO/'data/verilog/src/glbl.v'])
        run('xelab',[VIVADO/'bin/xelab.bat','tb_dphy_observer','glbl','-s','observer_revision2',
                     '-debug','typical','-mt','2','-L','unisims_ver','-L','unimacro_ver'])
        result['functional_simulation_started']=True
        run('xsim',[VIVADO/'bin/xsim.bat','observer_revision2','-runall','-log',str(runout/'simulation.log')])
        log=(runout/'simulation.log').read_text()
        marker=re.search(r'DPHY_OBSERVER_REVISION%d_PASS checks=(\d+)'%(4 if fixture else 3),log)
        assert marker and 'Fatal:' not in log,'Simulation did not finish every case'
        cases=re.findall(r'CASE_PASS (\w+)',log)
        expected_cases={'overlay_startup_and_actual_taps','baseline_axi_taps_frequency_timeout',
                           'reset_at_last_write_and_completion','loss_and_full_rewrite',
                           'stopped_disable_enable_and_continuous_capture','backpressure_then_read_isolation',
                           'reset_recovery_and_70mhz','shared_reset_warmup_and_real_serdes',
                           'clock_loss_hides_completed_buffer','configured_capture_timeout'}
        if fixture:expected_cases.add('error_observation_preserved')
        assert set(cases)==expected_cases
        errors=[s for s in log.splitlines() if s.startswith('Error:')]
        initial_edge=re.search(r'INITIAL_BYTE_EDGE time_ps=(\d+) binary=00000000 GSR=([01])',log) if fixture else None
        initial_ps=initial_edge.group(1) if initial_edge else '14286'
        if fixture:assert initial_edge,'Missing known initial source edge; cannot review primitive advisory'
        assert len(errors)<=1 and all('[XPM_CDC_GRAY S-2]' in e and ('src_in_bin at '+initial_ps+' ') in e
                                     and 'after a system reset' in e for e in errors),errors
        result.update(pass_status=('PASS_WITH_REVIEWED_INITIAL_EDGE_ADVISORY' if fixture else 'PASS_WITH_REVIEWED_GSR_ONLY_ADVISORY') if errors else 'PASS',
                      checks=int(marker.group(1)),covered_cases=cases,primitive_advisories=errors,
                      advisory_scope=('Only the first post-configuration source edge at'+initial_ps+'ps, binaryINIT0 and independent unit-step monitor; assertions stay enabled' if fixture else 'Only first source edge14.286ns under glbl.GSR until100ns; assertions remain enabled'),
                      post_simulation_delta=None)
        result['pass']=True
    except Exception as e:
        result['error']=str(e)
        raise
    finally:
        (runout/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        (OUT/'simulation.json').write_text(json.dumps(result,indent=2)+'\n')
        status='VERIFICATION_PASS' if result['pass'] else 'COMPILATION_FAILED' if result['compiler_retry_permitted'] else 'VERIFICATION_FAILED'
        ledger.update(status=status,closed=status=='VERIFICATION_FAILED')
        if result['pass']:(OUT/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        package.write_text(json.dumps(ledger,indent=2)+'\n')
        print('VERIFY_RESULT',json.dumps({k:result.get(k) for k in ['pass','checks','error']}),flush=True)


def synth_audit(audit_only=False):
    package=OUT/'package_ledger.json'; limits=json.loads(package.read_text())
    assert not limits['implementation_authorized']
    if audit_only:
        assert limits['status']=='AUDIT_REPAIR_RECORDED' and limits['synthesis_audits_used']==1
        assert limits['audit_read_attempts']<3 and limits.get('audit_repair_reviews')
        prior=json.loads((OUT/'synth_attempt.json').read_text())
        assert sha(OUT/'audit_input_synth.dcp')==prior['audit_input_sha256']
    else:
        assert limits['status']=='VERIFICATION_PASS'
        assert limits['synthesis_audits_used']==0 and not (OUT/'synth_attempt.json').exists()
    inputs=json.loads((OUT/'inputs.json').read_text())
    changed=[p for p,digest in inputs.items() if sha(Path(p))!=digest]
    if audit_only:
        assert all(Path(p) in [ROOT/'tools/build_dphy_observer.tcl',Path(__file__)] for p in changed)
    else:assert not changed
    limits.update(synthesis_audits_used=1,status='AUDIT_STARTED' if audit_only else 'SYNTHESIS_STARTED')
    if audit_only:limits['audit_read_attempts']+=1
    package.write_text(json.dumps(limits,indent=2)+'\n')
    attempt=OUT/'synth_attempt.json'
    if audit_only:
        saved=OUT/('synth_before_audit'+str(limits['audit_read_attempts'])+'.json')
        saved.write_bytes(attempt.read_bytes())
        result=json.loads(attempt.read_text());result.update(status='AUDIT_REPAIR')
        attempt.write_text(json.dumps(result,indent=2)+'\n')
    else:attempt.write_text(json.dumps({'status':'STARTED','scope':'SYNTHESIS_ONLY','inputs':inputs},indent=2)+'\n')
    name='audit'+str(limits['audit_read_attempts']) if audit_only else 'vivado'
    cmd=[str(VIVADO/'bin/vivado.bat'),'-mode','batch','-notrace','-source',str(ROOT/'tools/build_dphy_observer.tcl'),
         '-log',str(OUT/(name+'.log')),'-journal',str(OUT/(name+'.jou')),'-tclargs',str(OUT),
         'AUDIT_ONLY' if audit_only else 'SYNTHESIS_ONLY']
    rc=subprocess.run(cmd,cwd=ROOT.parent).returncode
    passed=rc==0 and (OUT/'synthesis_pass.json').is_file()
    result=json.loads(attempt.read_text());result.update(status='PASS' if passed else 'FAILED',returncode=rc)
    if (OUT/'audit_input_synth.dcp').exists():result['audit_input_sha256']=sha(OUT/'audit_input_synth.dcp')
    attempt.write_text(json.dumps(result,indent=2)+'\n')
    limits.update(status='SYNTHESIS_PASS' if passed else 'SYNTHESIS_FAILED',closed=True,
                  implementation_runs=0,bitstreams=0,board_operations=0,loads_used=0,stream_seconds=0)
    package.write_text(json.dumps(limits,indent=2)+'\n')
    if not passed:raise RuntimeError('Synthesis/structure audit failed; inspect whether report-script or real design failure. No resynthesis, implementation or board access')


def build():
    ledger=OUT/'build_attempt.json'
    if ledger.exists(): raise RuntimeError('Single build allowance already recorded; no retry')
    gate=json.loads((OUT/'simulation.json').read_text())
    assert gate['pass'] and gate['qualified_control_sha256']==sha(ROOT/'rtl/dphy_observer_control.sv')
    assert gate['testbench_sha256']==sha(ROOT/'sim/tb_dphy_observer.sv')
    assert gate['raw_source_sha256']==sha(ROOT/'repo/ip/MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd')
    assert gate['report_script_sha256']==sha(ROOT/'tools/build_dphy_observer.tcl')
    package=OUT/'package_ledger.json';limits=json.loads(package.read_text())
    assert limits['status']=='VERIFICATION_PASS' and limits['additional_builds_used']==0
    inputs=json.loads((OUT/'inputs.json').read_text())
    assert all(sha(Path(p))==digest for p,digest in inputs.items())
    ledger.write_text(json.dumps({'status':'STARTED','builds_allowed':1,'loads_allowed':1,
                                 'inputs':inputs,'validation':gate},indent=2))
    limits.update(additional_builds_used=1,status='BUILD_STARTED')
    package.write_text(json.dumps(limits,indent=2)+'\n')
    cmd=[str(VIVADO/'bin/vivado.bat'),'-mode','batch','-notrace','-source',str(ROOT/'tools/build_dphy_observer.tcl'),
         '-log',str(OUT/'vivado.log'),'-journal',str(OUT/'vivado.jou'),'-tclargs',str(OUT)]
    # Preserve known-good native console handles; do not redirect through Python.
    rc=subprocess.run(cmd,cwd=ROOT.parent).returncode
    result=json.loads(ledger.read_text())
    result.update(status='PASS' if rc==0 and (OUT/'implementation_pass.json').exists() else 'FAILED',
                  returncode=rc,builds_used=1,loads_used=0)
    ledger.write_text(json.dumps(result,indent=2))
    limits.update(status='BUILD_PASS' if result['status']=='PASS' else 'BUILD_FAILED')
    package.write_text(json.dumps(limits,indent=2)+'\n')
    if result['status']!='PASS':
        raise RuntimeError('Diagnostic build failed or qualification receipt missing; single allowance consumed')


def fixed_implement():
    """ONE continuation of the audited DCP. No synthesis, retry or board operation."""
    prior=OUT.parent
    ledger=OUT/'implementation_attempt.json'
    if ledger.exists():raise RuntimeError('Fixed implementation already recorded; no retry')
    old=json.loads((prior/'package_ledger.json').read_text())
    assert old['closed'] and old['status']=='SYNTHESIS_PASS'
    assert old['actual_synthesis_invocations']==1
    before=json.loads((OUT/'before_inputs.json').read_text())
    allowed={str(ROOT/'tools/build_dphy_observer.tcl'),str(Path(__file__).resolve()),str(ROOT.parent/'PROJECT_STATE.md')}
    assert all(sha(Path(p))==h for p,h in before.items() if p not in allowed)
    dcp=prior/'audited_synth.dcp'
    assert sha(dcp)=='bfc0cf2571e4095994c8dcf1d0739264b171ba32deb1d1aea3933e737dc486d4'
    protected=json.loads((OUT/'prior_evidence.json').read_text())
    assert all(sha(Path(p))==h for p,h in protected.items())
    inputs={p:sha(Path(p)) for p in before if not p.endswith('PROJECT_STATE.md')}
    inputs[str(dcp)]=sha(dcp)
    (OUT/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    with tarfile.open(OUT/'implementation_source.tar.gz','w:gz') as t:
        for p in inputs:
            if not p.endswith('.dcp'):t.add(p,arcname=Path(p).relative_to(ROOT.parent).as_posix())
    record={'authorization':'User: next package ONE fixed diagnostic implementation, finite board observation ONLY after gates. Combined loads1, stream60s max; no production/BOOT/DMA.',
            'status':'STARTED','implementation_allowed':1,'implementation_used':1,
            'historical_failed_full_implementations':2,'synthesis_used':0,
            'combined_loads_allowed':1,'loads_used':0,'stream_seconds_limit':60,'stream_seconds_used':0,
            'per_lane_taps':list(range(32)),'observations_per_tap':1,'long_packet_equivalent_limit_per_tap':16,
            'sample_buffer_capacity_words':8192,'input_dcp':str(dcp),'input_dcp_sha256':sha(dcp),
            'prior_review_sha256':sha(prior/'review.json'),'inputs':inputs,'board_operations':0}
    ledger.write_text(json.dumps(record,indent=2)+'\n')
    cmd=[str(VIVADO/'bin/vivado.bat'),'-mode','batch','-notrace','-source',str(ROOT/'tools/build_dphy_observer.tcl'),
         '-log',str(OUT/'vivado.log'),'-journal',str(OUT/'vivado.jou'),'-tclargs',str(OUT),'IMPLEMENT_ONLY']
    rc=subprocess.run(cmd,cwd=ROOT.parent).returncode
    record.update(status='IMPLEMENTATION_PASS' if rc==0 and (OUT/'implementation_pass.json').exists() else 'IMPLEMENTATION_FAILED',returncode=rc)
    record['prior_evidence_unchanged']=all(sha(Path(p))==h for p,h in protected.items())
    record['inputs_unchanged']=all(sha(Path(p))==h for p,h in inputs.items())
    ledger.write_text(json.dumps(record,indent=2)+'\n')
    if record['status']!='IMPLEMENTATION_PASS':raise RuntimeError('Fixed diagnostic implementation gate failed. Stop: no BIT load, board access, retry or new route.')


def fixed_gate_recheck():
    """One report-only repair on the already routed design; cannot reimplement."""
    ledger=OUT/'implementation_attempt.json'
    record=json.loads(ledger.read_text())
    assert record['status']=='IMPLEMENTATION_FAILED' and record['implementation_used']==1
    assert record.get('report_rechecks',0)==0 and not (OUT/'observer.bit').exists()
    log=(OUT/'vivado.log').read_text()
    assert 'invalid character "]"' in log and 'Unclocked diagnostic FF' in log
    prior_inputs=record['inputs'];allowed={str(Path(__file__).resolve()),str(ROOT/'tools/build_dphy_observer.tcl')}
    assert all(sha(Path(p))==h for p,h in prior_inputs.items() if p not in allowed)
    dcp=OUT/'observer_routed.dcp';digest=sha(dcp)
    record.update(status='GATE_RECHECK',report_rechecks=1,routed_dcp_sha256=digest,
                  repair='Only inherited extra Tcl bracket in final clock-coverage check; all previous gates passed. Open SAME routed DCP, no opt/place/route, no changed RTL/constraints.')
    ledger.write_text(json.dumps(record,indent=2)+'\n')
    (OUT/'gate_recheck_inputs.json').write_text(json.dumps({str(ROOT/'tools/build_dphy_observer.tcl'):sha(ROOT/'tools/build_dphy_observer.tcl'),str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(dcp):digest},indent=2)+'\n')
    cmd=[str(VIVADO/'bin/vivado.bat'),'-mode','batch','-notrace','-source',str(ROOT/'tools/build_dphy_observer.tcl'),
         '-log',str(OUT/'gate_recheck.log'),'-journal',str(OUT/'gate_recheck.jou'),'-tclargs',str(OUT),'ROUTED_GATE_ONLY']
    rc=subprocess.run(cmd,cwd=ROOT.parent).returncode
    record.update(status='IMPLEMENTATION_PASS' if rc==0 and (OUT/'gate_recheck/implementation_pass.json').exists() else 'GATE_RECHECK_FAILED',gate_recheck_returncode=rc,routed_dcp_unchanged=sha(dcp)==digest)
    ledger.write_text(json.dumps(record,indent=2)+'\n')
    if record['status']!='IMPLEMENTATION_PASS':raise RuntimeError('Report-only routed recheck failed; stop, no further run/load/board access')


def fixed_board_main():
    """Board-only bounded experiment; emitted verbatim into the hashed upload."""
    import fcntl
    import glob
    import importlib.util
    import mmap
    import multiprocessing
    import signal
    import struct
    import time
    import traceback
    from pathlib import Path
    root=Path(__file__).resolve().parent
    config=json.loads((root/'config.json').read_text())
    from functools import partial
    Region=partial(NativeRegion,library=root/'libdphy_observer_mmio.so')
    result={'status':'STARTED','pass':False,'loads_used':0,'stream_starts':0,
            'stream_seconds_used':0,'events':[],'records':[],'production_baseline':False}
    bus=None;regs=None;lock=None;firmware=None;worker=None;started=None;possible_emission=None;support=None
    def event(stage,**fields):
        result['stage']=stage
        result['events'].append(dict(stage=stage,monotonic=time.monotonic(),**fields))
        (root/'board_receipt.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print('DPHY_BOARD_EVENT '+json.dumps(dict(stage=stage,**fields),sort_keys=True),flush=True)
    def digest(data):return hashlib.sha256(data).hexdigest()
    def load_module(name,file):
        spec=importlib.util.spec_from_file_location(name,str(root/file))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    def command(off,value):
        regs.store(off,value)
        return regs.read(8)  # posted-write ordering, command register is not readable
    def bounded_capture():
        # A child contains potential SIGBUS from disappearing/isolated MMIO.
        # The parent owns the sensor and ALWAYS stops it on child failure/deadline.
        memory=None
        observed={'pass':False,'records':[],'frequency':[],'raw_format':0x08012801}
        try:
            memory=Region(0x43c10000,False,32768)
            def wait(mask,want,seconds):
                deadline=time.monotonic()+seconds
                while True:
                    status=regs.read(8)
                    if status&mask==want:return status
                    if status&0x48:raise RuntimeError('tap/capture error status '+hex(status))
                    if time.monotonic()>deadline:raise TimeoutError('status timeout '+hex(status))
                    time.sleep(0.0001)
            time.sleep(0.005)
            for _ in range(8):
                observed['frequency'].append({'count':regs.read(0x18),'window_cycles':regs.read(0x1c),'monotonic':time.monotonic()})
                time.sleep(0.002)
            assert all(x['count']>0 for x in observed['frequency']),'no observed byte clock'
            assert regs.read(0x20)==8192 and regs.read(0x2c)==0x08012801
            for tap in range(32):
                if time.monotonic()-started>45:raise TimeoutError('bounded stream cutoff before next tap')
                record={'tap_command':[tap,tap],'tap_index':tap,'sample_words':0,'status':'STARTED'}
                observed['records'].append(record)
                command(0x24,0);wait(0x12,0,0.05)
                command(0x10,tap|(tap<<5));command(0x14,1)
                wait(0x04,0,0.05)
                actual=regs.read(0x0c);record['tap_readback']=[actual&31,(actual>>5)&31]
                assert record['tap_readback']==[tap,tap],record
                record['status_before_enable']=regs.read(8)
                command(0x24,1);record['status_arm_ready']=wait(0x100,0x100,0.1)
                command(0x14,2);record['status_after_command']=regs.read(8)
                record['status_complete']=wait(0x30,0x20,1.2)
                # Read each aligned32-bit word. Do not use byte-oriented MMIO memcpy.
                words=[]
                for index in range(8192):
                    if index%64==0:
                        assert regs.read(8)&0x20,'capture isolated during RAM read'
                    words.append(memory.read(index*4))
                assert regs.read(8)&0x20,'capture lost before complete host copy'
                raw=struct.pack('<8192I',*words)
                name='tap_%02d.bin'%tap;(root/name).write_bytes(raw)
                record.update(status='COMPLETE_RAW_ONLY',sample_words=8192,raw_file=name,sha256=digest(raw),
                              frequency_count=regs.read(0x18),tap_after_copy=regs.read(0x0c),status_after_copy=regs.read(8))
                assert record['tap_after_copy']==actual
                # No packet/CRC correctness requirement is imposed on raw observation.
                command(0x24,0)
                assert not regs.read(8)&0x20,'old buffer remained visible after disable'
                (root/'observations.json').write_text(json.dumps(observed,sort_keys=True,indent=2)+'\n')
                print('DPHY_TAP '+str(tap)+' COMPLETE_RAW_ONLY',flush=True)
            observed['pass']=True
        except BaseException as exc:
            observed.update(error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
        finally:
            if memory is not None:memory.close()
            (root/'observations.json').write_text(json.dumps(observed,sort_keys=True,indent=2)+'\n')
        if not observed['pass']:raise RuntimeError(observed.get('error','capture failed'))
    try:
        assert os.geteuid()==0
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==config['boot_id']
        assert os.uname().release=='5.4.0-xilinx-v2020.1'
        for name,expected in config['boot_files'].items():assert digest((Path('/boot')/name).read_bytes())==expected
        for name,expected in config['files'].items():assert digest((root/name).read_bytes())==expected
        lock=open('/run/lock/codex_camera_environment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        support=load_module('retained_environment','environment_support.py')
        event('native_ram_abi_checked',**WordAccess.ram_self_test(root/'libdphy_observer_mmio.so'))
        support.Registers=Region
        support.assert_no_active_owner(support.owners())
        server=support.server_state()
        assert not server['bitfile'] and server['timestamp'] is None and not any(server['dictionary_sizes'])
        assert not glob.glob('/proc/device-tree/amba_pl/*')
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='unknown'
        before=support.ps_snapshot();rates=support.clock_rates(before,33333333)
        assert abs(rates[0]-100)<0.01 and before['0xf800010c']&4
        assert before['0xf8000900']==0 and before['0xf8000240']==0
        event('owner_and_cold_boot_verified',boot_id=config['boot_id'],owners=support.owners(),ps_before=before,clock_mhz=rates)
        # Claim reset LOW before configuring PL, then release only after clocks/reset qualify.
        chip=Path('/sys/class/gpio/gpiochip906');gpio=Path('/sys/class/gpio/gpio960')
        assert (chip/'label').read_text().strip()=='zynq_gpio' and int((chip/'ngpio').read_text())==118
        assert not gpio.exists(),'unexplained GPIO owner'
        Path('/sys/class/gpio/export').write_text('960')
        (gpio/'direction').write_text('low');assert (gpio/'value').read_text().strip()=='0'
        event('camera_reset_claimed_low')
        bit=(root/'observer.bit').read_bytes();header,payload=support.bit_payload(bit)
        firmware=Path('/lib/firmware')/('codex_dphy_'+root.name+'.bin')
        with firmware.open('xb') as f:f.write(payload)
        assert digest(firmware.read_bytes())==digest(payload)
        result['loads_used']=1
        event('one_load_requested',bit_sha256=digest(bit),binary_sha256=digest(payload),header=header)
        Path('/sys/class/fpga_manager/fpga0/flags').write_text('0')
        Path('/sys/class/fpga_manager/fpga0/firmware').write_text(firmware.name)
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        loaded=support.ps_snapshot();assert loaded['0xf800700c']&4 and loaded['0xf8000900']&15==15
        # The BIT uses existing FCLK0=100 and ref FCLK2=200 only. Preserve FCLK1/3 and PLLs.
        ps=support.Registers(0xf8000000,True);locked=bool(ps.read(0x0c)&1)
        try:
            if locked:ps.store(0x008,0xdf0d)
            ps.write(0x240,ps.read(0x240)|1)
            ps.write(0x198,ps.read(0x198)|1)
            ps.write(0x190,(ps.read(0x190)&~0x03f03f30)|(1<<20)|(5<<8))
            ps.write(0x198,ps.read(0x198)&~1)
            time.sleep(0.01);ps.write(0x240,ps.read(0x240)&~1)
        finally:
            if locked:ps.store(0x004,0x767b)
            ps.close()
        after=support.ps_snapshot();rates=support.clock_rates(after,33333333)
        assert abs(rates[0]-100)<0.01 and abs(rates[2]-200)<0.01
        for address in ['0xf8000100','0xf8000104','0xf8000108','0xf8000170','0xf8000180','0xf80001a0']:assert after[address]==before[address]
        assert after['0xf8000240']==0
        event('one_load_and_clocks_qualified',manager_state='operating',ps_after=after,clock_mhz=rates)
        regs=support.Registers(0x43c00000,True)
        assert regs.read(0)==0x44504859 and regs.read(4)==0x00010002
        assert regs.read(0x20)==8192 and regs.read(0x1c)==100000
        event('control_write_pending',offset=0x24,value=0,width_bits=32,
              accessor='audited native ARM STR with DMB/DSB; no readback of write-only command')
        command(0x24,0);assert not regs.read(8)&0x22
        event('control_disable_acknowledged',status=regs.read(8))
        deadline=time.monotonic()+0.1
        while not regs.read(8)&1:
            assert time.monotonic()<deadline,'IDELAYCTRL not ready';time.sleep(0.001)
        assert os.path.realpath('/sys/class/i2c-adapter/i2c-0/device/of_node').endswith('/i2c@e0004000')
        assert not Path('/sys/bus/i2c/devices/0-003c/driver').exists()
        possible_emission=time.monotonic()
        (gpio/'value').write_text('1');time.sleep(0.02)
        sensor_module=load_module('canonical_sensor','ov5640.py')
        bus=sensor_module.LinuxI2C('/dev/i2c-0').open();sensor=sensor_module.OV5640(bus)
        bus.write_register(0x3008,0x42)
        assert sensor.sensor_id()==(0x56,0x40)
        sensor.configure_raw10_720p()
        fields=(0x3008,0x3034,0x3035,0x3036,0x3037,0x3108,0x3808,0x3809,0x380a,0x380b,0x380c,0x380d,0x380e,0x380f,0x3820,0x3821,0x4300,0x4800,0x4837,0x5000,0x5001,0x501f,0x300e)
        expected={}
        for address,value in sensor_module.SENSOR_INIT+sensor_module.MODE_720P_RAW10:
            if address in fields:expected[address]=value
        expected[0x3008]=0x42
        actual={address:bus.read_register(address) for address in fields}
        assert actual==expected
        event('diagnostic_identity_and_canonical_standby',api=regs.read(4),status=regs.read(8),taps=regs.read(0x0c),sensor={hex(a):v for a,v in actual.items()},
              frequency_reference='PS ps_clk33333333 nominal -> FCLK0 ~99,999,999Hz; physical reference tolerance UNKNOWN',window_cycles=100000,
              capture_limit='8192 words per tap,8192 bytes/lane,10.202 RAW10 long-packet equivalents (<16); one capture for each tap0..31; no packet completeness implied')
        # Parent watchdog starts before stream write; no data export while streaming.
        started=time.monotonic();result['stream_starts']=1;sensor.start()
        worker=multiprocessing.Process(target=bounded_capture);worker.start();worker.join(48)
        if worker.is_alive():worker.terminate();worker.join(2);raise TimeoutError('parent stream watchdog')
        assert worker.exitcode==0,'observation child exit '+str(worker.exitcode)
        observed=json.loads((root/'observations.json').read_text())
        assert observed['pass'] and len(observed['records'])==32
        result['records']=observed['records'];result['frequency']=observed['frequency']
        result['pass']=True;result['status']='FINITE_RAW_OBSERVATION_COMPLETE'
    except BaseException as exc:
        result.update(status='STOPPED',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
    finally:
        if worker is not None and worker.is_alive():worker.terminate();worker.join(2)
        if (root/'observations.json').exists():
            observed=json.loads((root/'observations.json').read_text())
            result['records']=observed.get('records',[]);result['frequency']=observed.get('frequency',[])
            result['child_observation_pass']=observed.get('pass',False)
            if 'error' in observed:result['child_error']=observed['error']
        cleanup={}
        if bus is not None:
            try:bus.write_register(0x3008,0x42);cleanup['sensor_standby']=bus.read_register(0x3008);assert cleanup['sensor_standby']==0x42
            except BaseException as exc:cleanup['sensor_stop_error']=repr(exc);result['pass']=False
        if started is not None:result['stream_seconds_used']=time.monotonic()-started
        if possible_emission is not None:
            result['reset_release_to_final_standby_seconds']=time.monotonic()-possible_emission
            result['initialization_emission']='UNKNOWN within bounded reset-release-to-standby interval; not claimed zero'
        if regs is not None:
            try:command(0x14,4);command(0x24,0);cleanup['diagnostic_status']=regs.read(8);assert not cleanup['diagnostic_status']&0x32
            except BaseException as exc:cleanup['isolation_error']=repr(exc);result['pass']=False
            regs.close()
        if bus is not None:bus.close()
        if firmware is not None and firmware.exists():firmware.unlink();cleanup['firmware_staging_removed']=True
        if support is not None:
            try:
                cleanup['owners']=support.owners();support.assert_no_active_owner(cleanup['owners'])
                cleanup['ps_final']=support.ps_snapshot()
                cleanup['fpga_state']=Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()
                cleanup['boot_files_unchanged']=all(digest((Path('/boot')/n).read_bytes())==h for n,h in config['boot_files'].items())
                gpio=Path('/sys/class/gpio/gpio960')
                if gpio.exists():cleanup['gpio960']={'direction':(gpio/'direction').read_text().strip(),'value':(gpio/'value').read_text().strip()}
                assert cleanup['boot_files_unchanged']
            except BaseException as exc:cleanup['owner_error']=repr(exc);result['pass']=False
        result['cleanup']=cleanup
        if result['stream_seconds_used']>60:result['pass']=False;result['limit_violation']='stream duration'
        if result.get('reset_release_to_final_standby_seconds',0)>60:result['pass']=False;result['limit_violation']='conservative possible emission interval'
        if lock is not None:lock.close()
        event('closed_after_finite_observation',pass_in_scope=result['pass'],status=result['status'],loads_used=result['loads_used'],stream_seconds=result['stream_seconds_used'],cleanup=cleanup)
        print('DPHY_BOARD_JSON '+json.dumps(result,sort_keys=True),flush=True)


def fixed_board_run(prepare_only=False):
    """Single upload/load/finite observation with retained COM9 transport."""
    import ast
    import base64
    import importlib.util
    import inspect
    import io
    import time
    import uuid
    ledger=OUT/'board_run_attempt.json'
    if ledger.exists():raise RuntimeError('Single board load/stream package already recorded; no retry')
    attempt=json.loads((OUT/'implementation_attempt.json').read_text())
    preflight=json.loads((OUT/'board_preflight.json').read_text())
    assert attempt['status']=='IMPLEMENTATION_PASS' and attempt['loads_used']==0
    gate_inputs=json.loads((OUT/'gate_recheck_inputs.json').read_text())
    assert sha(ROOT/'tools/build_dphy_observer.tcl')==gate_inputs[str(ROOT/'tools/build_dphy_observer.tcl')]
    assert all(sha(Path(p))==h for p,h in attempt['inputs'].items() if p not in {str(Path(__file__).resolve()),str(ROOT/'tools/build_dphy_observer.tcl')})
    assert preflight['status']=='READONLY_PREFLIGHT_COMPLETE_REVIEW_REQUIRED'
    assert preflight['boot_id']=='7d26ebe0-cfa6-4630-8229-640158faac22'
    game=ROOT.parent/'output/build/game_app'
    support=game/'camera_environment_initialize_20261019.py'
    assert sha(support)=='9825da0c57a5d10ffc6e99cd5e205034274a4e673a5b267ef1e1eb9ac0271b37'
    assert sha(ROOT.parent/'pynq_vision/ov5640.py')=='537c9df9e61eb999cc8914f1a3eaf05e9e5972a42ff3e70f112bf4581f0bab61'
    bit=OUT/'gate_recheck/observer.bit'
    config={'boot_id':preflight['boot_id'],'boot_files':{k:v['sha256'] for k,v in preflight['stages'][0]['boot_files'].items()}}
    native=OUT/'mmio_contract/libdphy_observer_mmio.so'
    audit=json.loads((OUT/'mmio_contract/review.json').read_text())
    assert audit['decision']=='OFFLINE_WORD_ACCESS_PASS_BOARD_NOT_VALIDATED' and sha(native)==audit['native_library_sha256']
    assert sha(ROOT/'tools/dphy_observer_mmio.c')==audit['native_source_sha256']
    program='import os,json,hashlib,sys,ctypes\n'+inspect.getsource(_WordBuffer)+'\n'+inspect.getsource(WordAccess)+'\n'+inspect.getsource(NativeRegion)+'\n'+inspect.getsource(fixed_board_main)+'\nfixed_board_main()\n'
    files={'observe.py':program.encode(),'observer.bit':bit.read_bytes(),'environment_support.py':support.read_bytes(),
           'ov5640.py':(ROOT.parent/'pynq_vision/ov5640.py').read_bytes(),'libdphy_observer_mmio.so':native.read_bytes()}
    config['files']={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files['config.json']=(json.dumps(config,sort_keys=True)+'\n').encode()
    for name,data in files.items():
        if name.endswith('.py'):ast.parse(data,feature_version=(3,6))
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,data in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o600
            archive.addfile(entry,io.BytesIO(data))
    payload=stream.getvalue();payload_sha=hashlib.sha256(payload).hexdigest()
    (OUT/'board_upload.tar.gz').write_bytes(payload)
    receiver=r'''import base64,hashlib,io,json,os,runpy,sys,tarfile,tempfile,termios,signal
from pathlib import Path
assert os.geteuid()==0
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
signal.alarm(600)
old=termios.tcgetattr(0);quiet=termios.tcgetattr(0);quiet[3]&=~termios.ECHO
termios.tcsetattr(0,termios.TCSANOW,quiet);chunks=[]
try:
 print('DPHY_UPLOAD_READY',flush=True)
 for line in sys.stdin:
  if line.strip()=='END':break
  chunks.append(line.strip());assert len(chunks)<4000
  print('CODEX_CHUNK '+str(len(chunks)),flush=True)
finally:termios.tcsetattr(0,termios.TCSANOW,old)
data=base64.b64decode(''.join(chunks),validate=True)
assert hashlib.sha256(data).hexdigest()==DIGEST
directory=tempfile.mkdtemp(prefix='codex_dphy_observer_')
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
 members=archive.getmembers();assert {m.name for m in members}==NAMES
 for m in members:
  assert m.isfile() and '/' not in m.name
  with open(os.path.join(directory,m.name),'xb') as f:f.write(archive.extractfile(m).read())
print('DPHY_UPLOAD_JSON '+json.dumps({'directory':directory,'sha256':DIGEST}),flush=True)
runpy.run_path(os.path.join(directory,'observe.py'),run_name='_board_entry')
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for p in sorted(Path(directory).iterdir()):
  if p.name in ['board_receipt.json','observations.json'] or (p.name.startswith('tap_') and p.suffix=='.bin'):archive.add(str(p),arcname=p.name)
data=stream.getvalue();encoded=base64.b64encode(data).decode()
print('DPHY_EXPORT_BEGIN '+str(len(data))+' '+hashlib.sha256(data).hexdigest(),flush=True)
for n,offset in enumerate(range(0,len(encoded),768),1):
 print('DPHY_DATA '+str(n)+' '+encoded[offset:offset+768],flush=True)
 assert sys.stdin.readline().strip()=='ACK '+str(n)
print('DPHY_EXPORT_END',flush=True)
'''.replace('BOOT',repr(config['boot_id'])).replace('DIGEST',repr(payload_sha)).replace('NAMES',repr(set(files)))
    ast.parse(receiver,feature_version=(3,6))
    spec=importlib.util.spec_from_file_location('observer_transport',ROOT/'software/vision_ps_baremetal/tools/test_game_linux_native.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport);transport.OUTPUT=OUT
    command='sudo -n '+transport.python_command(receiver).replace('python3 -u','python3 -B -u',1)
    assert len(command)<4096
    record={'status':'STARTED','boot_id':config['boot_id'],'payload_sha256':payload_sha,'payload_bytes':len(payload),
            'board_program_sha256':hashlib.sha256(program.encode()).hexdigest(),'host_source_sha256':sha(Path(__file__)),
            'files':config['files'],'loads_reserved':1,'load_attempts_known':False,'stream_seconds_limit':60}
    record['command_bytes']=len(command)
    (OUT/'board_prepared.json').write_text(json.dumps(record,indent=2)+'\n')
    if prepare_only:
        print('BOARD_PREPARED '+json.dumps({k:record[k] for k in ['payload_bytes','payload_sha256','command_bytes']}),flush=True)
        return
    with ledger.open('x') as f:json.dump(record,f,indent=2)
    console=None
    try:
        console=transport.Console('COM9','fixed_diagnostic_observation');console.confirm_shell()
        # Keep unread tail bytes across markers. The first data frame can arrive
        # in the SAME UART read as EXPORT_BEGIN; legacy until() discards that tail.
        observer_buffered_console(console)
        token='DPHY_FINISHED_'+uuid.uuid4().hex
        console.foreground_owned=True
        console.send(command+"; printf '\\n"+token+":%s\\n' \"$?\"\r")
        match=console.until(('DPHY_UPLOAD_READY\r?\n|'+token+r':([0-9]+)\r?\n').encode(),12)
        if match.group(1) is not None:
            console.foreground_owned=False;record['load_attempts_known']=True;record['loads_used']=0
            raise RuntimeError('Root/boot upload guard failed; no upload/load')
        encoded=base64.b64encode(payload).decode();last=time.monotonic()
        for count,offset in enumerate(range(0,len(encoded),768),1):
            console.send(encoded[offset:offset+768]+'\r');console.until(('CODEX_CHUNK '+str(count)+r'\r?\n').encode(),5)
            if time.monotonic()-last>20:print('UPLOAD_PROGRESS',round(100*(offset+768)/len(encoded),1),'%',flush=True);last=time.monotonic()
        console.send('END\r')
        begin=observer_marker_or_exit(console,rb'DPHY_EXPORT_BEGIN ([0-9]+) ([0-9a-f]{64})\r?\n',token,75)
        size=int(begin.group(1));expected=begin.group(2).decode();chunks=[];last=time.monotonic()
        total=(4*((size+2)//3)+767)//768
        for n in range(1,total+1):
            frame=console.until(('DPHY_DATA '+str(n)+r' ([A-Za-z0-9+/=]+)\r?\n').encode(),6)
            chunks.append(frame.group(1));console.send('ACK '+str(n)+'\r')
            if time.monotonic()-last>20:print('RAW_EXPORT_PROGRESS',round(100*n/total,1),'%',flush=True);last=time.monotonic()
        console.until(rb'DPHY_EXPORT_END\r?\n',6)
        done=console.until((token+r':([0-9]+)\r?\n').encode(),10);console.foreground_owned=False
        assert int(done.group(1))==0
        data=base64.b64decode(b''.join(chunks),validate=True)
        assert len(data)==size and hashlib.sha256(data).hexdigest()==expected
        with (OUT/'board_observations.tar.gz').open('xb') as f:f.write(data)
        target=OUT/'board_observations';target.mkdir(exist_ok=False)
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            for member in archive.getmembers():
                assert member.isfile() and '/' not in member.name and '\\' not in member.name
                with (target/member.name).open('xb') as f:f.write(archive.extractfile(member).read())
        result=json.loads((target/'board_receipt.json').read_text())
        record.update(status='COMPLETE' if result['pass'] else 'STOPPED',result=result,loads_used=result['loads_used'],load_attempts_known=True,observations_sha256=expected)
        print('BOARD_RESULT '+json.dumps({k:result.get(k) for k in ['status','pass','loads_used','stream_seconds_used','error']}),flush=True)
    except BaseException as exc:
        record.update(status='HOST_STOPPED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if console:
            console.close();record['uart_log']=str(console.log)
        ledger.write_text(json.dumps(record,indent=2)+'\n')
        attempt.update(loads_used=record.get('loads_used',1),board_run_status=record['status'],board_operations=attempt.get('board_operations',0)+1,
                       stream_seconds_used=record.get('result',{}).get('stream_seconds_used','UNKNOWN'))
        (OUT/'implementation_attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')


def reload_control_board_main():
    """One same-BIT load, held reset LOW, at most3 native PL control writes."""
    import fcntl
    import glob
    import importlib.util
    import multiprocessing
    import time
    import traceback
    from functools import partial
    from pathlib import Path
    root=Path(__file__).resolve().parent
    config=json.loads((root/'config.json').read_text())
    Region=partial(NativeRegion,library=root/'libdphy_observer_mmio.so')
    expected_gpio=Path('/sys/class/gpio/gpio960')
    def digest(data):return hashlib.sha256(data).hexdigest()
    def save(path,data):
        temporary=path.with_suffix('.pending')
        with temporary.open('w') as file:
            json.dump(data,file,sort_keys=True,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(str(temporary),str(path))
    spec=importlib.util.spec_from_file_location('retained_support',str(root/'environment_support.py'))
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    support.Registers=Region
    result={'pass':False,'loads_used':0,'PL_control_write_attempts':0,'PL_control_writes_completed':0,
            'PS_write_attempts':[],'events':[],'stream_starts':0,'sensor_I2C_operations':0,'GPIO_high_writes':0}
    def event(stage,**fields):
        result['stage']=stage;result['events'].append(dict(stage=stage,monotonic=time.monotonic(),**fields))
        save(root/'worker_receipt.json',result)
        print('CONTROL_EVENT '+json.dumps(dict(stage=stage,**fields),sort_keys=True),flush=True)
    def worker():
        regs=None;ps=None
        try:
            event('native_RAM_ABI_pending')
            abi=WordAccess.ram_self_test(root/'libdphy_observer_mmio.so')
            event('native_RAM_ABI_pass',**abi)
            support.assert_no_active_owner(support.owners())
            server=support.server_state()
            assert not server['bitfile'] and server['timestamp'] is None and not any(server['dictionary_sizes'])
            assert not glob.glob('/proc/device-tree/amba_pl/*')
            assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='unknown'
            before=support.ps_snapshot();summary=support.clock_summary()
            reference=[int(l.split()[4]) for l in summary if l.split()[0]=='ps_clk']
            assert reference==[33333333]
            rates=support.clock_rates(before,reference[0])
            assert abs(rates[0]-100)<0.01 and before['0xf800010c']&4
            assert before['0xf8000900']==0 and before['0xf8000240']==0,'not the qualified cold/isolation profile'
            event('cold_profile_pass',ps_before=before,clock_mhz=rates)
            chip=Path('/sys/class/gpio/gpiochip906')
            assert (chip/'label').read_text().strip()=='zynq_gpio'
            assert int((chip/'base').read_text())==906 and int((chip/'ngpio').read_text())==118
            assert os.path.realpath(str(chip/'device')).endswith('/e000a000.gpio')
            assert not expected_gpio.exists(),'unexplained GPIO owner'
            event('GPIO_claim_pending',linux_gpio=960,direction='low')
            Path('/sys/class/gpio/export').write_text('960')
            (expected_gpio/'direction').write_text('low')
            assert (expected_gpio/'direction').read_text().strip()=='out'
            assert (expected_gpio/'value').read_text().strip()=='0'
            event('camera_reset_LOW',gpio=960)
            header,payload=support.bit_payload((root/'observer.bit').read_bytes())
            assert digest(payload)==config['binary_sha256']
            firmware=Path('/lib/firmware')/('codex_dphy_control_'+root.name+'.bin')
            with firmware.open('xb') as file:file.write(payload)
            assert digest(firmware.read_bytes())==config['binary_sha256']
            result['loads_used']=1;result['firmware_file']=str(firmware)
            event('one_load_requested',bit_sha256=config['files']['observer.bit'],binary_sha256=digest(payload),header=header)
            Path('/sys/class/fpga_manager/fpga0/flags').write_text('0')
            Path('/sys/class/fpga_manager/fpga0/firmware').write_text(firmware.name)
            assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
            loaded=support.ps_snapshot()
            assert loaded['0xf800700c']&4 and loaded['0xf8000900']&15==15
            event('one_load_returned',ps_loaded=loaded)
            ps=Region(0xf8000000,True)
            locked=bool(ps.read(0x0c)&1)
            def ps_store(offset,value,readback=True):
                result['PS_write_attempts'].append({'offset':offset,'value':value,'readback':readback})
                save(root/'worker_receipt.json',result)
                ps.store(offset,value)
                if readback:assert ps.read(offset)==value,'PS setup readback mismatch'
            try:
                if locked:ps_store(0x008,0xdf0d,False)
                ps_store(0x240,ps.read(0x240)|1)
                ps_store(0x198,ps.read(0x198)|1)
                ps_store(0x190,(ps.read(0x190)&~0x03f03f30)|(1<<20)|(5<<8))
                ps_store(0x198,ps.read(0x198)&~1)
                time.sleep(0.01);ps_store(0x240,ps.read(0x240)&~1)
            finally:
                if locked:ps_store(0x004,0x767b,False)
                ps.close();ps=None
            after=support.ps_snapshot();rates=support.clock_rates(after,reference[0])
            assert abs(rates[0]-100)<0.01 and abs(rates[2]-200)<0.01
            for address in ['0xf8000100','0xf8000104','0xf8000108','0xf8000170','0xf8000180','0xf80001a0']:
                assert after[address]==before[address],'unrelated PS clock/PLL changed'
            assert after['0xf8000240']==0 and after['0xf8000900']&15==15
            assert (expected_gpio/'value').read_text().strip()=='0'
            event('diagnostic_clock_reset_setup_pass',ps_after=after,clock_mhz=rates)
            regs=Region(0x43c00000,True)
            def snapshot():
                return {hex(o):regs.read(o) for o in [0,4,8,0x0c,0x10,0x18,0x1c,0x20,0x24,0x28,0x2c]}
            event('control_identity_read_pending')
            initial=snapshot();result['initial']=initial
            assert initial['0x0']==0x44504859 and initial['0x4']==0x00010002
            assert initial['0x10']==(12|(12<<5)) and initial['0x20']==8192
            assert initial['0x1c']==100000 and initial['0x2c']==0x08012801
            assert initial['0x24']==0 and initial['0x8']&0x13e==0,'not disabled and idle'
            assert initial['0x8']&1,'IDELAYCTRL not ready'
            event('control_identity_disabled_pass',registers=initial)
            original=initial['0x10'];changed=original^1;taps=initial['0xc']
            for offset,value,label in [(0x24,0,'disable'),(0x10,changed,'shadow_change'),(0x10,original,'shadow_restore')]:
                assert result['PL_control_write_attempts']<3
                result['PL_control_write_attempts']+=1
                event('control_write_pending',ordinal=result['PL_control_write_attempts'],offset=offset,value=value,label=label,width_bits=32)
                regs.store(offset,value)
                readback=regs.read(offset);status=regs.read(8);actual_taps=regs.read(0x0c)
                assert readback==value,'control word readback mismatch'
                assert status&0x13e==0 and status&1,'disabled/idle status changed'
                assert regs.read(0x24)==0 and actual_taps==taps,'observation/tap changed'
                assert (expected_gpio/'value').read_text().strip()=='0'
                result['PL_control_writes_completed']+=1
                event('control_write_verified',ordinal=result['PL_control_writes_completed'],offset=offset,value=value,readback=readback,status=status,taps=actual_taps)
            result['final']=snapshot()
            assert result['final']['0x10']==original and result['final']['0x24']==0
            assert result['final']['0xc']==taps
            result['ps_final']=support.ps_snapshot()
            result['pass']=True;event('control_three_writes_PASS',registers=result['final'])
        except BaseException as exc:
            result.update(error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
            event('STOP_FIRST_FAILURE',error=result['error'])
        finally:
            if regs is not None:regs.close()
            if ps is not None:ps.close()
    assert os.geteuid()==0
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==config['boot_id']
    for name,expected in config['files'].items():assert digest((root/name).read_bytes())==expected
    for name,expected in config['boot_files'].items():assert digest((Path('/boot')/name).read_bytes())==expected
    lock=open('/run/lock/codex_camera_environment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    support.assert_no_active_owner(support.owners())
    child=multiprocessing.get_context('fork').Process(target=worker)
    child.start();child.join(35)
    timed_out=child.is_alive()
    if timed_out:child.terminate();child.join(2)
    completed=not child.is_alive()
    report={'pass':False,'boot_id':config['boot_id'],'child_exitcode':child.exitcode,'child_timed_out':timed_out,
            'child_stopped':completed,'loads':0,'PL_control_writes':0,'stream_starts':0,'sensor_I2C_accesses':0,
            'JTAG_accesses':0,'builds':0,'events_source':'worker_receipt.json'}
    if (root/'worker_receipt.json').exists():
        try:report['worker']=json.loads((root/'worker_receipt.json').read_text())
        except BaseException as exc:report['worker_receipt_error']=repr(exc)
    data=report.get('worker',{})
    report['loads']=data.get('loads_used',0);report['PL_control_writes']=data.get('PL_control_write_attempts',0)
    report['pass']=bool(data.get('pass')) and child.exitcode==0 and not timed_out
    report['manager_state']=Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()
    if expected_gpio.exists():report['GPIO960']={n:(expected_gpio/n).read_text().strip() for n in ['direction','value']}
    report['boot_files_unchanged']=all(digest((Path('/boot')/n).read_bytes())==h for n,h in config['boot_files'].items())
    report['owners']=support.owners()
    try:support.assert_no_active_owner(report['owners'])
    except BaseException as exc:report['owner_error']=repr(exc);report['pass']=False
    firmware=data.get('firmware_file')
    if firmware and completed:
        path=Path(firmware)
        if path.exists():
            assert path.parent==Path('/lib/firmware') and path.name=='codex_dphy_control_'+root.name+'.bin'
            assert digest(path.read_bytes())==config['binary_sha256']
            path.unlink();report['own_firmware_staging_removed']=True
    if report['pass']:
        report['pass']=report.get('GPIO960')=={'direction':'out','value':'0'} and report['manager_state']=='operating' and report['boot_files_unchanged']
    report['status']='CONTROL_ONLY_PASS' if report['pass'] else 'STOPPED'
    save(root/'control_receipt.json',report);lock.close()
    print('CONTROL_RESULT_JSON '+json.dumps(report,sort_keys=True),flush=True)


def reload_control_run(prepare_only=False, frequency_board=None):
    """One authorized no-stream reload/control package; existing BIT/SO only."""
    import ast
    import base64
    import importlib.util
    import inspect
    import io
    import time
    import uuid
    ledger=OUT/'run_attempt.json'
    if ledger.exists():raise RuntimeError('One-shot control package already recorded; no retry')
    preflight=json.loads((OUT/'preflight.json').read_text());assert preflight['status']=='READY'
    authorization=json.loads((OUT/'authorization.json').read_text())
    assert authorization['loads_allowed']==1 and authorization['loads_used']==0
    if frequency_board:
        assert authorization['stream_starts_allowed']==1 and authorization['stream_seconds_limit']==2
    fixed=OUT.parent.parent;bit=fixed/'gate_recheck/observer.bit';native=OUT.parent/'libdphy_observer_mmio.so'
    assert sha(bit)=='61477eb99ebad3b6cb11b99f3664c17ca2810838c6cee6b5b4213364149efea0'
    assert sha(native)=='828912876a0abd788718eb87e69722ef12743e6e0d90afa2c13a74f8dda2d3d8'
    support=ROOT.parent/'output/build/game_app/camera_environment_initialize_20261019.py'
    assert sha(support)=='9825da0c57a5d10ffc6e99cd5e205034274a4e673a5b267ef1e1eb9ac0271b37'
    original=json.loads((fixed/'review.json').read_text())
    assert original['implementation']['bit_sha256']==sha(bit) and original['implementation']['cdc']['critical']==0
    assert sha(ROOT/'rtl/dphy_observer_control.sv')==original['provenance']['control_sha256']
    definitions=[_WordBuffer,WordAccess,NativeRegion,reload_control_board_main]
    if frequency_board:definitions.append(frequency_board)
    code='import os,json,hashlib,sys,ctypes\n'+'\n'.join(inspect.getsource(x) for x in definitions)+'\nreload_control_board_main()\n'
    if frequency_board:code+='\n'+frequency_board.__name__+'()\n'
    ast.parse(code,feature_version=(3,6))
    files={'control.py':code.encode(),'observer.bit':bit.read_bytes(),'libdphy_observer_mmio.so':native.read_bytes(),'environment_support.py':support.read_bytes()}
    if frequency_board:files['ov5640.py']=(ROOT.parent/'pynq_vision/ov5640.py').read_bytes()
    export_names=['worker_receipt.json','control_receipt.json']
    if frequency_board:export_names+=['frequency_receipt.json','frequency_samples.json','frequency_guard.json']
    config={'boot_id':preflight['boot_id'],'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
            'binary_sha256':'57ef1290a9452c154749538a86ae965f7ce30760ad3b839bcf720d5cf1a6383c',
            'boot_files':{name:value['sha256'] for name,value in preflight['stages'][0]['boot_files'].items()}}
    files['config.json']=(json.dumps(config,sort_keys=True)+'\n').encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,data in files.items():
            item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o600
            archive.addfile(item,io.BytesIO(data))
    payload=stream.getvalue();payload_sha=hashlib.sha256(payload).hexdigest()
    (OUT/'board_upload.tar.gz').write_bytes(payload)
    (OUT/'board_control_source.py').write_text(code)
    receiver=r'''import base64,hashlib,io,json,os,runpy,sys,tarfile,tempfile,termios,signal
from pathlib import Path
assert os.geteuid()==0
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
signal.alarm(600)
old=termios.tcgetattr(0);quiet=termios.tcgetattr(0);quiet[3]&=~termios.ECHO
termios.tcsetattr(0,termios.TCSANOW,quiet);chunks=[]
try:
 print('CONTROL_UPLOAD_READY',flush=True)
 for line in sys.stdin:
  if line.strip()=='END':break
  chunks.append(line.strip());assert len(chunks)<4000
  print('CODEX_CHUNK '+str(len(chunks)),flush=True)
finally:termios.tcsetattr(0,termios.TCSANOW,old)
data=base64.b64decode(''.join(chunks),validate=True)
assert hashlib.sha256(data).hexdigest()==DIGEST
directory=tempfile.mkdtemp(prefix='codex_dphy_control_')
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
 members=archive.getmembers();assert {m.name for m in members}==NAMES
 for m in members:
  assert m.isfile() and '/' not in m.name
  with open(os.path.join(directory,m.name),'xb') as f:f.write(archive.extractfile(m).read())
print('CONTROL_UPLOAD_JSON '+json.dumps({'directory':directory,'sha256':DIGEST}),flush=True)
runpy.run_path(os.path.join(directory,'control.py'),run_name='_control_entry')
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for name in EXPORT_NAMES:
  p=Path(directory)/name
  if p.exists():archive.add(str(p),arcname=name)
data=stream.getvalue();encoded=base64.b64encode(data).decode()
print('CONTROL_EXPORT_BEGIN '+str(len(data))+' '+hashlib.sha256(data).hexdigest(),flush=True)
for n,offset in enumerate(range(0,len(encoded),768),1):
 print('CONTROL_DATA '+str(n)+' '+encoded[offset:offset+768],flush=True)
 assert sys.stdin.readline().strip()=='ACK '+str(n)
print('CONTROL_EXPORT_END',flush=True)
'''.replace('EXPORT_NAMES',repr(export_names)).replace('BOOT',repr(config['boot_id'])).replace('DIGEST',repr(payload_sha)).replace('NAMES',repr(set(files)))
    ast.parse(receiver,feature_version=(3,6))
    spec=importlib.util.spec_from_file_location('control_transport',ROOT/'software/vision_ps_baremetal/tools/test_game_linux_native.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport);transport.OUTPUT=OUT
    command='sudo -n '+transport.python_command(receiver).replace('python3 -u','python3 -B -u',1)
    assert len(command)<4096
    record={'status':'PREPARED','boot_id':config['boot_id'],'payload_sha256':payload_sha,'payload_bytes':len(payload),
            'source_sha256':sha(Path(__file__)),'files':config['files'],'loads_allowed':1,'control_write_limit':3,
            'stream_starts_allowed':int(bool(frequency_board)),'builds':0,'JTAG_operations':0,'command_bytes':len(command)}
    (OUT/'prepared.json').write_text(json.dumps(record,indent=2)+'\n')
    if prepare_only:print(json.dumps(record),flush=True);return
    record['status']='STARTED'
    with ledger.open('x') as f:json.dump(record,f,indent=2)
    console=None
    try:
        console=transport.Console('COM9','reload_control');console.confirm_shell();observer_buffered_console(console)
        token='CONTROL_FINISHED_'+uuid.uuid4().hex
        console.foreground_owned=True
        console.send(command+"; printf '\\n"+token+":%s\\n' \"$?\"\r")
        ready=console.until(('CONTROL_UPLOAD_READY\r?\n|'+token+r':([0-9]+)\r?\n').encode(),12)
        if ready.group(1) is not None:
            console.foreground_owned=False;record.update(loads_used=0,PL_control_writes_used=0,stream_starts=0)
            raise RuntimeError('Root/current-boot receiver guard failed before upload; no device work')
        encoded=base64.b64encode(payload).decode();last=time.monotonic()
        for count,offset in enumerate(range(0,len(encoded),768),1):
            console.send(encoded[offset:offset+768]+'\r')
            observer_marker_or_exit(console,('CODEX_CHUNK '+str(count)+r'\r?\n').encode(),token,5)
            if time.monotonic()-last>20:print('UPLOAD_PROGRESS',round(100*(offset+768)/len(encoded),1),'%',flush=True);last=time.monotonic()
        console.send('END\r')
        begin=observer_marker_or_exit(console,rb'CONTROL_EXPORT_BEGIN ([0-9]+) ([0-9a-f]{64})\r?\n',token,60)
        size=int(begin.group(1));expected=begin.group(2).decode();chunks=[]
        count=(4*((size+2)//3)+767)//768
        for n in range(1,count+1):
            frame=observer_marker_or_exit(console,('CONTROL_DATA '+str(n)+r' ([A-Za-z0-9+/=]+)\r?\n').encode(),token,6)
            chunks.append(frame.group(1));console.send('ACK '+str(n)+'\r')
        observer_marker_or_exit(console,rb'CONTROL_EXPORT_END\r?\n',token,6)
        done=console.until((token+r':([0-9]+)\r?\n').encode(),10);console.foreground_owned=False
        assert int(done.group(1))==0
        data=base64.b64decode(b''.join(chunks),validate=True)
        assert len(data)==size and hashlib.sha256(data).hexdigest()==expected
        with (OUT/'board_receipts.tar.gz').open('xb') as f:f.write(data)
        target=OUT/'board_receipts';target.mkdir(exist_ok=False)
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            for member in archive.getmembers():
                assert member.isfile() and member.name in export_names
                with (target/member.name).open('xb') as f:f.write(archive.extractfile(member).read())
        result=json.loads((target/('frequency_receipt.json' if frequency_board else 'control_receipt.json')).read_text())
        record.update(status='PASS' if result['pass'] else 'STOPPED',result=result,loads_used=result['loads'],PL_control_writes_used=result['PL_control_writes'])
        print('CONTROL_RESULT '+json.dumps({k:result.get(k) for k in ['status','pass','child_exitcode','loads','PL_control_writes','GPIO960','own_firmware_staging_removed']}),flush=True)
    except BaseException as exc:
        record.update(status='HOST_STOPPED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if console:console.close();record['uart_log']=str(console.log)
        ledger.write_text(json.dumps(record,indent=2)+'\n')
        authorization.update(status=record['status'],closed=True,loads_used=record.get('loads_used','UNKNOWN'),
                             PL_control_writes_used=record.get('PL_control_writes_used','UNKNOWN'),
                             stream_starts=record.get('result',{}).get('stream_starts',record.get('stream_starts',0 if not frequency_board else 'UNKNOWN')))
        (OUT/'authorization.json').write_text(json.dumps(authorization,indent=2)+'\n')


def finite_observation_board_main():
    """No-load observation. Parent owns sensor stop; MMIO stays in child processes."""
    import fcntl
    import glob
    import importlib.util
    import multiprocessing
    import signal
    import struct
    import time
    import traceback
    from functools import partial
    root=Path(__file__).resolve().parent
    config=json.loads((root/'config.json').read_text())
    Region=partial(NativeRegion,library=root/'libdphy_observer_mmio.so')
    gpio=Path('/sys/class/gpio/gpio960')
    result={'status':'STARTED','pass':False,'loads':0,'builds':0,'PS_writes':0,
            'stream_start_attempts':0,'events':[],'production_baseline':False}
    def save(name,data):
        path=root/name;temporary=path.with_suffix('.pending')
        with temporary.open('w') as file:
            json.dump(data,file,sort_keys=True,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(str(temporary),str(path))
    def event(stage,**fields):
        result['stage']=stage
        result['events'].append(dict(stage=stage,monotonic=time.monotonic(),**fields))
        save('board_receipt.json',result)
        print('OBS_EVENT '+json.dumps(dict(stage=stage,**fields),sort_keys=True),flush=True)
    def module(name,file):
        spec=importlib.util.spec_from_file_location(name,str(root/file))
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
    def child(mode,started=None):
        regs=None;memory=None
        data={'mode':mode,'pass':False,'records':[],'frequency':[],'writes':[]}
        name=mode+'_receipt.json'
        def write(off,value):
            item={'offset':off,'value':value,'monotonic':time.monotonic(),'completed':False}
            data['writes'].append(item);save(name,data)
            regs.store(off,value);item['status_after']=regs.read(8);item['completed']=True
        def wait(mask,want,seconds):
            end=time.monotonic()+seconds
            while True:
                status=regs.read(8)
                if status&0x48:raise RuntimeError('tap/capture error status '+hex(status))
                if status&mask==want:return status
                if time.monotonic()>end:raise TimeoutError('status timeout '+hex(status))
                time.sleep(0.0001)
        try:
            data['native_RAM_ABI']=WordAccess.ram_self_test(root/'libdphy_observer_mmio.so')
            save(name,data)  # Durable before the first MMIO access.
            if mode=='gate':
                support.Registers=Region
                ps=support.ps_snapshot();summary=support.clock_summary()
                reference=[int(l.split()[4]) for l in summary if l.split()[0]=='ps_clk']
                assert reference==[33333333]
                rates=support.clock_rates(ps,reference[0])
                assert abs(rates[0]-100)<0.01 and abs(rates[2]-200)<0.01
                assert ps['0xf800010c']&4 and ps['0xf8000240']==0 and ps['0xf8000900']&15==15
                assert ps['0xf800700c']&4
                data.update(ps=ps,clock_mhz=rates,clock_summary=summary,
                            reference_hz=rates[0]*1000000,reference_tolerance='UNKNOWN; register-derived nominal')
                regs=Region(0x43c00000,False)
                initial={hex(off):regs.read(off) for off in [0,4,8,12,16,24,28,32,36,40,44]}
                data['initial']=initial
                assert initial['0x0']==0x44504859 and initial['0x4']==0x10002
                assert initial['0x8']==1 and initial['0x24']==0
                assert initial['0x20']==8192 and initial['0x1c']==100000
                assert initial['0x2c']==0x08012801 and initial['0xc']==396
            else:
                regs=Region(0x43c00000,True)
                if mode=='isolate':
                    write(0x14,4);write(0x24,0)
                    data['final']={hex(off):regs.read(off) for off in [0,4,8,12,16,24,28,32,36,40,44]}
                    assert not data['final']['0x8']&0x132 and data['final']['0x24']==0
                else:
                    assert mode=='capture'
                    memory=Region(0x43c10000,False,32768)
                    time.sleep(0.005)
                    for _ in range(8):
                        data['frequency'].append({'count':regs.read(0x18),'window_cycles':regs.read(0x1c),'monotonic':time.monotonic()})
                        time.sleep(0.002)
                    save(name,data)
                    assert all(x['count']>0 for x in data['frequency']),'no observed byte clock'
                    for tap in range(32):
                        assert time.monotonic()-started<45,'bounded emission cutoff before next tap'
                        record={'tap_index':tap,'tap_command':[tap,tap],'sample_words':0,'status':'STARTED'}
                        data['records'].append(record);save(name,data)
                        write(0x24,0);wait(0x12,0,0.05)
                        write(0x10,tap|(tap<<5));write(0x14,1);wait(4,0,0.05)
                        actual=regs.read(12);record['tap_readback']=[actual&31,(actual>>5)&31]
                        assert record['tap_readback']==[tap,tap],record
                        record['status_before_enable']=regs.read(8)
                        write(0x24,1);record['status_arm_ready']=wait(0x100,0x100,0.1)
                        write(0x14,2);record['status_after_command']=regs.read(8)
                        record['status_complete']=wait(0x30,0x20,1.2)
                        words=[]
                        for index in range(8192):
                            if index%64==0:assert regs.read(8)&0x20,'RAM publication lost during copy'
                            words.append(memory.read(index*4))
                        assert regs.read(8)&0x20,'RAM publication lost before full copy'
                        raw=struct.pack('<8192I',*words);filename='tap_%02d.bin'%tap
                        (root/filename).write_bytes(raw)
                        record.update(status='COMPLETE_RAW_ONLY',sample_words=8192,raw_file=filename,
                                      sha256=hashlib.sha256(raw).hexdigest(),frequency_count=regs.read(24),
                                      tap_after_copy=regs.read(12),status_after_copy=regs.read(8))
                        assert record['tap_after_copy']==actual
                        write(0x24,0)
                        assert not regs.read(8)&0x20,'old buffer visible after disable'
                        save(name,data);print('OBS_TAP '+str(tap)+' COMPLETE_RAW_ONLY',flush=True)
            data['pass']=True
        except BaseException as exc:
            data.update(error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
        finally:
            if memory is not None:memory.close()
            if regs is not None:regs.close()
            save(name,data)
    def run_child(mode,seconds,started=None):
        nonlocal worker
        worker=multiprocessing.Process(target=child,args=(mode,started));worker.start();worker.join(seconds)
        if worker.is_alive():worker.terminate();worker.join(1);raise TimeoutError(mode+' parent watchdog')
        assert worker.exitcode==0,mode+' child exit '+str(worker.exitcode)
        receipt=json.loads((root/(mode+'_receipt.json')).read_text())
        assert receipt['pass'],mode+': '+receipt.get('error','receipt failed')
        return receipt
    def deadline_error(signum,frame):raise TimeoutError('parent possible-emission deadline')
    def hard_stop(started):
        # Independent of MMIO, sensor ioctl and parent Python progress.
        if not stopped.wait(max(0,55-(time.monotonic()-started))):
            safety={'fired':True,'monotonic':time.monotonic()}
            try:(gpio/'value').write_text('0');safety['GPIO960']=(gpio/'value').read_text().strip()
            except BaseException as exc:safety['error']=repr(exc)
            save('hard_stop.json',safety)
    bus=None;lock=None;worker=None;guard=None;started=None;support=None;cleanup={}
    stopped=multiprocessing.Event()
    try:
        assert os.geteuid()==0
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==config['boot_id']
        for name,expected in config['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
        for name,expected in config['boot_files'].items():assert hashlib.sha256((Path('/boot')/name).read_bytes()).hexdigest()==expected
        lock=open('/run/lock/codex_camera_environment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        support=module('retained_environment','environment_support.py')
        owners=support.owners();support.assert_no_active_owner(owners)
        server=support.server_state()
        assert not server['bitfile'] and server['timestamp'] is None and not any(server['dictionary_sizes'])
        assert not glob.glob('/proc/device-tree/amba_pl/*')
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        assert (gpio/'direction').read_text().strip()=='out' and (gpio/'value').read_text().strip()=='0'
        assert os.path.realpath('/sys/class/i2c-adapter/i2c-0/device/of_node').endswith('/i2c@e0004000')
        assert not Path('/sys/bus/i2c/devices/0-003c/driver').exists()
        gate=run_child('gate',8);result['gate']=gate
        event('loaded_diagnostic_and_native_gate_pass',owners=owners,initial=gate['initial'],clock_mhz=gate['clock_mhz'])
        sensor_module=module('canonical_sensor','ov5640.py')
        bus=sensor_module.LinuxI2C('/dev/i2c-0').open();sensor=sensor_module.OV5640(bus)
        signal.signal(signal.SIGALRM,deadline_error)
        started=time.monotonic();signal.alarm(50)
        guard=multiprocessing.Process(target=hard_stop,args=(started,));guard.start()
        event('reset_release_pending',conservative_start=started,hard_stop_seconds=55)
        (gpio/'value').write_text('1');time.sleep(0.02)
        bus.write_register(0x3008,0x42);assert sensor.sensor_id()==(0x56,0x40)
        sensor.configure_raw10_720p()
        fields=(0x3008,0x3034,0x3035,0x3036,0x3037,0x3108,0x3808,0x3809,0x380a,0x380b,0x380c,0x380d,0x380e,0x380f,0x3820,0x3821,0x4300,0x4800,0x4837,0x5000,0x5001,0x501f,0x300e)
        expected={}
        for address,value in sensor_module.SENSOR_INIT+sensor_module.MODE_720P_RAW10:
            if address in fields:expected[address]=value
        expected[0x3008]=0x42
        actual={address:bus.read_register(address) for address in fields}
        result['sensor_standby']={hex(a):v for a,v in actual.items()};assert actual==expected
        result['stream_start_attempts']=1
        event('one_stream_start_pending',sensor=result['sensor_standby'])
        sensor.start();result['explicit_stream_started']=time.monotonic()
        observed=run_child('capture',max(0,47-(time.monotonic()-started)),started)
        assert len(observed['records'])==32
        result.update(pass_in_observation=True,status='FINITE_RAW_OBSERVATION_COMPLETE')
    except BaseException as exc:
        result.update(status='STOPPED',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
    finally:
        if worker is not None and worker.is_alive():worker.terminate();worker.join(1)
        if started is not None:
            try:
                bus.write_register(0x3008,0x42);cleanup['sensor_standby']=bus.read_register(0x3008)
                assert cleanup['sensor_standby']==0x42
            except BaseException as exc:cleanup['standby_error']=repr(exc)
            try:
                (gpio/'value').write_text('0');cleanup['GPIO960']=(gpio/'value').read_text().strip()
                assert cleanup['GPIO960']=='0'
                result['possible_emission_seconds']=time.monotonic()-started
                stopped.set();signal.alarm(0)
            except BaseException as exc:cleanup['reset_low_error']=repr(exc)
        if guard is not None:
            guard.join(6)
            if guard.is_alive():guard.terminate();guard.join(1);cleanup['guard_error']='guard did not acknowledge stop'
        signal.alarm(0)
        if bus is not None:bus.close()
        if started is not None:
            try:cleanup['isolation']=run_child('isolate',4)
            except BaseException as exc:cleanup['isolation_error']=repr(exc)
        try:
            if support is not None:
                cleanup['owners']=support.owners();support.assert_no_active_owner(cleanup['owners'])
            cleanup['boot_unchanged']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()==config['boot_id']
            cleanup['boot_files_unchanged']=all(hashlib.sha256((Path('/boot')/n).read_bytes()).hexdigest()==h for n,h in config['boot_files'].items())
            cleanup['fpga_state']=Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()
            cleanup['GPIO_final']={'direction':(gpio/'direction').read_text().strip(),'value':(gpio/'value').read_text().strip()}
        except BaseException as exc:cleanup['final_state_error']=repr(exc)
        result['cleanup']=cleanup
        result['pass']=bool(result.get('pass_in_observation') and cleanup.get('sensor_standby')==0x42 and cleanup.get('GPIO960')=='0'
                            and cleanup.get('isolation',{}).get('pass') and cleanup.get('boot_unchanged')
                            and cleanup.get('boot_files_unchanged') and result.get('possible_emission_seconds',61)<60
                            and not any(k.endswith('_error') for k in cleanup) and not (root/'hard_stop.json').exists())
        if lock is not None:lock.close()
        event('closed_after_finite_observation',pass_in_scope=result['pass'],status=result['status'],cleanup=cleanup,
              possible_emission_seconds=result.get('possible_emission_seconds'))


def finite_observation_run(prepare_only=False):
    """Transfer the bounded no-load program, then export only after stop/isolation."""
    import ast
    import base64
    import importlib.util
    import inspect
    import io
    import time
    import uuid
    ledger=OUT/'run_attempt.json'
    if ledger.exists():raise RuntimeError('Finite observation already attempted; no automatic retry')
    preflight=json.loads((OUT/'preflight.json').read_text());assert preflight['status']=='READY'
    authorization=json.loads((OUT/'authorization.json').read_text(encoding='utf-8'))
    assert not authorization['closed'] and authorization['stream_starts_allowed']==1
    assert authorization['loads_allowed']==0 and authorization['builds_allowed']==0
    fixed=OUT.parent.parent;native=OUT.parent/'libdphy_observer_mmio.so'
    support=ROOT.parent/'output/build/game_app/camera_environment_initialize_20261019.py'
    sensor=ROOT.parent/'pynq_vision/ov5640.py'
    assert sha(native)=='828912876a0abd788718eb87e69722ef12743e6e0d90afa2c13a74f8dda2d3d8'
    assert sha(support)=='9825da0c57a5d10ffc6e99cd5e205034274a4e673a5b267ef1e1eb9ac0271b37'
    assert sha(sensor)=='537c9df9e61eb999cc8914f1a3eaf05e9e5972a42ff3e70f112bf4581f0bab61'
    prior=json.loads((OUT.parent/'control_reload/review.json').read_text())
    assert prior['decision']=='CONTROL_ONLY_PASS_ON_BOARD' and prior['actual_board']['boot_id']==preflight['boot_id']
    implementation=json.loads((fixed/'review.json').read_text())
    assert sha(ROOT/'rtl/dphy_observer_control.sv')==implementation['provenance']['control_sha256']
    code='import os,json,hashlib,sys,ctypes\nfrom pathlib import Path\n'+'\n'.join(inspect.getsource(x) for x in [_WordBuffer,WordAccess,NativeRegion,finite_observation_board_main])+'\nfinite_observation_board_main()\n'
    ast.parse(code,feature_version=(3,6))
    files={'observe.py':code.encode(),'libdphy_observer_mmio.so':native.read_bytes(),
           'environment_support.py':support.read_bytes(),'ov5640.py':sensor.read_bytes()}
    config={'boot_id':preflight['boot_id'],'files':{n:hashlib.sha256(d).hexdigest() for n,d in files.items()},
            'boot_files':{n:v['sha256'] for n,v in preflight['stages'][0]['boot_files'].items()}}
    files['config.json']=(json.dumps(config,sort_keys=True)+'\n').encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,data in files.items():
            item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o600;archive.addfile(item,io.BytesIO(data))
    payload=stream.getvalue();payload_sha=hashlib.sha256(payload).hexdigest()
    (OUT/'board_upload.tar.gz').write_bytes(payload);(OUT/'board_observation_source.py').write_bytes(code.encode())
    receiver=r'''import base64,hashlib,io,json,os,runpy,sys,tarfile,tempfile,termios,signal
from pathlib import Path
assert os.geteuid()==0
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
signal.alarm(600)
old=termios.tcgetattr(0);quiet=termios.tcgetattr(0);quiet[3]&=~termios.ECHO
termios.tcsetattr(0,termios.TCSANOW,quiet);chunks=[]
try:
 print('OBS_UPLOAD_READY',flush=True)
 for line in sys.stdin:
  if line.strip()=='END':break
  chunks.append(line.strip());assert len(chunks)<4000
  print('CODEX_CHUNK '+str(len(chunks)),flush=True)
finally:termios.tcsetattr(0,termios.TCSANOW,old)
data=base64.b64decode(''.join(chunks),validate=True)
assert hashlib.sha256(data).hexdigest()==DIGEST
directory=tempfile.mkdtemp(prefix='codex_dphy_observe_')
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
 members=archive.getmembers();assert {m.name for m in members}==NAMES
 for m in members:
  assert m.isfile() and '/' not in m.name
  with open(os.path.join(directory,m.name),'xb') as f:f.write(archive.extractfile(m).read())
print('OBS_UPLOAD_JSON '+json.dumps({'directory':directory,'sha256':DIGEST}),flush=True)
runpy.run_path(os.path.join(directory,'observe.py'),run_name='_observation_entry')
assert (Path(directory)/'board_receipt.json').exists()
signal.alarm(600)
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for p in sorted(Path(directory).glob('*')):
  if p.name.endswith('_receipt.json') or p.name=='hard_stop.json' or (p.name.startswith('tap_') and p.suffix=='.bin'):
   archive.add(str(p),arcname=p.name)
data=stream.getvalue();encoded=base64.b64encode(data).decode()
print('OBS_EXPORT_BEGIN '+str(len(data))+' '+hashlib.sha256(data).hexdigest(),flush=True)
for n,offset in enumerate(range(0,len(encoded),768),1):
 print('OBS_DATA '+str(n)+' '+encoded[offset:offset+768],flush=True)
 assert sys.stdin.readline().strip()=='ACK '+str(n)
print('OBS_EXPORT_END',flush=True)
'''.replace('BOOT',repr(config['boot_id'])).replace('DIGEST',repr(payload_sha)).replace('NAMES',repr(set(files)))
    ast.parse(receiver,feature_version=(3,6))
    spec=importlib.util.spec_from_file_location('observation_transport',ROOT/'software/vision_ps_baremetal/tools/test_game_linux_native.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport);transport.OUTPUT=OUT
    command='sudo -n '+transport.python_command(receiver).replace('python3 -u','python3 -B -u',1)
    assert len(command)<4096
    record={'status':'PREPARED','boot_id':config['boot_id'],'payload_sha256':payload_sha,'payload_bytes':len(payload),
            'source_sha256':sha(Path(__file__)),'files':config['files'],'loads_allowed':0,'builds_allowed':0,
            'stream_starts_allowed':1,'tap_points_allowed':32,'sample_words_per_point':8192,'possible_emission_limit_seconds':60,
            'command_bytes':len(command),'prior_control_review_sha256':sha(OUT.parent/'control_reload/review.json')}
    (OUT/'prepared.json').write_text(json.dumps(record,indent=2)+'\n')
    if prepare_only:print(json.dumps(record),flush=True);return
    record['status']='STARTED'
    with ledger.open('x') as file:json.dump(record,file,indent=2)
    console=None
    try:
        console=transport.Console('COM9','finite_observation');console.confirm_shell();observer_buffered_console(console)
        token='OBS_FINISHED_'+uuid.uuid4().hex;console.foreground_owned=True
        console.send(command+"; printf '\\n"+token+":%s\\n' \"$?\"\r")
        ready=console.until(('OBS_UPLOAD_READY\r?\n|'+token+r':([0-9]+)\r?\n').encode(),12)
        if ready.group(1) is not None:
            console.foreground_owned=False;record.update(loads=0,stream_start_attempts=0)
            raise RuntimeError('Root/current-boot receiver guard failed before upload; no device work')
        encoded=base64.b64encode(payload).decode();last=time.monotonic()
        for count,offset in enumerate(range(0,len(encoded),768),1):
            console.send(encoded[offset:offset+768]+'\r')
            observer_marker_or_exit(console,('CODEX_CHUNK '+str(count)+r'\r?\n').encode(),token,5)
        console.send('END\r');print('OBSERVATION_UPLOADED; bounded gate/stream/cleanup running',flush=True)
        begin=observer_marker_or_exit(console,rb'OBS_EXPORT_BEGIN ([0-9]+) ([0-9a-f]{64})\r?\n',token,60)
        size=int(begin.group(1));expected=begin.group(2).decode();chunks=[]
        count=(4*((size+2)//3)+767)//768
        print('OBSERVATION_STOPPED_EXPORTING',size,'bytes',flush=True)
        for n in range(1,count+1):
            frame=observer_marker_or_exit(console,('OBS_DATA '+str(n)+r' ([A-Za-z0-9+/=]+)\r?\n').encode(),token,6)
            chunks.append(frame.group(1));console.send('ACK '+str(n)+'\r')
            if time.monotonic()-last>20:
                print('EXPORT_PROGRESS',round(100*n/count,1),'%',flush=True);last=time.monotonic()
        observer_marker_or_exit(console,rb'OBS_EXPORT_END\r?\n',token,6)
        done=console.until((token+r':([0-9]+)\r?\n').encode(),10);console.foreground_owned=False
        assert int(done.group(1))==0
        data=base64.b64decode(b''.join(chunks),validate=True)
        assert len(data)==size and hashlib.sha256(data).hexdigest()==expected
        with (OUT/'board_receipts.tar.gz').open('xb') as file:file.write(data)
        target=OUT/'board_receipts';target.mkdir(exist_ok=False)
        allowed={'board_receipt.json','gate_receipt.json','capture_receipt.json','isolate_receipt.json','hard_stop.json'}|{'tap_%02d.bin'%tap for tap in range(32)}
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            members=archive.getmembers();assert len({m.name for m in members})==len(members)
            for member in members:
                assert member.isfile() and member.name in allowed
                with (target/member.name).open('xb') as file:file.write(archive.extractfile(member).read())
        result=json.loads((target/'board_receipt.json').read_text())
        record.update(status='PASS' if result['pass'] else 'STOPPED',result=result,loads=0,
                      stream_start_attempts=result['stream_start_attempts'],export_sha256=expected)
        print('OBSERVATION_RESULT '+json.dumps({k:result.get(k) for k in ['status','pass','error','stream_start_attempts','possible_emission_seconds']}),flush=True)
    except BaseException as exc:
        record.update(status='HOST_STOPPED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if console:console.close();record['uart_log']=str(console.log)
        ledger.write_text(json.dumps(record,indent=2)+'\n')
        authorization.update(status=record['status'],closed=True,loads_used=0,builds_used=0,
                             stream_start_attempts=record.get('stream_start_attempts','UNKNOWN'))
        (OUT/'authorization.json').write_text(json.dumps(authorization,indent=2)+'\n')


def finite_observation_analyze():
    """Offline fixed-format inspection; no bit-order/lane-order search or correction."""
    import collections
    import struct
    target=OUT/'board_receipts';receipt=json.loads((target/'capture_receipt.json').read_text())
    syndromes=[7,11,13,14,19,21,22,25,26,28,35,37,38,41,42,44,49,50,52,56,31,47,55,59]
    def ecc(header):
        value=int.from_bytes(header[:3],'little');parity=0
        for bit,syndrome in enumerate(syndromes):
            if (value>>bit)&1:parity^=syndrome
        return parity
    def crc(payload):
        value=65535
        for byte in payload:
            for bit in range(8):
                value=(value>>1)^(0x8408 if (value^(byte>>bit))&1 else 0)
        return value
    output={'scope':'OFFLINE observations only; fixed HDL bit7-first chronology, CSI byteLSB-first and lane0/lane1 striping; no correction or alternate permutation search',
            'sampling_candidate_admitted':False,'points':[],'parser_limits':'First exact SoT with>=16leading zero bits within32 raw words of LP00 entry; per-lane SoT may align separately. No known payload or physical edge labels supplied. Header ECC/CRC coincidence cannot establish timing margin.'}
    for record in receipt['records']:
        raw=(target/record['raw_file']).read_bytes()
        assert len(raw)==32768 and hashlib.sha256(raw).hexdigest()==record['sha256']
        words=struct.unpack('<8192I',raw);lp=[(w>>16)&15 for w in words]
        point={'tap':record['tap_index'],'sha256':record['sha256'],'sample_words':len(words),
               'lp_counts':dict(collections.Counter(lp)),'clock_lp_counts':dict(collections.Counter((w>>28)&3 for w in words)),
               'reserved_nonzero':sum(bool(w>>30) for w in words),'lanes':[],'packets':[]}
        lanes=[]
        for lane in range(2):
            values=[(w>>(8*lane))&255 for w in words];flags=[(w>>(20+4*lane))&15 for w in words]
            lanes.append(''.join(format(value,'08b') for value in values))
            point['lanes'].append({'unique_bytes':len(set(values)),'flag_counts':dict(collections.Counter(flags)),
                                   'HSEV_counts':[sum((f>>i)&1 for f in flags) for i in range(4)]})
        entries=[i for i in range(1,len(lp)) if lp[i]==0 and lp[i-1]!=0]
        for entry in entries:
            packet={'lp00_entry_word':entry,'sot_bit_positions':[],'sot_candidate_counts':[]}
            positions=[]
            for bits in lanes:
                candidates=[j for j in range(max(16,(entry-4)*8),min(len(bits)-8,(entry+32)*8))
                            if bits[j:j+8]=='00011101' and bits[j-16:j]=='0'*16]
                packet['sot_candidate_counts'].append(len(candidates))
                positions.append(candidates[0] if candidates else None)
            packet['sot_bit_positions']=positions
            if all(p is not None for p in positions):
                packet['lane_sot_delta_bits']=positions[1]-positions[0]
                def lane_bytes(lane,count):
                    bits=lanes[lane];start=positions[lane]+8
                    return bytes(int(bits[j:j+8][::-1],2) for j in range(start,min(start+8*count,len(bits)-7),8))
                head=[lane_bytes(lane,2) for lane in range(2)]
                if all(len(h)==2 for h in head):
                    header=bytes([head[0][0],head[1][0],head[0][1],head[1][1]])
                    dtype=header[0]&63;count=int.from_bytes(header[1:3],'little')
                    packet.update(header=header.hex(),data_type=dtype,word_count_or_short_data=count,ecc_exact=(header[3]==ecc(header)))
                    if packet['ecc_exact'] and dtype==0x2b and count==1600:
                        decoded=[lane_bytes(lane,803) for lane in range(2)]
                        packet['complete_bytes_available']=all(len(d)==803 for d in decoded)
                        if packet['complete_bytes_available']:
                            data=bytes(v for pair in zip(*decoded) for v in pair)
                            packet.update(crc_exact=(crc(data[4:1604])==int.from_bytes(data[1604:1606],'little')),
                                          received_crc=data[1604:1606].hex(),calculated_crc=crc(data[4:1604]))
            point['packets'].append(packet)
        point['raw10_crc_exact_count']=sum(p.get('crc_exact',False) for p in point['packets'])
        point['ecc_exact_count']=sum(p.get('ecc_exact',False) for p in point['packets'])
        output['points'].append(point)
    output['HS_active_taps']=[p['tap'] for p in output['points'] if p['lp_counts'].get(0,0)]
    output['idle_only_taps']=[p['tap'] for p in output['points'] if p['lp_counts']=={15:8192}]
    output['raw10_crc_exact_total']=sum(p['raw10_crc_exact_count'] for p in output['points'])
    packets=[packet for point in output['points'] for packet in point['packets']]
    output['packet_totals']={'paired_SoT':len(packets),'header_ecc_exact':sum(p.get('ecc_exact',False) for p in packets),
                             'RAW10_headers':sum(p.get('data_type')==43 for p in packets),
                             'RAW10_complete_crc_exact':output['raw10_crc_exact_total'],
                             'RAW10_tail_truncated':sum(p.get('data_type')==43 and not p.get('complete_bytes_available',False) for p in packets),
                             'RAW10_complete_crc_bad':sum(p.get('complete_bytes_available',False) and not p.get('crc_exact',False) for p in packets)}
    output['sources']={str(path.relative_to(ROOT.parent)):sha(path) for path in [ROOT/'repo/ip/MIPI_CSI_2_RX/hdl/ECC.vhd',ROOT/'repo/ip/MIPI_CSI_2_RX/hdl/CRC16_behavioral.vhd',ROOT/'repo/ip/MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd']}
    (OUT/'raw_analysis.json').write_text(json.dumps(output,indent=2)+'\n')
    for p in output['points']:
        print(json.dumps({'tap':p['tap'],'HS_words':p['lp_counts'].get(0,0),'LP_entries':len(p['packets']),
                          'paired_sot':sum(all(x is not None for x in q['sot_bit_positions']) for q in p['packets']),
                          'ecc_exact':p['ecc_exact_count'],'RAW10_crc_exact':p['raw10_crc_exact_count']}))


def control_probe_preflight(resume=False,cold_reload=False,expected_boot=None):
    """Current loaded diagnostic only; no MMIO, GPIO writes or device opens."""
    import importlib.util
    fixed=OUT.parent.parent
    expected=expected_boot or '7d26ebe0-cfa6-4630-8229-640158faac22'
    path=OUT/'preflight.json'
    if path.exists():
        prior=json.loads(path.read_text())
        if not resume or prior['status']!='WAIT_USER_SUDO':raise RuntimeError('Preflight closed; no retry')
        with (OUT/'preflight_before_sudo.json').open('xb') as f:f.write(path.read_bytes())
    result={'status':'STARTED','stages':[],'MMIO_writes':0,'loads':0,'stream_starts':0}
    path.write_text(json.dumps(result,indent=2)+'\n')
    module_path=ROOT.parent/'output/build/game_app/pl_baseline_readonly_20261020.py'
    spec=importlib.util.spec_from_file_location('retained_readonly',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    transport=module.transport;transport.OUTPUT=OUT
    console=None
    try:
        console=transport.Console('COM9','control_probe_preflight');console.confirm_shell()
        def run(program,root=False):
            start=len(console.raw)
            command=transport.python_command(program).replace('python3 -u','python3 -B -u',1)
            console.command(('sudo -n ' if root else '')+command,45)
            matches=re.findall(rb'(?:^|\n)PL_BASELINE_READONLY_JSON ([^\r\n]+)',bytes(console.raw[start:]))
            assert len(matches)==1,'missing read-only receipt'
            data=json.loads(matches[0]);result['stages'].append(data)
            path.write_text(json.dumps(result,indent=2)+'\n');return data
        identity=run(module.IDENTITY)
        result['observed_boot']=identity['boot_id']
        if cold_reload:
            expected=identity['boot_id']
            assert identity['fpga']['state']=='unknown','unexplained already-operating PL; stop before new load'
            assert not identity.get('exported_gpio',[]),'unexpected GPIO owner before cold setup'
        else:
            assert identity['boot_id']==expected,'boot changed; current loaded diagnostic identity no longer valid'
            assert identity['fpga']['state']=='operating','diagnostic not operating; reload not authorized'
        before=json.loads((fixed/'board_preflight.json').read_text())['stages'][0]['boot_files']
        assert identity['boot_files']==before,'boot file identity changed'
        if not cold_reload:
            pins=[x for x in identity.get('exported_gpio',[]) if x['path'].endswith('/gpio960')]
            assert len(pins)==1 and pins[0]['direction']=='out' and pins[0]['value']=='0','camera reset not held low'
        if identity['sudo_n']['rc']!=0:
            result['status']='WAIT_USER_SUDO';return
        context=run(module.CONTEXT.replace('c4da3153-6ef5-4e83-a6b2-f3c9909def89',expected))
        ownership=run(module.OWNERSHIP.replace('c4da3153-6ef5-4e83-a6b2-f3c9909def89',expected),True)
        assert not context['pl_dt_nodes'] and context['bound_sensor_driver'] is None
        assert any(x in context['services']['bootpy.service']['stdout'] for x in ['ActiveState=failed','ActiveState=inactive']), 'boot service still active'
        for owner in ownership['owners']:
            assert owner['comm']=='start_pl_server' and not owner['fds'],owner
            assert all('/dev/mem' not in l or int(l.split()[2],16)==0xf8f00000 for l in owner['maps']),owner
        result.update(status='READY',boot_id=expected)
    except BaseException as exc:
        result.update(status='STOPPED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if console:console.close();result['uart_log']=str(console.log)
        path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:result.get(k) for k in ['status','boot_id','error','uart_log']}),flush=True)


def fixed_board_preflight(resume=False):
    """Read-only current board identity, then root ownership/PS state if sudo works."""
    import importlib.util
    import time
    attempt=json.loads((OUT/'implementation_attempt.json').read_text())
    assert attempt['status']=='IMPLEMENTATION_PASS' and attempt['loads_used']==0
    gate=json.loads((OUT/'gate_recheck/implementation_pass.json').read_text())
    assert gate['diagnostic_control_timing_pass'] and gate['critical_cdc']==0
    evidence=ROOT.parent/'output/build/game_app/pl_baseline_readonly_20261020.py'
    spec=importlib.util.spec_from_file_location('retained_readonly',evidence)
    retained=importlib.util.module_from_spec(spec);spec.loader.exec_module(retained)
    transport=retained.transport;transport.OUTPUT=OUT
    receipt=OUT/'board_preflight.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if not resume or previous['status']!='WAIT_USER_SUDO':raise RuntimeError('Board preflight already recorded; no automatic retry')
        saved=OUT/'board_preflight_before_sudo.json'
        with saved.open('xb') as f:f.write(receipt.read_bytes())
    result={'status':'STARTED','loads_used':0,'stream_seconds_used':0,'stages':[]}
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    console=None
    try:
        console=transport.Console('COM9','fixed_diagnostic_preflight')
        console.confirm_shell()
        def run(stage,program,root=False):
            offset=len(console.raw)
            command=transport.python_command(program).replace('python3 -u','python3 -B -u',1)
            if root:command='sudo -n '+command
            console.command(command,60)
            matches=re.findall(rb'(?:^|\n)PL_BASELINE_READONLY_JSON ([^\r\n]+)',bytes(console.raw[offset:]))
            assert len(matches)==1,stage
            value=json.loads(matches[0]);result['stages'].append(value)
            receipt.write_text(json.dumps(result,indent=2)+'\n')
            return value
        identity=run('identity',retained.IDENTITY)
        assert identity['uname'][4]=='armv7l' and identity['uname'][1]=='pynq'
        assert not any('error' in v for v in identity['boot_files'].values())
        result['boot_id']=identity['boot_id']
        if identity['sudo_n']['rc']!=0:
            result['status']='WAIT_USER_SUDO';return
        for stage,program in [('context',retained.CONTEXT),('ownership',retained.OWNERSHIP),('ps_state',retained.PS_STATE)]:
            program=program.replace('c4da3153-6ef5-4e83-a6b2-f3c9909def89',identity['boot_id'])
            run(stage,program,stage in ('ownership','ps_state'))
        result['status']='READONLY_PREFLIGHT_COMPLETE_REVIEW_REQUIRED'
    except BaseException as exc:
        result.update(status='PREFLIGHT_FAILED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if console:
            console.close();result['uart_log']=str(console.log)
        result['finished_unix']=time.time()
        receipt.write_text(json.dumps(result,indent=2)+'\n')
        attempt['board_operations']=attempt.get('board_operations',0)+1
        (OUT/'implementation_attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
        print(json.dumps({k:result.get(k) for k in ['status','boot_id','error','uart_log']}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['finite-analyze','finite-prepare','finite-run','finite-preflight','finite-preflight-resume','reload-control-prepare','reload-control-run','reload-preflight','reload-preflight-resume','control-preflight','control-preflight-resume','fixed-board-prepare','fixed-board-run','fixed-board-resume','fixed-board-preflight','fixed-gate-recheck','fixed-implement','prepare','verify','build','shared-prepare','shared-verify','shared-synth','shared-resume-prepare','shared-resume-verify','shared-resume-synth','fixture-prepare','fixture-verify','fixture-synth','fixture-audit']);args=ap.parse_args()
    if args.stage=='finite-analyze':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/finite_observation'
        finite_observation_analyze()
    elif args.stage in ('finite-prepare','finite-run'):
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/finite_observation'
        finite_observation_run(args.stage.endswith('-prepare'))
    elif args.stage in ('finite-preflight','finite-preflight-resume'):
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/finite_observation'
        control_probe_preflight(args.stage.endswith('-resume'),expected_boot='5869bf2b-72b5-4c1e-9990-3fc72f933dfc')
    elif args.stage in ('reload-control-prepare','reload-control-run'):
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/control_reload'
        reload_control_run(args.stage.endswith('-prepare'))
    elif args.stage in ('reload-preflight','reload-preflight-resume'):
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/control_reload'
        control_probe_preflight(args.stage.endswith('-resume'),True)
    elif args.stage in ('control-preflight','control-preflight-resume'):
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation/mmio_contract/control_probe'
        control_probe_preflight(args.stage.endswith('-resume'))
    elif args.stage=='fixed-board-prepare':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_board_run(True)
    elif args.stage=='fixed-board-run':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_board_run()
    elif args.stage=='fixed-board-resume':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_board_preflight(True)
    elif args.stage=='fixed-board-preflight':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_board_preflight()
    elif args.stage=='fixed-gate-recheck':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_gate_recheck()
    elif args.stage=='fixed-implement':
        OUT=BASE/'shared_reset_audit/fixture_package/fixed_implementation'
        fixed_implement()
    elif args.stage.startswith('fixture-'):
        OUT=BASE/'shared_reset_audit/fixture_package'
        {'fixture-prepare':lambda:resume_prepare(True),'fixture-verify':lambda:verify(True,True,True),
         'fixture-synth':synth_audit,'fixture-audit':lambda:synth_audit(True)}[args.stage]()
    elif args.stage.startswith('shared-'):
        OUT=BASE/'shared_reset_audit'
        if args.stage.startswith('shared-resume-'):
            OUT=OUT/'verification2'
            {'shared-resume-prepare':resume_prepare,'shared-resume-verify':lambda:verify(True,True),'shared-resume-synth':synth_audit}[args.stage]()
        else:
            {'shared-prepare':lambda:prepare(True),'shared-verify':lambda:verify(True),'shared-synth':synth_audit}[args.stage]()
    else:
        {'prepare':prepare,'verify':verify,'build':build}[args.stage]()
