# 目标接口契约模板

按目标系统填写；UNKNOWN 表示需要补证据，不代表零、不支持或通过。

| 项目 | 实际值 | 证据文件/位置 |
| --- | --- | --- |
| 契约版本、目标用途 | UNKNOWN | |
| 板卡、器件、内存范围 | UNKNOWN | |
| OS、Python、PYNQ、Vivado/Vitis 版本 | UNKNOWN | |
| 同次构建标识、源版本和配置 | UNKNOWN | |
| BIT/HWH/XSA 来源与 SHA256 | UNKNOWN | |
| IP 实例、VLNV/版本、基地址和范围 | UNKNOWN | |
| DMA 或 VDMA；MM2S/S2MM；simple/SG/park/genlock | UNKNOWN | |
| 数据/地址位宽、DRE、对齐、最大长度 | UNKNOWN | |
| 各时钟频率、复位极性、CDC 方式 | UNKNOWN | |
| 像素/样本格式、端序、平面与位打包 | UNKNOWN | |
| width/height 或每块样本数 | UNKNOWN | |
| 有效行字节、stride、分配字节 | UNKNOWN | |
| 每类缓冲数量、设备地址与地址区间 | UNKNOWN | |
| coherent 属性及证据、同步 API | UNKNOWN | |
| 提交/完成/错误/超时/帧序号语义 | UNKNOWN | |
| 中断与轮询；状态位是否 W1C | UNKNOWN | |
| 单通道唯一驱动、停机和释放顺序 | UNKNOWN | |
| 黄金输入、期望输出、容差 | UNKNOWN | |

每个缓冲画出实际所有权转移，例如：

```text
FREE -> DEVICE_WRITING -> READY_FOR_CPU -> CPU_READING -> FREE
FREE -> CPU_WRITING -> READY_FOR_DEVICE -> DEVICE_READING -> FREE
```

标明每条边由谁触发、完成依据、同步点以及失败时谁继续持有。状态名只是模板，
不能代替当前槽、帧序号、genlock 或明确握手证据。

预算表按链路分别填写：

| 链路 | 每帧/块有效字节 | 实际读写或同步 span | 最高帧/块率 | 最坏 B/s | 是否与其他项重叠 |
| --- | --- | --- | --- | --- | --- |
| capture / device write | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | |
| display / device read | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | |
| CPU copy read + write | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | |
| cache / algorithm / accelerator | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | |

应用到新板卡的验证记录：静态布局 → host 哨兵/步幅检查 → 获授权后单块已知输入
传输 → 长度/对齐/超时负例 → 所有权/多缓冲稳态。每步记录实际运行范围和失败边界。
