# DMA/VDMA 交接细节

按目标 IP 文档区分 simple DMA、SG、VDMA 和循环扫描输出；不要移植不同 IP 的寄存器位或完成条件。

| 方向 | CPU 可用前置条件 | 常见误判 |
| --- | --- | --- |
| CPU→设备 | CPU 写完，按平台 API 清理缓存并排序，设备取得所有权 | flush 后立即覆写原缓冲 |
| 设备→CPU | 真实完成且设备不再写该槽，再执行同步/失效 | 仅看到帧开始、指针变化或 CRC0 |
| 循环显示 | 新提交被设备接受，旧槽经过设计规定的退休栅栏 | 当前 PARK 等于请求值便复用旧槽 |
| 退出 | 停止相关通道，确认停止/排空，再释放各自分配 | 异常路径先 free，设备继续扫描 |

PYNQ 的非一致性缓冲通常提供 `flush/sync_to_device` 和 `invalidate/sync_from_device`。先核对具体版本/驱动是否已执行同步，避免把 API 名称当作完成证据。设备地址来自实际分配器，不传虚拟指针或 Python `id()`。

裸板使用匹配 BSP 的缓存和屏障接口；`volatile` 不能代替它们。对齐按缓存行与 DMA 的 DRE/数据宽度共同决定。输入长度、有效最后行、stride 和分配 span 分别计算，不能把图像有效字节数当整个 DMA 存储跨度。

simple AXI DMA 等不到 S2MM 完成时，核对流端 TLAST、实际接收字节数与缓冲容量、配置长度上限；没有 TLAST 不能期待接收正常完成。该规则不直接套到 VDMA。

超时先保存原始错误位、通道/槽、序号和时间，不在采样前清错。允许重试时重试同一未完成操作，不能假报退休来解锁新提交。无法确认所有权时保留缓冲；恢复必须与该 IP 状态机一致。

复用检查：改为带行填充的图像；制造槽重叠、未对齐或 CPU/设备同时写的描述；静态校验应拒绝。完成栅栏需另用寄存器模型或目标平台验证。

依据：[PYNQ Buffer](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/allocate.html)、[AXI DMA](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/dma.html)。版本和 cache 模型变化时重新核对。
