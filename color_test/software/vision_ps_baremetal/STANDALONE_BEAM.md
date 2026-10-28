# 裸板实景光束测试版

2026-10-27 起，当前实景测试改用 Cortex-A9/core0 Standalone。运行链路为：

`FSBL → 匹配 PL → beam_standalone.elf → OV5640 → CSI/VDMA → CPU BGR 副本 → 原检测器/Portal 联合定位 → game_beam → 原图叠加 → HDMI`

光源固定 `(32,500)`，方向 `(1,0)`，画面 1280×720。支持 Mirror、Portal A/B、Wall、Target；无实体 SOURCE、KEY、菜单、关卡、计时或结算。Target 只终止本帧光线，下一帧继续计算。

固定光源位置由 `pc_vision/game_config.json` 的 `real_scene.beam.emitter_point` 生成；串口启动行也直接打印生成配置，避免日志与实际光路分离。

运行不需要 PYNQ、Linux、Python、rootfs、systemd、boot.py 或运行时素材文件。主机 Python 仅用于构建前检查 XSA、从唯一 `pc_vision/game_config.json` 生成 C 数据；板卡只运行 C。旧 Linux 路径保留为历史参考，没有删除或覆盖。

## 已生成的 SD 启动文件

用户已改为授权 Codex 编译和生成 BOOT。本次成功输出为（WALL 暗色主体修正版）：

`color_test/build/beam_standalone/beam_live_base_9/output/BOOT.BIN`

大小 **2360528字节**，SHA256：

`15296F5049B996F54F548503F7F1B27754096D539AE5282086BF4648A075658C`

只将这一个文件复制到SD启动FAT分区根目录，替换原`BOOT.BIN`；不需要复制ELF、Python或素材包。本次没有连接或操作板卡/SD。旧live平台/BIT/FSBL保持不变，镜像包含新应用，尚未上板验收。

build9 相比 build8 只增加了受面积、长宽比、填充率和画面相交约束的黑色 WALL 主体候选，用来覆盖白色端标记受光照丢失的情况；没有取消 B 防抖，也没有实现 PL 加速。

`beam_live_base_8/output/verification.json`记录ARM ELF与三段BOOT逐字节校验；构建日志为`output/build/game_app/beam_live_base_8_build.log`。严格编译/链接通过。Windows原生size/readelf无法启动，使用`tools/verify_game_beam.py`的字节解析校验替代；Bootgen重叠提示与旧live相同，已核对FSBL和应用执行区间不重叠，BIT是PL配置分区。目录1/2/6保留失败阶段日志，目录3/4/5/7保留此前用户上板版本。

用户返回的build4诊断已确认首帧在`beam_submit`触发`STALE(6)`：提交帧龄1363ms，识别1218ms，其中AprilTag检测1140788us、内部quad阶段1114199us。本轮两个DMA无错误并完成安全停止，`frames=0`，没有重现此前0x90。build5依用户决定仅取消测试版帧龄拒绝/停机，增加帧龄显示；检测参数、原始时间戳和DMA安全规则不变。其后用户运行结果见下一段，不代表识别已提速或画面已通过验收。

后续build5用户日志有86次提交：26帧无物体且OK，55帧识别到1或2个物体但PENDING，5帧Portal受限且RESTRICTED；日志没有故障停机记录。连续观测间隔1299..1799ms，均超过B防抖内部的250ms支持间隔，导致每次重置、无法凑齐两次确认。这个间隔独立于build5取消的帧龄门限。用户明确要求保留防抖并通过PL加速：本次保留B与其支持间隔，未改为A或保持旧姿态。build7仅补齐PL选型所需的分项测时和类型掩码，**尚未实现PL加速，也未修复本轮光线消失**。

build7之后用户把WALL和Mirror移到固定光线`y=648`附近，日志仍为`raw_mask=08/0c`，没有Mirror `01`或WALL `20`。源码检查发现旧UI有效场地过滤`center_y<590`，所以这些物块在最终过滤阶段被丢弃；不是颜色/形状门槛或ray求交证据。build8只在Standalone编译中改为完整720行并检查bbox与画面相交，颜色/形状/marker门槛没有放宽。先用build8验证该确定修正，再根据新的raw_mask判断是否还需调整颜色/形状阈值。

## 当前硬件基线：已实际运行的旧 live

