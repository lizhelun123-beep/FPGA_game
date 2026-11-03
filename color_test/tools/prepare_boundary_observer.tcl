# User-run preparation of the passive CSI1.3 boundary observer in the existing BD.
# No synthesis/implementation, hardware connection, download, BOOT or export.
# Optional --generate refreshes BD output products only, after validation/save.
# Do not run the historical camera_production.tcl prepare stage afterwards: its
# build1..5 contract deliberately restores CSI1.2 and cannot qualify this change.

namespace eval boundary_prepare {
    proc one {objects label} {
        if {[llength $objects] != 1} {error "Expected one $label: $objects"}
        return [lindex $objects 0]
    }

    proc pin {name} {
        return [one [get_bd_pins -quiet $name] "BD pin $name"]
    }

    proc width {object} {
        set left [get_property -quiet LEFT $object]
        set right [get_property -quiet RIGHT $object]
        if {$left eq "" && $right eq ""} {return 1}
        if {![string is integer -strict $left] || ![string is integer -strict $right]} {
            error "Unknown pin width: $object LEFT=$left RIGHT=$right"
        }
        return [expr {abs($left - $right) + 1}]
    }

    proc net {object} {
        return [one [get_bd_nets -quiet -of_objects $object] "connected net for $object"]
    }

    proc require_same_clock {} {
        set source [pin MIPI_CSI_2_RX_0/video_aclk]
        set consumer [pin axi_vdma_1/s_axis_s2mm_aclk]
        if {[net $source] ne [net $consumer]} {
            error "Observer taps cross clock domains; CSI video and S2MM stream clocks must share one net"
        }
    }

    proc tap {source_name destination_name expected_width} {
        set source [pin $source_name]
        set destination [pin $destination_name]
        if {[width $source] != $expected_width || [width $destination] != $expected_width} {
            error "Observer tap width differs: $source_name -> $destination_name"
        }
        if {[get_property DIR $destination] ne "I"} {
            error "Observer pin is not a passive input: $destination_name"
        }
        set source_nets [get_bd_nets -quiet -of_objects $source]
        set destination_nets [get_bd_nets -quiet -of_objects $destination]
        if {[llength $destination_nets]} {
            if {[llength $source_nets] != 1 || $destination_nets ne $source_nets} {
                error "Observer pin already connected to another net: $destination_name"
            }
        } elseif {[llength $source_nets] == 1} {
            connect_bd_net -net [lindex $source_nets 0] $destination
        } elseif {[llength $source_nets] == 0} {
            # Interface-associated scalar pins are materialized by this fanout.
            # The AXIS interface itself remains attached to its original sink.
            connect_bd_net $source $destination
        } else {
            error "Ambiguous tap source nets for $source_name: $source_nets"
        }
        if {[net $source] ne [net $destination]} {
            error "Observer tap did not bind to the actual S2MM pin: $destination_name"
        }
        puts "BOUNDARY_OBSERVER_TAP $source_name -> $destination_name"
    }
}

set boundary_generate 0
if {[info exists argv]} {
    foreach argument $argv {
        if {$argument eq "--generate"} {
            set boundary_generate 1
        } else {
            error "Unsupported preparation option: $argument (only --generate is accepted)"
        }
    }
}
set boundary_root [file normalize [file join [file dirname [info script]] ..]]
set boundary_core_file [file join $boundary_root repo ip MIPI_CSI_2_RX component.xml]
foreach boundary_source {AxisBoundaryProbe.vhd CsiBoundaryObserver.vhd} {
    if {![file isfile [file join $boundary_root repo ip MIPI_CSI_2_RX hdl $boundary_source]]} {
        error "Missing observer source: $boundary_source"
    }
}

set boundary_opened_here 0
if {[llength [current_project -quiet]] == 0} {
    open_project [file join $boundary_root color_test.xpr]
    set boundary_opened_here 1
}
if {[get_property PART [current_project]] ne "xc7z020clg400-2" ||
    [file normalize [get_property DIRECTORY [current_project]]] ne $boundary_root} {
    error "Preparation requires the canonical color_test project and xc7z020clg400-2"
}

