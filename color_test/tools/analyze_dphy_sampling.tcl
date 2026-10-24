# Existing routed checkpoint only. --corners-only exports fixed-setting paths
# without entering the legacy what-if sweep. Never save a DCP or launch a build.
set project_dir [file normalize [file join [file dirname [info script]] ..]]
set report_dir [file join $project_dir reports]
set checkpoint [file join $project_dir color_test.runs impl_1 system_wrapper_routed.dcp]
set corners_only 0
if {[lindex $argv 0] eq "--corners-only"} {
    set corners_only 1
    set argv [lrange $argv 1 end]
}
if {[llength $argv] > 1 || [string match --* [lindex $argv 0]]} {
    error "Usage: analyze_dphy_sampling.tcl ?--corners-only? ?existing-routed.dcp?"
}
if {[llength $argv] > 0} { set checkpoint [file normalize [lindex $argv 0]] }
if {![file isfile $checkpoint]} { error "Missing routed checkpoint: $checkpoint" }
file mkdir $report_dir
open_checkpoint $checkpoint

set data_delays [lsort [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *HSDeserializerX/InputDelay}]]
set clock_delay [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *HSClockingX/InputDelay}]
set endpoints [lsort [get_pins -hier -filter {REF_PIN_NAME == DDLY && NAME =~ *HSDeserializerX/Deserializer/DDLY}]]
set ports [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
if {[llength $data_delays] != 2 || [llength $clock_delay] != 1 || [llength $endpoints] != 2 || [llength $ports] != 4} {
    error "Expected two data IDELAYs/DDLYs, one clock IDELAY, and four differential input ports"
}
foreach cell [concat $clock_delay $data_delays] {
    puts "DPHY_CELL $cell TYPE=[get_property IDELAY_TYPE $cell] TAPS=[get_property IDELAY_VALUE $cell] REFCLK=[get_property REFCLK_FREQUENCY $cell]"
}
if {$corners_only} {
    # Both checks at both process corners are needed to distinguish an empty
    # within-corner window from an empty intersection across process corners.
    # rise_to/fall_to select DDLY data transitions, NOT capture clock edges.
    # For each individual P/N source, retain both DDR capture clock edges.
    set corner_report [file join $report_dir dphy_sampling_corners.rpt]
    set header [open $corner_report w]
    puts $header "# DPHY_CORNER_QUERY_V1"
    puts $header "# checkpoint: $checkpoint"
    puts $header "# checkpoint_bytes: [file size $checkpoint]"
    puts $header "# checkpoint_mtime: [file mtime $checkpoint]"
    puts $header "# fixed setting; no property/constraint changes, sweep, build, DCP save or hardware access"
    set original_delays {}
    foreach cell [concat $clock_delay $data_delays] {
        lappend original_delays [get_property IDELAY_VALUE $cell]
        puts $header "# delay: $cell taps=[get_property IDELAY_VALUE $cell]"
    }
    close $header
    set requests 0
    foreach endpoint $endpoints {
        if {![regexp {DataLaneGen\[([01])\]} $endpoint unused lane]} {
            error "Unrecognized production lane endpoint: $endpoint"
        }
        foreach polarity {p n} {
            set port [get_ports -regexp [format {^dphy_data_hs_%s\[%d\]$} $polarity $lane]]
            if {[llength $port] != 1} { error "Missing lane $lane $polarity source" }
            foreach corner {Fast Slow} {
                foreach transition {rise fall} {
                    foreach type {max min} {
                        report_timing -from $port -${transition}_to $endpoint -corner $corner -delay_type $type -max_paths 8 -nworst 8 -significant_digits 3 -path_type full_clock_expanded -append -file $corner_report
                        incr requests
                    }
                }
            }
        }
    }
    set current_delays {}
    foreach cell [concat $clock_delay $data_delays] {
        lappend current_delays [get_property IDELAY_VALUE $cell]
    }
    if {$current_delays ne $original_delays || $requests != 32} {
        error "Read-only sampling query invariant failed"
    }
    set footer [open $corner_report a]
    puts $footer "# DPHY_CORNER_QUERY_COMPLETE requests=$requests"
    close $footer
    close_design
    puts "DPHY_CORNERS_COMPLETE: requests=$requests; fixed setting; no sweep/build/DCP save/hardware"
    return
}
report_methodology -file [file join $report_dir dphy_sampling_methodology.rpt]
set baseline_report [file join $report_dir dphy_sampling_baseline.rpt]
set baseline_file [open $baseline_report w]
puts $baseline_file "Baseline: both lanes; setup/hold over both DDR capture edges, grouped by data transition"
close $baseline_file
foreach endpoint $endpoints {
    foreach edge {rise fall} {
        foreach type {max min} {
            report_timing -from $ports -${edge}_to $endpoint -delay_type $type -max_paths 4 -nworst 4 -path_type full_clock_expanded -append -file $baseline_report
        }
    }
}

proc sample_slacks {ports endpoints} {
    set result {}
    foreach endpoint $endpoints {
        foreach edge {rise fall} {
            foreach type {max min} {
                set paths [get_timing_paths -quiet -from $ports -${edge}_to $endpoint -delay_type $type -max_paths 1]
                if {[llength $paths] != 1} { error "Missing $type $edge path to $endpoint" }
                lappend result [get_property SLACK [lindex $paths 0]]
            }
        }
    }
    return $result
}
puts "DPHY_BASELINE_SLACKS [sample_slacks $ports $endpoints]"

# Check the complete legal 0..31 tap range in the existing routed topology.
# The two data lanes are independent: evaluating equal tap counts enumerates
# every count for each lane, so per-lane feasibility permits unequal settings.
# Property changes affect only this process's timing model and are discarded.
set csv [open [file join $report_dir dphy_sampling_taps.csv] w]
puts $csv "clock_taps,data_taps,lane0_data_rise_setup,lane0_data_rise_hold,lane0_data_fall_setup,lane0_data_fall_hold,lane1_data_rise_setup,lane1_data_rise_hold,lane1_data_fall_setup,lane1_data_fall_hold"
set feasible_counts {0 0}
set best_margins {-Inf -Inf}
set best_settings {{} {}}
for {set clock_taps 0} {$clock_taps <= 31} {incr clock_taps} {
    set_property IDELAY_VALUE $clock_taps $clock_delay
    for {set data_taps 0} {$data_taps <= 31} {incr data_taps} {
        set_property IDELAY_VALUE $data_taps $data_delays
        update_timing
        set slacks [sample_slacks $ports $endpoints]
        puts $csv [join [concat $clock_taps $data_taps $slacks] ,]
        for {set lane 0} {$lane < 2} {incr lane} {
            set offset [expr {$lane * 4}]
            set margin [lindex [lsort -real [lrange $slacks $offset [expr {$offset + 3}]]] 0]
            if {$margin >= 0.0} { lset feasible_counts $lane [expr {[lindex $feasible_counts $lane] + 1}] }
            if {$margin > [lindex $best_margins $lane]} {
                lset best_margins $lane $margin
                lset best_settings $lane [list $clock_taps $data_taps]
            }
        }
    }
    flush $csv
    puts "DPHY_SWEEP clock=$clock_taps/31 feasible=$feasible_counts best=$best_margins"
}
close $csv
set summary [open [file join $report_dir dphy_sampling_window.txt] w]
puts $summary "Checkpoint: $checkpoint"
puts $summary "Input delays unchanged: min=0.268 ns, max=1.518 ns; DDR period=3.571 ns"
puts $summary "In-memory exhaustive IDELAY_VALUE sweep: 32 clock counts x 32 data counts"
puts $summary "Existing routing and primitive modes retained; no production signoff claim"
for {set lane 0} {$lane < 2} {incr lane} {
    puts $summary "Lane $lane: feasible counts=[lindex $feasible_counts $lane], best worst-edge/corner slack=[lindex $best_margins $lane] ns, clock/data taps=[lindex $best_settings $lane]"
}
if {[lindex $feasible_counts 0] == 0 || [lindex $feasible_counts 1] == 0} {
    puts $summary "NO_TAP_SOLUTION: do not apply best failing settings; a topology or verified interface-contract change is required"
    puts "DPHY_NO_TAP_SOLUTION: feasible=$feasible_counts best=$best_margins settings=$best_settings"
}
close $summary
close_design
puts "DPHY_ANALYSIS_COMPLETE: no checkpoint, project, BIT, or XSA was written"
