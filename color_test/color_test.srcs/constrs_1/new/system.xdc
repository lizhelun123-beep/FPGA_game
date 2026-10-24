# Measured fixed93.333Mb/s configuration:3035=61,4837=6c.
# Same declared15%/85%UI input model as the qualified fixed-rate OOC.
# No claim of physical-reference tolerance/full-PVT sensor guarantee.
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
create_clock -name mipi_hs_clk -period 21.428571429 -waveform {0 10.714285714} [get_ports dphy_hs_clock_clk_p]
set_input_delay -clock mipi_hs_clk -min -add_delay 1.607142 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -max -add_delay 9.107143 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -min -add_delay 1.607142 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -max -add_delay 9.107143 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
