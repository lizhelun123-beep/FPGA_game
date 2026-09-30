# AX7Z020B OV5640 MIPI 颜色识别验证

Vivado/Vitis 2023.1 GUI、XSCT 终端、QSPI 固化、SD 卡裸机启动以及 PYNQ 2.6.0
镜像/Overlay 的完整操作说明见
[`../doc/AX7Z020B_烧录指南/00_烧录方式总览.md`](../doc/AX7Z020B_烧录指南/00_烧录方式总览.md)。

本工程基于官方 `22_an5641_mipi_hdmi` 示例迁移到 Vivado 2023.1，目标器件为
`xc7z020clg400-2`。视频链路保持为：

`OV5640 RAW10 -> D-PHY -> CSI-2 -> 有效 RGGB 去马赛克 -> Gamma -> 白平衡 -> 颜色高亮 -> VDMA -> DDR -> VDMA -> HDMI`

颜色高亮模块位于 `axis_subset_converter_0` 与采集端 `axi_vdma_1` 之间；subset converter
采用 RGB 恒等映射，不交换 R/B，后级输入保持 `TDATA[23:16]=R`、`[15:8]=G`、`[7:0]=B`。
颜色高亮本身采用两级弹性 AXI4-Stream 流水线，保持 `TVALID/TREADY/TKEEP/TUSER/TLAST` 对齐。

## 颜色规则

输入为去马赛克、Gamma 和白平衡后的 RGB888，`TDATA[23:16]`、`TDATA[15:8]`、
`TDATA[7:0]` 分别为 R、G、B。

- 蓝色：`B >= 100 && 2B >= 3R && 2B >= 3G`，输出 `0080FF`。
- 红色：`R >= 120 && R >= 2G && R >= 2B`，输出 `FF0000`。
- 橙色：`R >= 140 && G >= 70 && R > G && 2G > R && G >= 2B`，输出 `FF8000`。
- 其余像素保持不变。

阈值在 `rtl/axis_color_highlight.v` 的参数区，可重新综合后调整。

## 构建与验证

在仓库根目录执行：

```powershell
& "$env:XILINX_VIVADO\bin\vivado.bat" -mode batch `
  -source .\color_test\tools\build_bitstream.tcl
```

主要输出：

- bitstream：`color_test.runs/impl_1/system_wrapper.bit`
- 硬件平台：`color_test.xsa`
- 时序报告：`reports/post_impl_timing.rpt`
- 资源报告：`reports/post_impl_utilization.rpt`

当前自检结果：

- 颜色/AXI RTL 仿真：17 项检查，0 失败；白平衡中灰、近黑和饱和检查通过；
- 摄像头故障注入检查：15 项通过；
- BD 校验通过，20 个 IP 均未锁定；
- bitstream 生成成功；
- 视频处理时钟域 `clk_fpga_1` WNS `+0.551 ns`；全局 CSI ILA 跨时钟路径仍有
  `-2.676 ns` 既有违例，详见 `reports/post_impl_timing.rpt`。

## 首次上板建议

1. 连接 OV5640 MIPI、HDMI 显示器和 JTAG，开发板使用 JTAG 启动模式。
2. 在 Vivado Hardware Manager 中下载
   `color_test.runs/impl_1/system_wrapper.bit`。
3. 在 Vitis 2023.1 中以 `color_test.xsa` 创建或更新硬件平台，初始化 PS 后，将
   `software/mipi_hdmi/mipi_hdmi.elf` 下载到 Cortex-A9 #0 并运行。
4. 依次放置纯红、纯蓝和橙色色卡，确认 HDMI 图像中的目标颜色被替换为固定高亮色，
   其他区域保持原图。

旧版 `software/mipi_hdmi/mipi_hdmi/Debug/mipi_hdmi.elf` 只执行一次摄像头诊断，
随后会从 `main()` 返回，不能用于验证复位恢复。请构建并使用
`build/camera_recovery/output/camera_recovery.elf`。

### JTAG 下载

首次下载或完全断电后，在 `color_test` 目录执行完整下载脚本。脚本依次配置 PL、初始化
PS、下载恢复版 ELF，并运行 Cortex-A9 #0：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" tools/program_camera_jtag.tcl
```

