# Zynq PS 裸机视觉识别

本目录复用现有 OV5640、MIPI、VDMA、DDR 帧管理和 HDMI 链路，结果同时输出到 HDMI 和 UART1。默认源码配置保持六类识别和 Portal 光线游戏路径（`VISION_FIXED_SCENE_DEMO=0`、`VISION_GREEN_TARGET_ONLY=0`）；物理计算与 framebuffer 绘图分离。

当前 MVP 在摄像头画面上仅绘制光线路径和左上角小状态栏，默认不绘制识别 bbox、类别/置信度、中心十字或成功特效。不依赖 Python、OpenCV、Linux、神经网络或 OCR。状态栏以 `R2` 标识当前固件，`DET` 显示本帧识别类别，`HIT` 显示已提交光线实际命中的类别；字母顺序为 `M`（Mirror）、`A/B`（Portal）、`T`（Target）、`S`（Source）、`W`（Wall），`N` 表示无类别。

## 三关原生 C 离线运行（当前入口）

在仓库根目录使用现有 Python/Pillow/OpenCV 和 host GCC：

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -OfflinePackage
python -m pc_vision.app --native-game --photos sample_photo
```

第一条完成严格编译、定向检查、素材转换、确定性回放和软件打包；第二条复用现有
照片/视频/scene-v1 输入及桌面鼠标查看原生 C 画面，Python 只传输输入和 BGR 像素。
鼠标只点菜单；A/D 浏览照片，Q 退出。准备阶段不计时；新鲜且未命中的完整场景才可明确开始。
照片每次重新经过 C 检测，使用处理前时间戳，慢结果仍会过期。scene-v1 的原始 capture_ms
不被接收时间替换；旧记录时间轴不匹配时安全拒绝，精确游戏调度回放使用下述原生事件入口。

输出位于 `output/build/game_app/offline_native_20261021/`，含 `native_game_offline.zip`、
`verification.json`、`gallery.png`、14 张原生截图和 `events.replay`。解压包后在 Windows cmd 运行：

```bat
game_offline.exe --assets assets/game_assets.bin < events.replay
```

回放中的模型移动和时间为明确标注的模拟输入，真实照片检测另存 `photo_scenes.json`，原始 077 不改为已解。
素材为 5° 离散姿态、中心锚点 (56,56)、BGR888/FF00FF 色键，加载校验一次并在退出释放；
常驻素材存储 13,956,928 字节，CPU 画布 3,072,000 字节，另加结构体/进程开销。六类配色和
几何来自旧 PC 游戏与唯一 JSON；姿态量化不影响 C 求解。画面为保持比例的未标定预览。
现有 ARM 工具可生成 Cortex-A9 armhf 静态 ELF，仅通过离线链接；动态试制要求 glibc 2.35，
不进入交付包。未执行目标程序或验收 HDMI、采集、真实 A3 标定、DMA 缓存/切换/停机及热插拔；显示后端继续关闭。

## 三关游戏控制核心（离线）

`src/game_session.h/.c` 是供后续 Linux C/C++ 程序使用的标准 C99 核心。
复用 `SceneObject` 和现有 `ray_game_trace`，不依赖 BSP、Linux 设备、OpenCV、系统时钟或
Python 运行时。现有 `RayGameLevel` 的裸机/诊断行为保持原样；新核心未接入裸机 `main.c`，PC 原生画面入口见上文。

唯一手工配置为仓库 `pc_vision/game_config.json`：既有 `model_sizes`、`physics_scale` 共用，
新增 `board_game` 定义三关锚点/权限、逻辑边界、场景新鲜度和计时/渲染预算。生成器只转写配置，
不实现 Python 游戏规则。模板来自原图的 C 检测姿态和恒等映射；075/076 命中，原始 077 未命中仍合法。
默认边界 1279×719、固定模型尺寸均为**未标定预览单位**，不是 A3 毫米值。

从仓库根目录运行最小离线入口（需要已安装的 Python 3 和 PATH 中的 host GCC）：

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_session.ps1 -StaticOnly
./color_test/software/vision_ps_baremetal/tools/test_game_session.ps1
```

完整入口本身也先运行 C99 严格静态检查，再编译运行 `tests/test_game_session.c`，只链接新核心、
现有 `ray_game.c` 和生成配置。时间完全模拟，不等待三分钟，不运行既有有失败项的整体 host gate。
生成 `.h/.c` 和可执行文件仅在 `output/build/game_session/`。已知沙箱 WinError 623 如阻止 GCC
启动，遵守 AGENTS 的一次重试限制；不要反复切 shell、复制工程或启动完整构建。

Linux host 的等价命令（离线测试，不是 armhf 兼容性或板端验收）：

```sh
python3 color_test/software/vision_ps_baremetal/tools/generate_game_config.py --output output/build/game_session/game_config.h
src=color_test/software/vision_ps_baremetal/src
test=color_test/software/vision_ps_baremetal/tests
build=output/build/game_session
gcc -std=c99 -Wall -Wextra -Werror -pedantic -I"$src" -I"$build" -fsyntax-only "$src/game_session.c" "$src/ray_game.c" "$build/game_config.c" "$test/test_game_session.c"
gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic -I"$src" -I"$build" "$src/game_session.c" "$src/ray_game.c" "$build/game_config.c" "$test/test_game_session.c" -lm -o "$build/test_game_session"
"$build/test_game_session"
```

C/C++ 调用顺序：

```c
#include "game_session.h"
#include "game_config.h" /* generated declaration; compile its .c as C */
GameSession game;
/* Check every return value in the real adapter. now_ms is supplied externally. */
game_session_init(&game, &game_default_config);
game_session_select(&game, 1, now_ms);
/* Tag captured work with game_session_snapshot(&game)->generation. */
game_session_submit(&game, &mapped_complete_scene, now_ms);
/* Only a fresh unsolved scene sets snapshot->ready. Solved preparation input
   sets scene_status=GAME_NEED_UNSOLVED; prompt the player to adjust it. */
game_session_start(&game, now_ms); /* explicit menu action */
/* Continue submit on new captures and tick even when no input arrives. */
game_session_tick(&game, now_ms);
const GameSnapshot *view = game_session_snapshot(&game);
```

`GameSceneInput` 必须是**坐标映射后**的完整实测场景；每个配置类别恰好一个，Portal 按 A/B
身份匹配，SOURCE 使用有效 `source_direction`，其他类型使用有效 `axis`。测量 bbox 尺寸和
原 SOURCE tip 不参与游戏几何。任一保留/预测姿态须标记 `held=1`，检测/方向/映射失败须
`valid=0`；不能用模板补失踪物体。默认采集年龄 ≤250 ms，序号和采集时间在本关代次内严格递增；
均为外部同一单调毫秒时间线。代次在采集/任务派发时标记，切关后禁止把旧结果重标成新代次。
接收无效几何会清空候选，重复/旧代次输入不替换当前版本，过期准备场景不能开始。

约束后重算固定尺寸模型及 SOURCE 尖端；MIRROR 端点由该模型 `center ± axis*length/2` 得到。
绘制必须读取 `GameSnapshot.objects` 和同版本 `ray`，不能使用原始检测坐标。
若以后增加标定，初始化前将模板锚点和实测输入放入一致坐标系，尺寸也采用匹配单位；
不要在每帧重新标定锚点。本核心不做 EMA，后续滤波应只作用于允许的自由度。
沿用物理缩放 100，epsilon/出射偏移/Portal 偏移为 0.01/0.03/0.01 逻辑单位。
完整保留求解器 17 段结果；`render_budget_exceeded` 单独报告超过配置的 5 段预算，
不截断物理、不改变真实 TARGET 判定。未来渲染器必须显式处理超限，不能静默画前五段当完整结果。

准备不计时；三关均可选并可跳关，每次选择重新发出代次、清空本关候选和成绩，明确开始后
各自计时 180000 ms。需要新的开始后采集帧才可通关；开始前的已解照片不能自动赢。
有效命中按采集时刻计星：`<60000` 三星、`[60000,120000)` 两星、`[120000,180000)` 一星；
接收/tick 时达到 180000 ms 先判超时，迟到帧不能恢复通关。遮挡不暂停，终态的场景与成绩锁定。
核心为串行调用，调用方负责帧边界一致发布和线程同步。未添加重置按钮、进度保存或声音。

验证覆盖权限与几何、打乱输入后的 Portal 绑定、准备/独立计时/跳关/锁分、精确评分边界、
无效/保留/过期/重复/失踪/旧代次输入，以及合法的原始 077 和仅移动 MIRROR 的独立解。
本次严格静态检查及 host C 的 **261 项断言通过**，另通过 C++ 调用/链接检查、旧 PC 配置加载
兼容检查和配置生成一致性检查；未运行整套已有回归。
标准 C 检测场景适配与离线应用入口见下一节；Linux 采集/evdev、A3 标定、
真实显示/输入性能及板端验证仍待实现。
PYNQ 镜像原生 GCC 7.3/glibc 2.27 与现有交叉工具默认 glibc 2.36 的兼容限制仍有效，
host 测试不能证明 ARM ABI、BIT/HWH/FCLK 匹配、1280×800 显示或板端验收。

## 标准 C 场景适配与离线应用入口

`src/game_scene_adapter.h/.c` 接收现有 C 检测器的 `VisionDetection[]`，调用原有
`ray_game_scene_from_detections`，经映射接口产生 `GameSceneInput`。
`src/game_app.h/.c` 提供可调用的选关、派发标记、提交、明确开始、无输入 tick、快照复制及文本输出。
没有新检测器、光线算法或游戏规则，也不接管裸机 `main.c`、PC 照片浏览和原稳定器。

目前唯一随附映射为 `game_uncalibrated_identity_mapping`，文本输出明确标识
`mapping=uncalibrated_preview calibrated=0`。它保持原采集像素预览坐标，不能声称是 A3/mm
标定。`GameSceneMapping.map_pose` 为未来真实标定保留接口，必须同时映射中心和方向，
失败返回 0；坐标空间必须与初始化前已准备好的配置锚点、固定模型尺寸一致。
映射在应用寿命内不变，改变标定须重新初始化。运动约束、固定尺寸/尖端重算和物理缩放仍由
游戏核心在映射后、求解前执行；适配层不覆盖锚点，不用模板补齐实物。

`GameDetectionFrame.valid` 包含采集、检测及上游方向可靠性；任一物体保留/预测时必须设置
`held`。SOURCE 必须同时有 `direction_valid` 和有限非零 `source_direction`；其他类别必须有
有限非零 `axis`，其 `direction_valid` 是 SOURCE 专用字段，无需置 1。非零但不可靠的方向也须
将帧标为无效。先拒绝未知类别及坏方向，防止旧转换函数的 WALL/angle 后备值把无效检测变为
有效观察。负检测数量、空检测指针、超容量均按无效输入提交核心；不静默截断。
缺失/重复/额外类别及过期/序号/代次最终由核心判定，无效新帧也会消费序号并清空候选。

最小调用顺序（检查每次返回值；所有调用由外部串行调度）：

```c
#include "game_app.h"
#include "game_config.h" /* existing generator output */
GameApp app;
GameSnapshot view;
GameDetectionFrame work = {0};
game_app_init(&app, &game_default_config, &game_uncalibrated_identity_mapping);
game_app_select(&app, 1, now_ms);
/* Call ONCE at capture/work dispatch; carry work.stamp with the task. */
game_app_capture_stamp(&app, frame_sequence, captured_ms, &work.stamp);
/* Detector may finish later, even after selection changes. Keep stamp intact. */
work.detections = detections; work.count = count;
work.valid = detection_valid; work.held = any_retained_pose;
game_app_submit(&app, &work, delivery_ms);
game_app_start(&app, start_ms); /* explicit external/menu action when ready */
game_app_tick(&app, next_ms);   /* also when no frame arrives */
game_app_snapshot(&app, &view); /* one copied model/ray/generation/score version */
game_app_write_snapshot(&app, stdout);
```

派发标记原样携带 64 位采集时间、原帧序号和当时的关卡代次。提交不读取时钟、不替换时间或
代次；同一外部单调毫秒时间线驱动全部操作。新输入不会自动开始；原始 077 仍可作为合法
未解准备场景。快照是值复制，后续检测缓冲复用不影响输出；未来渲染器须在帧边界发布该副本。

从仓库根目录运行聚焦验证并生成独立文本入口：

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -StaticOnly
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1
./output/build/game_app/game_offline.exe
```

脚本先严格 C99 静态检查，再运行 `test_game_session.c`、`test_game_app.c`、
`test_game_loop.c`、`test_game_pump.c`、`test_game_render.c`、`test_game_linux_io.c` 和文本/图像 stdin 回放。
配置仍仅从 `pc_vision/game_config.json` 生成，全部产物在 `output/build/game_app/`。
测试以配置锚点构造检测姿态夹具，验证适配和调度，不重新运行检测器照片回归。
Linux host 可用相同源文件、生成配置及 `-std=c99 -Wall -Wextra -Werror -pedantic -lm`
编译；应用测试和文本入口分别以 `tests/test_game_app.c`、`tools/game_offline.c` 作为 main，
共同链接 `game_app.c`、`game_scene_adapter.c`、`game_session.c`、`ray_game.c` 和生成表；
事件循环/运行泵测试及文本入口还链接 `game_input.c`、`game_evdev.c`、`game_loop.c`、`game_pump.c`；渲染测试和文本入口再链接 `game_render.c`、`vision_overlay.c`。

文本入口由标准输入完全驱动，无系统时钟、无交互窗口、无自动初始解：

```text
select NOW_MS LEVEL
frame NOW_MS GENERATION SEQUENCE CAPTURED_MS VALID HELD COUNT
TYPE CX CY AX AY DIRECTION_VALID DX DY
start NOW_MS
tick NOW_MS
snapshot
quit
```

每条 `frame` 后紧跟 COUNT 行检测，类别依次为 0=MIRROR、1=PORTAL_A、2=PORTAL_B、
3=TARGET、4=SOURCE、5=WALL；`GENERATION` 必须是采集/派发时保存的值。
每次操作打印状态码及一份完整快照，枚举值见 `game_session.h`。
例如 `select 0 3` 只进入空准备态；没有新帧时仍须显式发送 `tick` 推进外部时间。
文本读入程序只是离线回放边界，不是 Linux 摄像头/evdev 驱动。

本次 C99 严格静态检查、适配/应用 **519 项断言**和原核心 **261 项断言**通过，时间完全模拟。
独立文本入口的原始 077、64 位时间/序号、明确开始及无输入超时回放也通过，记录在
`output/build/game_app/offline_smoke.txt`。
真实 Linux 采集/evdev 设备接入、中文界面、真实 A3 标定、显示集成与板端验证仍待完成；
host 通过不是 Linux 运行验证或板端验收。

## 菜单输入与单步离线事件循环

`src/game_input.h/.c` 定义平台无关的指针移动、左键按下/释放和连接事件，以及
`SELECT`/`START` 菜单动作。鼠标只操作菜单。按下和释放必须落在同一按钮，且关卡代次
相同，释放才触发一次动作；重复按下、拖入按钮和重复释放均不会重复选关或开始。
断开取消未完成点击，恢复后须先释放再点击。连接事件不自动选关、开始、重置或暂停。
开始按钮是否可用直接由本步 `GameSnapshot.state/ready` 派生，不维护另一套游戏状态机。

布局唯一手工来源为 `pc_vision/game_config.json` 的 `board_game.menu`，由现有生成器输出
`game_default_menu_layout`。渲染器共用该表：显示/菜单像素画布为 1280×800，三个选关矩形
与配置关卡顺序对应，独立开始矩形；命中区间为 `[x,x+w) × [y,y+h)`，不允许重叠或越界。
这不是显示时序验收，也不改变相机/游戏的 1279×719 未标定坐标。

`src/game_loop.h/.c` 串行复用 `game_app`。每次 `game_loop_step` 先调用 `tick(now_ms)`，
再处理至多一个事件，最后返回一份完整 `GameLoopOutput.game` 值快照及从它派生的菜单视图。
无输入时传 `NULL`；即使检测结果被拒绝也推进时间。外部批次按顺序使用相同 `now_ms` 调用，
批次结束只发布最后的副本；下节的运行泵提供串行调度和等待边界，真实单调时间源、
线程/设备集成及显示帧边界仍由未来平台负责。
时间倒退返回 `GAME_BAD_TIME`，不消费鼠标边沿。

```c
#include "game_loop.h"
#include "game_config.h"
GameLoop loop;
GameLoopOutput out;
GameLoopEvent event = {0};
/* Check every return status in the real caller. */
game_loop_init(&loop, &game_default_config, &game_uncalibrated_identity_mapping,
               &game_default_menu_layout);
