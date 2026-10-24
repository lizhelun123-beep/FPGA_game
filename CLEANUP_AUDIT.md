# 历史文件、重复实现与目录结构清理审计

审计日期：2026-10-01  
审计状态：初始只读审计已完成；2026-10-01 已按本报告执行第一轮 A 类安全清理。未处理 B/C/D 类，未移动、重命名或修改代码及目录结构，未执行综合、JTAG、烧录或板上操作。

## 1. 审计范围与结论摘要

本报告结合了根目录结构、`AGENTS.md`、`PROJECT_STATE.md`、根/子目录 README、现有子项目 CHANGELOG、Git 状态与历史、源码调用关系、Python import、Tcl/Vivado 工程引用、BIF 启动配置和测试入口。

重要边界：

- 根目录没有 `ARCHITECTURE.md`，也没有根级 `CHANGELOG.md`；仅有 `color_test/software/vision_ps_baremetal/CHANGELOG.md`。因此无法用缺失文档交叉验证全仓库架构和历史。
- Git 当前只有一个提交：`71a3fc5 fix: preserve OV5640 Bayer RGB ordering`。所有 182 个已跟踪文件均在该提交一次性加入，无法从 Git 历史证明某个并存版本已经被后续版本替代。
- 工作区不是干净状态：13 个已跟踪文件有修改，且 `AGENTS.md`、`pc_vision/`、`color_test/software/vision_ps_baremetal/` 等为未跟踪内容。这些均应视为用户当前工作，清理前必须先纳入版本控制或另行备份。
- 未发现 `project/project/`、`pc_vision/pc_vision/` 或“整个仓库复制到仓库内部”的结构。
- 当前最大可清理空间来自被 `.gitignore` 排除的 Vivado/Vitis 生成物，而不是源代码副本。`color_test/` 当前约 718 MB，其中 `color_test.srcs` 约 340 MB、`build` 约 130 MB、`color_test.runs` 约 100 MB、`color_test.cache` 约 72 MB、`color_test.gen` 约 29 MB。
- 不能整体删除 `color_test.gen/` 或 `color_test.srcs/`：两者包含已跟踪且当前工程实际使用的文件；其中生成树里的 `AXI_BayerToRGB.vhd` 与 IP 仓库源有 7 行差异，项目状态又明确记录综合实际读取生成树副本。

## 2. 当前项目主要入口

| 入口 | 作用 | 当前地位 |
| --- | --- | --- |
| `color_test/color_test.xpr` | Vivado 2023.1 工程入口 | 正式硬件工程入口，C 类 |
| `color_test/tools/build_bitstream.tcl` | 打开 XPR、刷新 BD/IP、综合实现并输出 BIT/LTX/XSA/报告 | 正式可复现硬件构建入口，C 类 |
| `color_test/software/mipi_hdmi/mipi_hdmi/src/main.c` | OV5640、显示、VDMA 与摄像头恢复程序 | 当前恢复基线；被构建脚本和测试引用，C 类 |
| `color_test/tools/build_camera_recovery.tcl` | 从上述源码直接构建恢复版 ELF | 正式恢复软件构建入口，C 类 |
| `color_test/software/vision_ps_baremetal/src/main.c` | 裸机六类目标识别、完整帧交接与 HDMI 标注 | 当前新增识别实现；虽称“临时版”但文档/脚本完整，C 类 |
| `color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl` | 构建裸机视觉 ELF | 当前识别软件构建入口，C 类 |
| `pc_vision/app.py` | PC 图片、视频和 USB 摄像头识别 CLI/GUI | PC 参考实现入口，C 类 |
| `pc_vision/calibrate.py` | 基于标注 ROI/mask 的 HSV 标定入口 | PC 标定入口，C 类 |
| `color_test/sim/run_color_tests.tcl` | 两个颜色 RTL testbench 的批处理入口 | 当前测试入口；未跟踪，清理前应先纳入 Git，C 类 |
| `color_test/sim/test_camera_recovery.py` | 对恢复流程及关键源内容做主机侧故障注入检查 | 当前测试入口，C 类 |
| `pc_vision/test_*.py` | PC 视觉单元/集成回归 | 当前测试入口，C 类 |

