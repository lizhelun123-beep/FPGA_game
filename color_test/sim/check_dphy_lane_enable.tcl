# XSim checks on the integration harness's canonical RTL. Only readiness fault
# injection uses an internal force; launch flops, gates and chains are observed.
set top /dphy_lane_enable_harness
set checks 0
if {![info exists ppi_shared]} { set ppi_shared 1 }
proc drive {name bit} {
    global top
    # XSim's immediate constant force can change the displayed VHDL value
    # without a usable 'event/Rising_Edge. Schedule changes in simulator time.
    set old [value $name]
    if {$old eq $bit} {
        add_force $top/$name $bit -radix bin
    } else {
        add_force $top/$name [list $old 0ps] [list $bit 1ps] -radix bin
    }
}
proc value {name} { global top; return [get_value -radix bin $top/$name] }
proc check {name expected} {
    global checks
    set actual [value $name]
    if {$actual ne $expected} {
        catch { hs_trace "FAIL_$name" }
        error "$name expected $expected got $actual at [current_time]"
    }
    incr checks
}
set lanes [list phy/ClockLane {phy/\DataLaneGen(0)\/DPHY_LaneSFEN_X} {phy/\DataLaneGen(1)\/DPHY_LaneSFEN_X}]
proc enabled {expected} {
    global lanes
    foreach lane $lanes {
        check $lane/cEnable $expected
        check $lane/cIntRst [expr {1 - $expected}]
    }
}
proc gate {expected} {
    check phy/aLaneSCNNEnable $expected
    check phy/aLaneSFENEnable [string repeat $expected 2]
}
proc tick {} {
    global top lanes ppi_shared
    set chains [list phy/SyncPPIClkEnable]
    if {!$ppi_shared} {
        foreach lane [lrange $lanes 1 end] {
            lappend chains [string map {DPHY_LaneSFEN_X {\IndependentPPIEnable\/SyncPPIDataEnable}} $lane]
        }
    }
    lappend chains phy/YesAXILITE/SyncAsyncClkEnable
    foreach lane $lanes { lappend chains $lane/SyncAsyncEnable }
    set expected {}
    foreach chain $chains {
        lappend expected "[string index [value $chain/oSyncStages] 1][value $chain/aIn]"
    }
    add_force $top/RefClk {0 0ps} {1 2499ps}
    run 2.5 ns
    check RefClk 1
    foreach chain $chains bits $expected { check $chain/oSyncStages $bits }
    if {$ppi_shared} {
        # Fan-out is after the shared second FF, never from the foreign sender.
        set shared [value phy/rClkEnable]
        check phy/rDataEnable [string repeat $shared 2]
    }
}
proc fall {} {
    global top
    add_force $top/RefClk {1 0ps} {0 2499ps}
    run 2.5 ns
    check RefClk 0
}
proc cycles {n} { for {set i 0} {$i < $n} {incr i} { tick; fall } }
proc clock_run {name period half} {
    global top
    add_force $top/$name {0 0ns} [list 1 ${half}ns] -repeat_every ${period}ns
}
proc hs_run {} {
    global top
    clock_run dphy_clk_hs_p 3.571 1.7855
    add_force $top/dphy_clk_hs_n {1 0ns} {0 1.7855ns} -repeat_every 3.571ns
}
proc clock_activity {expected} {
    # Observe the actual BUFIO/BUFR outputs, never drive a derived clock.
    set previous [list [value serial_clk] [value byte_clk]]
    set changes {0 0}
    for {set i 0} {$i < 32} {incr i} {
        run 1 ns
        set now [list [value serial_clk] [value byte_clk]]
        for {set j 0} {$j < 2} {incr j} {
            if {[lindex $previous $j] ne [lindex $now $j]} {
                lset changes $j [expr {[lindex $changes $j] + 1}]
            }
        }
        set previous $now
    }
    global checks
    foreach count $changes name {serial_clk byte_clk} {
        if {($count > 0) != $expected} {
            error "$name activity=$count expected moving=$expected at [current_time]"
        }
        incr checks
    }
}
proc enter_hs {{manual 1}} {
    # The original PPI edge-count tests need the manual exit. Real recovery
    # tests already have a continuous RefClk; never rephase/pause it here.
    if {$manual} { clock_run RefClk 5 2.5 }
    drive dphy_clk_lp_p 1
    drive dphy_clk_lp_n 1
    run 200 ns
    check phy/ClockLane/aLP 11
    drive dphy_clk_lp_p 0
    run 100 ns
    check phy/ClockLane/aLP 01
    drive dphy_clk_lp_n 0
    run 500 ns
    check phy/ClockLane/aLP 00
    check clk_active 1
    clock_activity 1
    if {$manual} {
        drive RefClk 0
        run 0.002 ns
    }
}
proc video_enable {bit} {
    drive vEnable $bit
    run 20 ns
    check ppi_enable [string repeat $bit 3]
}
proc ppi_transition {bit} {
    set old [expr {1 - $bit}]
    video_enable $bit
    # Four RefClk edges from the canonical CSI sender, not a driven PPI port.
    for {set edge 1} {$edge <= 4} {incr edge} {
        tick
        enabled [expr {$edge < 4 ? $old : $bit}]
        gate [expr {$edge < 2 ? $old : $bit}]
        fall
    }
}
proc axi_write {word} {
    drive awaddr 0000
    # These control writes use only reset/enable bits 0/1. XSim Tcl lacks %b.
    drive wdata [string repeat 0 30][expr {($word >> 1) & 1}][expr {$word & 1}]
    drive awvalid 1
    drive wvalid 1
    run 40 ns
    drive awvalid 0
    drive wvalid 0
    run 20 ns
}
proc software_transition {bit} {
    set old [expr {1 - $bit}]
    axi_write [expr {$bit * 2}]
    check phy/xEnable $bit
    for {set edge 1} {$edge <= 4} {incr edge} {
        tick
        check phy/rSoftEnable [expr {$edge < 2 ? $old : $bit}]
        gate [expr {$edge < 2 ? $old : $bit}]
        enabled [expr {$edge < 4 ? $old : $bit}]
        fall
    }
}

