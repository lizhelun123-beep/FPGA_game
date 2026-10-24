# Download only the temporary PS application while keeping the PL image that
# is already configured on the board. Use this after a full PL configuration.
# Do not source ps7_init.tcl here: it would reinitialize PS PLL, clocks and
# DDR while PL VDMA may still be active.
set app_root [file normalize [file join [file dirname [info script]] ..]]
set project_dir [file normalize [file join $app_root .. ..]]
set xsa_file [file join $project_dir color_test.xsa]
set workspace [file join $project_dir build vision_ps_baremetal]
set elf_file [file join $workspace output vision_ps_baremetal.elf]

foreach required [list $xsa_file $elf_file] {
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

set software_inputs [concat \
    [glob -nocomplain [file join $app_root src *.c]] \
    [glob -nocomplain [file join $app_root src *.h]] \
    [glob -nocomplain [file join $app_root src i2c *]] \
    [glob -nocomplain [file join $app_root src dynclk *]] \
    [glob -nocomplain [file join $app_root src display_ctrl *]]]
assert_fresh $elf_file [concat [list $xsa_file] $software_inputs] \
    "xsct color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl"

if {[info exists ::env(VISION_JTAG_CHECK_ONLY)] &&
    $::env(VISION_JTAG_CHECK_ONLY) eq "1"} {
    puts "Vision ELF-only artifact check passed: XSA/ELF are fresh."
    exit 0
}

proc stop_if_running {} {
    if {[catch {stop} detail] &&
        ![string match -nocase "*already stopped*" $detail]} {
        error "Cannot stop Cortex-A9 #0: $detail"
    }
}

proc stop_video_dma {} {
    # AXI VDMA 1 S2MM and AXI VDMA 0 MM2S control registers. Clearing bit 0
    # quiesces DDR traffic before the processor is reset and the new app starts.
    foreach {name control status} {
        capture_s2mm 0x43000030 0x43000034
        display_mm2s 0x43010000 0x43010004
    } {
        set old_value [mrd -value $control]
        set new_value [expr {$old_value & 0xFFFFFFFE}]
        mwr -force $control $new_value
        puts [format "Quiesced %s VDMA CR: 0x%08x -> 0x%08x" \
            $name $old_value $new_value]
        set halted 0
        for {set attempt 0} {$attempt < 1000} {incr attempt} {
            if {([mrd -value $status] & 0x00000001) != 0} {
                set halted 1
                break
            }
            after 1
        }
        if {!$halted} {
            error "Timed out waiting for $name VDMA halt (SR=[mrd -value $status])"
        }
    }
}

connect -url tcp:127.0.0.1:3121
puts "Downloading temporary vision ELF onto the currently configured PL:"
puts "  ELF: $elf_file"
puts "  Existing PS/PL clocks and DDR are preserved; only VDMA is quiesced."

if {[catch {
    targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
    stop_if_running
    configparams force-mem-access 1
    stop_video_dma
    rst -processor
    stop_if_running
    dow $elf_file
    configparams force-mem-access 0
    con
} detail]} {
    puts stderr "ERROR: ELF download failed: $detail"
    catch {configparams force-mem-access 0}
    catch {disconnect}
    exit 3
}

puts "ELF download complete. This image is volatile and is lost after power-off."
disconnect
exit 0
