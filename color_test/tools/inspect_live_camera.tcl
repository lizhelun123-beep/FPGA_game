connect -url tcp:127.0.0.1:3121
targets -set 2
foreach addr {0x10080c 0x10083c 0x100890 0x1008c0 0x1008ec} {
    bpadd -addr $addr
}
con
after 20000
stop
puts "First reached camera startup return point and result:"
puts [rrd pc]
puts [rrd r0]
puts "Camera VDMA control/status:"
puts [mrd -force 0x43000030 2]
puts "CSI long-packet/CRC counters:"
puts [mrd -force 0x43C30004 2]
con
disconnect
exit 0
