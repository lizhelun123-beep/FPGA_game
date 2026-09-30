# 工具脚本

以下脚本均从 `color_test` 目录运行。

## 构建与下载

- `build_bitstream.tcl`：综合、实现、生成 bitstream 和 XSA，并输出时序及资源报告。
- `build_camera_recovery.tcl`：根据 XSA 创建 Vitis 平台并构建恢复版裸机应用。
- `program_camera_jtag.tcl`：完整配置 PL、初始化 PS、下载恢复版 ELF 并运行。
- `run_camera_recovery.tcl`：PL 已配置时，只复位 CPU 并重新下载恢复版 ELF。

## 硬件诊断

- `check_jtag.tcl`：列出 JTAG targets，确认 APU、Cortex-A9 和 FPGA 可见。
- `check_hdmi.tcl`：读取显示 VDMA、像素时钟、VTC、帧缓冲、摄像头 VDMA 和 CSI 计数。
- `check_cpu_pc.tcl`：短暂停止 Cortex-A9 #0，读取 PC/CPSR 后继续运行。

## 工程维护

- `migrate_integrate.tcl`：把颜色高亮模块接入视频 AXI4-Stream 数据通路。
- `refresh_mipi_ip.tcl`：刷新迁移后的 MIPI IP。
- `rebuild_debug_hub.tcl`：重建使用 PS FCLK0 的调试核并导出硬件平台。
- `export_xsa.tcl`：从当前实现导出 XSA。
- `inspect_*.tcl`、`list_ipdefs.tcl`、`check_ip_status.tcl`：工程结构与 IP 状态检查。

需要先启动 `hw_server` 才能运行 JTAG 脚本。工具安装位置由 PowerShell 中的
`XILINX_VIVADO` 和 `XILINX_VITIS` 环境变量决定；Tcl 脚本内部不包含开发机绝对路径。
