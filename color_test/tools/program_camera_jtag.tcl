# Configure PL, initialize the Zynq PS, download the recovery application, and run it.
# Prerequisites:
#   1. Run tools/build_bitstream.tcl.
#   2. Run tools/build_camera_recovery.tcl.
#   3. Start hw_server and connect the AX7Z020B JTAG cable.

set project_dir [file normalize [file join [file dirname [info script]] ..]]
set bit_file [file join $project_dir color_test.runs impl_1 system_wrapper.bit]
set ps_init [file join $project_dir build camera_recovery camera_platform hw ps7_init.tcl]
set elf_file [file join $project_dir build camera_recovery output camera_recovery.elf]
set xsa_file [file join $project_dir color_test.xsa]

foreach required [list $bit_file $xsa_file $ps_init $elf_file] {
    if {![file exists $required]} {
        puts stderr "ERROR: required build output not found: $required"
        exit 2
    }
}

# A successful download is not useful when the PL, BSP and application came
# from different source revisions.  Refuse stale artifacts instead of silently
# producing a one-colour image with incompatible RAW/ISP settings.
proc assert_fresh {output inputs rebuild_hint} {
    set output_time [file mtime $output]
    foreach input $inputs {
        if {[file exists $input] && [file mtime $input] > $output_time} {
            puts stderr "ERROR: stale build output: $output"
            puts stderr "       newer input: $input"
            puts stderr "       rebuild with: $rebuild_hint"
            exit 2
        }
    }
}

set bit_inputs [concat \
    [glob -nocomplain [file join $project_dir color_test.srcs sources_1 bd system system.bd]] \
    [glob -nocomplain [file join $project_dir color_test.srcs constrs_1 new *]] \
    [glob -nocomplain [file join $project_dir rtl *]] \
    [glob -nocomplain [file join $project_dir repo ip AXI_BayerToRGB hdl *]] \
    [glob -nocomplain [file join $project_dir repo ip AXI_GammaCorrection hdl *]]]
set software_inputs [concat \
    [glob -nocomplain [file join $project_dir software mipi_hdmi mipi_hdmi src *.c]] \
    [glob -nocomplain [file join $project_dir software mipi_hdmi mipi_hdmi src *.h]] \
    [glob -nocomplain [file join $project_dir software mipi_hdmi mipi_hdmi src i2c *]] \
    [glob -nocomplain [file join $project_dir software mipi_hdmi mipi_hdmi src dynclk *]] \
    [glob -nocomplain [file join $project_dir software mipi_hdmi mipi_hdmi src display_ctrl *]]]
assert_fresh $bit_file $bit_inputs "vivado -mode batch -source tools/build_bitstream.tcl"
assert_fresh $xsa_file [list $bit_file] "vivado -mode batch -source tools/build_bitstream.tcl"
assert_fresh $ps_init [list $xsa_file] "xsct tools/build_camera_recovery.tcl"
assert_fresh $elf_file [concat [list $xsa_file] $software_inputs] \
    "xsct tools/build_camera_recovery.tcl"

# Allows CI/developers to validate the complete BIT/XSA/ELF set without
# touching a connected board.  Normal programming is unchanged when unset.
if {[info exists ::env(CAMERA_JTAG_CHECK_ONLY)] &&
    $::env(CAMERA_JTAG_CHECK_ONLY) eq "1"} {
    puts "JTAG artifact check passed: BIT/XSA/PS init/ELF are matched and fresh."
    exit 0
}

proc stop_if_running {} {
    if {[catch {stop} detail] &&
        ![string match -nocase "*already stopped*" $detail]} {
        error "Cannot stop Cortex-A9 #0: $detail"
    }
}

connect -url tcp:127.0.0.1:3121

puts "Programming matched camera image:"
puts "  BIT: $bit_file"
puts "  ELF: $elf_file"

if {[catch {
    targets -set -nocase -filter {name =~ "*APU*"}
    rst -system
    after 2000

    targets -set -nocase -filter {name =~ "xc7z020*"}
    fpga -file $bit_file
    after 500

    targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
    # A second invocation can find CPU0 running the previously downloaded ELF.
    # Stop it before ps7_init writes PS registers through the debug interface.
    stop_if_running
    configparams force-mem-access 1
    source $ps_init
    ps7_init
    ps7_post_config
    rst -processor
    stop_if_running
    dow $elf_file
    configparams force-mem-access 0
    con
} detail]} {
    puts stderr "ERROR: JTAG programming failed: $detail"
    catch {configparams force-mem-access 0}
    catch {disconnect}
    exit 3
}

puts "JTAG programming complete: $elf_file"
disconnect
exit 0
