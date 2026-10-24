# Complete vendor PHY, fixed-seed family round 2 (section10 is round 1).
# No production project, board access, AUTO mode, scan or bitstream generation.
# --amd-phy-query is a read-only audit of the preserved optimized checkpoint;
# completion records known LP input-buffer failures, not implementation admission.
# Section23 closes this fixed sampling family: the LP IBUF repair adds no
# evidenced HS timing-improvement mechanism. Stop before any IP/tool mutation.
if {$argv in {--amd-phy-config --amd-phy-budget}} {
    error "AMD_RX_FIXED_ROUTE_STOPPED_NO_NEW_TIMING_MECHANISM: generation/budget disabled; see sampling report section23. A distinct mechanism needs evidence review before this stop can be reconsidered."
}
set out [file join $root build dphy_sampling amd_phy_fixed_probe]
file mkdir $out
set_param general.maxThreads 2
set_param synth.maxThreads 2
set ipname amd_fixed_rx

proc amd_stage {out phase value} {
    set f [open [file join $out ${phase}_stage.txt] w]
    puts $f $value
    close $f
    puts "AMD_PHY_STAGE $phase $value"
}

if {$argv eq "--amd-phy-query"} {
    # Read only the preserved Oct19 optimized checkpoint. Never regenerate IP,
    # synthesize, change constraints or continue its failed placement here.
    set audit [file join $out adoption_structure.tsv]
    if {[file exists $audit]} {error "Read-only audit already recorded; preserve evidence"}
    open_checkpoint [file join $out probe_optimized.dcp]
    set amd_audit_file [open $audit w]
    puts $amd_audit_file "kind\tname\tkey\tvalue"
    proc amd_audit_row {kind name key value} {
        global amd_audit_file
        set clean {}
        foreach field [list $kind $name $key $value] {
            lappend clean [string map [list "\t" " " "\n" " " "\r" " "] $field]
        }
        puts $amd_audit_file [join $clean "\t"]
    }
    proc amd_audit_check {name result detail} {
        amd_audit_row CHECK $name [expr {$result ? "PASS" : "FAIL"}] $detail
    }
    proc amd_audit_connected {a b} {
        set an [get_nets -quiet -segments -of_objects $a]
        set bn [get_nets -quiet -segments -of_objects $b]
        foreach n $an {if {$n in $bn} {return 1}}
        return 0
    }
    proc amd_audit_drivers {pin} {
        set nets [get_nets -quiet -segments -of_objects $pin]
        return [get_pins -quiet -of_objects $nets -filter {DIRECTION == OUT}]
    }
    proc amd_audit_const {pin} {
        set cells [get_cells -quiet -of_objects [amd_audit_drivers $pin]]
        set refs [lsort -unique [get_property REF_NAME $cells]]
        if {$refs eq "VCC"} {return 1}
        if {$refs eq "GND"} {return 0}
        return "DYNAMIC:$refs"
    }
    amd_audit_row IDENTITY checkpoint part [get_property PART [current_design]]
    amd_audit_row IDENTITY checkpoint stage HISTORICAL_OPTIMIZED_UNPLACED
    foreach {ref expected} {IBUFDS 3 IDELAYE2 2 IDELAYCTRL 1 ISERDESE2 2 BUFIO 1 BUFR 1} {
        set cells [get_cells -quiet -hier -filter "REF_NAME == $ref"]
        amd_audit_check count_$ref [expr {[llength $cells] == $expected}] "actual=[llength $cells] expected=$expected"
    }
    set cmt [get_cells -quiet -hier -filter {REF_NAME =~ MMCME* || REF_NAME =~ PLLE*}]
    amd_audit_check no_CMT [expr {![llength $cmt]}] $cmt
    set boxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
    amd_audit_check no_blackbox [expr {![llength $boxes]}] $boxes

    foreach {name pin standard} {
        dphy_clk_p Y7 LVDS_25 dphy_clk_n Y6 LVDS_25
        dphy_data_p[0] W11 LVDS_25 dphy_data_n[0] Y11 LVDS_25
        dphy_data_p[1] U9 LVDS_25 dphy_data_n[1] U8 LVDS_25
        dphy_clk_lp_p V8 HSUL_12 dphy_clk_lp_n W8 HSUL_12
        dphy_data_lp_p[0] T9 HSUL_12 dphy_data_lp_n[0] U10 HSUL_12
        dphy_data_lp_p[1] Y12 HSUL_12 dphy_data_lp_n[1] Y13 HSUL_12
    } {
        set port [get_ports $name]
        set actual_pin [get_property PACKAGE_PIN $port]
        set actual_standard [get_property IOSTANDARD $port]
        set package_pin [get_package_pins $actual_pin]
        set bank [get_property BANK $package_pin]
        amd_audit_check pin_$name [expr {$actual_pin eq $pin && $actual_standard eq $standard && $bank == 13}] \
            "PACKAGE_PIN=$actual_pin IOSTANDARD=$actual_standard BANK=$bank"
        foreach prop {PIN_FUNC DIFF_PAIR_PIN DIFF_PAIR_TYPE} {
            if {$prop in [list_property $package_pin]} {
                amd_audit_row PACKAGE $name $prop [get_property $prop $package_pin]
            }
        }
    }
    amd_audit_row BANK 13 INTERNAL_VREF [get_property INTERNAL_VREF [get_iobanks 13]]

    set primitives [get_cells -quiet -hier -filter {REF_NAME == IBUFDS || REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL || REF_NAME == ISERDESE2 || REF_NAME == BUFIO || REF_NAME == BUFR}]
    foreach cell [lsort $primitives] {
        amd_audit_row CELL $cell REF_NAME [get_property REF_NAME $cell]
        foreach prop {IOSTANDARD DIFF_TERM IBUF_LOW_PWR IDELAY_TYPE IDELAY_VALUE DELAY_SRC HIGH_PERFORMANCE_MODE REFCLK_FREQUENCY SIGNAL_PATTERN IODELAY_GROUP DATA_RATE DATA_WIDTH INTERFACE_TYPE IOBDELAY NUM_CE BUFR_DIVIDE IS_CLK_INVERTED IS_CLKB_INVERTED} {
            if {$prop in [list_property $cell]} {
                amd_audit_row PROPERTY $cell $prop [get_property $prop $cell]
            }
        }
        foreach pin [get_pins -of_objects $cell] {
            amd_audit_row NET $cell [get_property REF_PIN_NAME $pin] [get_nets -quiet -segments -of_objects $pin]
        }
    }
    set clock_buffer {}
    foreach cell [get_cells -quiet -hier -filter {REF_NAME == IBUFDS}] {
        amd_audit_check external_termination_$cell [expr {![get_property DIFF_TERM $cell]}] "DIFF_TERM=[get_property DIFF_TERM $cell]"
        if {[amd_audit_connected [get_ports dphy_clk_p] [get_pins $cell/I]]} {
            set clock_buffer $cell
            amd_audit_check clock_pn [amd_audit_connected [get_ports dphy_clk_n] [get_pins $cell/IB]] $cell
        }
    }
    set io [get_cells -hier -filter {REF_NAME == BUFIO}]
    set div [get_cells -hier -filter {REF_NAME == BUFR}]
    amd_audit_check direct_clock_to_BUFIO [amd_audit_connected [get_pins $clock_buffer/O] [get_pins $io/I]] $clock_buffer
    amd_audit_check direct_clock_to_BUFR [amd_audit_connected [get_pins $clock_buffer/O] [get_pins $div/I]] $clock_buffer
    amd_audit_check byte_divide4 [expr {[get_property BUFR_DIVIDE $div] eq "4"}] $div

    foreach cell [get_cells -hier -filter {REF_NAME == IDELAYE2}] {
        set lane -1
        foreach index {0 1} {
            foreach buffer [get_cells -hier -filter {REF_NAME == IBUFDS}] {
                if {[amd_audit_connected [get_ports [format {dphy_data_p[%d]} $index]] [get_pins $buffer/I]] &&
                    [amd_audit_connected [get_pins $buffer/O] [get_pins $cell/IDATAIN]]} {
                    set lane $index
                    amd_audit_check data${index}_pn [amd_audit_connected [get_ports [format {dphy_data_n[%d]} $index]] [get_pins $buffer/IB]] $buffer
                }
            }
        }
        amd_audit_check data_lane_identity_$cell [expr {$lane in {0 1}}] "lane=$lane"
        amd_audit_check seed_$cell [expr {[get_property IDELAY_VALUE $cell] == 1 && [get_property IDELAY_TYPE $cell] eq "VAR_LOAD"}] $cell
        foreach {pin expected} {CE 0 INC 0 LD 1 CNTVALUEIN[0] 1 CNTVALUEIN[1] 0 CNTVALUEIN[2] 0 CNTVALUEIN[3] 0 CNTVALUEIN[4] 0} {
            set actual [amd_audit_const [get_pins $cell/$pin]]
            amd_audit_check fixed_${pin}_$cell [expr {$actual eq $expected}] "actual=$actual expected=$expected"
        }
        set matched 0
        foreach sampler [get_cells -hier -filter {REF_NAME == ISERDESE2}] {
            if {![amd_audit_connected [get_pins $cell/DATAOUT] [get_pins $sampler/DDLY]]} {continue}
            incr matched
            amd_audit_row LANE $lane SAMPLER $sampler
            amd_audit_check sampler_mode_$sampler [expr {[get_property IOBDELAY $sampler] eq "BOTH" && [get_property DATA_WIDTH $sampler] == 8 && [get_property DATA_RATE $sampler] eq "DDR" && [get_property INTERFACE_TYPE $sampler] eq "NETWORKING"}] $sampler
            amd_audit_check serial_clock_$sampler [amd_audit_connected [get_pins $io/O] [get_pins $sampler/CLK]] $sampler
            amd_audit_check byte_clock_$sampler [amd_audit_connected [get_pins $div/O] [get_pins $sampler/CLKDIV]] $sampler
        }
        amd_audit_check one_sampler_$cell [expr {$matched == 1}] "count=$matched"
    }
    set ctrl [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]
    set rdy_endpoints [all_fanout -flat -endpoints_only -from [get_pins $ctrl/RDY]]
    amd_audit_check real_RDY_connected [expr {[llength $rdy_endpoints] > 1}] $rdy_endpoints
    amd_audit_row RDY $ctrl endpoints $rdy_endpoints
    set ref [get_clocks -of_objects [get_pins $ctrl/REFCLK]]
    amd_audit_check reference_200MHz [expr {[llength $ref] == 1 && [get_property PERIOD $ref] == 5.0}] $ref

    foreach name {dphy_clk_lp_p dphy_clk_lp_n dphy_data_lp_p[0] dphy_data_lp_n[0] dphy_data_lp_p[1] dphy_data_lp_n[1]} {
        set port [get_ports $name]
        set endpoints [all_fanout -flat -endpoints_only -from $port]
        amd_audit_check LP_live_$name [expr {[llength $endpoints] > 0}] $endpoints
        set buffered 0
        foreach cell [get_cells -quiet -hier -filter {REF_NAME == IBUF}] {
            if {[amd_audit_connected $port [get_pins $cell/I]]} {set buffered 1}
        }
        amd_audit_check LP_input_buffer_$name $buffered "Historical OOC wrapper has no explicit IBUF; placement already failed Place30-188"
    }
    foreach clock [get_clocks] {
        foreach prop {PERIOD WAVEFORM IS_GENERATED MASTER_CLOCK SOURCE_PINS DIVIDE_BY} {
            if {$prop in [list_property $clock]} {amd_audit_row CLOCK $clock $prop [get_property $prop $clock]}
        }
    }
    set hs [get_clocks -of_objects [get_ports dphy_clk_p]]
    amd_audit_check HS_period [expr {[llength $hs] == 1 && [get_property PERIOD $hs] == 3.571}] $hs
    close $amd_audit_file
    close_design
    puts "AMD_PHY_READ_ONLY_STRUCTURE_COMPLETE; LP IBUF failures retained; no new synth/opt/place/route/budget"
    return
}

