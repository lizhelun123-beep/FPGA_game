# Fixed candidate only. No tap/phase scan, project regeneration or board access.
# Launched only after the Python functional gate accepts both test layers.
# --synth-only is a runtime-read recovery check; it never refreshes OOC reports.
set synth_only 0
if {[llength $argv]} {
    if {$argv ne "--synth-only"} { error "Expected no arguments or --synth-only" }
    set synth_only 1
}
set root [file normalize [file join [file dirname [info script]] ..]]
set ip [file join $root repo ip MIPI_D_PHY_RX hdl]
set out [file join $root build dphy_sampling_ooc]
if {$synth_only} { set out [file join $root build vivado_runtime dphy_sampling] }
set reports [file join $root reports dphy_sampling_ooc]
file mkdir $out
file mkdir $reports
cd $out
set fp [open [file join $root build dphy_sampling functional_gate.txt] r]
if {[string trim [read $fp]] ne "UNFORCED_PRIMITIVE_AND_CONTROLLER_PASS"} { error "Functional gate not passed" }
close $fp

# Read only the existing board pin assignment. Do not rebuild/query old timing.
set checkpoint [file join $root color_test.runs impl_1 system_wrapper_routed.dcp]
set cached_pins [file join $reports pins.txt]
if {[file isfile $cached_pins] && [file mtime $cached_pins] >= [file mtime $checkpoint]} {
    set pinmap {}
    set f [open $cached_pins r]
    foreach line [split [string trim [read $f]] \n] {
        lassign $line name pin ios
        dict set pinmap $name [list $pin $ios]
    }
    close $f
    puts "REUSE_VERIFIED_MIPI_PINMAP $cached_pins"
} else {
open_checkpoint [file join $root color_test.runs impl_1 system_wrapper_routed.dcp]
set pinmap {}
set f [open [file join $reports pins.txt] w]
foreach p [get_ports dphy*] {
    set name [get_property NAME $p]
    set name [string map {dphy_hs_clock_clk_p dphy_clk_hs_p dphy_hs_clock_clk_n dphy_clk_hs_n} $name]
    set pin [get_property PACKAGE_PIN $p]
    set ios [get_property IOSTANDARD $p]
    if {$pin eq ""} { error "Missing physical pin $name" }
    dict set pinmap $name [list $pin $ios]
    puts $f "$name $pin $ios"
}
close $f
if {[dict size $pinmap] != 12} { error "Expected 12 fixed MIPI HS/LP pins" }
close_design

}
if {[dict size $pinmap] != 12} { error "Expected twelve fixed MIPI pins" }
foreach {port pin} {dphy_clk_hs_p Y7 dphy_clk_hs_n Y6 {dphy_data_hs_p[0]} W11 {dphy_data_hs_n[0]} Y11 {dphy_data_hs_p[1]} U9 {dphy_data_hs_n[1]} U8} {
    if {[lindex [dict get $pinmap $port] 0] ne $pin} { error "Changed fixed HS pin $port" }
}

foreach name {DPHY_Pkg SyncAsync SyncAsyncReset DebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver} {
    read_vhdl -vhdl2008 [file join $ip $name.vhd]
}
read_vhdl -vhdl2008 [file join $root sim dphy_sampling_ooc.vhd]
set tool_common [file join $::env(XILINX_VIVADO) scripts rt data common.tcl]
if {![file readable $tool_common]} { error "Synthesis runtime script is unreadable: $tool_common" }
set runtime_probe [open $tool_common r]
read $runtime_probe
close $runtime_probe
puts "SYNTH_RUNTIME_READABLE $tool_common"
# Keep two threads on the normal Windows/native-console launch path.
# Thread count alone did not cure the old launcher's intermittent Tcl failures.
set_param synth.maxThreads 2
puts "SYNTH_RUNTIME_THREADS 2"
synth_design -mode out_of_context -top dphy_sampling_ooc -part xc7z020clg400-2 -flatten_hierarchy rebuilt
if {$synth_only} {
    puts "DPHY_RUNTIME_SYNTH_PASS; no implementation, CDC or timing acceptance"
    close_design
    exit 0
}
create_clock -name mipi_hs_clk -period 3.571 [get_ports dphy_clk_hs_p]
create_clock -name ref_clk -period 5.000 [get_ports refclk]
read_xdc [file join $ip MIPI_DPHY_Receiver_clocks.xdc]
# Reuse existing synchronizer constraints; no additional timing exception.
read_xdc -ref MIPI_DPHY_Receiver [file join $ip MIPI_DPHY_Receiver.xdc]
dict for {name assignment} $pinmap {
    lassign $assignment pin ios
    set_property PACKAGE_PIN $pin [get_ports $name]
    set_property IOSTANDARD $ios [get_ports $name]
}
if {[llength [get_cells -hier -filter {REF_NAME == MMCME2_ADV}]] != 1 ||
    [llength [get_cells -hier -filter {REF_NAME == BUFH}]] != 3 ||
    [llength [get_cells -hier -filter {REF_NAME == IDELAYE2}]] != 0} { error "Candidate primitive structure mismatch" }
set serdes [get_cells -hier -filter {REF_NAME == ISERDESE2 && NAME =~ *HSDeserializerX/Deserializer}]
if {[llength $serdes] != 2} { error "Missing actual two-lane data SERDES" }
foreach cell $serdes {
    if {[get_property IOBDELAY $cell] ne "NONE"} { error "Not D-direct: $cell" }
}
opt_design
report_cdc -details -file [file join $reports cdc.rpt]
place_design
report_utilization -hierarchical -file [file join $reports utilization_placed.rpt]
report_utilization -file [file join $reports utilization.rpt]
route_design
write_checkpoint -force [file join $out candidate_routed.dcp]
report_drc -file [file join $reports drc.rpt]
report_methodology -file [file join $reports methodology.rpt]
report_clock_utilization -file [file join $reports clocks.rpt]
report_timing_summary -delay_type min_max -file [file join $reports timing.rpt]
set f [open [file join $reports structure.txt] w]
foreach c [get_cells -hier -filter {REF_NAME == MMCME2_ADV || REF_NAME == BUFH || REF_NAME == ISERDESE2 || REF_NAME == IDELAYCTRL}] {
    puts $f "$c [get_property REF_NAME $c] LOC=[get_property LOC $c] BEL=[get_property BEL $c]"
}
close $f
# Both data transitions/checks/process corners and differential pins. Each
# request retains the rise and fall capture paths: 32 requests / 64 items.
set report [file join $reports sampling_corners.rpt]
set f [open $report w]; puts $f "# BUFH_DDIRECT_M3 fixed 180/45 seed; actual D endpoints"; close $f
set requests 0
foreach cell $serdes {
    if {![regexp {DataLaneGen\[([01])\]} $cell -> lane]} { error "Unknown lane $cell" }
    foreach pn {p n} {
        set src [get_ports [format {dphy_data_hs_%s[%d]} $pn $lane]]
        foreach corner {Fast Slow} {
            foreach transition {rise fall} {
                foreach type {max min} {
                    report_timing -from $src -${transition}_to [get_pins $cell/D] -corner $corner -delay_type $type -max_paths 8 -nworst 8 -significant_digits 3 -path_type full_clock_expanded -append -file $report
                    incr requests
                }
            }
        }
    }
}
puts "DPHY_FIXED_OOC_COMPLETE requests=$requests; timing/CDC acceptance requires report audit"
close_design
