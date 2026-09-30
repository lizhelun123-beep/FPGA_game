set project_dir [file normalize [file join [file dirname [info script]] ..]]
open_project [file join $project_dir color_test.xpr]
set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
update_ip_catalog -rebuild
open_bd_design [get_files */system.bd]
set bd_file [get_files */system.bd]
reset_target all $bd_file
generate_target all $bd_file
close_project
