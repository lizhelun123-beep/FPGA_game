# 可复用 FPGA 技能包

面向 2026 AMD 自主选题初级组，从本工程方案、失败记录和保存日志提炼。
这是随作品提交的 `skill/`，不是另一套 FPGA 工程。各子目录可作为独立 Codex
Skill 使用；不安装时，也可让助手读取指定 `SKILL.md` 后按其执行。

## 三项技能

| 技能 | 适用范围与用法 | 已有证据 | 失效条件与限制 |
| --- | --- | --- | --- |
| [pynq-dma-contract](pynq-dma-contract/SKILL.md) | 换板卡、换算法时，核对 Overlay 来源、IP/寄存器、DMA/VDMA、stride、cache 和缓冲所有权。填写其契约模板后逐项检查。 | 工程已做同源 XSA 解包、HWH 地址解析、padding 排除及离线适配测试；本次静态核对了对应实现。 | 没有真实 IP 配置、缓存属性或完成握手时，只能指出缺项；PYNQ 板端和跨板迁移尚未验证。 |
| [stream-perf-analysis](stream-perf-analysis/SKILL.md) | 对摄像头、音频、采集或控制系统的累计阶段计时做离线比对，并区分接收沉默、显式缺失和超时。附独立标准库脚本。 | 本次对保存的性能日志重算，并用合成的双阶段任务验证可更换契约；详细数值见下文。 | 缺少完整快照、单位或启动分段时不能推断阶段成本；CPU 耗时不等于端到端延迟。 |
| [fpga-verification-gates](fpga-verification-gates/SKILL.md) | 审查黄金参考、AXI 流协议、IP 来源、实现时序和优化前后证据。填写验收表，选最便宜的有效检查。 | 来自旧生成 IP、Bayer 相位、局部 OOC 通过但顶层失败、照片分类通过但光路失败等实际记录。 | 工作流已做静态审查，没有在新项目独立实测；报告缺失、过期或不同配置时不得签署整体通过。 |

示例请求：

```text
读取 skill/pynq-dma-contract/SKILL.md，检查我的 Overlay 和缓冲区契约；只做离线检查。
读取 skill/stream-perf-analysis/SKILL.md，分析已有日志，区分运算瓶颈和发送服务间隔。
读取 skill/fpga-verification-gates/SKILL.md，审查本轮优化的证据，不运行完整构建或连接板卡。
```

目录只依赖 Markdown、JSON 和 Python 标准库；分析脚本需要 Python 3.8+，不需要
PYNQ、NumPy、串口或 Vivado。安装到 Codex 技能目录时，每个子目录分别安装，
不要把整个 `skill/` 当成单一 Skill。当前提交目录未安装到用户全局技能目录。

## 离线运行

以下命令从仓库根目录执行，输入文件保持只读，结果输出到终端：

```powershell
python -B -m unittest discover -s skill/stream-perf-analysis/scripts -p test_analyze.py -v
python -B skill/stream-perf-analysis/scripts/analyze.py skill/stream-perf-analysis/examples/performance.jsonl --contract skill/stream-perf-analysis/references/project-perf-contract.json
```

第二条使用随包交付的 24/25 两份完整报告摘录，含 62 行，与原始阶段数值一致，
去除了接收器的机器时间等无关字段。第一条包含另一题目的合成快照验证。
新题目按该技能说明提供自己的 JSON 契约和日志，不需要仓库其他源码。
若测试环境不允许写系统临时目录，可将 `SKILL_TEST_TMP` 环境变量设为已有可写的
输出目录；测试仅在其中创建并清理自身临时子目录。

## 来源与验证边界

- 指南：用户提供的 AMD 2026 PDF，3.3.2、3.3.3、3.3.5.2，印刷页 19–22
  （PDF 页 22–25）。PYNQ 是初级组推荐实现方式；通用 PYNQ Skill 单独加分，
  不意味着必须把当前裸机工程迁移到 PYNQ。
- 方案及现状：[PROJECT_STATE.md](../PROJECT_STATE.md) 的 Architecture、PYNQ
  Migration Status、Current Problem、PC Game Flicker、Live Scene Performance
  Investigation；[PYNQ 适配说明](../pynq_vision/README.md)；
  [裸机计时说明](../color_test/software/vision_ps_baremetal/README.md)。
- 原始观察：`pc_vision/output/perf_20261015_230249/performance.jsonl`、
  `scenes.jsonl`、`flicker_analysis.json`。293 条被界面采用的场景跨 454.328 s，
  约 0.643 Hz；间隔中位数 1.50 s，最长 5.313 s。这些记录不能证明线上丢包率。
- 本次重算：固定摘录为 62 行、2 份完整报告、1 个有效窗口。
  24→25 的 detect_six=450.034846 ms、process=479.983703 ms、
  poll_gap=239.994604 ms、fifo_span=1102.304129 ms；各指标样本数不同，不可相加。
- 新脚本的 13 项测试覆盖缺行、重复阶段、计数回退、重连、单位错误、零样本和
  另一题目的阶段名。脚本只计算观测，不自动改变固件、阈值、采样或缓存策略。

工程曾记录离线 26 项游戏测试通过；这是已有日志结论，本次没有重跑游戏或板端测试。
现有全套识别回归仍有失败，顶层时序/CDC 尚未闭合，PYNQ 实板运行和跨板复用仍待验证。
不把工作流、合成测试或 PC 回放写成板端成功。

提交设计报告时，还需提供真实的大模型提示词、回答、自我纠错记录，以及这些技能的
使用前后对比。本文是经验提炼，不能替代原始交互记录或板上实测。

## 比赛交付仍需处理的差距

指南 3.3.3.1 推荐 Vivado/Vitis 2026.1 或 2025.2；本工程为 2023.1，须在报告中
说明版本选择并给出可复现脚本，无需为整理技能立即升级工具链。指南 3.3.5.4
要求交付文件路径使用英文字符；当前工作区含中文样本/附件路径，需要单独做交付审查，
本次未重命名已有文件。没有擅自添加开源许可证或发布仓库。
