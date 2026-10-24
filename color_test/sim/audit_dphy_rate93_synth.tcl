# One fixed synthesis and, only after the offline gate, one routed OOC budget.
set root [file normalize [file join [file dirname [info script]] ..]]
if {$argc != 1 || [lindex $argv 0] ni {synth ready proof impl routed_audit}} { error "Expected synth, ready, proof, impl or routed_audit" }
set mode [lindex $argv 0]
set package [file join $root build dphy_rate93_qualified]
set out [file join $package $mode]
file mkdir $out
cd $out
proc stamp {name value} {
    set f [open $name w]; puts $f $value; close $f
}
proc export_structure {} {
    set f [open cells.tsv w]
    puts $f "cell\tref\tasync_reg\tinit\tblackbox\tclocks"
    foreach cell [get_cells -hier -filter {IS_PRIMITIVE == 1 || IS_BLACKBOX == 1}] {
        set props [list_property $cell]
        set row [list $cell [get_property REF_NAME $cell]]
        foreach prop {ASYNC_REG INIT IS_BLACKBOX} {
            set value ""
            if {[lsearch -exact $props $prop] >= 0} { set value [get_property $prop $cell] }
            lappend row $value
        }
        set cp [get_pins -quiet -of_objects $cell -filter {IS_CLOCK == 1}]
        lappend row [get_clocks -quiet -of_objects $cp]
        puts $f [join $row \t]
    }
    close $f
    set f [open nets.tsv w]
    puts $f "net\toutput_pins\tinput_pins\tports"
    foreach net [get_nets -hier] {
        set drivers [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
        set sinks [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
        set ports [get_ports -quiet -of_objects $net]
        puts $f [join [list $net $drivers $sinks $ports] \t]
    }
    close $f
    set f [open primitive_config.tsv w]
    foreach cell [get_cells -hier -filter {IS_PRIMITIVE == 1}] {
        foreach prop [lsort [list_property $cell]] {
            if {[regexp {^(INIT($|_)|SRVAL|READ_|WRITE_|DO[A-B]_REG|RSTREG|RST[A-B]|RAM_MODE|DATA_RATE|DATA_WIDTH|SERDES_MODE|INTERFACE_TYPE|IOBDELAY|DYN_CLK|IS_.*_INVERTED|IDELAY_|DELAY_SRC|HIGH_PERFORMANCE_MODE|SIGNAL_PATTERN|PIPE_SEL|REFCLK_FREQUENCY|BUFR_DIVIDE|DIFF_TERM|IOSTANDARD|IBUF_LOW_PWR)} $prop]} {
                puts $f [join [list $cell $prop [get_property $prop $cell]] \t]
            }
        }
    }
    foreach pin [get_pins -hier -filter {IS_CLOCK == 1}] {
        puts $f [join [list $pin IS_INVERTED [get_property IS_INVERTED $pin]] \t]
    }
    close $f
}
proc run_audit {} {
    global root out mode package
    set_param general.maxThreads 2
    set_param synth.maxThreads 2
    if {$mode eq "routed_audit"} {
        open_checkpoint [file join $package impl repaired_routed.dcp]
        foreach lane {0 1} {
            set dst [get_pins -hier -regexp [format {^phy/DataLaneGen\[%d\].DPHY_LaneSFEN_X/HSDeserializerX/Deserializer/DDLY$} $lane]]
            if {[llength $dst] != 1} { error "Actual lane sampler missing: $lane" }
            set src [get_ports [list [format {dphy_data_hs_p[%d]} $lane] [format {dphy_data_hs_n[%d]} $lane]]]
            foreach type {max min} {
                set paths [get_timing_paths -from $src -to $dst -delay_type $type -max_paths 4 -nworst 4]
                if {![llength $paths]} { error "No sampling timing paths: lane$lane $type" }
                report_timing -from $src -to $dst -delay_type $type -max_paths 4 -nworst 4 \
                    -file sampling_lane${lane}_${type}.rpt
            }
        }
        set f [open physical_identity.tsv w]
        puts $f "object\tpackage_pin\tstandard_or_type\tlocation"
        foreach port [get_ports dphy*] {
            puts $f [join [list $port [get_property PACKAGE_PIN $port] [get_property IOSTANDARD $port] {}] \t]
        }
        foreach cell [get_cells -hier -filter {REF_NAME == BUFIO || REF_NAME == BUFR || REF_NAME == BUFG || REF_NAME == IDELAYE2 || REF_NAME == ISERDESE2}] {
            puts $f [join [list $cell {} [get_property REF_NAME $cell] [get_property LOC $cell]] \t]
        }
        close $f
        stamp routed_audit_completed.txt [clock format [clock seconds] -gmt 1]
        return
    }
    if {$mode eq "proof"} {
        foreach label {synth ready} {
            set path [file join $package $label [expr {$label eq "synth" ? "repaired_synth.dcp" : "budget_ready.dcp"}]]
            open_checkpoint $path
            file mkdir [file join $out $label]
            cd [file join $out $label]
            export_structure
            close_design
            cd $out
        }
        stamp structure_proof_completed.txt [clock format [clock seconds] -gmt 1]
        return
    }
    if {$mode eq "ready"} {
        open_checkpoint [file join $package synth repaired_synth.dcp]
        set f [open gray_budget.tsv w]
        puts $f "bank\tsource_clock\tdestination_clock\tmax_delay_ns\tbus_skew_ns\tbits"
        set banks [get_cells -hier -filter {NAME =~ */rd_pntr_cdc_inst || NAME =~ */wr_pntr_cdc_inst}]
        if {[llength $banks] != 2} { error "Expected two real Gray pointer banks: $banks" }
        foreach bank $banks {
            set src [get_cells -hier -filter "NAME =~ $bank/src_gray_ff_reg*"]
            set candidates [get_cells -hier -filter "NAME =~ $bank/dest_graysync_ff_reg*"]
            set dst {}
            foreach cell $candidates {
                if {[regexp {dest_graysync_ff_reg\[0\]\[} $cell]} { lappend dst $cell }
            }
            if {[llength $src] != 5 || [llength $dst] != 5} { error "Gray bank width changed: $bank" }
            set sc [get_clocks -of_objects [get_pins -of_objects $src -filter {REF_PIN_NAME == C}]]
            set dc [get_clocks -of_objects [get_pins -of_objects $dst -filter {REF_PIN_NAME == C}]]
            if {[llength $sc] != 1 || [llength $dc] != 1 || $sc eq $dc} { error "Gray clocks not identified: $bank" }
            set sp [get_property -min PERIOD $sc]
            set dp [get_property -min PERIOD $dc]
            if {$sp <= 0 || $dp <= 0 || $sp >= 1000 || $dp >= 1000} { error "Fallback clock period remains" }
            # Exact formula in the installed2023.1 xpm_cdc_gray.tcl,lines17-18.
            set skew [expr {min($sp,$dp)}]
            set_max_delay -datapath_only -from $src -to $dst $sp
            set_bus_skew -from $src -to $dst $skew
            puts $f "$bank\t$sc\t$dc\t$sp\t$skew\t[llength $src]"
            set paths [get_timing_paths -from $src -to $dst -delay_type max -max_paths 5]
            if {[llength $paths] != 5} { error "Missing Gray timing coverage: $bank" }
            foreach path $paths {
                if {abs([get_property REQUIREMENT $path]-$sp)>0.001} { error "Gray max-delay override not effective" }
            }
        }
        close $f
        write_checkpoint budget_ready.dcp
        write_verilog -mode funcsim budget_ready.v
        write_xdc effective.xdc
        report_cdc -details -file cdc.rpt
        report_cdc -details -no_waiver -file cdc_no_waiver.rpt
        report_bus_skew -file bus_skew.rpt
        report_exceptions -coverage -file exceptions.rpt
        stamp budget_constraints_completed.txt [clock format [clock seconds] -gmt 1]
        return
    }
    if {$mode eq "impl"} {
        set gate [open [file join $package synthesis_gate.txt] r]
        if {[string trim [read $gate]] ne "PASS_CURRENT_SOURCE_CDC_STRUCTURE"} { error "Synthesis/CDC gate not passed" }
        close $gate
        open_checkpoint [file join $package ready budget_ready.dcp]
        stamp implementation_started.txt [clock format [clock seconds] -gmt 1]
        opt_design
        place_design
        route_design
        write_checkpoint repaired_routed.dcp
        report_timing_summary -delay_type min_max -report_unconstrained -file timing_routed.rpt
        report_cdc -details -file cdc.rpt
        report_cdc -details -no_waiver -file cdc_no_waiver.rpt
        report_bus_skew -file bus_skew.rpt
        report_drc -file drc.rpt
        report_utilization -file utilization.rpt
        report_utilization -hierarchical -file utilization_hierarchical.rpt
        check_timing -verbose -file check_timing.rpt
        report_exceptions -coverage -file exceptions.rpt
        report_route_status -file route_status.rpt
        report_clocks -file clocks.rpt
        set sample_cells [get_cells -hier -filter {REF_NAME == ISERDESE2}]
        report_timing -delay_type min_max -max_paths 64 -nworst 4 \
            -from [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}] \
            -to [get_pins -of_objects $sample_cells -filter {REF_PIN_NAME == DDLY}] \
            -file sampling_timing.rpt
        export_structure
        stamp implementation_completed.txt [clock format [clock seconds] -gmt 1]
        return
    }
    set gate [open [file join $package functional_gate.txt] r]
    if {[string trim [read $gate]] ne "PASS_CURRENT_SOURCE_FUNCTIONAL_MODEL"} { error "Functional gate not passed" }
    close $gate
    create_project -in_memory -part xc7z020clg400-2
    stamp tool_version.txt [version]
    set dphy [file join $root repo ip MIPI_D_PHY_RX hdl]
    set csi [file join $root repo ip MIPI_CSI_2_RX hdl]
    # Read existing, already generated real FIFO targets, with no IP generation
    # or upgrade. Integrate them in this one global synthesis, not extra OOC runs.
    set generated [file join $root color_test.srcs sources_1 bd system ip system_MIPI_CSI_2_RX_0_0 hdl]
    foreach name {cdc_fifo line_buffer} {
        set xci [file join $generated $name $name.xci]
        read_ip $xci
        set_property generate_synth_checkpoint false [get_files $xci]
        set ext [expr {$name eq "cdc_fifo" ? "vhd" : "v"}]
        set wrapper [get_files -all [file join $generated $name synth $name.$ext]]
        if {[llength $wrapper] != 1} { error "Existing real FIFO wrapper unavailable: $name" }
        set_property library csi $wrapper
    }
    report_ip_status -file ip_status.rpt
    set sources [open consumed_sources.tsv w]
    puts $sources "library\tpath"
    foreach name {DebugLib SyncAsync SyncAsyncReset SimpleFIFO ECC CRC16_behavioral LM LLP MIPI_CSI2_Rx} {
        set path [file join $csi $name.vhd]
        puts $sources "csi\t$path"
        read_vhdl -vhdl2008 -library csi $path
    }
    foreach name {DPHY_Pkg SyncAsync SyncAsyncReset DebugLib HS_Deserializer GlitchFilter HS_Clocking DPHY_LaneSCNN DPHY_LaneSFEN InputBuffer S_AXI_Lite MIPI_DPHY_Receiver} {
        set path [file join $dphy $name.vhd]
        puts $sources "dphy\t$path"
        read_vhdl -library dphy $path
    }
    set harness [file join $root sim dphy_lane_enable_harness.vhd]
    puts $sources "xil_defaultlib\t$harness"
    read_vhdl $harness
    close $sources
    report_compile_order -used_in synthesis -file compile_order.rpt
    stamp synthesis_started.txt [clock format [clock seconds] -gmt 1]
    synth_design -mode out_of_context -flatten_hierarchy rebuilt \
        -top dphy_lane_enable_harness -part xc7z020clg400-2
    stamp synthesis_completed.txt [clock format [clock seconds] -gmt 1]
    create_clock -name clk_fpga_0 -period 10.000 [get_ports s_axi_lite_aclk]
    create_clock -name clk_fpga_1 -period 6.667 [get_ports video_aclk]
    create_clock -name clk_fpga_2 -period 5.000 [get_ports RefClk]
    create_clock -name mipi_hs_clk -period 21.428571429 -waveform {0 10.714285714} [get_ports dphy_clk_hs_p]
    # Proposed fixed-rate overlay only. The production XDC is never changed.
    foreach edge {rise fall} {
        set opt {}
        if {$edge eq "fall"} { set opt {-clock_fall} }
        foreach polarity {p n} {
            set ports [get_ports [format {dphy_data_hs_%s[*]} $polarity]]
            set_input_delay -clock mipi_hs_clk {*}$opt -min -add_delay 1.607142 $ports
            set_input_delay -clock mipi_hs_clk {*}$opt -max -add_delay 9.107143 $ports
        }
    }
    read_xdc [file join $dphy MIPI_DPHY_Receiver.xdc]
    read_xdc [file join $csi mipi_csi2_rx.xdc]
    # The physical HS/LP assignment is identical to the production mipi.xdc.
    # Other ports are logical OOC boundaries, not additional package pads.
    foreach {name pin ios} {
        dphy_clk_hs_p Y7 LVDS_25 dphy_clk_hs_n Y6 LVDS_25
        dphy_clk_lp_p V8 HSUL_12 dphy_clk_lp_n W8 HSUL_12
        {dphy_data_hs_p[0]} W11 LVDS_25 {dphy_data_hs_n[0]} Y11 LVDS_25
        {dphy_data_hs_p[1]} U9 LVDS_25 {dphy_data_hs_n[1]} U8 LVDS_25
        {dphy_data_lp_p[0]} T9 HSUL_12 {dphy_data_lp_n[0]} U10 HSUL_12
        {dphy_data_lp_p[1]} Y12 HSUL_12 {dphy_data_lp_n[1]} Y13 HSUL_12
    } {
        set_property PACKAGE_PIN $pin [get_ports $name]
        set_property IOSTANDARD $ios [get_ports $name]
    }
    set_property INTERNAL_VREF 0.6 [get_iobanks 13]
    write_checkpoint repaired_synth.dcp
    write_verilog -mode funcsim repaired_synth.v
    write_xdc effective.xdc
    report_cdc -details -file cdc.rpt
    report_utilization -file utilization.rpt
    report_utilization -hierarchical -file utilization_hierarchical.rpt
    report_clocks -file clocks.rpt
    report_clock_interaction -file clock_interaction.rpt
    report_timing_summary -delay_type min_max -report_unconstrained -file timing_synth.rpt
    check_timing -verbose -file check_timing.rpt
    report_exceptions -coverage -file exceptions.rpt
    report_drc -file drc.rpt
    export_structure
    set f [open focused_properties.rpt w]
    foreach cell [get_cells -hier -regexp {.*(WatchHeartbeat|dByteHeartbeat|cByteAge|cByteRecent|RxClkActiveHSResetBridge|HSDeserializerX/ResetBridge|InputDelay|DivClkBuffer|SerialClkBuffer).*}] {
        puts $f [report_property -return_string $cell]
    }
    close $f
    stamp reports_completed.txt [clock format [clock seconds] -gmt 1]
}
if {[catch {run_audit} message options]} {
    stamp failure.txt "$message\n[dict get $options -errorinfo]"
    puts stderr $message
    exit 1
}
puts "RATE93_SYNTH_REPORTS_COMPLETE: structure acceptance requires offline audit"
exit 0
