# Explicit hardware authorization is required before running this script.
# Default: staged startup evidence. Pass "first-frame" to avoid intermediate
# stops; both modes leave CPU0 stopped. PL keeps running during CPU stops.
# Every breakpoint perturbs timing: repeat failures in first-frame mode.
set debug_mode stages
if {[llength $argv] > 1} {error "Usage: script.tcl ?stages|first-frame?"}
if {[llength $argv]} {set debug_mode [lindex $argv 0]}
if {$debug_mode ni {stages first-frame}} {error "Invalid debug mode"}

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

# Preflight uses the objdump shipped with this Vitis installation, before
# connecting or resetting hardware. Never use an address from another ELF.
if {![info exists ::env(XILINX_VITIS)]} {error "XILINX_VITIS is required"}
set objdump [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-objdump.exe]
set disassembly [exec $objdump -d $elf_file]
set symbols [exec $objdump -t $elf_file]
proc call_sites {assembly owner callee} {
    set inside 0
    set result {}
    foreach line [split $assembly \n] {
        if {[regexp {^[0-9a-fA-F]+ <([^>]+)>:} $line -> function]} {
            set inside [expr {$function eq $owner}]
        }
        if {$inside && [regexp {^\s*([0-9a-fA-F]+):.*\sbl\s+.*<([^>]+)>} $line -> address target] &&
            $target eq $callee} {
            lappend result 0x$address
        }
    }
    if {![llength $result]} {error "No $owner -> $callee call in current ELF"}
    return $result
}
proc object_address {symbols name} {
    foreach line [split $symbols \n] {
        if {[regexp {^([0-9a-fA-F]+)\s+.*\s([^ ]+)$} [string trim $line] -> address symbol] && $symbol eq $name} {
            return 0x$address
        }
    }
    error "Missing ELF object: $name"
}
set presented_address [object_address $symbols vision_frames_presented]
set probe_words_address [object_address $symbols vision_probe_words]
set camera_call [lindex [call_sites $disassembly main CameraStart] 0]
set i2c_call [call_sites $disassembly CameraStart i2c_init]
set configure_call [call_sites $disassembly CameraStart sensor_configure]
# VideoRegisters is called only once in VisionRunOnce, after ++frames_presented.
# At -O2, GCC may inline VisionRunOnce into main; source order leaves the
# FIRST_CAMERA_FRAME_COMMITTED call as main's final VideoRegisters call.
if {[catch {set commit_calls [call_sites $disassembly VisionRunOnce VideoRegisters]}]} {
    set main_video_calls [call_sites $disassembly main VideoRegisters]
    set commit_calls [list [lindex $main_video_calls end]]
}
if {[llength $i2c_call] != 1 || [llength $configure_call] != 1 || [llength $commit_calls] != 1} {
    error "Ambiguous stage calls; inspect current ELF before hardware use"
}
set stages [list \
    [list MAIN_ENTER &main] \
    [list CAMERA_CALL_PENDING $camera_call] \
    [list CAMERA_ENTER &CameraStart] \
    [list GPIO_DELAYS_DONE_I2C_PENDING [lindex $i2c_call 0]] \
    [list SENSOR_CONFIG_PENDING [lindex $configure_call 0]] \
    [list CAMERA_CHECK_ENTER &CameraCheck] \
    [list VALIDATED_FRAME_PROCESSING &VisionRunOnce] \
    [list FIRST_FRAME_COMMIT [lindex $commit_calls 0]]]
if {$debug_mode eq "first-frame"} {set stages [list [lindex $stages end]]}
puts "ELF=$elf_file size=[file size $elf_file] mtime=[file mtime $elf_file] mode=$debug_mode"
puts "STAGE_PLAN=$stages presented_address=$presented_address"

proc snapshot {stage} {
    global presented_address probe_words_address
    puts "SNAPSHOT stage=$stage host_ms=[clock milliseconds]"
    foreach register {pc lr sp cpsr} {
        if {[catch {rrd $register} value]} {set value "UNAVAILABLE: $value"}
        puts "$register=$value"
    }
    if {[catch {bt} value]} {set value "UNAVAILABLE: $value"}
    puts "BACKTRACE=$value"
    # Read only: do not acknowledge W1C status, reset counters, or write UART.
    foreach {name address} [list UART1_CR 0xE0001000 UART1_SR 0xE000102C \
        CSI_CONTROL_STATUS 0x43C30000 CSI_LONG_PACKETS 0x43C30004 \
        CSI_CRC_ERRORS 0x43C30008 S2MM_CR 0x43000030 S2MM_SR 0x43000034 \
        CAPTURE_PARK 0x43000028 MM2S_CR 0x43010000 MM2S_SR 0x43010004 \
        FRAMES_PRESENTED $presented_address] {
        if {[catch {mrd -force -value $address} value]} {set value "UNAVAILABLE: $value"}
        puts "$name=$value"
    }
    if {[string match "*FIRST_FRAME_COMMIT*" $stage]} {
        puts [format "PROBE_WORDS_ADDRESS=%08X" $probe_words_address]
        for {set i 0} {$i < 27} {incr i} {
            set value [mrd -force -value [expr {$probe_words_address + 4 * $i}]]
            puts [format "PROBE_WORD_%02d=%08X" $i $value]
        }
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
    configparams force-mem-access 0
    foreach stage $stages {
        lassign $stage name location
        # One hardware breakpoint at a time; no DDR instruction patching.
        set breakpoint [bpadd -addr $location -type hw]
        set wait_failed [catch {con -block -timeout 60} wait_detail]
        # XSCT may report timeout differently by version. Inspect stop reason
        # as well as command result; an arbitrary halt is never a stage hit.
        set target_state [targets -nocase -filter {name =~ "*Cortex-A9*#0"}]
        set expected $location
        if {[string index $location 0] eq "&"} {
            set expected [object_address $symbols [string range $location 1 end]]
        }
        if {$wait_failed || ![string match -nocase "*breakpoint*" $target_state]} {
            stop_if_running
        }
        set pc_text ""
        catch {set pc_text [rrd pc]}
        set pc_matches 0
        if {[regexp -nocase {pc:\s*(?:0x)?([0-9a-f]+)} $pc_text -> pc_hex]} {
            scan $pc_hex %x pc_value
            set pc_matches [expr {$pc_value == $expected}]
        }
        set hit [expr {!$wait_failed && $pc_matches &&
            [string match -nocase "*breakpoint*" $target_state]}]
        if {!$hit} {stop_if_running}
        snapshot [expr {$hit ? $name : "UNREACHED_$name"}]
        if {!$hit} {
            # PL continues while CPU is halted; two samples show packet/CRC
            # progress without relying on UART. Reads are not atomic.
            after 500
            snapshot "UNREACHED_${name}_PLUS_500MS_CPU_HALTED"
        }
        bpremove $breakpoint
        if {!$hit} {
            error "Stage $name unconfirmed: wait=$wait_detail target=$target_state"
        }
        puts "STAGE_HIT=$name location=$location"
        if {$name eq "FIRST_FRAME_COMMIT"} {
            set count [mrd -force -value $presented_address]
            if {$count != 1} {error "Commit breakpoint reached but frames_presented=$count (expected 1)"}
        }
    }
} detail]} {
    puts stderr "ERROR: HDMI debug JTAG evidence flow stopped: $detail"
    if {[info exists breakpoint]} {catch {bpremove $breakpoint}}
    catch {configparams force-mem-access 0}
    catch {disconnect}
    exit 3
}
puts "First camera frame committed; CPU0 left stopped. No further board operation performed."
disconnect
exit 0
