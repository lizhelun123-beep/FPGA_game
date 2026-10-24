# 工具脚本

以下脚本均从 `color_test` 目录运行。

## 构建与下载

- `run_hdmi_colorbars.py` / `build_hdmi_colorbars.tcl`：独立、可回退的纯 PL
  1280×800/82MHz 彩条诊断，仅复用 rgb2dvi。使用板载 50MHz，不使用 PS、摄像头、
  DDR、VDMA 或 Linux；不会连接板卡，也不修改生产 XPR/BD/默认 top。
  **本轮两次 Vivado 运行均未达到准入，尚无可下载 BIT，自动重试已停止。**
  源码、失败次数、报告、后续构建门槛及 JTAG/回退步骤见
  [`../build/hdmi_colorbars/REVIEW.md`](../build/hdmi_colorbars/REVIEW.md)。
  该诊断不使用下面的 `program_camera_jtag.tcl` 或任何 PS 初始化脚本。
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
- `analyze_dphy_sampling.tcl`：打开现有 routed DCP，在内存中检查全部
  0–31 clock/data IDELAY taps；输出逐 lane、逐数据跳变的 setup/hold、
  methodology、CSV 和窗口结论。每次查询覆盖两个 DDR 采样边沿；允许两条
  lane 使用不同 taps。保持输入延时、布线和原语模式不变，不启动构建、
  写回 DCP、发布 BIT/XSA 或连接板卡；分析结果不能替代修改后的实现验收。
  从本目录运行 `vivado -mode batch -source tools/analyze_dphy_sampling.tcl
  -nojournal -log reports/dphy_sampling_analysis.log`；可通过 `-tclargs <DCP>`
  指定检查点。默认使用 `color_test.runs/impl_1/system_wrapper_routed.dcp`。
  **仅补齐固定设置的角点证据时**，使用 `vivado -mode batch -source
  tools/analyze_dphy_sampling.tcl -nojournal -log reports/dphy_sampling_corners.log
  -tclargs --corners-only`（最后可附已有 DCP 路径）。该入口保持 clock/data
  taps=0/12，不进入原有扫描；分别查询两 lane、P/N、Fast/Slow、两种数据跳变
  的 setup/hold，保留两个 DDR capture 边沿。输出 `reports/dphy_sampling_corners.rpt`；
  完整结束标记之前的报告不能用于准入。它不修改原语属性、约束或 DCP。
  完整明细还包括较宽松的额外 DDR 边沿检查；审计分别标记主采样配对和额外检查，
  不把额外检查当作位序错误，也不以它们替代主采样窗口。
- `../sim/run_dphy_clock_ooc.tcl`：先仿真实验性 MMCM 复位控制，再以非工程
  OOC 流程综合、布局布线独立采样夹具。夹具复用规范 `HS_Deserializer`，
  检查匹配 BUFG 时钟/反馈及相位、tap 窗口，保留现有 DDR 输入延时。
  运行 `vivado -mode batch -source sim/run_dphy_clock_ooc.tcl -nojournal
  -log reports/dphy_clock_ooc.log`；输出在 `build/dphy_clock_ooc/` 与
  `reports/dphy_clock_ooc_*`。该夹具不加入生产 BD，未覆盖完整 LP/SoT
  状态机或真实模拟锁定过程，不能作为 BIT/XSA 或板卡验收。
- `audit_dphy_contract.py`：用 `python tools/audit_dphy_contract.py` 离线解析
  已有 D-PHY baseline/OOC 报告，复算 34 条路径的时序，并输出各 lane/边沿
  的外部预算、capture/bit 映射及跨角点窗口到 `reports/dphy_contract_*`、
  `reports/dphy_external_budget.csv` 和 `reports/dphy_capture_bit_map.csv`。
  物理参数缺项保持 `UNKNOWN`；位序检查是主机代数核对，不替代原语、LP/SoT
  或启动仿真。该脚本不调用 Vivado、不修改约束或操作板卡。
  用 `python tools/audit_dphy_contract.py --corners-report reports/dphy_sampling_corners.rpt`
  显式选用上述完整报告，替代旧生产明细；不自动读取可能过期的查询结果。
  新增 `dphy_contract_coverage.csv`、`dphy_contract_corner_windows.csv` 和
  `dphy_contract_gate.json`：每个拓扑要求 64 个覆盖项，逐角点及跨角点输出
  诊断偏移窗口，并分解 IBUF/IDELAY/时钟缓冲及残余延迟贡献。缺项保持
  UNKNOWN；报告完成、STA 位配对正确或模型内存在偏移窗口均不等于生产通过。
  物理契约和启动/首包尚无证据，因此 `candidate_eligible=false`；附加
  `--require-eligible` 会在未合格时返回退出码 2。默认退出码 0 仅表示审计完成。
  离线工具回归：`python -B sim/test_dphy_contract_audit.py`；不运行 Vivado 或 RTL 仿真。

