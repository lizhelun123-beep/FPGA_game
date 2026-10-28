# User-run XSCT2023.1: standalone ELF and optional FSBL+BIT+ELF BOOT.BIN.
# Does not run Vivado, connect hardware, download, or write an SD card.
if {[catch {
set app [file normalize [file join [file dirname [info script]] ..]]
set project [file normalize [file join $app .. ..]]
set repo [file dirname $project]
set xsa ""
set baseline live
set tag ""
set make_boot 0
foreach {key value} $argv {
    switch -- $key {
        -xsa {set xsa [file normalize $value]}
        -baseline {set baseline $value}
        -tag {set tag $value}
        -boot {set make_boot $value}
        default {error "Unknown argument $key; use -baseline live|xsa -xsa FILE -tag NAME -boot 0|1"}
    }
}
if {$baseline ni {live xsa} || ![regexp {^[a-zA-Z0-9_-]+$} $tag] || $make_boot ni {0 1} ||
    ($baseline eq "xsa" && ![file isfile $xsa])} {
    error "Required: -baseline live|xsa [-xsa FILE] -tag <fresh name> -boot 0|1"
}
if {![info exists ::env(XILINX_VITIS)]} {error "Start from Vitis2023.1 XSCT environment"}
set workspace [file join $project build beam_standalone $tag]
if {[file exists $workspace]} {error "Preserving existing output: $workspace; choose a new -tag"}
set python python
if {[info exists ::env(BEAM_PYTHON)]} {set python $::env(BEAM_PYTHON)}
set generated [file join $workspace inputs]
# Default live reuses the exact validated platform and does NOT run any XSCT
# platform command. Explicit xsa is the separate modern hardware path.
set prepare [list $python -B [file join $app tools prepare_game_beam.py] \
    --baseline $baseline --output $generated]
if {$xsa ne ""} {lappend prepare --xsa $xsa}
exec {*}$prepare >@stdout 2>@stderr
# The restored application deliberately has no AprilTag runtime. Reject a
# mismatched configuration before compiling rather than silently changing it.
set fd [open [file join $generated game_beam_config.c] r]
set config_text [read $fd]
close $fd
if {[string first VISION_PROFILE_RESTORED $config_text] < 0} {
    error "build_game_beam requires the restored_markers beam profile"
}
set xsa [file join $generated hardware.xsa]
if {$baseline eq "live"} {
    set bsp [file join $generated bsp]
    set fsbl [file join $generated fsbl.elf]
    puts "BEAM_REUSE_VERIFIED_LIVE_PLATFORM NO_PLATFORM_GENERATION"
} else {
setws $workspace
platform create -name beam_platform -hw $xsa -proc ps7_cortexa9_0 -os standalone
domain active standalone_domain
bsp config stdin ps7_uart_1
bsp config stdout ps7_uart_1
foreach ip {MIPI_CSI_2_RX MIPI_D_PHY_RX} {
    set makefile [file join $project repo ip $ip drivers ${ip}_v1_0 src Makefile]
    foreach target [concat \
        [glob -nocomplain [file join $workspace beam_platform hw drivers ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace beam_platform zynq_fsbl zynq_fsbl_bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]] \
        [glob -nocomplain [file join $workspace beam_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0 libsrc ${ip}_v1_0 src Makefile]]] {
        file copy -force $makefile $target
    }
}
platform generate
set bsp [file join $workspace beam_platform ps7_cortexa9_0 standalone_domain bsp ps7_cortexa9_0]
set fsbl [file join $workspace beam_platform zynq_fsbl fsbl.elf]
}
set bin [file join $::env(XILINX_VITIS) gnu aarch32 nt gcc-arm-none-eabi bin]
set compiler [file join $bin arm-none-eabi-gcc.exe]
set src [file join $app src]
set output [file join $workspace output]
file mkdir $output
set objects {}
set common_flags [list -std=gnu99 -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -O2 -g3 \
    -ffunction-sections -fdata-sections -DGAME_BEAM_STANDALONE=1 \
    -I[file join $bsp include] -I$src -I[file join $src standalone] -I$generated]
# Canonical detector and beam core. Never glob Linux menu/worker/main sources.
set sources {}
foreach name {game_beam ray_game game_scene_adapter vision_stabilizer vision_ps \
    green_target_detector vision_overlay game_linux_capture game_linux_display ov5640 scene_protocol} {
    lappend sources [file join $src ${name}.c]
}
lappend sources [file join $src i2c PS_i2c.c] [file join $generated game_beam_config.c]
foreach name {game_beam_standalone game_baremetal_io} {
    lappend sources [file join $src standalone ${name}.c]
}
set index 0
foreach source $sources {
    set object [file join $output app_[incr index].o]
    exec $compiler {*}$common_flags -Wall -Wextra -Werror -c $source -o $object >@stdout 2>@stderr
    lappend objects $object
}
set elf [file join $output beam_standalone.elf]
set map [file join $output beam_standalone.map]
# Keep the established DDR heap reservation; no AprilTag sources are linked.
# Linker bounds/DDR overflow are enforced at link, not by guessed DMA addresses.
exec $compiler {*}$common_flags -L[file join $bsp lib] -specs=[file join $src Xilinx.spec] \
    -T[file join $src lscript.ld] -Wl,--defsym=_HEAP_SIZE=0x08000000 \
    -Wl,--defsym=_STACK_SIZE=0x00040000 -Wl,--gc-sections -Wl,-Map=$map \
    {*}$objects -Wl,--start-group -lxil -lgcc -lc -lm -Wl,--end-group -o $elf >@stdout 2>@stderr
# Byte-level EABI/load/symbol checks also work on hosts whose vendor size/
# readelf utilities cannot start because of Windows DLL relocation conflicts.
exec $python -B [file join $app tools verify_game_beam.py] --inputs $generated --elf $elf >@stdout 2>@stderr
puts "BEAM_STANDALONE_ELF $elf"
if {$make_boot} {
    if {![file isfile $fsbl]} {error "Matching generated FSBL missing: $fsbl"}
    set bif [file join $output beam_standalone.bif]
    set fd [open $bif w]
    puts $fd "the_ROM_image:\n\{\n  \[bootloader\] \"$fsbl\"\n  \"[file join $generated system_wrapper.bit]\"\n  \"$elf\"\n\}"
    close $fd
    set bootgen [file join $::env(XILINX_VITIS) bin bootgen.bat]
    if {![file isfile $bootgen]} {error "bootgen not found: $bootgen"}
    exec $bootgen -arch zynq -image $bif -o [file join $output BOOT.BIN] >@stdout 2>@stderr
    exec $python -B [file join $app tools verify_game_beam.py] --inputs $generated --elf $elf \
        --boot [file join $output BOOT.BIN] >@stdout 2>@stderr
    puts "BEAM_STANDALONE_BOOT [file join $output BOOT.BIN]"
}
puts "NO_HARDWARE_CONNECTION_NO_SD_WRITE"
} error_message]} {
    puts stderr "ERROR: $error_message"
    exit 1
}
