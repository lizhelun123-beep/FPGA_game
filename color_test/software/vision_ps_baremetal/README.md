# Zynq PS 裸机视觉识别临时版

本目录是从 `color_test/software/mipi_hdmi/mipi_hdmi/src` 独立复制出的临时上板程序，原摄像头应用保持不变。v2 同步修改 PL 颜色模块，关闭固定颜色替换，需要重建匹配的 BIT/XSA。程序识别 MIRROR、PORTAL_A、PORTAL_B、TARGET、SOURCE 和 WALL，结果同时输出 HDMI 和 UART1。

当前为 v2：完整帧交接、HDMI 标注和逐帧识别。不依赖 Python、OpenCV、Linux、神经网络或 OCR。下载方式为 JTAG 临时运行，掉电后失效。

## 目录

- `src/main.c`：摄像头/显示主程序及视觉调用入口。
- `src/vision_ps.c`、`src/vision_ps.h`：整数 HSV、连通域、几何量和 marker 验证。
- `src/vision_ps_config.h`：全部 HSV 和 marker 阈值，现场调参优先修改此文件。
- `tests/test_vision_ps.c`：六类合成目标、错误 Portal marker 和亮度渐变 WALL 回归测试。
- `tools/test_host.ps1`：使用主机 GCC 编译并运行算法测试。
- `tools/build_vision_ps.tcl`：用 Vitis 2023.1/XSA 构建 Cortex-A9 ELF。
- `tools/run_vision_elf_jtag.tcl`：保留板上已有 PL，只下载临时 PS ELF。
- `tools/program_vision_ps_jtag.tcl`：校验并下载完整 BIT、PS 初始化文件和 ELF。

生成文件不放在本目录，位于：

```text
color_test/build/hw/system_wrapper.bit
color_test/build/hw/system_wrapper.ltx
color_test/build/vision_ps_baremetal/output/vision_ps_baremetal.elf
color_test/build/vision_ps_baremetal/output/vision_ps_baremetal.map
```

`color_test.runs/impl_1` 是 Vivado 管理的临时运行目录，执行 `reset_run` 会删除其中的
BIT/LTX。硬件构建成功后会把匹配的 BIT/LTX 复制到 `color_test/build/hw`，完整下载脚本
只使用该稳定副本。

## 当前输入和输出

- 输入：1280×720、BGR888。
- VDMA 行跨度：5760 字节，即 `1920 * 3`，不能按 `1280 * 3` 读取下一行。
- 采样：水平和垂直每 4 像素取样一次，逻辑分辨率为 320×180。
- 采集缓冲区独占 frame 0；S2MM 单帧完成并停机后，CPU invalidate 并复制至空闲显示缓冲区。
- 显示缓冲区 frame 1/2 交替使用，CPU 分析与标注完成后 flush，再等待 MM2S 当前帧指针确认换帧，才允许复用旧缓冲区。
- 输出：HDMI 叠加 bbox、中心十字、类型、CONF（百分数）；左上角显示 VISION V2、COUNT 和 PROC 耗时。PROC 不含等待换帧时间，不代表完整显示 FPS。
- UART1 115200 波特率，最多每秒打印一次结果。健康检查等待完成帧，2 秒仅是无帧超时，不再每次固定休眠。
- PL 禁用固定蓝/红/橙颜色替换，保留 Gamma 及固定白平衡；HSV 仍需按实际 OV5640 图像标定。

串口示例：

```text
Vision PS v2: complete frames, HDMI overlay, frame-driven processing
VISION detections=6 sample_step=4
VISION MIRROR cx=170 cy=80 bbox=40,48,264,64 angle=0 confidence=99 area=...
VISION WALL cx=800 cy=288 bbox=648,252,304,76 angle=0 confidence=75 area=...
```

## 识别规则

处理顺序是 BGR 转 OpenCV 标度 HSV、独立颜色 mask、8 邻域连通域、面积过滤、矩和协方差几何量、marker 验证。角度来自连通域主轴，不依赖多边形顶点数。