## Vivado 综合脚本读取（Windows / Codex）

本机 2023.1 的 `common.tcl`、生成的 realtime Tcl 和 `unimacro_verilog.tcl`
曾在综合启动时报读取失败，父进程可读并不代表综合子进程可读。受限进程还会
使 vendor batch launcher 的目录切换报 `Access is denied`。仅设置单/双线程
未稳定解决问题；本机已验证的绕行是**获准的普通 Windows 进程，从仓库根
启动并继承控制台句柄**，由 Vivado 自身 `-log/-journal` 保存日志。
底层间歇性原因未定位，不能把它当作普遍的权限或线程补丁。

既有 Python 入口已固化此方式。从本页约定的 `color_test` 目录运行：

```powershell
python -B sim/run_dphy_sampling_test.py ooc-synth
```

在 Codex 中用 `require_escalated` 对该次正常 Windows 进程提出审批；以当前
工具调用的有效权限为准。本轮未修改全局配置或 ACL。
`ooc-synth` 沿用现有功能证据及新鲜度门槛，综合后立即停止；记录输入、启动器
哈希和完成状态到 `build/vivado_runtime/dphy_sampling/last_run.json`。
`SYNTH_ONLY_COMPLETE` 不等于时序/CDC 合格；原 OOC 否决报告保持原状。
完整 `ooc` 会继续布局布线，仍须相应任务范围，本任务没有运行。

直接启动回退命令（先由上述入口通过功能证据门槛；保持本页的工作目录）：

