# Recreate a standalone build without relying on an old Eclipse workspace.
set root [file normalize [file join [file dirname [info script]] ..]]
set build_root [file normalize [file join $root build]]
set workspace [file normalize [file join $build_root camera_recovery]]
set xsa [file normalize [file join $root color_test.xsa]]
if {![file exists $xsa]} {
    error "Current hardware handoff not found: $xsa"
}
if {[file dirname $workspace] ne $build_root ||
    [file tail $workspace] ne "camera_recovery"} {
    error "Refusing to recreate unexpected workspace path: $workspace"
}
# A recovery platform is generated data.  Recreate the canonical workspace so
# no BSP, ps7_init, FSBL, embedded BIT, or driver metadata can survive from an
# older XSA.
if {[file exists $workspace]} {
    file delete -force $workspace
}
file mkdir $workspace
setws $workspace
platform create -name camera_platform -hw $xsa -proc ps7_cortexa9_0 -os standalone
domain active standalone_domain
bsp config stdin ps7_uart_1
bsp config stdout ps7_uart_1
# The XSA carries old driver Makefiles with literal *.c arguments on Windows.
# Use the already-corrected repository Makefiles in the generated platform.
foreach ip {MIPI_CSI_2_RX MIPI_D_PHY_RX} {
    set makefile [file join $root repo ip $ip drivers ${ip}_v1_0 src Makefile]
    foreach target [concat \
        [glob -nocomplain [file join $workspace camera_platform hw drivers ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace camera_platform zynq_fsbl zynq_fsbl_bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace camera_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]]] {
        file copy -force $makefile $target
    }
}
platform generate
# Compile the canonical sources directly with the generated BSP. This avoids
# stale imported source copies and does not require an Eclipse app project.
set bsp [file join $workspace camera_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0]
set src [file join $root software mipi_hdmi mipi_hdmi src]
set output [file join $workspace output]
file mkdir $output
set compiler [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin arm-none-eabi-gcc.exe]
set sources [concat [glob [file join $src *.c]] [glob [file join $src i2c *.c]] \
    [glob [file join $src dynclk *.c]] [glob [file join $src display_ctrl *.c]]]
set command [list $compiler -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -O0 -g3 -Wall -Wextra \
    -I[file join $bsp include] -I$src -L[file join $bsp lib] \
    -specs=[file join $src Xilinx.spec] -T[file join $src lscript.ld] \
    {*}$sources -Wl,--start-group -lxil -lgcc -lc -lm -Wl,--end-group \
    -o [file join $output camera_recovery.elf]]
exec {*}$command >@stdout 2>@stderr
puts "Built [file join $output camera_recovery.elf]"