event.kind = GAME_LOOP_MOUSE;
event.data.mouse = (GameMouseEvent){GAME_MOUSE_MOVE, x, y};
game_loop_step(&loop, now_ms, &event, &out); /* down/up events use the same API */
/* At capture/dispatch ONCE, after a level was selected: */
event.kind = GAME_LOOP_DISPATCH;
event.data.dispatch.sequence = producer_sequence;
event.data.dispatch.captured_ms = original_capture_ms;
game_loop_step(&loop, dispatch_ms, &event, &out);
work.stamp = out.stamp; /* retain with task; never regenerate on completion */
/* Later, even if selection changed: */
event.kind = GAME_LOOP_DETECTION;
event.data.detection = work; /* original stamp + real detections/valid/held */
game_loop_step(&loop, delivery_ms, &event, &out);
game_loop_step(&loop, next_ms, NULL, &out); /* no mouse/frame still ticks */
/* Publish out.game as one immutable model/ray/generation/score copy. */
```

`src/game_evdev.h/.c` 是可离线验证的 Linux 输入协议边界，没有 Linux 设备读取胶水。
`game_evdev_decode` 按显式小端布局解码**一条完整字节记录**，不强转 Windows 原始结构体：

| 布局 | 长度 | sec/usec | type/code/value 偏移 |
| --- | --- | --- | --- |
| `GAME_EVDEV_LE32` / 文本 `LE32` | 16 | 各 32 位，偏移 0/4 | 8/10/12 |
| `GAME_EVDEV_LE64` / 文本 `LE64` | 24 | 各 64 位，偏移 0/8 | 16/18/20 |

类型/代码为 16 位，value 为有符号 32 位；接受非负秒和 `[0,1000000)` 微秒。
不以 host 的 `sizeof(timeval)` 或 libc `time_t`/time64 推断设备 ABI。真实 Linux 读取端仍须
核对目标 UAPI 长度/字段偏移、映射系统调用返回值、热插拔和时钟域。下节已离线实现
短读重组和抽象 EOF/EINTR/EAGAIN 处理；Linux 调用及目标原生诊断见下方两节，完整游戏平台验收仍未完成。
原始输入事件的时间字段可解码，但不能据此替换检测采集时间或外部单调 `now_ms`。

`game_evdev_feed` 将 REL_X/REL_Y 归一化为菜单像素（每计数一像素，饱和到画布边界），
保留 BTN_LEFT 边沿顺序，忽略值 2 的按键重复和无关事件；普通事件在 SYN_REPORT 时交付，
同一报告内按下再释放也保留。相邻移动可合并。SYN_DROPPED 或 32 项有界队列溢出时立即
发出断开、丢弃未完成报告并回滚未发布指针，后续事件丢弃到下一个 SYN_REPORT，
然后继续忽略普通事件，直到调用者明确确认状态同步。边界前的恢复请求被忽略。
真实后端须查询/同步设备状态后才恢复；本离线层不执行 ioctl。

继续使用原有 `tools/game_offline.c` / `output/build/game_app/game_offline.exe`，新增文本命令：

```text
pointer NOW_MS X Y
left NOW_MS 0|1
input NOW_MS 0|1
dispatch NOW_MS SEQUENCE CAPTURED_MS
evdev NOW_MS LE32|LE64 HEX_RECORD
```

`left` 的 1/0 为按下/释放，`input` 的 1/0 为恢复/断开；`HEX_RECORD` 是无空格的 32/48 个
十六进制字符。每条原始记录也驱动 tick；未遇同步边界时不会操作菜单。直接 `pointer/left`
不能插入未完成的 evdev 报告。`dispatch` 输出原始代次/序号/采集时间，回放者必须原样保存到
既有 `frame` 命令；入口不会在结果交付时填入当前代次。`select/start/frame/tick/snapshot/quit`
保持兼容；每步输出状态、菜单和同一个已复制的完整游戏快照，使用既有序列化器
`game_app_write_view`，没有第二个应用入口、自动开始或补齐姿态。

聚焦命令仍是上一节的 `test_game_app.ps1`。当前严格 C99 静态检查通过，模拟时间的
原核心 **261**、适配/应用 **519**、输入/调度 **692** 项断言通过。
原有文本 smoke 和 **64 步** stdin 回放通过（菜单 22 步、LE32/LE64 各 21 步，另拒绝截短记录），
覆盖单击、明确开始、未就绪/已解/过期准备禁止开始、切关旧任务、无输入超时、断开恢复和快照一致性。
回放记录为 `output/build/game_app/offline_input.txt`、`offline_evdev_LE32.txt`、`offline_evdev_LE64.txt`。
GCC 首次沙箱启动出现已知 DLL 重定位错误，按规则仅在沙箱外重试一次后成功；未更换环境或安装依赖。
未运行照片全回归、完整工程构建或任何硬件操作。真实 Linux 采集/evdev 设备接入、中文界面、
真实标定、显示集成与板端验证仍待完成，host 测试通过不代表 Linux 运行验证或板端验收。

## 可注入 I/O 的持续运行泵（离线验证）

`src/game_pump.h/.c` 独占一个现有 `GameLoop`，串行处理字节输入、检测完成和 tick，
复用原菜单、计时、评分、运动约束、适配器及光线求解器。`GamePumpIO` 版本 1 注入
`now_ms/connection/read/wait_until`，以及可选的 `resync/result/stopping/publish`。
除有期限的等待外，回调须有界、非阻塞且不可重入；所有采集时间与 now 使用同一单调毫秒时间轴。
`game_pump_event` 可在批次之间同步派发菜单/采集任务；返回的 stamp 必须跟随原任务保存，
完成时不可重新标记当前代次。`game_pump_once` 处理一个批次，`game_pump_run` 持续运行到停止或平台错误。

每批最多 4 次读取（每次 192 字节）和 4 个完成结果，EINTR 也占一次读取预算；
每批开始、I/O 之后和批次结束都采样时间并调用既有 step/tick。无数据/结果时通过
`wait_until` 让出执行，中断不在内部无限重试。唯一新增调参项为 JSON 中的
`board_game.pump_tick_ms=10`，现有生成器生成 `game_default_pump_config`。
等待期限为 `min(now + tick_ms, 本关超时点)`；无鼠标、帧或结果也能准确超时。
读写回调必须遵守预算，单次阻塞超时仍需平台实现保证；host 模拟不能证明实际调度延迟。

`GameEvdevStream` 在既有 evdev 模块内逐字节拼接 16/24 字节记录，再调用原解码器和归一化器。
普通事件只在完整 SYN_REPORT 后进入菜单。AGAIN/EINTR 保留合法残片；EOF、断开、读取错误
清除残片/未同步报告并取消点击，故障保持到连接状态或 epoch 改变。新 fd/设备必须改变
`GamePumpConnection.epoch`，即使调度期间未观察到拔出；新连接不会自动选关、开始或暂停计时。
SYN_DROPPED、队列溢出和坏记录先丢弃到下一 REPORT，再在完整记录边界调用平台 `resync`；
同一次读取中 REPORT 后的残留事件也丢弃，尾部残片须继续收齐并丢弃后才能同步。
`resync=0` 继续等待，`1` 明确确认设备状态同步，`-1` 锁定故障。没有该回调就保持失同步。
恢复后菜单仍要求先释放左键，防止幽灵点击。

检测完成接口返回原始 `GameDetectionFrame`，其数组借用到下一次 result 轮询前；
泵立即同步提交，不暂存数组指针。生产者须保证提交期间数据不可变。
每批只调用一次 publish，传递完整值副本（模型、光线、代次、采集序号/时间、计时和成绩，
以及派生菜单）；发布指针仅在回调内有效，保留须整体复制。真实显示帧边界提交仍待集成。
倒退时钟、等待错误或完成接口失败会返回给调用者，不自动重试。

仍使用唯一 `game_offline` 入口，原协议保留，新增确定性脚本命令：

```text
pump_begin NOW_MS LE32|LE64
pump_bytes HEX_BYTES
pump_io again|interrupt|eof|disconnect|error
pump_link 0|1 EPOCH
pump_resync 0|1
pump_frame NOW_MS GENERATION SEQUENCE CAPTURED_MS VALID HELD COUNT
  （接原有 COUNT 行检测数据）
pump_run UNTIL_MS
```

`pump_begin` 只能执行一次。字节槽最多 192 字节，完成槽拥有自己的检测数组；未消费时拒绝
覆盖。`pump_frame` 原样保存传入 stamp，下一次 run 才提交，不把排队或出队时间当采集时间。
`pump_link`、`pump_resync` 设置模拟平台状态，下一批应用；它们不替代 REPORT 丢弃边界。
`pump_run` 通过模拟等待推进时间，批内 publish 复制完整快照，命令结束输出最后完整快照及
累计 batches/waits、最后一批 result_status。期间没有真实睡眠。泵启用后 select/start/
dispatch/frame/tick 仍通过泵串行执行，pointer/left/input/evdev 原始替代输入不可混用。
例如分片重组一个空的 LE32 REPORT：

```text
pump_begin 0 LE32
pump_bytes 0000000000
pump_run 10
pump_io interrupt
pump_run 20
pump_bytes 0000000000000000000000
pump_run 30
quit
```

验证仍运行 `tools/test_game_app.ps1 -StaticOnly`，再运行 `tools/test_game_app.ps1`。
严格 C99 静态检查及原有 261/519/692 项断言通过；新增运行泵 **271558 项断言**通过，
覆盖两种布局分片/多记录、各读取状态、连接/丢包恢复顺序、空闲精确超时、连续输入及中断
让出计时/结果提交、等待接口、旧任务拒绝、结果数组复用和完整模型/光线/代次/成绩一致性。
文本原 smoke 与 **102 步**回放通过，其中两种布局各 19 步为完整运行泵路径：
字节流选关、原始派发 stamp、检测完成、明确开始、EOF/新 epoch 恢复、无输入 180 秒超时及旧任务拒绝。
产物仅在 `output/build/game_app/`，新增记录 `offline_pump_LE32.txt`、`offline_pump_LE64.txt`。

这些是模拟后端 host 验证。Linux open/read/poll/clock_gettime/ioctl 源码现见下方 `game_linux_io` 一节，
未验证目标 input_event UAPI/armhf ABI、系统调用、真实采集/evdev、真实标定、
显示集成或板端行为；未安装依赖、运行照片全回归、完整工程构建或操作硬件。

## 完整快照驱动的原生 C 离线虚拟界面

`src/game_render.h/.c` 消费同一次发布的 `GameLoopOutput`（完整 `GameSnapshot` 与派生
`GameMenuView`），以及不可变的配置和共享菜单布局，生成 1280×800 纯虚拟 BGR888 画面。
渲染不读摄像头像素，不 tick，不求解光线，不计算成绩，不缓存上次场景或维护另一套状态机。
这是 host 预览、显示接入参考和后续 PL 渲染的视觉基准，不确立全帧 PS 软件绘图为板端稳态架构。

```c
#include "game_render.h"
#include "game_config.h" /* existing generator output */
/* Copy/retain one published pump.view as a whole; never mix menu/game versions. */
VisionCanvas target = {bgr, 1280, 800, stride_bytes, accessible_capacity};
GameRenderStatus status = game_render(&published.view, &game_default_config,
    &game_default_menu_layout, &game_default_render_config, &target);
