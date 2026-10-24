# Resume the already loaded minimal vision ELF, run without breakpoints, then
# stop once and read its flushed probe export. Explicit hardware authorization
# is required before running this script.
set app_root [file normalize [file join [file dirname [info script]] ..]]
set run_ms 10000
if {[llength $argv] > 1} {error "Usage: script.tcl ?run_ms?"}
if {[llength $argv] == 1} {set run_ms [lindex $argv 0]}
set project_dir [file normalize [file join $app_root .. ..]]
set elf_file [file join $project_dir build vision_ps_baremetal output vision_ps_baremetal.elf]
if {![file exists $elf_file]} {error "Missing ELF: $elf_file"}
if {![info exists ::env(XILINX_VITIS)]} {error "XILINX_VITIS is required"}
set nm [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-nm.exe]
set symbols [exec $nm $elf_file]

proc object_address {symbols name} {
    foreach line [split $symbols \n] {
        if {[regexp {^([0-9a-fA-F]+)\s+.*\s([^ ]+)$} [string trim $line] -> address symbol] && $symbol eq $name} {
            return 0x$address
        }
    }
    error "Missing ELF object: $name"
}

set probe_words_address [object_address $symbols vision_probe_words]
set calibration_words_address [object_address $symbols vision_calibration_words]
set presented_address [object_address $symbols vision_frames_presented]
connect -url tcp:127.0.0.1:3121
if {[catch {
    targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
    con
    after $run_ms
    stop
    puts "LIVE_PROBE CPU0 stopped after $run_ms ms breakpoint-free run"
    foreach {name address} [list CSI_CONTROL_STATUS 0x43C30000 \
        CSI_LONG_PACKETS 0x43C30004 CSI_CRC_ERRORS 0x43C30008 \
        S2MM_CR 0x43000030 S2MM_SR 0x43000034 CAPTURE_PARK 0x43000028 \
        MM2S_CR 0x43010000 MM2S_SR 0x43010004 \
        FRAMES_PRESENTED $presented_address] {
        set value [mrd -force -value $address]
        puts "$name=$value"
    }
    puts [format "PROBE_WORDS_ADDRESS=%08X" $probe_words_address]
    for {set i 0} {$i < 27} {incr i} {
        set value [mrd -force -value [expr {$probe_words_address + 4 * $i}]]
        puts [format "PROBE_WORD_%02d=%08X" $i $value]
    }
    puts [format "CALIBRATION_WORDS_ADDRESS=%08X" $calibration_words_address]
    for {set i 0} {$i < 39} {incr i} {
        set value [mrd -force -value [expr {$calibration_words_address + 4 * $i}]]
        puts [format "CALIBRATION_WORD_%02d=%08X" $i $value]
    }
} detail]} {
    puts stderr "ERROR: live vision probe failed: $detail"
    catch {stop}
    catch {disconnect}
    exit 3
}
puts "Live probe captured; CPU0 left stopped."
disconnect
exit 0
