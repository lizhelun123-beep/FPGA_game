# Resumed report-only review of build2. Complete timing-context replay avoids
# relying on unavailable input-delay removal commands or command-history grep.
# No synthesis, optimization, placement, routing or bitstream generation.
set root [file normalize [file join [file dirname [info script]] ..]]
set build [file join $root build pl_rate93_production build_2]
set stage [file join $build declared_model_replay]
if {$argc == 1 && [lindex $argv 0] eq "--correct-data-endpoints"} {
    set f [open [file join $build declared_model_replay.log] r]
    set prior [read $f];close $f
    if {[string first "Unexpected two-lane sampling endpoints" $prior] < 0} {error "Unexpected prior fixture failure"}
    set stage [file join $build declared_model_replay_endpoints]
} elseif {$argc != 0} {error "Unknown report invocation"}
if {[file exists $stage]} {error "Single resumed report entry only; preserve prior evidence"}
set receipt [file join $build declared_model_resume.json]
if {![file exists $receipt]} {error "Missing resumed-entry authorization and hash checks"}
file mkdir $stage
source [file join $root tools fixed_display.tcl]
open_checkpoint [file join $build route routed.dcp]
fd::clock_state startup [file join $build declared_model_candidate.xdc]
foreach {command name options} {
    report_timing_summary timing {-delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10}
    report_clock_interaction clock_interaction {}
    report_clocks clocks {}
    report_exceptions exceptions {-coverage}
    report_cdc cdc {-details -no_waiver}
    report_drc drc {-ruledecks {default bitstream_checks} -no_waivers}
    report_methodology methodology {-no_waivers}
    report_bus_skew bus_skew {}
    report_utilization utilization {}
    report_io io {}
} {$command {*}$options -file [file join $stage $name.rpt]}
set data [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
# The full top also contains four LP ISERDES units. Select the two actual HS
# data deserializers from the frozen routed netlist inventory, not all ISERDES.
set receivers [get_cells -hier -filter {REF_NAME == ISERDESE2 && NAME =~ */HSDeserializerX/Deserializer}]
set ddly [get_pins -of_objects $receivers -filter {REF_PIN_NAME == DDLY}]
if {[llength $data] != 4 || [llength $ddly] != 2} {error "Unexpected two-lane sampling endpoints"}
report_timing -delay_type min_max -max_paths 64 -nworst 4 -from $data -to $ddly -file [file join $stage sampling_timing.rpt]
fd::state_reports $stage
# The helper restores startup attributes before this checkpoint is written.
write_checkpoint [file join $stage routed.dcp]
close_design
puts "CAMERA_DECLARED_MODEL_REPLAY_COMPLETE_NO_SYNTHESIS_IMPLEMENTATION_EXPORT"
