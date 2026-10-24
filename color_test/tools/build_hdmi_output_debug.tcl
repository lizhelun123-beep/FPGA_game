# Build a standalone HDMI-output diagnostic bitstream from the current
# post-opt implementation checkpoint.  This deliberately does not modify the
# block design, project sources, or the stable build/hw programming artifacts.

set project_dir [file normalize [file join [file dirname [info script]] ..]]
set input_dcp [file join $project_dir color_test.runs impl_1 system_wrapper_opt.dcp]
set output_dir [file join $project_dir build hdmi_output_debug]

if {![file exists $input_dcp]} {
    error "Missing implementation checkpoint: $input_dcp"
}
file mkdir $output_dir

proc require_cell {cell_name} {
    set cell [get_cells -quiet $cell_name]
    if {[llength $cell] != 1} {
        error "Expected one cell named $cell_name, found [llength $cell]"
    }
    return $cell
}

proc net_from_pin {cell_name pin_name} {
    set full_pin [format "%s/%s" $cell_name $pin_name]
    set pin [get_pins -quiet $full_pin]
    if {[llength $pin] != 1} {
        error "Expected one pin named $full_pin, found [llength $pin]"
    }
    set net [get_nets -quiet -of_objects $pin]
    if {[llength $net] != 1} {
        error "Expected one net on $full_pin, found [llength $net]"
    }
    return $net
}

proc nets_from_bus {cell_name pin_base width} {
    set nets {}
    for {set bit 0} {$bit < $width} {incr bit} {
        set pin_name [format {%s[%d]} $pin_base $bit]
        lappend nets [net_from_pin $cell_name $pin_name]
    }
    return $nets
}

proc add_ila_probe {core_name probe_index width nets} {
    if {[llength $nets] != $width} {
        error "$core_name/probe$probe_index width is $width but [llength $nets] nets were supplied"
    }
    if {$probe_index > 0} {
        create_debug_port $core_name probe
    }
    set port [get_debug_ports ${core_name}/probe${probe_index}]
    set_property PORT_WIDTH $width $port
    connect_debug_port $port $nets
}

open_checkpoint $input_dcp

set vdma_cell system_i/axi_vdma_0
set video_cell system_i/v_axi4s_vid_out_0
set dynclk_cell system_i/axi_dynclk_0
set rgb2dvi_cell system_i/rgb2dvi_0
foreach cell_name [list $vdma_cell $video_cell $dynclk_cell $rgb2dvi_cell] {
    require_cell $cell_name
}

# AXI4-Stream monitor.  Trigger on tuser && tvalid && tready in Hardware
# Manager to capture the first active line of a frame.
set axis_core hdmi_axis_ila
create_debug_core $axis_core ila
set_property C_DATA_DEPTH 4096 [get_debug_cores $axis_core]
set_property C_INPUT_PIPE_STAGES 1 [get_debug_cores $axis_core]
connect_debug_port ${axis_core}/clk [net_from_pin $vdma_cell m_axis_mm2s_aclk]
add_ila_probe $axis_core 0 24 [nets_from_bus $vdma_cell m_axis_mm2s_tdata 24]
add_ila_probe $axis_core 1 1 [list [net_from_pin $vdma_cell m_axis_mm2s_tvalid]]
add_ila_probe $axis_core 2 1 [list [net_from_pin $vdma_cell m_axis_mm2s_tready]]
add_ila_probe $axis_core 3 1 [list [net_from_pin $vdma_cell {m_axis_mm2s_tuser[0]}]]
add_ila_probe $axis_core 4 1 [list [net_from_pin $vdma_cell m_axis_mm2s_tlast]]

# Parallel-video monitor at the RGB2DVI input.  Trigger on vid_active_video's
# rising edge to capture a complete 1280-pixel active line plus blanking.
set video_core hdmi_video_ila
create_debug_core $video_core ila
set_property C_DATA_DEPTH 4096 [get_debug_cores $video_core]
set_property C_INPUT_PIPE_STAGES 1 [get_debug_cores $video_core]
connect_debug_port ${video_core}/clk [net_from_pin $dynclk_cell PXL_CLK_O]
add_ila_probe $video_core 0 24 [nets_from_bus $video_cell vid_data 24]
add_ila_probe $video_core 1 1 [list [net_from_pin $video_cell vid_active_video]]
add_ila_probe $video_core 2 1 [list [net_from_pin $video_cell vid_hsync]]
add_ila_probe $video_core 3 1 [list [net_from_pin $video_cell vid_vsync]]
# The original block design leaves locked/underflow/overflow and the output
# blanking pins unconnected, so synthesis removes them. Compare the connected
# VTC timing inputs with the RGB2DVI-facing outputs instead.
add_ila_probe $video_core 4 1 [list [net_from_pin $video_cell vtg_active_video]]
add_ila_probe $video_core 5 1 [list [net_from_pin $video_cell vtg_hsync]]
add_ila_probe $video_core 6 1 [list [net_from_pin $video_cell vtg_vsync]]
add_ila_probe $video_core 7 1 [list [net_from_pin $dynclk_cell LOCKED_O]]

puts "HDMI_DEBUG axis_clock=[net_from_pin $vdma_cell m_axis_mm2s_aclk]"
puts "HDMI_DEBUG video_clock=[net_from_pin $dynclk_cell PXL_CLK_O]"
puts "HDMI_DEBUG rgb_reset=[net_from_pin $rgb2dvi_cell aRst_n]"

implement_debug_core
place_design
phys_opt_design
route_design

set output_base [file join $output_dir system_wrapper_hdmi_debug]
write_checkpoint -force ${output_base}_routed.dcp
write_debug_probes -force ${output_base}.ltx
write_bitstream -force ${output_base}.bit
report_utilization -file [file join $output_dir post_impl_utilization.rpt]
report_timing_summary -file [file join $output_dir post_impl_timing.rpt]
report_drc -file [file join $output_dir post_impl_drc.rpt]

foreach required [list ${output_base}.bit ${output_base}.ltx ${output_base}_routed.dcp] {
    if {![file exists $required]} {
        error "HDMI debug build completed but artifact is missing: $required"
    }
}

puts "HDMI_DEBUG_BUILD BIT=${output_base}.bit"
puts "HDMI_DEBUG_BUILD LTX=${output_base}.ltx"
puts "HDMI_DEBUG_BUILD DCP=${output_base}_routed.dcp"
puts "HDMI_DEBUG_BUILD COMPLETE"
close_design
