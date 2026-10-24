# Minimal synthesis-runtime probe. No project, implementation or board access.
# vivado -mode batch -source tools/check_vivado_runtime.tcl \
#   -tclargs <output-directory> <synth-threads: 1 or 2>
if {[llength $argv] != 2} { error "Expected output directory and synthesis threads" }
lassign $argv out threads
if {$threads ni {1 2}} { error "Expected synthesis threads 1 or 2" }
set out [file normalize $out]
file mkdir $out
cd $out
set common [file join $::env(XILINX_VIVADO) scripts rt data common.tcl]
set f [open $common r]
set common_bytes [string length [read $f]]
close $f
puts "RUNTIME_PARENT_READ_PASS path=$common bytes=$common_bytes"
puts "RUNTIME_CONTEXT vivado=[version -short] threads=$threads cwd=[pwd]"
foreach key {TEMP TMP} {
    if {[info exists ::env($key)]} { puts "RUNTIME_CONTEXT $key=$::env($key)" }
}
set f [open runtime_probe.v w]
puts $f {module runtime_probe(input clk, input d, output reg q);
always @(posedge clk) q <= d;
endmodule}
close $f
read_verilog [file join $out runtime_probe.v]
set_param synth.maxThreads $threads
synth_design -mode out_of_context -top runtime_probe -part xc7z020clg400-2
if {[llength [get_cells -hier -filter {REF_NAME == FDRE}]] != 1} {
    error "Expected the probe's single register after synthesis"
}
set f [open PASS.txt w]
puts $f "VIVADO_RUNTIME_SYNTH_PASS version=[version -short] threads=$threads"
close $f
puts "VIVADO_RUNTIME_SYNTH_PASS"
close_design
