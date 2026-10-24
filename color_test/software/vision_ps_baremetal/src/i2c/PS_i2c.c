#include "xil_printf.h"
#include "PS_i2c.h"
#include "sleep.h"

int i2c_wait_idle(XIicPs *InstancePtr)
{
	u32 count;
	for (count = 0; count < 1000; ++count) {
		if (!XIicPs_BusIsBusy(InstancePtr)) return XST_SUCCESS;
		usleep(1000);
	}
	xil_printf("Camera I2C bus busy timeout\r\n");
	return XST_FAILURE;
}

int i2c_reg8_write(XIicPs *InstancePtr, char IIC_ADDR, char Addr, char Data)
{
	int Status;
	u8 SendBuffer[2];

	SendBuffer[0] = Addr;
	SendBuffer[1] = Data;
	Status = XIicPs_MasterSendPolled(InstancePtr, SendBuffer, 2, IIC_ADDR);
	while (XIicPs_BusIsBusy(InstancePtr));

	return Status;
}

char i2c_reg8_read(XIicPs *InstancePtr, char IIC_ADDR, char Addr)
{
	u8 wr_data, rd_data;

	wr_data = Addr;
	XIicPs_MasterSendPolled(InstancePtr, &wr_data, 1, IIC_ADDR);
	XIicPs_MasterRecvPolled(InstancePtr, &rd_data, 1, IIC_ADDR);
	while (XIicPs_BusIsBusy(InstancePtr));
	return rd_data;
}

int i2c_reg16_write(XIicPs *InstancePtr, char IIC_ADDR, unsigned short Addr, char Data)
{
	int Status;
	u8 SendBuffer[3];

	SendBuffer[0] = Addr>>8;
	SendBuffer[1] = Addr;
	SendBuffer[2] = Data;
	Status = XIicPs_MasterSendPolled(InstancePtr, SendBuffer, 3, IIC_ADDR);
	if (Status != XST_SUCCESS) return Status;
	Status = i2c_wait_idle(InstancePtr);

	return Status;
}

char i2c_reg16_read(XIicPs *InstancePtr, char IIC_ADDR, unsigned short Addr)
{
	u8 rd_data;
	u8 SendBuffer[2];

	SendBuffer[0] = Addr>>8;
	SendBuffer[1] = Addr;
	XIicPs_MasterSendPolled(InstancePtr, SendBuffer, 2, IIC_ADDR);
	XIicPs_MasterRecvPolled(InstancePtr, &rd_data, 1, IIC_ADDR);
	while (XIicPs_BusIsBusy(InstancePtr));
	return rd_data;
}



int i2c_init(XIicPs *Iic,short DeviceID ,u32 IIC_SCLK_RATE)
{
	XIicPs_Config *Config;
	int Status;

	Config = XIicPs_LookupConfig(DeviceID);
	if (NULL == Config) {
		xil_printf("XIicPs_LookupConfig failure\r\n");
		return XST_FAILURE;
	}

	Status = XIicPs_CfgInitialize(Iic, Config, Config->BaseAddress);
	if (Status != XST_SUCCESS) {
		xil_printf("XIicPs_CfgInitialize failure\r\n");
		return XST_FAILURE;
	}
	Status = XIicPs_SetSClk(Iic, IIC_SCLK_RATE);
	if (Status != XST_SUCCESS) return Status;
	return i2c_wait_idle(Iic);
}