/* OK or FULL_RAY both produced a complete image. Other statuses wrote nothing. */
```

`VisionCanvas` 由共享 `vision_overlay.h/.c` 提供：容量明确，以 `size_t` 计算行偏移，检查
尺寸、stride、容量乘加溢出和 `PTRDIFF_MAX`；最后一行只要求有效像素跨度。
仅写有效像素，保留 padding。低层画布的 16384 尺寸上限、线刷半径上限是防溢出结构边界。
既有裸机 `vision_overlay` / `vision_overlay_scene` 接口保留，六类模型、ASCII 字库和
安全裁剪原语只有这一份实现。新接口传入的容量必须是实际可访问容量，不能填虚构的大值。

新增可配置视口仅在 `pc_vision/game_config.json` 的 `board_game.render`，由既有生成器
输出 `game_default_render_config`。菜单的三个关卡按钮及开始按钮外观，直接使用输入命中的
同一半开矩形。逻辑场景 `[0,width] × [0,height]` 等比例缩放并居中，独立子画布裁剪模型和线段，
不会侵入菜单。未标定预览有明确中文标签；没有 A3 角点、毫米参数或伪造标定。
中文短标签使用 `src/game_font.h` 中自制、可分发的 CC0 16×16 点阵，无系统字体、下载或新依赖。

界面包含准备、运行、通关、超时、发布的剩余时间与星级、鼠标指针、输入断开、无效/过期场景。
时间只格式化快照的 `remaining_ms`（整秒向下显示）；终态使用已冻结的成绩。
不绘制无效/过期几何，不补齐缺失模型。切关清空来自核心的新代次快照。
`render_budget_exceeded` 时 host 绘出全部已发布线段（容量 17），显示“光线超限 / ALL 数量 / 预算”，
返回 `GAME_RENDER_FULL_RAY`；不静默截断、不改变 TARGET 或游戏状态。

唯一 `game_offline` 入口保留全部原协议，新增：

```text
render output/build/game_app/preview.ppm
```

路径为不含空白的单个 token，父目录须已存在。标准 C `game_render_write_ppm` 将带 stride 的
BGR 转为 P6 RGB，检测写入及关闭失败。`render` 不推进时间、不接收排队结果。
普通 loop 模式使用上一次完整 step 的发布；pump 模式只用最近一次 `publish` 回调的值，
因此 `select/start/dispatch/pump_frame` 之后需显式 `pump_run NOW_MS` 才会更新导出画面。
导出前后原有 `snapshot` 文本仍可用于状态检查；文本诊断可比实际发布更新。

验证命令仍为 `tools/test_game_app.ps1 -StaticOnly` 和 `tools/test_game_app.ps1`。
严格 C99 `-Wall -Wextra -Werror -pedantic` 静态检查先于运行；原核心 261、适配/应用 519、
输入/循环 692、运行泵 271558 项断言继续通过，新渲染测试覆盖容量/溢出、前后保护区与 padding、
极端模型/线段/指针/UTF-8 裁剪、相同输入确定性、输入及游戏不变、完整快照各字段可见性、
半开按钮命中和状态转换。最终 **639725 项断言**通过（含逐字节保护区检查），记录见 `output/build/game_app/game_render_host.txt`。
对共享原语另运行已有 `python color_test/software/vision_ps_baremetal/tests/test_fixed_scene.py`，
其几何/BGR/stride/保护区/裁剪和模拟提交检查通过，产物在既有 `color_test/build/`。

原 smoke 及 102 步文本回放通过；新增完整运行泵回放生成 13 张 PPM，两次文本和图像逐字节一致，
检查未发布事件/排队结果隔离、通关后切关、旧任务拒绝、断开、过期、超时。
输入仍为既有检测姿态 fixtures，没有运行检测器或照片全回归。
`offline_render_input.txt` 可直接重放；`offline_render.txt` 为文本结果，`render_hashes.json`
为图像 SHA256。代表图为 `render_preparing`、`render_running`、`render_cleared`、`render_portals`、
`render_disconnected`、`render_stale`、`render_timeout`；可选已安装 Pillow 自动另存 PNG，
PPM 和测试本身不依赖 Pillow。`render_budget_test.ppm` 是渲染容量边界夹具，重复既有线段以检查
17 段警告，不能当作真实求解结果。所有新产物在 `output/build/game_app/`。

已通过的是离线 host 渲染和模拟时间/I/O 回放。Linux 输入系统调用源码及其离线检查见下一节，
目标 evdev UAPI/armhf ABI 仍未运行验证；真实采集/evdev、A3 标定、显示后端、真实帧边界提交、
1280×800 HDMI 模式与板端验收仍待后续授权任务。离线导图不代表真实 HDMI 显示集成完成。

## Linux 输入与期限等待胶水（源码及离线验证）

`src/game_linux_io.h/.c` 为现有 `GamePumpIO` 提供 Linux `open/read/poll/close`、
`clock_gettime(CLOCK_MONOTONIC)` 和 evdev `ioctl` 实现，没有第二套应用或游戏状态机。
唯一 `game_offline` 文本入口继续保持纯离线，不会因链接此模块而自动访问设备。
`game_linux_system_calls()` 在非 Linux host 返回 NULL；取得 Linux 调用表本身不打开设备。
本轮测试只调用注入的假系统调用，没有访问板卡、实际鼠标、串口或 SSH。

初始化检查**编译头文件所描述的** `input_event` 大小、字段宽度/偏移及小端布局，选择既有
LE32/LE64 解析器，并采样单调时钟。真实后端必须在目标上运行这些检查并验证实际事件，
这段自检源码和 ARM 编译不能替代目标 UAPI/ABI 验收。采集任务须使用同一个单调时钟域保存
原始 capture/generation/sequence，输入事件的 timeval 不用于重标记检测任务。

输入 fd 由此模块独占；必须由上层显式提供设备路径、调用 `game_linux_io_open`。
实际 open 使用只读、NONBLOCK、CLOEXEC，并通过能力查询要求 REL_X、REL_Y 和 BTN_LEFT。
不自动扫描、抓占、发现或重开设备。每次成功 open（即使重用相同 fd 数字）递增 epoch，
避免跨连接拼接旧分片/点击；`game_linux_io_close` 只关闭自己的 input fd，绝不重试 close(EINTR)。

`read` 的短读交给现有 stream 重组；EAGAIN 保留分片，EINTR 消耗一次有界读取预算。
EOF/ENODEV/错误关闭并锁住当前连接，后续 poll 排除该 fd，空闲仍按 deadline 等待，避免忙等。
`poll` 将绝对单调 deadline 转为不超过 INT_MAX 的剩余毫秒；每次 EINTR 返回泵，不内部无限重试。
可选 wake fd 由上层借入，须非阻塞并提供 drain 回调；输入 HUP/ERR 断开，wake fd 故障报错。
未提供 wake fd 时，完成/停止在下一期限 tick 检查；没有自动热插拔发现线程。

SYN_DROPPED 仍先丢弃到完整 SYN_REPORT，只有泵确认记录边界后才执行 EVIOCGKEY。
按键仍按下或查询暂被中断时保持断开，按键为 UP 才允许恢复；不虚构释放/点击，保留原输入层的
重新连接后必须释放策略。结果与发布回调通过 `GameLinuxHooks` 同步转发，检测数组仍按原合同借用。

运行泵新增 `GAME_PUMP_CLOCK_ERROR=UINT64_MAX`，该值为保留值，不能作为有效 now_ms。
系统时钟读取失败、回退或不可表示时锁住失败；泵在 tick/消费本次字节/发布前返回 BAD_CLOCK。
所有 fatal clock/poll/wake 错误均交回上层处理，不能继续重试失败的运行泵。
上层可通过 `GameLinuxIO.error` 获得最近负 errno；它不是自动恢复调度器。

后续原生 Linux owner 的接入顺序为：初始化现有 GameLoop → 初始化 GameLinuxIO（显式 calls/hooks）
→ 显式 open 已确认的输入路径 → `game_linux_pump_io` → `game_pump_init`（使用 io.layout）
→ 原有 pump 调度；退出关闭 input fd，上层关闭自己的 wake fd。真实调用/设备验收属于另行授权任务。

```powershell
# 仍为同一个聚焦测试脚本；host 路径完全使用假系统调用。
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -StaticOnly
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1
# 使用已有 ARM Linux 编译器，只检查源码/头文件并生成一个 .o，不链接/运行应用。
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -LinuxStaticOnly
# 可用 -LinuxCompiler 指定另一个已安装编译器，不安装工具链。
```

严格 host C99 和真实 Linux 分支 ARM C99 检查通过。新测试 **161 项断言通过**，覆盖系统调用
返回值、短读/中断、EOF 后不读旧 fd、同号 fd 重开代次、期限上限、wake drain、恢复查询顺序、
按键保持、完整菜单发布、时钟故障前后隔离。原有核心 261、适配 519、输入 692、运行泵 271558、
渲染 639725 项断言、原 smoke/102 步文本及 13 图两次确定性回放继续通过。
产物仅在 `output/build/game_app/`：`game_linux_io_host.txt`、`game_linux_io.arm.o`；本轮另外检查该
4.8 KB 文件确为 ELF32 little-endian ARM relocatable，记录在 `game_linux_io_arm_check.json`。
没有真实 sleep、依赖安装或完整 Vivado/Linux/SDK 构建。

**边界：**上述是系统调用源码、可注入适配、host 模拟测试与 ARM 头文件/目标文件检查。
现有交叉工具 sysroot 为 glibc 2.36，镜像为 2.27；交叉工具的默认链接仍不作运行时兼容承诺。
镜像原生编译与输入诊断的有限证据见下一节。生产应用接线、热插拔、采集、标定、显示后端、
帧边界提交及完整游戏验收仍待完成，离线图像也仍不是 HDMI 集成。

## 板端原生 C 输入与运行泵诊断

`tests/game_linux_native_probe.c` 是有时限的测试程序，不是第二个生产应用入口。
它链接既有 `game_linux_io → game_evdev → game_pump → game_loop/game_app`，使用实际
open/read/poll/ioctl/CLOCK_MONOTONIC；没有摄像头、假识别结果、PL 加载或显示访问。
仅将初始指针置于共享布局第一关中心 `(240,114)`，选择必须来自真实鼠标按下/释放。
每次发布检查完整快照与应用状态一致；无检测结果时禁止运行、成绩、模型或光线凭空产生。
默认模式要求物理 X/Y、按键、SYN_REPORT、实际选关、合法等待与完整快照检查。
`--clicks-only` 模式要求三组真实按下/释放、至少两次实际选关，不要求移动，成功后立即停止。
选关后还通过既有事件入口验证无有效场景时显式开始被拒绝。

已授权串口任务可使用 `tools/test_game_linux_native.py`。要求 COM9 已登录镜像 shell、
板上已有 Python3/native GCC、电脑已有 pyserial；不安装依赖、不自动发现设备。
先使用既有生成器生成配置，再分阶段运行：

```powershell
python color_test/software/vision_ps_baremetal/tools/generate_game_config.py --output output/build/game_app/game_config.h
python color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py prepare --port COM9
# 操作者准备好后启动；等打印 NATIVE_INTERACTIVE_READY 再原地左键三次。
python color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py run --port COM9 --device /dev/input/event0 --seconds 45 --clicks-only
# 若需验证移动，去掉 --clicks-only，三次点击后再小幅上下左右移动。
python color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py cleanup --port COM9
```

`prepare` 只传输选定 C 模块/头文件、生成配置及两个测试源文件到唯一 `/tmp/codex_game_native_*`；
校验 SHA256、严格 C99 静态检查通过后才链接，再运行 161 项注入调用测试，记录 ELF/动态符号信息。
失败编译自动清理自己的临时目录；成功后由 `cleanup` 清理。所有阶段退出都会释放 COM9。
若 sudo 需要密码，可用 `--sudo-password-stdin` 从受控 stdin 提供已授权凭据；密码不放命令参数、
源文件、manifest 或日志。没有凭据时中止，不猜密码、不修改设备权限；不以启动诊断脚本代替硬件授权。

本镜像 GCC 7.3/glibc 2.27 的严格编译、链接及板上 161 项测试通过。ELF 为 ARM EABI5
hard-float，loader `/lib/ld-linux-armhf.so.3`，最高需要 GLIBC_2.17。旧镜像 UAPI 没有新头文件的
`input_event_sec/usec` 别名，现通过局部字段选择兼容，同时保留尺寸/偏移检查；新 ARM 头文件检查通过。
实际 `input_event` 为 16 字节，type/code/value 偏移 8/10/12、long 为 4 字节。
**原生 C 物理选关验收通过**：本次收到实际就绪标记再提示操作者，第一次 click-only 窗口即成功并提前退出。
三组真实左键按下/释放触发两次第一关选择（首组连接释放保护保留），generation=2，
PREPARING，remaining=180000，模型/光线/成绩/耗时均为 0。共 336 字节/21 条完整记录、
7 次 SYN_REPORT、1820 次完整发布，无记录或快照一致性错误。实际指针 `(239,113)` 在共享按钮内。
没有有效观察场景时，显式开始正确返回 GAME_INVALID_SCENE=8；没有虚构模型或绕过游戏条件。
新模式严格 ARM C99 检查、板上严格编译/链接及 161 项聚焦测试先通过，再进行真实点击。
此前两个未通过窗口的日志保留：零事件、或只有一组点击；其中实际移动 X=383/Y=525，
800 ms 空闲阶段约 3.4 ms CPU。此次成功后未继续重试，板端临时目录已清理，COM9 已释放。
结果和分析见 `output/build/game_app/game_linux_native_result.json`、`game_linux_native_analysis.json`。
初次旧头文件编译失败、成功编译和各次输入窗口的原始日志均保留在该目录。

以上只限定本镜像和本次程序；不证明实际热插拔/SYN_DROPPED 恢复、运行中计时与真实检测联动、
采集/标定、显示、帧边界提交或整机性能。PYNQ Linux 启动及鼠标事件可用，仍不等于真实 HDMI 显示集成。

## 离线预渲染素材最小演示

当前运行主线是 AX7Z020B 上已有 Linux/PYNQ 2.6、原生 C/C++，不是改回裸机。
本目录保留裸机诊断参考；`game_render`、`VisionCanvas` 和显示生命周期是唯一复用入口。
2026-10-19 起显示采用 **电脑制作素材 → SD 普通文件 → PS 常驻缓存/二维合成 →
既有 display VDMA → HDMI**。不建设三维引擎、PL Sprite 引擎或另一套渲染框架。

本次实现为阶段 2 的 **CPU 离线可验证部分**：一次读入背景和两张独立物体图片，
回放坐标/姿态，用常驻背景覆盖旧画面再色键叠加。未连接板卡，未在 SD 实读或显示 HDMI，
未接入真实识别、A3 标定或三关游戏。示例为未标定画布坐标，不是关卡配置。
演示坐标仅用于离线展示；最终鼠标仍只操作菜单，实物由摄像头定位。

### 当前架构审查与取舍

| 问题 | 源码核查与最小决定 |
| --- | --- |
| 1. 是否有非必要实时渲染架构 | 当前规范 BD/游戏 C 源码未见 GPU、三维引擎或 PL 游戏绘图器；`vision_canvas_object` 是现有软件诊断几何绘制，可保留。过度设计主要在旧文档默认推进 PL 光栅化/图元框架，现已取消。`axis_vision_features.sv` 是识别特征实验，不是绘图引擎，且未接入当前 BD。 |
| 2. DMA/VDMA/DDR/HDMI 各做什么 | 当前 BD 的 `axi_vdma_1` 仅 S2MM，把 ISP 视频流写入采集 DDR；`axi_vdma_0` 仅 MM2S，把显示 DDR 读成 24-bit 视频流。DDR 容纳独立采集缓冲、PS 素材/合成和扫描缓冲；`axi_dynclk_0`、VTC、`v_axi4s_vid_out_0`、`rgb2dvi_0` 提供显示时序、流转视频和 TMDS。它们不负责图形生成。未发现需要为 Sprite 新增的通用 AXI DMA。 |
| 3. 所有 HDMI 方案必须处理什么 | 屏幕支持的完整模式/像素时钟、复位、链路背压、像素格式与 stride、有效 DMA 地址、cache 同步、独占访问、提交/旧缓冲复用和退出停机。当前该平台的这些绑定仍待核准；离线素材不能消除它们。 |
| 4. 电脑预制作避免什么 | 避免板端三维投影/模型变换、自由旋转、复杂纹理/Alpha、PNG 解码及逐帧 SD 加载。图像直接转换为 BGR888，角度用有限张图。光路仍在 ARM 计算，显示可用 `vision_canvas_line`。 |
| 5. 保留/复用什么 | `game_render`/`vision_overlay` 的画布、边界检查、PPM 与线段；`game_linux_display` 生命周期；`vision_ps`、`game_scene_adapter`、`game_session`、`ray_game`、菜单/evdev/调度；既有 DDR/VDMA/HDMI 与必要摄像头链路。 |
| 6. 简化/暂缓什么 | 简化为 CPU 背景复制+色键 Sprite；暂缓 PL 图元/纹理/绘图加速、局部 DMA、脏矩形管理、动画框架、非必要驱动及影子特征加速。不删除已有用户实验，不修改采样候选；历史失败继续保留。 |
| 7. 最小改动/最低上板风险 | 在既有 `game_render.c/.h` 增加文件读入及裁剪复制两个函数，扩展既有 `game_linux_static_menu` 为 CPU 素材回放。普通 malloc 素材与 DMA 分开。后续只在核准显示后端后复用既有扫描通路；动态呈现需核准旧缓冲何时可写，或先采用确认停机后再准备的低频更新。 |

外部参考已按实际路径、commit、许可范围及适配限制写入根 `AGENTS.md`。
ALINX `20_sd_hdmi_out/.../bmp_read/main.c` 的 FatFs→DDR→VDMA 流程用于学习；
Linux 复用普通 stdio，无须 FatFs/BSP。其固定 54-byte BMP 假设不作为安全通用解析器。
参考 B 只取 Sprite 背景/位置/可见性/图层思想，参考 C 只取帧缓冲及线段分工思想；
本轮未复制任何外部驱动、RTL、BSP 或素材。已有 C 绘图能完成本演示。

### 文件与内存契约

PC 工具 `tools/prepare_game_assets.py` 输出普通文件，无包管理器或运行时素材框架：

| 文件 | 板端读取方式 |
| --- | --- |
| `background.bgr` | 1280×800、3,072,000 bytes，不透明完整背景 |
| `mirror_000.bgr`、`mirror_090.bgr` | 每张 128×128、49,152 bytes，RGB `FF00FF` 为透明色键 |
| `assets.json`、PNG | PC 检查尺寸/哈希及预览；C 不解析 JSON/PNG |
| `demo.replay` | 每行 `x y pose`，pose 仅 0 或 90；x/y 是物体图片左上角，可负数裁剪 |

`.bgr` 均为自上而下、无头、无行 padding 的 BGR888；必须恰好为声明长度。
短文件、额外字节或读取错误拒绝显示，丢弃已部分读入的素材。读取只写活动像素，
文件关闭错误也传播。PC 可接收自制 PNG/BMP，要求精确尺寸、不拉伸；Sprite 的 Alpha
在电脑以 128 为界转二值掩码，保留的不透明洋红像素报错，板卡不执行 Alpha 混合。

合成目标沿用 1280×800 BGR888、HSIZE=3840、stride=5760、span=4,608,000。
三张常驻素材共 3,170,304 bytes，加一个普通 CPU 合成目标共 **7,778,304 bytes**；
尚不包含后端 DMA 扫描缓冲、系统及采集资源。若后端复制到一个同跨度扫描缓冲，
额外 4,608,000 bytes，不能把 malloc 指针传给 VDMA。
每次全背景恢复活动字节 3,072,000，CPU 至少读+写 6,144,000 bytes，
128×128 Sprite 至多另读+写 98,304 bytes；SD 仅初始化读 3,170,304 bytes。
示例的 PPM/PNG 导出是离线验证 I/O，最终 HDMI 运行不逐帧写这些文件。
显示 VDMA 活动载荷为 `3,072,000 × 实际显示Hz` bytes/s，与合成更新频率分开；
摄像头/DDR/cache 流量另计。不把 60 FPS 作为本演示门槛，未测板端速度。

### 构建、运行和离线验证

从仓库根目录执行（已装 host GCC、Python/Pillow；板端不需要 Pillow）：

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -SpriteOnly
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -DisplayOnly
```

第一个入口严格 C99 编译，运行文件/色键/裁剪/stride/别名检查，生成 PC 示例素材，
用同一 C 进程一次加载三图，依次 `(420,300,0)`、`(650,360,0)`、`(650,360,90)`，
独立 Pillow 合成逐像素比较三帧，同时检查旧位置恢复、坏文件/坏坐标拒绝、原始菜单
`1f497c09` 哈希及 `--display` 拒绝。第二个入口复验原有显示生命周期假平台。
输出只在 `output/build/game_app/`：素材演示的 `sprites/verification.json`、
`replay.log`、`frame_000/001/002.ppm/.png`、`preview.png`；均不是 HDMI 验收。

自制美术导出（不指定三个输入时生成上面的简单演示素材）：

```powershell
python color_test/software/vision_ps_baremetal/tools/prepare_game_assets.py --output output/build/game_app/sprites --background BACKGROUND.png --mirror-000 MIRROR_000.png --mirror-090 MIRROR_090.png
output/build/game_app/game_linux_static_menu.exe --assets output/build/game_app/sprites --replay output/build/game_app/sprites/demo.replay --output output/build/game_app/sprites
```

修改 replay 的坐标/姿态即可；每次进程生命周期内素材只读一次。示例不改唯一游戏
配置 JSON，正式接识别时使用已有快照的类别/映射坐标/方向和有效状态，姿态量化
只选素材，不改变 `ray_game` 实际几何或判定。背景→可见物体→光线→动态 UI 的
顺序仍在同一 CPU 画布完成；本轮未进行阶段 3 的识别接入。