默认改用 `color_test/build/vision_ps_baremetal/output/live/` 对应的历史平台，而不是之前说明中的 build5。已重新验证历史 `validation.json` 中12个输入/输出的大小与SHA256：XSA `03ae58ac...`、BIT `a5a88800...`、旧ELF `50391dab...`、旧BOOT `f1200d4c...`，包括原BSP、FSBL和PS初始化文件。

2026-10-26 的 `output/build/game_app/jtag_camera_pc_20261026_1/` 下载/状态日志记录旧ELF已运行、已提交1442帧、CSI CRC=0，S2MM `CR=0x10003/SR=0x11000`，MM2S `CR=0x10001/SR=0x11000`。这支持将该PL/平台作为恢复基线，**不等于新光束程序通过，也不证明旧光线抖动已经解决**。

这两个硬件版本不能只靠文件名互换：旧live是CSI1.1、16字节寄存器窗口、没有`DISPLAY_READY_O`；build5是CSI1.2、32字节窗口和带READY的显示复位链。默认构建冻结旧XSA/BIT/BSP/FSBL/ps7_init，不更新历史平台，不重新构建PL。新程序按所选硬件生成CSI版本和显示状态掩码，启动必须匹配；旧CSI不访问可能发生别名的`0x10`及以上地址。

## 源码入口与数据契约

- `src/standalone/game_beam_standalone.c`：独立主入口；构建不包含旧 `src/main.c`。
- `src/standalone/game_baremetal_io.c`：一个设备所有者；复用现有 sensor/I2C 源与 `game_display_*` 的可移植三缓冲状态机。`game_linux_display.*` 的文件名保留，但 Standalone 编译选择非 Linux 分支和新的 BSP 回调。
- `src/vision_ps.c`、`vision_portal.c`、`game_beam.c`、`ray_game.c`：沿用同一检测、稳定、几何和光路规则；不构造另一套游戏。
- `src/standalone/apriltag_port.c`：AprilTag 的单线程任务与 XTime 计时服务；不使用 pthread 运行库。仅 core0 主循环可调用，不可重入或从中断调用。

采集、显示各有三个独立静态 DDR 槽：每槽 `stride=5760, hsize=3840, vsize=720, span=4147200`。地址由链接器分配，通过匹配 BSP 的 DDR 范围检查，不使用 Linux CMA 或手填物理地址。

启动先沿旧live的 `CR=0x10003` 循环接收，复核实际布局并观察三个新的START，期间不读相机槽；通过后打印`BEAM_CAPTURE_CIRCULAR_OK`。然后才切换固定writer，执行请求/当前一致、W1C低和两个新START退休检查，通过后打印`BEAM_CAPTURE_PARKED_OK`。因此新日志可分开判断同一旧PL上的流启动与park交接；1442帧历史记录只覆盖前者使用的循环路径，没有验证新park路径。

后续固定writer持续接收。切换writer并通过同样退休检查，才能invalidate并复制旧槽；复制前后复核实际布局/控制/错误/park。没有恢复旧live仅看环形槽指针前后的复制方式，因为它不能排除复制期间绕圈覆写。检测和绘制只访问独立的 `2764800` 字节 CPU BGR 图像。显示提交继续使用原有 flush/barrier/park/两个新 START 退休检查。

generation 固定为本次启动的1，sequence 单调增长；`captured_ms` 是在源帧 START 之前取得的保守时间下界，不声称曝光时间。唯一JSON的`real_scene.beam.max_age_ms=0`表示本无关卡测试不按帧龄拒绝/停机；设回250可恢复原策略。保留时间倒退、未来时间、旧generation、重复帧、held帧拒绝及硬件超时/异常停机。图像、检测和光路仍对应同一CPU帧，不把旧姿态冒充新观测。HDMI上的`FRAME AGE ... MS`为渲染时相对该时间下界的帧龄，串口另记录提交/显示阶段年龄，均不是曝光到显示的精确延迟。完整游戏`board_game.scene_max_age_ms=250`未改动。取消门限只用于观察慢速测试，不能称为实时性通过。

Portal 模板、实测尺寸和有效边界直接从 JSON 派生；至少两个有效标签角点联合拟合，单标签/不一致标签只画橙色诊断边框，不提交有效 Portal 姿态。模型与光路仍是未完成公共平面标定的相机像素预览；不会自动改变当前标签打印尺寸或重做标定。

## 由用户编译

