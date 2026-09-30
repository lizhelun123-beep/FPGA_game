set workspace [file normalize [file join [file dirname [info script]] .. software mipi_hdmi]]

setws $workspace
platform active color_test
domain active standalone_ps7_cortexa9_0
bsp config stdin ps7_uart_1
bsp config stdout ps7_uart_1
bsp regenerate
platform generate
app build -name mipi_hdmi
