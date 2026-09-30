set project_dir [file normalize [file join [file dirname [info script]] ..]]

open_project [file join $project_dir color_test.xpr]
set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
update_ip_catalog

open_run impl_1
write_hw_platform -fixed -include_bit -force \
    -file [file join $project_dir color_test.xsa]

close_design
close_project