## 3. 当前核心模块与主要运行流程

### 3.1 FPGA 视频链路

```text
color_test.xpr
  -> color_test.srcs/sources_1/bd/system/system.bd
  -> repo/ip/MIPI_D_PHY_RX
  -> repo/ip/MIPI_CSI_2_RX
  -> AXI_BayerToRGB
  -> AXI_GammaCorrection
  -> rtl/axis_color_highlight.v（含白平衡；当前默认关闭固定色替换）
  -> 采集 VDMA -> DDR -> 显示 VDMA
  -> rgb2dvi/HDMI
```

当前有效像素流程由文档确认是：

```text
OV5640 RAW10
  -> D-PHY/CSI-2
  -> 有效 RGGB 去马赛克
  -> Gamma
  -> 固定白平衡
  -> AXI 颜色模块
  -> VDMA/DDR
  -> HDMI
```

### 3.2 摄像头恢复应用

```text
software/mipi_hdmi/mipi_hdmi/src/main.c
  -> DisplayInitialize()/DisplayStart()
  -> sensor_configure()
  -> vdma_write_init()
  -> sensor_start()
  -> CSI/CRC/VDMA 健康检查与最多三次恢复
  -> HDMI 画面与 UART1 诊断
```

`build_camera_recovery.tcl` 明确从该 `src/` 收集源码，`test_camera_recovery.py` 也直接读取该目录中的 `main.c`、`ov5640.c`。因此这套源码不是未引用旧副本。

### 3.3 PS 裸机视觉应用

```text
software/vision_ps_baremetal/src/main.c
  -> 复用 OV5640/显示/VDMA 代码
  -> frame 0 单帧采集并停机
  -> CPU 复制到 frame 1/2
  -> vision_ps.c：HSV/连通域/几何/marker 分类
  -> vision_overlay.c：bbox/中心/类别/CONF/状态栏
  -> HDMI 换帧 + UART1 限频输出
```

该目录与恢复应用共享大量同源代码，但主程序、VDMA、显示时钟和视觉处理已分叉。它是重复实现问题，不是可直接删除的旧版。

### 3.4 PC 视觉原型

```text
pc_vision/app.py
  -> config.py
  -> detector.py
     -> body_refinement.py
  -> OpenCV HSV/mask/形态学/轮廓/marker/几何
  -> GUI、JSONL、标注帧或调试快照
```

PC 原型与裸机算法目标相同，但平台、依赖、算法细节和用途不同：前者用于标定、可视化和参考回归，后者用于 Cortex-A9 上板运行。二者不是简单文件副本。

## 4. 清理候选与分类

分类定义：A=明确可删除；B=高概率可删除但应人工确认；C=当前使用必须保留；D=当前证据不足，暂不删除。

