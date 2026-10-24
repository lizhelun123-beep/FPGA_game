set script_dir [file dirname [file normalize [info script]]]
set project_dir [file normalize [file join $script_dir ..]]
set probes_file [file join $project_dir build hw system_wrapper.ltx]
set csv_file [file join $project_dir build hw csi_ila_capture.csv]

open_hw_manager
connect_hw_server -url 127.0.0.1:3121
open_hw_target
set device [lindex [get_hw_devices -filter {PART == "xc7z020"}] 0]
if {$device eq ""} {
    error "xc7z020 hardware device not found"
}
set_property PROBES.FILE $probes_file $device
set_property FULL_PROBES.FILE $probes_file $device
refresh_hw_device $device
set ila [lindex [get_hw_ilas -of_objects $device -filter {CELL_NAME =~ "*ILAVidClk*"}] 0]
if {$ila eq ""} {
    error "CSI video-clock ILA not found"
}
puts "CSI_ILA [get_property CELL_NAME $ila]"
set trigger_probe [lindex [get_hw_probes -of_objects $ila -filter {NAME =~ "*mFmt_Tlast*"}] 0]
set_property CONTROL.TRIGGER_POSITION 1024 $ila
set_property TRIGGER_COMPARE_VALUE eq1'b1 $trigger_probe
run_hw_ila $ila
wait_on_hw_ila $ila
set data [upload_hw_ila_data $ila]
write_hw_ila_data -force -csv_file $csv_file $data
puts "CSI_ILA_CSV $csv_file"
close_hw_manager