使用 Vitis/XSCT **2023.1**，从仓库根目录运行，明确选择历史live：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" `
  .\color_test\software\vision_ps_baremetal\tools\build_game_beam.tcl `
  -baseline live -tag beam_live_base_1 -boot 1
```

`-boot 0` 只构建ELF；`-boot 1` 同时生成裸板BOOT。默认`-baseline live`核对固定历史清单，复制已经匹配的BSP、FSBL、PS初始化和XSA/BIT到新输入目录，不调用`platform generate/update`。只编译新应用，旧ELF/BOOT和平台均不修改。拒绝覆盖已有`-tag`输出；若主机Python命令不叫`python`，设置`BEAM_PYTHON`为其完整路径。

只有明确比较现代CSI1.2/1.3硬件时，才选择`-baseline xsa -xsa <对应system.xsa>`；此路径从指定XSA创建新平台/BSP/FSBL，不能套用旧live的运行结论。不会在live构建失败后自动改用build5，也不会把CSI1.1仅按版本号放行，必须匹配固定XSA/BIT哈希。

预期输出目录 `color_test/build/beam_standalone/beam_live_base_1/`：

- `inputs/hardware.xsa`、`system_wrapper.bit`、`bsp/`、`fsbl.elf`、`ps7_init.tcl`、生成配置与`inputs.json`：冻结的构建输入及其身份。
- `output/beam_standalone.elf`、`.map`、`elf_identity.txt`。
- `output/BOOT.BIN`（选择`-boot 1`时）：仅包含**核对过的旧live FSBL + 同版XSA内BIT + 新ELF**，不包含U-Boot/Linux。它不是直接复制旧live/BOOT.bin，后者只运行旧应用。

AprilTag 使用动态内存，脚本将旧8KiB heap改为128MiB，主栈256KiB；最终 DDR 容量和段占用必须以链接结果/map为准。工程仍复用原 linker script，未修改历史 ELF。

输入检查仅证明器件/角色/数据宽度/声明时钟/高亮旁路/CSI ABI等静态契约，以及XSA提取文件身份；不能替代实际时序、CDC、相机稳定性和HDMI验收。CSI1.2提供一致计数快照；CSI1.3另支持此前尚未构建验证的被动边界观测器。**默认live恢复不要求构建新观测器或运行Vivado。**

旧CSI1.1只有直接计数器读取。代码重复读取、拒绝可见CRC错误/回退并保留原有计数进展检查，日志标记`counters_coherent=0`。连续相同读值不能证明跨时钟一致，不可把它包装成新CDC/完整帧有效性通过。若需要精确判定提前SOF、缺行或丢TLAST，仍须同帧被动信号证据；本轮不猜测修改LLP。

## 由用户上板观察

SD 裸板启动使用新 `output/BOOT.BIN` 放入启动 FAT 分区；需要保留旧内容时先自行备份。旧 `boot.py/image.ub/boot.scr/beam_runtime.tar.gz` 不参与新启动链，不需要复制进新裸板部署。Codex 本次未写 SD、下载或连接板卡。

JTAG调试使用新目录`inputs/system_wrapper.bit`、`inputs/ps7_init.tcl`和新ELF；不能在仍运行Linux/PYNQ的PS上直接覆盖ELF。旧live的下载日志是JTAG运行证据，不是新BOOT冷启动验收。启动模式切换、复位和下载由用户执行。

串口115200/8N1关注：`BEAM_STANDALONE_BEGIN` → `BEAM_CAPTURE_PREPARED` → `BEAM_HDMI_STARTED` → `BEAM_CAPTURE_CIRCULAR_OK` → `BEAM_CAPTURE_PARKED_OK` → `BEAM_CAPTURE_STARTED` → `BEAM_FIRST_FRAME` → 周期`BEAM_FRAME`。

首次异常先打印 `BEAM_FIRST_FAULT` 并保留全局 `game_beam_first_fault`，随后停止传感器、保留接收/消费时钟观察尾部，再确认采集和显示 DMA HALTED。无法确认时保留上下文/缓冲/必要时钟，进入常驻等待；无自动重置、清错或重试。`BEAM_CAPTURE_HALTED` 会另外显示仍保留的错误位，`BEAM_CAPTURE_RETAINED` 表示停机未确认。

