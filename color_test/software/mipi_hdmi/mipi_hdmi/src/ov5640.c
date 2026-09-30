#include "ov5640.h"
#include "xiicps.h"
#include "xparameters.h"
#include "i2c/PS_i2c.h"
#include "sleep.h"
struct reginfo sensor_init_data[] =
{	
		//[7]=0 Software reset; [6]=1 Software power down; Default=0x02
		{0x3008, 0x42},
		//[1]=1 System input clock from PLL; Default read = 0x11
		{0x3103, 0x03},
		//[3:0]=0000 MD2P,MD2N,MCP,MCN input; Default=0x00
		{0x3017, 0x00},
		//[7:2]=000000 MD1P,MD1N, D3:0 input; Default=0x00
		{0x3018, 0x00},
		//[6:4]=001 PLL charge pump, [3:0]=1000 MIPI 8-bit mode
		{0x3034, 0x18},
		//PLL1 configuration
		//[7:4]=0001 System clock divider /1, [3:0]=0001 Scale divider for MIPI /1
		{0x3035, 0x11},
		//[7:0]=56 PLL multiplier
		{0x3036, 0x38},
		//[4]=1 PLL root divider /2, [3:0]=1 PLL pre-divider /1
		{0x3037, 0x11},
		//[5:4]=00 PCLK root divider /1, [3:2]=00 SCLK2x root divider /1, [1:0]=01 SCLK root divider /2
		{0x3108, 0x01},
		//PLL2 configuration
		//[5:4]=01 PRE_DIV_SP /1.5, [2]=1 R_DIV_SP /1, [1:0]=00 DIV12_SP /1
		{0x303D, 0x10},
		//[4:0]=11001 PLL2 multiplier DIV_CNT5B = 25
		{0x303B, 0x19},

		{0x3630, 0x2e},
		{0x3631, 0x0e},
		{0x3632, 0xe2},
		{0x3633, 0x23},
		{0x3621, 0xe0},
		{0x3704, 0xa0},
		{0x3703, 0x5a},
		{0x3715, 0x78},
		{0x3717, 0x01},
		{0x370b, 0x60},
		{0x3705, 0x1a},
		{0x3905, 0x02},
		{0x3906, 0x10},
		{0x3901, 0x0a},
		{0x3731, 0x02},
		//VCM debug mode
		{0x3600, 0x37},
		{0x3601, 0x33},
		//System control register changing not recommended
		{0x302d, 0x60},
		//??
		{0x3620, 0x52},
		{0x371b, 0x20},
		//?? DVP
		{0x471c, 0x50},

		{0x3a13, 0x43},
		{0x3a18, 0x00},
		{0x3a19, 0xf8},
		{0x3635, 0x13},
		{0x3636, 0x06},
		{0x3634, 0x44},
		{0x3622, 0x01},
		{0x3c01, 0x34},
		{0x3c04, 0x28},
		{0x3c05, 0x98},
		{0x3c06, 0x00},
		{0x3c07, 0x08},
		{0x3c08, 0x00},
		{0x3c09, 0x1c},
		{0x3c0a, 0x9c},
		{0x3c0b, 0x40},

		//[7]=1 color bar enable, [3:2]=00 eight color bar
		{0x503d, 0x00},
		//[2]=1 ISP vflip, [1]=1 sensor vflip
		{0x3820, 0x46},

		//[7:5]=001 Two lane mode, [4]=0 MIPI HS TX no power down, [3]=0 MIPI LP RX no power down, [2]=1 MIPI enable, [1:0]=10 Debug mode; Default=0x58
		{0x300e, 0x45},
		//[5]=0 Clock free running, [4]=1 Send line short packet, [3]=0 Use lane1 as default, [2]=1 MIPI bus LP11 when no packet; Default=0x04
		{0x4800, 0x14},
		{0x302e, 0x08},
		//[7:4]=0x3 YUV422, [3:0]=0x0 YUYV
		//{0x4300, 0x30},
		//[7:4]=0x6 RGB565, [3:0]=0x0 {b[4:0],g[5:3],g[2:0],r[4:0]}
		{0x4300, 0x6f},
		{0x501f, 0x01},

