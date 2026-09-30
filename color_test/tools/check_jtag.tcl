set server "tcp:127.0.0.1:3121"
puts "Connecting to $server"
if {[catch {connect -url $server} channel]} {
    puts stderr "ERROR: cannot connect to hw_server: $channel"
    exit 2
}
puts "Connected: $channel"
after 1000
set found [targets]
if {[string trim $found] eq ""} {
    puts stderr "ERROR: hw_server is running, but the JTAG target list is empty."
    disconnect
    exit 3
}
puts "JTAG targets:"
puts $found
disconnect
exit 0
