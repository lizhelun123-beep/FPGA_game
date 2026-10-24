# Focused behavioral simulation and synthesis/CDC of canonical production
# D-PHY RTL only. No project regeneration, implementation, bitstream or hardware.
# Optional -tclargs sim runs only the behavioral simulation.
if {$argc > 1 || ($argc == 1 && [lindex $argv 0] ne "sim")} { error "Expected no argument, or sim" }
set root [file normalize [file join [file dirname [info script]] ..]]
set ip_dir [file join $root repo ip MIPI_D_PHY_RX hdl]
set build_dir [file join $root build dphy_settled]
set report_dir [file join $root reports]
file mkdir $build_dir
file mkdir $report_dir
cd $build_dir

# XSim observes the actual DUT chains, rather than a copied synchronizer model.
set checks [open settled_checks.tcl w]
puts $checks {
set top /tb_dphy_settled
set count 0
proc drive {name value} {
    global top
    add_force $top/$name $value
}
proc check {lane signal expected} {
    global top count
    set hdl_name [dict get {dsettled dSettled dlogicrst dLogicRst dserdesrst dSerdesRst} $signal]
    set path [format {%s/\lanes(%d)\/dut/%s} $top $lane $hdl_name]
    set actual [get_value -radix bin $path]
    if {$actual ne $expected} { error "$path expected $expected, got $actual at [current_time]" }
    incr count
}
proc both {signal expected} {
    foreach lane {0 1} { check $lane $signal $expected }
}
proc tick {{low_time 7.142}} {
    drive div_clk 0
    run $low_time ns
    drive div_clk 1
    run 0.001 ns
}
proc fall {} {
    run 7.141 ns
    drive div_clk 0
    run 0.001 ns
}
drive div_clk 0
drive settled 00
drive rst 1
run 200 ns
both dsettled 0
both dlogicrst 1

# Startup with a stopped byte clock: releasing both asynchronous inputs must
# not release either chain until two rising edges arrive.
drive rst 0
drive settled 11
run 100 ns
both dsettled 0
both dserdesrst 1
tick
both dsettled 0
both dserdesrst 1
fall
tick
both dsettled 1
both dserdesrst 0
fall
tick
both dlogicrst 1
fall
tick
both dlogicrst 0
fall

# Independent lanes, a short clear pulse entirely while DivClk is stopped,
# and recovery. The pulse must reset BOTH stages, not just the output stage.
drive settled 10
run 0.001 ns
check 0 dsettled 0
check 1 dsettled 1
run 1 ns
drive settled 11
run 100 ns
check 0 dsettled 0
check 1 dsettled 1
tick
check 0 dsettled 0
check 1 dsettled 1
fall
tick
both dsettled 1
fall

# Assert while stopped high as well as stopped low; sweep release offsets
# over a byte period. Digital simulation checks latency, not metastability.
for {set phase 0} {$phase < 16} {incr phase} {
    drive div_clk [expr {$phase % 2}]
    run 1 ns
    drive settled 00
    run 0.001 ns
    both dsettled 0
    drive div_clk 0
    run [expr {0.2 + $phase * 0.85}] ns
    drive settled 11
    run 0.001 ns
    both dsettled 0
    tick [expr {0.001 + $phase * 0.85}]
    both dsettled 0
    fall
    both dsettled 0
    tick
    both dsettled 1
    fall
}

# Warm reset/clock-loss boundary: canonical lane logic clears cHSSettled
# on clock loss. Apply that resulting clear together with the SERDES reset.
drive rst 1
drive settled 00
run 0.001 ns
both dsettled 0
both dserdesrst 1
both dlogicrst 1
run 100 ns
drive rst 0
drive settled 11
run 100 ns
both dsettled 0
both dserdesrst 1
tick
both dsettled 0
both dserdesrst 1
fall
tick
both dsettled 1
both dserdesrst 0
fall
tick
both dlogicrst 1
fall
tick
both dlogicrst 0
puts "DPHY_SETTLED_SIM_PASS checks=$count; stopped clocks, short clear, independent lanes, 16 release offsets, warm reset"
quit
}
close $checks
set bin [file join $::env(XILINX_VIVADO) bin]
exec [file join $bin xvhdl.bat] [file join $ip_dir DPHY_Pkg.vhd] [file join $ip_dir SyncAsync.vhd] [file join $ip_dir SyncAsyncReset.vhd] [file join $ip_dir HS_Deserializer.vhd] [file join $root sim tb_dphy_settled.vhd] > compile.log 2>@1
exec [file join $bin xelab.bat] tb_dphy_settled -debug typical -s dphy_settled -L unisim > elaborate.log 2>@1
exec [file join $bin xsim.bat] dphy_settled -tclbatch settled_checks.tcl > simulation.log 2>@1
set sim_log [open simulation.log r]
set sim_text [read $sim_log]
close $sim_log
if {![regexp -line {^DPHY_SETTLED_SIM_PASS checks=([0-9]+);[^\r\n]*} $sim_text sim_result sim_count] || $sim_count != 210 || [string match {*ERROR:*} $sim_text]} {
    error "Settled simulation failed; inspect $build_dir/simulation.log"
}
puts $sim_result
set sim_report [open [file join $report_dir dphy_settled_simulation.txt] w]
puts $sim_report $sim_result
puts $sim_report "Canonical HS_Deserializer/ResetBridge; behavioral checks only. No analog metastability, complete lane FSM/LP/SoT/first-payload or board acceptance."
close $sim_report
if {$argc == 1} { exit }

# Match the current production XCI parameters; synthesize the existing D-PHY
# top directly. Boundary CSI enable launch flops are outside this OOC check.
foreach name {DPHY_Pkg SyncAsync SyncAsyncReset DebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver} {
    read_vhdl [file join $ip_dir $name.vhd]
}
synth_design -mode out_of_context -flatten_hierarchy none -top MIPI_DPHY_Receiver -part xc7z020clg400-2 -generic {kNoOfDataLanes=2 kGenerateMMCM=false kGenerateAXIL=true kDebug=false kLPFromLane0=false kRefClkFreqHz=200000000}
create_clock -name ref_clk -period 5.000 [get_ports RefClk]
create_clock -name axi_clk -period 10.000 [get_ports s_axi_lite_aclk]
create_clock -name mipi_hs_clk -period 3.571 [get_ports dphy_clk_hs_p]
# Keep the canonical input delays and existing CDC constraints unchanged.
read_xdc [file join $ip_dir MIPI_DPHY_Receiver_clocks.xdc]
read_xdc [file join $ip_dir MIPI_DPHY_Receiver.xdc]
set cdc [report_cdc -details -return_string -file [file join $report_dir dphy_settled_cdc.rpt]]
foreach lane {0 1} {
    set pattern [format {CDC-9\s+Info\s+Asynchronous reset synchronized with ASYNC_REG property\s+2\s+[^\n]*DataLaneGen\[%d\][^\n]*cHSSettled_reg/C[^\n]*DataLaneGen\[%d\][^\n]*SyncAsyncSettled/SyncAsyncx/oSyncStages_reg\[0\]/CLR} $lane $lane]
    if {[regexp -all $pattern $cdc] != 1} { error "Lane $lane settled crossing was not reported once as CDC-9 Info, depth 2" }
}
if {[regexp {CDC-7[^\n]*cHSSettled_reg/C} $cdc]} { error "cHSSettled CDC-7 remains" }
puts "DPHY_SETTLED_CDC_PASS: both cHSSettled crossings CDC-9, depth 2; no timing or whole-project signoff"
close_design
