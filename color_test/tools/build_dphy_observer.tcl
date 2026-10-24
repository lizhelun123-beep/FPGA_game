# Pure report gates are shared with directed Tcl checks, without opening Vivado.
proc observer_control_slacks {} {
    set setup 1000000
    set hold 1000000
    foreach group [get_path_groups] {
        if {$group eq "RAW_MEASUREMENT"} {continue}
        foreach type {max min} {
            set paths [get_timing_paths -group $group -delay_type $type -max_paths 1]
            if {![llength $paths]} {continue}
            set slack [get_property SLACK [lindex $paths 0]]
            if {$type eq "max"} {set setup [expr {min($setup,$slack)}]}
            if {$type eq "min"} {set hold [expr {min($hold,$slack)}]}
        }
    }
    if {$setup == 1000000 || $hold == 1000000 || $setup < 0 || $hold < 0} {
        error "Missing/negative diagnostic control timing: $setup/$hold"
    }
    return [list $setup $hold]
}
proc observer_bus_skew_gate {path} {
    set f [open $path r]
    set report [read $f]
    close $f
    if {[regexp -nocase {VIOLATED|no paths found} $report]} {error "Bus-skew failed: $path"}
    set checks [regexp -all -inline {Slack\s+\((MET|VIOLATED)\)\s*:\s*([-+0-9.]+)\s*ns} $report]
    if {![llength $checks]} {error "Missing/unrecognized bus-skew slack: $path"}
    foreach {entry status slack} $checks {
        if {$status ne "MET" || ![string is double -strict $slack] || $slack < 0} {
            error "Invalid bus-skew result: $entry"
        }
    }
}
proc observer_reset_ram_audit {out samplers} {
    set f [open [file join $out reset_structure.rpt] w]
    set source [get_cells -hier -filter {NAME == control/sampler_hold_reg}]
    if {[llength $source]!=1} {error "Missing unique sampler_hold register"}
    set source_q [get_pins -of_objects $source -filter {REF_PIN_NAME == Q}]
    set source_loads [get_pins -leaf -of_objects [get_nets -segments -of_objects $source_q] -filter {DIRECTION == IN}]
    puts $f "SAMPLER_HOLD_LOADS $source_loads"
    set async_loads {}
    foreach p $source_loads {
        if {[get_property REF_PIN_NAME $p] in {PRE CLR}} {lappend async_loads $p}
    }
    if {[llength $async_loads]!=4} {error "Expected exactly ONE four-stage reset chain, got $async_loads"}
    foreach p $async_loads {
        if {![string match {control/byte_reset_bridge/*} $p]} {error "Independent reset chain remains: $p"}
    }
    set stages [get_cells -hier -regexp {^control/byte_reset_bridge/(.*/)?arststages_ff_reg\[[0-9]+\]$}]
    puts $f "RESET_CHAIN_STAGES $stages"
    if {[llength $stages]!=4} {error "Missing four shared reset stages"}
    for {set i 0} {$i<4} {incr i} {
        set cell [get_cells -hier -regexp [format {^control/byte_reset_bridge/(.*/)?arststages_ff_reg\[%d\]$} $i]]
        set d [get_pins -of_objects $cell -filter {REF_PIN_NAME == D}]
        set driver [get_pins -leaf -of_objects [get_nets -segments -of_objects $d] -filter {DIRECTION == OUT}]
        puts $f "CHAIN_LINK $i D=$d DRIVER=$driver"
        if {$i==0} {
            if {[llength [get_cells -of_objects $driver -filter {REF_NAME == GND}]]!=1} {error "Shared reset first D is not zero"}
        } elseif {![regexp [format {^control/byte_reset_bridge/(.*/)?arststages_ff_reg\[%d\]/Q$} [expr {$i-1}]] $driver]} {
            error "Reset stages are not one serial chain: $i $driver"
        }
    }
    if {[llength [get_cells -quiet -hier -regexp {^lanes\[[01]\]\.sampler/.*SerdesReset.*}]]} {
        error "Lane internal reset bridge was not bypassed"
    }
    set reset_nets {}
    foreach p [get_pins -of_objects $samplers -filter {REF_PIN_NAME == RST}] {
        set nets [get_nets -segments -of_objects $p]
        set drivers [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
        puts $f "ISERDES_RST $p DRIVERS $drivers"
        if {[llength $drivers]!=1 || ![regexp {^control/byte_reset_bridge/(.*/)?arststages_ff_reg\[3\]/Q$} $drivers]} {
            error "Lane reset does not consume shared final stage: $p $drivers"
        }
        lappend reset_nets $drivers
    }
    if {[llength [lsort -unique $reset_nets]]!=1} {error "Lane resets diverge"}
    set controls [get_cells -hier -regexp {^control/(write_index_reg\[[0-9]+\]|capturing_reg|finish_pending_reg|request_seen_reg|done_byte_reg|warmup_reg\[[0-9]+\])$}]
    if {[llength $controls]<20} {error "Missing capture/RAM control registers"}
    foreach c $controls {
        puts $f "RAM_OR_CAPTURE_CONTROL $c [get_property REF_NAME $c]"
        if {[get_property REF_NAME $c] ni {FDRE FDSE}} {error "Async reset reintroduced into capture/RAM control: $c"}
    }
    set shared_q [lindex $reset_nets 0]
    set shared_loads [get_pins -leaf -of_objects [get_nets -segments -of_objects $shared_q] -filter {DIRECTION == IN}]
    puts $f "SHARED_RESET_LOADS $shared_loads"
    # Ack must reset while stopped; its only async reset is the shared output.
    set ack [get_pins control/byte_released_reg/CLR]
    if {$ack ni $shared_loads} {error "Release acknowledgement not on shared reset"}
    # Inspect the inferred RAM ports themselves, including their complete
    # combinational cones back to sequential startpoints, not just RTL names.
    set rams [get_cells -hier -filter {REF_NAME =~ RAMB*}]
    if {![llength $rams]} {error "Expected inferred observation BRAM"}
    set ram_controls [get_pins -of_objects $rams -filter {REF_PIN_NAME =~ ADDR* || REF_PIN_NAME =~ EN* || REF_PIN_NAME =~ WE*}]
    set starts [all_fanin -flat -startpoints_only -to $ram_controls]
    set drivers [get_cells -of_objects $starts -filter {REF_NAME =~ FD*}]
    if {![llength $drivers]} {error "No RAM control sequential startpoints found"}
    foreach c $drivers {
        puts $f "ACTUAL_RAM_CONTROL_STARTPOINT $c [get_property REF_NAME $c]"
        if {[get_property REF_NAME $c] ni {FDRE FDSE}} {error "Async RAM address/enable startpoint: $c"}
    }
    close $f
    set init_file [open [file join $out initialization.rpt] w]
    set ff_by_name [dict create]
    foreach ff [get_cells -hier -filter {REF_NAME =~ FD*}] {dict set ff_by_name [get_property NAME $ff] $ff}
    set expected_init {control/delay_hold_reg 1 control/sampler_hold_reg 1 control/observe_reg 0
        control/cap_valid_reg 0 control/cap_busy_reg 0 control/request_reg 0 control/byte_released_reg 0
        control/capturing_reg 0 control/finish_pending_reg 0 control/request_seen_reg 0 control/done_byte_reg 0
        control/rvalid_reg 0 control/bvalid_reg 0}
    for {set i 0} {$i<4} {incr i} {
        lappend expected_init [format {control/warmup_reg[%d]} $i] 0
        lappend expected_init [format {control/clear_wait_reg[%d]} $i] [expr {$i==3 ? 1 : 0}]
        lappend expected_init [format {control/byte_reset_bridge/arststages_ff_reg[%d]} $i] 0
    }
    foreach {name expected} $expected_init {
        if {![dict exists $ff_by_name $name]} {error "Missing initialization register $name"}
        set cell [dict get $ff_by_name $name]
        set init [string tolower [get_property INIT $cell]]
        puts $init_file "$name [get_property REF_NAME $cell] INIT=$init EXPECTED=$expected"
        if {($expected==0 && $init ni {0 1'b0 1'h0}) || ($expected==1 && $init ni {1 1'b1 1'h1})} {
            error "Startup INIT mismatch: $name $init"
        }
    }
    foreach c $stages {
        set async [get_property ASYNC_REG $c]
        puts $init_file "SHARED_ASYNC_REG $c ASYNC_REG=$async CLOCK [get_clocks -of_objects [get_pins -of_objects $c -filter {REF_PIN_NAME == C}]]"
        if {![string is boolean -strict $async] || !$async} {error "Missing ASYNC_REG: $c VALUE=$async"}
    }
    foreach s $samplers {
        foreach property {INIT_Q1 INIT_Q2 INIT_Q3 INIT_Q4 SRVAL_Q1 SRVAL_Q2 SRVAL_Q3 SRVAL_Q4} {
            set value [string tolower [get_property $property $s]]
            puts $init_file "$s $property=$value"
            if {$value ni {0 1'b0 1'h0}} {error "Unexpected sampler startup/reset value: $s $property $value"}
        }
    }
    close $init_file
}
if {[info exists ::DPHY_REPORT_TEST_ONLY]} {return}

# Exactly one additional isolated diagnostic implementation. Never edits the production BD,
# never builds the stopped vendor/fixed families, never starts a hardware session.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[llength $argv] ni {1 2}} {error "Use the explicitly authorized attempt driver"}
set out [file normalize [lindex $argv 0]]
set routed_gate_only [expr {[llength $argv]==2 && [lindex $argv 1] eq "ROUTED_GATE_ONLY"}]
set implement_only [expr {[llength $argv]==2 && [lindex $argv 1] eq "IMPLEMENT_ONLY"}]
set audit_only [expr {[llength $argv]==2 && [lindex $argv 1] eq "AUDIT_ONLY"}]
set synth_only [expr {[llength $argv]==2 && [lindex $argv 1] in {SYNTHESIS_ONLY AUDIT_ONLY}}]
set expected [expr {$synth_only ? "shared_reset_audit" : "attempt2"}]
set permitted [list [file normalize [file join $root build dphy_observer_140 $expected]]]
if {$synth_only} {lappend permitted [file normalize [file join $root build dphy_observer_140 shared_reset_audit verification2]]}
if {$synth_only} {lappend permitted [file normalize [file join $root build dphy_observer_140 shared_reset_audit fixture_package]]}
if {$implement_only || $routed_gate_only} {lappend permitted [file normalize [file join $root build dphy_observer_140 shared_reset_audit fixture_package fixed_implementation]]}
if {$out ni $permitted} {
    error "Unexpected attempt directory"
}
set ip [file join $root repo ip MIPI_D_PHY_RX hdl]
set ps [file join $root color_test.srcs sources_1 bd system ip system_processing_system7_0_0]
set psdcp [file join $root color_test.runs system_processing_system7_0_0_synth_1 system_processing_system7_0_0.dcp]
set ledger_name [expr {($implement_only || $routed_gate_only) ? "implementation_attempt.json" : $synth_only ? "synth_attempt.json" : "build_attempt.json"}]
if {![file exists [file join $out $ledger_name]]} {error "Use the single-attempt driver"}
set ledger_file [open [file join $out $ledger_name] r]
set ledger_text [read $ledger_file]
close $ledger_file
if {![regexp {"status"\s*:\s*"(STARTED|AUDIT_REPAIR|GATE_RECHECK)"} $ledger_text]} {
    error "Attempt is not STARTED; preserve the consumed allowance and prior evidence"
}
if {[file exists [file join $out observer.bit]]} {error "Preserve the prior diagnostic bitstream"}
if {$routed_gate_only} {
    open_checkpoint [file join $out observer_routed.dcp]
    set_param general.maxThreads 2
    set out [file join $out gate_recheck]
    file mkdir $out
} elseif {$implement_only} {
    # Fixed, already functionally and structurally audited generation; no synthesis.
    open_checkpoint [file join [file dirname $out] audited_synth.dcp]
    set_param general.maxThreads 2
    set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2}]
    if {[llength $samplers]!=2} {error "Implementation input sampler identity mismatch"}
} elseif {!$audit_only} {
create_project -in_memory -part xc7z020clg400-2
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_CDC} [current_project]
set_param general.maxThreads 2
set_param synth.maxThreads 2

