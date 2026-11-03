# 累计统计输入格式

分析器是 Python 3.8+ 标准库工具，对输入只读，结果打印 JSON。它不连接 UART、不导入原项目、不生成硬件报告。

每行一个 JSON 对象：`connection` 为整数或字符串；`report` 为非负整数；`stage` 为阶段名；`n` 为累计样本数；`total` 为累计耗时微秒；`maximum` 为累计最大耗时微秒；测量阶段 `unit="us"`。布尔值不能代替整数，计数和耗时必须非负。一个报告内每个配置阶段恰好一行，报告连续排列。

配置 `version=1`，`stages` 映射名字到类型：leaf 独立阶段、envelope 包含其他阶段、span 可重叠跨度、event 计数事件（耗时必须0）、meta 元信息。可选 boot_marker 指向一个 meta 阶段的 n/total/maximum 字段；其回退只能发现部分重启，不能证明启动身份。

相邻完整报告且连接相同、report 递增、计数不回退时，窗口均值为 `(total2-total1)/(n2-n1)/1000` 毫秒。缺报/重复/未知阶段使报告丢弃并断开窗口；回退或不可能的窗口总量也断开比较。没有新样本时均值为 null。累计最大值原样输出，不能推导窗口最大值或分位数。

累计 maximum 增大意味着窗口内出现了该耗时的新样本，新增 total 至少应等于新 maximum，否则窗口矛盾。maximum 沿用旧值时没有这一最低总量要求；仍检查新增 total 不超过新增 n 乘以累计 maximum。

退出码：0 至少一个有效窗口；2 没有有效窗口或输入/配置/文件错误，原因分别在 JSON 或标准错误中。结果中的 limitations 应随结论一起解释。输入已经按已知连接/启动区间分段仍是调用方责任。

`performance.jsonl` 是项目保留的62行累计报告样例，`project-perf-contract.json` 为匹配阶段契约。`audio-performance.jsonl` 与 `audio-contract.json` 是新合成的换题示例，两报告的 n 为10/20、total为10000/40000，均值3ms。

事件型串口 JSONL（event/time_ms/data_hex等）不符合此格式；应先用目标协议的规范解析器取得真实帧和对应诊断，或者独立分析同域事件。不能直接改字段名冒充累计数据，也不因格式不匹配而另建一套协议。