- MIRROR：黄色长条为候选，主轴两端必须分别有黑色实心区域。
- PORTAL_A：蓝色胶囊候选，一端为白色实心圆，另一端为白色环且环中心仍为蓝色。
- PORTAL_B：与 PORTAL_A 相同，主体颜色改为橙色。
- TARGET：绿色近圆候选，中心附近必须同时满足白环和黑色中心。
- SOURCE：品红色连通域是主要依据，只用基本面积和形状范围辅助，不要求精确三个顶点。
- WALL：低饱和、低亮度长条候选；要求足够面积、长宽比和相对周围背景的亮度差，并排除已接受彩色目标的重叠区域。

`confidence` 是规则通过后的固定等级分数，用于区分规则强弱，并非统计概率。当前值为 MIRROR/PORTAL 99、TARGET 96、SOURCE 80、WALL 75。

## 主机测试

在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\color_test\software\vision_ps_baremetal\tools\test_host.ps1
```

预期输出：

```text
vision_ps host tests passed
```

测试脚本将可执行文件放在系统临时目录，不修改测试图像或原摄像头工程。

## 构建 ELF

先安装并配置 Vitis 2023.1，然后在仓库根目录运行：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\build_vision_ps.tcl
```

脚本使用当前 `color_test/color_test.xsa` 创建 standalone BSP，直接编译本目录源码，并打印 ARM ELF 的 size。2026-10-01 黑屏防护修改后的离线构建结果为：

```text
text=107513, data=3264, bss=19091264 bytes
```

较大的 BSS 主要来自原摄像头程序的 DDR 帧缓冲区。视觉算法使用固定静态工作区，不执行动态内存分配。

## JTAG 临时下载

### 板上已经配置了匹配的 PL

这是修改阈值后最快的迭代方式：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\run_vision_elf_jtag.tcl
```

脚本会检查 XSA、源码和 ELF 的时间关系，然后先停止显示/采集两个 AXI VDMA 通道，再复位 Cortex-A9 #0、下载 ELF 并运行。它不会调用 `ps7_init.tcl`，因此不会重新初始化正在使用的 PS PLL、时钟或 DDR，也不会改写 PL bitstream。该方式要求板上已经配置与 XSA 对应的 PL，并且 PS/DDR 已经完成上电初始化。

### 完整下载 PL 和 PS

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\program_vision_ps_jtag.tcl
```

完整脚本在连接板卡前检查 BIT、XSA、PS 初始化文件和 ELF 是否齐全且新鲜。只检查、不下载：

```powershell
$env:VISION_JTAG_CHECK_ONLY = "1"
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\program_vision_ps_jtag.tcl
Remove-Item Env:VISION_JTAG_CHECK_ONLY
```

如果脚本报告 `stale build output`，应按它给出的命令重新生成对应硬件或软件产物，不能用旧 BIT 和新 XSA/ELF 强行组合下载。

脚本停止 VDMA 使用当前工程固定地址：采集 S2MM 控制寄存器 `0x43000030`，显示 MM2S 控制寄存器 `0x43010000`。如果硬件地址发生变化，必须同时更新脚本和 XSA。

## 调参

只修改 `src/vision_ps_config.h`，然后重新构建 ELF，并用 ELF-only 脚本下载。HSV 采用 OpenCV 标度：H 为 0..179，S/V 为 0..255。建议先从 PC 原型和同一摄像头的原始帧统计值修改颜色范围，再调整 marker 采样比例。

如需候选级串口诊断，可在 ARM 编译参数中加入 `-DVISION_TRACE=1`。诊断会增加串口输出量，不建议作为常态版本。

## v2 帧管理与已知限制

- 当前采用单帧采集后停机，而非全速视频环形采集；PS 复制后即重新启动 S2MM。显示重复最近一张已处理图像，帧率取决于采集、复制、算法及 HDMI 换帧耗时，不承诺 60 fps。
- 4×采样优先降低 PS 负载，小目标 marker 可能只有少量采样点。
- 嵌入式版没有移植 PC 端的形态学开闭运算和轮廓层级；marker 使用主轴端点/中心的局部采样比例。
- SOURCE 目前没有强制黑边验证；WALL 仍最依赖现场曝光、灰卡背景和阈值。
- CONF 沿用规则评分，不是概率；没有逐 marker 轮廓绘制。检测为零时仍有状态栏。
- 合成帧测试和 ARM 编译已经通过；真实识别精度仍需用板卡串口日志和未标注原始相机画面继续标定。
- 显示动态时钟的 `ClkStart/ClkStop` 已增加有限轮询超时；超时会返回错误并打印日志，避免 CPU 永久卡在时钟等待循环。

