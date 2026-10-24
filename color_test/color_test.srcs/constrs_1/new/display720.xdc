# Same MMCM/BUFIO/BUFR hardware, two existing DRP states, one implementation.
# Assertions belong in fixed_display.tcl, not in this XDC.
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
# Retain native MMCM/BUFR auto-derived clocks and their edge propagation.
# fixed_display.tcl checks startup and runtime in separate timing contexts
# of the SAME checkpoint. Runtime MMCM attributes are analysis-only; restore
# startup attributes/constraints before any checkpoint or artifact operation.
# Raw MMCM LOCKED has no STA launch clock. The old bridge-CLR exception
# covered zero valid paths (native report: Non-existent path); omit it.
# Check the exact two async-assert/sync-release stages structurally instead.
# In particular, shared lock_sync[1] -> registered READY CLR stays timed.

# Retained camera control only; no D-PHY receivers, VREF or input-delay model.
set_property -dict {PACKAGE_PIN U7 IOSTANDARD LVCMOS33 PULLUP true} [get_ports {cam_gpio_tri_io[0]}]
set_property -dict {PACKAGE_PIN T5 IOSTANDARD LVCMOS33 PULLUP true} [get_ports cam_i2c_scl_io]
set_property -dict {PACKAGE_PIN U5 IOSTANDARD LVCMOS33 PULLUP true} [get_ports cam_i2c_sda_io]
