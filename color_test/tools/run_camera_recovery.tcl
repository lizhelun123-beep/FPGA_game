connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
stop
rst -processor
after 500
set project_dir [file normalize [file join [file dirname [info script]] ..]]
set elf_file [file join $project_dir build camera_recovery output camera_recovery.elf]
if {![file exists $elf_file]} {
    puts stderr "ERROR: application not found: $elf_file"
    puts stderr "Run tools/build_camera_recovery.tcl first."
    disconnect
    exit 2
}
dow $elf_file
con
disconnect
exit 0
