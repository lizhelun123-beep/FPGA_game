set project_dir [file normalize [file join [file dirname [info script]] ..]]
open_project [file join $project_dir color_test.xpr]
set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
update_ip_catalog
open_bd_design [get_files */system.bd]
validate_bd_design
report_ip_status
foreach ip [get_ips] {
    puts [format "IP_STATUS name=%s locked=%s upgrade=%s" \
        [get_property NAME $ip] \
        [get_property IS_LOCKED $ip] \
        [get_property UPGRADE_VERSIONS $ip]]
}
close_project