		{0x4713, 0x03},
		{0x4407, 0x04},
		{0x440e, 0x00},
		{0x460b, 0x35},
		//[1]=0 DVP PCLK divider manual control by 0x3824[4:0]
		{0x460c, 0x20},
		//[4:0]=1 SCALE_DIV=INT(3824[4:0]/2)
		{0x3824, 0x01},
		// RAW(DPC) is demosaiced in the PL. Keep BPC/WPC, but disable the
		// sensor CIP so that the FPGA never receives already-interpolated data.
		{0x5000, 0x06},
		// AWB/CCM operate on processed color, not on the RAW(DPC) stream.
		{0x5001, 0x00},

		{SEQUENCE_END, 0x00}
};


struct reginfo cfg_720p_60fps[] =
{
		//1280 x 720 binned, RAW10, MIPISCLK=280M, SCLK=56Mz, PCLK=56M
		//PLL1 configuration
		//[7:4]=0010 System clock divider /2, [3:0]=0001 Scale divider for MIPI /1
		{0x3035, 0x21},
		//[7:0]=70 PLL multiplier
		{0x3036, 0x46},
		//[4]=0 PLL root divider /1, [3:0]=5 PLL pre-divider /1.5
		{0x3037, 0x05},
		//[5:4]=01 PCLK root divider /2, [3:2]=00 SCLK2x root divider /1, [1:0]=01 SCLK root divider /2
		{0x3108, 0x11},

		//[6:4]=001 PLL charge pump, [3:0]=1010 MIPI 10-bit mode
		{0x3034, 0x1A},

		//[3:0]=0 X address start high byte
		{0x3800, (0 >> 8) & 0x0F},
		//[7:0]=0 X address start low byte
		{0x3801, 0 & 0xFF},
		//[2:0]=0 Y address start high byte
		{0x3802, (8 >> 8) & 0x07},
		//[7:0]=0 Y address start low byte
		{0x3803, 8 & 0xFF},

		//[3:0] X address end high byte
		{0x3804, (2619 >> 8) & 0x0F},
		//[7:0] X address end low byte
		{0x3805, 2619 & 0xFF},
		//[2:0] Y address end high byte
		{0x3806, (1947 >> 8) & 0x07},
		//[7:0] Y address end low byte
		{0x3807, 1947 & 0xFF},

		//[3:0]=0 timing hoffset high byte
		{0x3810, (0 >> 8) & 0x0F},
		//[7:0]=0 timing hoffset low byte
		{0x3811, 0 & 0xFF},
		//[2:0]=0 timing voffset high byte
		{0x3812, (0 >> 8) & 0x07},
		//[7:0]=0 timing voffset low byte
		{0x3813, 0 & 0xFF},

		//[3:0] Output horizontal width high byte
		{0x3808, (1280 >> 8) & 0x0F},
		//[7:0] Output horizontal width low byte
		{0x3809, 1280 & 0xFF},
		//[2:0] Output vertical height high byte
		{0x380a, (720 >> 8) & 0x7F},
		//[7:0] Output vertical height low byte
		{0x380b, 720 & 0xFF},

		//HTS line exposure time in # of pixels
		{0x380c, (1896 >> 8) & 0x1F},
		{0x380d, 1896 & 0xFF},
		//VTS frame exposure time in # lines
		{0x380e, (984 >> 8) & 0xFF},
		{0x380f, 984 & 0xFF},

		//[7:4]=0x3 horizontal odd subsample increment, [3:0]=0x1 horizontal even subsample increment
		{0x3814, 0x31},
		//[7:4]=0x3 vertical odd subsample increment, [3:0]=0x1 vertical even subsample increment
		{0x3815, 0x31},

