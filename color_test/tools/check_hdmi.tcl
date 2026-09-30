set server "tcp:127.0.0.1:3121"
puts "Connecting to $server"
connect -url $server
after 500
if {[catch {set cpu [targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}]} detail]} {
    puts stderr "ERROR: Cortex-A9 #0 was not found; reconnect board/JTAG first."
    disconnect
    exit 2
}
puts "Selected CPU0"
puts "SLCR FCLK0 clock control @ 0xF8000170"
puts [mrd -force 0xF8000170 1]
puts "SLCR FPGA reset control @ 0xF8000240"
puts [mrd -force 0xF8000240 1]
puts "Display VDMA MM2S registers @ 0x43010000"
puts [mrd -force 0x43010000 24]
puts "Dynamic pixel clock registers @ 0x43C00000"
puts [mrd -force 0x43C00000 8]
puts "VTC control/timing registers @ 0x43C10000"
puts [mrd -force 0x43C10000 24]
puts "VTC generator timing registers @ 0x43C10060"
puts [mrd -force 0x43C10060 16]
puts "Display framebuffer first 64 bytes @ 0x00114C00"
puts [mrd -force 0x00114C00 16]
puts "Display framebuffer center sample @ 0x0030F780"
puts [mrd -force 0x0030F780 16]
puts "Camera VDMA S2MM control/status @ 0x43000030"
puts [mrd -force 0x43000030 2]
puts "CSI counters, first sample @ 0x43C30004"
puts [mrd -force 0x43C30004 2]
after 500
puts "CSI counters, second sample after 500 ms"
puts [mrd -force 0x43C30004 2]
disconnect
exit 0
