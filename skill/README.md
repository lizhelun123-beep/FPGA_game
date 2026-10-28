# 工程技能说明

这些技能服务于 [最终方案](../pc_vision/FINAL_PLAN.md)：板端摄像头精确定位、固定关卡光源驱动的动态光路，以及实景叠加/电脑 Godot 游戏两种呈现。统一 1280×720，复用现有检测、C 会话、光路和配置。它们是按问题使用的工程指引。

## 选择技能

| 技能 | 只在以下问题出现时使用 | 输出 |
| --- | --- | --- |
| [ray-game-integration](ray-game-integration/SKILL.md) | 固定光源契约、Portal 多标签姿态、有效边界、防抖或 Godot 正式会话桥接 | 当前接口改动、最小验证与未覆盖范围 |
| [xilinx-project-flow](xilinx-project-flow/SKILL.md) | Vivado/Vitis/XSCT、XSA/BIT/XDC、BD/IP、PS/Linux 或工具链阶段路由 | 阶段选择、现有入口、同源制品和最小下一步 |
| [pynq-dma-contract](pynq-dma-contract/SKILL.md) | capture/display 缓冲、stride、cache、所有权、DMA 停止或复用不清楚 | 一份短契约结论和最小修复/验证动作 |
| [stream-perf-analysis](stream-perf-analysis/SKILL.md) | 需要判断实时帧率、处理延迟、新鲜度或遮挡保持期 | 一个主导瓶颈、已有数据和下一步 |
| [fpga-verification-gates](fpga-verification-gates/SKILL.md) | PL/RTL、AXI、Bayer、时序/CDC 或制品同源性直接阻塞闭环 | 只覆盖当前改动的最小验证结论 |

默认先读 `AGENTS.md`、最终方案相关段落、`PROJECT_STATE.md` 当前摘要和目标源码。实际涉及 Vivado/Vitis/PS/板端工具链阶段时才读 `xilinx-project-flow`；纯电脑呈现或离线定位不进入硬件流程。按当前问题补充专门技能，不加载全部目录、模板、历史报告或日志。

## 共同规则

- 只回答当前问题；优先静态检查、host 回放和 ARM 编译，再考虑板端或 Vivado。
- 现有证据可以直接引用路径和结论。除非用户要求或新证据确实需要，不新建 REVIEW、审计、总结、交接或重复 JSON 报告。
- 板端连接、下载/复位/烧录、SD 写入、服务改动和完整 Vivado 构建仍需当前任务明确授权；技能说明本身不构成授权。
- 明确区分离线、host、ARM 和真实板端结果，不把模拟画面或旧制品写成实时摄像头或完整游戏通过。
- 输出优先包含：改动/结论、验证或证据、未覆盖范围、最小下一步。分析日志本身不改阈值；用户要求实现防抖时，可在唯一配置中按同一录像的 A/B 比较调整算法，不能借此放宽新鲜度、CRC 或所有权门限。
- 改写或清理旧版前保存包含实际待移除内容的 Git 提交；本次修改前说明已归档至 `codex/archive-pynq-guidance-20261026`（`5da71ab`）。PYNQ 的采集与 DMA 仍保留，旧版“实体 SOURCE 必检、PC 仅参考、PYNQ 全虚拟画面”的目标以最终方案为准。

## 现有脚本

`stream-perf-analysis` 下的脚本可对已有 JSONL 做只读计算。只有用户明确要求性能分析时才运行；脚本输出直接留在终端即可，不要求另存报告。
