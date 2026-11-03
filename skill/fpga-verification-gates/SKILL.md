---
name: fpga-verification-gates
description: 验证 RTL/AXI、复位、Bayer 与时序故障。
---
# FPGA 定向验证

把症状改写为可证伪条件，再选择能回答它的最低成本检查。

1. 绑定实际源码、参数、约束和输入；计数按同一帧/复位窗口关联。
2. AXI 按 VALID且READY 计数；覆盖背压保持、边界、复位和连续帧。CSI 包数、CRC0不能代替输出行数/有效字节。
3. Bayer 核对位打包、相位、裁剪奇偶与 DDR 顺序；不靠下游换色掩盖上游错误。
4. 只在问题需要时进入实现，检查当前时序/CDC/DRC；不添加无依据例外。

AXI、图像或实现任务按需读[定向用例](references/focused-checks.md)。输出一个结论、对应输入/结果和未覆盖范围；区分 host 模型、RTL 仿真、实现与实测，验收口径遵循项目明确规则。