# Refresh this edited package's checksums before rebuilding the catalog. Never
# rewrite a prior BIT/HWH/XSA, build gate or boot manifest to bless the new RTL.
set boundary_core [ipx::open_core -set_current false $boundary_core_file]
if {[get_property VERSION $boundary_core] ne "1.3"} {
    ipx::unload_core $boundary_core
    error "The passive observer requires CSI package version1.3"
}
ipx::update_checksums $boundary_core
ipx::save_core $boundary_core
ipx::unload_core $boundary_core
set boundary_repos [get_property ip_repo_paths [current_project]]
set boundary_repo [file join $boundary_root repo ip]
if {[lsearch -exact $boundary_repos $boundary_repo] < 0} {lappend boundary_repos $boundary_repo}
set_property ip_repo_paths $boundary_repos [current_project]
update_ip_catalog -rebuild
boundary_prepare::one [get_ipdefs -all -quiet digilentinc.com:ip:MIPI_CSI_2_RX:1.3] "CSI1.3 catalog definition"

set boundary_bd [boundary_prepare::one [get_files -quiet */system.bd] system.bd]
open_bd_design $boundary_bd
set boundary_csi [boundary_prepare::one [get_bd_cells -quiet MIPI_CSI_2_RX_0] CSI cell]
if {[get_property VLNV $boundary_csi] ni {
    digilentinc.com:ip:MIPI_CSI_2_RX:1.2 digilentinc.com:ip:MIPI_CSI_2_RX:1.3
}} {error "Unreviewed CSI baseline: [get_property VLNV $boundary_csi]"}
set boundary_ip_name "[get_property NAME [current_bd_design]]_MIPI_CSI_2_RX_0_0"
set boundary_ip [boundary_prepare::one [get_ips -quiet $boundary_ip_name] "CSI IP $boundary_ip_name"]
if {[get_property VLNV $boundary_csi] ne "digilentinc.com:ip:MIPI_CSI_2_RX:1.3" ||
    [llength [get_bd_pins -quiet MIPI_CSI_2_RX_0/ObserveVdmaValid]] != 1} {
    upgrade_ip -vlnv digilentinc.com:ip:MIPI_CSI_2_RX:1.3 $boundary_ip
}
set boundary_csi [get_bd_cells MIPI_CSI_2_RX_0]
if {[get_property VLNV $boundary_csi] ne "digilentinc.com:ip:MIPI_CSI_2_RX:1.3"} {
    error "CSI instance did not upgrade to the observer ABI"
}
set_property -dict {CONFIG.kVersionMajor 1 CONFIG.kVersionMinor 3} $boundary_csi
if {[get_property CONFIG.C_S_AXI_LITE_ADDR_WIDTH $boundary_csi] != 5 ||
    [get_property CONFIG.kGenerateAXIL $boundary_csi] ni {1 true}} {
    error "Observer requires the existing 32-byte CSI AXI-Lite aperture"
}
if {[get_property CONFIG.C_M_AXIS_TDATA_WIDTH $boundary_csi] != 40 ||
    [get_property CONFIG.C_M_MAX_SAMPLES_PER_CLOCK $boundary_csi] != 4} {
    error "Observer's CSI320-beat line contract requires RAW10 four-pixel output"
}
boundary_prepare::require_same_clock
if {[boundary_prepare::width [boundary_prepare::pin axi_vdma_1/s_axis_s2mm_tdata]] != 24} {
    error "Observer's VDMA1280-beat line contract requires the actual24-bit S2MM input"
}
foreach {boundary_signal boundary_port boundary_width} {
    s_axis_s2mm_tvalid ObserveVdmaValid 1
    s_axis_s2mm_tready ObserveVdmaReady 1
    s_axis_s2mm_tuser  ObserveVdmaSof   1
    s_axis_s2mm_tlast  ObserveVdmaEol   1
    s_axis_s2mm_tkeep  ObserveVdmaKeep  3
} {
    boundary_prepare::tap axi_vdma_1/$boundary_signal MIPI_CSI_2_RX_0/$boundary_port $boundary_width
}
validate_bd_design
boundary_prepare::require_same_clock
if {[get_property CONFIG.kVersionMajor $boundary_csi] != 1 ||
    [get_property CONFIG.kVersionMinor $boundary_csi] != 3} {
    error "BD propagation did not retain CSI1.3 identity"
}
save_bd_design
if {$boundary_generate} {
    set_property SYNTH_CHECKPOINT_MODE None $boundary_bd
    reset_target all $boundary_bd
    generate_target all $boundary_bd
    foreach boundary_wrapper [make_wrapper -files $boundary_bd -top] {
        if {[llength [get_files -quiet $boundary_wrapper]] == 0} {
            add_files -norecurse -fileset sources_1 $boundary_wrapper
        }
    }
    update_compile_order -fileset sources_1
}
puts "BOUNDARY_OBSERVER_PREPARED version=1.3 passive_taps=5 output_products=$boundary_generate NO_SYNTHESIS_NO_EXPORT_NO_BOARD"
if {$boundary_opened_here} {close_project}
