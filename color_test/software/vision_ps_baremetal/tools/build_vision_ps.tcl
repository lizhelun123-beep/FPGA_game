# Build the standalone Cortex-A9 vision prototype against the current XSA.
# XSCT can otherwise return zero after a Tcl error; propagate build failures.
if {[catch {
set app_root [file normalize [file join [file dirname [info script]] ..]]
set project_dir [file normalize [file join $app_root .. ..]]
set workspace [file join $project_dir build vision_ps_baremetal]
set xsa [file join $project_dir color_test.xsa]

if {![file exists $xsa]} {
    puts stderr "ERROR: missing hardware handoff: $xsa"
    puts stderr "       build it with: vivado -mode batch -source color_test/tools/build_bitstream.tcl"
    exit 2
}

set reuse_bsp [expr {[info exists ::env(VISION_REUSE_BSP)] && $::env(VISION_REUSE_BSP) eq "1"}]
set build_mode default
if {[info exists ::env(VISION_BUILD_MODE)]} { set build_mode $::env(VISION_BUILD_MODE) }
if {$build_mode ni {default camera fixed both live perf}} {
    error "VISION_BUILD_MODE must be camera, fixed, both, live or perf (or unset)"
}
if {$build_mode eq "perf" && !$reuse_bsp} {
    error "Performance-only build requires VISION_REUSE_BSP=1; no platform generation allowed"
}
set platform_dir [file join $workspace vision_ps_platform]
set bsp [file join $platform_dir ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0]
proc read_binary {path} {
    set handle [open $path rb]
    set data [read $handle]
    close $handle
    return $data
}
if {$reuse_bsp} {
    # PS-only builds must never silently update hardware or regenerate a BSP.
    set spr [file join $platform_dir platform.spr]
    foreach input [list $spr [file join $bsp include xparameters.h] \
            [file join $bsp lib libxil.a]] {
        if {![file isfile $input]} { error "Missing existing platform/BSP input: $input" }
    }
    set spr_data [read_binary $spr]
    if {[string first "\"platHandOff\":\"$xsa\"" $spr_data] < 0 ||
        [string first {"processors":"ps7_cortexa9_0"} $spr_data] < 0 ||
        [string first {"os":"standalone"} $spr_data] < 0} {
        error "Existing platform handoff/processor/OS does not match; no platform updated"
    }
    foreach copy [list [file join $platform_dir hw color_test.xsa] \
            [file join $platform_dir export vision_ps_platform hw color_test.xsa]] {
        if {![file isfile $copy] || [read_binary $copy] ne [read_binary $xsa]} {
            error "XSA mismatch: $copy; no platform updated"
        }
    }
    puts "Reusing byte-matched XSA and existing standalone Cortex-A9 BSP; no generation"
} else {
setws $workspace
if {![file exists [file join $workspace vision_ps_platform platform.spr]]} {
    platform create -name vision_ps_platform -hw $xsa -proc ps7_cortexa9_0 -os standalone
} else {
    platform active vision_ps_platform
    platform config -updatehw $xsa
}
domain active standalone_domain
bsp config stdin ps7_uart_1
bsp config stdout ps7_uart_1

# Repair legacy driver Makefiles copied through the XSA, as in camera_recovery.
foreach ip {MIPI_CSI_2_RX MIPI_D_PHY_RX} {
    set makefile [file join $project_dir repo ip $ip drivers ${ip}_v1_0 src Makefile]
    foreach target [concat \
        [glob -nocomplain [file join $workspace vision_ps_platform hw drivers ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace vision_ps_platform zynq_fsbl zynq_fsbl_bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace vision_ps_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]]] {
        file copy -force $makefile $target
    }
}
platform generate
}

set src [file join $app_root src]
set output [file join $workspace output]
file mkdir $output
set compiler [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-gcc.exe]
set size_tool [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-size.exe]
set sources [concat [glob [file join $src *.c]] [glob [file join $src i2c *.c]] \
    [glob [file join $src dynclk *.c]] [glob [file join $src display_ctrl *.c]]]
if {$build_mode eq "both"} { set modes {camera fixed} } else { set modes [list $build_mode] }
if {$build_mode ne "default"} {
    set config [read_binary [file join $src vision_ps_config.h]]
    foreach option {VISION_MINIMAL_TEST VISION_GREEN_TARGET_ONLY} {
        if {![regexp -line "^#define $option 0\r?$" $config]} {
            error "$option must remain 0 for the camera/fixed strict builds"
        }
    }
}
foreach mode $modes {
    set defines {}
    set mode_output $output
    if {$mode ne "default"} {
        set mode_output [file join $output $mode]
        if {$mode eq "perf" && [info exists ::env(VISION_PERF_OUTPUT_TAG)]} {
            set tag $::env(VISION_PERF_OUTPUT_TAG)
            if {![regexp {^[a-zA-Z0-9_-]+$} $tag] || $tag in {live camera fixed default}} {
                error "VISION_PERF_OUTPUT_TAG must be a distinct simple directory name"
            }
            set mode_output [file join $output $tag]
        }
        file mkdir $mode_output
        lappend defines -DVISION_FIXED_SCENE_DEMO=[expr {$mode eq "fixed" ? 1 : 0}]
        lappend defines -DVISION_SCENE_STREAM_ENABLE=[expr {$mode in {live perf} ? 1 : 0}]
        lappend defines -DVISION_PERF_ENABLE=[expr {$mode eq "perf" ? 1 : 0}]
        if {$mode in {live perf} && [info exists ::env(VISION_SCENE_STREAM_HZ)]} {
            if {![string is integer -strict $::env(VISION_SCENE_STREAM_HZ)] ||
                $::env(VISION_SCENE_STREAM_HZ) < 1 || $::env(VISION_SCENE_STREAM_HZ) > 30} {
                error "VISION_SCENE_STREAM_HZ must be in 1..30"
            }
            lappend defines -DVISION_SCENE_STREAM_HZ=$::env(VISION_SCENE_STREAM_HZ)
        }
        if {$mode eq "perf" && [info exists ::env(VISION_PERF_REPORT_MS)]} {
            if {![string is integer -strict $::env(VISION_PERF_REPORT_MS)] ||
                $::env(VISION_PERF_REPORT_MS) < 5000 || $::env(VISION_PERF_REPORT_MS) > 60000} {
                error "VISION_PERF_REPORT_MS must be in 5000..60000"
            }
            lappend defines -DVISION_PERF_REPORT_MS=$::env(VISION_PERF_REPORT_MS)
        }
    }
    set elf [file join $mode_output vision_ps_baremetal.elf]
    set map [file join $mode_output vision_ps_baremetal.map]
    if {$mode eq "perf" && ([file exists $elf] || [file exists $map] ||
            [file exists [file join $mode_output BOOT.bin]])} {
        error "Preserving existing diagnostic output; choose a fresh VISION_PERF_OUTPUT_TAG"
    }
    set command [list $compiler -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard \
    -O2 -g3 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    {*}$defines \
    -I[file join $bsp include] -I$src -L[file join $bsp lib] \
    -specs=[file join $src Xilinx.spec] -T[file join $src lscript.ld] \
    {*}$sources -Wl,--gc-sections -Wl,-Map=$map \
    -Wl,--start-group -lxil -lgcc -lc -lm -Wl,--end-group -o $elf]
    puts "Strict ARM build mode=$mode: -O2 -Wall -Wextra -Werror $defines"
    exec {*}$command >@stdout 2>@stderr
    exec $size_tool $elf >@stdout 2>@stderr
    puts "Built $elf"
    puts "Map   $map"
}
} build_error]} {
    puts stderr "ERROR: $build_error"
    exit 1
}