如果只是按了处理器 Reset，且 PL 中的 bitstream 仍然存在，可以只重新下载 ELF：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" tools/run_camera_recovery.tcl
```

这两个脚本均使用相对路径。`program_camera_jtag.tcl` 要求先生成 bitstream 和
`camera_recovery.elf`。

## SD 卡启动（可选）

恢复版启动镜像由 `sd_boot/recovery/boot.bif` 描述，依次包含：

1. `build/camera_recovery/camera_platform/zynq_fsbl/fsbl.elf`；
2. `color_test.runs/impl_1/system_wrapper.bit`；
3. `build/camera_recovery/output/camera_recovery.elf`。

完成硬件和软件构建后，在 `sd_boot/recovery` 目录运行：

```powershell
& "$env:XILINX_VITIS\bin\bootgen.bat" -arch zynq -image boot.bif -o BOOT.bin -w on
```

将 MicroSD 卡的启动分区格式化为 FAT32，把 `sd_boot/recovery/BOOT.bin` 复制到分区根目录。
断电后插卡，按 AX7Z020B 板卡上的启动模式跳线/丝印切换到 SD 启动，再上电。
串口使用 115200 波特率观察 FSBL 和应用日志，同时检查 HDMI 摄像头画面及颜色高亮。
当前版本已完成 JTAG 下载后的 HDMI 颜色实板验收，红、蓝通道显示正确；SD 启动和多轮
冷启动/Reset 稳定性仍需单独记录。

### CSI 调试核时钟

`color_test.srcs/constrs_1/new/debug_hub.xdc` 将 `dbg_hub` 接至 PS FCLK0（100 MHz）。
此前自动连接的时钟来自 MIPI 高速时钟；摄像头无输出时，Hardware Manager 无法检测到调试核。
使用 ILA 时，必须下载同一次实现生成的 `system_wrapper.bit` 和 `system_wrapper.ltx`。
本次实现的 USER 扫描链为 1，可在 Hardware Manager 的 Tcl Console 中设置
`set_property BSCAN_SWITCH_USER_MASK 1 [get_hw_devices xc7z020_1]` 后刷新设备。
新的 bitstream 已通过完整 JTAG 下载脚本写入已连接板卡；时序报告中仍有 CSI IP
内置 ILA 的跨时钟路径违例，视频处理时钟域满足约束。

## 摄像头串口诊断

应用源码位于 `software/mipi_hdmi/mipi_hdmi/src/`。修改后运行
`tools/build_camera_recovery.tcl`，再按上面的命令重新生成
`sd_boot/recovery/BOOT.bin`；仅下载 bitstream 不会更新这些串口打印。

上电后观察 `OV5640 0x3008`、`CSI long packets` 和 `Camera VDMA S2MM status`：

串口连接沿用官方例程的 PS UART1（115200 波特率）；新镜像启动时应先看到
`Camera recovery v2` 和 `OV5640 RAW10 verified: 1280x720 BGGR, DPC only`。
当前诊断镜像在启动显示后先输出彩条 5 秒，串口会打印 `HDMI color bars for 5 seconds`，
然后才初始化摄像头。彩条能显示而摄像头画面黑，说明 HDMI 输出通路可以工作，继续检查摄像头输入。
彩条也看不到时，先检查显示器输入源、HDMI 连接和显示输出通路。

- `0x3008 = 0x02` 表示传感器寄存器读回正常且已退出软件待机，但不能单独证明 MIPI 视频链路正常。
- 两秒内 `CSI long packets` 增加，表示 CSI 接收端看到了完整视频长包；不增加时结合 `CRC errors` 和 VDMA 状态继续检查摄像头时钟、MIPI 排线和接收链路。没有长包时，`CRC errors = 0` 不能说明链路正常。
- `OV5640 write failed` 会给出失败的寄存器地址；此时先检查 I²C 与摄像头供电。

## 迁移说明

### 摄像头启动恢复版本（2026-09-24）

`sensor_configure()` 完成寄存器配置后保持待机，采集 VDMA 就绪后由
`sensor_start()` 开始出图。每次启动或运行中恢复最多尝试 3 次；每个 2 秒
观察窗口要求 CSI 长包增长、CRC 无新增错误、VDMA 无错误且出现新的帧完成状态。
正常运行时持续检查，检测失败会打印计数和状态并重启采集。
VDMA 复位等待上限为 1 秒，复位失败立即停止恢复；尝试耗尽后若能成功停止
采集，则重新绘制诊断彩条。此版本不复位自定义 D-PHY/CSI 接收 IP。

同时初始化采集 VDMA 的全部帧地址槽，并为摄像头 I2C 写入后的总线空闲等待
增加超时。软件重试不能代替对摄像头参考时钟、接收 IP 复位与排线的板上检查。

从 `color_test` 目录运行（按实际安装位置调整工具路径）：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" tools/build_camera_recovery.tcl
python sim/test_camera_recovery.py
Push-Location sd_boot/recovery
& "$env:XILINX_VITIS\bin\bootgen.bat" -arch zynq -image boot.bif -o BOOT.bin -w on
Pop-Location
```

脚本在 `build/camera_recovery` 生成 BSP，并直接编译仓库源码，应用输出为
`build/camera_recovery/output/camera_recovery.elf`。它使用仓库已有的修正
Makefile 覆盖 XSA 内旧 MIPI 驱动的 Windows 通配符写法。
故障注入测试需要主机 GCC，验证软件流程，不模拟真实 MIPI/VDMA 硬件。

SD 启动请使用 `sd_boot/recovery/BOOT.bin`；旧的 `sd_boot/BOOT.bin` 和
`software/mipi_hdmi/mipi_hdmi/Debug/mipi_hdmi.elf` 不会被本构建覆盖。
新版本串口应出现 `Camera recovery v2`、`Camera start attempt 1/3`，成功后
打印 `Camera capture ready on attempt N`。JTAG 上板验证中，CSI 长包计数在 500 ms
内从 `0x000638E0` 增长到 `0x000667B0`，CRC 错误保持为 0，采集 VDMA 正常完成帧传输。
仍建议分别做 10 次冷启动和 10 次 Reset，记录首次成功、重试成功和最终失败次数。

Vivado 2023.1 会把官方 MIPI CSI-2 IP 内部的 `axis_data_fifo` 从 1.1 升级到 2.0。
新版将同步 FIFO 的计数端口拆分为读/写计数端口，本工程在
`repo/ip/MIPI_CSI_2_RX/hdl/LLP.vhd` 中改用 `axis_rd_data_count`，其余 CSI-2 数据路径
未修改。

官方 IP 自带的 ILA 和旧版 HDMI/MIPI 时钟约束在 2023.1 下会产生若干 Critical
Warning；它们未阻止 DRC、布局、布线或 bitstream 生成，且已约束的时序路径全部满足。
目前时序报告中 CSI IP 内置 ILA 的跨时钟路径未满足约束；首次上板仍需观察
MIPI 锁定、图像稳定性和 HDMI 输出，才能完成物理验证。
