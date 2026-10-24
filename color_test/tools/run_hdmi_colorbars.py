"""Explicit offline simulation/build stages; never connects to hardware.

Run in the authorized ordinary Windows environment. Failed outputs are retained;
this launcher never retries or selects a new setting automatically.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "color_test"
BIN = Path(os.environ.get("XILINX_VIVADO", "D:/Xilinx/Vivado/2023.1")) / "bin"
IP = PROJECT / "repo/ip/rgb2dvi_v1_3/src"
IP_NAMES = "SyncAsync SyncAsyncReset DVI_Constants OutputSERDES TMDS_Encoder ClockGen rgb2dvi".split()
RTL_NAMES = "hdmi_colorbars_timing hdmi_colorbars_guard hdmi_colorbars_top".split()


def sources():
    return [IP/(n+".vhd") for n in IP_NAMES]+[PROJECT/"rtl"/(n+".vhd") for n in RTL_NAMES]


def fingerprint(paths):
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def call(tool, args, cwd, log=None):
    # xsim embeds -tclbatch in a generated Tcl source command. Backslashes
    # become Tcl escapes (\b, \t, etc.), so pass absolute POSIX-style paths.
    cmd = [str(BIN/(tool+".bat")), *[a.as_posix() if isinstance(a,Path) else str(a) for a in args]]
    print("RUN", subprocess.list2cmdline(cmd), flush=True)
    if log:
        with log.open("w") as f:
            result = subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(cmd,cwd=cwd)
    if result.returncode:
        raise RuntimeError("{} failed {}, see {}".format(tool,result.returncode,log or cwd))


def simulate(out):
    work = out/"sim"
    work.mkdir(parents=True,exist_ok=False)
    tests = [PROJECT/"sim"/(n+".vhd") for n in ("tb_hdmi_colorbars","tb_hdmi_colorbars_top")]
    hashes = fingerprint(sources()+tests)
    (work/"source_hashes.json").write_text(json.dumps(hashes,indent=2)+"\n")
    call("xvhdl",["--2008",*sources(),*tests],work,work/"compile.log")
    for top,token in [("tb_hdmi_colorbars","HDMI_RASTER_GUARD_PASS"),("tb_hdmi_colorbars_top","HDMI_UNISIM_STARTUP_PASS")]:
        call("xelab",[top,"-L","unisim","-debug","typical","-s",top,"-timescale","1ns/1fs","-timeprecision_vhdl","1fs"],work,work/(top+"_elaborate.log"))
        batch = work/(top+".tcl")
        batch.write_text("run all\nquit\n")
        log = work/(top+"_run.log")
        call("xsim",[top,"-tclbatch",batch],work,log)
        text=log.read_text(errors="replace")
        if token not in text or "Failure:" in text or "Fatal:" in text:
            raise RuntimeError("Missing PASS or assertion failure: "+str(log))
    (work/"PASS.json").write_text(json.dumps({"sources":hashes,"result":"PASS","scope":"two pixel frames, reset supervisor, UNISIM startup/forwarded clock; no analog/hardware proof"},indent=2)+"\n")
    print("HDMI_SIMULATIONS_PASS",flush=True)


def build(out):
    # attempt_1 was an xsim path failure, not a design implementation. Preserve
    # its evidence while enforcing at most two actual implementation rounds.
    if len(list(out.parent.glob("attempt_*/build_started.txt"))) >= 2:
        raise RuntimeError("Two implementation rounds exhausted; stop for review")
    passed=json.loads((out/"sim/PASS.json").read_text())
    for path,digest in fingerprint(sources()).items():
        if passed["sources"].get(path)!=digest:
            raise RuntimeError("Simulation is stale: "+path)
    inputs = sources()+[PROJECT/"sim/hdmi_colorbars.xdc",Path(__file__),PROJECT/"tools/build_hdmi_colorbars.tcl"]
    (out/"build_input_hashes.json").write_text(json.dumps(fingerprint(inputs),indent=2)+"\n")
    call("vivado",["-mode","batch","-nojournal","-log",out/"vivado.log","-source",PROJECT/"tools/build_hdmi_colorbars.tcl","-tclargs",out],ROOT)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=("simulate","build"))
    p.add_argument("--attempt",type=int,choices=(1,2,3),required=True,
                   help="Evidence directory number; maximum two actual implementation rounds")
    a=p.parse_args()
    out=PROJECT/"build/hdmi_colorbars"/("attempt_"+str(a.attempt))
    out.mkdir(parents=True,exist_ok=True)
    if a.stage=="simulate": simulate(out)
    else: build(out)


if __name__=="__main__": main()
