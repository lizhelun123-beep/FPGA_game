# 官方来源索引

查阅日期：2026-11-01。只保存会影响部署决策的结论，不复制教程。升级运行时/转换器、目标环境改变或兼容性有疑点时，重查对应来源的版本说明；不要整表重搜。下列资料支持通用方法，不证明本工程已实机部署。

## S1 LiteRT 入口

[Getting started with LiteRT](https://developers.google.com/edge/litert/overview)

用于区分新版 CompiledModel 与保留的 Interpreter 路径，并核对 SDK 要求。查阅时新版 Python 入口列出 Python3.9起的要求；不能据此给 Python3.6 板端直接安装最新版，更不能照搬示例模型作为业务识别成果。

## S2 ARM 构建

[Cross compilation Interpreter API with CMake](https://developers.google.com/edge/litert/build/cmake_arm)

用于核对目标指令集、32/64位、浮点 ABI、sysroot 和 GLIBC。文档的树莓派3/4示例使用 VFPv4/NEON；指定 GCC8.3 工具链的示例二进制提示 GLIBC2.28要求。它不是所有 ARMv7、所有工具链或当前 PYNQ 的通用安装命令。

## S3 量化

[Post-training quantization](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_quantization)

用于选择量化路线。先转换不量化的模型作为算子/数值基线；完整整数化需要代表性数据校准。量化后的精度、峰值内存和延迟必须重新测量，文档示例收益不是当前板卡的性能承诺。

## S4 性能证据

[Benchmark Interpreter API](https://developers.google.com/edge/litert/models/measurement)

用于分开测量初始化、预热、稳定推理和内存；再测应用级输入到结果的时延。线程数和后端须记录；单次 invoke 或模型基准不能代替相机、显示和串口一起运行的结果。

## S5 数据与预处理

[Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html)

用于预处理一致性和防止测试泄漏。先分数据再学习归一化等参数，训练和部署保持同一变换，测试集不用于拟合或选择阈值。按视频/采集批次分组是对本工程连续相机数据的适配判断。

## S6 权重与推理模式

[Saving and Loading Models — PyTorch](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html)

仅当训练/来源为 PyTorch 时读取：权重与模型结构需要匹配，优先保存 state_dict；推理设 eval。按实际版本采用 weights_only 等加载接口，不把训练主机上的 pickle 对象视为通用 ARM 部署格式。

## S7 分数与概率

[Probability calibration](https://scikit-learn.org/stable/modules/calibration.html)

用于区分模型分数、类别判定和经过检验的概率。高分不自动代表同等真实正确率；需要概率解释时，用独立数据检查校准，校准拟合也不能泄漏测试数据。
