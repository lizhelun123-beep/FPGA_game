# Bounded canonical CSI -> D-PHY integration. No production project changes,
# implementation, bitstream or board access. Optional sim/sim-reuse/cdc/audit;
# audit reopens only this harness's saved synthesized DCP, without synthesis.
if {$argc > 1} { error "Expected sim, sim-reuse, cdc, audit, or no argument" }
set mode [expr {$argc ? [lindex $argv 0] : "all"}]
if {$mode ni {all sim sim-reuse cdc audit}} { error "Expected sim, sim-reuse, cdc, audit, or no argument" }
set root [file normalize [file join [file dirname [info script]] ..]]
set dphy_dir [file join $root repo ip MIPI_D_PHY_RX hdl]
set csi_dir [file join $root repo ip MIPI_CSI_2_RX hdl]
set build_dir [file join $root build dphy_lane_enable]
set report_dir [file join $root reports]
file mkdir $build_dir
file mkdir $report_dir
cd $build_dir
set dphy_names {DPHY_Pkg SyncAsync SyncAsyncReset DebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver}
set csi_names {DebugLib SyncAsync SyncAsyncReset SimpleFIFO ECC CRC16_behavioral LM LLP MIPI_CSI2_Rx}
set harness [file join $root sim dphy_lane_enable_harness.vhd]