| 路径 | 当前作用 | Git 历史 | 当前引用情况 | 分类 | 建议 | 删除风险 |
| --- | --- | --- | --- | --- | --- | --- |
| `0x%08X $crc0 $crc1]; puts [format Capture` | 28 字节异常文件，内容仅为两行 `ECHO is off.`，疑似错误 shell 重定向产物 | 未跟踪、无历史 | 删除前复核全仓库无引用 | A（已删除） | 已于 2026-10-01 删除 | 极低 |
| 根目录 `.Xil/` | Vivado/XSCT 会话缓存；删除前为空目录树 | 忽略、无历史 | 无源码/脚本引用 | A（已删除） | 已于 2026-10-01 删除 | 极低，可自动重建 |
| 根目录及各子目录 `vivado*.jou`、`vivado*.log` | Vivado 操作日志和备份日志 | 均被忽略、无历史 | 运行流程不读取；删除前无 Vivado/XSCT/Vitis 进程 | A（已删除） | 已删除根目录、`color_test/` 和视觉源码目录中的现有日志 | 低，失去历史诊断细节 |
| `color_test/vivado_pid30556.str` | Vivado 进程字符串/会话产物 | 未跟踪，且当前 `.gitignore` 未覆盖 | 删除前复核无工程引用 | A（已删除） | 已删除；后续仍建议在 `.gitignore` 增加 `vivado_pid*.str` | 极低 |
| `color_test/NA/ps7_summary.html` | 工具生成的 PS7 摘要 | `NA/` 被忽略、无历史 | 删除前复核无脚本引用 | A（已删除） | 已删除目录 | 低，可由工具重建 |
| `pc_vision/__pycache__/` | Python 字节码缓存，约 99 KB | 子目录 `.gitignore` 排除 | Python 自动生成 | A（已删除） | 已删除；验证使用 `python -B`，未重新生成 | 无 |
| `pc_vision/output/` | demo、参考图和运行输出，约 488 KB | 子目录 `.gitignore` 排除 | 仅 `demo.png` 可明确追溯到 `test_vision.py --demo`；其余参考图片无生成入口 | B（由 A 降级） | 本轮保留；先人工确认其余图片是否为唯一现场/参考样本 | 中，可能删除不可恢复的样本 |
| `color_test/color_test.sim/` | 空的仿真生成目录 | 忽略、无历史 | 删除前复核无直接引用 | A（已删除） | 已于 2026-10-01 删除 | 无 |
| `color_test/.Xil/` | 工程本地 Vivado 会话缓存，约 20 KB | 忽略、无历史 | 无脚本直接引用；删除前无 Vivado/XSCT/Vitis 进程 | A（已删除） | 已于 2026-10-01 删除 | 低 |
| `color_test/software/vision_ps_baremetal/vivado.jou`、`vivado.log` | 在源码目录误落的工具日志 | 忽略、无历史 | 删除前复核无引用 | A（已删除） | 已于 2026-10-01 删除 | 极低 |
| `color_test/software/mipi_hdmi/color_test/` | Vitis 生成的 FSBL 工作区，约 473 KB | 被 `.gitignore` 明确排除 | 旧 `sd_boot/boot.bif` 引用其中 `fsbl.elf` | B | 若废弃旧 BIF/旧镜像则一并删；否则先保留 | 中，旧启动镜像无法原地重打包 |
| `color_test/software/mipi_hdmi/mipi_hdmi/Debug/` | 旧 Vitis Debug ELF，约 535 KB | 被忽略、无历史 | 旧 `sd_boot/boot.bif` 明确引用；README 明确称其为旧版且不用于恢复验证 | B | 与旧 `sd_boot/boot.bif` 成组确认后删除 | 中，仍是旧启动流程依赖 |
| `color_test/sd_boot/BOOT.bin` + `sd_boot/boot.bif` | 旧一次性诊断启动镜像及配方 | BIF 已跟踪且当前有修改；BIN 被忽略 | README 明确要求恢复版使用 `sd_boot/recovery/BOOT.bin`，但旧 BIF 仍自洽引用旧 FSBL/ELF | B | 人工确认不再需要旧启动路径后整组移除，不要只删其中一个 | 中，删除后丢失旧可直接启动镜像 |
| `color_test/sd_boot/recovery/BOOT.bin` | 当前恢复版 SD 启动镜像 | 被忽略、无历史 | README 当前流程使用 | C | 保留到完成发布/验收；之后可作为 Release 产物而非源码保留 | 高，影响当前可直接启动能力 |
| `color_test/build/` | Vitis 工作区、ELF、稳定 BIT/LTX，约 130 MB | 被忽略、无历史 | 当前 JTAG 脚本和 BIF 直接引用 `build/hw`、恢复/视觉 ELF 和 `ps7_init.tcl` | C | 当前必须保留；未来在确认可重建且发布物已归档后，仅清理非发布工作区 | 高，会直接破坏当前下载/打包流程 |
| `color_test/reports/` | 当前综合/实现时序与资源报告 | 被忽略、无历史 | README/PROJECT_STATE 引用报告结论 | B | 在新构建可重现并保存关键报告后清理；更适合纳入发布/CI 产物 | 中，丢失当前实现证据 |
| `color_test/color_test.cache/` | Vivado IP/仿真缓存，约 72 MB | 被忽略、无历史 | 未发现脚本硬编码引用 | B | 关闭 Vivado，先做一次干净工程可打开/可重建验证后删除 | 中，重建耗时且可能暴露 IP 版本问题 |
| `color_test/color_test.runs/` | 综合与实现运行目录，约 100 MB | 被忽略、无历史 | 构建脚本读取实现输出并复制 BIT/LTX；当前稳定副本已设计在 `build/hw` | B | 先确认 `build/hw` 完整且可重新实现，再删除 | 中高，丢失增量结果和当前 run 状态 |
| `color_test/color_test.hw/` | Hardware Manager 布局/波形，约 177 KB | 被忽略、无历史 | 构建不依赖，可能保存 ILA 观察布局 | B | 确认不需保留调试波形/探针视图后删除 | 中，失去调试会话信息 |
| `color_test/color_test.srcs/sources_1/bd/system/ip/` 等被忽略生成 IP | Vivado BD 输出产品，是 `color_test.srcs` 体积主体 | 被忽略、无历史；其中 subset converter 的两个文件例外，已被跟踪 | XPR/BD 会使用输出产品；理论可重建，但当前工程依赖具体 Vivado/IP 状态 | B | 只能按“忽略且可由 BD 重新生成”的子路径清理，禁止删除已跟踪例外；先做归档/重建验证 | 高，误删会导致工程打不开或重生成结果变化 |
| `color_test/color_test.srcs/sources_1/bd/system/ui/bd_c954508f.ui` | BD GUI 布局文件 | 未跟踪、无 Git 历史 | 不参与综合，Vivado GUI 使用 | B | 若不需保留当前 BD 排版可删；若排版有人工价值则纳入 Git | 低至中 |
| `color_test/color_test.gen/` | BD/IP 生成树，约 29 MB | 大部分忽略；其中 Bayer VHDL 被跟踪 | 当前综合记录指向其内 Bayer 文件 | D | 不整体删除；先消除 Bayer 双源并验证 IP 重生成，再评估其余忽略内容 | 高 |
| `color_test/repo/ip/AXI_BayerToRGB/hdl/AXI_BayerToRGB.vhd` | IP 仓库源；component.xml 引用 | 已跟踪，仅一个提交 | 测试脚本读取；IP 仓库声明引用 | C | 保留，目标应成为唯一 canonical 源 | 高 |
| `color_test/color_test.gen/.../e9e4/hdl/AXI_BayerToRGB.vhd` | Vivado 生成/缓存副本；与 repo 源有 3 增 4 删差异 | 已跟踪，仅一个提交 | PROJECT_STATE 和综合日志确认当前综合实际读取 | C（现状） | 暂保留；后续把修正合并到 repo 源、重打包/升级 IP、重建验证后再取消跟踪 | 极高，当前直接删除可能改变综合结果 |
| 各 IP `xgui/*_v1_0.tcl`、`*_v1_1.tcl`、`*_v1_2.tcl` 等旧版本名文件 | IP GUI/升级兼容文件 | 已跟踪，仅一个提交 | 例如 Bayer `component.xml` 当前直接列出 `v1_3`，同时声明可从 1.0–1.2 升级；其他包未逐一完成 Vivado 打包器验证 | D | 不因 `v1`/`v2` 名称删除；逐个用 IP Packager 校验后再决定 | 中高，可能破坏旧 IP 升级/GUI |
| `color_test/software/mipi_hdmi/mipi_hdmi/src/` | 摄像头恢复基线 | 已跟踪 | 构建、测试、README 与恢复流程直接引用 | C | 保留 | 高 |
| `color_test/software/vision_ps_baremetal/` | 当前 PS 裸机识别 v2，约 141 KB | 整目录未跟踪、无历史 | PROJECT_STATE、README、三个工具脚本和主机测试共同使用 | C | 立即优先纳入 Git；不能按“临时版”删除 | 极高，当前唯一裸机识别实现会丢失 |
| `pc_vision/` 源码、配置、测试 | PC 参考识别/标定/回归 | 整目录未跟踪、无历史 | README、内部 import 和 20 项测试说明完整 | C | 立即优先纳入 Git；保留与裸机实现的差异化职责 | 高 |
| `color_test/sim/run_color_tests.tcl` | RTL 仿真编排 | 未跟踪、无历史 | 直接加载 RTL 与两个 testbench | C | 纳入 Git | 高，删除后失去文档所述 17 项测试入口 |
| `AGENTS.md` | 仓库工作规则 | 未跟踪、无历史 | 用户明确要求遵守 | C | 纳入 Git并保留 | 高 |
| `PROJECT_STATE.md`、`color_test/README.md` 及当前 11 个其他已修改跟踪文件 | 当前未提交工作 | 基线在唯一提交中，工作区有改动 | 当前功能与构建相关 | C | 清理前先审阅并提交；不得覆盖或还原 | 极高 |

