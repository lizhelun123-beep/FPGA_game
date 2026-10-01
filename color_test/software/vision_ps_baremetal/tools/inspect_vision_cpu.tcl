# Briefly halt CPU0 to identify the current software path, then always resume.
connect -url tcp:127.0.0.1:3121
targets -set 2
set detail ""
if {[catch {
    stop
    puts [rrd pc]
    puts [rrd lr]
    puts [rrd sp]
    puts [rrd r0]
    puts [rrd r1]
} detail]} {
    puts stderr "Inspection failed: $detail"
}
if {[catch {con} resume_detail] &&
    ![string match -nocase "*already running*" $resume_detail]} {
    puts stderr "Resume failed: $resume_detail"
    disconnect
    exit 3
}
disconnect
exit 0
