# Non-project, isolated D-PHY clock topology verification. No production
# project update, full build, BIT/XSA publication, or hardware connection.
set root [file normalize [file join [file dirname [info script]] ..]]
set sim_dir [file join $root sim]
set build_dir [file join $root build dphy_clock_ooc]
set report_dir [file join $root reports]
set ip_dir [file join $root repo ip MIPI_D_PHY_RX hdl]
file mkdir $build_dir
file mkdir $report_dir

# Adopted complete AMD RX/FIXED PHY. Configuration is audited before the
# separately authorized single fixed implementation; no legacy scan is entered.
if {$argv in {--amd-phy-config --amd-phy-budget --amd-phy-query}} {
    source [file join $sim_dir dphy_amd_phy_budget.tcl]
    exit 0
}

if {$argv eq "--hpc-budget-query"} {
    # Read-only decomposition of the SAME attempt; no synth/place/route rerun.
    set out [file join $root build dphy_sampling hpc_internal_probe]
    open_checkpoint [file join $out probe_routed.dcp]
    set f [open [file join $out net_delays.txt] w]
    set mmcm [get_cells mmcm]
    foreach pin {CLKIN1 CLKFBOUT CLKOUT0 CLKOUT1} {
        set net [get_nets -of_objects [get_pins $mmcm/$pin]]
        puts $f "NET_AT_MMCM_PIN $pin $net"
        foreach delay [get_net_delays -of_objects $net] {
            puts $f [report_property -all -return_string $delay]
        }
    }
    foreach cell [get_cells -hier -filter {REF_NAME == BUFIO || REF_NAME == BUFR}] {
        puts $f "BUFFER $cell"
        puts $f [report_property -all -return_string $cell]
        set net [get_nets -of_objects [get_pins $cell/O]]
        foreach delay [get_net_delays -of_objects $net] {
            puts $f [report_property -all -return_string $delay]
        }
    }
    close $f
    set report [file join $out byte_clock_paths.rpt]
    foreach corner {Fast Slow} {
        foreach type {max min} {
            report_timing -from [get_clocks byte_unbuffered] -to [get_clocks byte_unbuffered] \
                -corner $corner -delay_type $type -max_paths 1 -path_type full_clock_expanded \
                -significant_digits 3 -append -file $report
        }
    }
    puts "HPC_INTERNAL_SAME_DCP_QUERY_COMPLETE"
    close_design
    exit 0
}

# Check logical leaf membership across hierarchical aliases. This
# helper also resumes report-only queries from the SAME optimized checkpoint.
proc shared_feedback_model_reports {out samplers} {
    if {[file exists [file join $out sampling_corners.rpt]]} {
        error "Preserve existing shared model report; no silent overwrite"
    }
    set shared_net [get_nets -of_objects [get_pins shared_feedback.feedback_serial_buffer/O]]
    set shared_pins [get_property NAME [get_pins -leaf -of_objects [get_nets -segments $shared_net]]]
    set receipt [file join $out connections_model_query_verified.txt]
    if {[file exists $receipt]} {error "Preserve existing model-query connectivity receipt"}
    set f [open $receipt w]
    puts $f "SHARED_FEEDBACK_NET $shared_net"
    puts $f "PINS $shared_pins"
    foreach cell [get_cells -hier -filter {REF_NAME == MMCME2_ADV || REF_NAME == BUFG || REF_NAME == ISERDESE2 || REF_NAME == IBUFDS}] {
        puts $f "CELL $cell [get_property REF_NAME $cell]"
    }
    close $f
    if {[lsearch -exact $shared_pins mmcm/CLKFBIN] < 0} {
        error "Feedback is not on the serial BUFG net"
    }
    foreach cell $samplers {
        foreach pin {CLK CLKB} {
            if {[lsearch -exact $shared_pins $cell/$pin] < 0} {
                error "D sampler is not on the shared feedback/serial net"
            }
        }
    }
    report_clocks -file [file join $out generated_clocks.rpt]
    report_utilization -file [file join $out utilization_synthesized.rpt]
    set report [file join $out sampling_corners.rpt]
    set f [open $report w]
    puts $f "# SHARED_FB_MODEL_V1 fixed 0/0; unplaced model only; feedback family attempt 2"
    close $f
    set requests 0
    foreach cell $samplers {
        if {![regexp {lanes\[([01])\]} $cell -> lane]} {error "Unknown model lane"}
        foreach pn {p n} {
            set src [get_ports [format {dphy_data_%s[%d]} $pn $lane]]
            foreach corner {Fast Slow} {
                foreach transition {rise fall} {
                    foreach type {max min} {
                        report_timing -from $src -${transition}_to [get_pins $cell/D] \
                            -corner $corner -delay_type $type -max_paths 8 -nworst 8 \
                            -significant_digits 3 -path_type full_clock_expanded -append -file $report
                        incr requests
                    }
                }
            }
        }
    }
    set f [open $report a]; puts $f "# SHARED_FB_MODEL_COMPLETE requests=$requests"; close $f
}