## 5. 重复实现分析

### 5.1 两套裸机应用的复制代码

`vision_ps_baremetal/src` 明确从 `mipi_hdmi/mipi_hdmi/src` 复制。16 个同路径文件中，9 个完全相同，7 个已经分叉；视觉目录另增 5 个视觉文件。目录级 diff 约为 850 行增加、30 行删除。

完全相同的典型文件包括：

- `display_demo.h`
- `lscript.ld`
- `ov5640.h`
- `display_ctrl/display_ctrl.h`
- `display_ctrl/vga_modes.h`
- `i2c/PS_i2c.c`、`PS_i2c.h`

已分叉的关键文件包括：

- `main.c`：视觉版增加逐帧采集、识别、叠加和换帧；
- `vdma.c/.h`：视觉版增加单帧交接；
- `display_ctrl.c`、`dynclk.c/.h`：视觉版包含超时与显示保护修正；
- `ov5640.c`：仅有很小差异，仍会产生维护漂移。

当前 canonical 结论不是“二选一”：

- 摄像头恢复职责的正式实现仍是 `mipi_hdmi/mipi_hdmi/src`；
- 裸机目标识别职责的正式实现是 `vision_ps_baremetal/src`；
- 摄像头、I2C、显示、VDMA 共用层目前没有 canonical 实现，而是复制后分叉，这是应在后续结构调整中解决的问题。

