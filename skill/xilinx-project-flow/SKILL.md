---
name: xilinx-project-flow
description: 路由当前仓库实际涉及 Vivado、Vitis、XSCT、制品交接或板端运行的 Xilinx/AMD 工具链任务，核对版本、入口和同源制品；纯定位、光路配置与电脑界面不进入硬件流程。
---

# Xilinx 工程流程

本 skill 是当前仓库的工具链入口。实际任务涉及 Vivado、Vitis、XSCT、XSA、BIT、XDC、Block Design、IP、AXI/VDMA、JTAG 或 Linux/PS 硬件交接时使用。单纯提及 PYNQ、修改固定逻辑光源、Portal 软件定位或电脑 Godot 界面，不构成进入硬件流程的理由。它负责定位已有入口、确认前置条件和整理可复现输出；不复制工程，不因调用就获得板端或完整 Vivado 构建授权。

## 当前工程基线

- 目标板为 AX7Z020B，器件为 `xc7z020clg400-2`；源码和脚本按 Vivado/Vitis 2023.1 维护。若用户指定了别的器件或版本，先标出不兼容风险，不把本地默认值静默套用。
- 采集契约保持两 lane、1280×720、RAW10/BGGR；最终 HDMI 和电脑画布均为 1280×720、16:9。1280×800 屏幕保持比例显示；分辨率一致不能替代缓冲、格式、stride 和所有权检查。
- Linux/PYNQ 优先复用现有镜像、采集和原生 C/C++；电脑虚拟游戏使用已有 Godot 呈现与 NativeGame 权威桥接，不为完成美术在 PYNQ 上新增全虚拟渲染器。不能假设 PetaLinux、X Desktop、DRM、`/dev/fb0` 或自定义设备树已经可用。
- 固定关卡光源、已改的 Portal 三标签和软件职责按 `pc_vision/FINAL_PLAN.md`；它们本身不要求更换 BIT/HWH/BOOT 或相机模式。
- 当前目标、授权边界和未通过项以仓库根目录 `AGENTS.md` 与 `PROJECT_STATE.md` 的 `Current Goal`、`Delivery Gates and Next Task` 为准。历史 BIT、XSA、HWH、ELF、BOOT 或截图不能替代当前制品证据。

## 阶段路由

先判断用户要回答的是哪一个问题，再只读取对应入口和参考文件：

| 阶段 | 当前入口 | 最小输入/输出 |
| --- | --- | --- |
| 工程、BD、IP、XDC、综合/实现 | `color_test/tools/build_bitstream.tcl`、`migrate_integrate.tcl`、`refresh_mipi_ip.tcl`、`export_xsa.tcl` | 先核对 `color_test/README.md`、`color_test/tools/README.md`、实际 BD/IP/XDC；输出明确的 BIT/XSA/报告身份 |
| 结构/IP/约束只读检查 | `inspect_*.tcl`、`list_ipdefs.tcl`、`check_ip_status.tcl`、`check_vivado_runtime.tcl` | 先用静态或单寄存器探针区分工具启动问题与工程问题，不自动进入完整构建 |
| D-PHY、CSI、AXI、Bayer、CDC、时序或制品门禁 | `color_test/tools/camera_production*.tcl`、相关 `sim/` 入口 | 同时使用 `fpga-verification-gates`；先做源/参数/约束核对，再决定是否需要 OOC 或实现 |
| PS/Vitis/裸机 | `color_test/tools/build_vitis*.tcl`、`color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl`、`build_camera_recovery.tcl` | 核对 XSA、处理器、sysroot/ABI、链接产物和其对应硬件代次 |
| JTAG、下载、HDMI 或实时板测 | `program_*jtag.tcl`、`check_jtag.tcl`、`check_hdmi.tcl` 及当前任务指定工具 | 需要用户当前任务的硬件授权；一次有界运行，记录输入制品、目标、停止/清理结果 |
| Linux 游戏、采集/显示 owner、PYNQ 缓冲 | `color_test/software/vision_ps_baremetal/src/`、`color_test/software/vision_ps_baremetal/tools/`、`pynq_vision/` 现有入口 | 需要时加载 `pynq-dma-contract`；若问题是帧率/延迟/新鲜度，再加载 `stream-perf-analysis` |

不要把外部项目建议的 `01_hls/02_vivado/03_vitis/04_petalinux` 目录结构复制到本仓库；当前工程的 `color_test/`、`pynq_vision/` 和既有脚本才是规范入口。HLS 或 PetaLinux 只有用户明确提出且仓库存在实际输入时才新增路由。

## 生成或执行脚本前

1. 记录目标、阶段、器件/板卡、Vivado/Vitis 版本、输入制品、预期输出和可能的外部副作用。缺少这些信息时，先从源码、脚本和状态文件读取；仍无法确定的项写 `UNKNOWN`，不要猜地址、时钟、IP 版本或设备所有权。
2. 先阅读与当前阶段对应的仓库文档和脚本，再生成 Tcl/XSCT/Python/Make 命令。不同版本的 Tcl API、IP 参数和 `write_hw_platform` 语义不能凭记忆混用。
3. 检查 `git status` 并保留用户已有修改。删除旧版前保存包含实际待移除内容的 Git 提交，未提交/未跟踪文件也须纳入；已归档不代表允许删除仍在使用的采集/DMA。不要 reset、覆盖生成源、删除失败账本或用改名目录绕过次数/准入限制。
4. 沿来源建立制品链：源码/BD/IP/XDC → 实现 → BIT/HWH/XSA → ELF/BOOT/运行时。只有同一配置、同一代次且能由路径或哈希绑定的制品才可交接；文件名和时间戳单独不算证据。
5. 选择能回答问题的最便宜检查：静态/语法、host 回放、单元/最小仿真、ARM 编译，再到 OOC/完整实现，最后才是板端。完整 Vivado、JTAG、复位、SD 写入和服务改动按 `AGENTS.md` 需要明确授权。
6. 同一原因连续两次没有新信息就停止该路径，保留失败原因和最小下一步；不扫参、不放宽阈值、不用下游换色或旧截图掩盖上游错误。

## 输出契约

当本 skill 生成或修改脚本时，结果必须说明：

- 文件的绝对或仓库相对路径、调用命令、所需环境变量和工具版本；
- 预期生成的 BIT/XSA/HWH/ELF/报告以及如何绑定到本次输入；
- 已完成的离线、host、ARM 或真实板端验证，并把未覆盖项单独列出；
- 完成这一阶段后的最小下一步，以及仍需用户授权的动作。

脚本本身应失败得早、保留日志并避免开发机绝对路径；已有受控入口优先复用，只有重复逻辑会造成实际错误时才增加 helper。硬件操作完成后确认停止/清理状态，再释放相关资源。

## 相关 skill 与参考

- 固定逻辑光源、Portal 多标签、有效边界、防抖或 Godot 正式桥接：使用 [ray-game-integration](../ray-game-integration/SKILL.md)，按实际改动决定是否还需要本硬件流程。
- 采集/显示 DMA、cache、stride、所有权或安全退出：阅读 [pynq-dma-contract](../pynq-dma-contract/SKILL.md)。
- 实时帧率、处理延迟、新鲜度或遮挡保持期：阅读 [stream-perf-analysis](../stream-perf-analysis/SKILL.md)。
- PL/RTL、AXI、Bayer、时序/CDC 或同源制品直接阻塞闭环：阅读 [fpga-verification-gates](../fpga-verification-gates/SKILL.md)。
- 本 skill 的仓库入口、版本和证据要求详见 [project-map.md](references/project-map.md) 与 [evidence-gates.md](references/evidence-gates.md)。

