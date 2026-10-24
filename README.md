# FPGA 机器视觉项目

本仓库包含 AX7Z020B（Zynq-7020B）机器视觉工程、OV5640 MIPI 摄像头软件、
颜色高亮 RTL、Vivado/Vitis 自动化脚本，以及 Portal 交互原型和设计文档。

新板端游戏已有独立 C 规则核心，板端界面和硬件接入尚未完成：AX7Z020B、实物手动交互、纯虚拟中文界面、
非触摸 HDMI 1280×720（16:9，目标 60 Hz）、有线 USB-A 鼠标、三关各自 180 秒倒计时与星级结算；
不提供重置、进度持久化或声音。显示架构采用电脑离线预渲染二维背景/Sprite、SD 卡素材、
现有 Linux/PYNQ 上原生 C/C++ 常驻缓存与简单二维合成、现有 PL VDMA/HDMI 输出；
不开发 PL 绘图引擎，不以未来优化为由增加 DMA 或切换系统。摄像头采集保持独立。
已有 Linux/PYNQ 镜像已完成进一步离线评估，可作为候选运行系统，板端兼容性尚未验收；
优先使用镜像内原生 GCC/G++，本机安装 PetaLinux 不是前置条件。
完整 20 项决定、参数边界、已确认的独立计时规则及后续任务见
[PROJECT_STATE.md 的首版约定](PROJECT_STATE.md#board-game-first-release-contract)。

离线最小素材演示：运行
`./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -SpriteOnly`。
同一进程一次加载背景及两个预制姿态，输出坐标变化、背景恢复与姿态切换的三张图，
结果位于 `output/build/game_app/sprites/preview.png`。这不是 SD/HDMI 实板通过；
原生显示后端仍拒绝未核准的硬件操作。架构审查、素材格式、Linux 构建及上板步骤见
[素材演示说明](color_test/software/vision_ps_baremetal/README.md#离线预渲染素材最小演示)。

三关布局模板已确定为 `sample_photo/075.png`、`076.png`、`077.png`：第一关只允许
SOURCE 原地旋转；第二关只允许两个 Portal 平移和旋转；第三关只允许 MIRROR 平移和旋转。
其余物体的位置和姿态锁定。照片只作布局模板，开始计时前由玩家将可操作物体摆到未通关状态。
用户明确确认 `077.png` 不是正确答案，原图无需命中 TARGET，保持第三关原布局。
规则定义和离线检查说明见
[三关运动约束](PROJECT_STATE.md#three-level-templates-and-motion-rules)。

标准 C99 核心已实现三种运动权限、选关/准备/明确开始/通关或超时、独立计时及成绩锁定，
拒绝缺失、重复、过期和旧关卡输入。配置唯一手工来源为 `pc_vision/game_config.json`；
沿用 C 光线求解器及完整 17 段容量，另行报告 5 段渲染预算超限。标准 C 场景适配和离线应用
已接通 `VisionDetection[] → SceneObject[] → 映射 → game_session → GameSnapshot`。
运行聚焦验证并生成文本入口：

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1
./output/build/game_app/game_offline.exe
```

脚本先静态检查，再运行持续运行泵、输入/调度、适配/应用和原三关核心的模拟时间 host C 测试及文本回放；
产物只写 `output/build/game_app/`。同一文本入口已支持鼠标菜单、evdev 分片/多记录字节流、
原始任务派发标记、检测完成与模拟期限等待回放。运行泵采用有界批次，空闲也 tick 并等待，
每批发布一份完整快照；仅明确开始才计时，不自动生成姿态。
完整快照已接入原生 C 中文虚拟渲染与 PPM 导出；菜单外观和命中共用 JSON 布局，
带 stride/容量检查并按发布边界回放。接口、命令及验证结果见
[软件 README](color_test/software/vision_ps_baremetal/README.md#完整快照驱动的原生-c-离线虚拟界面)。
目前为未标定预览单位，真实 Linux 采集/evdev 设备接入、A3 标定、显示后端、帧边界提交和板端验证
仍待完成。Linux 输入/单调时钟/期限等待系统调用源码已加入，并通过假系统调用测试与 ARM 静态检查；
尚未执行真实 Linux 调用或验证目标 evdev UAPI/armhf ABI，host 通过不是 Linux 运行验证或板端验收。

照片虚拟游戏第一版已接入现有 `pc_vision/app.py`：只读取 `sample_photo`，
调用当前板端 C 识别器和 `ray_game.c`，在独立窗口生成六类标准模型与光线。
第一阶段未连接板卡、未更换模型标记、未修改 PL 或 HDMI 行为。

```powershell
python pc_vision/app.py --game --photos sample_photo
```

默认打开 `077.png`，鼠标按钮可暂停、锁定、解锁、重置、切换照片、标定和保存截图。
需要 Python、`pc_vision/requirements.txt` 和 PATH 中的 host GCC；首次启动自动严格编译
最小 C 桥接。无四点标定时明确显示未标定预览。运行、离线回放、尺寸设置和
标定说明见 [pc_vision/README.md](pc_vision/README.md#照片虚拟游戏第一版)。

第二阶段已新增裸机 PS 固定场景 HDMI 演示代码，默认关闭，保留原摄像头行为。
在 `color_test/software/vision_ps_baremetal/src/vision_ps_config.h` 将
`VISION_FIXED_SCENE_DEMO` 设为 `1`，并保持 `VISION_MINIMAL_TEST=0`、
`VISION_GREEN_TARGET_ONLY=0`，即可选择固定场景入口。它使用 1280×720 逻辑像素，
复用 `ray_game.c` 和现有显示 VDMA/VTC/像素时钟，绕过摄像头启动；一次绘制后持续显示。
布局、调用关系和后续验收见
[裸机应用 README](color_test/software/vision_ps_baremetal/README.md#固定场景-hdmi-演示第二阶段)。
本阶段只修改源码并静态审查，未编译、未运行光线、未仿真、未验证 HDMI 或操作板卡。
真实毫米标定、实际鼠标交互、串口接入和板端程序加载仍待完成，电脑端预览不代表这些链路已验证。

## 主要目录

- `color_test/`：可上板运行的 OV5640 MIPI 到 HDMI 工程。
- `color_test/rtl/`：AXI4-Stream 颜色高亮模块。
- `color_test/software/`：Cortex-A9 裸机摄像头和显示应用源码。
- `color_test/tools/`：Vivado 构建、Vitis 构建、JTAG 下载和硬件诊断脚本。
- `color_test/sim/`：RTL 与摄像头恢复流程测试。
- [`skill/`](skill/README.md)：面向自主选题初级组的三项可复用技能、接口模板与离线日志分析器。
- `doc/`：方案、调研和板上故障排查记录。
- `portal-showcase/`：浏览器交互原型。

## 当前硬件版本

目标硬件为 AX7Z020B、OV5640 MIPI 摄像头和 HDMI 显示设备。工程使用
Vivado/Vitis 2023.1，目标器件为 `xc7z020clg400-2`。

完整的 Vivado/Vitis GUI、XSCT 终端、QSPI 固化、SD 卡裸机启动和 PYNQ 烧录说明见
[`doc/AX7Z020B_烧录指南/00_烧录方式总览.md`](doc/AX7Z020B_烧录指南/00_烧录方式总览.md)。

摄像头恢复版软件会先显示 5 秒诊断彩条。每次重试都会停止采集 VDMA，复位当前
Digilent D-PHY/CSI 接收核，硬复位并重新配置 OV5640，在释放接收核后启动采集 VDMA，
最后退出传感器 software standby。程序会回读 OV5640 的 MIPI/RAW10/PLL/720p 关键
寄存器，并持续检查 CSI 长包、CRC、接收 FIFO 和 VDMA 状态，异常时最多重试三次。
当前 D-PHY IP 的 AXI-Lite 接口只公开 control/version，不公开 HS、stop-state 或 lane
状态；当 CSI 长包仍为 0 时，软件日志会明确保留这段不可进一步区分的故障边界。

板上验证已经确认恢复版可以在 Reset 后重新获得摄像头数据：CSI 长包计数持续增长、
CRC 错误为 0，采集和显示 VDMA 均正常运行。详细构建和下载步骤见
[`color_test/README.md`](color_test/README.md)，故障分析见
[`doc/AX7Z020B_OV5640_复位恢复说明.md`](doc/AX7Z020B_OV5640_复位恢复说明.md)。

## 不安装本机 PetaLinux 的 Linux 游戏推进方案

2026-10-16 离线结论：**优先复用现有镜像＋板端原生 C/C++＋现有 PL 接口**。
PYNQ 是候选 Linux 运行环境，不要求用 Python 重写游戏、检测器或光线算法。
当前没有证据要求重建整个系统，但也不能据此宣称镜像已适配当前自定义 PL。
详细证据、哈希和限制见 [PYNQ Migration Status](PROJECT_STATE.md#pynq-migration-status)。

镜像仍位于：

```text
C:\Users\11967\Downloads\ax7z020b-2.6.0.img\ax7z020b-2.6.0.img
```

- 大小 6,140,747,776 字节（6.14 GB / 5.719 GiB），与旧记录相同；本次建立了完整
  SHA256 基线。无旧完整哈希或发行方校验值，不能证明与原下载逐字节一致或来源可信。
- 内部记录为 2023-07-10 构建；实际是 Linux `5.4.0-xilinx-v2020.1`、PYNQ **2.6.2**、
  Ubuntu 18.04 基础用户态、armhf/glibc **2.27**，不是由文件名推断版本。
  FIT 内核/设备树校验通过，内嵌内核配置与根文件系统保存的配置相同。
- DT 标识 `ax7z020`，USB0/ULPI/MIO46 与现有 XSA 有对应证据，仍缺精确 AX7Z020B
  修订版及 FSBL/DDR 初始化证明、原始镜像下载页和发行方校验值。
- 沿用原分区偏移读取文件，没有重新检查分区表。读取启动文件时确认 BPB 为 **FAT16**；
  旧文档按分区类型写成 FAT32 的结论应以此更正。镜像没有被挂载、复制或修改。

| 项目 | 可复用部分与必要适配 |
| --- | --- |
| C/C++ | 镜像已含 ARM 原生 GCC/G++ 7.3、make、头文件、链接启动文件和运行库，优先直接编译。现有 Vitis 2023.1 交叉 GCC 12.2 能启动，但默认 sysroot 是 glibc 2.36；后续交叉构建需使用匹配的 2.27 armhf sysroot 并检查 ELF 依赖。裸机 `arm-none-eabi` 不能替代 Linux 编译器。 |
| 鼠标 | 内核已编入 USB Host/HID/evdev；使用 `/dev/input/event*`，不要依赖未启用的 `/dev/input/mice`。USB 角色、供电、枚举、权限和拔插恢复未上板验证。 |
| DMA/外设 | 已有 128 MiB CMA 配置、XLNK、`libcma.so`、原生 C 分配/物理地址/cache 同步 API，I2C/GPIO/FPGA Manager 支持也在。实际设备节点、CMA 可用量、时钟及 DMA/cache 一致性仍须板端验证。 |
| 算法/模型 | 复用裸机目录现有 `vision_ps.c`、`green_target_detector.c`、`ray_game.c` 和模型/光线绘制原语，适配 Linux 缓冲、MMIO、计时及输入接口。保留原回归问题，不能声称全体回归通过。现有英数字体不能充当中文界面，需要确定中文字库/小型字形资源。 |
| 显示 | 当前 DT 没有自定义 VDMA/VTC/dynclk 绑定，不能假设 X 桌面、SDL、DRM 或 `/dev/fb0` 自动驱动该 PL。先复用现有独占 MMIO 控制路径，再验证显示；内核无需仅因 PL 使用 Vivado 2023.1 就自动整体升级。 |

加载 PL 前有三项已确认的适配门槛，本任务均未修改：

1. 当前 XSA、标准 BIT、旧 `output/pynq_overlay/` 的哈希不一致；适配代码的哈希常量
   对应旧输出。需确定同代 BIT/HWH 与 PS 初始化契约，不能混用，也不能覆盖现有产物。
2. Python 适配要求 FCLK1 精确 150 MHz，但 XSA 实际是 142.857132 MHz；需按选定硬件
   和实际 PLL 核对。HWH 解析回退不能证明时钟、复位或硬件版本兼容。
3. 镜像已启用 `bootpy.service`，启动脚本尝试加载 `BaseOverlay("base.bit")`；其 base
   目录仅见 BIT，没有对应 BaseOverlay 实现/HWH。后续首次启动前须准备在目标 SD 上
   可逆禁用该服务的方案，不能假定“原镜像启动但不加载 Overlay”。

最终显示已明确采用1280×720，不再要求1280×800输出。沿用已存EDID及现有720p
显示证据，仍须按实际制品核准时序、缓冲与启动恢复。当前素材和逻辑画布仍有1280×800；
已验证的720p路径使用等比缩放居中，原生720布局、素材及鼠标映射适配尚待完成。
采集继续1280×720 RAW10/BGGR，采集与显示尺寸、stride及所有权分别管理；
旧六帧缓冲估算约20.65–25.05 MiB仅为历史范围，最终按实际分配加对齐与余量核准。
60 帧采集＋60 帧显示的有效像素 DMA 为 350.208 MB/s，CPU/cache/PL 流量另计。
虚拟背景不复制摄像头图像；启动阶段可静态/局部绘制，稳态 PL 渲染按既定门槛推进。
实际 HDMI 刷新、渲染速率、识别速率和鼠标延迟须分别测量，尚无 60 Hz 验收结论。

标准 C 场景适配、菜单输入、离线事件循环及可注入 I/O 的持续运行泵已完成 host 验证。
下一任务完成原生 Linux owner 接线，验证已有输入系统调用胶水及目标 UAPI/ABI，接入采集和显示平台接口，
核对同代交付物/FCLK，选定中文资源和屏幕时序，准备启动服务处理方案。
另行获得硬件授权后，才确认 SD 目标、处理自动加载并首次启动，收集启动日志、
`uname`、CMA/设备节点、原生编译器和鼠标事件证据；先验收原生 C＋鼠标，再逐步验收
独占 PL/DMA/cache、纯虚拟 HDMI、最终1280×720，最后接入720p摄像头与现有 C 检测/光线。
生产 MIPI 时序和七项 Critical CDC 问题仍是 PL 验收门槛，不能用能显示替代通过。

磁盘按应用而非整套系统构建预留：本机输出/资源/日志约 **0.1–0.5 GiB**，目标 SD 根分区
额外可用空间 **0.3–0.5 GiB**；若以后确需匹配的最小交叉 sysroot，另预留 **0.5–2 GiB**。
这些是规划额度。镜像未扩容的根分区目前约 0.91 GiB 空闲块，扣保留块约 0.63 GiB；
本机 C/D 可用约 19.8/47.7 GiB。复用现有镜像，无需再复制 5.719 GiB，也无需新装工具。
只有确认必要驱动、内核 ABI 或 PS 初始化无法由现有运行时/用户态/设备树适配满足时，
才提出具体重建项并评估其他匹配版本的 Linux 构建主机；不自动退回本机 PetaLinux。
本次只读核查并更新两份文档，未安装、下载、构建、写卡、加载 PL 或连接/测试板卡。

## Git 仓库说明

仓库提交源码、约束、Block Design、可复现构建脚本和文档。Vivado/Vitis 工作区、
bitstream、ELF、XSA 和 BOOT.bin 均为可重建产物，由 `.gitignore` 排除。需要发布可直接
烧录的文件时，建议把 `system_wrapper.bit`、`camera_recovery.elf` 和 `BOOT.bin` 作为
GitHub Release 附件上传，并注明对应提交和 Vivado/Vitis 版本。
