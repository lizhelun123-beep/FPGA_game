# Current canonical project only; preparation and expensive stages stay separate.
if {$argc != 2 || [lindex $argv 0] ni {prepare synth inspect implement export} || [lindex $argv 1] ni {2 3 4 5}} {error "Expected explicit stage and authorized build index2/3/4/5"}
set mode [lindex $argv 0]
set build_index [lindex $argv 1]
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build pl_rate93_production build_$build_index]
if {![file exists [file join $out authorization.json]]} {error "Missing additional build authorization"}
if {$mode eq "inspect"} {
 set camera_query_output $out
 source [file join $root build pl_rate93_production build_2 inspect_structure.tcl]
 source [file join $root build pl_rate93_production build_2 inspect_memory_controls.tcl]
 return
}
if {$mode eq "export"} {source [file join $root tools camera_production_export.tcl];return}
if {$mode ne "prepare"} {source [file join $root tools camera_production_build.tcl];return}
set done [file join $out native_prepared.txt]
if {[file exists $done]} {error "Preparation already completed;no automatic rerun"}
proc one {objects label} {
    if {[llength $objects] != 1} {error "Expected one $label: $objects"}
    return [lindex $objects 0]
}
open_project [file join $root color_test.xpr]
if {[get_property PART [current_project]] ne "xc7z020clg400-2"} {error "Wrong part"}
set_property ip_repo_paths [list [file join $root repo ip]] [current_project]
foreach folder {AXI_BayerToRGB MIPI_D_PHY_RX MIPI_CSI_2_RX axi_dynclk_v1_0 rgb2dvi_v1_3} {
    set core [ipx::open_core -set_current false [file join $root repo ip $folder component.xml]]
    if {$folder eq "MIPI_CSI_2_RX"} {
        set_property VERSION 1.2 $core
        foreach {parameter value} {C_S_AXI_LITE_ADDR_WIDTH 5 kVersionMinor 2} {
            set_property VALUE $value [one [ipx::get_user_parameters $parameter -of_objects $core] "CSI parameter $parameter"]
            set_property VALUE $value [one [ipx::get_hdl_parameters $parameter -of_objects $core] "CSI HDL parameter $parameter"]
        }
        foreach group_name {xilinx_anylanguagesynthesis xilinx_anylanguagebehavioralsimulation} {
            set group [one [ipx::get_file_groups $group_name -of_objects $core] "CSI file group $group_name"]
            if {[llength [ipx::get_files hdl/CSIStatusBridge.vhd -of_objects $group]] == 0} {
                set source [ipx::add_file hdl/CSIStatusBridge.vhd $group]
                set_property TYPE vhdlSource $source
            }
        }
    }
    ipx::update_checksums $core
    # Build4's repaired PHY package is already saved and bound by the offline
    # functional review. Retain its identity, including creation timestamp.
    if {$build_index < 4 || $folder ne "MIPI_D_PHY_RX"} {ipx::save_core $core}
    ipx::unload_core $core
}
update_ip_catalog -rebuild
set bd [one [get_files */system.bd] system.bd]
open_bd_design $bd
report_ip_status -file [file join $out ip_status_before_refresh.rpt]
foreach name {system_MIPI_D_PHY_RX_0_0 system_MIPI_CSI_2_RX_0_0} {
    upgrade_ip [one [get_ips -quiet $name] "camera instance refresh $name"]
}
set connections [open [file join $out interconnect_rebind.tsv] w]
foreach cell {ps7_0_axi_periph ps7_0_axi_periph/xbar} {
    set object [one [get_bd_cells -quiet $cell] $cell]
    puts $connections "$cell\tbefore\t[get_property CONFIG.NUM_MI $object]"
    if {$cell eq "ps7_0_axi_periph"} {
        set_property CONFIG.NUM_MI 7 $object
    } elseif {[get_property CONFIG.NUM_MI $object] != 7} {
        error "Parent interconnect did not refresh its read-only xbar"
    }
    puts $connections "$cell\tafter\t[get_property CONFIG.NUM_MI $object]"
}
close $connections
set csi [get_bd_cells MIPI_CSI_2_RX_0]
foreach {property expected} {C_S_AXI_LITE_ADDR_WIDTH 5 kVersionMinor 2} {
    puts "CSI_NATIVE_PARAMETER $property=[get_property CONFIG.$property $csi]"
    if {[get_property CONFIG.$property $csi] != $expected} {
        set_property CONFIG.$property $expected $csi
    }
}
foreach {cell property expected} {
    MIPI_D_PHY_RX_0 kPPISharedEnable true
    MIPI_D_PHY_RX_0 kLPFromLane0 false
    MIPI_D_PHY_RX_0 kAddDelayClk_ps 0
    MIPI_D_PHY_RX_0 kAddDelayData0_ps 0
    MIPI_D_PHY_RX_0 kAddDelayData1_ps 0
    MIPI_CSI_2_RX_0 kDebug false
    MIPI_CSI_2_RX_0 C_S_AXI_LITE_ADDR_WIDTH 5
    MIPI_CSI_2_RX_0 kVersionMinor 2
} {
    set object [one [get_bd_cells -quiet $cell] $cell]
    if {[get_property CONFIG.$property $object] ne $expected} {error "$cell.$property differs"}
}
if {[get_property VLNV [get_bd_cells MIPI_CSI_2_RX_0]] ne "digilentinc.com:ip:MIPI_CSI_2_RX:1.2"} {error "CSI ABI not refreshed"}
foreach name {axis_color_highlight_0} {
    if {![string match "xilinx.com:module_ref:*" [get_property VLNV [get_bd_cells $name]]]} {error "Not an HDL module reference: $name"}
    update_module_reference system_${name}_0
}
foreach f [get_files -of_objects [get_filesets constrs_1]] {
    set name [file tail $f]
    set historical_context [file normalize [file join $root .. output build game_app single_image_720p fixed_build_4 synth timing_context.xdc]]
    set prior_production_context [file normalize [file join $root build pl_rate93_production build_2 synth timing_context.xdc]]
    set build3_context [file normalize [file join $root build pl_rate93_production build_3 synth timing_context.xdc]]
    set build3_input_snapshot [file normalize [file join $root build pl_rate93_production build_3 synth input_model_effective.xdc]]
    set build4_context [file normalize [file join $root build pl_rate93_production build_4 synth timing_context.xdc]]
    set build4_input_snapshot [file normalize [file join $root build pl_rate93_production build_4 synth input_model_effective.xdc]]
    if {[file normalize $f] eq $historical_context || ($build_index >= 3 && [file normalize $f] eq $prior_production_context) || ($build_index >= 4 && [file normalize $f] in [list $build3_context $build3_input_snapshot]) || ($build_index == 5 && [file normalize $f] in [list $build4_context $build4_input_snapshot])} {
        # read_xdc in the old display report persisted this flattened snapshot.
        # Retain its file/evidence; it is not a current production input.
        set_property IS_ENABLED false $f
        continue
    }
    if {$name ni {system.xdc mipi.xdc hdmi_out.xdc debug_hub.xdc display720.xdc}} {error "Unreviewed XDC: $name"}
    set_property IS_ENABLED [expr {$name ne "debug_hub.xdc"}] $f
    if {$name eq "system.xdc"} {set_property PROCESSING_ORDER EARLY $f}
}
set libs [get_property XPM_LIBRARIES [current_project]]
if {[lsearch -exact $libs XPM_CDC] < 0} {lappend libs XPM_CDC}
set_property XPM_LIBRARIES $libs [current_project]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs synth_1]
set_property INCREMENTAL_CHECKPOINT {} [get_runs synth_1]
set_property SYNTH_CHECKPOINT_MODE None $bd
validate_bd_design
save_bd_design
reset_target all $bd
generate_target all $bd
foreach wrapper [make_wrapper -files $bd -top] {
    if {[llength [get_files -quiet $wrapper]] == 0} {add_files -norecurse -fileset sources_1 $wrapper}
}
foreach name {system_MIPI_D_PHY_RX_0_0 system_MIPI_CSI_2_RX_0_0 system_AXI_BayerToRGB_0_0 system_axi_dynclk_0_0 system_rgb2dvi_0_0} {
    config_ip_cache -disable_for_ip [one [get_ips -quiet $name] "cache IP $name"]
}
update_compile_order -fileset sources_1
report_ip_status -file [file join $out ip_status.rpt]
report_compile_order -used_in synthesis -file [file join $out compile_order.rpt]
set f [open [file join $out compile_sources.tsv] w]
foreach source [get_files -compile_order sources -used_in synthesis] {puts $f [file normalize $source]}
close $f
set f [open [file join $out native_parameters.tsv] w]
foreach cell {MIPI_D_PHY_RX_0 MIPI_CSI_2_RX_0 axi_vdma_1 axi_vdma_0 axi_dynclk_0 rgb2dvi_0 processing_system7_0} {
    set object [get_bd_cells $cell]
    foreach property [lsort [list_property $object]] {
        if {[string match CONFIG.* $property]} {puts $f "$cell\t$property\t[get_property $property $object]"}
    }
}
puts $f "part\t[get_property PART [current_project]]"
puts $f "top\t[get_property TOP [get_filesets sources_1]]"
puts $f "auto_incremental\t[get_property AUTO_INCREMENTAL_CHECKPOINT [get_runs synth_1]]"
puts $f "incremental_checkpoint\t[get_property INCREMENTAL_CHECKPOINT [get_runs synth_1]]"
puts $f "bd_checkpoint\t[get_property SYNTH_CHECKPOINT_MODE $bd]"
close $f
close_project
set f [open $done w];puts $f "NATIVE_PREPARATION_ONLY_NO_SYNTHESIS_IMPLEMENTATION_EXPORT";close $f
puts "CAMERA_NATIVE_PREPARATION_COMPLETE_NO_BUILD"