if {$argv eq "--amd-phy-config"} {
    set receipt [file join $out config_stage.txt]
    if {[file exists $receipt]} {
        # One pre-generation directory-precondition correction, never a second
        # IP setting/design attempt. Original log/source are retained separately.
        set prior [open $receipt r]
        set value [string trim [read $prior]]
        close $prior
        if {$value ne "STARTED_FAMILY_ROUND2" ||
            ![file exists [file join $out config_precondition_failure.json]] ||
            [file exists [file join $out config_precondition_resume_used.txt]] ||
            [file exists [file join $out ip $ipname $ipname.xci]]} {
            error "Configuration already attempted; preserve evidence"
        }
        set used [open [file join $out config_precondition_resume_used.txt] w]
        puts $used "One correction: create missing IP output directory; same fixed seed, family round2"
        close $used
    }
    amd_stage $out config STARTED_FAMILY_ROUND2
    create_project -in_memory -part xc7z020clg400-2
    file mkdir [file join $out ip]
    create_ip -name mipi_dphy -vendor xilinx.com -library ip -version 4.3 \
        -module_name $ipname -dir [file join $out ip]
    set core [get_ips $ipname]
    set settings [list \
        CONFIG.C_DPHY_MODE SLAVE CONFIG.C_DPHY_LANES 2 \
        CONFIG.C_HS_LINE_RATE 560 CONFIG.C_CAL_MODE FIXED CONFIG.C_IDLY_TAP 1 \
        CONFIG.C_EN_EXT_TAP false CONFIG.C_SHARE_IDLYCTRL false \
        CONFIG.C_EN_CLK300M false CONFIG.C_EN_REG_IF false \
        CONFIG.C_INIT 100000 CONFIG.C_HS_SETTLE_NS 152 \
        CONFIG.C_STABLE_CLK_PERIOD 200.000 CONFIG.DPHY_PRESET None \
        CONFIG.C_EN_TXSPLT false CONFIG.C_RCVE_DESKEW_SEQ false \
        CONFIG.C_RCVE_ALT_DESKEW_SEQ false CONFIG.C_EN_CNTS_BYTE_CLK false]
    set_property -dict $settings $core
    set f [open [file join $out requested_and_actual_config.txt] w]
    puts $f "PART [get_property PART [current_project]]"
    puts $f "IPDEF [get_property IPDEF $core]"
    foreach {name expected} $settings {
        set actual [get_property $name $core]
        puts $f "$name expected=$expected actual=$actual"
        if {$actual ne $expected && !([string is double -strict $actual] &&
            [string is double -strict $expected] && $actual == $expected)} {
            close $f
            error "Exact fixed configuration mismatch: $name"
        }
    }
    close $f
    report_property -all $core -file [file join $out configured_properties.txt]
    generate_target all $core
    report_ip_status -file [file join $out ip_status.rpt]
    set f [open [file join $out generated_files.txt] w]
    foreach item [get_files -all] {puts $f [get_property NAME $item]}
    close $f
    amd_stage $out config GENERATED_PENDING_TEXT_CONSTRAINT_AUDIT
    close_project
    return
}