```powershell
$taskRoot = (Resolve-Path .).Path
$taskOut = Join-Path $taskRoot 'build/vivado_runtime/dphy_sampling'
New-Item -ItemType Directory -Path $taskOut -Force | Out-Null
Set-Location (Split-Path $taskRoot -Parent)
try {
    & "$env:XILINX_VIVADO/bin/vivado.bat" -mode batch -notrace `
        -source "$taskRoot/sim/run_dphy_sampling_ooc.tcl" `
        -log "$taskOut/direct_vivado.log" -journal "$taskOut/direct_vivado.jou" `
        -tclargs --synth-only
} finally {
    Set-Location $taskRoot
}
```

`check_vivado_runtime.tcl` 是一个单寄存器综合探针，参数为输出目录和1/2线程，
输出 `VIVADO_RUNTIME_SYNTH_PASS`。它用于区分工具启动/读取故障与原工程问题；
小例程通过后仍须用实际入口验证。本次直接启动和修正后的 Python 入口均以
实际接收器通过（133普通警告、0严重警告、0错误），未生成 BIT/XSA 或操作板卡。

参考 [OpenAI Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
的有效权限/文件访问检查，以及 [AMD UG835 2023.1 synth_design](https://docs.amd.com/r/2023.1-English/ug835-vivado-tcl-commands/synth_design)
的非工程综合入口。官方资料没有建立本机间歇性错误的确切根因；上述绕行为
本仓库实测结论。

需要先启动 `hw_server` 才能运行 JTAG 脚本。工具安装位置由 PowerShell 中的
`XILINX_VIVADO` 和 `XILINX_VITIS` 环境变量决定；Tcl 脚本内部不包含开发机绝对路径。

## 隔离D-PHY原始采样观测诊断

`dphy_observer.py`提供`prepare`、`verify`及受账本保护的`build`阶段，使用
`build_dphy_observer.tcl`，生成内容全部位于`color_test/build/dphy_observer_140/`。
该顶层复用本工程PS7叶检查点和规范采样原语，以GP0访问实际tap、独立计数和
片上原始采样RAM；没有DMA/ISP/HDMI或自动选码，不修改生产BD、XDC或启动配置。
仿真入口为`color_test/sim/tb_dphy_observer.sv`；精确源版本及告警审查边界以
该目录`simulation.json`、`validation_review.md`和`build_attempt.json`为准。

2026-10-20授权的一次构建已使用并停止：保存了routed DCP，但有3处Critical
CDC和BRAM异步控制告警，另有默认路径组报告脚本错误，未生成BIT、未加载。
入口拒绝再次`build`；不得删除账本或改名目录重试。追加修复/验证/构建须另获
明确范围，并保留原失败记录。详见`build/dphy_observer_140/REVIEW.md`和采样
报告第30节。该诊断未通过，不得作为生产接收器、时序合格或实测频率证据。

其后按第31/32节完成修复及明确追加的一轮验证、一次构建：API1.2、STATUS bit8
为ARM_READY，2070项修订版仿真和13项报告门禁检查通过；`attempt2/`实际实现仍
有3处Critical CDC-11，禁止加载。原CDC-10及RAM异步控制告警已消除，不等于
整体诊断合格。两次构建均已使用；加载总额仍0/1，没有板端操作。
旧账本、输入及报告留在父目录；本轮记录在`attempt2/package_ledger.json`，
不覆盖或清零旧失败。当前入口拒绝继续prepare/verify/build；不得改名或删账本
重试。下一项是复位拓扑及统一释放契约审查，详见第32节和attempt2/REVIEW.md。

第33节按明确授权实现共享字节域复位，复用同一入口增加`shared-prepare`、
`shared-verify`、`shared-synth`阶段，输出位于既有诊断目录的`shared_reset_audit/`。
`shared-synth`严格在综合/CDC结构审计后退出，不运行opt/place/route、不生成BIT。
两个诊断lane仅明确启用`kExternalByteReset=true`时绕过内部桥；生产默认false。
RAM控制仍同步复位；共享释放后等待8个byte边沿，保留API1.2/ARM_READY门禁。

本次定向验证已在SV编译阶段失败：VRFC10-3380，`frequency_count`在声明前被引用。
VHDL编译和13项报告fixture通过，仿真与最小综合尚未执行。声明顺序已修正，
当前源码未复验；原失败输入、快照、日志和用量保留，入口拒绝再次验证。
下一步需明确追加修正后的定向验证额度；通过后才可使用尚未消耗的最小综合额度。
没有追加实现、加载或板端授权，不得删除/改写账本以重跑。详细结果与哈希见
`build/dphy_observer_140/shared_reset_audit/REVIEW.md`和`review.json`。

第34节明确追加的一轮验证使用`shared-resume-prepare/verify/synth`阶段，记录在
同目录`verification2/`。父级失败账本不变，子记录明确继承未用综合总额度1，
不增加实现/加载额度；单轮内相关声明/类型/端口编译错误可留档后修正复验，
功能仿真失败则关闭入口。本次仅一次编译调用，编译与展开均通过，仿真在
76.430us的非SoT标志断言失败。9个CASE_PASS不等于整轮通过，未进入综合0/1。
全1输入的复位边界可合法触发现有soft匹配；测试独立取整的两个时钟也不是精确
÷4。先修正激励/黄金契约及失败可观测性，再决定另行授权验证；当前不值得
追加诊断实现。源码、日志、原WDB及哈希见`verification2/REVIEW.md/review.json`。

第35节在集中修复授权内完成`fixture-prepare/verify/synth/audit`包，记录于
`shared_reset_audit/fixture_package/`。共同串行时钟驱动真实BUFR整数÷4；两lane
soft/valid及合成error/invalid观测均按原始32bit格式存入RAM。失败直接打印lane、
H/S/E/V、tap、共享复位/热身及采集状态，不把soft或坏观测自动判为诊断失败。
最终定向仿真12102项、11场景和13项报告fixture通过。首次功能运行也走完全部
场景，但旧首边沿时间戳报告门拒收；该失败及修复后重跑均保留。

唯一一次最小综合已用1/1。`fixture-audit`只重读同一封存DCP，处理报告脚本的
布尔属性和PS专用BIBUF追踪问题，不重新综合；3次只读复查后通过。实际Critical
CDC为0，共享复位链深度4；RAM控制和INIT已审查。综合前优化阶段的PS pad DRC
提示保留原级别，130个固定PS端口及15个PL管脚均核准；不能代替实现后的完整DRC。
制品为综合DCP，不含BIT/HWH/XSA或板测结果。入口账本已关闭，不得删账本重试。
后续一次诊断实现及有条件有限板测仍待明确授权；生产接收正确率/余量另行准入。
