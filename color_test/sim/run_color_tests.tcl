set root [file normalize [file join [file dirname [info script]] ..]]
create_project -force vision_color_tests [file join $root build vision_color_tests] -part xc7z020clg400-2
add_files [file join $root rtl axis_color_highlight.v]
add_files [file join $root rtl axis_vision_features.sv]
add_files -fileset sim_1 [list \
    [file join $root sim tb_axis_color_highlight.sv] \
    [file join $root sim tb_axis_color_isp.sv] \
    [file join $root sim tb_axis_vision_features.sv]]
set_property xsim.simulate.runtime all [get_filesets sim_1]
foreach bench {tb_axis_color_highlight tb_axis_color_isp tb_axis_vision_features} {
    set_property top $bench [get_filesets sim_1]
    launch_simulation
    close_sim
}
close_project