if {$argv eq "--shared-feedback-model-query"} {
    # Resume the entry assertion failure without another synthesis/attempt.
    set out [file join $root build dphy_sampling shared_feedback_model]
    open_checkpoint [file join $out probe_optimized.dcp]
    set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2 && NAME =~ */Deserializer}]
    if {[llength $samplers] != 2} {error "Expected two D samplers in saved model"}
    shared_feedback_model_reports $out $samplers
    set f [open [file join $out model_query_stage.txt] w]
    puts $f "UNPLACED_MODEL_REPORTS_COMPLETE_SAME_DCP_NO_IMPLEMENTATION"
    close $f
    close_design
    exit 0
}

# Explicitly authorized pre-functional, one-seed budget probe. This branch
# never executes the historical guard simulation or phase/tap loops below.
if {$argv in {--hpc-budget --bufg-feedback-budget --shared-feedback-model-budget --local-clock-budget --pll-clock-budget}} {
    set pll_probe [expr {$argv eq "--pll-clock-budget"}]
    set local_probe [expr {$argv eq "--local-clock-budget"}]
    set model_probe [expr {$argv eq "--shared-feedback-model-budget"}]
    set bufg_probe [expr {!$local_probe && $argv ne "--hpc-budget"}]
    set tag [expr {$local_probe ? "LOCAL_CLOCK" : ($model_probe ? "SHARED_FB_MODEL" : ($bufg_probe ? "BUFG_FEEDBACK" : "HPC_INTERNAL"))}]
    set folder [expr {$local_probe ? "local_clock_probe" : ($model_probe ? "shared_feedback_model" : ($bufg_probe ? "bufg_feedback_probe" : "hpc_internal_probe"))}]
    set generic [expr {$local_probe ? "LOCAL_CLOCK_PROBE=1" : ($model_probe ? "SHARED_FB_SERIAL_PROBE=1" : ($bufg_probe ? "BUFG_FEEDBACK_PROBE=1" : "HPC_INTERNAL_PROBE=1"))}]
    if {$pll_probe} {
        set tag PLL_CLOCK
        set folder pll_clock_probe
        set generic PLL_CLOCK_PROBE=1
    }
    set cmt_kind [expr {$pll_probe ? "pll" : "mmcm"}]
    set out [file join $root build dphy_sampling $folder]
    if {[file exists [file join $out probe_stage.txt]]} {
        error "Budget attempt already exists; preserve evidence, do not silently rerun"
    }
    file mkdir $out
    cd $out
    proc probe_stage {value} {
        set f [open probe_stage.txt w]; puts $f $value; close $f
        puts "BUDGET_PROBE_STAGE $value"
    }
    probe_stage [expr {$model_probe ? "STARTED_FEEDBACK_FAMILY_ATTEMPT_2_MODEL_ONLY" : "STARTED_ATTEMPT_1"}]
    puts "PROBE_TOOL [version]"
    set_param synth.maxThreads 2
    foreach name {DPHY_Pkg SyncAsync SyncAsyncReset HS_Deserializer} {
        read_vhdl -vhdl2008 [file join $ip_dir $name.vhd]
    }
    read_verilog -sv [file join $sim_dir dphy_clock_compensation_ooc.sv]
    synth_design -mode out_of_context -top dphy_clock_compensation_ooc \
        -part xc7z020clg400-2 -flatten_hierarchy rebuilt -generic $generic
    probe_stage SYNTHESIZED
    create_clock -name mipi_hs_clk -period 3.571 [get_ports dphy_clk_p]
    create_clock -name ref_clk -period 5.000 [get_ports refclk]
    set data_ports [get_ports {dphy_data_p[*] dphy_data_n[*]}]
    foreach edge {rise fall} {
        set opts {}
        if {$edge eq "fall"} {set opts {-clock_fall}}
        set_input_delay -clock mipi_hs_clk {*}$opts -min -add_delay 0.268 $data_ports
        set_input_delay -clock mipi_hs_clk {*}$opts -max -add_delay 1.518 $data_ports
    }
    foreach {port pin ios} {dphy_clk_p Y7 LVDS_25 dphy_clk_n Y6 LVDS_25 dphy_clk_lp_p V8 HSUL_12 dphy_clk_lp_n W8 HSUL_12 dphy_data_p[0] W11 LVDS_25 dphy_data_n[0] Y11 LVDS_25 dphy_data_p[1] U9 LVDS_25 dphy_data_n[1] U8 LVDS_25 dphy_data_lp_p[0] T9 HSUL_12 dphy_data_lp_n[0] U10 HSUL_12 dphy_data_lp_p[1] Y12 HSUL_12 dphy_data_lp_n[1] Y13 HSUL_12} {
        set_property PACKAGE_PIN $pin [get_ports $port]
        set_property IOSTANDARD $ios [get_ports $port]
    }
    set_property INTERNAL_VREF 0.6 [get_iobanks 13]
    if {$local_probe} {
        set_property IODELAY_GROUP DPHY_LOCAL_BUDGET [get_cells -hier -filter {REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL}]
    }
    # No exceptions or CLOCK_DEDICATED_ROUTE overrides in this probe.
    opt_design
    set mmcm [get_cells -quiet -hier -filter [expr {$pll_probe ? {REF_NAME == PLLE2_ADV} : {REF_NAME == MMCME2_ADV}}]]
    set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2 && NAME =~ */Deserializer}]
    if {[llength $mmcm] != [expr {$local_probe ? 0 : 1}] || [llength $samplers] != 2 ||
        [llength [get_cells -hier -filter {REF_NAME == ISERDESE2}]] != 6 ||
        [llength [get_cells -quiet -hier -filter {REF_NAME == IDELAYE2}]] != [expr {$local_probe ? 1 : 0}] ||
        [llength [get_cells -hier -filter {REF_NAME == BUFIO}]] != [expr {$bufg_probe ? 0 : 1}] ||
        [llength [get_cells -hier -filter {REF_NAME == BUFR}]] != [expr {$bufg_probe ? 0 : 1}] ||
        [llength [get_cells -hier -filter {REF_NAME == BUFG}]] != [expr {$model_probe ? 3 : ($bufg_probe ? 4 : 1)}]} {
        error "Fixed budget probe primitive/load mismatch"
    }
    if {$pll_probe && ([llength [get_cells -quiet -hier -filter {REF_NAME == MMCME2_ADV}]] != 0 ||
        [llength [get_cells -quiet -hier -filter {REF_NAME == IDELAYCTRL}]] != 0 ||
        [get_property CLKFBOUT_MULT $mmcm] != 4 || [get_property CLKOUT0_DIVIDE $mmcm] != 4 ||
        [get_property CLKOUT1_DIVIDE $mmcm] != 16 || [get_property CLKOUT0_PHASE $mmcm] != -90.0 ||
        [get_property CLKOUT1_PHASE $mmcm] != -22.5)} {
        error "Not the single fixed PLL M4/D1/O4/O16 negative-phase point"
    }
    foreach cell $samplers {
        if {[get_property IOBDELAY $cell] ne "NONE"} {error "Probe is not D direct"}
    }
    if {$local_probe} {
        set delay [get_cells -hier -filter {REF_NAME == IDELAYE2}]
        if {[get_property IDELAY_TYPE $delay] ne "VARIABLE" ||
            [get_property IDELAY_VALUE $delay] != 0 ||
            [get_property SIGNAL_PATTERN $delay] ne "CLOCK" ||
            [get_property REFCLK_FREQUENCY $delay] != 200.0 ||
            [llength [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]] != 1} {
            error "Local probe is not the fixed VARIABLE clock-tap0 point"
        }
        report_property -all $delay -file clock_delay_optimized.txt
    } else {
        report_property -all $mmcm -file ${cmt_kind}_optimized.txt
    }
    write_checkpoint -force probe_optimized.dcp
    if {$model_probe} {
        # Cheap, unplaced model screen. Deliberately exits before place/route.
        # A positive estimate would still require an independent routed gate.
        shared_feedback_model_reports $out $samplers
        probe_stage UNPLACED_MODEL_REPORTS_COMPLETE_NO_IMPLEMENTATION
        close_design
        exit 0
    }
    place_design
    probe_stage PLACED
    if {!$local_probe} {report_property -all $mmcm -file ${cmt_kind}_placed.txt}
    report_utilization -file utilization_placed.rpt
    report_utilization -hierarchical -file utilization_hierarchical.rpt
    route_design
    probe_stage ROUTED
    write_checkpoint -force probe_routed.dcp
    if {$local_probe} {
        report_property -all $delay -file clock_delay_routed.txt
    } else {report_property -all $mmcm -file ${cmt_kind}_routed.txt}
    report_drc -file drc.rpt
    report_route_status -file route_status.rpt
    report_methodology -file methodology.rpt
    report_clock_utilization -file clocks.rpt
    report_cdc -details -file cdc.rpt
    report_timing_summary -delay_type min_max -file timing.rpt
    report_clocks -file generated_clocks.rpt
    set f [open connections.txt w]
    foreach cell [get_cells -hier -filter {REF_NAME == MMCME2_ADV || REF_NAME == PLLE2_ADV || REF_NAME == BUFG || REF_NAME == BUFIO || REF_NAME == BUFR || REF_NAME == ISERDESE2 || REF_NAME == IBUFDS || REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL}] {
        puts $f "CELL $cell [get_property REF_NAME $cell] LOC=[get_property LOC $cell] BEL=[get_property BEL $cell]"
    }
    foreach pin [expr {$local_probe ? {} : {CLKIN1 CLKFBIN CLKFBOUT CLKOUT0 CLKOUT1}}] {
        set net [get_nets -of_objects [get_pins $mmcm/$pin]]
        puts $f "[string toupper $cmt_kind]_PIN $pin NET=$net PINS=[get_pins -of_objects $net]"
        puts $f "ROUTE [get_property ROUTE $net]"
        puts $f "NODES [get_nodes -of_objects $net]"
    }
    close $f
    if {$local_probe} {
        # Verify leaf membership, not hierarchical net-object identity.
        set serial [get_cells -hier -filter {REF_NAME == BUFIO}]
        set byte [get_cells -hier -filter {REF_NAME == BUFR}]
        set f [open local_clock_connections.txt w]
        foreach {cell pin} [list $delay DATAOUT $serial O $byte O] {
            set net [get_nets -of_objects [get_pins $cell/$pin]]
            set leaves [get_property NAME [get_pins -leaf -of_objects [get_nets -segments $net]]]
            puts $f "CLOCK_OUTPUT $cell/$pin NET=$net LEAVES=$leaves"
            puts $f "ROUTE [get_property ROUTE $net]"
            if {$cell eq $delay} {
                foreach sink [list $serial/I $byte/I] {
                    if {[lsearch -exact $leaves $sink] < 0} {error "Local clocks do not share the delayed source"}
                }
            } else {
                foreach sampler [get_cells -hier -filter {REF_NAME == ISERDESE2}] {
                    foreach clkpin [expr {$cell eq $serial ? {CLK CLKB} : {CLKDIV}}] {
                        if {[lsearch -exact $leaves $sampler/$clkpin] < 0} {error "Local sampler clock connection mismatch"}
                    }
                }
            }
        }
        puts $f [report_property -all -return_string $byte]
        close $f
        set f [open net_delays.txt w]
        foreach {cell pin} [list clock_input O $delay DATAOUT $serial O $byte O] {
            set net [get_nets -of_objects [get_pins $cell/$pin]]
            puts $f "NET_AT_PIN $cell/$pin $net"
            foreach value [get_net_delays -of_objects $net] {
                puts $f [report_property -all -return_string $value]
            }
        }
        close $f
        set f [open io_properties.txt w]
        foreach port [get_ports dphy_*] {
            puts $f [report_property -all -return_string $port]
            puts $f [report_property -all -return_string [get_package_pins -of_objects $port]]
        }
        close $f
        set byte_clock [get_clocks -of_objects [get_pins $byte/O]]
        foreach corner {Fast Slow} {
            foreach type {max min} {
                report_timing -from $byte_clock -to $byte_clock -corner $corner -delay_type $type \
                    -max_paths 1 -path_type full_clock_expanded -significant_digits 3 \
                    -append -file byte_clock_paths.rpt
            }
        }
    }
    if {$bufg_probe} {
        # Same routed attempt: expose feedback/forward delays and the actual
        # byte load without another implementation or any phase/tap mutation.
        set f [open net_delays.txt w]
        foreach pin {CLKIN1 CLKFBOUT CLKOUT0 CLKOUT1} {
            set net [get_nets -of_objects [get_pins $mmcm/$pin]]
            puts $f "NET_AT_MMCM_PIN $pin $net"
            foreach delay [get_net_delays -of_objects $net] {
                puts $f [report_property -all -return_string $delay]
            }
        }
        foreach cell [get_cells -hier -filter {REF_NAME == BUFG}] {
            puts $f "BUFFER $cell"
            puts $f [report_property -all -return_string $cell]
            set net [get_nets -of_objects [get_pins $cell/O]]
            puts $f "OUTPUT $net SINKS=[get_pins -of_objects $net -filter {DIRECTION == IN}]"
            foreach delay [get_net_delays -of_objects $net] {
                puts $f [report_property -all -return_string $delay]
            }
        }
        close $f
        set f [open io_properties.txt w]
        foreach port [get_ports dphy_*] {
            puts $f [report_property -all -return_string $port]
            puts $f [report_property -all -return_string [get_package_pins -of_objects $port]]
        }
        close $f
        set byte_buffer [get_cells -hier -filter {REF_NAME == BUFG && NAME =~ *byte_buffer}]
        if {[llength $byte_buffer] != 1} {error "Expected one actual byte BUFG"}
        set byte_clock [get_clocks -of_objects [get_pins $byte_buffer/O]]
        foreach corner {Fast Slow} {
            foreach type {max min} {
                report_timing -from $byte_clock -to $byte_clock \
                    -corner $corner -delay_type $type -max_paths 1 -path_type full_clock_expanded \
                    -significant_digits 3 -append -file byte_clock_paths.rpt
            }
        }
    }
    set report sampling_corners.rpt
    set f [open $report w]
    set setting [expr {$local_probe ? "clock_tap=0" : "0/0"}]
    if {$pll_probe} {set setting "serial_phase=-90 byte_phase=-22.5"}
    puts $f "# ${tag}_PROBE_V1 fixed $setting; routed budget only; no functional acceptance"
    close $f
    set requests 0
    foreach cell $samplers {
        if {![regexp {lanes\[([01])\]} $cell -> lane]} {error "Unknown probe lane"}
        foreach pn {p n} {
            set src [get_ports [format {dphy_data_%s[%d]} $pn $lane]]
            foreach corner {Fast Slow} {
                foreach transition {rise fall} {
                    foreach type {max min} {
                        report_timing -from $src -${transition}_to [get_pins $cell/D] \
                            -corner $corner -delay_type $type -max_paths 8 -nworst 8 \
                            -significant_digits 3 -path_type full_clock_expanded -append -file $report
                        incr requests
                    }
                }
            }
        }
    }
    set f [open $report a]; puts $f "# ${tag}_PROBE_COMPLETE requests=$requests"; close $f
    probe_stage BUDGET_REPORTS_COMPLETE
    close_design
    exit 0
} elseif {[llength $argv]} {
    error "Expected explicit --pll-clock-budget, --local-clock-budget, --hpc-budget, --bufg-feedback-budget, --shared-feedback-model-budget or --shared-feedback-model-query; no-argument mode is historical scan"
}

