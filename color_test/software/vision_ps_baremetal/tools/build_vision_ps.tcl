# Build the standalone Cortex-A9 vision prototype against the current XSA.
set app_root [file normalize [file join [file dirname [info script]] ..]]
set project_dir [file normalize [file join $app_root .. ..]]
set workspace [file join $project_dir build vision_ps_baremetal]
set xsa [file join $project_dir color_test.xsa]

if {![file exists $xsa]} {
    puts stderr "ERROR: missing hardware handoff: $xsa"
    puts stderr "       build it with: vivado -mode batch -source color_test/tools/build_bitstream.tcl"
    exit 2
}

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

set bsp [file join $workspace vision_ps_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0]
set src [file join $app_root src]
set output [file join $workspace output]
file mkdir $output
set elf [file join $output vision_ps_baremetal.elf]
set map [file join $output vision_ps_baremetal.map]
set compiler [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-gcc.exe]
set size_tool [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-size.exe]
set sources [concat [glob [file join $src *.c]] [glob [file join $src i2c *.c]] \
    [glob [file join $src dynclk *.c]] [glob [file join $src display_ctrl *.c]]]
set command [list $compiler -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard \
    -O2 -g3 -Wall -Wextra -ffunction-sections -fdata-sections \
    -I[file join $bsp include] -I$src -L[file join $bsp lib] \
    -specs=[file join $src Xilinx.spec] -T[file join $src lscript.ld] \
    {*}$sources -Wl,--gc-sections -Wl,-Map=$map \
    -Wl,--start-group -lxil -lgcc -lc -lm -Wl,--end-group -o $elf]
exec {*}$command >@stdout 2>@stderr
exec $size_tool $elf >@stdout 2>@stderr
puts "Built $elf"
puts "Map   $map"