建议后续抽取一个共享硬件支持层，由两个应用分别保留自己的 `main.c` 和业务逻辑。此调整会改变构建脚本和 include 路径，属于第三阶段高风险结构工作，不能当作简单删除。

### 5.2 BayerToRGB 双源

同时存在：

- `color_test/repo/ip/AXI_BayerToRGB/hdl/AXI_BayerToRGB.vhd`
- `color_test/color_test.gen/sources_1/bd/system/ipshared/e9e4/hdl/AXI_BayerToRGB.vhd`

两文件只差 7 行，但职责冲突：IP `component.xml` 和测试指向 repo 源，实际综合记录却指向 `.gen` 副本。这是当前最危险的重复实现。正式目标应是让 `repo/ip/...` 成为唯一手工维护源，并通过重新打包/升级 IP 生成 `.gen` 输出；完成重建、仿真和实现验证前，两份都必须保留。

### 5.3 PC 与 PS 视觉实现

两者识别相同六类目标，但不构成可删除副本：

- PC 版依赖 OpenCV，包含标定、调试窗口、形态学、轮廓层级和更丰富诊断；
- PS 版是固定内存、整数算法、4×采样、裸机 UART/HDMI 输出；
- PC 版应作为算法参考和阈值标定工具，PS 版是部署实现。

