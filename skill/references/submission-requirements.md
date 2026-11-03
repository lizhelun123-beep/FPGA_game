# 技能子包的提交范围

依据用户提供的 PYNQ 建议片段组织：PS 用 Python/Jupyter 编排，PL 通过 Overlay 交接，并提炼不与题目/板卡绑定的加载、寄存器及 DMA 方法。本表不是对完整竞赛规则或评分结果的认定。

| 材料 | 对应位置 |
| --- | --- |
| 技能用途、方法与失败边界 | README 索引及各 SKILL.md |
| 通用 Overlay 加载/校验、register_map | pynq-overlay-control |
| DMA/cache、所有权及故障定位 | pynq-dma-contract，含静态正反例 |
| Python 调用 C、Notebook/常驻会话复用 | pynq-c-runtime |
| 裸板入口、计时、UART、缓存及恢复 | baremetal-runtime |
| 跨题目/平台复用示例 | usage-cases、音频累计统计、合成 DMA/HWH 夹具 |
| 可重复效果与范围 | verification.txt、脚本测试、各参考中的反例 |
| 外部设计参考 | source-patterns.md；只借鉴组织方式，规则按本工程重新编写 |

原工程的经验压缩为不带板卡参数的反例：PARK不等于退休、CRC0不等于整帧、额外类别与必需类别要区分、观测无效不应直接关停健康显示。这些方法不承诺更换硬件后的性能或成功率。

完整工程源码、设计说明、原始协作记录按实际提交要求另行提供。技能的静态自检不代替工程的功能验收；自定义验收口径也不改变测试实际执行环境。