if {$argv ne "--amd-phy-budget"} {error "No saved AMD query was requested/needed"}
if {![file exists [file join $out config_admission.json]]} {
    error "Exact generated configuration/constraint audit must admit this seed first"
}
if {[file exists [file join $out budget_stage.txt]]} {
    error "One fixed budget already attempted; do not restart family round2"
}
amd_stage $out budget STARTED_FAMILY_ROUND2_ONE_FIXED_SEED
set phy [file join $out ip $ipname]
read_verilog -sv [file join $phy hdl mipi_dphy_v4_3_vl_rfs.sv]
foreach file [list $ipname.v ${ipname}_core.v ${ipname}_c1.v \
    [file join $ipname support ${ipname}_support.v]] {
    read_verilog [file join $phy $file]
}
read_verilog -sv [file join $sim_dir dphy_clock_compensation_ooc.sv]
# Deliberately read generated HDL, NOT read_ip: no generated clock/CDC waiver
# files are automatically applied. All original generated files are preserved.
synth_design -mode out_of_context -top dphy_amd_phy_fixed_ooc \
    -part xc7z020clg400-2 -flatten_hierarchy rebuilt
amd_stage $out budget SYNTHESIZED
if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} {
    error "Unresolved vendor core is not an admissible timing probe"
}
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
set_property IODELAY_GROUP DPHY_AMD_FIXED_BUDGET \
    [get_cells -hier -filter {REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL}]
