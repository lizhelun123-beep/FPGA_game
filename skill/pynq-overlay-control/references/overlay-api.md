# Overlay/MMIO 的分阶段操作

静态预检不导入 PYNQ。相同文件名只是一种配对约定，还要绑定同次构建导出的 BIT/HWH/XSA 和目标器件。`inspect_overlay.py` 核对文件与 HWH 内容，不能从任意两个文件证明同源。

层级设计的短 INSTANCE 可重复；查询完整 FULLNAME 后，MEMRANGE 的归属仍须唯一。地址记录只有歧义短名时拒绝，不合并给任一模块；没有 INSTANCE 的范围不能归给目标。此时核对原 HWH/构建设计，不猜测硬件地址。

需要 PYNQ 元数据且环境允许时：

```python
from pynq import Overlay
overlay = Overlay(bit_path, download=False)
info = overlay.ip_dict[ip_name]
```

此调用不主动下载 BIT，但驱动初始化可能查询平台信息；不要将它当完全离线工具。实际 API 取安装版本，旧 PYNQ 的 HWH 解析能力不等于新 Vivado 元数据支持。

授权加载后按目标流程下载，优先使用已绑定 IP 对象的 `register_map`。若寄存器元数据缺失，用匹配 IP 规格里的 offset/宽度建立薄驱动，不能凭其他 Overlay 的地址猜测。

寄存器访问前核对：对齐、访问宽度、有效掩码、大小端、RO/RW/W1C、读清零和副作用。以32位 W1C 为例应写明确待清位，不读取整字后原值写回；参数写入使用已核准范围并按规格读回。GPIO 额外检查 EMIO/MIO、编号、方向、有效电平和复位次序。

超时保留 IP/offset、原始返回值和输入，不全域扫描寄存器。运行中重载 Overlay 前先结束所有依赖设备的任务并排空 DMA。Notebook 重跑不得创建第二个所有者。

依据：[PYNQ Overlay 教程](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/overlay_tutorial.html)。
