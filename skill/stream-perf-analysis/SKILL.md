---
name: stream-perf-analysis
description: 分析流式日志的吞吐、延迟、新鲜度。
---
# 流式日志分析

先确定一个指标与单位，筛选同一启动/连接/时钟窗口；不全量转储日志。

- 原始事件按帧号/代次关联。无包、无效、PENDING、过期和显示保持分别计数；诊断拒绝计数不等于坏姿态数。
- 累计计数用差分；重连、回退、缺报告处分段。重叠耗时不相加，累计最大值不能推导窗口 P95。
- 跨设备无时钟映射时只给同域指标；保留原始采集时间，不把 UI FPS 当检测率。

累计 JSONL 在本技能目录用主机 Python 3.8+ 执行 `python scripts/analyze.py examples/audio-performance.jsonl --contract examples/audio-contract.json`；适配字段时读[格式](references/log-formats.md)。其他 UART/二进制格式按需读[事件分析](references/event-analysis.md)，不要硬塞给累计分析器。先 `--help`，按输出定位才读脚本。

回答主导瓶颈、两三项数据和最小下一步；分析任务不自动改阈值或连接硬件。
