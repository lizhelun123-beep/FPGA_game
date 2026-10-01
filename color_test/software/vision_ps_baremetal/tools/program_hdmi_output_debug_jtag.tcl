# Program the standalone HDMI-output debug bitstream and stop CPU0 at
# CameraStart(), leaving the PL video path running for ILA capture.

set app_root [file normalize [file join [file dirname [info script]] ..]]
set project_dir [file normalize [file join $app_root .. ..]]
set bit_file [file join $project_dir build hdmi_output_debug system_wrapper_hdmi_debug.bit]
set ps_init [file join $project_dir build vision_ps_baremetal vision_ps_platform hw ps7_init.tcl]
set elf_file [file join $project_dir build vision_ps_baremetal output vision_ps_baremetal.elf]

foreach required [list $bit_file $ps_init $elf_file] {
    if {![file exists $required]} {
        puts stderr "ERROR: required debug build output not found: $required"
        exit 2
    }
}

proc stop_if_running {} {
    if {[catch {stop} detail] &&
        ![string match -nocase "*already stopped*" $detail]} {
        error "Cannot stop Cortex-A9 #0: $detail"
    }
}

connect -url tcp:127.0.0.1:3121
if {[catch {
    targets -set -nocase -filter {name =~ "*APU*"}
    rst -system
    after 2000
    targets -set -nocase -filter {name =~ "xc7z020*"}
    fpga -file $bit_file
    after 500
    targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
    stop_if_running
    configparams force-mem-access 1
    source $ps_init
    ps7_init
    ps7_post_config
    rst -processor
    stop_if_running
    dow $elf_file
    bpadd -addr 0x00111BD0
    configparams force-mem-access 0
    con
    after 8000
    stop_if_running
    puts "CAMERA_START_BREAKPOINT_PC=[rrd pc]"
    puts "CAMERA_START_BREAKPOINT_LR=[rrd lr]"
} detail]} {
    puts stderr "ERROR: HDMI debug JTAG setup failed: $detail"
    catch {configparams force-mem-access 0}
    catch {disconnect}
    exit 3
}

puts "HDMI debug bitstream programmed and CPU0 left stopped at CameraStart breakpoint."
disconnect
exit 0
