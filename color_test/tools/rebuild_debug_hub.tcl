set project_dir [file normalize [file join [file dirname [info script]] ..]]
set debug_xdc [file join $project_dir color_test.srcs constrs_1 new debug_hub.xdc]

open_project [file join $project_dir color_test.xpr]
if {[llength [get_files -quiet $debug_xdc]] == 0} {
    add_files -fileset constrs_1 $debug_xdc
}
set_property USED_IN_SYNTHESIS false [get_files $debug_xdc]

reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
set impl_status [get_property STATUS [get_runs impl_1]]
puts "BUILD_STATUS impl_1=$impl_status"
if {![string match "write_bitstream Complete*" $impl_status]} {
    error "Implementation/bitstream failed: $impl_status"
}

open_run impl_1
puts "DEBUG_HUB_SCAN_CHAIN=[get_property C_USER_SCAN_CHAIN [get_debug_cores dbg_hub]]"
puts "DEBUG_HUB_CLOCK_SOURCE=[all_fanin -to [get_pins dbg_hub/clk] -flat -startpoints_only]"
report_timing_summary -file [file join $project_dir reports post_impl_timing.rpt]
write_hw_platform -fixed -include_bit -force -file [file join $project_dir color_test.xsa]
close_design
close_project