以下为后续获授权后在镜像原生 GCC 的构建方法，**本轮未在板端执行**：

```sh
src=color_test/software/vision_ps_baremetal/src
build=output/build/game_app
mkdir -p "$build"
python3 color_test/software/vision_ps_baremetal/tools/generate_game_config.py --output "$build/game_config.h"
gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic -I"$src" -I"$build" \
  "$src/game_session.c" "$src/ray_game.c" "$build/game_config.c" \
  "$src/game_scene_adapter.c" "$src/game_app.c" "$src/game_input.c" "$src/game_loop.c" \
  "$src/game_render.c" "$src/vision_overlay.c" "$src/game_linux_display.c" \
  color_test/software/vision_ps_baremetal/tools/game_linux_static_menu.c \
  -lm -o "$build/game_linux_static_menu"
```

### 显示接入离线核准更新（2026-10-19）

**后续用户决定：xlnk 标记为“部分完成、非当前阻塞项”，本轮不深挖内核。**
旧实景工程连接本屏可正常工作，继续复用其 rgb2dvi/HDMI 路径；记为用户确认的
既有实屏证据，不自动归给当前82MHz制品或当前Linux绑定。下表为此前审查记录，
其中控制板型号及exact xlnk身份缺口已被同日后续结论取代，不重新索取材料。

本轮完成材料核对，原生绑定仍阻塞；没有修改生产 C/HDL 或新增驱动/回调。
复核报告：`output/build/game_app/display_review_20261019/REVIEW.md`，输入哈希及结果
在同目录 `review.json`；现有 `game_linux_display_qualification.json` 追加独立记录，
历史原生验证批次及全部 gate 值不变。本轮没有编译/软件测试或板端操作。

| 条件 | 本轮结论与最小缺口 |
| --- | --- |
| 制品/素材 | XSA 与包内 BIT/HWH、保存的 EDID、三份 BGR 长度/哈希均一致；同档案配对及离线图像仍不代表同代顶层时序/CDC/实屏通过。 |
| 引脚 | 已上传的 B 底板/核心板原理图已核对 HDMI 正负连线，六项显式 XDC 一致；仍缺实物修订对应和所选 BIT implemented I/O，不补写 N 引脚约束来代替证据。 |
| 屏幕 | 两份 PDF 均在，分别描述 LVDS 成品与 MIPI 裸屏，不能确定当前 HDMI 控制板模式。需控制板/固件型号对应与候选时钟容差，不需重传通用 PDF。 |
| 时钟 | 100 MHz 参考下，现有整数接口对 82.170 MHz 最近为 82.000 MHz（约 -0.207%），非精确解；未擅设容差，approved mode/dividers/VTC 仍为空。没有据此宣称小数分频硬件不可行。 |
| DMA/退出 | 最新四项卡文件哈希和内核 SDK 已存在，但不证明 exact xlnk 及可观察 alloc/sync/free/rollback、异常退出安全；既有 libcma 继续不合格，不切换到未验收的 zocl 支线。 |

最小接入仍是把既有 `game_render_blit` 合成的 VisionCanvas 交给
`game_display_prepare` 的逐行复制，保持一帧不可变扫描；现有接口足够，暂不新增
占位中间层。真实平台 acquire/分配/同步/时钟/退出证据齐备前，`--display` 保持
返回 3；移动/姿态还须另证停机更新或安全换帧，不能修改活动扫描缓冲。
既有 PC 设置、UART、板端原生构建及采样停止账本不因本轮核准而重置。

后续同日已获授权的内存诊断补充：实际安装 PYNQ2.6.2 与 xlnk 内核二进制已核对，
单个4 KiB正常调用/strace通过。先前“exact xlnk不明”的身份缺口已解除，但实际
实现的失败回滚、状态、所有权和退出缺口仍使显示后端不合格。`freebuffer()` 后
可能直到数组 GC 才真正释放，不能据其返回释放/复用扫描内存。具体证据及本轮
边界见 `output/build/game_app/pynq_memory_20261019_REVIEW.md`；未启用显示绑定。

### 拆机屏兼容性与纯 PL 彩条优先（2026-10-19 最新决定）

不再将无法确认 HDMI 控制板型号或缺厂家时钟容差文档视为绝对阻塞，已有资料无需
重传。以保存的真实 EDID 声明和实板兼容性测试验收。完整模式表、时序/DRC审查及
最小测试步骤在 `output/build/game_app/hdmi_compat_20261019/REVIEW.md`。

真实EDID明确包含VIC4标准1280×720@60Hz；首测仍选1280×800、82.000MHz，
H=1280/110/40/220，总1650；V=800/5/5/20，总830，+/+，约59.875867Hz。
偏差约-0.207%只作为测试输入；不据此断言兼容性，不先开发小数分频。
720p只能签署备选链路诊断，不能代替原生1280×800游戏显示验收。

先准备显式、可逆的纯PL计数器彩条→现有rgb2dvi路径，绕过Linux/xlnk/VDMA。
当前BD没有该旁路；旧HDMI debug仍依赖VDMA，其program脚本会复位PS，不直接使用。
现存实现按约74.286MHz约束且全顶层时序失败，没有82MHz合格制品。需为诊断确定
无需Linux的参考时钟/启动方式，取得同代routed timing/DRC/clock/pin报告，之后
另获JTAG临时加载与实屏观察授权。保持生产工程/启动卡，诊断不作为生产默认。
本轮未修改生产代码，未构建或上板。后面的Linux步骤仍需独立安全核准，纯PL或
EDID通过不开放真实绑定；xlnk、回调/独占/同步/释放及异常退出门槛保持。

### 实板剩余步骤与停止条件（纯 PL 彩条通过之后）

最新范围允许先连续完成下面的Linux/素材离线准备，不重启已停止的彩条构建或
内核调查；实际显示仍须对选用制品和资源绑定验收。旧实景上屏证据保留。

1. 提前准备板卡电源、UART 和 HDMI 屏幕及现有 SD/Linux；摄像头联调时再接 AN5641，
   鼠标验收时接 USB HOST 有线鼠标。每次板端操作需当前任务明确授权。
2. 核准同代 BIT/HWH/XSA 与必要时序/CDC、屏幕 EDID/完整模式、实际时钟及 Linux
   资源独占。不能把现有“可用 HDMI 链路结构”当成当前制品或原生 1280×800 已通过。
3. 在 SD 的普通应用目录放三张 BGR 素材，保持 BOOT/分区/系统不变；板上原生编译、
   先运行同一 `--assets ... --replay ... --output ...` 验证文件读入。核验 armhf loader、
   glibc 需求及无 libcma 预加载。host/ARM 静态编译不能代替本步。
4. 完成既有 Linux 显示平台绑定的实际分配/缓存同步、时钟/VTC、MM2S HALTED 及
   信号退出策略核准后，才把 CPU 合成画布交给既有显示生命周期。当前 `--display`
   明确返回 3，没有绕过开关；本轮未提供可运行的 HDMI 绑定或缓冲翻转。
5. 先保持一帧不可变扫描 ≥30 秒，检查颜色、边缘、错误与退出；再按确认的缓冲切换
   或停机更新策略实屏验证移动/姿态，不能边扫边改。实测不满足演示再审查局部优化。

本轮素材功能 **不需要修改 PL**。原生 1280×800 是否能只调现有硬件配置仍 UNKNOWN；
摄像头采样时序的历史失败仍需独立解决，不能靠素材绕过。不要为了显示素材添加
新 IP、下载参考工程 BIT、重建内核或改启动卡。

### 常驻素材到静态扫描缓冲的离线衔接（2026-10-19）

复用已有 `tests/test_game_linux_display.c` 的唯一假平台，将已保存三份素材经
`game_render_read_bgr` / `game_render_blit` 交给真实 `game_display_prepare/start/stop`。
不新建渲染器或平台模拟器，不改变后端运行行为；`game_linux_display.c` 仅更新
注释以区分“xlnk身份已建立”和“最终绑定未启用”。

```powershell
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -DisplayOnly -DisplayAssets output/build/game_app/sprites
```

`-DisplayAssets` 为可选项，读取现存素材，不生成/覆盖美术；从仓库根运行。
检查三个独立静态提交 `(420,300,0)`、`(650,360,0)`、`(650,360,90)`，每次先
确认上一个测试所有者完全释放，再启动下一次；不是已实现实板连续换帧。
扫描时生成下一张CPU图不得改变已提交副本；强制HALTED超时须保留全部资源，
恢复HALTED后才能逐缓冲释放。导出的是假扫描缓冲完整span，包括padding，
由Pillow独立合成逐像素核对，且检查全部padding为零、原素材哈希不变。

本次严格C99编译、原有1,540,479项显示生命周期检查、新增7,579项衔接检查、
三个逐像素比较、无CMA导入、原菜单哈希`1f497c09`及`--display`返回3均通过；
ARM Linux严格语法检查通过，仅编译检查，没有ARM执行或glibc链接验收。
首次受限环境GCC启动遇DLL重定位错误，同方法普通Windows环境唯一一次重试通过。
证据在 `output/build/game_app/display_asset_submission/REVIEW.md`、
`verification.json`、`submission.log` 和 `scanout_000/001/002.bgr`。

**2026-10-19 的接入记录：** 当时qualify拒绝、10个Linux资源回调未实现：
acquire/close、allocate/release/flush、configure/output/finish、read/write。
已实现的barrier/now_ms/wait_ms和可注入生命周期不能代替这10项。
xlnk不是当前阻塞项；当前工作是把上述既有接口绑定到明确的旧工程显示制品与
Linux时钟/复位/HP/显示MM2S资源所有者。EDID已核对、旧链路能显示或本测试通过
均不自动打开真实平台。后续设备访问、原生运行、时钟/MM2S及退出验证需明确板端授权。

本轮没有连接板卡、加载库/驱动、访问寄存器、启动DMA、修改PL/BOOT/SD/服务，
也没有推进新的渲染架构或摄像头支线；生产采样基线未闭合的事实不变。

本次文件清单（保留工作区此前所有改动，未 commit/push）：

| 类别 | 文件 |
| --- | --- |
| 规则与现状 | 根 `AGENTS.md`、`PROJECT_STATE.md`、`README.md`、本 README |
| 扩展已有实现 | `src/game_render.c/.h`、`tools/game_linux_static_menu.c`、`tools/test_game_app.ps1` |
| 新增 PC 素材工具 | `tools/prepare_game_assets.py` |
| 新增定向验证 | `tests/test_game_sprites.c`、`tests/test_game_sprites.py` |

未改 HDL/XDC、BD、BOOT、系统镜像、检测器/求解器或显示后端；未新增平行实现、
工程副本、源码内素材/生成物或额外目录。素材/图片/日志均在已有 output/build 下。

## Linux 原生静态菜单显示（软件验证阶段）

`src/game_linux_display.h/.c` 提供可注入平台的显示后端，目标固定为 1280×800、
BGR888、1:1，无缩放或裁剪。HSIZE=3840、VSIZE=800、stride=5760，独占扫描
缓冲跨度 4,608,000 字节。模式必须包含有来源的完整时序、实际时钟分频及屏幕范围；
测试中的虚拟时序仅用于假平台，不能作为屏幕参数。当前没有 720p 适配或默认回退。

后端 v2 先验证完整模式及无副作用的平台资格，再进入 acquire（库加载／设备打开／映射）
和分配。初始化失败也逐阶段清理已取得的资源。整张缓冲准备及 cache 同步/屏障完成后
一次提交，三处帧地址相同，VSIZE 最后写入。扫描中不修改缓冲；停机确认 MM2S
HALTED 后，依次关闭输出、恢复本任务配置、单独释放缓冲、关闭平台资源。失败的释放／
关闭保留剩余所有权，重试不会重复释放。`game_display_owner_can_exit()` 仅在资源全部
归还后允许退出；最终调用 `game_display_owner_drain()` 会持续有界停机／等待／重试，
包括等待出错时，不从持有资源的调用路径返回。永久失败会一直保留进程和库。
未来真实所有者仍需先落实信号／退出策略；此循环不能保证 SIGKILL、OOM 或断电后的
内存存活，也不得用 atexit、dlclose、退出进程代替安全停止。

`tools/game_linux_static_menu.c --check` 从现有 game_loop/app 和生成配置取得固定
时刻 0 的完整初始快照，用原有 game_render/vision_overlay/font 渲染一次。它不接
输入、摄像头或计时动画，不自动选关或开始；`--display` 当前返回阻塞状态 3。
`game_display_linux_platform()` 已实现 Linux 单调时钟、nanosleep 和 ARM `dsb sy`，
以及2026-10-20补入的资源取得/撤销和受限MM2S读写代码（详细边界见下节）。
原生preflight仍拒绝，真实设备路径未开放；没有dlopen/libcma分配、时钟/复位/VTC
实现或资格覆盖开关。真实平台绑定尚未完成，不能进行 HDMI 验收。

### 原生 Linux 资源接口进展（2026-10-20）

`game_linux_display.c` 内新增acquire/close/read/write，继续复用现有显示接口。
取得资源按非阻塞独占锁→设备fd→三个4KiB寄存器页执行，部分失败交给同一所有者
逐项撤销；撤销成功才清除句柄，不重复关闭已退役fd，不unlink常驻锁文件。
MM2S读写仅允许当前静态提交所需的寄存器和几何值，拒绝S2MM、状态清错、reset、
非法地址/偏移。RS=0不足以撤销映射；armed保持到读到HALTED且RS=0。
协作锁不等于已排除PYNQ、内核或其他PL所有者，资格检查仍在一切设备操作之前。

```powershell
# 只在本轮明确授权连接后：原生编译及普通临时文件资源测试
python -B color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py display-resources --port COM9
```

此入口复用原有源文件传送/编译流程，单独保存resources会话，不覆盖历史display
session。测试构建直接包含规范display.c一次以验证私有资源辅助函数，不链接第二份；
测试用普通/tmp文件验证真实Linux flocks/mmap/munmap/close，不打开真实设备。
strace保留原始调用，成功后仅清理本次临时bundle；失败目录保留。资源测试不执行
素材回放、EDID、CMA ABI探针或内核调查。现有display-prepare/cleanup入口保留。

本次板上GCC7.3 strict C99编译/链接、2,105项资源检查、无CMA/loader/ioctl导入
检查、`--display`拒绝和glibc≤2.27检查通过；strace无/dev/mem、xlnk、uio、dri、
fb访问，唯一ioctl为stdout终端TCGETS。ARM交叉严格语法检查也通过。
日志、当前启动清单、源码/制品哈希及限制见
`output/build/game_app/display_interfaces_20261020/REVIEW.md` 和manifest。

**仍剩六项：** allocate/release/flush与configure/output/finish继续明确不可用；
qualify不开放。当前新boot的FPGA身份unknown，内核摘要仅FCLK0启用，且PL server
仍有SCU映射；这些不是实际显示PL/时钟/HP或独占运行证明，未盲读PL寄存器。
先对应现有制品与Linux显示资源profile，再实现/核准其余接口和实际显示启停。
xlnk保持“部分完成、非当前阻塞项”；不重复素材、EDID或内核调查。
本轮无PL下载/复位、寄存器访问、DMA、SD/BOOT、驱动或服务改动，COM9已关闭。

以下保留既有用法；2026-10-19 素材任务只重新运行 host `-DisplayOnly`，
没有执行下面的板端 prepare/cleanup，也不把历史板端结果归给当前素材代码。

```powershell
# 仅聚焦 C99 检查、假平台测试、单次 CPU 渲染及未合格入口拒绝检查
./color_test/software/vision_ps_baremetal/tools/test_game_app.ps1 -DisplayOnly

# 仅在获授权且 COM9 已出现 xilinx@pynq:~$ 后执行原生软件编译
python -B color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py display-prepare --port COM9
# 清理成功编译所创建的本任务板端临时目录
python -B color_test/software/vision_ps_baremetal/tools/test_game_linux_native.py display-cleanup --port COM9
```

