# 复用与路由检查

这些是可用于人工或智能体评估的任务，不是已完成的跨板 LLM 性能基准。维护时只提供对应入口和该项输入，检查实际决策；禁止为得到预期答案改输入含义。

| 提问/输入 | 首选技能 | 应观察的决策 |
| --- | --- | --- |
| 只有 BIT/HWH，想知道 accel_0 的地址 | pynq-overlay-control | 纯离线提取，不调用 Overlay 下载，不声称同源 |
| HWH 中两个模块共用短 INSTANCE | pynq-overlay-control | 模块与 MEMRANGE 均核对唯一归属；完整模块路径不消除地址记录的歧义 |
| CPU 读到旧图，设备仍可能写入 | pynq-dma-contract | 先查所有权与完成，再查同步；不先释放 |
| simple AXI DMA 的 S2MM 一直等不到完成 | pynq-dma-contract | 读交接参考检查 TLAST、实际字节数、容量与长度上限，不套到 VDMA |
| 图像有效48字节、stride64、4行，只分配192字节 | pynq-dma-contract | 按声明整行契约拒绝；要求至少256字节 |
| 裸板 ELF 想从 Python 直接加载 | pynq-c-runtime | 改编译目标和平台入口，核对 ABI；复用算法 |
| C 只接收连续指针，却传入转置或负步长 ROI | pynq-c-runtime | 核对布局/字节范围；按接口传步幅或在归还 CPU 并同步后复制，保持存活 |
| Notebook 重跑第二次占用同一个 UART | pynq-c-runtime | 复用/关闭原 Session，不再开第二个所有者 |
| 裸板观察到7候选后画面退出 | baremetal-runtime | 区分业务歧义与设备故障，不截断候选或套systemd |
| 只改 C 串口协议，需要新应用 | xilinx-project-flow | 匹配 BSP/硬件，定向编译；不默认完整实现或写卡 |
| CRC0但只收到719行 | fpga-verification-gates | 关联同帧有效行/握手；CRC不代表整帧 |
| 累计报告回退/重连，想算均值 | stream-perf-analysis | 切断窗口，不跨启动相减，不推导P95 |
| 新增 total=1000us，maximum 却从1000增至5000us | stream-perf-analysis | 拒绝不可能窗口；旧 maximum 不变时允许新增总量小于旧最大值 |
| 关卡仅需三类，输入中有五类 | ray-game-integration | 从产品规则适配必需集合，仍拒绝缺失/重复；额外碰撞实体不任意忽略 |
| 要改网页按钮颜色 | 无需这些技能 | 不加载 DMA/BSP/PL 流程 |

可直接执行的验证：Overlay 的9个合成用例、DMA静态正反例、统计窗口正反例。单独复制带脚本的技能后，应能从其入口得知主机版本和工作目录。打包校验还应把每个技能单独复制到新目录，确认链接和工具不依赖原工程。完整脚本结果以本次包的 verification.txt 为准。