		//[2]=0 ISP mirror, [1]=0 sensor mirror, [0]=1 horizontal binning
		{0x3821, 0x01},

		//little MIPI shit: global timing unit, period of PCLK in ns * 2(depends on # of lanes)
		{0x4837, 36}, // 1/56M*2

		//Undocumented anti-green settings
		{0x3618, 0x00}, // Removes vertical lines appearing under bright light
		{0x3612, 0x59},
		{0x3708, 0x64},
		{0x3709, 0x52},
		{0x370c, 0x03},

		//[7:4]=0x0 Formatter RAW, [3:0]=0x0 BGBG/GRGR
		{0x4300, 0x00},
		//[2:0]=0x3 Format select ISP RAW (DPC)
		{0x501f, 0x03},
		// BPC/WPC only; PL performs Bayer interpolation and RGB correction.
		{0x5000, 0x06},
		{0x5001, 0x00},
		{SEQUENCE_END, 0x00}
};



struct reginfo cfg_1080p_30fps[] =
{//1920 x 1080 @ 30fps, RAW10, MIPISCLK=420, SCLK=84MHz, PCLK=84M
		//PLL1 configuration
		//[7:4]=0010 System clock divider /2, [3:0]=0001 Scale divider for MIPI /1
		{0x3035, 0x21}, // 30fps setting
		//[7:0]=105 PLL multiplier
		{0x3036, 0x69},
		//[4]=0 PLL root divider /1, [3:0]=5 PLL pre-divider /1.5
		{0x3037, 0x05},
		//[5:4]=01 PCLK root divider /2, [3:2]=00 SCLK2x root divider /1, [1:0]=01 SCLK root divider /2
		{0x3108, 0x11},

		//[6:4]=001 PLL charge pump, [3:0]=1010 MIPI 10-bit mode
		{0x3034, 0x1A},

		//[3:0]=0 X address start high byte
		{0x3800, (336 >> 8) & 0x0F},
		//[7:0]=0 X address start low byte
		{0x3801, 336 & 0xFF},
		//[2:0]=0 Y address start high byte
		{0x3802, (426 >> 8) & 0x07},
		//[7:0]=0 Y address start low byte
		{0x3803, 426 & 0xFF},

		//[3:0] X address end high byte
		{0x3804, (2287 >> 8) & 0x0F},
		//[7:0] X address end low byte
		{0x3805, 2287 & 0xFF},
		//[2:0] Y address end high byte
		{0x3806, (1529 >> 8) & 0x07},
		//[7:0] Y address end low byte
		{0x3807, 1529 & 0xFF},

		//[3:0]=0 timing hoffset high byte
		{0x3810, (16 >> 8) & 0x0F},
		//[7:0]=0 timing hoffset low byte
		{0x3811, 16 & 0xFF},
		//[2:0]=0 timing voffset high byte
		{0x3812, (12 >> 8) & 0x07},
		//[7:0]=0 timing voffset low byte
		{0x3813, 12 & 0xFF},

		//[3:0] Output horizontal width high byte
		{0x3808, (1920 >> 8) & 0x0F},
		//[7:0] Output horizontal width low byte
		{0x3809, 1920 & 0xFF},
		//[2:0] Output vertical height high byte
		{0x380a, (1080 >> 8) & 0x7F},
		//[7:0] Output vertical height low byte
		{0x380b, 1080 & 0xFF},

		//HTS line exposure time in # of pixels Tline=HTS/sclk
		{0x380c, (2500 >> 8) & 0x1F},
		{0x380d, 2500 & 0xFF},
		//VTS frame exposure time in # lines
		{0x380e, (1120 >> 8) & 0xFF},
		{0x380f, 1120 & 0xFF},

		//[7:4]=0x1 horizontal odd subsample increment, [3:0]=0x1 horizontal even subsample increment
		{0x3814, 0x11},
		//[7:4]=0x1 vertical odd subsample increment, [3:0]=0x1 vertical even subsample increment
		{0x3815, 0x11},

