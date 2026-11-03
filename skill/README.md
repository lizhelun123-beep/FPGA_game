# PYNQ 与裸板工程技能包

供智能体按任务选用的 8 项技能。入口只保留决策规则，详细接口和示例按需读取；不依赖原摄像头题目、板卡地址或聊天记录。

| 技能 | 适用任务 | 必要输入 / 失败边界 |
| --- | --- | --- |
| [pynq-overlay-control](pynq-overlay-control/SKILL.md) | Overlay、MMIO、GPIO 和 register_map | 配对 BIT/HWH、目标版本；静态元数据不证明同源或可下载 |
| [pynq-dma-contract](pynq-dma-contract/SKILL.md) | DMA/VDMA 布局、cache、交接与释放 | 格式/stride/span、所有权；未知完成条件不能判定退休 |
| [pynq-c-runtime](pynq-c-runtime/SKILL.md) | Python/Jupyter 调用 C/C++ | 头文件、ABI、sysroot、数据寿命；不直接运行裸板 ELF |
| [baremetal-runtime](baremetal-runtime/SKILL.md) | Standalone 入口、计时、UART 与恢复 | BSP/链接脚本、时钟、设备契约；不套 Linux 服务流程 |
| [xilinx-project-flow](xilinx-project-flow/SKILL.md) | 软件/PL 构建阶段与制品交接 | 器件、工具、来源；不自动重建 PL 或写卡 |
| [fpga-verification-gates](fpga-verification-gates/SKILL.md) | AXI、图像、复位与时序反例 | 实际配置与可证伪条件；区分模型/仿真/实测 |
| [stream-perf-analysis](stream-perf-analysis/SKILL.md) | 已有日志的吞吐、延迟、新鲜度 | 同时钟/启动窗口；不能从 UI FPS 推识别速度 |
| [ray-game-integration](ray-game-integration/SKILL.md) | 姿态、求解与呈现一致性 | 身份、坐标、有效边界；显示保持不充当新观测 |

## 使用

把需要的单项文件夹放入所用工具的技能目录，或直接将其 SKILL.md 作为任务说明。每项只引用自身目录内资料，可单独携带。不要把整个技能包全文加入提示词，也不要自动串联全部技能。

例：`使用 $pynq-overlay-control，检查给定 BIT/HWH 的 accel_0，先做离线核对。`
脚本命令以对应技能目录为工作目录；先用 `--help`，需要修改脚本时才阅读源码。

主机自检仅需 Python 3.8+ 标准库，无 PYNQ、网络或设备依赖：

```text
python -B skill/scripts/verify_package.py skill
python -B skill/scripts/measure_context.py skill
```

Overlay 元数据、DMA 布局与累计日志脚本含可重复正反例。检查通过只覆盖其声明范围；算法、RTL、目标 ABI 和硬件操作仍按项目要求验证。更换板卡/题目时替换格式、地址、版本、时钟和产品规则，不照抄示例参数。

## 参考与提交

[案例比较](references/source-patterns.md)记录 6 个公开 Skill 的可用设计及取舍；[场景检查](references/usage-cases.md)提供路由/迁移用例；[提交对应](references/submission-requirements.md)说明材料范围。上述资料供评审或维护使用，普通任务不必加载。

从仓库根生成独立包（目标必须是新目录）：

```text
python -B skill/scripts/package_skill.py --destination output/build/game_app/skill_submission_20261101
```

ZIP 含根说明、`skill/`、文件哈希、入口体积和离线验证结果。原工程参数/历史证据、构建输出、venv、缓存和固件不进入提交包。完整工程源码、设计报告及协作记录另按提交要求组织。