先前记录的本地严格 C99 检查及 **1,540,479 项假平台检查通过**，单次菜单渲染校验值为
`1f497c09`；覆盖模式/刷新率拒绝、BGR、stride、边界、同步/提交顺序、超时和安全退出。
板端镜像 GCC **7.3.0** 原生严格编译、链接、**1,540,483 项假平台检查**、
单次 CPU 渲染及未合格入口拒绝检查均通过；原生渲染校验值与 host 一致。
菜单 ELF 为 ARM EABI5 hard-float，loader 为 `/lib/ld-linux-armhf.so.3`，最高依赖
GLIBC_2.17（新增单调时钟调用，原先最高为 2.4），兼容镜像 glibc 2.27。
同一日志前段的 GLIBC_2.4 版本表属于 `libcma_abi` 链接探针，后段菜单 ELF 才是
GLIBC_2.17；不能将探针结果填入菜单的资格字段。
原生测试的额外四项仅检查 Linux 时钟／等待／屏障。执行两个 CPU 程序前先检查 ELF，
确认无 libcma 依赖或库加载／设备调用导入；主机也检查菜单的导入表和固定哈希。
已安装 libcma 的头文件及 ABI 链接检查通过；
库依赖 pthread，探针需链接 `-lcma -pthread`。探针只编译/链接，**没有执行或分配 CMA**。
成功日志：`output/build/game_app/game_linux_native_display-prepare_428ba986.log`。
该日志的 `NATIVE_PREP` 与 `game_linux_display_native_session.json` 的目录、完整
bundle SHA256 `f7548935bf55814bca012211de9a5fc07f1d61e00cd1429dd963a53c8891988f`
及 `prepare_log` 对应；日志还记录 `renders=1`、`snapshot_unchanged=1`。
session 的 `cleaned=true` 是该次临时目录已清理的历史记录，本轮未重新连接核验。
COM9 当时已关闭；本地结果保存在 `output/build/game_app/`。
这些结果只证明对应历史 bundle 的软件行为，不自动证明当前源码或硬件合格。
资格 JSON 的逐字段来源见 `software_verification_provenance`；旧 `242832ca` 批次的原
记录保存在 `software_verification_history`，未重新验证，不与新批次混用；原始日志不变。

已安装 libcma 的只读核查结论（完整地址、哈希和日志见 PROJECT_STATE.md）：

- init-array → framework_open → xlnkOpen／context／xlnkCounterMap；后者会打开
  `/dev/mem` 并映射 0xf8f00000。直接链接 `-lcma` 或提前 dlopen 都会早于资格检查
  产生副作用；`--check` 程序不可链接该库。
- fini-array → framework_close → 引用计数归零 → xlnkClose。它遍历库内分配表释放，
  再发送 **0xc0045864** 并关闭 fd。镜像只保留内核 APF Kconfig/Makefile，缺少所查
  驱动源码、目标文件和 vmlinux；运行内核中的含义及跨进程范围仍未证实。下面官方候选
  源码将它分派到空操作，不能将候选行为当作镜像已证实行为。真实卸载继续阻塞。
- 分配失败路径返回 NULL，头文件却标注 -1；mmap 失败路径未见释放已取得的句柄。
  物理查找失败返回 0；缓存／非缓存参数虽传至 sds/xlnk，驱动对齐和映射属性未证实。
  `cma_free` 同样为 void，底层清理未检查 munmap／ioctl 返回值，不能证明释放成功。
- `cma_flush_cache` 忽略虚拟指针，向底层传物理地址／长度，ioctl 失败仅打印，返回
  void。errno 或没有 stderr 输出都不足以证明同步成功。需有已核实驱动的可返回状态
  同步接口或一致性证明；缓存失败和不可观察成功都必须禁止提交。

### libcma/xlnk 官方证据与资格判定

**现有库不能原样满足 v2 显示后端契约，原生 preflight 保持 UNQUALIFIED，资源回调
继续阻塞。** 以下分开记录已匹配的用户态二进制和尚未匹配的内核候选；相同版本字符串、
函数名或 ioctl 编号不构成运行内核对应证明。

- [官方 v2.6.0 发布说明][pynq26-release] 将镜像关联到 PetaLinux 2020.1。
  官方 tag 对应 PYNQ 提交 `86c52c29f1de2df8812ca11f0ecbd694473b15ac`。
  其 [libcma.so.32][pynq26-lib] Git blob 为
  `9ce6ae2901f1f2faa7331cf58c3edc6e806e8643`，57,048 字节；前次官方审计
  （2026-10-17）在主机内存中解码官方 GitHub blob 并计算 SHA256，得到
  `126301f9575d119f3b12e41bc2ce26df79a0fdae210169da3bf4b6548dd1fdd3`，
  与既有 `game_linux_native_display_cma_safety_ef492a8c.log` 的已安装库哈希完全一致。
  **库二进制对应已建立**，沿用原反汇编结论；当时未执行、加载或落盘该库。
  本轮复用该审计记录，不重新联网获取或核验官方源码。
  [Makefile][pynq26-make] L4-L19 用 `sdscc -static-sds`，默认安装预编译库；
  [pynqlib.c][pynq26-wrapper] L64-L78、L95-L125 仅封装分配／free／cache 接口，
  不提供内嵌 SDS/xlnk runtime 的完整源码。
- 官方内核 tag `xilinx-v2020.1` 解引用到提交
  `043f8a226a752a1dd11f7ff64cee6dbe7334d394`。下表中的驱动路径均为该提交的
  [drivers/staging/apf/xlnk.c][xlnk20]，编号来自同提交的
  [xlnk-ioctl.h][xlnk20-ioctl] L6-L34；按 ARM32 `unsigned long=4` 解码，
  不套用到 64 位 ABI。[PYNQ 内核 bbappend][pynq26-kernel] L1-L8 未列 xlnk 补丁，
  [pynq.cfg][pynq26-config] L199-L200 配置 APF/DMA_APF=y（内建）；缺少 .ko
  本身不能证明驱动不存在。这些仅确立官方候选，未排除镜像定制、BSP 补丁或重建差异。

| 核查项 | 官方候选源码行为及位置（不代表运行内核已匹配） |
| --- | --- |
| 析构请求与跨进程范围 | `0xc0045864 = XLNK_IOCSHUTDOWN`（头文件 L33），分派 L1497-L1498 → `xlnk_shutdown` L1563-L1566，直接返回 0，不释放缓冲、不停止 DMA。另一个请求 `0xc0045865 = XLNK_IOCRECRES`（头文件 L34），分派 L1499-L1500 → `xlnk_recover_resource` L1568-L1575 → `xlnk_free_all_buf` L758-L764，遍历全局池 1..4095，无 fd/PID 过滤，并在 DMA_APF 启用时调用 `xdma_release_all_channels`。它能影响其他进程，不能代替任务局部释放。包装层 `_xlnk_reset`（pynqlib.c L11、L80-L91）使用的是 101，而非析构使用的 100。 |
| 分配与失败清理 | L349-L380：`dma_alloc_attrs`，cacheable 非零传 `DMA_ATTR_NON_CONSISTENT`，否则 attrs=0；先分配再找全局槽位，池满返回 -ENOMEM 未释放先前分配。L693-L719：成功后返回 ID/DMA 地址；`copy_to_user` 失败直接返回未复制字节数（可为正），未回滚池项。不能将 ioctl 非负简单等同于分配成功。已安装库另有 mmap 失败未释放句柄的反汇编证据。 |
| mmap 与缓存映射属性 | L1514-L1550：由 offset 的 16 位编码解出 bufid；该编码不等于物理地址 64 KiB 对齐。flag=0 时用 `pgprot_noncached`，非零保留原用户映射页属性，再 `remap_pfn_range`；没有显式 ID 范围、分配长度或 PID 校验。记录用户地址/PID 后，映射失败直接返回 status，不释放缓冲；成功映射也不持有防释放的缓冲引用。不能只据 cacheable 参数推断实际镜像的缓存一致性。 |
| 物理对齐与地址适用性 | xlnk 不额外规定 64 B 对齐。相同提交 [arch/arm/mm/dma-mapping.c][arm-dma20] L686-L777 的 `__dma_alloc` 按 PAGE_ALIGN(size) 取整，CMA 分支 L545-L577 以页和 get_order(size) 请求连续内存，DMA handle 由页 PFN 转换；这是选用该 ARM DMA/CMA 路径时的源码行为。仍需匹配运行配置、DMA ops/地址转换，不能把 DMA 地址无条件视为 VDMA 可用物理地址；保留非零、64 B 对齐、32 位可达及完整 span 无溢出检查。 |
| 缓存同步返回 | `0xc0045818` → L1277-L1327：复制参数失败 -ENOMEM，action 非 0/1 或地址不在池内返回 -EINVAL；ARM32 调用 CPU dcache flush 和 outer flush，action=1 另做 outer invalidate，随后返回 0。未校验 PID/完整长度/溢出；CPU flush 用池基址，未加传入物理子区间偏移。返回 0 表示此处理函数已走完，不证明显示 DMA 停止；已安装 `cma_flush_cache` 将 ioctl 状态丢失，不能用 void 返回包装出成功。 |
| 单缓冲释放返回 | `0xc0045803` → L766-L782 → `xlnk_freebuf` L722-L756：ID 无效或槽位空返回 -ENOMEM，否则先清表再调用 void `dma_free_attrs` 并返回 0。没有 filp/PID、仍存活的 VMA 或 DMA 使用检查，持有全局 ID 可释放其他进程缓冲。该返回也不证明硬件已停止；已安装 `cma_free` 又丢弃 munmap/ioctl 结果，无法支持后端“失败保留所有权并安全重试”的契约。 |
| fd 关闭、退出、异常死亡 | 最终 `xlnk_release` L514-L517 直接返回 0；`xlnk_vma_close` L1558-L1561 仅减计数，没有缓冲回收。该驱动未实现按 fd/PID 的退出清理。正常退出可能由用户态析构遍历库表释放，既无 HALTED 前提也无可靠状态；SIGKILL/OOM 不经过该析构，结合上述回调推断可遗留池项。泄漏不构成安全保留承诺，其他进程的 free/recover 仍可释放它。 |

最小后续方案和资格条件：

2026-10-17 17:22（北京时间），用户授权小屏连接电脑后的只读检测。Windows 活动
HDMI 显示器为 `HHD65B1 / 9032AB54`，由 RTX 4060 Laptop GPU 输出；当时与内屏
复制桌面，外接实际配置为 **1920×1080@60 Hz、148.500 MHz、总长 2200×1125**，
尚未测试原生 1280×800。QueryDisplayConfig 不报告同步极性，不能把 EDID 声明
当成当前发出信号的极性测量。

Windows 驱动接口返回的 256 字节 EDID 与该活动目标的注册表缓存一致，两块校验和
均通过；其 CTA 原生详细时序为 **1280×800@60 Hz、82.170 MHz、H+/V+**：

| 参数 | 水平（像素） | 垂直（行） |
| --- | ---: | ---: |
| 有效区 | 1280 | 800 |
| 前肩 | 110 | 5 |
| 同步宽度 | 40 | 5 |
| 后肩 | 220 | 20 |
| 总长 | 1650 | 830 |

CTA DTD 位于字节 155，标志 0x1e 明确声明数字独立同步和双正极性；基础块同尺寸
DTD 的标志却为 0x00，保留这一内部差异。驱动返回和缓存一致不证明本次读取直接
访问了 HDMI 总线，也不是信号分析仪测量。该机 CIM 方法声明 Boolean 并返回 true，
不能套用文档中的数值状态 0 判定；读取也核对了块长度和校验和。

客服的 `37280042682660_1280x800_Only(1).c` 包含另一份 EDID：83.760 MHz、
H 1280/72/128/200/1680、V 800/3/6/22/831、约 59.9966 Hz，标志 0x04 未提供
可靠的独立 H/V 极性。两份不可混用。建议优先评审实物 CTA 的 82.170 MHz 模式，
再单独安排电脑原生模式验证；本次未切换模式或测试极性组合，未进行 FPGA 操作。
完整原始字节、哈希及当前输出配置保存在资格 JSON 的 `pc_display_observation`；
候选时序独立记录，不直接写入已批准的 FPGA 模式／时钟／VTC 字段或放行门禁。

2026-10-17 17:35—17:38（北京时间），另行授权尝试电脑原生模式，目标身份和路径
不变。先在现有 JSON 的 `pc_native_mode_validation_history` 追加完整初始活动路径、
模式、DEVMODE 和缩放，保留此前 1080p 快照与两份 EDID 来源；系统已有模式列出
1280×800、60 Hz。未激活的独立 DISPLAY5 不提供模式列表，因此先请求扩展桌面，
保留两块屏原目标信号并将小屏置于内屏右侧。沙箱内验证返回拒绝访问（5），仅在
沙箱外重试一次：验证返回 0，但应用返回参数无效（87），尚未进入 1280×800 选择。
复核确认是调用错误：应用及回滚误用 0xC0（VALIDATE|APPLY），既同时置位互斥标志，
也遗漏 USE_SUPPLIED_DISPLAY_CONFIG；正确的供应配置应用组合应为 0xA0。依据
[微软接口说明](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setdisplayconfig)，
不能将这次 87 归因于驱动或屏幕拒绝模式。遵守两次失败后停止规则，本轮未再调用
更正后的组合。回滚调用同样返回 87，不能称为回滚成功；随后读回的活动路径及模式原始字节与
初始快照完全一致，确认没有配置变化留存。小屏仍为复制显示的
**1920×1080@60 Hz、148.500 MHz、总长 2200×1125**；内屏 BOE0C29 仍为
1920×1080、34685000/240864 Hz（约 144.002425 Hz）、346.850 MHz、总长
2080×1158、缩放 100%。停止本分支，不据此判断原生模式不受支持，也不再尝试其他
切换方式、时序或极性组合；后续任务应先更正调用标志，再完成同范围原生模式验证。

以上是驱动读回，未做物理信号测量；实际 H/V 极性仍为**未测量**，不能以 EDID 的
H+/V+ 声明替代。原生画面是否完整、是否裁切／偏移／闪烁，以及稳定约 30 秒后的
实屏照片均待人工确认；本轮未到达原生模式，现有 1080p 画面不能补足该证据。
未编译或重跑软件测试；`qualified_for_loading`、`qualified_for_display` 仍为 false，
所有 FPGA 门禁保持原值，native preflight 仍为 UNQUALIFIED，真实资源回调继续阻塞。
本轮结果不构成 FPGA 原生菜单、逐像素显示或 HDMI 整体验收。

2026-10-17 17:50—17:51（北京时间），另起独立记录执行更正后的电脑侧调用，旧失败
记录、1080p 快照和两份 EDID 来源均保留。以命名常量组合
`USE_SUPPLIED_DISPLAY_CONFIG(0x20) | VALIDATE(0x40) = 0x60`，以及
`USE_SUPPLIED_DISPLAY_CONFIG(0x20) | APPLY(0x80) = 0xA0`；未混用 VALIDATE/APPLY，
未使用 ALLOW_CHANGES、SAVE_TO_DATABASE、自定义时序或通用拓扑切换。重新读取并
保存完整初始路径、模式、当前 DEVMODE、内屏精确刷新率和缩放；目标身份未变，未重读 EDID。
初始配置验证在沙箱内返回 5，同方法仅在沙箱外重试一次后返回 0；这一步不等于回滚成功。

扩展请求保留内屏原源模式、位置及两屏原目标信号，小屏置于 (1920,0)；验证 0x60
与应用 0xA0 均返回 **0**。立即读回为小屏 NVIDIA DISPLAY5、内屏 Intel DISPLAY1，
两个适配器的源编号虽均为 0，仍是独立源。内屏分辨率、目标信号、精确刷新率和位置
保持不变，但适配器／源发生重分配，缩放从 **100% 变为 125%**。按本轮停止条件立即
停止，未枚举扩展后小屏的已有模式，未选择或应用 1280×800，也未继续尝试其他途径。

使用完整初始配置和 **0xA0** 回滚返回 **0**；读回的活动路径／模式原始字节、当前
DEVMODE 和缩放均与初始快照一致，已核对恢复成功，无配置变化留存。小屏最终为复制
显示的 **1920×1080 逐行、60/1 Hz、148.500 MHz、总长 2200×1125**；内屏恢复为
1920×1080、34685000/240864 Hz（约 144.002425 Hz）、缩放 **100%**。
本轮既未达到 1280×800 输出尺寸，也未证实匹配 **1280×800 逐行、60 Hz、82.170 MHz、
总长 1650×830** 的实物 CTA 候选；未到达原生模式阶段，不能据此判定驱动或屏幕拒绝它。
实际 H/V 极性仍为**未测量**，H+/V+ 只来自原有 CTA 标志 0x1e；接口没有提供实际极性。
原生实屏是否完整、有无裁切／偏移／闪烁及稳定约 30 秒后的照片仍待后续原生模式成功后
人工确认，当前 1080p 照片不能代替。当前电脑侧缺口是扩展时保持内屏 100% 缩放，原因
未在本轮继续调查。新证据见资格 JSON 的 `pc_native_mode_validation_history[-1]`；
该 JSON 被 Git 忽略。未编译、重跑软件测试、新增脚本或操作 FPGA；全部 FPGA 门禁原值
不变，`qualified_for_loading=false`、`qualified_for_display=false`，native preflight
仍为 UNQUALIFIED，真实资源回调继续阻塞。未完成 FPGA 菜单、逐像素或 HDMI 整体验收。

