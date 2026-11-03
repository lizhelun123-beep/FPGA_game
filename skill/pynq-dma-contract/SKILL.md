---
name: pynq-dma-contract
description: 排查 PYNQ/裸板 DMA 步幅、缓存、所有权与释放。
---
# DMA 缓冲交接

只追踪出错通道的一个缓冲槽，不加载其他技能或项目历史。

1. 从实际配置取格式、有效行字节、stride、分配 span、设备地址和缓存属性；保留行填充，核对 DMA 模式与长度上限。
2. 写清 CPU写→同步→设备读、设备写完成→同步→CPU读。flush/invalidate 不证明设备完成；PARK、当前指针和帧开始也不自动证明旧槽退休。
3. 标明提交、完成、复用条件和超时分支；未知所有权时不重写、不释放。停止后按该 IP 的停止/排空语义确认，不能给所有 DMA 套同一个 HALTED 位。

主机 Python 3.8+，在本技能目录执行 `python scripts/check_layout.py examples/layout.json`；换输入先读[格式](references/layout-schema.md)。排查完成/超时或改交接时读[缓存与状态机](references/handoff.md)。脚本先用 `--help`，无需通读源码。

输出出错交接点、证据、最小修复和适用范围。静态布局通过不代表 DMA 实测完成。
