# External-clock mode uses sibling inputs from one MMCM output.  The
# top-level system.xdc supplies the common-source runtime clocks; do not create
# the invalid PixelClk -> SerialClk generated-clock edge in the IP OOC scope.
create_clock -period 13.461538 [get_ports PixelClk]
create_clock -period 2.692308 [get_ports SerialClk]