# Lightweight controller simulation before synthesis. Explicit CLI stages
# keep all simulation artifacts under the established generated build path.
set previous_dir [pwd]
cd $build_dir
set bin [file join $::env(XILINX_VIVADO) bin]
exec [file join $bin xvlog.bat] -sv [file join $sim_dir dphy_clock_compensation_ooc.sv] [file join $sim_dir tb_dphy_mmcm_reset_guard.sv] > guard_compile.log 2>@1
exec [file join $bin xelab.bat] tb_dphy_mmcm_reset_guard -s dphy_guard > guard_elaborate.log 2>@1
exec [file join $bin xsim.bat] dphy_guard -runall > guard_simulation.log 2>@1
set guard_log [open guard_simulation.log r]
set guard_text [read $guard_log]
close $guard_log
if {![string match {*PASS: delayed startup*} $guard_text]} { error "Reset guard simulation did not pass; inspect $build_dir/guard_simulation.log" }
puts "DPHY_GUARD_SIM_PASS"
cd $previous_dir

read_vhdl [list [file join $ip_dir DPHY_Pkg.vhd] [file join $ip_dir SyncAsync.vhd] [file join $ip_dir SyncAsyncReset.vhd] [file join $ip_dir HS_Deserializer.vhd]]
read_verilog -sv [file join $sim_dir dphy_clock_compensation_ooc.sv]
synth_design -mode out_of_context -top dphy_clock_compensation_ooc -part xc7z020clg400-2
create_clock -name mipi_hs_clk -period 3.571 [get_ports dphy_clk_p]
create_clock -name ref_clk -period 5.000 [get_ports refclk]
set data_ports [get_ports {dphy_data_p[*] dphy_data_n[*]}]
foreach edge {rise fall} {
    set edge_args {}
    if {$edge eq "fall"} { set edge_args {-clock_fall} }
    set_input_delay -clock mipi_hs_clk {*}$edge_args -min -add_delay 0.268 $data_ports
    set_input_delay -clock mipi_hs_clk {*}$edge_args -max -add_delay 1.518 $data_ports
}
foreach {port pin} {dphy_clk_p Y7 dphy_clk_n Y6 {dphy_data_p[0]} W11 {dphy_data_n[0]} Y11 {dphy_data_p[1]} U9 {dphy_data_n[1]} U8} {
    set_property PACKAGE_PIN $pin [get_ports $port]
}
set_property IOSTANDARD LVDS_25 [get_ports {dphy_clk_p dphy_clk_n dphy_data_p[*] dphy_data_n[*]}]
set_property IODELAY_GROUP DPHY_OOC [get_cells -hier -filter {REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL}]
set_false_path -to [get_pins -hier -regexp {^.*/lock_sync_reg\[0\]/D$}]
set_false_path -to [get_pins -hier -regexp {^.*/oSyncStages_reg\[0\]/D$}]
set_false_path -through [get_pins -hier -regexp {^.*/oSyncStages_reg\[[0-9]+\]/(PRE|CLR)$}]
set_false_path -from [get_ports request_reset]
opt_design
place_design
route_design
report_drc -file [file join $report_dir dphy_clock_ooc_drc.rpt]
report_methodology -file [file join $report_dir dphy_clock_ooc_methodology.rpt]
report_utilization -hierarchical -file [file join $report_dir dphy_clock_ooc_utilization.rpt]
report_timing_summary -delay_type min_max -file [file join $report_dir dphy_clock_ooc_timing.rpt]

