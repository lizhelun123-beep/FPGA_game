# Authorized standalone non-project diagnostic, not a production-project edit.
# -tclargs <unique attempt directory>. Never overwrites prior attempts.
if {[llength $argv] != 1} {error "Expected unique attempt output directory"}
if {[version -short] ne "2023.1"} {error "Vivado 2023.1 required"}
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file normalize [lindex $argv 0]]
set started [file join $out build_started.txt]
if {[file exists $started]} {error "Attempt already started; preserve its results"}
file mkdir $out
set f [open $started w]; puts $f [clock format [clock seconds]]; close $f
cd $out
set_param general.maxThreads 2
set_param synth.maxThreads 2
set ip [file join $root repo ip rgb2dvi_v1_3 src]
foreach name {SyncAsync SyncAsyncReset DVI_Constants OutputSERDES TMDS_Encoder ClockGen rgb2dvi} {
  read_vhdl -vhdl2008 [file join $ip ${name}.vhd]
}
foreach name {hdmi_colorbars_timing hdmi_colorbars_guard hdmi_colorbars_top} {
  read_vhdl -vhdl2008 [file join $root rtl ${name}.vhd]
}
synth_design -top hdmi_colorbars_top -part xc7z020clg400-2 -flatten_hierarchy none
read_xdc [file join $root sim hdmi_colorbars.xdc]
# General Tcl is deliberately outside read_xdc. Fail on missing constraints.
foreach {port pin} {ref_clk_50 U18 TMDS_clk_p U13 TMDS_clk_n V13
  TMDS_data_p[0] W14 TMDS_data_n[0] Y14 TMDS_data_p[1] Y18
  TMDS_data_n[1] Y19 TMDS_data_p[2] Y16 TMDS_data_n[2] Y17} {
  if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "Wrong/missing pin $port"}
}
# LOCKED is asynchronous status. Cut only each first synchronizer D pin.
foreach guard {reference_guard video_guard} {
  set first [get_pins -hier -filter "NAME =~ ${guard}/lock_pipe_reg*0*/D"]
  if {[llength $first] != 1} {error "Expected one LOCKED first stage: $guard $first"}
  set_false_path -to $first
}
# Existing 2-FF ResetBridge: async assert, synchronous release. Cut only PRE
# recovery/removal on its synchronizer flops; downstream paths stay timed.
set reset_pins [get_pins -hier -filter {REF_PIN_NAME == PRE && NAME =~ *SyncAsyncx/oSyncStages_reg* && NAME !~ reference_guard/hold_bridge/*}]
if {[llength $reset_pins] != 6} {error "Expected three nonconstant bridges / six PRE pins: $reset_pins"}
# reference_guard/hold_bridge has aRst tied to constant zero. Before opt_design
# its two PRE pins may still exist; they are not asynchronous status crossings
# and deliberately receive no exception. Do not count them as a live bridge.
set_false_path -to $reset_pins
write_checkpoint [file join $out synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $out routed.dcp]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file timing_summary.rpt
report_timing -delay_type max -max_paths 20 -path_type full_clock_expanded -file setup_paths.rpt
report_timing -delay_type min -max_paths 20 -path_type full_clock_expanded -file hold_paths.rpt
report_drc -file drc.rpt
report_cdc -details -file cdc.rpt
report_clocks -file clocks.rpt
report_clock_interaction -file clock_interaction.rpt
report_exceptions -coverage -file exceptions.rpt
check_timing -verbose -file check_timing.rpt
report_utilization -hierarchical -file utilization_hierarchical.rpt
report_utilization -file utilization.rpt
report_io -file io.rpt
report_methodology -file methodology.rpt
write_edif [file join $out hdmi_colorbars.edf]
set f [open timing_gate.txt w]
foreach type {max min} {
  set path [get_timing_paths -delay_type $type -max_paths 1]
  if {[llength $path] != 1} {error "Missing $type timing path"}
  set slack [get_property SLACK $path]
  puts $f "$type $slack"
  if {$slack < 0} {close $f; error "Routed $type slack failed: $slack"}
}
close $f
set violations [get_drc_violations -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
if {[llength $violations]} {error "DRC error/critical: $violations"}
set f [open cdc.rpt r]; set cdc_text [read $f]; close $f
if {[regexp -line {^CDC-[0-9]+[ \t]+Critical[ \t]+[1-9][0-9]*[ \t]} $cdc_text]} {
  error "Critical CDC remains; no BIT generation"
}
# Release BIT is generated only after routed setup/hold and DRC gates above.
# CDC/IO/coverage/resource review and simulation receipts are also required by
# the packaging stage; presence of this file alone is not a release signature.
write_bitstream [file join $out hdmi_colorbars.bit]
set f [open build_complete.txt w]
puts $f "HDMI_COLORBARS_BUILD_COMPLETE tool=[version -short] part=xc7z020clg400-2"
close $f
close_design
