set project_dir [file normalize [file join [file dirname [info script]] ..]]
set report_dir [file join $project_dir reports]
file mkdir $report_dir

open_project [file join $project_dir color_test.xpr]
set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
update_ip_catalog

set bd_file [get_files */system.bd]
open_bd_design $bd_file
update_compile_order -fileset sources_1
# Refresh module-reference parameters/ports from the current RTL before
# generating its wrapper.  Without this, Vivado can retain an older wrapper
# even when the referenced Verilog source was edited.
update_module_reference {system_axis_color_highlight_0_0}
save_bd_design
validate_bd_design
generate_target all $bd_file
update_compile_order -fileset sources_1

# These repository IPs contain the RAW colour fixes.  Vivado may otherwise
# reuse an out-of-context DCP even when its HDL changed, leaving a new top-level
# bitstream with old Bayer/WB logic inside it.
set camera_ooc_runs {}
foreach {ip_name run_name} {
    system_AXI_BayerToRGB_0_0       system_AXI_BayerToRGB_0_0_synth_1
    system_axis_color_highlight_0_0 system_axis_color_highlight_0_0_synth_1
} {
    # Vivado's cache ID for a module-reference wrapper does not include the
    # referenced RTL contents.  Disable cache use for these source-owned IPs
    # so an edited Bayer/WB module cannot silently reuse an older DCP.
    set ip_obj [get_ips -quiet $ip_name]
    if {[llength $ip_obj] != 0} {
        config_ip_cache -disable_for_ip $ip_obj
    }
    set run_obj [get_runs -quiet $run_name]
    if {[llength $run_obj] != 0} {
        reset_run $run_obj
        lappend camera_ooc_runs $run_name
    }
}
if {[llength $camera_ooc_runs] != 0} {
    launch_runs $camera_ooc_runs -jobs 2
    foreach run_name $camera_ooc_runs {
        wait_on_run $run_name
        set run_status [get_property STATUS [get_runs $run_name]]
        puts "BUILD_STATUS $run_name=$run_status"
        if {![string match "synth_design Complete*" $run_status] &&
            ![string equal $run_status "Using cached IP results"]} {
            error "Out-of-context synthesis failed: $run_name: $run_status"
        }
    }
}

reset_run synth_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set synth_status [get_property STATUS [get_runs synth_1]]
puts "BUILD_STATUS synth_1=$synth_status"
if {![string match "synth_design Complete*" $synth_status]} {
    error "Synthesis failed: $synth_status"
}

open_run synth_1
report_utilization -file [file join $report_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $report_dir post_synth_timing.rpt]
close_design

launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
set impl_status [get_property STATUS [get_runs impl_1]]
puts "BUILD_STATUS impl_1=$impl_status"
if {![string match "write_bitstream Complete*" $impl_status]} {
    error "Implementation/bitstream failed: $impl_status"
}

open_run impl_1
report_utilization -file [file join $report_dir post_impl_utilization.rpt]
report_timing_summary -file [file join $report_dir post_impl_timing.rpt]
write_hw_platform -fixed -include_bit -force \
    -file [file join $project_dir color_test.xsa]
close_design
close_project
