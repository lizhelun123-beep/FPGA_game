---
name: pynq-overlay-control
description: 检查 PYNQ Overlay、MMIO、GPIO 与寄存器。
---
# Overlay 与寄存器接入

1. 核对板卡、PYNQ/Python 版本及同一构建的 BIT/HWH；先静态检查，再按已授权范围加载。`Overlay` 构造默认可能下载，预检明确用 `download=False`。
2. 从 HWH/IP 字典确认名称、地址范围、寄存器宽度和时钟，先读有文档的身份寄存器。优先 `register_map`；原始 MMIO 按目标规格访问。
3. 写前确认 RO/RW/W1C/读清零语义及参数范围；W1C 不做读改写，GPIO 极性和编号不照抄其他板。
4. Notebook 与常驻入口复用一个所有者，重载前先结束依赖 DMA 的任务。

仅核对文件时，在本技能目录用主机 Python 3.8+ 执行 `python scripts/inspect_overlay.py path/to/design.bit --ip IP_NAME`；输出只证明静态元数据。实际 Python 控制与失败分支按需读[操作细节](references/overlay-api.md)。不默认导入 PYNQ、下载 PL 或扫描未知地址。

输出匹配关系、访问方法及检查结论，不展开整个寄存器表。
