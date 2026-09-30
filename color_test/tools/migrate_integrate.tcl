set project_dir [file normalize [file join [file dirname [info script]] ..]]
set project_file [file join $project_dir color_test.xpr]
set repo_dir [file join $project_dir repo ip]
set rtl_file [file join $project_dir rtl axis_color_highlight.v]
set bd_path [file join $project_dir color_test.srcs sources_1 bd system system.bd]

open_project $project_file
set_property ip_repo_paths [list $repo_dir] [current_project]
update_ip_catalog

if {[llength [get_files -quiet $rtl_file]] == 0} {
    add_files -norecurse -fileset sources_1 $rtl_file
}
set bd_file [get_files -quiet $bd_path]
if {[llength $bd_file] == 0} {
    add_files -norecurse -fileset sources_1 $bd_path
    set bd_file [get_files -quiet $bd_path]
}
open_bd_design $bd_file

set vdma [get_bd_cells /axi_vdma_1]
set_property CONFIG.c_include_s2mm {1} $vdma

set color_cell [get_bd_cells -quiet /axis_color_highlight_0]
if {[llength $color_cell] > 0} {
    delete_bd_objs $color_cell
    save_bd_design
    close_bd_design [current_bd_design]
    open_bd_design $bd_file
}
set color_cell [create_bd_cell -type module -reference axis_color_highlight axis_color_highlight_0]
set color_clk [get_bd_pins -quiet /axis_color_highlight_0/aclk]

set subset [get_bd_cells /axis_subset_converter_0]
foreach net_name {axis_subset_converter_0_M_AXIS axis_color_highlight_0_M_AXIS} {
    set old_net [get_bd_intf_nets -quiet $net_name]
    if {[llength $old_net] > 0} {
        delete_bd_objs $old_net
    }
}

set subset_m [get_bd_intf_pins -quiet /axis_subset_converter_0/M_AXIS]
set color_s [get_bd_intf_pins -quiet /axis_color_highlight_0/S_AXIS]
set color_m [get_bd_intf_pins -quiet /axis_color_highlight_0/M_AXIS]
set vdma_s [get_bd_intf_pins -quiet /axi_vdma_1/S_AXIS_S2MM]

if {[llength $subset_m] > 0 && [llength $color_s] > 0 && [llength $color_m] > 0 && [llength $vdma_s] > 0} {
    connect_bd_intf_net $subset_m $color_s
    connect_bd_intf_net $color_m $vdma_s
} else {
    puts "INFO: AXIS interfaces were not inferred; connecting scalar ports."
    foreach sig {tdata tkeep tlast tuser tvalid} {
        connect_bd_net \
            [get_bd_pins /axis_subset_converter_0/m_axis_$sig] \
            [get_bd_pins /axis_color_highlight_0/s_axis_$sig]
        connect_bd_net \
            [get_bd_pins /axis_color_highlight_0/m_axis_$sig] \
            [get_bd_pins /axi_vdma_1/s_axis_s2mm_$sig]
    }
    connect_bd_net \
        [get_bd_pins /axis_subset_converter_0/m_axis_tready] \
        [get_bd_pins /axis_color_highlight_0/s_axis_tready]
    connect_bd_net \
        [get_bd_pins /axis_color_highlight_0/m_axis_tready] \
        [get_bd_pins /axi_vdma_1/s_axis_s2mm_tready]
}

set color_clk [get_bd_pins -quiet /axis_color_highlight_0/aclk]
if {[llength $color_clk] > 0 && [llength [get_bd_nets -quiet -of_objects $color_clk]] == 0} {
    connect_bd_net [get_bd_pins /axis_subset_converter_0/aclk] $color_clk
}

save_bd_design
validate_bd_design

set constr_dir [file join $project_dir color_test.srcs constrs_1 new]
foreach constr {system.xdc mipi.xdc hdmi_out.xdc} {
    set constr_file [file join $constr_dir $constr]
    if {[llength [get_files -quiet $constr_file]] == 0} {
        add_files -norecurse -fileset constrs_1 $constr_file
    }
}

set wrapper_files [make_wrapper -files [get_files $bd_file] -top]
set wrapper_file [lindex $wrapper_files 0]
if {[llength [get_files -quiet $wrapper_file]] == 0} {
    add_files -norecurse -fileset sources_1 $wrapper_file
}
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
set_property top system_wrapper [get_filesets sim_1]
update_compile_order -fileset sim_1
close_project