# HS-lock acceptance observes the real BUFR source, the shared bridge, the
# retained clock-lane history and both real data-lane reset receivers.
set hs_bridge phy/ClockLane/RxClkActiveHSResetBridge/SyncAsyncx
proc hs_receivers {rst} {
    global lanes
    check phy/cRxClkActiveHS_int [expr {1 - $rst}]
    foreach lane [lrange $lanes 1 end] {
        check $lane/cHSClkRst $rst
        if {$rst} {
            check $lane/cHSReset 1
            check $lane/cHSSettled 0
            check $lane/SyncAsyncValid/oSyncStages 00
            check $lane/HSDeserializerX/SyncAsyncSettled/SyncAsyncx/oSyncStages 00
            check $lane/HSDeserializerX/SerdesReset/SyncAsyncx/oSyncStages 11
            check $lane/HSDeserializerX/dLogicRst 1
        }
    }
}
proc hs_clear {} {
    global hs_bridge
    check clk_active 0
    check phy/ClockLane/HSClockingX/SyncAsyncLocked/oSyncStages 00
    check $hs_bridge/oSyncStages 00
    hs_receivers 1
}
proc hs_trace {label} {
    global hs_bridge lanes
    set c phy/ClockLane
    puts "HS_CONTROL $label RefClk=[value RefClk] RDY=[value phy/rDlyLckd] soft_enable=[value phy/rSoftEnable] core_reset=[value phy/rIntRst] PPI=[value ppi_enable]"
    puts "HS_TRACE $label t=[current_time] raw=[value $c/HSClockingX/SyncAsyncLocked/oSyncStages] shared=[value $hs_bridge/oSyncStages] history=[value $c/SyncAsyncLocked/oSyncStages] q=[value $c/cHSClkLocked_q] rst=[value $c/cHSRst] lost=[value $c/cHSClkLost] state=[value $c/state] next=[value $c/nstate] byte=[value byte_clk]"
    foreach lane [lrange $lanes 1 end] {
        puts "HS_LANE $lane reset=[value $lane/cHSReset] settled=[value $lane/cHSSettled] valid=[value $lane/dValid] valid_sync=[value $lane/SyncAsyncValid/oSyncStages] serdes=[value $lane/HSDeserializerX/SerdesReset/SyncAsyncx/oSyncStages] settled_sync=[value $lane/HSDeserializerX/SyncAsyncSettled/SyncAsyncx/oSyncStages] state=[value $lane/state]"
        puts "HS_LANE_INPUT $lane enable=[value $lane/cEnable] clock_reset=[value $lane/cHSClkRst] LP_raw=[value $lane/aLP] LP_serdes_O=[value $lane/aLP_int] LP_sync=[value $lane/cLPGlitch] LP_filtered=[value $lane/cLP] next=[value $lane/nstate] init_timeout=[value $lane/cInitTout] counter=[value $lane/cDelayCnt]"
    }
}
proc data_lp_check {bits state} {
    global lanes
    foreach lane [lrange $lanes 1 end] {
        check $lane/cEnable 1
        check $lane/cHSClkRst 0
        check $lane/cLP $bits
        check $lane/state $state
    }
}
proc hs_tick {{raw_stable 1}} {
    global hs_bridge
    # Used with the byte source stable. Check BOTH FFs, not just final status.
    set raw [value clk_active]
    set shared [value $hs_bridge/oSyncStages]
    set history [value phy/ClockLane/SyncAsyncLocked/oSyncStages]
    set local_rst [value phy/ClockLane/cHSRst]
    tick
    if {$raw_stable} { check clk_active $raw }
    if {$raw && [value clk_active]} { set shared_next "[string index $shared 1]1" } else { set shared_next 00 }
    if {$local_rst || [value phy/ClockLane/cHSRst]} { set history_next 00 } else { set history_next "[string index $history 1][string index $shared 0]" }
    check $hs_bridge/oSyncStages $shared_next
    check phy/ClockLane/SyncAsyncLocked/oSyncStages $history_next
    check phy/ClockLane/cHSClkLocked_q [string index $history 0]
    check phy/ClockLane/cHSClkLost [expr {[string index $history 0] && ![string index $history_next 0]}]
    hs_receivers [expr {1 - [value phy/cRxClkActiveHS_int]}]
    fall
}
proc hs_manual_restart {delay {exit_preload 0}} {
    global hs_bridge
    # Actual clock-lane LP FSM and BUFR reset. Stop HS until RefClk has
    # removed BUFR CLR, then obtain raw lock from exactly two real byte edges.
    drive dphy_clk_hs_p 0
    drive dphy_clk_hs_n 1
    clock_run RefClk 5 2.5
    drive dphy_clk_lp_p 1
    drive dphy_clk_lp_n 1
    run 100 ns
    hs_clear
    drive dphy_clk_lp_p 0
    run 100 ns
    drive dphy_clk_lp_n 0
    run 500 ns
    check phy/ClockLane/cHSRst 0
    check phy/ClockLane/HSClockingX/cBUFR_Rst 0
    drive RefClk 0
    run 0.002 ns
    hs_clear
    if {$exit_preload} {
        # Queue a REAL LP exit before starting the byte clock. With 4..7
        # RefClk edges preloaded, raw lock is reachable briefly, but the
        # existing local FSM reset can preempt the four-edge status rise.
        drive dphy_clk_lp_p 1
        drive dphy_clk_lp_n 1
        run 0.002 ns
        for {set i 0} {$i < $exit_preload} {incr i} { hs_tick }
        check phy/ClockLane/cHSRst 0
    }
    hs_run
    # Poll only the real BUFR output. No lock/FF/reset/derived-clock forces.
    set old 0
    set edges 0
    for {set i 0} {$i < 100} {incr i} {
        run 0.5 ns
        set now [value byte_clk]
        if {$now eq "1" && $old eq "0"} { incr edges }
        set old $now
        set bits [lindex {00 01 11} $edges]
        check phy/ClockLane/HSClockingX/SyncAsyncLocked/oSyncStages $bits
        if {$edges == 2} { break }
    }
    if {$edges != 2} { error "No two real BUFR rising edges" }
    check clk_active 1
    # RefClk stopped: raw lock alone cannot release either data reset.
    check $hs_bridge/oSyncStages 00
    hs_receivers 1
    run $delay ns
    if {$exit_preload} {
        set high_edges 0
        set seen_status 0
        for {set i 1} {$i <= 10} {incr i} {
            if {[value clk_active]} { incr high_edges }
            hs_tick 0
            if {[value phy/ClockLane/cHSClkLocked]} { set seen_status 1 }
            hs_trace "short_preload${exit_preload}_edge$i"
            if {![value clk_active]} { break }
        }
        hs_clear
        check phy/ClockLane/cHSRst 1
        check phy/ClockLane/SyncAsyncLocked/oSyncStages 00
        if {$high_edges < 1 || $high_edges > 5 || $seen_status} {
            error "Short-lock boundary changed: captures=$high_edges status_seen=$seen_status"
        }
        puts "HS_SCENARIO_PASS short_lock preload=$exit_preload raw_high_capture_edges=$high_edges local_reset_preempts_status=1"
        return
    }
    for {set i 1} {$i <= 4} {incr i} {
        hs_tick
        check phy/cRxClkActiveHS_int [expr {$i >= 2}]
        check phy/ClockLane/cHSClkLocked [expr {$i >= 4}]
        check phy/ClockLane/cHSRst 0
        check phy/ClockLane/cHSClkLost 0
        hs_trace "relock_delay${delay}_edge$i"
    }
    puts "HS_SCENARIO_PASS relock delay=$delay raw_two_BUFR_edges=1 data_release_edges=2 clock_status_edges=4"
}
proc stop_byte_at {level} {
    # Freeze the differential source at its CURRENT phase, only after the
    # actual BUFR output reaches the requested level. No added input edge.
    for {set i 0} {$i < 200} {incr i} {
        run 0.1 ns
        if {[value byte_clk] eq $level} { break }
    }
    check byte_clk $level
    set source [value dphy_clk_hs_p]
    drive dphy_clk_hs_p $source
    drive dphy_clk_hs_n [expr {1 - $source}]
    run 100 ns
    check byte_clk $level
    clock_activity 0
    check byte_clk $level
    puts "HS_SCENARIO_PASS real_BUFR_stopped level=$level held_source=$source"
}

