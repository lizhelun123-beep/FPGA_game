# AX7Z020B base/core Rev1.0 schematic chain. Plain XDC commands only:
# read_xdc does not execute general Tcl foreach/if control flow.
set_property PACKAGE_PIN U18 [get_ports ref_clk_50]
set_property IOSTANDARD LVCMOS33 [get_ports ref_clk_50]
create_clock -name board50 -period 20.000 [get_ports ref_clk_50]
set_input_jitter board50 0.100
# TMDS P/N pairs: CLK U13/V13, D0 W14/Y14, D1 Y18/Y19, D2 Y16/Y17.
set_property PACKAGE_PIN U13 [get_ports TMDS_clk_p]
set_property PACKAGE_PIN V13 [get_ports TMDS_clk_n]
set_property PACKAGE_PIN W14 [get_ports {TMDS_data_p[0]}]
set_property PACKAGE_PIN Y14 [get_ports {TMDS_data_n[0]}]
set_property PACKAGE_PIN Y18 [get_ports {TMDS_data_p[1]}]
set_property PACKAGE_PIN Y19 [get_ports {TMDS_data_n[1]}]
set_property PACKAGE_PIN Y16 [get_ports {TMDS_data_p[2]}]
set_property PACKAGE_PIN Y17 [get_ports {TMDS_data_n[2]}]
set_property IOSTANDARD TMDS_33 [get_ports {TMDS_clk_p TMDS_clk_n TMDS_data_p[*] TMDS_data_n[*]}]
# All clocks remain related. Vivado derives both MMCMs and BUFR/5 clocks.
# No clock groups, data-path false paths or timing-exception IP XDC are loaded.
# Scoped reset/status exceptions and cardinality checks live in the build Tcl.
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
