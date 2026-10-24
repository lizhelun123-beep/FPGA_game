"""Linux I2C control for the current OV5640 MIPI RAW10 configuration."""

import os
import time

I2C_SLAVE = 0x0703
OV5640_ADDRESS = 0x3C

# Ported from the current verified mipi_hdmi/ov5640.c. The two legacy
# formatter writes were deliberately kept RAW here; no DVP/RGB565 table from
# the ALINX reference ZIP is used.
SENSOR_INIT = (
    (0x3008, 0x42), (0x3103, 0x03), (0x3017, 0x00), (0x3018, 0x00),
    (0x3034, 0x1A), (0x3035, 0x11), (0x3036, 0x38), (0x3037, 0x11),
    (0x3108, 0x01), (0x303D, 0x10), (0x303B, 0x19),
    (0x3630, 0x2E), (0x3631, 0x0E), (0x3632, 0xE2), (0x3633, 0x23),
    (0x3621, 0xE0), (0x3704, 0xA0), (0x3703, 0x5A), (0x3715, 0x78),
    (0x3717, 0x01), (0x370B, 0x60), (0x3705, 0x1A), (0x3905, 0x02),
    (0x3906, 0x10), (0x3901, 0x0A), (0x3731, 0x02), (0x3600, 0x37),
    (0x3601, 0x33), (0x302D, 0x60), (0x3620, 0x52), (0x371B, 0x20),
    (0x471C, 0x50), (0x3A13, 0x43), (0x3A18, 0x00), (0x3A19, 0xF8),
    (0x3635, 0x13), (0x3636, 0x06), (0x3634, 0x44), (0x3622, 0x01),
    (0x3C01, 0x34), (0x3C04, 0x28), (0x3C05, 0x98), (0x3C06, 0x00),
    (0x3C07, 0x08), (0x3C08, 0x00), (0x3C09, 0x1C), (0x3C0A, 0x9C),
    (0x3C0B, 0x40), (0x503D, 0x00), (0x3820, 0x46), (0x300E, 0x45),
    (0x4800, 0x14), (0x302E, 0x08), (0x4300, 0x00), (0x501F, 0x03),
    (0x4713, 0x03), (0x4407, 0x04), (0x440E, 0x00), (0x460B, 0x35),
    (0x460C, 0x20), (0x3824, 0x01), (0x5000, 0x06), (0x5001, 0x00),
)

MODE_720P_RAW10 = (
    (0x3035, 0x21), (0x3036, 0x46), (0x3037, 0x05), (0x3108, 0x11),
    (0x3034, 0x1A),
    (0x3800, 0x00), (0x3801, 0x00), (0x3802, 0x00), (0x3803, 0x08),
    (0x3804, 0x0A), (0x3805, 0x3B), (0x3806, 0x07), (0x3807, 0x9B),
    (0x3810, 0x00), (0x3811, 0x00), (0x3812, 0x00), (0x3813, 0x00),
    (0x3808, 0x05), (0x3809, 0x00), (0x380A, 0x02), (0x380B, 0xD0),
    (0x380C, 0x07), (0x380D, 0x68), (0x380E, 0x03), (0x380F, 0xD8),
    (0x3814, 0x31), (0x3815, 0x31), (0x3821, 0x01), (0x4837, 36),
    (0x3618, 0x00), (0x3612, 0x59), (0x3708, 0x64), (0x3709, 0x52),
    (0x370C, 0x03), (0x4300, 0x00), (0x501F, 0x03),
    (0x5000, 0x06), (0x5001, 0x00),
)

RAW10_EXPECTED = {
    0x3034: 0x1A,
    0x3808: 0x05,
    0x3809: 0x00,
    0x380A: 0x02,
    0x380B: 0xD0,
    0x4300: 0x00,
    0x5000: 0x06,
    0x5001: 0x00,
    0x501F: 0x03,
}


class LinuxI2C:
    def __init__(self, device, address=OV5640_ADDRESS):
        self.device = str(device)
        self.address = int(address)
        self.fd = None

    def open(self):
        if self.fd is None:
            try:
                import fcntl
            except ImportError:
                raise RuntimeError("Linux fcntl is required to open an I2C device")
            self.fd = os.open(self.device, os.O_RDWR)
            fcntl.ioctl(self.fd, I2C_SLAVE, self.address)
        return self

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def write_register(self, register, value):
        self.open()
        payload = bytes(((register >> 8) & 0xFF, register & 0xFF, value & 0xFF))
        written = os.write(self.fd, payload)
        if written != len(payload):
            raise OSError("short OV5640 I2C write")

    def read_register(self, register):
        self.open()
        address = bytes(((register >> 8) & 0xFF, register & 0xFF))
        if os.write(self.fd, address) != 2:
            raise OSError("short OV5640 register-address write")
        value = os.read(self.fd, 1)
        if len(value) != 1:
            raise OSError("short OV5640 I2C read")
        return value[0]


class OV5640:
    def __init__(self, bus):
        self.bus = bus

    def sensor_id(self):
        return self.bus.read_register(0x300A), self.bus.read_register(0x300B)

    def write_table(self, table):
        for register, value in table:
            self.bus.write_register(register, value)

    def configure_raw10_720p(self):
        if self.sensor_id() != (0x56, 0x40):
            raise RuntimeError("OV5640 ID is not 56 40")
        self.bus.write_register(0x3103, 0x11)
        self.bus.write_register(0x3008, 0x82)
        time.sleep(1.0)
        self.write_table(SENSOR_INIT)
        time.sleep(1.0)
        self.bus.write_register(0x3008, 0x42)
        self.write_table(MODE_720P_RAW10)
        self.verify_raw10_720p()

    def verify_raw10_720p(self):
        actual = {register: self.bus.read_register(register)
                  for register in RAW10_EXPECTED}
        wrong = {register: (actual[register], expected)
                 for register, expected in RAW10_EXPECTED.items()
                 if actual[register] != expected}
        if wrong:
            raise RuntimeError("OV5640 RAW10 readback mismatch: {!r}".format(wrong))
        return actual

    def start(self):
        self.bus.write_register(0x3008, 0x02)
        value = self.bus.read_register(0x3008)
        if value != 0x02:
            raise RuntimeError("OV5640 failed to leave standby: 0x{:02x}".format(value))

    def stop(self):
        self.bus.write_register(0x3008, 0x42)
        if self.bus.read_register(0x3008) != 0x42:
            raise RuntimeError("OV5640 standby did not latch")

    def lock_exposure_gain(self):
        values = {register: self.bus.read_register(register)
                  for register in (0x3500, 0x3501, 0x3502, 0x350A, 0x350B)}
        manual = self.bus.read_register(0x3503) | 0x03
        self.bus.write_register(0x3503, manual)
        if self.bus.read_register(0x3503) & 0x03 != 0x03:
            raise RuntimeError("OV5640 exposure/gain lock did not latch")
        return values
