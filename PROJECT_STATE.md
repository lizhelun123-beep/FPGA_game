你好，

以下是截至 2026 年 9 月 24 日，AX7Z020B（Zynq-7020B）+ OV5640 MIPI 摄像头到 HDMI 例程的排查记录。

主要问题与现象
此前启动后 HDMI 无摄像头画面，曾出现黑屏；加入 5 秒彩条诊断后，彩条能够正常显示，而且在异常运行中会一直留在屏幕上。这说明显示输出通路能工作，当时没有新的摄像头画面覆盖帧缓冲区。
串口能读到 OV5640 ID 56 40，寄存器 0x3008 = 0x02，说明 I²C 控制通道可用，但不能单独证明 MIPI 视频数据正常。
异常运行时，CSI 长包计数为 0 → 0，CRC 错误为 0；ILA 的视频输入有效信号为 0，部分采样曾提示 Lane 时钟停止。另一次运行中，两条 Lane 都观察到高速活动，2 秒内收到 43,179 个 CSI 长包且 CRC 错误为 0。链路表现具有间歇性。
在镜像、排线和供电均未更改的情况下，仅按板上 Reset 后，当前例程恢复正常工作。
目前判断
故障更接近摄像头 MIPI 输入或启动初始化阶段，而不是持续性的 HDMI 输出故障。Reset 能恢复，说明排线或摄像头并非永久失效；但现有证据不足以区分上电/复位时序、接头偶发接触问题或接收端状态异常。此前的 HW Target shutdown 属于调试连接中断，不能直接当作摄像头故障证据。

后续复现时建议记录
分别做数次冷上电和 Reset 测试，保留每次的串口启动日志、CSI long packets 前后计数、CRC 错误、VDMA S2MM 状态和 HDMI 画面状态，并记下所按复位键的标识。若稳定出现“冷上电无长包、Reset 后有长包”，再优先检查复位与初始化时序。

另：当前实现报告中，CSI IP 内置 ILA 有跨时钟路径违例（WNS 约 -2.913 ns）；尚无证据表明它就是此次黑屏原因。

2026-09-24 代码修改与验证

已将摄像头配置和出图拆分为 sensor_configure()/sensor_start()：保持待机完成配置，采集 VDMA 启动后再出图。启动及运行异常后的恢复各最多尝试 3 次；每 2 秒检查 CSI 长包增长、CRC 增量、VDMA 错误和新帧完成状态。VDMA 复位设置 1 秒超时，复位失败立即退出；重试耗尽后，在确认采集已停止的前提下恢复诊断彩条。未增加自定义 D-PHY/CSI IP 的软件复位。

同时补齐采集 VDMA 配置结构和所有帧地址槽的初始化，增加摄像头 I2C 写入后的总线空闲等待超时，以及 GPIO/显示初始化错误处理。

Vitis 2023.1 ARM 编译通过；15 项主机故障注入检查通过（仅验证软件流程）。可重建脚本为 color_test/tools/build_camera_recovery.tcl，测试脚本为 color_test/sim/test_camera_recovery.py。应用位于 color_test/build/camera_recovery/output/camera_recovery.elf，独立 SD 镜像位于 color_test/sd_boot/recovery/BOOT.bin；原有 ELF 和 sd_boot/BOOT.bin 未覆盖。

Bootgen 已生成新镜像，回读确认包含 FSBL、bitstream 和新应用；应用及 FSBL 分区数据与本次 ELF 一致。打包有涉及 bitstream 的内存范围重叠警告；回读中 bitstream 分区属性为 0x20，FSBL 与应用加载地址分别为 0x0、0x100000。XSA 内 bitstream 与实现输出一致。尚未上板验证，不能据此认定间歇性故障已解决。

上板先确认串口出现 Camera recovery v1，再记录 Camera capture ready on attempt N、CSI/CRC 和帧完成状态，分别做 10 次冷启动与 10 次 Reset 测试。

2026-09-24 Reset 后实板复测与仓库整理

按 Reset 后，显示 VDMA、动态像素时钟和 1280x720 VTC 时序仍正常，帧缓冲保留诊断彩条；CSI 长包计数为 0，说明停止的是摄像头输入链，而不是 DDR 或 HDMI 内部显示链。CPU 停在 0x0010b4c0；读取板上指令并与 ELF 符号比对后，确认它是旧版 mipi_hdmi.elf 的 _exit 循环。旧版应用只执行一次诊断后返回，没有运行中恢复功能。

已通过 JTAG 下载 camera_recovery.elf，CSI 长包计数恢复增长且 CRC 为 0。随后新增并实板验证 tools/program_camera_jtag.tcl：该脚本完成 bitstream 配置、PS 初始化和恢复版 ELF 下载。完整下载后，CSI 计数在 500 ms 内从 0x000F7904 增加到 0x000FA5A1，采集和显示 VDMA 均正常。

GitHub 版本已在 FPGA-main/FPGA-main 内整理：新增根 README、复位恢复说明和可移植 JTAG 脚本；run_camera_recovery.tcl 已移除本机绝对路径；.gitignore 排除 build、BIT、ELF、XSA、BOOT.bin 等生成产物。可直接提交的源码与文档约 190 个文件，最大候选文件为 3.07 MB，没有误包含 Vitis 构建工作区。

