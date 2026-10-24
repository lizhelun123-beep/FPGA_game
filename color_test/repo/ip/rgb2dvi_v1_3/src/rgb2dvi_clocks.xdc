### Clock constraints ###
# External-clock RGB2DVI receives sibling clocks from axi_dynclk.
# PixelClk is the BUFR /5 branch of the same MMCM CLKOUT0 that feeds BUFIO
# and SerialClk; do not describe SerialClk as PixelClk x5 here.