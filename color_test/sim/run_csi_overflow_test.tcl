# Behavioral test of the production CSI-2 core's backpressure overflow latch.
set sim_dir [file normalize [file join [file dirname [info script]] .. build csi_overflow_sim]]
set ip_dir [file normalize [file join [file dirname [info script]] .. repo ip MIPI_CSI_2_RX]]

create_project csi_overflow_sim $sim_dir -part xc7z020clg400-2 -force
set_property target_language VHDL [current_project]
set_property simulator_language Mixed [current_project]

add_files -norecurse [list \
    [file join $ip_dir tb fifo_models.vhd] \
    [file join $ip_dir hdl DebugLib.vhd] \
    [file join $ip_dir hdl SyncAsync.vhd] \
    [file join $ip_dir hdl SyncAsyncReset.vhd] \
    [file join $ip_dir hdl SimpleFIFO.vhd] \
    [file join $ip_dir hdl ECC.vhd] \
    [file join $ip_dir hdl CRC16_behavioral.vhd] \
    [file join $ip_dir hdl LM.vhd] \
    [file join $ip_dir hdl LLP.vhd] \
    [file join $ip_dir hdl MIPI_CSI2_Rx.vhd] \
    [file join $ip_dir tb tb_MIPI_CSI2.vhd]]

set_property top tb_MIPI_CSI2 [get_filesets sim_1]
update_compile_order -fileset sim_1
launch_simulation -simset sim_1 -mode behavioral
run 1 ms
close_sim
close_project
