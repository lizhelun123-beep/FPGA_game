# Fixed 720p display preparation/build, invoked only by build_bitstream.tcl.
# No standalone project, parameter scan, camera fallback or automatic retry.
namespace eval fd {
    variable project_dir [file normalize [file join [file dirname [info script]] ..]]
    variable keep {processing_system7_0 axi_vdma_0 axi_dynclk_0 axi_mem_intercon ps7_0_axi_periph rst_100M proc_sys_reset_150M v_axi4s_vid_out_0 vtg rgb2dvi_0 xlconcat_0}
    variable remove {MIPI_D_PHY_RX_0 MIPI_CSI_2_RX_0 AXI_BayerToRGB_0 AXI_GammaCorrection_0 axi_vdma_1 axi_mem_intercon_1 proc_sys_reset_200M axis_subset_converter_0 axis_color_highlight_0}
}
proc fd::one {objects label} {
    if {[llength $objects] != 1} { error "$label: expected one object, got [llength $objects]" }
    return [lindex $objects 0]
}
proc fd::pin {name} { return [one [get_bd_pins -quiet $name] $name] }
proc fd::reconnect {source destination} {
    set p [pin $destination]
    set n [get_bd_nets -quiet -of_objects $p]
    if {[llength $n]} { disconnect_bd_net $n $p }
    connect_bd_net [pin $source] $p
}
proc fd::partition {} {
    variable keep; variable remove
    set actual {}
    foreach c [get_bd_cells] { lappend actual [string trimleft $c /] }
    set expected [concat $keep {display_irq_zero display_rst_axis display_rst_pixel}]
    if {[lsort $actual] eq [lsort $expected]} {
        validate_partition
        return
    }
    if {[lsort $actual] ne [lsort [concat $keep $remove]]} { error "Refuse unrecognized partial BD topology" }
    foreach name $keep { one [get_bd_cells -quiet $name] "retained $name" }
    # Preserve all software-visible addresses, remap only interconnect ports.
    foreach p [get_bd_intf_pins ps7_0_axi_periph/M*_AXI] {
        set n [get_bd_intf_nets -quiet -of_objects $p]
        if {[llength $n]} { delete_bd_objs $n }
    }
    foreach name $remove { delete_bd_objs [one [get_bd_cells -quiet $name] "remove $name"] }
    # Interface owns its physical clock p/n ports: delete the owner first.
    set interfaces [get_bd_intf_ports -quiet dphy_hs_clock]
    if {[llength $interfaces]} { delete_bd_objs $interfaces }
    set ports [get_bd_ports -quiet dphy_*]
    if {[llength $ports]} { delete_bd_objs $ports }
    set_property CONFIG.NUM_MI 3 [get_bd_cells ps7_0_axi_periph]
    foreach {master slave} {M00_AXI axi_dynclk_0/s00_axi M01_AXI vtg/ctrl M02_AXI axi_vdma_0/S_AXI_LITE} {
        connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/$master] [get_bd_intf_pins $slave]
    }
    foreach i {00 01 02} {
        reconnect processing_system7_0/FCLK_CLK0 ps7_0_axi_periph/M${i}_ACLK
        reconnect rst_100M/peripheral_aresetn ps7_0_axi_periph/M${i}_ARESETN
    }
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 display_irq_zero
    set_property -dict {CONFIG.CONST_WIDTH 1 CONFIG.CONST_VAL 0} [get_bd_cells display_irq_zero]
    reconnect display_irq_zero/dout xlconcat_0/In2
    # Vendor reset cores synchronize/filter the same held qualifier into each
    # respective domain. Legal 16-cycle aux filtering plus the reset sequencer;
    # this is NOT the VTC's independently required >=32 pixel reset pulse.
    # software waits 1ms after READY, with no active DMA during reconfiguration.
    foreach {name clock} {display_rst_axis processing_system7_0/FCLK_CLK1 display_rst_pixel axi_dynclk_0/PXL_CLK_O} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 $name
        set_property -dict {CONFIG.C_AUX_RESET_HIGH 0 CONFIG.C_AUX_RST_WIDTH 16} [get_bd_cells $name]
        reconnect $clock $name/slowest_sync_clk
        reconnect processing_system7_0/FCLK_RESET0_N $name/ext_reset_in
        reconnect axi_dynclk_0/DISPLAY_READY_O $name/aux_reset_in
        # Unused dcm_locked=1, mb_debug_sys_rst=0 use documented IP defaults.
    }
    reconnect display_rst_axis/peripheral_aresetn v_axi4s_vid_out_0/aresetn
    reconnect display_rst_pixel/peripheral_reset v_axi4s_vid_out_0/vid_io_out_reset
    reconnect display_rst_pixel/peripheral_aresetn vtg/resetn
    reconnect axi_dynclk_0/DISPLAY_READY_O rgb2dvi_0/aRst_n
    validate_partition
}
proc fd::same_net {source sink} {
    set a [one [get_bd_nets -quiet -of_objects [pin $source]] "source net $source"]
    set b [one [get_bd_nets -quiet -of_objects [pin $sink]] "sink net $sink"]
    if {$a ne $b} { error "Wrong connection: $source -> $sink" }
}
proc fd::validate_partition {} {
    variable keep
    validate_bd_design
    set actual {}
    foreach c [get_bd_cells] { lappend actual [string trimleft $c /] }
    if {[lsort $actual] ne [lsort [concat $keep {display_irq_zero display_rst_axis display_rst_pixel}]]} { error "Expected exact 14-cell display topology" }
    if {[llength [get_bd_ports -quiet dphy_*]] || [llength [get_bd_intf_ports -quiet dphy_hs_clock]]} { error "D-PHY port remains" }
    if {[get_property CONFIG.NUM_MI [get_bd_cells ps7_0_axi_periph]] != 3} { error "AXIL must have three masters" }
    foreach {name clock} {display_rst_axis processing_system7_0/FCLK_CLK1 display_rst_pixel axi_dynclk_0/PXL_CLK_O} {
        foreach {parameter value} {C_AUX_RST_WIDTH 16 C_AUX_RESET_HIGH 0 C_EXT_RESET_HIGH 0} {
            if {[get_property CONFIG.$parameter [get_bd_cells $name]] != $value} { error "Wrong derived reset parameter $name/$parameter" }
        }
        foreach pinname {ext_reset_in aux_reset_in} {
            if {[get_property CONFIG.POLARITY [pin $name/$pinname]] ne "ACTIVE_LOW"} { error "Wrong reset pin polarity: $name/$pinname" }
        }
        same_net $clock $name/slowest_sync_clk
        same_net processing_system7_0/FCLK_RESET0_N $name/ext_reset_in
        same_net axi_dynclk_0/DISPLAY_READY_O $name/aux_reset_in
    }
    foreach {source sink} {
        display_rst_axis/peripheral_aresetn v_axi4s_vid_out_0/aresetn
        display_rst_pixel/peripheral_reset v_axi4s_vid_out_0/vid_io_out_reset
        display_rst_pixel/peripheral_aresetn vtg/resetn
        axi_dynclk_0/DISPLAY_READY_O rgb2dvi_0/aRst_n
        display_irq_zero/dout xlconcat_0/In2
    } { same_net $source $sink }
    foreach {name offset} {axi_dynclk_0 0x43C00000 vtg 0x43C10000 axi_vdma_0 0x43010000} {
        set s [one [get_bd_addr_segs -of_objects [get_bd_addr_spaces processing_system7_0/Data] -filter "NAME =~ *SEG_${name}_*"] "address $name"]
        set range [get_property RANGE $s]
        if {$range eq "64K"} { set range 65536 }
        if {[get_property OFFSET $s] != $offset || $range != 65536} { error "Address ABI changed: $name" }
    }
    save_bd_design
}
proc fd::clock_audit {out state manifest} {
    foreach {name period} {clk_fpga_0 10 clk_fpga_1 7} {
        set c [one [get_clocks -quiet $name] "clock $name"]
        set actual [get_property PERIOD $c]
        if {abs($actual-$period)>0.002} { error "Clock period mismatch: $name $actual" }
        if {$state eq "startup"} { puts $manifest "$name\t$actual" }
    }
    foreach name {CLKOUT0 LOCKED} {
        one [get_pins -quiet system_i/axi_dynclk_0/U0/Inst_mmcme2_drp/mmcm_adv_inst/$name] "MMCM $name"
    }
    if {[llength [get_pins -quiet {system_i/axi_dynclk_0/U0/DisplayGuard/lock_sync_reg[*]/CLR}]] != 2} { error "Qualification reset exception target changed" }
    set at_serial [get_clocks -of_objects [get_pins system_i/axi_dynclk_0/U0/Inst_mmcme2_drp/mmcm_adv_inst/CLKOUT0]]
    set at_pixel [get_clocks -of_objects [get_pins system_i/axi_dynclk_0/U0/BUFR_inst/O]]
    set serial [one $at_serial "native serial clock"]
    set pixel [one $at_pixel "native pixel clock"]
    if {$state eq "startup"} {set period 2.0} elseif {$state eq "runtime"} {set period [expr {35.0/13}]} else {error "Unknown fixed clock state"}
    set f [open [file join $out ${state}_clock_identity.tsv] w]
    foreach {kind c factor high} [list serial $serial 1 0.5 pixel $pixel 5 0.4] {
        set p [get_property PERIOD $c]
        set wave [get_property WAVEFORM $c]
        if {abs($p-$period*$factor)>0.002 || [llength $wave]!=2 || abs([lindex $wave 0])>0.002 || abs([lindex $wave 1]-$p*$high)>0.002} {error "Native $state $kind waveform mismatch: $p $wave"}
        if {![get_property IS_GENERATED $c]} {error "Clock is not generated: $c"}
        puts $manifest "hdmi_${kind}_${state}\t$p"
        puts $f "$kind\t$c\t$p\t$wave\t[get_property MASTER_CLOCK $c]"
    }
    close $f
    return [list $serial $pixel]
}
proc fd::clock_state {state context} {
    set mmcm [one [get_cells -quiet system_i/axi_dynclk_0/U0/Inst_mmcme2_drp/mmcm_adv_inst] MMCM]
    # Remove invalid old exceptions AND clock-name reservations before reload.
    # Replay the complete flattened IP/user context, not just root clocks.
    reset_timing -invalid -clock_reservation
    if {$state eq "startup"} {set mult 10.0;set div 1} elseif {$state eq "runtime"} {set mult 52.0;set div 7} else {error "Unknown fixed clock state"}
    set_property CLKFBOUT_MULT_F $mult $mmcm
    set_property DIVCLK_DIVIDE $div $mmcm
    set_property CLKOUT0_DIVIDE_F 2.0 $mmcm
    read_xdc $context
    update_timing
}
proc fd::state_reports {out} {
    set context [file join $out timing_context.xdc]
    # reset_timing leaves physical properties and existing IP waivers intact.
    # Export/reload timing only; do not duplicate or broaden vendor waivers.
    write_xdc -type timing -force $context
    set cf [open $context r]; set text [read $cf]; close $cf
    if {[regexp {create_generated_clock[^\n]*(axi_dynclk|hdmi_)} $text]} {error "Manual HDMI clock override in timing context"}
    set f [open [file join $out mode_slack.tsv] w]
    set manifest [open [file join $out clocks.tsv] w]
    set rc [catch {
        foreach state {startup runtime} {
            clock_state $state $context
            set clocks [clock_audit $out $state $manifest]
            report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $out ${state}_timing.rpt]
            report_clock_interaction -file [file join $out ${state}_clock_interaction.rpt]
            report_bus_skew -file [file join $out ${state}_bus_skew.rpt]
            report_drc -ruledecks {default bitstream_checks} -no_waivers -file [file join $out ${state}_drc.rpt]
            report_cdc -details -file [file join $out ${state}_cdc.rpt]
            report_methodology -no_waivers -file [file join $out ${state}_methodology.rpt]
            report_exceptions -coverage -file [file join $out ${state}_exceptions.rpt]
            report_exceptions -ignored -file [file join $out ${state}_ignored_exceptions.rpt]
            report_exceptions -to [get_pins {system_i/axi_dynclk_0/U0/DisplayGuard/lock_sync_reg[*]/CLR}] -coverage -file [file join $out ${state}_lock_exception.rpt]
            foreach direction {from to} {
                foreach delay {max min} {
                    set p [one [get_timing_paths -$direction $clocks -delay_type $delay -max_paths 1] "$state $direction $delay path"]
                    puts $f "$state\t$direction\t$delay\t[get_property SLACK $p]"
                }
            }
        }
    } message options]
    close $f
    close $manifest
    # Never allow a runtime analysis view to become an exported artifact.
    clock_state startup $context
    if {$rc} {return -options $options $message}
}
proc fd::reports {out {stage routed} {emit_checkpoint 1}} {
    set f [open [file join $out pins.tsv] w]
    set pins {TMDS_clk_p U13 TMDS_clk_n V13 {TMDS_data_p[0]} W14 {TMDS_data_n[0]} Y14 {TMDS_data_p[1]} Y18 {TMDS_data_n[1]} Y19 {TMDS_data_p[2]} Y16 {TMDS_data_n[2]} Y17 hdmi_ddc_scl_io V18 hdmi_ddc_sda_io V17 {cam_gpio_tri_io[0]} U7 cam_i2c_scl_io T5 cam_i2c_sda_io U5}
    foreach {name location} $pins {
        set p [one [get_ports -quiet [list $name]] "board port $name"]
        set standard [expr {[string match TMDS* $name] ? "TMDS_33" : "LVCMOS33"}]
        if {[get_property PACKAGE_PIN $p] ne $location || [get_property IOSTANDARD $p] ne $standard} { error "Board I/O mismatch: $name" }
        puts $f "$name\t$location\t$standard"
    }
    foreach p [get_ports] {
        if {![dict exists $pins $p] && ![string match DDR_* $p] && ![string match FIXED_IO_* $p]} { error "Unexpected PL port: $p" }
    }
    close $f
    if {$emit_checkpoint} {write_checkpoint [file join $out $stage.dcp]}
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $out timing.rpt]
    report_clock_interaction -file [file join $out clock_interaction.rpt]
    report_clocks -file [file join $out clocks.rpt]
    report_exceptions -coverage -file [file join $out exceptions.rpt]
    report_cdc -details -file [file join $out cdc.rpt]
    report_drc -ruledecks {default bitstream_checks} -no_waivers -file [file join $out drc.rpt]
    report_methodology -no_waivers -file [file join $out methodology.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    report_utilization -file [file join $out utilization.rpt]
    report_io -file [file join $out io.rpt]
    if {$stage eq "routed"} {
        # A loaded gate-level DCP does not compile RTL. Bind its original,
        # hash-checked synthesis provenance; never pretend to query new HDL.
        foreach name {compile_order.rpt compile_sources.tsv} {
            file copy [file join $out synth $name] [file join $out $name]
        }
    } else {
        report_compile_order -used_in synthesis -file [file join $out compile_order.rpt]
        set f [open [file join $out compile_sources.tsv] w]
        foreach source [get_files -compile_order sources -used_in synthesis] {
            puts $f [file normalize $source]
        }
        close $f
    }
    set f [open [file join $out netlist_cells.tsv] w]
    foreach cell [get_cells -hier] {
        puts $f "$cell\t[get_property REF_NAME $cell]\t[get_property IS_PRIMITIVE $cell]\t[get_property IS_BLACKBOX $cell]"
    }
    close $f
    set f [open [file join $out structure.tsv] w]
    foreach cell [get_cells -hier -filter {IS_PRIMITIVE}] {
        set init {}
        foreach property [list_property $cell] {
            if {[string match INIT* $property]} { lappend init $property [get_property $property $cell] }
        }
        puts $f "$cell\t[get_property REF_NAME $cell]\t$init"
    }
    close $f
    set f [open [file join $out connections.tsv] w]
    foreach name {v_axi4s_vid_out_0/aresetn v_axi4s_vid_out_0/vid_io_out_reset vtg/resetn rgb2dvi_0/aRst_n} {
        set p [one [get_pins -quiet system_i/$name] "reset sink $name"]
        puts $f "$name\t[all_fanin -flat -startpoints_only -to $p]"
    }
    foreach cell [get_cells -hier -filter {REF_NAME =~ RAM* || REF_NAME =~ FIFO*}] {
        foreach p [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
            set ref [get_property REF_PIN_NAME $p]
            if {[regexp {^(CLK|RST|EN|WE|CE)} $ref]} {
                puts $f "$p\t[all_fanin -flat -startpoints_only -to $p]"
            }
        }
    }
    close $f
    state_reports $out
}
proc fd::prepare_layout {} {
    variable project_dir
    open_project [file join $project_dir color_test.xpr]
    if {[get_property PART [current_project]] ne "xc7z020clg400-2"} { error "Wrong part" }
    foreach f [get_files -of_objects [get_filesets constrs_1]] {
        if {[file tail $f] ni {system.xdc mipi.xdc hdmi_out.xdc debug_hub.xdc display720.xdc}} { error "Unreviewed user XDC: $f" }
    }
    set_property ip_repo_paths [list [file join $project_dir repo ip]] [current_project]
    foreach folder {axi_dynclk_v1_0 rgb2dvi_v1_3} {
        set core [ipx::open_core -set_current false [file join $project_dir repo ip $folder component.xml]]
        ipx::update_checksums $core; ipx::save_core $core; ipx::unload_core $core
    }
    update_ip_catalog -rebuild
    set bd [one [get_files */system.bd] system.bd]
    open_bd_design $bd
    upgrade_ip [get_ips {system_axi_dynclk_0_0 system_rgb2dvi_0_0}]
    partition
    # Select only the fixed display XDC and the existing board HDMI pins.
    # Camera constraints remain intact on disk, but cannot constrain this BD.
    foreach name {system.xdc mipi.xdc debug_hub.xdc} {
        foreach f [get_files -quiet */$name] { set_property IS_ENABLED false $f }
    }
    set_property IS_ENABLED true [one [get_files */hdmi_out.xdc] "board HDMI constraints"]
    set display_xdc [file join $project_dir color_test.srcs constrs_1 new display720.xdc]
    if {[llength [get_files -quiet $display_xdc]] == 0} { add_files -fileset constrs_1 -norecurse $display_xdc }
    set_property IS_ENABLED true [get_files $display_xdc]
    set_property PROCESSING_ORDER LATE [get_files $display_xdc]
    set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs synth_1]
    set_property INCREMENTAL_CHECKPOINT {} [get_runs synth_1]
    if {[get_property AUTO_INCREMENTAL_CHECKPOINT [get_runs synth_1]] != 0 || [get_property INCREMENTAL_CHECKPOINT [get_runs synth_1]] ne ""} { error "Stale synthesis checkpoint remains enabled" }
    # Synthesize the selected BD RTL in the one new top-level synthesis; do not
    # import stale per-IP DCPs. This also exposes the actual source file graph.
    set_property SYNTH_CHECKPOINT_MODE None $bd
    if {[get_property SYNTH_CHECKPOINT_MODE $bd] ne "None"} { error "BD RTL synthesis mode not applied" }
    return $bd
}
proc fd::disable_ip_caches {} {
    set count 0
    foreach name {system_axi_dynclk_0_0 system_rgb2dvi_0_0} {
        config_ip_cache -disable_for_ip [one [get_ips -quiet $name] "cache IP $name"]
        incr count
    }
    return $count
}
proc fd::prepare_full {out} {
    set bd [prepare_layout]
    set f [open [file join $out command_help.rpt] w]
    puts $f "Vivado [version -short]; full help output is retained in this invocation's Vivado log."
    foreach command {config_ip_cache reset_run report_compile_order} {
        puts $f "$command\n[help $command]"
    }
    close $f
    reset_target all $bd
    generate_target all $bd
    foreach wrapper [make_wrapper -files $bd -top] {
        if {[llength [get_files -quiet $wrapper]] == 0} { add_files -norecurse -fileset sources_1 $wrapper }
    }
    update_compile_order -fileset sources_1
    set count [disable_ip_caches]
    reset_run synth_1
    # Actual Vivado compile graph, not a mocked/source-only command check.
    report_compile_order -used_in synthesis -file [file join $out compile_order.rpt]
    set f [open [file join $out compile_sources.tsv] w]
    foreach source [get_files -compile_order sources -used_in synthesis] { puts $f [file normalize $source] }
    close $f
    report_ip_status -file [file join $out ip_status.rpt]
    set enabled {}
    foreach source [get_files -of_objects [get_filesets constrs_1]] {
        if {[get_property IS_ENABLED $source]} { lappend enabled [file tail $source] }
    }
    set f [open [file join $out prelaunch.tsv] w]
    puts $f "part\t[get_property PART [current_project]]"
    puts $f "top\t[get_property TOP [get_filesets sources_1]]"
    puts $f "auto_incremental\t[expr {[get_property AUTO_INCREMENTAL_CHECKPOINT [get_runs synth_1]] ? 1 : 0}]"
    puts $f "incremental_checkpoint\t[get_property INCREMENTAL_CHECKPOINT [get_runs synth_1]]"
    puts $f "bd_checkpoint\t[get_property SYNTH_CHECKPOINT_MODE $bd]"
    puts $f "cache_calls\t$count"
    puts $f "enabled_user_xdc\t[join [lsort $enabled] ,]"
    close $f
    close_project
}
proc fixed_display_main {args} {
    set finalize 0
    set prepare_only 0
    set synthesize 0
    set report_synth 0
    set report_implementation 0
    set implement 0
    if {[lindex $args 0] eq "-prepare-only"} { set prepare_only 1; set args [lrange $args 1 end] }
    if {[lindex $args 0] eq "-synthesize"} { set synthesize 1; set args [lrange $args 1 end] }
    if {[lindex $args 0] eq "-report-synth"} { set report_synth 1; set args [lrange $args 1 end] }
    if {[lindex $args 0] eq "-report-implementation"} { set report_implementation 1; set args [lrange $args 1 end] }
    if {[lindex $args 0] eq "-implement"} { set implement 1; set args [lrange $args 1 end] }
    if {[lindex $args 0] eq "-finalize"} { set finalize 1; set args [lrange $args 1 end] }
    if {$prepare_only + $synthesize + $report_synth + $report_implementation + $implement + $finalize > 1} { error "Exactly one operation mode is allowed" }
    if {[llength $args]!=2 || [lindex $args 0] ne "-out"} { error "Usage: -display720 -out <new fixed-build directory>" }
    set out [file normalize [lindex $args 1]]
    set project_dir $fd::project_dir
    set audit [file join $project_dir tools fixed_display_audit.py]
    if {![string match "2023.1*" [version -short]]} { error "Vivado 2023.1 required" }
    if {$prepare_only} {
        exec python -I $audit prepare --out $out
        fd::prepare_full $out
        exec python -I $audit prepared --out $out
        puts "FIXED_DISPLAY_FULL_PRELAUNCH_PASS_NO_SYNTHESIS"
        return
    }
    if {$finalize} {
        # Resume ONLY the same hash-bound routed checkpoint after offline
        # structural review. No extra synth/route; export has its own quota.
        exec python -I $audit gate --out $out
        if {[file exists [file join $out system_wrapper.bit]]} { error "BIT already generated; no automatic repeat" }
        open_checkpoint [file join $out routed.dcp]
        if {[get_property PART [current_design]] ne "xc7z020clg400-2"} { error "Wrong part" }
        fd::publish $out $audit
        close_project
        return
    }
    if {$report_synth} {
        # Read the existing synthesis result only; never reset/launch a run.
        if {![file exists [file join $out synthesis.claim]]} { error "No existing synthesis claim" }
        open_project [file join $project_dir color_test.xpr]
        open_run synth_1
        fd::reports [file join $out synth] synthesized
        close_project
        exec python -I $audit synth_gate --out $out
        return
    }
    if {$report_implementation} {
        exec python -I $audit implementation_report_inputs --out $out
        open_checkpoint [file join $out routed.dcp]
        fd::reports $out routed 0
        close_design
        exec python -I $audit gate --out $out
        puts "FIXED_READ_ONLY_ROUTED_REPORTS_COMPLETE_NO_EXPORT"
        return
    }
    if {$implement} {
        exec python -I $audit claim_implementation --out $out
        open_project [file join $project_dir color_test.xpr]
        # Route the exact audited input; project run dependencies cannot launch
        # synthesis or regenerate IP. Default opt/place/route, one attempt only.
        open_checkpoint [file join $out synth synthesized.dcp]
        opt_design
        place_design
        route_design
        fd::reports $out
        close_project
        exec python -I $audit gate --out $out
        puts "FIXED_IMPLEMENTATION_REPORTS_COMPLETE_NO_EXPORT"
        return
    }
    if {!$synthesize} {
        exec python -I $audit prepare --out $out
        fd::prepare_full $out
        exec python -I $audit prepared --out $out
    }
    exec python -I $audit claim_prepared --out $out
    open_project [file join $project_dir color_test.xpr]
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {![string match "synth_design Complete*" [get_property STATUS [get_runs synth_1]]]} { error "Fixed synthesis failed" }
    open_run synth_1
    file mkdir [file join $out synth]
    fd::reports [file join $out synth] synthesized
    close_project
    # A missing manual structural review intentionally pauses before implementation.
    exec python -I $audit synth_gate --out $out
}
proc fd::publish {out audit} {
    # Publishing is a separately authorized operation, even after all reports pass.
    exec python -I $audit claim_export --out $out
    # The routed DCP embeds its hardware definition. Vivado 2023.1's direct
    # fixed-platform export was checked against the canonical HWH before BIT.
    # include_bit itself runs bitgen in this context: do NOT write_bitstream
    # separately. Extract the exact generated payloads from the resulting XSA.
    write_hw_platform -fixed -include_bit [file join $out system.xsa]
    exec python -I $audit extract_export --out $out
    exec python -I $audit export --out $out
}