# Canonical submodule changed only in the opt-in diagnostic generic. Refresh
# package checksums without regenerating production targets or editing the BD.
if {$synth_only} {
    set core [ipx::open_core -set_current false [file join $root repo ip MIPI_D_PHY_RX component.xml]]
    ipx::update_checksums $core
    ipx::save_core $core
    ipx::unload_core $core
}
# Explicit read_vhdl below uses canonical files, never generated ipshared copies.
set_property ip_repo_paths [list [file join $root repo ip]] [current_project]
update_ip_catalog -rebuild

foreach name {DPHY_Pkg DphySyncAsync DphySyncAsyncReset HS_Deserializer InputBuffer} {
    read_vhdl -vhdl2008 [file join $ip ${name}.vhd]
}
read_verilog [file join $ps system_processing_system7_0_0_stub.v]
read_verilog -sv [file join $root rtl dphy_observer_control.sv]
read_verilog -sv [file join $out dphy_observer_top.sv]
synth_design -top dphy_observer_top -part xc7z020clg400-2 -flatten_hierarchy rebuilt
read_checkpoint -cell ps $psdcp
write_checkpoint -force [file join $out linked_synth.dcp]

read_xdc [file join $out pins.xdc]
create_clock -name hs140 -period [expr {50.0/7.0}] -waveform [list 0 [expr {25.0/7.0}]] [get_ports dphy_hs_clock_clk_p]
create_clock -name ctrl100 -period 10 [get_pins ps/FCLK_CLK0]
create_clock -name ref200 -period 5 [get_pins ps/FCLK_CLK2]
foreach ports {{dphy_data_hs_p[*]} {dphy_data_hs_n[*]}} {
    foreach edge {rise fall} {
        set opts {}
        if {$edge eq "fall"} {set opts {-clock_fall}}
        set_input_delay -clock hs140 {*}$opts -min -add_delay 0.535714 [get_ports $ports]
        set_input_delay -clock hs140 {*}$opts -max -add_delay 3.035715 [get_ports $ports]
    }
}
set_property IODELAY_GROUP DPHY_OBSERVER [get_cells -hier -filter {REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL}]
# Canonical async-assert/sync-release bridges. Only their first stages and reset
# pins are excepted; no blanket clock group, data or sampler exception is added.
set first [get_pins -quiet -hier -regexp {^.*/oSyncStages_reg\[0\]/D$}]
if {[llength $first]} {set_false_path -to $first}
set resets [get_pins -quiet -hier -regexp {^.*/oSyncStages_reg\[[0-9]+\]/(PRE|CLR)$}]
if {[llength $resets]} {set_false_path -through $resets}
set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2}]
if {[llength $samplers]!=2} {error "Expected two canonical high-speed samplers"}
set raw_inputs [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set sampler_data [get_pins -of_objects $samplers -filter {REF_PIN_NAME == DDLY}]
group_path -name RAW_MEASUREMENT -from $raw_inputs -to $sampler_data
if {$synth_only} {
    write_checkpoint -force [file join $out audit_input_synth.dcp]
    set f [open [file join $out synthesis_complete.json] w]
    puts $f {{"synthesis_completed":true,"implementation_runs":0}}
    close $f
}
} else {
    # Only re-read the exact synthesized/fully constrained DCP for a reviewed
    # report-script repair. No synth_design, catalog edit or constraint changes.
    open_checkpoint [file join $out audit_input_synth.dcp]
    set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2}]
    if {[llength $samplers]!=2} {error "Audit DCP sampler identity mismatch"}
}
if {$synth_only} {
    # Deliberately terminate BEFORE opt/place/route. This is a structural gate,
    # never a routed timing, physical reset-skew or load authorization receipt.
    report_cdc -details -file [file join $out cdc.rpt]
    report_drc -no_waivers -file [file join $out drc.rpt]
    report_utilization -hierarchical -file [file join $out utilization.rpt]
    check_timing -verbose -file [file join $out check_timing.rpt]
    report_clocks -file [file join $out clocks.rpt]
    report_timing_summary -report_unconstrained -file [file join $out timing_estimated.rpt]
    observer_reset_ram_audit $out $samplers
    # Pre-opt synthesis still counts dedicated PS DDR/MIO pads as logical I/O.
    # Never waive DRC: bind its reported ports to real PS7 pads and separately
    # require every ordinary PL port to retain its package pin and IOSTANDARD.
    set io_report [open [file join $out io_scope_review.rpt] w]
    set ps7 [get_cells -hier -filter {REF_NAME == PS7}]
    if {[llength $ps7]!=1} {error "Retained PS leaf is not exactly one hard PS7"}
    set pads [get_ports {DDR_* MIO[*] PS_CLK PS_SRSTB PS_PORB}]
    puts $io_report "DEDICATED_PS_LOGICAL_PORTS [llength $pads]"
    if {[llength $pads]!=130} {error "Unexpected retained PS pad interface"}
    if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX && !IS_PRIMITIVE}]]} {error "Unresolved linked blackbox"}
    foreach port [get_ports] {
        set name [get_property NAME $port]
        if {[regexp {^(DDR_|MIO\[|PS_(CLK|SRSTB|PORB)$)} $name]} {
            # The synthesized top still has pad buffers. Traverse only data
            # pins of I/O buffers (never T/control or arbitrary combinational
            # logic) to bind each dedicated port to its real hard-PS pin.
            set frontier [get_nets -segments -of_objects $port]
            set owners {}
            for {set depth 0} {$depth<4} {incr depth} {
                set endpoints [get_pins -leaf -of_objects $frontier]
                set owners [get_cells -of_objects $endpoints -filter {REF_NAME == PS7}]
                puts $io_report "PAD_TRACE $name DEPTH=$depth PINS=$endpoints"
                if {[llength $owners]} {break}
                # Vivado2023.1 processing_system7.ttcl explicitly inserts
                # BIBUF(PAD,IO) for fixed PS pads; these are not PL IOBs.
                set buffers [get_cells -of_objects $endpoints -filter {REF_NAME == BIBUF || REF_NAME =~ IBUF* || REF_NAME =~ OBUF* || REF_NAME =~ IOBUF*}]
                if {![llength $buffers]} {break}
                set data_pins [get_pins -of_objects $buffers -filter {REF_PIN_NAME == I || REF_PIN_NAME == O || REF_PIN_NAME == IO || REF_PIN_NAME == PAD}]
                set frontier [get_nets -segments -of_objects $data_pins]
            }
            puts $io_report "PS_PAD $name OWNERS $owners"
            if {[llength $owners]!=1} {error "Unresolved hard PS pad: $name"}
        } else {
            set package_pin [get_property PACKAGE_PIN $port]
            set standard [get_property IOSTANDARD $port]
            puts $io_report "PL_PAD $name PACKAGE_PIN=$package_pin IOSTANDARD=$standard"
            if {$package_pin eq "" || $standard in {DEFAULT ""}} {error "PL I/O constraint missing: $name"}
        }
    }
    foreach v [get_drc_violations] {
        set name [get_property NAME $v]
        set severity [get_property SEVERITY $v]
        puts $io_report "DRC $name SEVERITY=$severity"
        if {[string match NSTD-1* $name] || [string match UCIO-1* $name]} {
            foreach port [get_ports -of_objects $v] {
                set port_name [get_property NAME $port]
                if {![regexp {^(DDR_|MIO\[|PS_(CLK|SRSTB|PORB)$)} $port_name]} {
                    error "DRC includes unreviewed PL pad: $name $port_name"
                }
            }
        } elseif {![string match IOCNT-1* $name] && $severity in {Warning {Critical Warning} Error}} {
            error "Unreviewed synthesis DRC: $name $severity"
        }
    }
    close $io_report
    set critical [get_cdc_violations -filter {SEVERITY == Critical}]
    set warnings [get_cdc_violations -filter {SEVERITY == Warning}]
    if {[llength $critical] || [llength $warnings]} {error "CDC audit failed: $critical $warnings"}
    if {[llength [get_drc_violations -filter {SEVERITY == Error}]] ||
        [llength [get_drc_violations -quiet {REQP-1839* REQP-1840* CHECK-3* PDCN-1569*}]]} {
        error "DRC/RAM audit failed"
    }
    write_checkpoint -force [file join $out audited_synth.dcp]
    set receipt [open [file join $out synthesis_pass.json] w]
    puts $receipt {{"scope":"SYNTHESIS_ONLY","shared_reset_chains":1,"reset_stages":4,"lane_internal_reset_bridges":0,"critical_cdc":0,"ram_async_controls":0,"initialization_checked":true,"implementation_runs":0,"bitstreams":0,"timing_signoff":false,"board_operations":0}}
    close $receipt
    puts "DPHY_OBSERVER_SHARED_RESET_SYNTHESIS_PASS"
    close_design
    exit
}
# A varying tap intentionally probes invalid points. These real constrained I/O
# paths remain reported, but do not sign off reception. All diagnostic control,
# storage, clocks and CDC must independently pass before a bitstream is written.
if {!$routed_gate_only} {
    opt_design
    place_design
    route_design
    write_checkpoint -force [file join $out observer_routed.dcp]
}
report_timing_summary -report_unconstrained -file [file join $out timing_all.rpt]
report_utilization -hierarchical -file [file join $out utilization.rpt]
report_utilization -file [file join $out utilization_full.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
# Batch mode ignores report names. Query the actual current result set below.
report_cdc -details -file [file join $out cdc.rpt]
report_drc -no_waivers -file [file join $out drc.rpt]
report_clocks -file [file join $out clocks.rpt]
report_exceptions -file [file join $out exceptions.rpt]
set skew_report [report_bus_skew -delay_type min_max -warn_on_violation -return_string]
set skew_file [open [file join $out bus_skew.rpt] w]
puts $skew_file $skew_report
close $skew_file
foreach type {max min} {
    foreach corner {Fast Slow} {
        report_timing -group RAW_MEASUREMENT -delay_type $type -corner $corner \
            -max_paths 64 -nworst 8 -path_type full_clock_expanded -significant_digits 3 \
            -append -file [file join $out raw_measurement_paths.rpt]
    }
}
observer_reset_ram_audit $out [get_cells -hier -filter {REF_NAME == ISERDESE2}]
lassign [observer_control_slacks] control_wns control_whs
set critical [get_cdc_violations -filter {SEVERITY == Critical}]
if {[llength $critical]} {error "Unresolved Critical CDC: $critical; no bitstream"}
set cdc_warnings [get_cdc_violations -filter {SEVERITY == Warning}]
if {[llength $cdc_warnings]} {error "CDC warnings require review: $cdc_warnings; no bitstream"}
set drc_errors [get_drc_violations -filter {SEVERITY == Error}]
if {[llength $drc_errors]} {error "DRC errors: $drc_errors; no bitstream"}
set drc_critical [get_drc_violations -filter {SEVERITY == "Critical Warning"}]
if {[llength $drc_critical]} {error "Unresolved physical Critical DRC: $drc_critical; no bitstream"}
set ram_drc [get_drc_violations {REQP-1839* REQP-1840* CHECK-3* PDCN-1569*}]
if {[llength $ram_drc]} {error "Unresolved RAM control/inference or capped DRC report: $ram_drc; no bitstream"}
foreach warning [get_drc_violations -filter {SEVERITY == Warning}] {
    # The unchanged canonical LP bus is DONT_TOUCH; replicated bits not used by
    # its stop detector have no loads. Review only that exact structural case.
    if {![string match "RTSTAT-10*" [get_property NAME $warning]]} {
        error "Unreviewed DRC warning: $warning; no bitstream"
    }
    foreach net [get_nets -of_objects $warning] {
        if {![regexp {^lanes\[[01]\]\.sampler/dLP} $net]} {
            error "Unexpected loadless net: $net; no bitstream"
        }
    }
}
# XPM Gray crossings have bus-skew constraints. Missing/unrecognized evidence
# fails closed instead of treating a warning-only report command as a pass.
observer_bus_skew_gate [file join $out bus_skew.rpt]
set f [open [file join $out check_timing.rpt] r]
set coverage [read $f]
close $f
foreach check {no_clock constant_clock unconstrained_internal_endpoints multiple_clock partial_input_delay partial_output_delay} {
    if {![regexp [format {checking %s \(([0-9]+)\)} $check] $coverage all count] || $count!=0} {
        error "Unresolved constraint coverage: $check; no bitstream"
    }
}
if {![regexp {checking no_input_delay \(([0-9]+)\)} $coverage all count] || $count!=6} {
    error "Unexpected unconstrained input set; expected only six asynchronous LP status inputs"
}
set ffs [get_cells -hier -filter {REF_NAME =~ FD*}]
foreach ff $ffs {
    set cp [get_pins -quiet -of_objects $ff -filter {REF_PIN_NAME == C}]
    if {[llength $cp] && ![llength [get_clocks -quiet -of_objects $cp]]} {error "Unclocked diagnostic FF: $ff"}
}
set ps7 [get_cells -hier -filter {REF_NAME == PS7}]
if {[llength $ps7]!=1} {error "Retained hard PS was not linked exactly once"}
if {[llength [get_cells -quiet -hier -filter {REF_NAME =~ *vdma* || REF_NAME =~ *Bayer* || REF_NAME =~ *rgb2dvi*}]]} {
    error "Forbidden production video/DMA logic in isolated diagnostic"
}
set bram [llength [get_cells -hier -filter {REF_NAME =~ RAMB36*}]]
set bram18 [llength [get_cells -hier -filter {REF_NAME =~ RAMB18*}]]
set lut [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
set ffcount [llength $ffs]
set slice_sites {}
foreach loc [get_property LOC [get_cells -hier -filter {IS_PRIMITIVE}]] {
    if {[string match SLICE_* $loc]} {lappend slice_sites $loc}
}
set slices [llength [lsort -unique $slice_sites]]
set dsp [llength [get_cells -hier -filter {REF_NAME =~ DSP48*}]]
if {$bram+$bram18/2.0>=98 || $lut>=37240 || $ffcount>=74480 || $dsp>=154 || $slices>=9975} {
    error "Diagnostic exceeds70percent major-resource or75percent slice cap"
}
set report [open [file join $out control_timing_groups.rpt] w]
foreach group [get_path_groups] {
    foreach type {max min} {
        set paths [get_timing_paths -group $group -delay_type $type -max_paths 1]
        puts $report "GROUP=$group TYPE=$type PATHS=[llength $paths]"
        if {[llength $paths]} {puts $report "SLACK=[get_property SLACK [lindex $paths 0]]"}
    }
}
close $report
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
write_bitstream -force [file join $out observer.bit]
set f [open [file join $out implementation_pass.json] w]
puts $f "{\"diagnostic_control_timing_pass\":true,\"control_wns_ns\":$control_wns,\"control_whs_ns\":$control_whs,\"critical_cdc\":0,\"bram36\":$bram,\"bram18\":$bram18,\"lut\":$lut,\"ff\":$ffcount,\"slices\":$slices,\"dsp\":$dsp,\"initialization_checked\":true,\"constraint_coverage_checked\":true,\"raw_sampler_signoff\":false,\"dma_instances\":0,\"production_baseline\":false}"
close $f
puts "DPHY_OBSERVER_DIAGNOSTIC_BUILD_PASS"
close_design
