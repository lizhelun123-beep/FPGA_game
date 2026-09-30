set project_dir [file normalize [file join [file dirname [info script]] ..]]
set project_file [file join $project_dir color_test.xpr]
set repo_dir [file join $project_dir repo ip]

open_project $project_file
set_property ip_repo_paths [list $repo_dir] [current_project]
update_ip_catalog

set bd_path [file join $project_dir color_test.srcs sources_1 bd system system.bd]
if {[llength [get_files -quiet $bd_path]] == 0} {
    add_files -norecurse -fileset sources_1 $bd_path
}
set bd_file [get_files -quiet $bd_path]
if {[llength $bd_file] == 0} {
    error "system.bd was not added to color_test"
}

open_bd_design $bd_file
puts "=== BD CELLS ==="
foreach cell [get_bd_cells] {
    puts "CELL [get_property NAME $cell] VLNV=[get_property VLNV $cell]"
}
puts "=== BD INTERFACE PINS ==="
foreach pin [get_bd_intf_pins] {
    puts "IFPIN [get_property NAME $pin] MODE=[get_property MODE $pin] VLNV=[get_property VLNV $pin]"
}
puts "=== BD INTERFACE NETS ==="
foreach net [get_bd_intf_nets] {
    puts "IFNET [get_property NAME $net] PINS=[join [get_bd_intf_pins -of_objects $net] {, }]"
}
puts "=== BD PINS ==="
foreach pin [get_bd_pins] {
    set direction [get_property DIR $pin]
    if {$direction ne ""} {
        puts "PIN [get_property NAME $pin] DIR=$direction"
    }
}
puts "=== VALIDATE ==="
validate_bd_design
close_project
