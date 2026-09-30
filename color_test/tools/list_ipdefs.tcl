create_project -in_memory -part xc7z020clg400-2
set requested {v_tc axi_vdma axis_subset_converter processing_system7 v_axi4s_vid_out}
foreach name $requested {
    puts "=== $name ==="
    foreach ip [get_ipdefs -all -filter "NAME == $name"] {
        puts "[get_property VLNV $ip]"
    }
}
exit
