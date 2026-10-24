# One staged production build in the canonical project. No implicit export.
if {$mode in {implement export}} {source [file join $root tools camera_production_physical.tcl];return}
if {$mode ne "synth"} {error "Unimplemented stage: $mode"}
set audit [file join $root tools camera_production_audit.py]
exec python -I $audit claim_synth $build_index
open_project [file join $root color_test.xpr]
if {[get_property PART [current_project]] ne "xc7z020clg400-2"} {error "Wrong part"}
if {[get_property AUTO_INCREMENTAL_CHECKPOINT [get_runs synth_1]] != 0 || [get_property INCREMENTAL_CHECKPOINT [get_runs synth_1]] ne ""} {error "Incremental source override"}
set bd [get_files */system.bd]
if {[get_property SYNTH_CHECKPOINT_MODE $bd] ne "None"} {error "Unexpected per-IP DCP synthesis"}
reset_run synth_1
launch_runs synth_1 -jobs 2
set f [open [file join $out synthesis_started.txt] {WRONLY CREAT EXCL}]
puts $f "ONE_AUTHORIZED_PRODUCTION_SYNTHESIS_LAUNCHED";close $f
wait_on_run synth_1
if {![string match "synth_design Complete*" [get_property STATUS [get_runs synth_1]]]} {error "Production synthesis failed;no retry"}
open_run synth_1
set stage [file join $out synth]
file mkdir $stage
write_checkpoint [file join $stage raw_synthesized.dcp]
source [file join $root tools camera_input_model.tcl]
camera_apply_declared_input_model $root $stage
write_checkpoint [file join $stage synthesized.dcp]
if {$build_index >= 3} {
 set f [open [file join $stage phy_drain_registers.tsv] w]
 set busy_pattern [expr {$build_index >= 4 ? "*dDrainBusy_int_reg" : "*dDrainBusy_reg"}]
 foreach {group cells} [list stop [get_cells -hier -filter {NAME =~ *dLPStop_q_reg}] busy [get_cells -hier -filter "NAME =~ $busy_pattern"] sync [get_cells -hier -filter {NAME =~ *SyncAsyncValid*oSyncStages_reg*}]] {
  foreach cell $cells {
   set cp [get_pins $cell/C]
   set qn [get_nets -of_objects [get_pins $cell/Q]]
   set sinks [get_cells -of_objects [get_pins -leaf -of_objects $qn -filter {DIRECTION == IN}]]
   puts $f "$group\t$cell\t[get_property REF_NAME $cell]\t[get_property INIT $cell]\t[get_nets -of_objects $cp]\t[get_clocks -of_objects $cp]\t[get_property ASYNC_REG $cell]\t$sinks"
  }
 }
 close $f
}
if {$build_index >= 4} {
 set f [open [file join $stage phy_rearm.tsv] w]
 foreach {kind pattern} {
  logic_reset *HSDeserializerX/dLogicRst_reg
  settled *cHSSettled_reg
  settled_sync *SyncAsyncSettled*oSyncStages_reg*
  serdes_sync *UseInternalReset*oSyncStages_reg*
 } {
  foreach cell [get_cells -hier -filter "NAME =~ $pattern"] {
   if {![regexp {DataLaneGen\[([01])\]} $cell ignored lane]} {error "Unknown data lane: $cell"}
   set clk [get_clocks -of_objects [get_pins $cell/C]]
   set controls "ASYNC_REG=[get_property ASYNC_REG $cell]";set starts {};set leaves {}
   foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
    set rp [get_property REF_PIN_NAME $pin]
    if {$rp in {D CE CLR PRE R S}} {
     foreach start [all_fanin -flat -startpoints_only -to $pin] {lappend starts $start}
     foreach leaf [all_fanin -flat -only_cells -to $pin] {lappend leaves $leaf}
     if {$rp in {CLR PRE R S}} {lappend controls $rp [get_nets -of_objects $pin]}
    }
   }
   puts $f "$kind\t$lane\t$cell\t[get_property REF_NAME $cell]\t[get_property INIT $cell]\t$clk\t$controls\t[lsort -unique $starts]\t[lsort -unique $leaves]"
  }
 }
 close $f
}
if {$build_index == 5} {
 set f [open [file join $stage llp_frame_boundary.tsv] w]
 set counter_cells [get_cells -hier -filter {NAME =~ *LLP_inst/mFrameCount_reg*}]
 set counter_clocks [get_clocks -of_objects [get_pins -of_objects $counter_cells -filter {REF_PIN_NAME == C}]]
 foreach {kind pattern} {
  pending_fs *LLP_inst/mFrameStartPending_reg
  payload_sof *LLP_inst/mReg_Tuser_reg*
  pending_crc *LLP_inst/mPacketEndPending_reg
 } {
  foreach cell [get_cells -hier -filter "NAME =~ $pattern"] {
   set reset [get_nets -of_objects [get_pins -quiet $cell/R]]
   puts $f "$kind\t$cell\t[get_property REF_NAME $cell]\t[get_property INIT $cell]\t[get_clocks -of_objects [get_pins $cell/C]]\t$reset\t$counter_clocks"
  }
 }
 close $f
}
foreach {command name options} {
    report_timing_summary timing {-delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10}
    report_clock_interaction clock_interaction {}
    report_clocks clocks {}
    report_exceptions exceptions {-coverage}
    report_cdc cdc {-details -no_waiver}
    report_drc drc {-ruledecks {default bitstream_checks} -no_waivers}
    report_methodology methodology {-no_waivers}
    report_bus_skew bus_skew {}
    report_utilization utilization {}
    report_io io {}
} {$command {*}$options -file [file join $stage $name.rpt]}
set f [open [file join $stage netlist_cells.tsv] w]
foreach cell [get_cells -hier] {puts $f "$cell\t[get_property REF_NAME $cell]\t[get_property IS_PRIMITIVE $cell]\t[get_property IS_BLACKBOX $cell]"}
close $f
set f [open [file join $stage structure.tsv] w]
set other_cells {}
foreach cell [get_cells -hier -filter {IS_PRIMITIVE}] {
    if {![regexp {^(FD|LUT|SRL)} [get_property REF_NAME $cell]]} {lappend other_cells $cell}
}
# Batch the common scalar INIT properties; inspect complete RAM/FIFO and other
# primitive INIT properties individually. Avoid listing every FF/LUT property.
foreach pattern {FD* LUT* SRL*} {
    set cells [get_cells -hier -filter "IS_PRIMITIVE && REF_NAME =~ $pattern"]
    if {[llength $cells]} {
        set refs [get_property REF_NAME $cells]
        set initials [get_property INIT $cells]
        if {[llength $cells] != [llength $initials]} {error "Incomplete INIT inventory: $pattern"}
        foreach cell $cells ref $refs init $initials {puts $f "$cell\t$ref\tINIT $init"}
    }
}
foreach cell $other_cells {
    set init {}
    foreach property [list_property $cell] {
        if {[string match INIT* $property]} {lappend init $property [get_property $property $cell]}
    }
    puts $f "$cell\t[get_property REF_NAME $cell]\t$init"
}
close $f
set f [open [file join $stage status_domain.tsv] w]
set counter_pins [get_pins -quiet {system_i/MIPI_CSI_2_RX_0/U0/MIPI_CSI2_Rx_inst/LLP_inst/mFrameCount_reg[*]/C system_i/MIPI_CSI_2_RX_0/U0/MIPI_CSI2_Rx_inst/LLP_inst/mCrcErrorCount_reg[*]/C}]
set held_pins [get_pins -quiet {system_i/MIPI_CSI_2_RX_0/U0/YesAXILITE.StatusSnapshot/held_reg[*]/C}]
foreach {kind pins} [list counters $counter_pins snapshot_held $held_pins] {
    set clocks [get_clocks -of_objects $pins]
    puts $f "$kind\t[llength $pins]\t$clocks"
    if {[llength $pins] != 64 || $clocks ne "clk_fpga_1"} {error "Wrong actual status producer domain: $kind $clocks"}
}
close $f
set f [open [file join $stage connections.tsv] w]
foreach cell [get_cells -hier -filter {REF_NAME =~ RAM* || REF_NAME =~ FIFO* || ASYNC_REG == TRUE}] {
    foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
        if {[regexp {^(C|CLK|RST|CLR|PRE|R|EN|WE|CE|D)[0-9A-Z]*$} [get_property REF_PIN_NAME $pin]]} {
            puts $f "$pin\t[all_fanin -flat -startpoints_only -to $pin]"
        }
    }
}
close $f
report_compile_order -used_in synthesis -file [file join $stage compile_order.rpt]
source [file join $root tools fixed_display.tcl]
fd::state_reports $stage
close_project
puts "CAMERA_SYNTHESIS_REPORTS_COMPLETE_NO_IMPLEMENTATION_NO_EXPORT"
