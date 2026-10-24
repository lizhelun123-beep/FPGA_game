# Explicit fixed display profile; the legacy production entry remains below.
# Preparation never runs merely by sourcing the helper. No camera build fallback.
if {[lindex $argv 0] eq "-display720"} {
    source [file join [file dirname [info script]] fixed_display.tcl]
    fixed_display_main {*}[lrange $argv 1 end]
    return
}
if {[llength $argv] != 0} { error "Unknown build profile: $argv" }
set project_dir [file normalize [file join [file dirname [info script]] ..]]
set report_dir [file join $project_dir reports]
set artifact_dir [file join $project_dir build hw]
file mkdir $report_dir
file mkdir $artifact_dir

open_project [file join $project_dir color_test.xpr]
set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
set debug_hub_xdc [get_files -quiet */debug_hub.xdc]
if {[llength $debug_hub_xdc] != 0} {
    set_property IS_ENABLED false $debug_hub_xdc
}

# Refresh the packaged Bayer IP checksum before regenerating the block design.
# Without this, Vivado can keep an old ipshared HDL copy even after the
# canonical repository VHDL changes, and a reset OOC run will synthesize that
# stale copy into an otherwise new bitstream.
set bayer_component [file join $project_dir repo ip AXI_BayerToRGB component.xml]
set bayer_core [ipx::open_core -set_current false $bayer_component]
ipx::update_checksums $bayer_core
ipx::save_core $bayer_core
ipx::unload_core $bayer_core
update_ip_catalog -rebuild

set bd_file [get_files */system.bd]
open_bd_design $bd_file
foreach ip_name {
    system_AXI_BayerToRGB_0_0
    system_MIPI_D_PHY_RX_0_0
    system_MIPI_CSI_2_RX_0_0
} {
    upgrade_ip [get_ips $ip_name]
}
set csi_cell [get_bd_cells MIPI_CSI_2_RX_0]
set_property CONFIG.kDebug false $csi_cell
if {[get_property CONFIG.kDebug $csi_cell] ne "false"} {
    error "Production build requires MIPI_CSI_2_RX_0 CONFIG.kDebug=false"
}
update_compile_order -fileset sources_1
# Refresh module-reference parameters/ports from the current RTL before
# generating its wrapper.  Without this, Vivado can retain an older wrapper
# even when the referenced Verilog source was edited.
update_module_reference {system_axis_color_highlight_0_0}
save_bd_design
validate_bd_design
reset_target all $bd_file
generate_target all $bd_file
update_compile_order -fileset sources_1

# These repository IPs contain the RAW colour fixes.  Vivado may otherwise
# reuse an out-of-context DCP even when its HDL changed, leaving a new top-level
# bitstream with old Bayer/WB logic inside it.
set camera_ooc_runs {}
foreach {ip_name run_name} {
    system_MIPI_CSI_2_RX_0_0      system_MIPI_CSI_2_RX_0_0_synth_1
    system_AXI_BayerToRGB_0_0       system_AXI_BayerToRGB_0_0_synth_1
    system_axis_color_highlight_0_0 system_axis_color_highlight_0_0_synth_1
    system_axis_subset_converter_0_0 system_axis_subset_converter_0_0_synth_1
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
report_clock_interaction -file [file join $report_dir post_impl_clock_interaction.rpt]
report_cdc -details -file [file join $report_dir post_impl_cdc.rpt]

set worst_setup_path [get_timing_paths -delay_type max -max_paths 1]
if {[llength $worst_setup_path] == 0} {
    error "Implementation completed without any setup timing paths"
}
set worst_setup_slack [get_property SLACK [lindex $worst_setup_path 0]]
puts "POST_IMPL_WNS=$worst_setup_slack"
if {$worst_setup_slack < 0.0} {
    error "Production implementation has negative setup slack: WNS=$worst_setup_slack"
}

set worst_hold_path [get_timing_paths -delay_type min -max_paths 1]
if {[llength $worst_hold_path] == 0} {
    error "Implementation completed without any hold timing paths"
}
set worst_hold_slack [get_property SLACK [lindex $worst_hold_path 0]]
puts "POST_IMPL_WHS=$worst_hold_slack"
if {$worst_hold_slack < 0.0} {
    error "Production implementation has negative hold slack: WHS=$worst_hold_slack"
}

# Vivado owns color_test.runs and reset_run is allowed to delete everything in
# it. Publish programming artifacts only after both timing gates pass.
set impl_dir [get_property DIRECTORY [get_runs impl_1]]
set run_bit [file join $impl_dir system_wrapper.bit]
set run_ltx [file join $impl_dir system_wrapper.ltx]
if {![file exists $run_bit]} {
    error "Implementation completed but required artifact is missing: $run_bit"
}
set artifact_bit [file join $artifact_dir system_wrapper.bit]
set artifact_ltx [file join $artifact_dir system_wrapper.ltx]
file copy -force $run_bit $artifact_bit
puts "BUILD_ARTIFACT BIT=$artifact_bit"
if {[file exists $run_ltx]} {
    file copy -force $run_ltx $artifact_ltx
    puts "BUILD_ARTIFACT LTX=$artifact_ltx"
} else {
    if {[file exists $artifact_ltx]} {
        file delete -force $artifact_ltx
    }
    puts "BUILD_ARTIFACT LTX=none (production debug cores disabled)"
}

write_hw_platform -fixed -include_bit -force \
    -file [file join $project_dir color_test.xsa]
close_design
close_project
