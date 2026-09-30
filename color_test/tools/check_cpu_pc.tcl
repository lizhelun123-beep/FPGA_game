connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0"}
stop
puts "CPU0 registers after Reset:"
puts [rrd pc]
puts [rrd cpsr]
con
disconnect
exit 0
