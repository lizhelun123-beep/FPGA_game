# Board timing owns the declared fixed93 input window. Replay the complete
# timing context, removing only the packaged receiver's obsolete high-rate
# window; preserve every clock, exception and physical property.
proc camera_apply_declared_input_model {root out} {
    set ports [get_ports -quiet {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
    if {[llength $ports] != 4} {error "Expected four physical data inputs"}
    set clock [get_clocks -quiet mipi_hs_clk]
    if {[llength $clock] != 1 || abs([get_property PERIOD $clock]-21.428571429)>0.002} {error "Unexpected measured-rate clock model"}
    set raw [file join $out input_model_before.xdc]
    set clean [file join $out input_model_effective.xdc]
    write_xdc -type timing -force $raw
    set f [open $raw r];set text [read $f];close $f
    set f [open $clean w]
    # A reloaded DCP flattens source-file headings. Match the eight exact
    # obsolete commands (both native write_xdc list spellings), not headings.
    set obsolete [dict create]
    foreach polarity {n p} {
        foreach edge {"" "-clock_fall "} {
            foreach {bound value} {min 0.268 max 1.518} {
                set key "$polarity/$edge/$bound"
                foreach template {
                    {set_input_delay -clock [get_clocks -of_objects [get_ports dphy_hs_clock_clk_p]] %s-%s -add_delay %s [get_ports {{dphy_data_hs_%s[0]} {dphy_data_hs_%s[1]}}]}
                    {set_input_delay -clock [get_clocks -of_objects [get_ports dphy_hs_clock_clk_p]] %s-%s -add_delay %s [get_ports [list {dphy_data_hs_%s[0]} {dphy_data_hs_%s[1]}]]}
                } {dict set obsolete [format $template $edge $bound $value $polarity $polarity] $key}
            }
        }
    }
    set removed 0;set board_bounds 0;set seen [dict create]
    foreach line [split $text \n] {
        if {[regexp {^set_input_delay .* (0\.268|1\.518) \[get_ports } $line]} {
            if {![dict exists $obsolete $line]} {error "Unknown obsolete input-window command"}
            set key [dict get $obsolete $line]
            if {[dict exists $seen $key]} {error "Duplicate obsolete input-window command"}
            dict set seen $key 1
            incr removed
            continue
        }
        if {[regexp {^set_input_delay -clock mipi_hs_clk .* (1\.607|9\.107) \[get_ports } $line]} {incr board_bounds}
        puts $f $line
    }
    close $f
    if {$removed ni {0 8} || $board_bounds != 4} {error "Unknown input-model assembly: removed=$removed board_bounds=$board_bounds"}
    source [file join $root tools fixed_display.tcl]
    fd::clock_state startup $clean
    set f [open [file join $out input_model_binding.tsv] w]
    puts $f "obsolete_IP_commands_removed\t$removed"
    puts $f "canonical_board_bounds\t$board_bounds"
    puts $f "clock\tmipi_hs_clk\t[get_property PERIOD [get_clocks mipi_hs_clk]]"
    puts $f "ports\t$ports"
    close $f
}
