# Observation only. No force of any clock, data, reset, ready or internal signal.
set top /tb_dphy_rate93
set raw [open internal.tsv w]
puts $raw "time\tcase\tlane\tstate\tc_reset\tc_settled\td_reset\td_settled\td_logic_reset\traw\talign\thard\tsoft\terr\tvalid\tready\tppi_data\tppi_active\tppi_sync\tppi_error\tppi_soft\tbyte_recent\tbyte_age"
proc sample {} {
    global top raw
    foreach lane {0 1} {
        set d [format {%s/dut/\DataLaneGen(%d)\/DPHY_LaneSFEN_X} $top $lane]
        set s $d/HSDeserializerX
        set values [list [current_time] [get_value -radix dec $top/scenario] $lane]
        foreach path [list $d/state $d/cHSReset $d/cHSSettled $s/dSerdesRst $s/dSettled $s/dLogicRst $s/dDataIn_int $s/dAlignment_int $s/dSyncHard_int $s/dSyncSoft_int $s/dSyncErr_int $d/dValid $top/ready] {
            lappend values [get_value -radix bin $path]
        }
        lappend values [get_value -radix hex $top/data]
        foreach path [list $top/active $top/sync $top/soterr $top/softerr $top/dut/ClockLane/HSClockingX/Legacy/GenNoMMCM/cByteRecent $top/dut/ClockLane/HSClockingX/Legacy/GenNoMMCM/cByteAge] {
            lappend values [get_value -radix bin $path]
        }
        puts $raw [join $values \t]
    }
    flush $raw
}
proc sample_byte {} {
    global top
    set case [get_value -radix dec $top/scenario]
    if {$case >= 0 && $case ni {17 23 24 25}} { sample }
}
add_condition -notrace "$top/byteclk == 1" {sample_byte}
add_condition -notrace "$top/audit_tick == 1" {sample}
add_condition -notrace "$top/audit_tick == 0" {sample}
set elapsed_us 0
while {[get_value -radix bin $top/done] ne "1" && $elapsed_us < 600} {
    run 1 us
    incr elapsed_us
}
if {[get_value -radix bin $top/done] ne "1"} { error "Incomplete fixed-rate stimulus" }
sample
close $raw
puts "DPHY_RATE93_OBSERVATION_COMPLETE"
quit