drive RefClk 0
clock_run s_axi_lite_aclk 10 5
clock_run video_aclk 6.667 3.3335
hs_run
drive dphy_clk_lp_p 1
drive dphy_clk_lp_n 1
drive dphy_data_lp_p 11
drive dphy_data_lp_n 11
drive dphy_data_hs_p 00
drive dphy_data_hs_n 11
drive video_aresetn 0
drive vEnable 0
drive aRst 1
drive s_axi_lite_aresetn 0
drive awvalid 0
drive wvalid 0
drive bready 1
drive awaddr 0000
drive wdata 0
clock_run RefClk 5 2.5
run 200 ns
enabled 0
set hs_startup_checks $checks
hs_clear
set hs_startup_checks [expr {$checks - $hs_startup_checks}]
drive s_axi_lite_aresetn 1
drive video_aresetn 1
drive aRst 0
run 5000 ns
check phy/rDlyLckd 1
check phy/rSoftEnable 1
enabled 0
# Manual edge-count checks intentionally pause RefClk between transactions.
# UNISIM correctly drops RDY on those pauses; hold it only during these
# isolated digital-control checks, then release for real reset acceptance.
drive phy/rDlyLckd 1
drive RefClk 0
run 0.002 ns

ppi_transition 1
ppi_transition 0
ppi_transition 1
software_transition 0
software_transition 1

