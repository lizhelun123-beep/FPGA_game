# FPGA 机器视觉项目

本仓库包含 AX7Z020B（Zynq-7020B）机器视觉工程、OV5640 MIPI 摄像头软件、
颜色高亮 RTL、Vivado/Vitis 自动化脚本，以及 Portal 交互原型和设计文档。

## 主要目录

- `color_test/`：可上板运行的 OV5640 MIPI 到 HDMI 工程。
- `color_test/rtl/`：AXI4-Stream 颜色高亮模块。
- `color_test/software/`：Cortex-A9 裸机摄像头和显示应用源码。
- `color_test/tools/`：Vivado 构建、Vitis 构建、JTAG 下载和硬件诊断脚本。
- `color_test/sim/`：RTL 与摄像头恢复流程测试。
- `doc/`：方案、调研和板上故障排查记录。
- `portal-showcase/`：浏览器交互原型。

## 当前硬件版本

目标硬件为 AX7Z020B、OV5640 MIPI 摄像头和 HDMI 显示设备。工程使用
Vivado/Vitis 2023.1，目标器件为 `xc7z020clg400-2`。

完整的 Vivado/Vitis GUI、XSCT 终端、QSPI 固化、SD 卡裸机启动和 PYNQ 烧录说明见
[`doc/AX7Z020B_烧录指南/00_烧录方式总览.md`](doc/AX7Z020B_烧录指南/00_烧录方式总览.md)。

摄像头恢复版软件会先显示 5 秒诊断彩条，再按“摄像头保持待机完成配置、启动采集
VDMA、最后开始 MIPI 输出”的顺序启动。程序持续检查 CSI 长包、CRC 和 VDMA 状态，
异常时最多重试三次。

板上验证已经确认恢复版可以在 Reset 后重新获得摄像头数据：CSI 长包计数持续增长、
CRC 错误为 0，采集和显示 VDMA 均正常运行。详细构建和下载步骤见
[`color_test/README.md`](color_test/README.md)，故障分析见
[`doc/AX7Z020B_OV5640_复位恢复说明.md`](doc/AX7Z020B_OV5640_复位恢复说明.md)。

## Git 仓库说明

仓库提交源码、约束、Block Design、可复现构建脚本和文档。Vivado/Vitis 工作区、
bitstream、ELF、XSA 和 BOOT.bin 均为可重建产物，由 `.gitignore` 排除。需要发布可直接
烧录的文件时，建议把 `system_wrapper.bit`、`camera_recovery.elf` 和 `BOOT.bin` 作为
GitHub Release 附件上传，并注明对应提交和 Vivado/Vitis 版本。