## 黑屏分阶段诊断（仅离线验证）

启动顺序为显示初始化、frame 1 彩条、5 秒仅彩条窗口，再启动摄像头。
UART 的 `DISPLAY_INIT_BEGIN/FAILED`、`DISPLAY_START_BEGIN/FAILED` 定位显示启动问题；
`BARS_ACTIVE` 表示 MM2S 无错误且 park 指针已确认，不等同于物理 HDMI 已验收。
`FIRST_CAMERA_FRAME_COMMITTED` 只在首张完整、非全零、带 VISION V2 状态栏的图像换帧确认后出现。
若彩条阶段已黑屏，检查显示链；若彩条可见而首帧提交后异常，检查采集/换帧日志。
本次未连接板卡，实际黑屏阶段仍需后续授权后观察。

每次启动 S2MM **之前**记录 CSI/CRC 基线，覆盖与 CPU 识别重叠的整个采集窗口。
健康条件：长包无符号增量非零、CRC 增量为零、完成中断和 HALTED 同时置位、无 VDMA 错误。
计数按 32 位模运算处理回绕（一个窗口少于 2^32 个事件），每个完成帧仅消费一次。
全零检查扫描所有有效像素并跳过 padding，不设亮度阈值；仅一个值为 1 的有效字节也放行。
完全零值无法区分极暗截断与无效数据，因此保留彩条/上一帧，每秒打印原因并继续采集。
识别算法和 HSV/marker 阈值没有调整。

换帧在 250 ms 内确认 MM2S 当前帧指针且无错误后才提交 `curFrame`。失败撤回旧 park，
进入 `DIAGNOSTIC HOLD`，冻结两个显示缓冲区并持续重试旧帧确认，禁止迟到切换后错误复用。
识别/重新启动采集失败同样保留画面并持续 UART 输出；CSI/S2MM 健康失败则分批重试相机初始化。
MM2S 错误时只复位读通道并重启保留画面。物理时钟/输出故障持续存在时软件不能保证 HDMI
可见，但会持续输出明确状态，不从 main 退出。

日志含 MM2S/S2MM CR、SR、PARKPTR、ADDR0、VSIZE、HSIZE、STRIDE 和三个预期 DDR 地址。
当前两个 XCI 均启用 `C_ENABLE_VIDPRMTR_READS=1`；启动校验三个地址槽、64-byte 对齐、
VSIZE=720、HSIZE=3840、stride=5760。采集三个槽均指向 frame 0，显示槽指向 frame 0/1/2，
但 MM2S 从启动即 park 在 frame 1，运行中仅选择 1/2。
BSP 驱动为 `axivdma_v6_13`，硬件 IP 为 `axi_vdma:6.3`。
[AMD PG020](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM-Vertical-Size-S2MM_VSIZE-Offset-0xA0)
确认 S2MM VSIZE 偏移为 0xA0；代码改用 `XAXIVDMA_S2MM_ADDR_OFFSET + XAXIVDMA_VSIZE_OFFSET`，
写入已配置高度，避免依赖读回。当前读回已启用，不能认定原来的 0xA0 是黑屏根因。

新增离线故障注入（需要 Python、主机 GCC 和已生成的 BSP 头文件）：

```powershell
python .\color_test\software\vision_ps_baremetal\tests\test_video_pipeline.py
```

测试编译实际 C 函数，覆盖无包、CRC 增长/回绕、包计数回绕、各 VDMA 错误、完成/HALTED 缺失、
重复消费、全零/近黑/padding、识别失败、换帧失败/超时/迟到切换、上一帧保留和读通道恢复、
地址/stride 错配，以及无 VSIZE 读回时重启仍写入 720。临时文件在 build 下自动清理。
本次 ARM `-Wall -Wextra -Werror` 编译、故障注入和既有算法/overlay 主机测试均通过；
CHECK_ONLY 新鲜度通过，XSA 内 BIT、PS init 与实际文件哈希一致。未烧录、未上板验收。