建议在文档中固定“PC reference / PS deployment”的对应关系，并增加共享测试向量或配置转换，而不是合并成同一源码。

### 5.4 旧启动镜像

`sd_boot/boot.bif`/`BOOT.bin` 与 `sd_boot/recovery/boot.bif`/`BOOT.bin` 是明确的新旧启动路径。README 已指定 recovery 为当前路径，但旧 BIF 仍引用旧 Debug ELF 和旧 FSBL，因而不是孤立无引用文件。清理应按完整依赖组进行：旧 BIF、旧 BIN、旧 FSBL 工作区、旧 Debug ELF 一起确认和移除。

## 6. 目录深度问题

### 明确存在但暂不应直接扁平化

1. `color_test/software/mipi_hdmi/mipi_hdmi/src/`
   - 两层同名 `mipi_hdmi` 来自 Vitis workspace/project 结构，语义弱、路径冗长。
   - 但当前构建脚本、测试和文档均硬编码该路径。
   - 建议最终迁为 `color_test/software/camera_recovery/src/`，同时一次性更新 Tcl、测试和文档。

2. `color_test/color_test.srcs/sources_1/bd/system/...`
   - 很深，但属于 Vivado 管理的工程层次，不是 AI 随意嵌套。
   - 不建议手工扁平化；只应通过 Vivado 工程重建策略减少生成物，而不是移动内部文件。

3. `color_test/repo/ip/*/drivers/*_v1_0/src/`
   - 深度来自 Xilinx IP 打包标准，具有工具语义。
   - 必须保留结构。

4. `color_test/software/vision_ps_baremetal/src/display_ctrl`、`dynclk`、`i2c`
   - 这些目录具有模块边界，深度合理。

### 未发现的问题

- 没有 `project/project/`、`pc_vision/pc_vision/`、`backup_project/`、`old/`、`final_version/` 等整项目套娃。
- `pc_vision/output/demo_result/` 是输出层次，不是源码目录嵌套；但同一 `output/` 中部分参考图片无法追溯生成入口，本轮已将整个目录降为 B 类并保留。

## 7. 推荐的新目录结构（仅方案）

```text
repo-root/
  AGENTS.md
  README.md
  PROJECT_STATE.md
  ARCHITECTURE.md              # 若后续补建，统一记录硬件/软件边界
  CHANGELOG.md                 # 若后续补建，只记录全仓库重要变更
  color_test/
    color_test.xpr
    color_test.srcs/           # 仅保留必要且受控的 XPR/BD/约束源
    repo/ip/                   # 自定义 IP 唯一 canonical 源
    rtl/
    sim/
    tools/
    software/
      common/                  # 后续抽取 OV5640/I2C/显示/VDMA 共用层
      camera_recovery/
        src/
      vision_ps_baremetal/
        src/
        tests/
        tools/
    sd_boot/
      recovery/                # 仅保留当前 BIF；BIN 作为构建/发布产物
    build/                     # 本地忽略；稳定可下载产物或转 Release
    reports/                   # 本地/CI 产物，不与源码混放
  pc_vision/
    app.py
    calibrate.py
    config.py
    detector.py
    body_refinement.py
    tests/                     # 后续可归拢 test_*.py
    output/                    # 忽略的运行产物
```

该方案不建议创建 `clean_project/` 或新仓库副本。Vivado 管理目录应通过工具重建和精确 ignore 管理，不手工改造成普通源码树。

## 8. 推荐清理顺序

### 8.1 最安全

1. 先保护当前工作：把 `AGENTS.md`、`pc_vision/`、`vision_ps_baremetal/`、`run_color_tests.tcl` 和所有已修改文件审阅后纳入 Git；本仓库目前只有一个提交，未跟踪源码没有历史保护。
2. 已完成：删除明确会话/缓存产物，包括异常 28 字节文件、根/子目录 `.Xil`、现有 `vivado*.jou/log`、`vivado_pid*.str`、`NA/ps7_summary.html`、`__pycache__` 和空 `color_test.sim/`。
3. `pc_vision/output/` 已降为 B 类；除 `demo.png` 外，先确认其余图片没有唯一现场/参考价值再处理。
4. 补充 `.gitignore` 对 `vivado_pid*.str` 等已确认生成物的规则，避免再次出现。

