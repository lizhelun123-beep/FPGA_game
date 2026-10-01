# Configure the existing PL image and download the temporary PS vision ELF.
set app_root [file normalize [file join [file dirname [info script]] ..]]
set project_dir [file normalize [file join $app_root .. ..]]
set bit_file [file join $project_dir build hw system_wrapper.bit]
set xsa_file [file join $project_dir color_test.xsa]
set workspace [file join $project_dir build vision_ps_baremetal]
set ps_init [file join $workspace vision_ps_platform hw ps7_init.tcl]
set elf_file [file join $workspace output vision_ps_baremetal.elf]

foreach required [list $bit_file $xsa_file $ps_init $elf_file] {
    if {![file exists $required]} {
        puts stderr "ERROR: required build output not found: $required"
        exit 2
    }
}

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
    [glob -nocomplain [file join $app_root src *.c]] \
    [glob -nocomplain [file join $app_root src *.h]] \
    [glob -nocomplain [file join $app_root src i2c *]] \
    [glob -nocomplain [file join $app_root src dynclk *]] \
    [glob -nocomplain [file join $app_root src display_ctrl *]]]
assert_fresh $bit_file $bit_inputs \
    "vivado -mode batch -source color_test/tools/build_bitstream.tcl"
assert_fresh $xsa_file [list $bit_file] \
    "vivado -mode batch -source color_test/tools/build_bitstream.tcl"
assert_fresh $ps_init [list $xsa_file] \
    "xsct color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl"
assert_fresh $elf_file [concat [list $xsa_file] $software_inputs] \
    "xsct color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl"

if {[info exists ::env(VISION_JTAG_CHECK_ONLY)] &&
    $::env(VISION_JTAG_CHECK_ONLY) eq "1"} {
    puts "Vision JTAG artifact check passed: BIT/XSA/PS init/ELF are matched and fresh."
    exit 0
}

proc stop_if_running {} {
    if {[catch {stop} detail] &&
        ![string match -nocase "*already stopped*" $detail]} {
        error "Cannot stop Cortex-A9 #0: $detail"
    }
}

connect -url tcp:127.0.0.1:3121
puts "Programming temporary vision image:"
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

puts "JTAG programming complete. This image is volatile and is lost after power-off."
disconnect
exit 0
