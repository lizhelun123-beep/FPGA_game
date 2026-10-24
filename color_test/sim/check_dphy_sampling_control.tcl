# Independent controller fault injection on the SAME canonical top and guard.
# Only LOCKED is forced. MMCM/BUFH/ISERDES/LP/CDC/data remain real UNISIM RTL.
# This run is never counted as unforced primitive acceptance.
set top /tb_dphy_sampling_control/fixture
set phy [format {%s/\configs(1)\/dut} $top]
set guard $phy/ClockLane/HSClockingX/candidate
set shared $phy/cRxClkActiveHS_int
set serial [open control_serial.txt w]
set checks [open control_checks.txt w]
set count 0
set waiting_ready 0
set case -1
set UI 1785500

log_wave $top/* $phy/ClockLane/* $guard/*
foreach lane {0 1} {
    set d [format {%s/\DataLaneGen(%d)\/DPHY_LaneSFEN_X} $phy $lane]
    log_wave $d/* $d/HSDeserializerX/*
}
proc now_fs {} {
    if {![regexp {^([0-9.]+) *(fs|ps|ns|us|ms|s)$} [current_time] -> n u]} { error "Unknown time [current_time]" }
    return [expr {wide(round($n * [dict get {fs 1 ps 1000 ns 1000000 us 1000000000 ms 1000000000000 s 1000000000000000} $u]))}]
}
proc advance {fs} { run $fs fs }
proc put_event {kind bits} {
    global serial case
    puts $serial "[now_fs] fs $kind $case $bits"
}
proc drive {name bits} {
    global top
    add_force -radix bin $top/$name $bits
}
proc eq {path expected reason} {
    global count checks
    set got [get_value -radix bin $path]
    if {$got ne $expected} { error "${reason}: expected $expected, got $got at [current_time] ($path)" }
    incr count
    puts $checks "[current_time] PASS $reason"
}
proc blocked {reason} {
    global phy guard shared
    eq $shared 0 "$reason shared ready"
    eq $guard/capture_reset 1 "$reason capture reset"
    foreach lane {0 1} { eq $phy/rbD${lane}RxValidHS 0 "$reason lane$lane valid" }
}
add_condition -radix unsigned -notrace "$shared == 1" {
    if {$waiting_ready} { stop }
}
proc await_ready {} {
    global shared waiting_ready
    set waiting_ready 1
    if {[get_value -radix bin $shared] ne "1"} { run 10 us }
    set waiting_ready 0
    eq $shared 1 "qualified ready arrives"
    put_event READY 00
}
proc lock {bit} {
    global guard
    add_force -radix bin $guard/locked_raw $bit
}
proc fresh_clock {} {
    drive clock_lp 11
    advance 300000000
    drive clock_lp 01
    advance 100000000
    drive clock_lp 00
    advance 3000000000
}
proc entry {id accept} {
    global case
    set case $id
    global top
    add_force -radix dec $top/scenario $id
    put_event [expr {$accept ? "ACCEPT" : "REJECT"}] 00
    drive lp0 11
    drive lp1 11
    drive serial_data 00
    advance 300000000
    drive lp0 01
    drive lp1 01
    advance 100000000
    drive lp0 00
    drive lp1 00
    advance 400000000
}
proc schedule_burst {} {
    global top serial case UI
    set base [now_fs]
    set wave [list add_force -radix bin $top/serial_data]
    set offset 0
    set previous ""
    puts $serial "$base fs SOT $case 00"
    # The adversarial payload includes zero runs and another B8, so a receiver
    # that searches for SoT after becoming ready mid-burst would falsely join.
    for {set i -1} {$i < 44} {incr i} {
        if {$i == -1} { set x 184; set y 184 } elseif {$i >= 32} { set x 255; set y 255 } elseif {$i < 12} { set x 0; set y 0 } elseif {$i == 12} { set x 184; set y 184 } else {
            set x [expr {($i*73+$case*17+37)%256}]
            set y [expr {($i*109+$case*29+83)%256}]
        }
        if {$i == 0} { puts $serial "[expr {$base+$offset}] fs PAYLOAD $case 00" }
        if {$i == 32} { puts $serial "[expr {$base+$offset}] fs TRAIL $case 00" }
        for {set b 0} {$b < 8} {incr b} {
            set bits "[expr {($y>>$b)&1}][expr {($x>>$b)&1}]"
            puts $serial "[expr {$base+$offset}] fs BIT $case $bits"
            if {$bits ne $previous} {
                lappend wave [list $bits ${offset}fs]
                set previous $bits
            }
            incr offset $UI
        }
    }
    {*}$wave
    return $offset
}
proc finish_burst {duration} {
    advance $duration
    drive lp0 11
    drive lp1 11
    put_event EXIT 11
    advance 300000000
}
proc good_burst {id} {
    entry $id 1
    set duration [schedule_burst]
    finish_burst $duration
}

# Keep LOCKED low for a real 100 us RefClk-timed wait. No byte-clock timeout.
lock 0
advance 300000000
drive rst 0
advance 1000000000
fresh_clock
advance 100000000000
blocked delayed_startup
eq $guard/mmcm_reset 0 "no reset loop while awaiting lock"

# First SoT before ready; release during payload, including a later B8.
entry 100 0
set base [now_fs]
set duration [schedule_burst]
advance 50000000
lock 1
await_ready
finish_burst [expr {$base+$duration-[now_fs]}]
good_burst 101

# Re-enter the clock state with a new lock wait before each boundary case.
foreach scenario {coincident late middle} id {110 120 130} {
    lock 0
    advance 1000000
    blocked ${scenario}_loss
    fresh_clock
    if {$scenario eq "late"} {
        set case $id
        add_force -radix dec $top/scenario $id
        lock 1
        await_ready
        good_burst $id
    } else {
        entry $id 0
        if {$scenario eq "coincident"} {
            lock 1
            await_ready
            # First SoT bit is scheduled at the exact shared-ready event.
            put_event COINCIDENT 00
            set duration [schedule_burst]
            finish_burst $duration
        } else {
            set base [now_fs]
            set duration [schedule_burst]
            advance 130000000
            lock 1
            await_ready
            finish_burst [expr {$base+$duration-[now_fs]}]
        }
        good_burst [expr {$id+1}]
    }
}

# A 400 ps lock-loss pulse entirely between RefClk edges must be latched.
set align [expr {(5000000-([now_fs]%5000000))%5000000}]
advance [expr {$align+400000}]
lock 0
advance 400000
lock 1
advance 1000
blocked short_lock_loss_latched
eq $guard/loss_latched 1 "sub-RefClk loss survives raw LOCKED recovery"
advance 10000000
eq $guard/mmcm_reset 1 "short loss requests MMCM reset"
lock 0
fresh_clock
lock 1
await_ready
good_burst 141

# Lose lock during accepted data. Keep both data lanes in LP-00 while the
# clock lane restarts, then present an entire B8/payload without a new entry.
# It must stay blocked until a subsequent, genuinely complete data-lane entry.
entry 150 1
set duration [schedule_burst]
advance 200000000
put_event LOSS 00
lock 0
advance 1000
blocked loss_during_payload
advance 399000
lock 1
advance 10000000
lock 0
fresh_clock
lock 1
await_ready
set case 151
add_force -radix dec $top/scenario 151
put_event REJECT 00
set duration [schedule_burst]
finish_burst $duration
good_burst 152

close $serial
close $checks
puts "DPHY_CONTROL_PASS checks=$count; delayed/early/coincident/late/middle ready, adversarial B8, short loss and complete re-entry"
quit