opt_design
set samplers [get_cells -hier -filter {REF_NAME == ISERDESE2}]
set delays [get_cells -hier -filter {REF_NAME == IDELAYE2}]
if {[llength $samplers] != 2 || [llength $delays] != 2 ||
    [llength [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]] != 1 ||
    [llength [get_cells -quiet -hier -filter {REF_NAME =~ MMCME* || REF_NAME =~ PLLE*}]] ||
    [llength [get_cells -hier -filter {REF_NAME == BUFIO}]] != 1 ||
    [llength [get_cells -hier -filter {REF_NAME == BUFR}]] != 1 ||
    [llength [get_cells -hier -filter {REF_NAME == IBUFDS}]] != 3} {
    error "Vendor fixed-clock/data-delay structure must match the admitted family"
}
set f [open [file join $out primitive_connections.txt] w]
foreach c [lsort [get_cells -hier -filter {REF_NAME =~ IBUF* || REF_NAME =~ BUF* || REF_NAME == IDELAYE2 || REF_NAME == IDELAYCTRL || REF_NAME == ISERDESE2}]] {
    puts $f "CELL $c [get_property REF_NAME $c]"
    set props [list_property $c]
    foreach p {IOSTANDARD DIFF_TERM IBUF_LOW_PWR IDELAY_TYPE IDELAY_VALUE DELAY_SRC HIGH_PERFORMANCE_MODE REFCLK_FREQUENCY SIGNAL_PATTERN DATA_RATE DATA_WIDTH INTERFACE_TYPE IOBDELAY SERDES_MODE NUM_CE BUFR_DIVIDE IS_CLK_INVERTED IS_CLKB_INVERTED IS_CLKDIV_INVERTED} {
        if {$p in $props} {puts $f "  $p=[get_property $p $c]"}
    }
    foreach pin [get_pins -of_objects $c] {
        puts $f "  PIN [get_property REF_PIN_NAME $pin] NET [get_nets -of_objects $pin]"
    }
}
close $f
foreach c $delays {
    if {[get_property IDELAY_VALUE $c] != 1} {error "Not fixed tap1"}
}
foreach c [get_cells -hier -filter {REF_NAME == IBUFDS}] {
    if {[get_property DIFF_TERM $c]} {error "Internal termination incompatible with admitted Bank13 supply"}
}
foreach c $samplers {
    if {[get_property IOBDELAY $c] ni {IFD BOTH} ||
        [get_property DATA_WIDTH $c] != 8 || [get_property INTERFACE_TYPE $c] ne "NETWORKING"} {
        error "Unexpected vendor sampler interface"
    }
}
# Native vendor LP is sampled by real fabric synchronizers at core_clk, not
# four canonical LP ISERDES. Keep all four LP data inputs and both clock-LP
# inputs connected into the full vendor PCS; do not add dummy SERDES loads.
foreach port [get_ports {dphy_data_lp_p[*] dphy_data_lp_n[*] dphy_clk_lp_p dphy_clk_lp_n}] {
    if {![llength [all_fanout -flat -endpoints_only -from $port]]} {
        error "LP input optimized away: $port"
    }
}
write_checkpoint [file join $out probe_optimized.dcp]
write_xdc -force [file join $out effective_constraints.xdc]
report_clocks -file [file join $out clocks_optimized.rpt]
amd_stage $out budget OPTIMIZED_PRIMITIVE_ADMISSION_PASS
place_design
write_checkpoint [file join $out probe_placed.dcp]
amd_stage $out budget PLACED
route_design
amd_stage $out budget ROUTED
write_checkpoint [file join $out probe_routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_clocks -file [file join $out clocks.rpt]
report_timing_summary -report_unconstrained -max_paths 8 -file [file join $out timing.rpt]
report_utilization -hierarchical -file [file join $out utilization_hierarchical.rpt]
report_utilization -file [file join $out utilization_placed.rpt]
report_drc -file [file join $out drc.rpt]
report_cdc -details -file [file join $out cdc.rpt]
report_exceptions -file [file join $out exceptions.rpt]
set f [open [file join $out io_properties.txt] w]
foreach port [get_ports {dphy_clk_p dphy_clk_n dphy_data_p[*] dphy_data_n[*] dphy_clk_lp_p dphy_clk_lp_n dphy_data_lp_p[*] dphy_data_lp_n[*]}] {
    puts $f [report_property -all -return_string $port]
}
close $f
set report [file join $out sampling_corners.rpt]
set f [open $report w]
puts $f "# AMD_PHY_FIXED_PROBE_V1 fixed data_tap=1; family round2; own routed paths"
close $f
set requests 0
foreach cell $samplers {
    if {![regexp {dl([01])_.*iserdese2_master$} $cell -> lane]} {
        error "Unrecognized vendor HS sampler lane: $cell"
    }
    foreach pn {p n} {
        set src [get_ports [format {dphy_data_%s[%d]} $pn $lane]]
        foreach corner {Fast Slow} {
            foreach transition {rise fall} {
                foreach type {max min} {
                    report_timing -from $src -${transition}_to [get_pins $cell/DDLY] \
                        -corner $corner -delay_type $type -max_paths 8 -nworst 8 \
                        -significant_digits 3 -path_type full_clock_expanded -append -file $report
                    incr requests
                }
            }
        }
    }
}
set f [open $report a]
puts $f "# AMD_PHY_FIXED_PROBE_COMPLETE requests=$requests"
close $f
if {$requests != 32} {error "Incomplete fixed budget path queries"}
amd_stage $out budget BUDGET_REPORTS_COMPLETE
close_design
