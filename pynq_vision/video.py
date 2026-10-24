"""Fixed 1280x720 dynamic-clock and VTC setup used by the verified design."""

from .registers import RegisterBlock


class DynamicClock:
    # Digilent axi_dynclk values calculated for 74.25 MHz from a 100 MHz FCLK0.
    REGISTERS_720P = {
        0x08: 0x00000041,
        0x0C: 0x0000069A,
        0x10: 0x00000000,
        0x14: 0x000020C4,
        0x18: 0xCFAFA401,
        0x1C: 0x00A300FF,
    }

    def __init__(self, io):
        self.regs = RegisterBlock(io)

    def stop(self):
        self.regs.write(0x00, 0)
        self.regs.wait(0x04, 1, 0)

    def start_720p(self):
        self.stop()
        for offset, value in sorted(self.REGISTERS_720P.items()):
            self.regs.write(offset, value)
        self.regs.write(0x00, 1)
        self.regs.wait(0x04, 1, 1)


class VideoTimingController:
    """Programs the same 720p60 generator values as the Xilinx XVtc driver."""

    CONTROL = 0x000
    REG_UPDATE = 0x00000002
    GENERATOR_ENABLE = 0x00000004
    GENERATOR_SOURCES = 0x03FDEF00

    def __init__(self, io):
        self.regs = RegisterBlock(io)

    @staticmethod
    def _pair(start, end):
        return (int(end) << 16) | int(start)

    def configure_720p(self):
        self.regs.write(self.CONTROL, self.REG_UPDATE)
        self.regs.write(0x060, self._pair(1280, 720))      # active H/V
        self.regs.write(0x094, 720 << 16)                 # field-1 V active
        self.regs.write(0x068, 0)                         # progressive
        self.regs.write(0x06C, 0x7F)                      # positive polarities
        self.regs.write(0x070, 1650)
        self.regs.write(0x074, self._pair(750, 750))
        self.regs.write(0x078, self._pair(1390, 1430))
        self.regs.write(0x07C, self._pair(1280, 1280))
        self.regs.write(0x080, self._pair(724, 729))
        self.regs.write(0x084, self._pair(1390, 1390))
        self.regs.write(0x088, self._pair(1280, 1280))
        self.regs.write(0x08C, self._pair(724, 729))
        self.regs.write(0x090, self._pair(1390, 1390))
        self.regs.write(self.CONTROL,
                        self.GENERATOR_SOURCES | self.REG_UPDATE | self.GENERATOR_ENABLE)