		//[2]=0 ISP mirror, [1]=0 sensor mirror, [0]=0 no horizontal binning
		{0x3821, 0x00},

		//little MIPI shit: global timing unit, period of PCLK in ns * 2(depends on # of lanes)
		{0x4837, 24}, // 1/84M*2

		//Undocumented anti-green settings
		{0x3618, 0x00}, // Removes vertical lines appearing under bright light
		{0x3612, 0x59},
		{0x3708, 0x64},
		{0x3709, 0x52},
		{0x370c, 0x03},

		//[7:4]=0x0 Formatter RAW, [3:0]=0x0 BGBG/GRGR
		{0x4300, 0x00},
		//[2:0]=0x3 Format select ISP RAW (DPC)
		{0x501f, 0x03},
		{0x5000, 0x06},
		{0x5001, 0x00},

		{SEQUENCE_END, 0x00}
};


struct reginfo cfg_advanced_awb[] =
{
		// Enable Advanced AWB
		{0x3406 ,0x00},
		{0x5192 ,0x04},
		{0x5191 ,0xf8},
		{0x518d ,0x26},
		{0x518f ,0x42},
		{0x518e ,0x2b},
		{0x5190 ,0x42},
		{0x518b ,0xd0},
		{0x518c ,0xbd},
		{0x5187 ,0x18},
		{0x5188 ,0x18},
		{0x5189 ,0x56},
		{0x518a ,0x5c},
		{0x5186 ,0x1c},
		{0x5181 ,0x50},
		{0x5184 ,0x20},
		{0x5182 ,0x11},
		{0x5183 ,0x00},
		{0x5001 ,0x03},

		{SEQUENCE_END, 0x00}
};

int ov5640_read(XIicPs *IicInstance,u16 addr,u8 *read_buf)
{
	u8 reg_addr[2] = {addr >> 8, addr & 0xff};
	int status = i2c_wait_idle(IicInstance);
	if (status != XST_SUCCESS)
		return status;
	status = XIicPs_MasterSendPolled(IicInstance, reg_addr, 2, 0x3c);
	if (status != XST_SUCCESS)
		return status;
	status = i2c_wait_idle(IicInstance);
	if (status != XST_SUCCESS)
		return status;
	status = XIicPs_MasterRecvPolled(IicInstance, read_buf, 1, 0x3c);
	if (status != XST_SUCCESS)
		return status;
	return i2c_wait_idle(IicInstance);
}

int ov5640_write(XIicPs *IicInstance,u16 addr,u8 data)
{

	return i2c_reg16_write(IicInstance,0x3c,addr,data);
}

/* write a array of registers  */
int sensor_write_array(XIicPs *IicInstance, struct reginfo *regarray)
{
	int i = 0;
	int status;
	while (regarray[i].reg != SEQUENCE_END) {
		status = ov5640_write(IicInstance,regarray[i].reg,regarray[i].val);
		if (status != XST_SUCCESS) {
			xil_printf("OV5640 write failed: reg=0x%04x value=0x%02x status=%d\r\n",
				regarray[i].reg, regarray[i].val, status);
			return status;
		}
		i++;
	}
	return XST_SUCCESS;
}

static int sensor_verify_raw_mode(XIicPs *IicInstance)
{
	static const struct reginfo expected[] = {
		{0x3034, 0x1a}, /* MIPI RAW10 */
		{0x3808, 0x05}, {0x3809, 0x00}, /* 1280 */
		{0x380a, 0x02}, {0x380b, 0xd0}, /* 720 */
		{0x4300, 0x00}, /* RAW, BGGR */
		{0x5000, 0x06}, /* BPC/WPC, no sensor CIP */
		{0x5001, 0x00}, /* no color ISP on RAW */
		{0x501f, 0x03}, /* ISP RAW(DPC) */
		{SEQUENCE_END, 0x00}
	};
	u8 value = 0;
	int i;
	int status;

	for (i = 0; expected[i].reg != SEQUENCE_END; ++i) {
		value = 0;
		status = ov5640_read(IicInstance, expected[i].reg, &value);
		if (status != XST_SUCCESS || value != expected[i].val) {
			xil_printf("OV5640 RAW mode verify failed: reg=0x%04x read=0x%02x expected=0x%02x status=%d\r\n",
				expected[i].reg, value, expected[i].val, status);
			return XST_FAILURE;
		}
	}
	xil_printf("OV5640 RAW10 verified: 1280x720 BGGR, DPC only\r\n");
	return XST_SUCCESS;
}