### 8.2 中等风险

1. 确认 recovery 启动路径已经完全替代旧路径，再成组删除旧 `sd_boot/boot.bif`、旧 `BOOT.bin`、旧 Debug ELF 和旧 FSBL 工作区。
2. 保留 `build/hw`、当前 ELF、PS 初始化文件和 recovery BOOT.bin，直到有可验证的新构建或 Release 归档。
3. 关闭 Vivado/Vitis 后，按子目录清理 `color_test.cache`、`color_test.runs`、`color_test.hw` 和被忽略的 BD 输出；随后验证 XPR 打开、BD/IP 状态、最小仿真和可重建性。
4. 报告目录在确认关键结论已保存且新构建可重现后再清理。

### 8.3 需要结构调整

1. 先解决 Bayer 双源：同步 repo 源、重新打包/升级 IP、重新生成输出，并验证仿真、综合读取路径和实现结果；随后才可取消跟踪 `.gen` 副本。
2. 从两套裸机应用抽取共享 OV5640/I2C/显示/VDMA 层，保留两个独立入口；更新两个构建脚本与测试。
3. 在共享层稳定后，将 `software/mipi_hdmi/mipi_hdmi/src` 扁平化为语义明确的 `software/camera_recovery/src`。
4. 最后再评估各 IP 包内旧版本 xgui Tcl；必须通过 Vivado IP Packager/升级路径验证，禁止仅凭文件名删除。

## 9. 第一轮 A 类清理执行记录

删除的文件：

- 根目录 `vivado.jou`、`vivado.log` 和异常 28 字节文件；
- `color_test/vivado.jou`、`color_test/vivado.log`、5 组 `vivado_<pid>.backup.jou/.log`、`color_test/vivado_pid30556.str`；
- `color_test/software/vision_ps_baremetal/vivado.jou`、`vivado.log`；
- `color_test/NA/ps7_summary.html`；
- `pc_vision/__pycache__/` 内 9 个 `.pyc` 文件。

删除的目录：根目录 `.Xil/`、`color_test/.Xil/`、`color_test/NA/`、空的
`color_test/color_test.sim/`、`pc_vision/__pycache__/`。这些目录仅包含忽略的会话、
缓存或工具输出，删除前再次检查了源码、入口、配置、构建、测试和 Tcl 引用。

验证结果：

- `python -B color_test/sim/test_camera_recovery.py`：15 项通过；
- `python -B -m unittest discover -s pc_vision -p test_*.py -v`：20 项通过；
- `color_test/software/vision_ps_baremetal/tools/test_host.ps1`：通过，含 overlay clipping；
- XPR、BD、RTL、两套软件入口、构建脚本、recovery BIF、当前 BIT 和两个当前 ELF 路径均存在；
- 已删除路径无残留，未发现新的 import 或路径引用错误。

未运行 Vivado 综合/实现、JTAG、烧录或板上测试，因为本轮只删除可再生成的本地杂项，
这些高成本或硬件验证不会为该变更增加相称证据。

## 10. 当前必须暂停的原因与下一阶段前置条件

本阶段到此停止，不执行任何清理。下一阶段开始前建议先满足：

1. 对当前未跟踪源码和已修改文件建立 Git 保护点；
2. 明确旧 `sd_boot` 启动路径是否仍需保留；
3. 明确是否允许删除本地可重建产物，以及是否接受重新构建 Vivado/Vitis 的时间成本；
4. 对 `build/hw`、当前 ELF、recovery BOOT.bin 等可直接运行产物决定“保留在本机、归档为 Release、还是可重建后删除”；
5. Bayer 双源和裸机公共代码抽取应作为独立实现任务，不与低风险缓存删除混在同一次提交中。
