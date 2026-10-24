# Pure Tcl fixtures. No Vivado commands, design generation or device access.
set ::DPHY_REPORT_TEST_ONLY 1
source [file join [file dirname [info script]] .. tools build_dphy_observer.tcl]
set checks 0
proc check {condition description} {
    if {![uplevel 1 [list expr $condition]]} {error "FAIL: $description"}
    incr ::checks
}
proc get_path_groups {} {return {**default** ctrl100 byte_clk RAW_MEASUREMENT}}
proc get_timing_paths {args} {
    set group [lindex $args 1]
    if {$group eq "RAW_MEASUREMENT"} {error "Raw exception was not kept separate"}
    return [list [lindex $args 3]]
}
proc get_property {property path} {
    if {$property ne "SLACK"} {error "Property lookup on a special path-group string"}
    if {$path eq "max"} {return $::setup}
    return $::hold
}
set setup 2.0
set hold 0.05
check {[observer_control_slacks] eq {2.0 0.05}} "default group is a string; min/max kept"
set hold -0.01
check {[catch {observer_control_slacks}]} "negative control hold stops publication"
set hold 0.05
set setup -0.01
check {[catch {observer_control_slacks}]} "negative control setup stops publication"
rename get_path_groups {}
proc get_path_groups {} {return {RAW_MEASUREMENT}}
check {[catch {observer_control_slacks}]} "missing control result stops publication"

set path [file join [pwd] skew_fixture.rpt]
foreach {text accepted} {
    {Slack (MET) : 0.150ns} 1
    {Slack (MET) : 0.000ns} 1
    {Slack (VIOLATED) : -0.010ns} 0
    {Slack (MET) : -0.010ns} 0
    {} 0
    {UNKNOWN FORMAT} 0
    {Slack (MET) : 0.200ns
Slack (VIOLATED) : unknown} 0
    {No paths found} 0
} {
    set f [open $path w]; puts $f $text; close $f
    check {(![catch {observer_bus_skew_gate $path}]) == $accepted} "bus-skew fixture: $text"
}
file delete $path
check {[catch {observer_bus_skew_gate $path}]} "missing report file stops publication"
puts "DPHY_OBSERVER_REPORT_GATES_PASS checks=$checks"
