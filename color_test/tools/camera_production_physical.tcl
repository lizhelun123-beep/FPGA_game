# Implementation consumes the already audited checkpoint, never a project run.
if {$mode ne "implement"} {error "Export gate not open"}
set audit [file join $root tools camera_production_audit.py]
exec python -I $audit claim_implementation $build_index
open_project [file join $root color_test.xpr]
open_checkpoint [file join $out synth synthesized.dcp]
set model_stage [file join $out implementation_input_model]
file mkdir $model_stage
source [file join $root tools camera_input_model.tcl]
camera_apply_declared_input_model $root $model_stage
opt_design
place_design
route_design
set stage [file join $out route]
file mkdir $stage
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
set f [open [file join $stage status_domain.tsv] w]
foreach {kind pattern} {
    counters {system_i/MIPI_CSI_2_RX_0/U0/MIPI_CSI2_Rx_inst/LLP_inst/mFrameCount_reg[*]/C system_i/MIPI_CSI_2_RX_0/U0/MIPI_CSI2_Rx_inst/LLP_inst/mCrcErrorCount_reg[*]/C}
    snapshot_held {system_i/MIPI_CSI_2_RX_0/U0/YesAXILITE.StatusSnapshot/held_reg[*]/C}
} {
    set pins [get_pins -quiet $pattern]
    puts $f "$kind\t[llength $pins]\t[get_clocks -of_objects $pins]"
}
close $f
set f [open [file join $stage pins.tsv] w]
foreach p [get_ports] {puts $f "$p\t[get_property PACKAGE_PIN $p]\t[get_property IOSTANDARD $p]"}
close $f
source [file join $root tools fixed_display.tcl]
fd::state_reports $stage
# state_reports restores the real startup MMCM attributes/constraints first.
write_checkpoint [file join $stage routed.dcp]
close_project
puts "CAMERA_IMPLEMENTATION_REPORTS_COMPLETE_NO_EXPORT"