set delays [lsort [get_cells -hier -filter {REF_NAME == IDELAYE2}]]
set endpoints [lsort [get_pins -hier -filter {REF_PIN_NAME == DDLY && NAME =~ *sampler/Deserializer/DDLY}]]
set clock_cell [get_cells -hier -filter {REF_NAME == MMCME2_ADV}]
if {[llength $delays] != 2 || [llength $endpoints] != 2 || [llength $clock_cell] != 1} { error "Unexpected OOC sampler/MMCM structure" }
set csv [open [file join $report_dir dphy_clock_ooc_window.csv] w]
puts $csv "serial_phase_degrees,data_taps,lane0_setup,lane0_hold,lane1_setup,lane1_hold"
set feasible 0
set best_margin -Inf
set best_setting {}
for {set phase 0} {$phase < 360} {incr phase 15} {
    set_property CLKOUT0_PHASE $phase $clock_cell
    set_property CLKOUT1_PHASE [expr {$phase / 4.0}] $clock_cell
    for {set taps 0} {$taps <= 31} {incr taps} {
        set_property IDELAY_VALUE $taps $delays
        update_timing
        set slacks {}
        foreach endpoint $endpoints {
            foreach type {max min} {
                set paths [get_timing_paths -quiet -from $data_ports -to $endpoint -delay_type $type -max_paths 1]
                if {[llength $paths] != 1} { error "Missing OOC input $type path to $endpoint" }
                lappend slacks [get_property SLACK [lindex $paths 0]]
            }
        }
        set margin [lindex [lsort -real $slacks] 0]
        if {$margin >= 0.0} { incr feasible }
        if {$margin > $best_margin} { set best_margin $margin; set best_setting [list $phase $taps] }
        puts $csv [join [concat $phase $taps $slacks] ,]
    }
    flush $csv
    puts "DPHY_OOC_WINDOW phase=$phase feasible=$feasible best=$best_margin setting=$best_setting"
}
close $csv
set summary [open [file join $report_dir dphy_clock_ooc_summary.txt] w]
puts $summary "Isolated non-project OOC on xc7z020clg400-2; production sources/project unchanged"
puts $summary "Topology: IBUFDS -> MMCM (M=3,D=1,VCO=840.101 MHz) -> matched serial/byte BUFGs; BUFG feedback"
puts $summary "Input contract: 3.571 ns DDR clock, min=0.268 ns, max=1.518 ns on both edges"
puts $summary "Reset guard behavioral simulation passed; injected lock delay=100 us, reset hold=40 ns"
puts $summary "Sensor source config 0x4800=0x14 requests continuous HS clock; live continuity not measured"
puts $summary "Placed/routed at initial phases 60/15 degrees, data taps=12; what-if phase/tap edits remain in memory"
puts $summary "Sweep: 24 serial phases (15-degree serial-phase increments), matching byte phase/4, 32 data taps; feasible=$feasible"
puts $summary "Best common margin=$best_margin ns; serial phase/data taps=$best_setting"
puts $summary "Boundary: no complete LP/SoT/startup packet simulation, IDELAYCTRL RDY/reset sequencing, analog lock measurement, production CDC signoff, or board operation"
puts $summary "OOC refclk/reset boundary routing is incomplete; their reported timing is not production evidence"
if {$feasible == 0} { puts $summary "REJECTED: this candidate has no tested common sampling window; do not integrate or relax input timing" }
close $summary
puts "DPHY_OOC_COMPLETE feasible=$feasible best=$best_margin setting=$best_setting; experimental only, no production acceptance"
close_design