# Real IDELAYCTRL startup above; inject RDY loss/reacquisition independently
# of software enable. Local gating retains the original two-edge latency.
drive phy/rDlyLckd 0
run 0.002 ns
gate 0
tick; enabled 1; fall
tick; enabled 0; fall
drive phy/rDlyLckd 1
run 0.002 ns
gate 1
tick; enabled 0; fall
tick; enabled 1; fall

# Pending CSI enable while not ready, then enable while software is disabled.
ppi_transition 0
drive phy/rDlyLckd 0
video_enable 1
cycles 4
gate 0
enabled 0
drive phy/rDlyLckd 1
run 0.002 ns
cycles 2
enabled 1
software_transition 0
drive phy/rDlyLckd 0
run 0.002 ns
cycles 2
enabled 0
drive phy/rDlyLckd 1
run 0.002 ns
cycles 2
gate 0
enabled 0
video_enable 0
cycles 4
axi_write 2
cycles 4
check phy/rSoftEnable 1
enabled 0
ppi_transition 1

# Pulses entirely between RefClk edges are not queued; a pulse captured by
# stage 1 propagates through all four stages. No new pulse-stretching policy.
video_enable 0
video_enable 1
cycles 4
enabled 1
video_enable 0
tick; enabled 1; fall
video_enable 1
tick; enabled 1; fall
tick; enabled 1; fall
tick; enabled 0; fall
tick; enabled 1; fall

