set workspace [file normalize [file join [file dirname [info script]] .. software mipi_hdmi]]

setws $workspace
app build -name mipi_hdmi