if {$mode in {all sim sim-reuse}} {
    set bin [file join $::env(XILINX_VIVADO) bin]
    set csi_files [list [file join $root repo ip MIPI_CSI_2_RX tb fifo_models.vhd]]
    foreach name $csi_names { lappend csi_files [file join $csi_dir $name.vhd] }
    set dphy_files {}
    foreach name $dphy_names { lappend dphy_files [file join $dphy_dir $name.vhd] }
    # Refuse a stale replay; Tcl-only assertion changes need no RTL rebuild.
    set signature [list dphy_lane_enable -debug all -L unisim -L csi -L dphy $::env(XILINX_VIVADO)]
    foreach src [concat $csi_files $dphy_files [list $harness]] {
        lappend signature $src [file size $src] [file mtime $src]
    }
    if {$mode eq "sim-reuse"} {
        set f [open snapshot_signature.txt r]; set saved [string trim [read $f]]; close $f
        if {$saved ne $signature} { error "RTL/config changed: rebuild with sim" }
    } else {
        exec [file join $bin xvhdl.bat] --2008 --work csi {*}$csi_files > csi_compile.log 2>@1
        exec [file join $bin xvhdl.bat] --work dphy {*}$dphy_files > dphy_compile.log 2>@1
        exec [file join $bin xvhdl.bat] --work work $harness > harness_compile.log 2>@1
        exec [file join $bin xelab.bat] work.dphy_lane_enable_harness -debug all -s dphy_lane_enable -L unisim -L csi -L dphy > elaborate.log 2>@1
        set f [open snapshot_signature.txt w]; puts $f $signature; close $f
    }
    set check_script [file join $root sim check_dphy_lane_enable.tcl]
    set f [open $check_script r]; set check_source [read $f]; close $f
    if {![info complete $check_source]} { error "Incomplete simulation Tcl" }
    puts "SIM_SNAPSHOT_SIGNATURE_MATCH: canonical sources, harness, default shared generic and compile configuration"
    set sim_report [file join $report_dir dphy_lane_enable_simulation.txt]
    set f [open $sim_report w]
    puts $f "CANDIDATE_SIM_NOT_ACCEPTED: started; require separate PPI, HS scenario and overall PASS markers. See build/dphy_lane_enable/simulation.log on failure."
    close $f
    set xsim_failed [catch {exec [file join $bin xsim.bat] dphy_lane_enable -tclbatch $check_script > simulation.log 2>@1} xsim_error]
    set f [open simulation.log r]; set sim [read $f]; close $f
    set markers {}
    foreach line [split $sim \n] {
        if {[regexp {^(DPHY_PPI_REGRESSION_PASS|DPHY_HS_LOCK_SIM_PASS|HS_SCENARIO_PASS)} $line]} { lappend markers $line }
    }
    if {$xsim_failed || ![regexp -line {^DPHY_LANE_ENABLE_SIM_PASS checks=([0-9]+);[^\r\n]*} $sim result count] || $count < 300 || [string match {*ERROR:*} $sim]} {
        set f [open $sim_report w]
        puts $f "CANDIDATE_SIM_FAIL: no overall HS-lock acceptance; see build/dphy_lane_enable/simulation.log"
        foreach line $markers { puts $f $line }
        foreach line [split $sim \n] {
            if {[regexp {^[^#].* expected .* got .* at } $line]} { puts $f $line }
        }
        if {$xsim_failed} { puts $f "XSim process failed: $xsim_error" }
        close $f
        error "Simulation failed; inspect $build_dir/simulation.log"
    }
    foreach required {{DPHY_PPI_REGRESSION_PASS checks=1959} DPHY_HS_LOCK_SIM_PASS {HS_SCENARIO_PASS relock delay=0.2} {HS_SCENARIO_PASS relock delay=4.8} {HS_SCENARIO_PASS short_lock preload=4} {HS_SCENARIO_PASS short_lock preload=7} {HS_SCENARIO_PASS real_reset_recovery_and_data_settle} {HS_SCENARIO_PASS local_LP_reset lane=0} {HS_SCENARIO_PASS local_LP_reset lane=1} {HS_SCENARIO_PASS real_BUFR_stopped level=0} {HS_SCENARIO_PASS real_BUFR_stopped level=1} {HS_SCENARIO_PASS actual_raw_loss BUFR_was_stopped=0} {HS_SCENARIO_PASS actual_raw_loss BUFR_was_stopped=1} {HS_SCENARIO_PASS stopped_BUFR_restart level=0} {HS_SCENARIO_PASS stopped_BUFR_restart level=1} {HS_SCENARIO_PASS software_reset_and_relock} {HS_SCENARIO_PASS ppi_reset_and_relock}} {
        if {[string first $required [join $markers \n]] < 0} { error "Missing required simulation coverage: $required" }
    }
    puts $result
    set f [open $sim_report w]
    puts $f $result
    foreach line [split $sim \n] {
        if {[regexp {^DPHY_(PPI_REGRESSION|HS_LOCK)_SIM_PASS|^DPHY_PPI_REGRESSION_PASS|^HS_SCENARIO_PASS} $line]} { puts $f $line; puts $line }
    }
    puts $f "Real CSI, BUFIO/BUFR source and three HS-lock receiving branches; RDY fault injection only for manual RefClk isolation, removed for real reset/recovery. No HS-lock/FF/reset/derived-clock injection. No analog, packet/first-payload or hardware signoff."
    close $f
}
if {$mode in {sim sim-reuse}} { exit }

if {$mode eq "audit"} {
    open_checkpoint [file join $build_dir lane_enable_synth.dcp]
} else {
    foreach name $csi_names { read_vhdl -vhdl2008 -library csi [file join $csi_dir $name.vhd] }
    foreach name $dphy_names { read_vhdl -library dphy [file join $dphy_dir $name.vhd] }
    read_vhdl $harness
    # Match production's ordinary rebuilt hierarchy/identical-register merging.
    # Retain the actual CSI sender; do not substitute a test register or read
    # simulation FIFO models. This does not sign off the unrelated CSI FIFO IP.
    synth_design -mode out_of_context -flatten_hierarchy rebuilt -top dphy_lane_enable_harness -part xc7z020clg400-2
    create_clock -name clk_fpga_0 -period 10.000 [get_ports s_axi_lite_aclk]
    create_clock -name clk_fpga_1 -period 6.667 [get_ports video_aclk]
    create_clock -name clk_fpga_2 -period 5.000 [get_ports RefClk]
    create_clock -name mipi_hs_clk -period 3.571 [get_ports dphy_clk_hs_p]
    read_xdc [file join $dphy_dir MIPI_DPHY_Receiver_clocks.xdc]
    read_xdc [file join $dphy_dir MIPI_DPHY_Receiver.xdc]
    read_xdc [file join $csi_dir mipi_csi2_rx.xdc]
    write_checkpoint -force [file join $build_dir lane_enable_synth.dcp]
}
set cdc [report_cdc -details -return_string -file [file join $report_dir dphy_lane_enable_cdc.rpt]]

# Shared-mode acceptance requires ONE CDC chain, followed by real RefClk fan-out.
# Counts alone are insufficient: trace sender loads, both FFs, gates and sinks.
set audit [open [file join $report_dir dphy_lane_enable_structure.txt] w]
set firsts [get_cells -hier -regexp {phy/.*SyncPPI.*oSyncStages_reg\[0\]}]
if {[llength $firsts] != 1} { error "Shared PPI mode must have exactly one crossing, got $firsts" }
foreach first $firsts {
    set dpin [get_pins $first/D]
    set drivers [get_pins -leaf -of_objects [get_nets -of_objects $dpin] -filter {DIRECTION == OUT}]
    if {[llength $drivers] != 1 || ![regexp {^csi_rx/a(D|Clk)EnableInt_reg.*?/Q$} $drivers]} { error "Not a direct canonical CSI register -> $dpin: $drivers" }
    set sender [get_cells -of_objects $drivers]
    set src_clk [get_clocks -of_objects [get_pins $sender/C]]
    set dst_clk [get_clocks -of_objects [get_pins $first/C]]
    if {$src_clk ne "clk_fpga_1" || $dst_clk ne "clk_fpga_2"} { error "Wrong PPI clocks: $src_clk -> $dst_clk" }
    # Replace only the stage suffix, never a DataLaneGen[0] hierarchy index.
    regsub {\[0\]$} $first {[1]} second
    if {![get_property ASYNC_REG $first] || ![get_property ASYNC_REG [get_cells $second]]} { error "Missing two-stage ASYNC_REG chain" }
    set stage_driver [get_pins -leaf -of_objects [get_nets -of_objects [get_pins $second/D]] -filter {DIRECTION == OUT}]
    if {$stage_driver ne "$first/Q" || [get_clocks -of_objects [get_pins $second/C]] ne "clk_fpga_2"} { error "Broken PPI second stage: $second <- $stage_driver" }
    set launch_sinks [all_fanout -flat -endpoints_only -from $drivers]
    foreach sink $launch_sinks {
        if {[string match phy/* $sink] && $sink ne "$first/D"} { error "Foreign PPI control still fans out inside PHY: $sink" }
    }
    set first_sinks [all_fanout -flat -endpoints_only -from [get_pins $first/Q]]
    if {[llength $first_sinks] != 1 || $first_sinks ne "$second/D"} { error "First PPI stage used outside synchronizer: $first_sinks" }
    set shared_second $second
    puts $audit "CSI $drivers ($src_clk) -> $first -> $second ($dst_clk); no combinational logic before first stage"
    puts $audit "Actual sender endpoints: $launch_sinks; first-stage endpoints: $first_sinks"
}

# Trace actual gates/pipelines to all THREE canonical lane branches, whether
# equivalent registers are retained or merged by production-style synthesis.
set lane_firsts [get_cells -hier -regexp {phy/.*(ClockLane|DPHY_LaneSFEN_X)/SyncAsyncEnable/oSyncStages_reg\[0\]}]
if {[llength $lane_firsts] < 1} { error "Original lane enable pipelines missing" }
set all_sinks {}
foreach cell $lane_firsts {
    set starts [all_fanin -flat -startpoints_only -to [get_pins $cell/D]]
    # all_fanin startpoints for sequential cells are clock pins, not Q pins.
    foreach pattern {{*SyncPPI*oSyncStages_reg[[]1]/C} {*SyncAsyncClkEnable/oSyncStages_reg[[]1]/C} {*IDelayCtrlX/RDY}} {
        if {[lsearch -glob $starts $pattern] < 0} { error "Gate missing $pattern at $cell: $starts" }
    }
    if {[lsearch -exact $starts "$shared_second/C"] < 0} { error "Lane gate is not driven by the shared SECOND stage: $cell" }
    if {[get_clocks -of_objects [get_pins $cell/C]] ne "clk_fpga_2"} { error "Wrong lane chain clock" }
    set gate_pin [get_pins -leaf -of_objects [get_nets -of_objects [get_pins $cell/D]] -filter {DIRECTION == OUT}]
    set gate_cell [get_cells -of_objects $gate_pin]
    if {[llength $gate_cell] != 1 || [get_property REF_NAME $gate_cell] ne "LUT3" || [get_property INIT $gate_cell] ne "8'h80"} { error "Expected actual three-input AND gate at $cell: $gate_cell" }
    puts $audit "Gate $gate_cell LUT3 INIT=[get_property INIT $gate_cell] -> $cell/D"
    regsub {\[0\]$} $cell {[1]} second
    set stage_driver [get_pins -leaf -of_objects [get_nets -of_objects [get_pins $second/D]] -filter {DIRECTION == OUT}]
    if {$stage_driver ne "$cell/Q"} { error "Original lane pipeline depth changed: $cell -> $second" }
    if {![get_property ASYNC_REG $cell] || ![get_property ASYNC_REG [get_cells $second]]} { error "Original lane ASYNC_REG chain changed" }
    set sinks [all_fanout -flat -endpoints_only -from [get_pins $second/Q]]
    lappend all_sinks {*}$sinks
    puts $audit "$cell/D RefClk gate inputs: $starts; second stage $second; sinks $sinks"
}
foreach branch {{phy/ClockLane/*} {phy/DataLaneGen[[]0].DPHY_LaneSFEN_X/*} {phy/DataLaneGen[[]1].DPHY_LaneSFEN_X/*}} {
    if {[lsearch -glob $all_sinks $branch] < 0} { error "Canonical lane branch trimmed: $branch" }
}

# Every source row for the real PPI sender must be Info CDC-3 depth 2; a
# warning/critical reclassification (including CDC-11) is a failure.
set rows 0
set unsafe 0
foreach line [split $cdc \n] {
    if {[regexp {csi_rx/a(D|Clk)EnableInt_reg.*?/C} $line]} {
        if {![regexp {CDC-3\s+Info\s+1-bit synchronized with ASYNC_REG property\s+2} $line]} { incr unsafe }
        incr rows
        puts $audit $line
    }
}
if {$rows != [llength $firsts]} { error "Missing exact PPI CDC rows" }
foreach lane {0 1} {
    set pattern [format {CDC-9\s+Info\s+Asynchronous reset synchronized with ASYNC_REG property\s+2\s+[^\n]*DataLaneGen\[%d\][^\n]*cHSSettled_reg/C[^\n]*DataLaneGen\[%d\][^\n]*SyncAsyncSettled/SyncAsyncx/oSyncStages_reg\[0\]/CLR} $lane $lane]
    if {[regexp -all $pattern $cdc] != 1} { error "Lane $lane cHSSettled depth-2 CDC-9 not preserved" }
    puts $audit "Lane $lane cHSSettled -> SyncAsyncSettled/SyncAsyncx: CDC-9 Info depth 2 preserved"
}
if {$unsafe} {
    puts $audit "DPHY_LANE_ENABLE_CDC_FAIL: $unsafe/$rows PPI crossings are not CDC-3 Info depth 2; all three receiving branches and both cHSSettled depth-2 bridges retained. No waiver or acceptance."
    close $audit
    error "Unsafe PPI CDC ($unsafe/$rows); see dphy_lane_enable_structure.txt"
}
puts $audit "DPHY_LANE_ENABLE_CDC_PASS: three receiving branches preserved, PPI crossings CDC-3 Info depth 2, both cHSSettled CDC-9 Info depth 2. Other CDC/timing not accepted."

# HS-lock: audit the entire actual launch fan-out, including the clock lane.
# Accept a single active-low asynchronous bridge, followed only by local
# RefClk distribution. Ordinary synthesis may merge equivalent logic.
proc hs_one_name {objects description} {
    if {[llength $objects] != 1} { error "Expected one $description, got $objects" }
    # Extract the native object, whose scalar string form is its name. Keep
    # its Vivado type for get_property/-of_objects; a plain NAME string loses
    # that type, while the collection string can add braces to pin paths.
    return [lindex $objects 0]
}
proc hs_cell {name} {
    # Literal hierarchical names include bus/generate brackets and dots.
    regsub -all {[][\\.^$*+?(){}|]} $name {\\&} escaped
    set cells [get_cells -quiet -hier -regexp [format {^%s$} $escaped]]
    return [hs_one_name $cells "HS cell $name"]
}
proc hs_driver {pin} {
    set pins [get_pins -quiet $pin]
    set pin_name [hs_one_name $pins "HS pin $pin"]
    set drivers [get_pins -leaf -of_objects [get_nets -of_objects $pins] -filter {DIRECTION == OUT}]
    return [hs_one_name $drivers "driver for $pin_name"]
}
set raw {phy/ClockLane/HSClockingX/SyncAsyncLocked/oSyncStages_reg[1]}
set bridge {phy/ClockLane/RxClkActiveHSResetBridge/SyncAsyncx}
set raw [hs_cell $raw]
set hs0 [hs_cell $bridge/oSyncStages_reg\[0\]]
set hs1 [hs_cell $bridge/oSyncStages_reg\[1\]]
set shared_firsts [get_cells -hier -regexp {phy/.*RxClkActiveHSResetBridge/SyncAsyncx/oSyncStages_reg\[0\]}]
if {[hs_one_name $shared_firsts "shared HS bridge first stage"] ne $hs0} { error "HS lock must cross exactly once: $shared_firsts" }
foreach cell [list $hs0 $hs1] {
    if {![get_property ASYNC_REG $cell] || [get_property REF_NAME $cell] ne "FDCE" || [get_clocks -of_objects [get_pins $cell/C]] ne "clk_fpga_2"} {
        error "HS bridge must retain two RefClk FDCE ASYNC_REG stages: $cell"
    }
    set clr_starts [all_fanin -flat -startpoints_only -to [get_pins $cell/CLR]]
    if {[hs_one_name $clr_starts "HS async-clear source"] ne "$raw/C"} { error "HS bridge asynchronous clear has other conditions: $clr_starts" }
    # Synthesized FDCE clock inversion is a PIN property; IS_C_INVERTED
    # is not a cell property on this Vivado netlist. Empty is not false.
    set clock_inverted [get_property IS_INVERTED [get_pins $cell/C]]
    if {$clock_inverted ne "0" || [get_property REF_NAME [get_cells -of_objects [hs_driver $cell/CE]]] ne "VCC"} { error "HS bridge clock/enable polarity changed: $cell ($clock_inverted)" }
}
set clear_driver [hs_driver $hs0/CLR]
if {[hs_driver $hs1/CLR] ne $clear_driver} { error "Shared bridge stages have different async clears" }
set inverter [hs_one_name [get_cells -of_objects $clear_driver] "HS async-clear inverter"]
if {[get_property REF_NAME $inverter] ne "LUT1" || [get_property INIT $inverter] ne "2'h1" || [hs_driver $inverter/I0] ne "$raw/Q"} { error "Expected active-low raw lock -> active-high FDCE clear" }
if {[get_property REF_NAME [get_cells -of_objects [hs_driver $hs0/D]]] ne "VCC"} { error "Shared bridge must release by shifting ones" }
set raw_sinks [all_fanout -flat -endpoints_only -from [get_pins $raw/Q]]
set expected_sinks [list $hs0/CLR $hs1/CLR clk_active]
if {[lsort $raw_sinks] ne [lsort $expected_sinks]} { error "Unbridged HS-lock fan-out: $raw_sinks" }
if {[get_clocks -of_objects [get_pins $raw/C]] ne "byte_clk"} { error "HS-lock launch is not the real BUFR domain" }
set raw_clock_driver [hs_driver $raw/C]
if {$raw_clock_driver ne "phy/ClockLane/HSClockingX/DivClkBuffer/O" || [get_property REF_NAME [get_cells -of_objects $raw_clock_driver]] ne "BUFR"} { error "Real BUFR source missing: $raw_clock_driver" }
if {[get_property REF_NAME [get_cells phy/ClockLane/HSClockingX/SerialClkBuffer]] ne "BUFIO"} { error "Real serial BUFIO missing" }
set hs0_sinks [hs_one_name [all_fanout -flat -endpoints_only -from [get_pins $hs0/Q]] "HS first-stage endpoint"]
if {$hs0_sinks ne "$hs1/D"} { error "HS bridge first stage used outside chain: $hs0_sinks" }
set hs1_driver [hs_driver $hs1/D]
if {$hs1_driver ne "$hs0/Q"} { error "Broken HS bridge second stage" }
set local_history [hs_cell {phy/ClockLane/SyncAsyncLocked/oSyncStages_reg[0]}]
set local_second [hs_cell {phy/ClockLane/SyncAsyncLocked/oSyncStages_reg[1]}]
set history_q [hs_cell {phy/ClockLane/cHSClkLocked_q_reg}]
set history_driver [hs_driver $local_history/D]
if {$history_driver ne "$hs1/Q"} { error "Clock lane bypasses shared bridge: $history_driver" }
set local_reset [all_fanin -flat -startpoints_only -to [get_pins $local_history/CLR]]
if {[lsearch -glob $local_reset {*ClockLane/SyncAsyncEnable/oSyncStages_reg[[]1]/C}] < 0 || [lsearch -glob $local_reset {*ClockLane/FSM*}] < 0} { error "Clock-lane local cHSRst conditions lost: $local_reset" }
if {[hs_driver $local_second/D] ne "$local_history/Q" || [hs_driver $history_q/D] ne "$local_second/Q"} { error "Clock-lane two-stage status/falling-edge history lost" }
foreach cell [list $local_history $local_second] {
    if {[get_property REF_NAME $cell] ne "FDCE" || ![get_property ASYNC_REG $cell] || [get_clocks -of_objects [get_pins $cell/C]] ne "clk_fpga_2" || [hs_driver $cell/CLR] ne [hs_driver $local_history/CLR]} { error "Clock-lane local history reset/clock changed: $cell" }
}
set history_sinks [all_fanout -flat -endpoints_only -from [get_pins $local_second/Q]]
set q_sinks [all_fanout -flat -endpoints_only -from [get_pins $history_q/Q]]
if {[lsearch -glob $q_sinks {phy/ClockLane/FSM*}] < 0 || [lsearch -exact $history_sinks "$history_q/D"] < 0} { error "Clock-lane loss detector no longer reaches FSM: $history_sinks / $q_sinks" }
puts $audit "HS raw $raw/Q ([get_clocks -of_objects [get_pins $raw/C]]) driven by $raw_clock_driver; complete endpoints: $raw_sinks"
puts $audit "HS shared $hs0 -> $hs1 (RefClk, FDCE, ASYNC_REG); first endpoints $hs0_sinks"
puts $audit "HS polarity: raw/Q -> $inverter INIT=[get_property INIT $inverter] -> both CLR; stage-0 D and both CE tied high; rising-edge RefClk"
puts $audit "Clock-lane local history $local_history <- $history_driver; preserved cHSRst starts $local_reset"
puts $audit "Clock-lane status $local_history -> $local_second -> $history_q; status endpoints $history_sinks; delayed-status endpoints $q_sinks"
set shared_sinks [all_fanout -flat -endpoints_only -from [get_pins $hs1/Q]]
puts $audit "HS shared second-stage complete endpoints: $shared_sinks"
set expected_shared_sinks [list $local_history/D]
foreach lane {0 1} {
    set base [format {phy/DataLaneGen[%d].DPHY_LaneSFEN_X} $lane]
    foreach suffix {cHSReset_reg/PRE cHSSettled_reg/CLR SyncAsyncValid/oSyncStages_reg[0]/CLR SyncAsyncValid/oSyncStages_reg[1]/CLR} {
        set sink $base/$suffix
        lappend expected_shared_sinks $sink
        if {[lsearch -exact $shared_sinks $sink] < 0} { error "Missing actual lane reset receiver $sink" }
        set starts [all_fanin -flat -startpoints_only -to [get_pins $sink]]
        if {[hs_one_name $starts "lane $lane HS reset source"] ne "$hs1/C"} { error "Lane $lane reset bypasses shared stage 2: $sink <- $starts" }
        puts $audit "HS receiver $sink <- $starts"
    }
    # Per-lane FSM/enable and byte-clock reset/settled paths must still exist.
    set enable_cell [get_cells $base/SyncAsyncEnable/oSyncStages_reg\[1\]]
    if {[llength $enable_cell] != 1} { error "Lane $lane local enable lost" }
    foreach path {SerdesReset SyncAsyncSettled} {
        foreach stage {0 1} {
            set name [format {%s/HSDeserializerX/%s/SyncAsyncx/oSyncStages_reg[%d]} $base $path $stage]
            set cell [hs_cell $name]
            if {![get_property ASYNC_REG $cell] || [get_clocks -of_objects [get_pins $cell/C]] ne "byte_clk"} { error "Lane $lane $path lost two-stage byte-clock bridge" }
        }
    }
    foreach reg {cHSReset cHSSettled} {
        set cell [hs_cell $base/${reg}_reg]
        set starts [all_fanin -flat -startpoints_only -to [get_pins $cell/D]]
        if {[lsearch -glob $starts [format {phy/DataLaneGen[[]%d].DPHY_LaneSFEN_X/FSM*} $lane]] < 0} { error "Lane $lane $reg local FSM conditions lost: $starts" }
        puts $audit "HS local lane $lane $reg synchronous D starts: $starts"
    }
}
if {[lsort $shared_sinks] ne [lsort $expected_shared_sinks]} { error "Unreviewed shared HS-lock receiver: $shared_sinks" }
set hs_rows 0
foreach line [split $cdc \n] {
    if {[string first "$raw/C" $line] >= 0} {
        if {![regexp {CDC-9\s+Info\s+Asynchronous reset synchronized with ASYNC_REG property\s+2} $line] || [string first "$hs0/CLR" $line] < 0} { error "Unsafe HS-lock CDC row: $line" }
        incr hs_rows
        puts $audit $line
    }
    if {[regexp {CDC-[0-9]+\s+Critical} $line]} { error "Critical CDC remains in bounded integration: $line" }
}
if {$hs_rows != 1} { error "Expected one exact HS-lock CDC-9 depth-2 crossing, got $hs_rows" }
puts $audit "DPHY_HS_LOCK_CDC_PASS: complete byte-domain fan-out crosses once as CDC-9 Info depth 2; clock-lane local reset/history and both actual data-lane reset/settled/valid branches retained; no Critical CDC in bounded report. No production timing/datapath signoff."
close $audit
puts "DPHY_LANE_ENABLE_CDC_PASS: see dphy_lane_enable_structure.txt; bounded integration only"
puts "DPHY_HS_LOCK_CDC_PASS: shared async-loss/two-edge-release bridge; all actual receiving branches traced"
close_design