2026-10-17 用户补充 PCB 照片并确认：板卡为 ALINX **AX7Z020B**，镜像由 ALINX
官方提供且对应该板卡。照片可读到底板 AX7Z020B、核心板 AC7Z020 标签；这些已列为
已有依据，不再要求重复确认型号或供应方。现有 `hdmi_out.xdc` 的六处显式引脚分配
与 [ALINX 在线手册的 HDMI 引脚表](https://ax7z020b-20231-v101.readthedocs.io/zh-cn/latest/7Z020UserManual_CN/AX7Z020UserManual.html)
一致（U13、W14、Y18、Y16、V18、V17）。该页面正文标注 AX7Z020，仅作为系列级
参考；B 型专用原理图已定位但尚未核读，仍缺 PCB 修订号、所选 BIT 的实际引脚报告及
同代约束依据。镜像由官方提供的用户确认也不等于运行内核与 xlnk 源码／配置的构建对应证明。
照片路径、哈希和核对边界见 PROJECT_STATE.md，资格 JSON 的 `board_evidence` 与
`linux_image_evidence` 分别记录这两类证据；相关资格门禁继续为 false。

逐项门禁见 [PROJECT_STATE.md 的资格缺口表](../../../PROJECT_STATE.md#native-c-static-menu-display-safe-linux-adapter-checkpoint-2026-10-17)：
每项列出当前结论、证据、缺失材料、通过条件、下一工作及授权边界。表中分开记录
内核对应、分配／同步／释放所有权、退出策略、屏幕、同代制品／板卡引脚、STA/CDC、
Linux 时钟／复位／HP 和实时独占；历史 iomem/fd/maps 或时钟快照不证明未来运行时独占。

1. **先补内核对应证据，再讨论绑定。** 最小人工需求是实际启动内核制品及能将其哈希／
   build ID 关联到源码提交、补丁、.config 的构建清单，以及匹配的内建 xlnk.o／vmlinux
   或等价可核验驱动二进制。若无可追溯清单，需对关联到启动制品的驱动代码逐项反汇编
   比对分派、shutdown/recover、alloc/free/cache、mmap/release；仅给同版本源树不够。
   当前只有 UTS 和缺失文件的只读记录，未形成这条对应链，**在此停止，不猜测镜像语义**。
   不再寻找另一份同版本源码；已记录的离线镜像也不能代替实际启动内核的身份链。
2. 即使驱动最终匹配候选，现有 libcma 的 void 同步／释放、失败遗留和进程级析构仍不
   满足契约。后续另立任务评审保留同一驱动的最薄状态接口及必要的现有路径修正；
   单纯包装返回值不能修复驱动池满／copy_to_user 泄漏或补出单缓冲所有权。
   若需改驱动或复用其他已有可证明接口，必须单独确定范围；本轮不实现替代分配器。
3. 后续验证必须证明：所有分配/mmap/回传失败均回滚或显式保留可恢复所有权；
   同步及 munmap/单缓冲释放可观察成功／失败并能安全重试；无全局 recover、无跨进程
   误释放；匹配的映射属性、地址和全 span 同步正确；fd/信号/正常及异常退出策略与
   HALTED 前保留一致。先做静态核查和聚焦故障注入，再另行授权板端验证。
   即使这些通过，屏幕时序、制品/STA/CDC/引脚和 Linux 时钟/复位/HP 门禁仍需满足。

屏幕已有上述两份 EDID 候选；仍需型号／候选适用性确认和 FPGA 可实现性评审，
并补齐同代 BIT/HWH/XSA 的全哈希构建／
导出清单、可追溯的布线后 setup/hold/CDC 验收报告、准确 PCB 修订号与其原理图／实际
引脚对应依据；板卡型号及镜像供应方已有上述用户确认。板卡公开资料由离线评审补充，
工程自身的同代报告应先核查已有构建记录。
现有相关文档／清单未指出这些缺失材料的本地路径；不声称其他位置一定不存在，
也不做目录或磁盘搜索。待人工给出明确材料路径后再离线评审；当前停止各缺料分支。

[pynq26-release]: https://github.com/Xilinx/PYNQ/releases/tag/v2.6.0
[pynq26-lib]: https://github.com/Xilinx/PYNQ/blob/86c52c29f1de2df8812ca11f0ecbd694473b15ac/sdbuild/packages/libsds/libcma/libcma.so.32
[pynq26-make]: https://github.com/Xilinx/PYNQ/blob/86c52c29f1de2df8812ca11f0ecbd694473b15ac/sdbuild/packages/libsds/libcma/Makefile#L4-L19
[pynq26-wrapper]: https://github.com/Xilinx/PYNQ/blob/86c52c29f1de2df8812ca11f0ecbd694473b15ac/sdbuild/packages/libsds/libcma/pynqlib.c#L64-L125
[pynq26-kernel]: https://github.com/Xilinx/PYNQ/blob/86c52c29f1de2df8812ca11f0ecbd694473b15ac/sdbuild/boot/meta-pynq/recipes-kernel/linux/linux-xlnx_%25.bbappend#L1-L8
[pynq26-config]: https://github.com/Xilinx/PYNQ/blob/86c52c29f1de2df8812ca11f0ecbd694473b15ac/sdbuild/boot/meta-pynq/recipes-kernel/linux/linux-xlnx/pynq.cfg#L199-L200
[xlnk20]: https://github.com/Xilinx/linux-xlnx/blob/043f8a226a752a1dd11f7ff64cee6dbe7334d394/drivers/staging/apf/xlnk.c
[xlnk20-ioctl]: https://github.com/Xilinx/linux-xlnx/blob/043f8a226a752a1dd11f7ff64cee6dbe7334d394/drivers/staging/apf/xlnk-ioctl.h#L6-L34
[arm-dma20]: https://github.com/Xilinx/linux-xlnx/blob/043f8a226a752a1dd11f7ff64cee6dbe7334d394/arch/arm/mm/dma-mapping.c#L545-L777

前次证据一致性收口只交叉核对原始日志、session、资格 JSON 和先前官方审计记录；
本次再补充照片／用户来源声明，并只读核对公开板卡资料和现有 HDMI 约束，更新证据
元数据。两次均没有重跑编译或假平台测试，没有使用 COM9，
没有加载或执行 libcma、分配／同步／释放 CMA 或进行任何板端操作。此前 COM9 工具
在传输前确认实际 `xilinx@pynq:~$`，未确认 shell 时不会发送 Ctrl-C。
屏幕候选模式适用性与 FPGA 时钟/VTC 验证、合格同代 BIT/HWH、板卡引脚、STA/CDC、
Linux 时钟／复位及资源独占、
驱动语义和所有者生存策略仍是阻塞。缺少这些条件时不加载位流、分配 CMA 或写显示
硬件。软件通过或临时 720p 显示均不能代替原生 1280×800 现场验收。
`output/build/game_app/game_linux_display_qualification.json` 保存当前同代候选哈希和
显示接口证据；`qualified_for_loading`、`qualified_for_display` 继续为 false，
所有未满足门禁继续为 false，已批准模式及实际 FPGA 原生时钟/VTC 字段仍为 null；
已解出的 EDID 候选参数在独立证据字段中保留。
同档配对为 true 仅表示来源关系；原生 preflight 仍为 UNQUALIFIED，真实资源回调继续阻塞。

## 板端场景性能计时（默认关闭）

现场日志前 78 条为 70.36 s、1.094 Hz，接收间隔中位数 812 ms、最大 1828 ms，
`capture_ms` 差值中位数 883 ms，tx 连续且全部 valid。当前 466 条文件快照为
378.797 s、1.228 Hz，一次 tx 跳号；日志只记录界面采用的场景，不能据此认定 UART 丢包。
完整分析见独立交付目录中的 `existing_log_analysis.json`。8 Hz 是调度目标，电脑端显示
修复不能证明板端达到 8～10 Hz 或约 200 ms 响应。

调用链：`CameraStart -> VisionRunOnce -> CameraCheck -> 下一次 VisionRunOnce`。
每次处理为环检查 -> invalidate -> 非零检查 -> 安全复制 -> 环指针复查 -> 六类检测
-> ScenePublish/scene_stream_poll -> 光线/关卡 -> overlay -> flush -> DisplayChangeFrame
-> poll。CameraObserve 在复制前开启下一帧窗口，采集与 CPU 工作重叠，CameraCheck
可能立即返回；显示驱动内部等待没有新增 UART 服务点，仍保持原显示行为。

保留原 `vision_last_capture_ms/color_ms/processing_ms` 和 probe。协议 capture_ms 是处理
开始时刻；旧 capture 变量是检查/复制包络，color 含发布/发送服务，processing 在
overlay/flush/换帧前结束。新增 `vision_perf.c/.h` 使用同一 XTime 时钟补足缺口。
**计时功能已实现并离线验证，性能根因仍待板端数据确认。**

`VISION_PERF_ENABLE=0` 为默认值，关闭时无新增时钟读取、统计存储或诊断字节。
规范 `perf` 模式开启完整 live 与计时，必须 `VISION_REUSE_BSP=1`，禁止生成平台。
`VISION_PERF_REPORT_MS` 可配置 5000～60000，默认 5000。以下统计均为累计次数 n(u32)、
total/maximum(u64 微秒)，没有逐像素计时或逐帧打印：

| ID（hex） | 阶段 | 测量边界 |
| --- | --- | --- |
| 00 | capture_wait | CameraCheck，包括最多 2 s 等待和健康检查 |
| 01/02/03 | invalidate/pixel_check/copy | 4,147,200 B invalidate、非零检查、2,764,800 B 有效行复制，分别计时 |
| 04 | detect_six | 仅 canonical vision_detect_bgr888，不含发布/光线 |
| 05/06 | ray/overlay | 场景转换与关卡光线；HDMI 光线/状态栏绘制 |
| 07/08 | flush/display_wait | 原 span flush；换帧确认及失败/超时 |
| 09/0a/0b | publish/encode/uart_service | 观测复制、scene 编码、FIFO 服务的 CPU 时间 |
| 0c/0d | poll_gap/queue_age | 相邻 poll 间隔；实际编码的最新观测从排队到编码入口 |
| 0e/0f | fifo_span/wire_idle_upper | 首次写 FIFO 到末字节入 FIFO；首次写到硬件 idle 观测的上界 |
| 10/11 | process/loop | VisionRunOnce（含失败/重试）；一轮处理加 CameraCheck 或恢复分支 |
| 12/13 | recovery/retry | 初始 CameraStart 或运行恢复（含既有 1 s 等待）；重试事件 |
| 14/15 | sleep/report | main 内原 usleep 包络；实际诊断行服务 CPU 时间 |
| 16/17/18 | capture_fail/process_fail/hold | 采集不健康、处理失败、进入保持的次数，total/max 为零 |

process/loop/recovery/sleep 是嵌套包络；poll_gap/queue_age/fifo_span/wire_idle_upper 是
跨度，不能与叶阶段 CPU 时间重复相加。重试前已经执行的复制等仍计入次数。启动统计
包含彩条/曝光等待；稳态用两个完整快照的 `Δtotal/Δn`，累计最大值不能相减得到窗口最大值。
可在排除失败/恢复的窗口内，用 loop 与非重叠叶阶段差值估计环检查、调用和其他剩余开销。

诊断行为固定 61 B：`@PF1 report stage n total maximum\r\n`，字段为固定宽度 hex
8/2/8/16/16 位。每份报告冻结 25 个统计行和 6 个关联行。只保存一个快照和一行，
无动态分配、printf 或历史队列。每次 poll 与 scene **合计最多 64 B**，无 UART 等待。
只在完整 scene 包边界且 FIFO/移位器均空闲时开始诊断行；意外半行必须续完才发下一包。
包边界保留一次诊断机会，防止 scene 常待发时诊断永久饥饿，剩余预算可立即服务 scene。
最短每 5 s 开始一份 1891 B 报告，平均上限约 378 B/s（115200/8N1 的 3.3%）；
服务稀疏时发齐一份可能超过 5 s，不补发积压。额外字节占用服务预算，不能声称零扰动；
report 统计只含实际行服务，其他计时调用开销仍在外层包络中。

PC 同一个接收线程在指定 `--output` 时保存解码后的 `performance.jsonl`，附电脑单调
接收时刻和连接编号。stat 的 total/maximum 单位为 us；关联行字段解释如下：

| ID | n | total | maximum |
| --- | --- | --- | --- |
| f0 | 最新发布 frame | 处理开始 ms（协议 capture_ms） | 发布时刻 us |
| f1 | 当前/最近编码 tx | 首字节写 FIFO 后的软件观测 us | 末字节入 FIFO 后 us，未完成为 0 |
| f2 | 同 f1 的 tx | TXEMPTY=1 且 TACTIVE=0 的观测 us，未观测为 0 | 该包 frame |
| f3 | 含启动包的 FIFO 完成包数 | 最新观测替换次数 | scene FIFO 满次数 |
| f4 | 无法归属线上完成时刻的包数 | scene FIFO 字节数 | 诊断 FIFO 字节数 |
| f5 | 快照 uptime ms | offset 高32位/length 低32位 | 最新发布 frame 高32位/当前 tx 低32位 |

f0 和 f1/f2 可能不是同一帧，必须按 frame/tx 关联。首/末 FIFO 时刻不是物理首/末停止位，
sent 也只表示已入 FIFO。idle 观测可能被 CPU 长段工作推迟，因此 0f 是轮询上界，
不是精确线上发送耗时；若下一包前未观测 idle，增加 f4.n，该包线上时刻记为未知。
不阻塞等待。按实际包长/115200/8N1 算纯线速下限（348 B 为 30.21 ms），与 FIFO 跨度、
poll gap 对照。曝光及最终显示延迟仍须外部测量。诊断无独立 CRC，应按完整报告检查
一致性；scene-v1 的原 CRC 和格式不变。

独立交付：`color_test/build/vision_ps_baremetal/output/perf_live_20261015/`，包含
ELF/MAP、BOOT/BIF、ARM/主机测试日志、matched_inputs.json 和 validation.json。
本轮严格 Cortex-A9/VFPv3 hard-float、`-O2 -g3 -Wall -Wextra -Werror` 编译/链接/size
通过，沿用 linker/spec/libxil/libgcc/libc/libm；text/data/bss=146719/3268/32461072。
ELF 910384 B，SHA256 `b6c1538ccf8edd93103e511434036434de415dbdb63f85035fdf5007b21a22d9`；
BOOT 2262224 B，SHA256 `4f2e8716ff17f731d2e66120dc6ea129bf86475f67ff5cffcc0014b9fc04d906`。
八项输入指纹和三个分区载荷/范围/校验和均通过；原 live 目录 12 个文件哈希不变。
Bootgen 原有 memory-range overlap 警告仍存在，文件分区范围及载荷一致性检查通过。
主机测试为 `tests/test_vision_perf.py`、既有 `tests/test_video_pipeline.py` 和
`python -m unittest pc_vision.test_game -v`（23 项）；实际均由带总超时的调用者执行。
离线重建用全新标签（本轮 XSCT 总超时 240 s，Bootgen 60 s，主机子进程均有超时）：

```powershell
$env:XILINX_VITIS = 'D:/Xilinx/Vitis/2023.1'
$env:VISION_REUSE_BSP = '1'
$env:VISION_BUILD_MODE = 'perf'
$env:VISION_PERF_OUTPUT_TAG = 'perf_take02' # 必须全新，已有 ELF/MAP/BOOT 时拒绝覆盖
$env:VISION_PERF_REPORT_MS = '5000'
$env:VISION_SCENE_STREAM_HZ = '8'
# 调用者需设进程总超时并保留 stdout/stderr 到新目录 arm_build.log。
& "$env:XILINX_VITIS/bin/xsct.bat" color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl
# 成功后再打包；要求该目录存在本次成功的 arm_build.log：
python color_test/software/vision_ps_baremetal/tools/package_live_boot.py --mode perf --output-tag perf_take02
Remove-Item Env:VISION_REUSE_BSP, Env:VISION_BUILD_MODE, Env:VISION_PERF_OUTPUT_TAG, Env:VISION_PERF_REPORT_MS, Env:VISION_SCENE_STREAM_HZ
# 复核已经交付的本轮 BOOT：
python color_test/software/vision_ps_baremetal/tools/package_live_boot.py --mode perf --output-tag perf_live_20261015 --verify-only
```

打包先核对既有 fixed_scene_validation.json 的八项 XSA/BSP/BIT/FSBL/PS-init 指纹，
只用平台 hw/color_test.bit、现有 FSBL 和新 ELF。build/hw/system_wrapper.bit 不匹配，
禁止混用。直接校验三个 BOOT 分区头/校验和、文件范围及各输入载荷逐字节一致。
不运行 Vivado，不生成 BIT/XSA、更新平台、连接串口/JTAG 或写 SD。

人工采集（由用户执行，本任务不操作硬件）：

1. 按 validation 核对输入和 BOOT 哈希，人工保留旧卡内容后使用诊断 BOOT。
2. 人工启动板卡，关闭其他同端口终端，仅运行原接收器：
   `python pc_vision/app.py --game --serial COM9 --baud 115200 --output pc_vision/output/perf_take01`。
   COM9 换为人工确认的端口，目录必须不存在，不另开串口连接。
3. 保持 HDMI、完整六类、安全复制及 RUNNING/未锁定；稳定后固定场景至少 120 s，
   移动/旋转场景至少 120 s，记录段落起止和物体数量，不必主动制造故障。
4. 正常退出，保留 performance.jsonl、scenes.jsonl、metrics.json、BOOT 的 validation/
   哈希和人工操作时间。至少取得三份完整报告（每份 31 行），按连接/重启分组，不跨重启
   求差，丢掉残缺报告；没有诊断时只反馈固件身份、时长和已有文件，不自动连接板卡。
5. 用稳态 `Δn/Δt`、`Δtotal/Δn` 和累计最大值，结合产生帧数、FIFO 完成包数/替换数、
   诊断字节、poll_gap/queue_age/fifo_span 判断主导阶段，之后再做一个最小优化任务。

候选建议须由数据触发：CPU 快而 FIFO/poll_gap 长时，考虑在已有有界阶段边界补 poll，
保留 64 B 预算；detect_six 主导时先内部细分，暂不改阈值/marker；显示等待或 copy/cache
主导时先核对等待和带宽证据，不移除 HDMI、安全复制或改缓冲架构；恢复/重试增长时
单独调查采集可靠性。当前没有板端分阶段数据，不宣布根因或性能提升。

## 摄像头定位＋电脑渲染紧急演示

源码默认 `VISION_SCENE_STREAM_ENABLE=0`，保持原 HDMI 和每秒诊断输出。
规范构建新增 `VISION_BUILD_MODE=live`，一致启用完整摄像头模式：
`VISION_FIXED_SCENE_DEMO=VISION_MINIMAL_TEST=VISION_GREEN_TARGET_ONLY=0`，
`VISION_SCENE_STREAM_ENABLE=1`，默认目标 8 Hz。阈值、marker、`ray_game.c`
和显示驱动未更改；保留当前安全复制和 HDMI 链路。

发送复用 `scene_protocol.c/.h`：一份不可变的发送中包、一份可替换的最新观测。
每次 poll 最多尝试写 64 字节，FIFO 满立即返回；在现有 1 ms 等待中继续服务，
不等待整包发完。发送独立于每秒日志，实时模式关闭 main.c 的详细 UART 日志，
底层启动/错误日志由电脑解析器跳过。没有日志拼接定位或无界发送队列。
检测失败和采集/显示失败发 valid=0；有效空场景发 valid=1/count=0；SOURCE
消失只发送本帧其他对象。没有定时重发旧位置。采集无进展时电脑按接收年龄超时。
frame 是处理观测递增编号，capture_ms 是本次处理开始时的单调毫秒时间。
启动发送现有 scene-v1 无效零帧通知重启，普通 tx 从 1 开始。

ASCII 包长为 `60+48*N` 字节：六物体 348 B，8 Hz 为 2784 B/s，8N1 占
115200 baud 的 24.2%；16 物体 828 B，8 Hz 占 57.5%。调度间隔取目标周期
与实际包长占用 65% 波特率预算所需周期的较大值，不追赶错过的发送时隙。
包的理论线上耗时分别约 30.2/71.9 ms；CPU 单次 poll 不等待这些时间。
`VISION_SCENE_STREAM_HZ` 可通过编译设置 1..30；过高设置会受带宽限制，
并非实测更新率。UART1 保持匹配 FSBL/BSP 的 115200/8N1/无流控。

本轮独立产物在 `color_test/build/vision_ps_baremetal/output/live/`：

- `vision_ps_baremetal.elf`、`.map`、`arm_build.log`：严格 Cortex-A9/VFPv3
  hard-float `-O2 -g3 -Wall -Wextra -Werror` 编译链接通过，size
  text/data/bss=140599/3264/32459536。源码默认开关未改为开启。
- `boot.bif`、`BOOT.bin`、`bootgen.log`、`validation.json`：显式使用匹配平台
  FSBL、BIT 和本轮 live ELF；没有使用旧 `sd_boot/vision/boot.bif`。
  BOOT SHA256 为 `f1200d4c4cc0ae4bb245e9193a1e9fc57c4e75687bf350b22ff4bb4e99bde47b`。
  验证记录覆盖所有输入/源文件哈希、ELF32/EABI5、三个分区头校验和、范围、
  FSBL/应用 PT_LOAD 字节和去 BIT 容器头后的 32-bit 换序配置载荷完全一致。
  Bootgen 有既有的 BIT 内存范围 overlap 警告；BOOT 文件分区范围核对通过。
- `host_game_tests.log`：22 项相关离线测试通过。现有采集/显示故障注入与
  C 光线测试另行通过；没有运行无关完整套件或修复旧六类合成失败。
- `offline_validation.json` 汇总验证范围，`latest_scene_test.log` 核对 10,000
  输入最终显示帧/位置，`ray_game_host.log` 保存原 C 光线结果；
  `simulated_game.png` 是明确标注无板卡的模拟软件预览，已目视检查。

匹配输入沿用 `output/fixed_scene_validation.json`，打包前全部核对：

| 输入 | SHA256 |
| --- | --- |
| `color_test/color_test.xsa`（与平台 hw/export 相同） | `03ae58ac8483359101e5286931effb0d84544f4b9b6c215572ff88653011e0c8` |
| `vision_ps_platform/hw/color_test.bit`（与 XSA 内嵌 BIT 相同） | `a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55` |
| `vision_ps_platform/zynq_fsbl/fsbl.elf` | `c204dd713eb00693a916453700bf024e85019257856f59686956474842ceafc4` |

平台路径基于 `color_test/build/vision_ps_baremetal/`。根 `build/hw/system_wrapper.bit`
不匹配，禁止混入这组输入。BSP 的 xparameters/libxil 和 ps7_init 指纹也在记录中。
未覆盖此前 camera/fixed/未标注 ELF 或任何旧 BOOT。重建入口（无需 Vivado）：

```powershell
$env:XILINX_VITIS = 'D:/Xilinx/Vitis/2023.1'
$env:VISION_REUSE_BSP = '1'
$env:VISION_BUILD_MODE = 'live'
# 可选：$env:VISION_SCENE_STREAM_HZ = '8'
& "$env:XILINX_VITIS/bin/xsct.bat" color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl
# 本轮 BOOT 已存在，先复核。打包脚本默认拒绝覆盖已有 BOOT/BIF。
python color_test/software/vision_ps_baremetal/tools/package_live_boot.py --verify-only
# 仅在独立 live 输出尚无 BOOT/BIF 时首次生成：
# python color_test/software/vision_ps_baremetal/tools/package_live_boot.py
Remove-Item Env:VISION_REUSE_BSP, Env:VISION_BUILD_MODE
```

重编译 ELF 后旧 BOOT 会核对失败，须由人工决定新交付目录/旧产物保留后再打包；
不要只重建 ELF 却沿用旧 BOOT。每次新交付须核对 validation 与实际有效构建参数。

后续人工验收（本轮未执行）：

1. 复核 `validation.json` 和 BOOT SHA256，按既有板卡 SD 启动方式，把此处
   `BOOT.bin` 放到人工确认的启动分区根目录；旧卡内容由人工先保留。
2. 由人工设置 SD 启动、上电，保持 OV5640/HDMI 原连接；确认运行摄像头模式。
3. 人工确认 USB-UART 的 COM 号，关闭同端口终端。电脑运行
   `python pc_vision/app.py --game --serial COM5 --baud 115200`，COM5 替换为实际端口。
4. 每类先只放一个物体：SOURCE＋TARGET，再加入 MIRROR，最后加入 Portal A/B。
   移动/旋转实物，检查固定尺寸模型的中心/有向轴及光路同步变化；移走 SOURCE，
   检查清光；短遮挡、持续遮挡、拔线重连和板端重启分别记录状态与恢复行为。
5. 保持 RUNNING/未锁定，用实际 Hz RX、包间隔和带时间的实物/屏幕记录测量更新与
   端到端响应。目标 8～10 Hz、争取约 200 ms，不能由绘制 FPS 或 RX age 推算达成。

**本轮没有操作板卡、打开真实串口/JTAG、下载、写 SD、复位或运行 Vivado；真实
摄像头跟随、端到端延迟与现场稳定性仍待后续板端验收。**

## 固定场景 HDMI 演示（第二阶段）

在 `src/vision_ps_config.h` 将 `VISION_FIXED_SCENE_DEMO` 改为 `1`，保持
`VISION_MINIMAL_TEST=0` 和 `VISION_GREEN_TARGET_ONLY=0`。也可给所有 C 翻译单元一致添加
`-DVISION_FIXED_SCENE_DEMO=1`；冲突模式会触发 `#error`。恢复为 `0` 即选择原摄像头流程。
下文提供复用匹配 XSA/BSP 的双模式严格构建命令，无需修改源码默认值。
2026-10-14 已生成独立 `output/camera/` 和 `output/fixed/` ELF/MAP；
既有未分模式 ELF 和 BOOT 未替换，不能作为本轮固定场景验收产物。

本模式不初始化摄像头 GPIO/I2C、Gamma、S2MM、D-PHY/CSI，不调用 `CameraStart`、
`CameraCheck` 或检测器。显示沿用既有 MM2S/VTC/动态像素时钟/HDMI；摄像头故障不作为启动条件。
完整游戏区域为 `[0,1279] × [0,719]`，没有预留 UI 区域，上方两行状态文字仅叠加显示。
绘图地址保持 `frame + y*5760 + x*3`，颜色为 DDR BGR888，每行有效 3840 字节。

电脑端未标定 `PlaneMapper` 同样使用 `[0,1279] × [0,719]`。板端使用恒等映射
`(x,y) -> (x,y)`、尺寸比例 1、方向不变；不沿用电脑端 1280×900 窗口的 UI 平移和缩放。
电脑端位置来自照片观测，没有独立固定布局表；本次复用 `pc_vision/game_config.json` 的
标准尺寸和 `game_scene.py`/`game_view.py` 的三角尖端、有限镜面、圆形 TARGET、Portal
实心端到圆环端方向及配色约定，由 `main.c::FixedScenePresent` 提供固定位置。
这些尺寸是逻辑像素碰撞模型，不是毫米标定结果。电脑端桥接的 `physics_scale=100` 是
其数值缩放；板端直接以像素调用原算法，SOURCE 前移 3 像素、求交 epsilon 1 像素。

| 物体 | 中心像素 | 长×宽 | 有向轴 |
| --- | --- | --- | --- |
| SOURCE | (160,540) | 54×40 | (1,0)，向右 |
| MIRROR | (420,540) | 140×12 | (√½,-√½)，-45° |
| WALL | (660,550) | 160×30 | (1,0) |
| TARGET | (1100,300) | 64×64 | 圆形，半径 32 |
| PORTAL_A | (420,300) | 164×56 | (1,0)，实心端向圆环端 |
| PORTAL_B | (860,300) | 164×56 | (0,1)，实心端向圆环端 |

实际 `FixedScenePresent` 和 `ray_game.c` 的 host 执行与手工推导一致：尖端 `(196,540)`
前移至 `(199,540)`，第一段到 MIRROR `(420,540)`；反射后以 1 像素 epsilon 从
`(420,539)` 向上到 A 下侧 `(420,328)`；传送出口表面为 B 右侧 `(888,300)`，
第三段从 `(889,300)` 向右到 TARGET `(1068,300)`。
断言通过：`segment_count=3`、`interaction_count=2`、`success=1`、
`termination=RAY_GAME_TARGET`、命中顺序 `MIRROR -> PORTAL_A -> TARGET`。
方向为 `(1,0)`、`(0,-1)`、`(1,0)`，交点容差 0.02 逻辑像素。
没有提前命中 WALL 或屏幕边界；Portal 间不画连接线。
MIRROR 的白色有限中心线就是碰撞面，长度 140 不再乘识别载体的 0.66；宽度 12
只作模型外观。WALL/Portal 四角及 TARGET 圆半径直接来自同一 `SceneObject`。

调用顺序：`DisplayInitialize -> DisplayStart -> DisplayChangeFrame(1)` 确认彩条帧，
`VideoLayoutMatches(0) -> FixedScenePresent` 构造六个物体并调用 `ray_game_trace` 一次，
`vision_overlay_scene` 一次绘制空闲帧 2 的背景、模型、光线和同坐标边界，
`PresentFrame(2)` flush `5760*720=4,147,200` 字节后由 `DisplayChangeFrame(2)` 等待 MM2S
当前帧指针确认。失败时保留冻结缓冲进入已有诊断保持流程；成功后循环只休眠，VDMA 持续读帧 2。
不新增 framebuffer，不写扫描中的缓冲，原摄像头分支的安全复制、缓存和所有权规则保留。
显示每帧读取有效像素 2,764,800 字节；按 60 Hz 计为 165,888,000 字节/秒，
固定模式稳态无 CPU 整帧写入/复制或采集流量。这是契约计算，尚未实测带宽。

本轮 host 严格编译和既有光线测试通过，实际固定绘制通过 1280×720 BGR888、5760 stride、
每行 padding、缓冲区前后哨兵、四角模型和跨边光线裁剪、非法尺寸/stride 拒绝检查。
无光线遮挡的模型检查确认 MIRROR 有效线段两端、SOURCE 尖端及 Portal 实心端到圆环端方向；
物理与绘图使用同一组实际构造的 `SceneObject`。已目视检查实际缓冲导出的
`color_test/build/vision_ps_baremetal/output/fixed_scene.png`，这是**软件预览，不是 HDMI 截图**。
同目录 `fixed_scene_host.log` 保存实际光路；显示提交采用 host stub，不验证真实缓存/VDMA。

本轮未操作板卡，未运行 Vivado，未重新生成 BIT/XSA/BOOT，未连接串口/JTAG、下载、写 SD 或复位。
HDMI 持续显示和硬件换帧行为仍待验收；不宣称整个工程回归通过。
旧六类合成测试已知失败未运行或修复；未增加实时定位、毫米标定、鼠标、串口或折射功能。

## 目录

- `src/main.c`：摄像头/显示主程序及视觉调用入口。
- `src/green_target_detector.c`、`.h`：纯绿色实心圆/圆环 TARGET-only 检测器。
- `src/vision_ps.c`、`src/vision_ps.h`：整数 HSV、连通域、几何量和 marker 验证。
- `src/vision_stabilizer.c`、`.h`：SOURCE/Portal 两帧确认、短时关联和有向轴低通滤波。
- `src/vision_ps_config.h`：模式开关、全部 HSV 和 marker 阈值。
- `src/ray_game.c`、`.h`：不依赖 framebuffer 的场景转换、最近交点、反射、传送和终止逻辑。
- `src/vision_overlay.c`、`.h`：裁剪并绘制 `RaySegment[]`，固定模式绘制同几何模型，不参与物理计算。
- `tests/test_vision_ps.c`：六类合成目标、带白带 SOURCE 有向轴、错误 Portal marker、WALL 和 overlay 回归测试。
- `tests/test_ray_game.c`：边界、镜面、WALL、TARGET、Portal、最近交点、16 次上限及固定场景光路/绘制检查。
- `tests/test_fixed_scene.py`：抽取实际 `FixedScenePresent`，复用 C 光线测试并导出软件预览。
- `tests/test_source_marker_real.py`：30 张带标记 SOURCE 实拍图的检测和方向回归。
- `tests/test_portal_video_regression.py`：实拍视频逐帧检测/稳定/光线几何回归入口；使用 VS2022 x64 MSVC 严格构建临时 DLL。
- `tests/test_green_target.c`：绿色实心圆、圆环和拒绝场景的主机 C 回归。
- `tests/test_green_target_real.py`：五张实拍图的 Python/C 坐标和 bbox 对比。
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
- TARGET mask：每 4 像素读取一个 BGR 像素，转换为 OpenCV 标度 HSV，以 H=34..70、S>=50、V>=50 建立 320×180 mask，再执行 sampled-grid cross open/close 和 8 邻域连通域筛选。
- 采集缓冲区独占 frame 0；S2MM 单帧完成并停机后，CPU invalidate 并复制至空闲显示缓冲区。
- 显示缓冲区 frame 1/2 交替使用，CPU 分析与标注完成后 flush，再等待 MM2S 当前帧指针确认换帧，才允许复用旧缓冲区。
- 输出：HDMI 先绘制约 6 像素黑色轮廓，再绘制约 4 像素亮黄色光线；Portal 前后是两条不连续线段。左上角状态栏格式为 `R2 RAY <段数> DET <类别> HIT <类别> <耗时> MS`。耗时不含等待换帧时间，不代表完整显示 FPS。若画面中的 Mirror/Portal 对光线无反应，先看 `DET`：缺少 `M/A/B` 属于镜像版本或识别问题；`DET` 存在而 `HIT` 缺少对应字母，才属于碰撞几何问题。
- UART1 115200 波特率，最多每秒打印一次结果。健康检查等待完成帧，2 秒仅是无帧超时，不再每次固定休眠。
- PL 禁用固定蓝/红/橙颜色替换，保留 Gamma 及固定白平衡；HSV 仍需按实际 OV5640 图像标定。

串口示例：

```text
Vision PS v3: pure-green circular TARGET HDMI overlay
VISION detections=1 sample_step=4
TARGET cx=324 cy=275 bbox=296,248,56,56 area=... confidence=99 processing_ms=...
```

## 识别规则

处理顺序是 BGR 转 OpenCV 标度 HSV、独立颜色 mask、4×4 间隔采样、8 邻域连通域、面积过滤、矩和协方差几何量、marker 验证，再对 SOURCE/Portal 做两帧确认、短时关联和方向滤波。Portal 方向为实心圆指向圆环；正反 marker 分数接近时拒绝定向。

- MIRROR：黄色长条为候选，主轴两端必须分别有黑色实心区域。
- PORTAL_A：蓝色胶囊候选，一端为白色实心圆，另一端为白色环且环中心仍为蓝色。
- PORTAL_B：与 PORTAL_A 相同，主体颜色改为橙色。
- 当前 TARGET-only 路径：按面积、帧面积占比、最大长宽比 1.35、bbox 填充率和椭圆覆盖率筛选绿色连通域；实心圆和圆环都可通过，圆环中心空洞不参与外形拒绝。
- SOURCE：保留原橙红主体阈值，但通用橙红连通域不再生成 SOURCE。专用路径必须将相邻橙红连通域与高亮低饱和白带唯一配对，并校验间距、面积比、主轴一致性、填充率和橙红端收尖。单位出射方向为“白带质心指向橙红质心”，出射点使用橙红前端约 30% 的稳健投影。配对或方向有歧义时整帧拒绝 SOURCE；不再使用“窄端即尖端”假设。
- WALL：低饱和、低亮度长条候选；要求足够面积、长宽比和相对周围背景的亮度差，并排除已接受彩色目标的重叠区域。

摄像头模式的 `VisionDetection[]` 经 `ray_game_scene_from_detections()` 转为 `SceneObject[]`，再由 `ray_game_trace()` 产生 `RaySegment[]`；固定模式直接构造 `SceneObject[]`。MIRROR 是有限反射线段；WALL 和 Portal 使用有向 OBB 边界，Portal 仅接受长侧面交点。Portal A/B 保持入口 `u`，按入口/出口有向轴基变换方向，从配对 Portal 的相反侧射出；TARGET 使用模型短边一半为半径的圆形命中区。每次选择当前方向最近交点，交互上限为 16。本阶段未修改这些物理规则。

`confidence` 是规则通过后的固定等级分数，用于区分规则强弱，并非统计概率。当前值为 MIRROR/PORTAL 99、TARGET 96、SOURCE 80、WALL 75。

## 主机测试

仅验证本阶段固定场景和相关光线/overlay，不运行旧六类合成或照片套件：

```powershell
& .\color_test\software\vision_ps_baremetal\tools\test_host.ps1 -FixedSceneOnly
```

需要 Python/Pillow 和 host GCC，严格参数 `-std=c99 -O2 -Wall -Wextra -Werror`。
实际函数临时 include、可执行文件和原始 BGR 缓冲由系统临时目录自动清理，无第二套场景/物理实现。
受限沙箱首次启动 MinGW 返回 WinError 623；相同命令仅在沙箱外重试一次并通过。

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

五张实拍图的 C/Python 对比可单独运行：

```powershell
python .\color_test\software\vision_ps_baremetal\tests\test_green_target_real.py `
  --samples-dir "C:\Users\11967\Pictures\Screenshots"
```

脚本按阶段打印 GCC、编译、链接、Python 检测和 C 探针耗时，并为外部进程设置独立超时。2026-10-04 的五张样本均产生且仅产生一个 TARGET，中心和 bbox 均在配置容差内。

带标记 SOURCE 实拍回归：

```powershell
python .\color_test\software\vision_ps_baremetal\tests\test_source_marker_real.py `
  --samples-dir "C:\Users\11967\Pictures\Screenshots"
```

收紧标记组合后的当前结果为 30 张中 21 张产生有效方向；其中 20 张方向误差不超过脚本当前 38 度门限，1 张小尺寸边缘样本发生错误配对，其余 9 张因裁切/证据不足被拒绝。合成 0/30/60/90/135/-45 度仍通过。当前策略优先拒绝歧义，不能再引用旧的“30/30 全部通过”结论。

视频逐帧回归入口通过 VS2022 x64 `vcvars64.bat` 导出的环境直接调用
`cl.exe /W4 /WX`，并在临时目录清理前释放 DLL。2026-10-06 的 10126 帧
完整回归通过：SOURCE 方向 P95 0.55°、无缺失 marker，988 次 Portal 传送
的最大局部位置误差 0.00 px 且无同侧错误，565 次 MIRROR 命中的最大边界
残差 0.00 px。没有连续 Portal 对满足 <=20 px 静止筛选（`portal_steps=0`），
因此独立的逐帧 180° 翻转指标本次没有有效样本。

## 构建 ELF

本阶段沿用此入口，明确复用已有匹配 BSP，生成两个独立模式：

```powershell
$env:VISION_REUSE_BSP = '1'
$env:VISION_BUILD_MODE = 'both'  # 也可单独选 camera 或 fixed
try {
  & "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\build_vision_ps.tcl
  if ($LASTEXITCODE -ne 0) { throw 'Strict ARM build failed' }
} finally {
  Remove-Item Env:VISION_REUSE_BSP, Env:VISION_BUILD_MODE
}
```

复用路径检查平台 handoff、Cortex-A9/standalone、XSA 与平台 hw/export 副本逐字节一致性，
以及 BSP 头文件/库存在性；不更新平台或生成 BSP。两模式使用原编译器、链接脚本、Xilinx.spec、
`-lxil -lgcc -lc -lm`，严格参数为 Cortex-A9/VFPv3 hard-float 和
`-O2 -g3 -Wall -Wextra -Werror -ffunction-sections -fdata-sections`。
所有 C 翻译单元一致指定 `VISION_FIXED_SCENE_DEMO=0/1`；检查配置中
`VISION_MINIMAL_TEST=VISION_GREEN_TARGET_ONLY=0`，源码默认仍为摄像头模式。
入口已修正 Tcl 错误传播：输入检查、编译、链接或 size 失败返回非零。

2026-10-14 两模式严格编译/链接/ARM size 通过，无源码 warning 或链接错误。
首轮摄像头链接后 size 在沙箱内启动失败（invalid argument）；相同入口仅在沙箱外重试一次，
全部完成。ELF32/EABI5 hard-float 检查通过；固定 ELF 包含 `ray_game_trace`/`vision_overlay_scene`，
不含检测器、CameraStart/CameraCheck、GPIO 初始化或 `captureAux`。

| 模式 | output 下的产物 | ELF 字节 | text / data / bss 字节 |
| --- | --- | ---: | --- |
| 摄像头（0） | `camera/vision_ps_baremetal.elf`、同名 `.map` | 856,524 | 142,479 / 3,264 / 32,457,296 |
| 固定场景（1） | `fixed/vision_ps_baremetal.elf`、同名 `.map` | 562,716 | 89,935 / 2,816 / 18,687,872 |

output 根目录为 `color_test/build/vision_ps_baremetal/output/`，
ELF SHA256 为 `7f2bf17c9bbbd50e474d825f51c430055b02719f5a7bba5525854cf155f2daf5`（camera）、
`e6654a5101b83e5bba73f51e1c98ad477f28762ad1689797d94d1f7ec487bd0c`（fixed）。
同目录 `fixed_scene_validation.json` 记录模式及 ELF/MAP、XSA、BSP、匹配 BIT/FSBL、预览的内容指纹。
未覆盖旧未分模式 ELF/MAP 或 `sd_boot/vision/BOOT.bin`。

后续另行授权的板端验收使用以下组合与步骤：

1. 使用 `color_test/color_test.xsa`（SHA256 `03ae58ac8483359101e5286931effb0d84544f4b9b6c215572ff88653011e0c8`）、
   已有 `vision_ps_platform/ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0` 和本节选定模式 ELF。
2. 使用 `color_test/build/vision_ps_baremetal/vision_ps_platform/hw/color_test.bit`
   （SHA256 `a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55`，与 XSA 内嵌 BIT 一致）
   及同平台 `hw/ps7_init.tcl`。如选择 SD 启动，使用该平台 `zynq_fsbl/fsbl.elf`
   （SHA256 `c204dd713eb00693a916453700bf024e85019257856f59686956474842ceafc4`），
   后续需为所选 ELF 单独生成并核对 BOOT。本轮没有生成 BOOT。
   当前 `build/hw/system_wrapper.bit`（SHA256 `212715e66e209e3ca6f60c97dcf6504d67d6dec297238b06a71897a38c2b1f32`）
   与本次 XSA 不匹配，不能混用；本轮未替换它。
3. 固定模式检查摄像头不参与启动、1280×720 彩色/stride、三段几何和 TARGET REACHED、
   frame 1 到 frame 2 的实际 MM2S park 确认、缓存一致性与长时间持续 HDMI。
   摄像头模式检查原采集/检测/光线显示。既有下载脚本默认指向未分模式旧 ELF，
   后续必须明确选择本节相应产物，不能直接按默认路径下载。

以下为原有完整平台构建路径，会创建/更新 BSP；本轮未执行该路径：

先安装并配置 Vitis 2023.1，然后在仓库根目录运行：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" .\color_test\software\vision_ps_baremetal\tools\build_vision_ps.tcl
```

未设置上述环境变量时，脚本使用当前 `color_test/color_test.xsa` 创建/更新 standalone BSP，直接编译本目录源码，并打印 ARM ELF 的 size。2026-10-13 旧未分模式严格构建结果为：

```text
text=142479, data=3264, bss=32457296 bytes
```

旧未分模式 ELF 为 856,464 字节，SHA256 为 `453C559EE7EE7050EE0183A854DFBDA05D69DDCC5B69F1C2B23C2178A1A6AFC5`。XSA/PL 接口未变化，因此沿用既有 standalone BSP，以脚本中的相同编译器、链接脚本、库和严格参数完成构建。对应 `sd_boot/vision/BOOT.bin` 为 2,245,840 字节，SHA256 为 `30B532FE6325312CDDE6438040228FB4580FCB5371E9ED2D5D42DFED6C543AE4`，已由 Bootgen 成功生成；当前 `-read` 命令在参数解析阶段失败，因此尚未重新完成分区反读及应用 PT_LOAD 一致性校验。

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

只修改 `src/vision_ps_config.h`，然后重新构建 ELF。HSV 采用 OpenCV 标度：H 为 0..179，S/V 为 0..255；TARGET 初值为 H=34..70、S>=50、V>=50。建议先用同一摄像头的原始帧统计和 PC 原型调整颜色范围，再修改面积、长宽比、填充率和椭圆覆盖率。

如需候选级串口诊断，可在 ARM 编译参数中加入 `-DVISION_TRACE=1`。诊断会增加串口输出量，不建议作为常态版本。

常态版本启动时打印 `Vision firmware build=PORTAL_RAY_R2_20261013`。每秒的 `OBJECT` 行包含 `geom`、`axis_milli` 和 `size`，`RAY_SUMMARY` 包含检测掩码、命中掩码、交互次数和终止原因。只有同时看到该 build ID 与 HDMI 左上角 `R2`，才表示板卡正在运行本节记录的识别镜像。

## v2 帧管理与已知限制

- 当前采用单帧采集后停机，而非全速视频环形采集；PS 复制后即重新启动 S2MM。显示重复最近一张已处理图像，帧率取决于采集、复制、算法及 HDMI 换帧耗时，不承诺 60 fps。
- 全分辨率 mask 已有 3×3 开闭运算，但候选仍为 4×采样连通域；小目标 marker 可能只有少量采样点。
- 嵌入式版没有 PC 端轮廓/孔洞层级；MIRROR/Portal marker 使用主轴端点/中心的局部采样比例，SOURCE 使用独立的橙红/白带连通域配对。
- SOURCE 不强制黑边验证，但只有可信白带配对才能产生有向光线；WALL 仍最依赖现场曝光、灰卡背景和阈值。
- CONF 沿用规则评分，不是概率；没有逐 marker 轮廓绘制。检测为零时仍有状态栏。
- 当前严格主机、完整视频和 Portal 实图回归均已通过；ARM ELF 与对应 BOOT.bin 已离线重建并验证，真实板卡行为仍需在另行授权的任务中验收。
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
当前测试已增加生成代码编译/执行超时和阶段检查点，并把该超大单翻译单元改为 `-O0` 主机编译，同时保留 `-Wall -Wextra -Werror`。但 2026-10-06 的两次外层运行仍分别在 60 秒和 90 秒内未返回，且未返回阶段输出；因此当前不能声称故障注入通过，也尚未排除主循环抽取/集成问题。此前 Portal MVP 的严格 ARM 编译通过，但本轮源码重建受 platform 文件访问错误阻塞。未烧录、未上板验收。

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
| angle | minAreaRect；Portal 有方向 | 协方差主轴；Portal 方向已对齐；SOURCE 由橙红/白带质心确定方向 | APPROXIMATE |
| marker | ROI 轮廓、孔洞、圆度、同心度 | 主轴端点/中心局部比例采样 | PARTIAL |
| SOURCE 标记 | 黑边用于主体恢复 | 橙红主体+白带配对；不依赖黑边 | DIFFERENT |
| WALL 背景条件 | 中位数、填充、silhouette overlap | 中位数、bbox overlap | APPROXIMATE |
| 类别顺序 | 六类固定顺序 | 相同 | EQUIVALENT |
| overlay | PC 调试绘制 | 仅 RaySegment 黑边/黄线和小状态栏 | NOT APPLICABLE |

主机 parity 测试覆盖纯红/绿/蓝、灰/白/黑、Hue wrap、全部阈值上下界 ±1、
六类目标、组合优先级、frame edge、非紧密 stride、bbox/center 容差和 overlay
padding/clipping。PC 使用 200 px² 最小 contour 面积；PS 的 4×4 采样使该边界量化为
12 cells=192 px 与 13 cells=208 px，无法声称 199/200/201 像素逐点等价。

### 参考照片输入入口

`tools/test_game_photos.py --output <输出目录> --assets <现有game_assets.bin>`
仅在本机生成075/076/077的无缩放BGR文件、编译host/ARM入口并做定向检查；不连接板卡。
`--photo-check <照片目录> <素材包> <输出目录>`是纯文件几何核对，输出虚拟画面和原始检测/有效模型/光线；其合成时间不证明运行时新鲜度。
获授权板测包使用`--photos720 <鼠标节点> <素材包> <照片目录> <10至120秒>`，
照片目录须含准确2764800字节的`075.bgr`、`076.bgr`、`077.bgr`，启动时一次读入。
选关后重新运行现有C检测器，经同一适配器/关卡规则/渲染器提交连续显示；照片不作背景，
画面标记FILE INPUT。处理时间使用单调时钟，仍受现有250ms限制；不自动开始或修改通关条件。
该入口的编译期`GAME_PHOTO_DISPLAY_CHECKER`仅选择本次受保护资格文件位置，默认连续菜单资格路径不变。
当前实板验收结论和额度只查仓库`PROJECT_STATE.md`。

### SD卡素材分发

`tools/prepare_game_assets.py --sd-from output/build/game_app/offline_native_20261021/assets --output output/sd_card/ray_game_assets`
从已有完整素材包导出SD目录及同名ZIP，保留`game_assets.bin`字节和几何不变；不覆盖已有分发目录。
目录包含全部姿态PNG预览、独立背景BGR和`check_assets.py`。复制整个目录到SD后，
现有C加载器直接读取`game_assets.bin`；具体复制/路径/纯文件检查方法见包内`使用说明.md`。
