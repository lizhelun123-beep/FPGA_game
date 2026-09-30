set project_dir [file normalize [file join [file dirname [info script]] ..]]
set project_file [file join $project_dir color_test.xpr]
set repo_dir [file join $project_dir repo ip]
open_project $project_file
set_property ip_repo_paths [list $repo_dir] [current_project]
update_ip_catalog
set bd_path [file join $project_dir color_test.srcs sources_1 bd system system.bd]
set bd_file [get_files -quiet $bd_path]
if {[llength $bd_file] == 0} {
    add_files -norecurse -fileset sources_1 $bd_path
    set bd_file [get_files -quiet $bd_path]
}
open_bd_design $bd_file
foreach cell_name {axis_subset_converter_0 axi_vdma_1} {
    puts "=== $cell_name ==="
    foreach pin [get_bd_pins -of_objects [get_bd_cells /$cell_name]] {
        set pin_nets [get_bd_nets -quiet -of_objects $pin]
        set net_name "<none>"
        if {[llength $pin_nets] > 0} {
            set net_name [get_property NAME [lindex $pin_nets 0]]
        }
        puts "PIN [get_property NAME $pin] DIR=[get_property DIR $pin] WIDTH=[get_property LEFT $pin]:[get_property RIGHT $pin] NET=$net_name"
    }
    foreach pin [get_bd_intf_pins -of_objects [get_bd_cells /$cell_name]] {
        set pin_nets [get_bd_intf_nets -quiet -of_objects $pin]
        set net_name "<none>"
        if {[llength $pin_nets] > 0} {
            set net_name [get_property NAME [lindex $pin_nets 0]]
        }
        puts "IFPIN [get_property NAME $pin] MODE=[get_property MODE $pin] NET=$net_name"
    }
}
close_project