## 2026-09-29 RAW ISP、绿屏与虚焦修复

本轮复核确认视频链实际为 `OV5640 RAW10 -> CSI-2 -> BayerToRGB -> Gamma ->
axis_color_highlight -> VDMA -> HDMI`。OV5640 的 `0x4300=0x00` 对应 BGGR，而原
`AXI_BayerToRGB` 以 RGGB 选择红蓝通道，造成红蓝互换及明显偏色；同时传感器端开启 CIP，
但 PL 又进行去马赛克，RAW 和 RGB ISP 的职责不清。原链路只有去马赛克和 Gamma，没有白平衡。

已完成以下修改：

- 修正 `AXI_BayerToRGB.vhd` 的红蓝 Bayer 相位，使其与 OV5640 BGGR 输出一致。
- OV5640 固定使用 1280×720 RAW10 BGGR，设置 `0x5000=0x06`、`0x5001=0x00`、
  `0x501f=0x03`，禁用传感器 CIP/颜色 ISP，只保留坏点/白点修正；启动时读回 RAW10、
  尺寸、Bayer 相位及 ISP 寄存器，不匹配即停止。
- 在 PL RGB 路径增加定点白平衡基线：R/B 为 1.5 倍、G 为 1 倍并饱和到 8 bit，之后再做
  颜色高亮。实现采用移位加法和两级弹性 AXI 流水线，视频时钟域 WNS 为 +0.551 ns；最终
  增益仍应以灰卡实拍标定。
- Gamma 固定为 1.8；`AXI_GammaCorrection` 的 AXI-Lite 读接口固定返回 0，软件只写入
  Gamma 选择值，不再用读回值作启动失败条件。启动日志升级为 `Camera recovery v2`，明确
  打印 RAW/ISP 配置和定焦镜头机械调焦提示。
- `build_camera_recovery.tcl` 在复用 Vitis platform 时强制更新 XSA；
  `build_bitstream.tcl` 强制刷新 Bayer 与颜色模块的 OOC 综合结果，避免顶层 BIT 沿用旧 DCP。
- `program_camera_jtag.tcl` 在连接硬件前校验 BIT、XSA、PS 初始化文件与 ELF 的存在性和
  修改时间，任一产物过期就拒绝烧录；设置 `CAMERA_JTAG_CHECK_ONLY=1` 可只检查产物而不上板。

软件故障注入测试共 15 项通过；颜色高亮 RTL 共 17 项通过；新增 ISP RTL 检查覆盖中灰、
近黑和饱和白平衡结果。Vivado 2023.1 已重新综合 Bayer/颜色 OOC IP，并进行完整顶层重建；
最终实现时序与产物状态见 `color_test/reports/post_impl_timing.rpt`；视频域 WNS 为 +0.551 ns，
CSI ILA 跨时钟路径仍有 -2.676 ns 既有违例。

严重“虚焦”不是 RAW 颜色矩阵能够修复的问题。若当前为常见定焦 OV5640 模组，需要松开胶或
固定环后旋转镜头，以远处高反差边缘为目标机械调焦；若模组确实带 VCM，则还必须确认 VCM
供电并加载对应 AF 固件后才能发自动对焦命令。本轮没有在未知模组类型下写入 AF 固件，避免
错误驱动硬件。最终 BIT/XSA/ELF 新鲜度检查已通过，完整 JTAG 下载已成功返回；由于当前环境
未枚举出串口设备，尚未读取 `OV5640 RAW10 verified`、CSI long packets、CRC 与 VDMA 状态，
仍需人工观察 HDMI 画面并完成冷启动/Reset 验收。

## 2026-09-29 Gamma 读回校验修正

复核发现此前新增的 Gamma 读回校验错误地要求 AXI-Lite 读回 `3`。该 IP 的读数据在 RTL
中固定为 `0`，`3` 是 1/1.8 Gamma 的写入选择值，不是可读回的寄存器值。已移除错误的
读回比较，保留 Gamma 选择值写入，并增加回归检查，避免程序在摄像头和 HDMI 初始化前
误退出。该修正尚未替代真实上板验证；仍需观察串口日志并完成冷启动/Reset 验收。

## 2026-09-30 Bayer 相位与颜色顺序实板验收

本轮只修改实际参与综合的 generated BayerToRGB 源码：按当前 OV5640 翻转/裁剪后的
有效 RGGB 相位选择 `sPixel(0..3)`，不再让后级 RGB/BGR 交换补偿 Bayer phase。
`axis_subset_converter_0` 已恢复恒等映射，保持 AXI4-Stream `TDATA[23:16]=R`、
`TDATA[15:8]=G`、`TDATA[7:0]=B`。

Vivado 2023.1 已重新完成 BayerToRGB 与 subset converter 的 OOC 综合，均为 0 errors；
综合日志确认 Bayer 实际读取 `color_test.gen/sources_1/bd/system/ipshared/e9e4/hdl/AXI_BayerToRGB.vhd`。
重新下载该版本后，OV5640 HDMI 画面颜色已实板确认正确，红、蓝通道不再互换。
本记录只代表当前 bitstream 的颜色验收，不替代后续冷启动/Reset 稳定性测试。