# Stopped video clock holds the actual CSI register despite input changes.
drive video_aclk 0
drive vEnable 0
run 30 ns
check ppi_enable 111
cycles 5
enabled 1
clock_run video_aclk 6.667 3.3335
run 20 ns
check ppi_enable 000
cycles 4
enabled 0
ppi_transition 1

# RefClk stopped low/high: no control update until it resumes. RDY is held
# for this isolation check, so this is not an IDELAY clock-loss recovery test.
foreach level {0 1} {
    drive RefClk $level
    run 0.002 ns
    video_enable 0
    run 50 ns
    enabled 1
    drive RefClk 0
    run 0.002 ns
    cycles 4
    enabled 0
    ppi_transition 1
}

# HS and real BUFR byte clock run, stop low/high and restart independently
# of the RefClk control plane. Enter clock-lane HS via its actual LP inputs.
enter_hs
foreach level {0 1} {
    drive dphy_clk_hs_p $level
    drive dphy_clk_hs_n [expr {1 - $level}]
    run 100 ns
    clock_activity 0
    ppi_transition 0
    ppi_transition 1
    hs_run
    enter_hs
    enabled 1
}

# Keep HS running while disable/reset stops the real BUFR byte clock.
ppi_transition 0
cycles 4
check clk_active 0
set held [value byte_clk]
run 32 ns
check byte_clk $held
ppi_transition 1
enter_hs

# Video reset disables through the real registered PPI path (four edges).
drive video_aresetn 0
run 20 ns
check ppi_enable 000
cycles 3
enabled 1
cycles 1
enabled 0
drive video_aresetn 1
run 20 ns
cycles 4
enabled 1

# External reset while RefClk is stopped retains the existing bridge and
# synchronous IDELAYCTRL reset behavior. Remove RDY injection for real reset.
remove_forces $top/phy/rDlyLckd
drive aRst 1
run 20 ns
check phy/rIntRst 1
enabled 1
cycles 5
check phy/rDlyLckd 0
enabled 0
drive aRst 0
clock_run RefClk 5 2.5
run 5000 ns
check phy/rDlyLckd 1
enabled 1

# With injection removed, real IDELAYCTRL RDY drops on missing RefClk.
# Reacquire through an explicit external reset; this tests the vendor digital
# model, not analog calibration or an automatic recovery policy.
foreach level {0 1} {
    drive RefClk $level
    run 100 ns
    check phy/rDlyLckd 0
    gate 0
    cycles 2
    enabled 0
    drive aRst 1
    clock_run RefClk 5 2.5
    run 200 ns
    check phy/rDlyLckd 0
    drive aRst 0
    run 5000 ns
    check phy/rDlyLckd 1
    enabled 1
}

