# 修改日志

## 2026-09-30 v2：完整帧及 HDMI 标注

- S2MM 配置单帧计数，确认帧完成且 HALTED 后才把 frame 0 复制给 CPU。
- frame 1/2 交替供 CPU 与 MM2S 使用；cache flush 后切换 park 指针，确认当前显示帧索引再复用旧缓冲区。换帧有 250 ms 超时。
- 识别在未标注的完整副本上运行；之后绘制 bbox、中心、类别、规则置信度及状态栏。
- 摄像头健康检查改为帧完成轮询，2 秒只作为超时；UART 限制为每秒输出一次。
- PL 新增 ENABLE_HIGHLIGHT，默认 0，保留 Gamma/WB，禁用固定颜色替换；兼容仿真显式启用旧高亮功能。
- Vivado 构建脚本显式重置 subset converter 的旧排队任务，避免等待残留任务。
- 验证：主机六类识别及标注边界测试、ARM 严格语法检查、15 项原摄像头恢复测试、17 项高亮 RTL 测试和 ISP 颜色保真测试通过。
- 硬件实现、最终 ELF 与板上验证正在进行；本条不代表上板验收完成。

局限：这是完整帧快照方案，显示刷新使用最近处理结果，不承诺摄像头满帧率。PL 仍做 Gamma/WB，因此 HSV 需按 OV5640 实拍标定。CONF 不是概率。

## 2026-10-01：固定 BIT/LTX 产物路径

- 原因确认：Vivado GUI 在上一轮实现完成后执行了 `reset_run synth_1`，连带清理其管理的
  `color_test.runs/impl_1`。该目录只剩步骤标记文件，因此完整下载脚本找不到
  `system_wrapper.bit`；位于运行目录之外的 XSA 和报告没有被删除。
- `build_bitstream.tcl` 和 `rebuild_debug_hub.tcl` 现在要求运行目录同时存在匹配的
  BIT/LTX，成功后复制到 `color_test/build/hw`。复制顺序为 LTX 后 BIT，BIT 更新表示整对
  调试产物已经就绪。
- 完整 JTAG 下载脚本及 SD 启动 BIF 改用 `build/hw/system_wrapper.bit`，后续
  `reset_run` 不会删除正式副本。
- 本次按要求只修改脚本和文档，没有重新运行 Vivado 构建、连接板卡或烧录；稳定目录中的
  BIT/LTX 需要下次完整构建成功后生成。

## 2026-10-01：黑屏诊断及有效帧保护

- 彩条先于相机启动，新增显示启动/彩条/首帧提交阶段与寄存器日志；完整有效帧绘制状态栏后才显示。
- CSI/CRC 窗口从采集启动前开始，支持回绕和单次消费；全零帧保留旧画面并重试，不以亮度阈值拒绝暗场。
- 换帧确认后才提交所有权，超时撤回旧 park 并冻结缓冲区；失败持续打印和保留画面，main 不退出。
- 官方 S2MM VSIZE 宏及配置高度替代读回重写；校验尺寸、stride 和帧地址；未改 PC/PS 识别阈值或 PL。
- 流水线故障注入、原识别/overlay 主机测试、ARM 严格编译通过；ELF text/data/bss 为 107513/3264/19091264 字节。
- BIT/XSA/PS init/ELF 新鲜度通过，XSA 内 BIT/PS init 与实际文件一致。未连接或烧录板卡，物理可见性与黑屏阶段尚待另行授权验收。
