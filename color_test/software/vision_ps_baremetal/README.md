# Zynq PS 裸机视觉识别

本目录是从 `color_test/software/mipi_hdmi/mipi_hdmi/src` 独立复制出的临时上板程序，原摄像头应用保持不变。v2 同步修改 PL 颜色模块，关闭固定颜色替换，需要重建匹配的 BIT/XSA。程序识别 MIRROR、PORTAL_A、PORTAL_B、TARGET、SOURCE 和 WALL，结果同时输出 HDMI 和 UART1。

当前为 v3：完整帧交接、HDMI 标注、逐帧识别，并按 `pc_vision/` 对齐默认 HSV、全分辨率形态学和关键几何语义。不依赖 Python、OpenCV、Linux、神经网络或 OCR。

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
- mask：先在 1280×720 全分辨率执行 BGR→HSV、阈值和 OpenCV 3×3 椭圆核等价的 open/close，再每 4 像素采样为 320×180 连通域网格。
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

处理顺序是 BGR 转 OpenCV 标度 HSV、独立颜色 mask、全分辨率 3×3 open/close、4×4 间隔采样、8 邻域连通域、面积过滤、矩和协方差几何量、marker 验证。角度来自连通域主轴，不依赖多边形顶点数；Portal 方向为实心圆指向圆环。

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
vision_ps host tests passed (including overlay clipping)
....
OK
```

测试脚本将可执行文件放在系统临时目录，不修改测试图像或原摄像头工程。

## 构建 ELF

先安装并配置 Vitis 2023.1，然后在仓库根目录运行：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\build_vision_ps.tcl
```

脚本使用当前 `color_test/color_test.xsa` 创建 standalone BSP，直接编译本目录源码，并打印 ARM ELF 的 size。2026-10-01 黑屏防护修改后的离线构建结果为：

```text
text=108153, data=3264, bss=20934464 bytes
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
- 全分辨率 mask 已有 3×3 开闭运算，但候选仍为 4×采样连通域；小目标 marker 可能只有少量采样点。
- 嵌入式版没有 PC 端轮廓/孔洞层级；marker 使用主轴端点/中心的局部采样比例。
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

## PC_VISION_SPEC 与移植对照

黄金参考是 `pc_vision/config.py`、`detector.py` 和
`body_refinement.py` 的默认配置；`camera_low_contrast.json` 只是可选试调
profile，不是默认规范。PS 可通过 `VISION_USE_LOW_CONTRAST_PROFILE=1` 显式选择
同一 profile，默认值为 0。

- 输入是任意处理分辨率的 BGR888；本板固定 1280×720，active width 3840 bytes，
  DDR stride 5760 bytes。OpenCV 调用是 `COLOR_BGR2HSV`，H=0..179，S/V=0..255。
- 每个颜色的多个闭区间先分别 `inRange` 再按位 OR。默认阈值为：
  yellow 20..36/90..255/70..255，blue 90..130/85..255/45..255，
  orange 4..19/100..255/80..255，green 37..89/70..255/45..255，
  magenta 135..179 或 0..3/S>=65/V>=60，black V<=65，
  white S<=65/V>=175；WALL 独立为 S<=110/V<=120。
- 每个 mask 使用 3×3 `MORPH_ELLIPSE`、open 一次、close 一次。PS 在全分辨率 packed
  masks 上做相同 cross kernel 与边界语义，随后每 4 像素取样进入 320×180 网格。
- PC 主体候选使用 `findContours(RETR_EXTERNAL, CHAIN_APPROX_SIMPLE)`；
  marker 与 SOURCE 黑边使用 `RETR_CCOMP`。面积为 `contourArea`，周长为闭合
  `arcLength`；当前分类不调用 `approxPolyDP`，SOURCE 仅用
  `minEnclosingTriangle` 加少量置信分。
- PC bbox 是 `boundingRect`；中心优先使用 contour `moments` 面积质心；长宽比、
  fill 和主轴来自 `minAreaRect`。长轴角范围 [-90,90)，图像坐标顺时针为正。
  Portal 角从实心圆指向圆环，Target 固定为 0。
- marker 必须位于主体填充轮廓内。MIRROR 要求长轴两端黑色实心圆；Portal 要求两端
  白色实心圆+白环且环心保持主体色；Target 要求中心白环及近同心黑心。
- WALL 使用内部/外围 V 中位数差至少 12，深灰填充率至少 0.80，并拒绝与已接受彩色
  主体重叠超过 10% 的候选。分类顺序为 MIRROR、PORTAL_A、PORTAL_B、TARGET、
  SOURCE、WALL；无通用 NMS，仅已接受彩色对象抑制重复 WALL。
- 输出坐标是处理图像左上角原点的像素坐标。PS bbox/center 从 sampled grid 乘 4
  回到 1280×720；`sampled_area` 明确保持 sampled-cell 单位，不冒充像素²。

| 功能 | PC | PS v3 | 状态 |
| --- | --- | --- | --- |
| BGR/HSV、Hue wrap、阈值闭区间 | OpenCV + 默认配置 | 舍入误差允许 1；默认阈值一致 | EQUIVALENT |
| mask open/close | 全分辨率 3×3 ellipse | 全分辨率 packed cross | EQUIVALENT |
| 主体提取 | 外轮廓 | 4× sampled 8 邻域连通域 | APPROXIMATE |
| contour hierarchy | marker/SOURCE 使用 CCOMP | 无层级树 | MISSING |
| 面积 | contour 像素² | sampled cells，13 cells≈208 px | DIFFERENT |
| bbox/center | contour bbox/moments | sampled bbox/均值还原 | APPROXIMATE |
| angle | minAreaRect；Portal 有方向 | 协方差主轴；Portal 方向已对齐 | APPROXIMATE |
| marker | ROI 轮廓、孔洞、圆度、同心度 | 主轴端点/中心局部比例采样 | PARTIAL |
| SOURCE 黑边 | 闭合黑边恢复定位 | 仅品红主体 | MISSING |
| WALL 背景条件 | 中位数、填充、silhouette overlap | 中位数、bbox overlap | APPROXIMATE |
| 类别顺序 | 六类固定顺序 | 相同 | EQUIVALENT |
| overlay | PC 调试绘制 | 独立 HDMI bbox/中心/状态栏 | NOT APPLICABLE |

主机 parity 测试覆盖纯红/绿/蓝、灰/白/黑、Hue wrap、全部阈值上下界 ±1、
六类目标、组合优先级、frame edge、非紧密 stride、bbox/center 容差和 overlay
padding/clipping。PC 使用 200 px² 最小 contour 面积；PS 的 4×4 采样使该边界量化为
12 cells=192 px 与 13 cells=208 px，无法声称 199/200/201 像素逐点等价。
