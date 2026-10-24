# Read-only live health sampling for the current vision application.
# The script does not stop/reset the CPU or write any device register.
connect -url tcp:127.0.0.1:3121
targets -set 2
for {set i 0} {$i < 20} {incr i} {
    set csi_status [mrd -force -value 0x43C30000]
    set packets [mrd -force -value 0x43C30004]
    set crc [mrd -force -value 0x43C30008]
    set s2mm_cr [mrd -force -value 0x43000030]
    set s2mm_sr [mrd -force -value 0x43000034]
    set mm2s_cr [mrd -force -value 0x43010000]
    set mm2s_sr [mrd -force -value 0x43010004]
    set park [mrd -force -value 0x43000028]
    set presented [mrd -force -value 0x0011C0C4]
    puts [format "SAMPLE %02d csi=%08X packets=%08X crc=%08X s2mm=%08X/%08X mm2s=%08X/%08X park=%08X presented=%u" \
        $i $csi_status $packets $crc $s2mm_cr $s2mm_sr $mm2s_cr $mm2s_sr $park $presented]
    after 500
}
disconnect
exit 0