int sensor_configure(XIicPs *IicInstance)
{
	u8 sensor_id[2] ;
	int status;
	status = ov5640_read(IicInstance, 0x300A, &sensor_id[0]);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 ID high read failed: %d\r\n", status);
		return XST_FAILURE;
	}
	status = ov5640_read(IicInstance, 0x300B, &sensor_id[1]);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 ID low read failed: %d\r\n", status);
		return XST_FAILURE;
	}

	if (sensor_id[0] != 0x56 || sensor_id[1] != 0x40)
	{
		xil_printf("Not ov5640 id, %x %x\r\n", sensor_id[0], sensor_id[1]);
		return XST_FAILURE;
	}
	else
	{
		xil_printf("Got ov5640 id, %x %x\r\n", sensor_id[0], sensor_id[1]);
	}

	//[1]=0 System input clock from pad; Default read = 0x11
	status = ov5640_write(IicInstance,0x3103,0x11);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 write failed: reg=0x3103 status=%d\r\n", status);
		return XST_FAILURE;
	}
	//[7]=1 Software reset; [6]=0 Software power down; Default=0x02
	status = ov5640_write(IicInstance,0x3008, 0x82);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 write failed: reg=0x3008 value=0x82 status=%d\r\n", status);
		return XST_FAILURE;
	}

	usleep(1000000);

	status = sensor_write_array(IicInstance,sensor_init_data);
	if (status != XST_SUCCESS) return XST_FAILURE;
	usleep(1000000);
	//[7]=0 Software reset; [6]=1 Software power down; Default=0x02
	status = ov5640_write(IicInstance,0x3008, 0x42);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 write failed: reg=0x3008 value=0x42 status=%d\r\n", status);
		return XST_FAILURE;
	}
	//720p 60fps
	status = sensor_write_array(IicInstance,cfg_720p_60fps);
	if (status != XST_SUCCESS) return XST_FAILURE;
	//1080p 30fps
	//sensor_write_array(IicInstance,cfg_1080p_30fps);

	/* Do not enable the sensor AWB/CCM while FORMAT_MUX selects RAW(DPC). */
	status = sensor_verify_raw_mode(IicInstance);
	if (status != XST_SUCCESS) return XST_FAILURE;

	/* Leave the sensor in standby until the capture VDMA is ready. */
	return XST_SUCCESS;
}

int sensor_start(XIicPs *IicInstance)
{
	u8 control;
	int status;
	//[7]=0 Software reset; [6]=0 Software power down; Default=0x02
	status = ov5640_write(IicInstance,0x3008, 0x02);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 write failed: reg=0x3008 value=0x02 status=%d\r\n", status);
		return XST_FAILURE;
	}

	status = ov5640_read(IicInstance, 0x3008, &control);
	if (status != XST_SUCCESS) {
		xil_printf("OV5640 0x3008 read failed: %d\r\n", status);
		return XST_FAILURE;
	}
	xil_printf("OV5640 0x3008 = 0x%02x (expected 0x02)\r\n", control);
	return control == 0x02 ? XST_SUCCESS : XST_FAILURE;
}

/* Preserve the original configure-and-start API for other callers. */
int sensor_init(XIicPs *IicInstance)
{
	int status = sensor_configure(IicInstance);
	return status == XST_SUCCESS ? sensor_start(IicInstance) : status;
}