# D-PHY software reset uses the actual AXI register and existing reset bridge.
axi_write 3
run 100 ns
check phy/rSoftRst 1
check phy/rDlyLckd 0
enabled 0
axi_write 2
run 5000 ns
check phy/rDlyLckd 1
enabled 1
# Keep the original PPI regression count independently visible.
set ppi_checks [expr {$checks - $hs_startup_checks}]
if {$ppi_checks != 1959} { error "Original PPI regression count changed: $ppi_checks" }
puts "DPHY_PPI_REGRESSION_PASS checks=$ppi_checks"

# Manual HS edge-count tests isolate RDY as in the PPI tests above. Remove
# this injection before entering the continuously clocked real-reset tests.
set hs_start $checks
drive phy/rDlyLckd 1
run 0.002 ns
foreach delay {0.2 1.4 2.6 4.8} { hs_manual_restart $delay }
foreach preload {4 5 6 7} { hs_manual_restart 0.2 $preload }
remove_forces $top/phy/rDlyLckd
clock_run RefClk 5 2.5
drive dphy_data_lp_p 11
drive dphy_data_lp_n 11
# After removing the injection, do not assume RDY must remain low once
# continuous RefClk resumes. Establish a known state through real reset.
drive aRst 1
run 200 ns
check phy/rDlyLckd 0
hs_clear
drive aRst 0
run 5000 ns
check phy/rDlyLckd 1
hs_trace after_real_reset
enter_hs 0
check phy/rDlyLckd 1
hs_receivers 0
run 110000 ns
hs_trace before_data_HS_entry
data_lp_check 11 stStop
drive dphy_data_lp_p 00
run 100 ns
data_lp_check 01 stHS_Rqst
drive dphy_data_lp_n 00
run 500 ns
data_lp_check 00 stHS_Rcv
foreach lane [lrange $lanes 1 end] {
    check $lane/cHSReset 0
    check $lane/cHSSettled 1
    check $lane/HSDeserializerX/dSettled 1
    check $lane/HSDeserializerX/SerdesReset/SyncAsyncx/oSyncStages 00
    check $lane/HSDeserializerX/SyncAsyncSettled/SyncAsyncx/oSyncStages 11
    check $lane/SyncAsyncValid/oSyncStages 00
    check $lane/dValid 0
}
hs_trace running
puts "HS_SCENARIO_PASS real_reset_recovery_and_data_settle"

# Independent lane LP/FSM resets remain local despite sharing clock activity.
foreach pair {{01 0 1} {10 1 0}} {
    lassign $pair bits stopped running
    drive dphy_data_lp_p $bits
    drive dphy_data_lp_n $bits
    run 200 ns
    check [lindex $lanes [expr {$stopped + 1}]]/cHSReset 1
    check [lindex $lanes [expr {$stopped + 1}]]/cHSSettled 0
    check [lindex $lanes [expr {$running + 1}]]/cHSReset 0
    check [lindex $lanes [expr {$running + 1}]]/cHSSettled 1
    hs_receivers 0
    hs_trace "local_LP_reset_lane$stopped"
    puts "HS_SCENARIO_PASS local_LP_reset lane=$stopped other_lane_running=$running"
    drive dphy_data_lp_p 00
    run 100 ns
    drive dphy_data_lp_n 00
    run 500 ns
}