CSI1.3 时可导出24行 `BEAM_BOUNDARY`；reason bit31表示软件发现异常后才冻结，不能解释成DMA故障的精确周期。旧 CSI1.2 不访问新增寄存器。故障证据保存在 RAM 和 UART，断电后 RAM 不保留，需保存串口文本。

`BEAM_FIRST_FAULT phase=1`为循环流启动，`phase=2`为第一次park退休，`phase=3`为后续复制/检测/显示。只有新日志能判断这些阶段：循环即失败时不能归因于本轮还没执行的park；循环通过、park失败也不能直接断言LLP缺陷，需结合首次CR/SR/PARK。build5取消的是应用帧龄门限，硬件等待和错误仍受原有安全检查约束。

build7启动应含`BEAM_DIAGNOSTICS version=3 max_age_ms=0 age_policy=disabled_test stability=B`和只读`BEAM_CPU`的MMU/I/D cache使能位。BSP启动代码已启用缓存，不能仅因main没有显式CacheEnable就断言缓存关闭。发生故障或成功帧周期报告时，额外输出：

build8相同诊断内容，仅新增Standalone全画面物体检测范围；无PL或CSI/VDMA改动。

- `BEAM_FRAME_DIAGNOSTIC`：精确结果、检测数`count`、原始帧标记、提交时实际使用的`submit_at_ms`及`age_at_submit_ms`。build4的STALE已由250ms门限解释；build5禁用帧龄门限后仍可因帧身份或时间无效返回STALE，不能仅凭状态名归因于处理慢。BAD_ARGUMENT时核对数量等输入契约。
- `BEAM_FRAME_COST`：采集等待与CPU复制、检测、诊断绘图、提交、渲染、显示耗时，单位ms，未执行/无法形成区间为`-1`。采集等待包含安全退休，不能当成纯memcpy耗时。
- `BEAM_PORTAL_COST`：灰度、AprilTag总检测、联合拟合耗时，单位us；`quad_us/decode_us`是`detector_us`内部阶段，不能重复相加。`called=0`表示本帧Portal后端没有运行，其零值不是性能通过。
- `BEAM_QUAD_COST`：`threshold_us/components_us/clusters_us/fit_quads_us`分别为上游现有profiler的阈值化、连通域、梯度聚类、四边形拟合区间，均包含在`quad_us`内；`stage_mask=15`才表示四项均已测到。这不是新增处理或加速结果。
- `BEAM_FRAME`新增`raw_mask/supported_mask/pending_mask/restricted_mask`；位0/1/2/3/5对应Mirror/Portal A/Portal B/Target/Wall，位4为已取消的SOURCE，应保持0。原日志不能识别PENDING物体类别，不能据此认定每类物体都已检测成功。

诊断在完成时间采样和原始硬件首故障冻结后打印，避免串口输出计入同帧检测/提交耗时。没有改变`quad_decimate=1`、标签字典/质量门槛或时间戳。下一轮需观察`BEAM_FIRST_FRAME`和连续`BEAM_FRAME`，并保留上述耗时诊断；取消门限不能解决已测的1.2s识别耗时。

PL下一步：物块在场时取10..20帧分项耗时，先确定四个子阶段哪项占主导，再将相应像素/连通域工作移至PL，继续复用现有C解码、Portal拟合和防抖入口。运行中的旧live BIT没有仓库的HSV特征模块，也没有AprilTag加速器；不能只接灰度/颜色模块便宣称解决约1s的quad开销。摄像头/显示退休等待也计入有效观测周期，硬件加速后仍需验证完整间隔低于250ms。任何PL结果须匹配同一原图帧和原始标记，经cache和所有权检查再交给PS；最终还需新BIT/XSA/BOOT的时序/CDC/资源和实板验证。本次未执行Vivado或修改BIT。

当前此前首帧前 `S2MM SR=0x15090 / errors=0x90` 的原因仍未确认。裸板迁移不会自动修复 CSI/LLP/AXI 帧边界，必须以新的编译结果及板端日志判断。

本轮18项输入/基线/构建控制流检查及8项原配置检查通过，包含测试版0/250策略与完整游戏250ms保留检查；严格ARM编译/链接、BOOT生成及三段字节校验通过。新增host C帧龄模式回归因已知本机GCC的DLL重定位问题未执行，保留测试源码。**本轮没有进行RTL仿真、Vivado构建或实板运行**；不能将编译/打包通过称为0x90根因修复或实时闭环验收。
