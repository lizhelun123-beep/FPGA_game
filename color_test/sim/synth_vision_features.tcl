set root [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $root build vision_features_ooc]
set report_dir [file join $root reports]
file mkdir $report_dir

create_project -force vision_features_ooc $build_dir -part xc7z020clg400-2
add_files [file join $root rtl axis_vision_features.sv]
set_property top axis_vision_features [current_fileset]
synth_design -mode out_of_context -top axis_vision_features -part xc7z020clg400-2
create_clock -name feature_clk -period 7.000 [get_ports aclk]
report_utilization -file [file join $report_dir axis_vision_features_ooc_utilization.rpt]
report_timing_summary -delay_type min_max -max_paths 10 \
    -file [file join $report_dir axis_vision_features_ooc_timing.rpt]

set timing_paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $timing_paths] == 0} {
    error "No timed paths found for axis_vision_features"
}
set worst_slack [get_property SLACK [lindex $timing_paths 0]]
puts "FEATURE_OOC_WNS=$worst_slack"
puts "FEATURE_OOC_LUT=[llength [get_cells -hier -filter {PRIMITIVE_GROUP == LUT}]]"
puts "FEATURE_OOC_FF=[llength [get_cells -hier -filter {PRIMITIVE_GROUP == FLOP_LATCH}]]"
puts "FEATURE_OOC_DSP=[llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]"
if {$worst_slack < 0.0} {
    error "axis_vision_features misses 142.857 MHz timing: WNS=$worst_slack"
}
close_project