# With no MMCM there is no independent clock-loss detector. Actual BUFR stopped
# low or high freezes activity; it does not invent a reset. RefClk loss alone
# also holds the bridge. Observe this explicitly before requesting real reset.
foreach level {0 1} {
    stop_byte_at $level
    check clk_active 1
    hs_receivers 0
    foreach reflevel {0 1} {
        drive RefClk $reflevel
        run 100 ns
        check clk_active 1
        check byte_clk $level
        hs_receivers 0
    }
    # External assertion reaches rIntRst asynchronously, but RDY/enable/FSM
    # still need RefClk. Check the stopped condition and every restart edge.
    drive aRst 1
    run 20 ns
    check phy/rIntRst 1
    check clk_active 1
    hs_receivers 0
    drive RefClk 0
    run 0.002 ns
    for {set i 0} {$i < 12 && [value clk_active] ne "0"} {incr i} {
        hs_tick 0
        # A loss at this RefClk edge must assert the shared reset without
        # any subsequent RefClk OR byte edge, including with BUFR stopped.
        if {[value clk_active] eq "0"} { hs_clear }
        hs_trace "stopped${level}_reset_edge$i"
    }
    hs_clear
    puts "HS_SCENARIO_PASS actual_raw_loss BUFR_was_stopped=$level shared_async_clear=1"
    clock_activity 0
    drive RefClk 1
    run 100 ns
    hs_clear
    drive RefClk 0
    run 100 ns
    hs_clear
    clock_run RefClk 5 2.5
    run 200 ns
    drive aRst 0
    run 5000 ns
    hs_run
    enter_hs 0
    check phy/rDlyLckd 1
    run 110000 ns
    drive dphy_data_lp_p 11
    drive dphy_data_lp_n 11
    run 200 ns
    data_lp_check 11 stStop
    drive dphy_data_lp_p 00
    run 100 ns
    data_lp_check 01 stHS_Rqst
    drive dphy_data_lp_n 00
    run 500 ns
    data_lp_check 00 stHS_Rcv
    foreach lane [lrange $lanes 1 end] {
        check $lane/cHSReset 0
        check $lane/cHSSettled 1
    }
    puts "HS_SCENARIO_PASS stopped_BUFR_restart level=$level"
}

# Software reset and PPI disable stop the real BUFR while BUFIO/HS continues.
foreach action {software ppi} {
    data_lp_check 00 stHS_Rcv
    if {$action eq "software"} { axi_write 3 } else { video_enable 0 }
    run 200 ns
    enabled 0
    hs_clear
    set held [value byte_clk]
    run 32 ns
    check byte_clk $held
    set serial_before [value serial_clk]
    run 1.7855 ns
    check serial_clk [expr {1 - $serial_before}]
    if {$action eq "software"} { axi_write 2 } else { video_enable 1 }
    run 5000 ns
    enter_hs 0
    check phy/rDlyLckd 1
    enabled 1
    hs_receivers 0
    # A recovered shared lock does not by itself prove lane initialization
    # and LP/FSM receive recovery. Exercise the real 100 us init contract.
    drive dphy_data_lp_p 11
    drive dphy_data_lp_n 11
    run 110000 ns
    data_lp_check 11 stStop
    drive dphy_data_lp_p 00
    run 100 ns
    data_lp_check 01 stHS_Rqst
    drive dphy_data_lp_n 00
    run 500 ns
    data_lp_check 00 stHS_Rcv
    foreach lane [lrange $lanes 1 end] {
        check $lane/cHSReset 0
        check $lane/cHSSettled 1
        check $lane/HSDeserializerX/SerdesReset/SyncAsyncx/oSyncStages 00
        check $lane/HSDeserializerX/SyncAsyncSettled/SyncAsyncx/oSyncStages 11
        check $lane/HSDeserializerX/dLogicRst 0
        check $lane/SyncAsyncValid/oSyncStages 00
        check $lane/dValid 0
    }
    hs_trace "${action}_reset_recovered"
    puts "HS_SCENARIO_PASS ${action}_reset_and_relock full_data_recovery=1"
}
puts "DPHY_HS_LOCK_SIM_PASS checks=[expr {$checks - $hs_start}]; real BUFR source/clock and three RefClk branches; no HS-lock fault injection"
puts "DPHY_LANE_ENABLE_SIM_PASS checks=$checks; canonical CSI + DPHY; PPI/software/RDY/reset and HS-lock/real BUFR stop/restart"
quit
