# PC 展示界面与 720p 布局

2026-10-30共享电脑运行层更新为 `20261030-pc-responsive-7`：用户允许降低准入门槛后，场景与计分准入从350放宽为600ms；按选中关卡筛选必需物块，仍拒绝缺失/重复/无效/旧会话。网页与Godot共用此JSON/Python/C实现，板端B350ms和校时质量250ms不变。重启电脑后台才能生效；下文旧版本号和350ms约束是历史描述。

当前共享运行层为`20261028-binary-v3-350-6`：电脑场景准入窗口统一为350ms，由唯一JSON同时生成C配置并供Godot/网页使用；两种前端的更新断档提示也读取该窗口。保留二进制v3、READY/START门控及整帧保留，不修改原始时序或独立的250ms校时质量限制。继续使用原version14 BOOT，重启电脑后台生效。

## 当前：v3二进制协议与version14固件

当前电脑build=`20261028-binary-v3-5`，配套BOOT为`color_test/build/beam_standalone/restored_binary_v3_1/output/BOOT.BIN`（version14）。**必须同时更新电脑和BOOT，旧version13固件不识别新协议。** 当前更新包`output/build/game_app/binary_v3_delivery/pc_vision_binary_v3.zip`同时包含Godot与网页入口，二者使用同一个串口所有者/配置/C核心，同时只启动一个入口。

选关、READY、开始、重置、校时及姿态全部采用v3二进制消息，完整帧为`00 FF + COBS(RG/版本/类型/长度/负载/CRC32) + 00`。LEVEL3为43字节，三/五物块姿态为106/130字节；START3之前不发送姿态，READY3仍在新光源画面退休栅栏后返回。按开始收到STARTED3才计时。姿态保留原始相机时序并绑定关卡/PC代次/nonce，保留250ms准入与运行中旧场景整帧显示。协议字段与精度见[串口协议](../SERIAL_PROTOCOL.md)。下方v13/v2文字作为历史说明，不覆盖本节。

用户替换SD卡BOOT并启动板卡后，关闭旧Godot/Python/网页后台及串口助手，从仓库根目录执行：

```powershell
& .\pc_vision\start_game.ps1 -SerialPort COM9
```

仅编译/检查（不打开串口）：`python -m pc_vision.godot_bridge --check`。独立解压后的Godot引擎路径可用`-GodotPath`指定；日志仍保存实际二进制TX/RX十六进制。首次使用v3应确认`BEAM_DIAGNOSTICS version=14`和`BEAM_POSE protocol=3`。本次完成主机/离线/ARM/BOOT校验，尚未做新版硬件串口实测。

## 历史：v2交付与展示说明

2026-10-28 Portal B对齐更新（PC build `20261028-portal-b-aligned-4`）：电脑C会话现在通过唯一JSON的`board_game.portal_b_exit_side=1`复用现有`ray_game_trace_from_emitter_policy`，与当前BOOT的`real_scene.beam.portal_b_exit_side=1`一致。B沿solid→ring轴的正法向`(-axis.y,axis.x)`，从对应长边垂直射出；旧电脑规则会随入口侧/角度改变出口，不能靠旋转模型贴图对齐。关卡2的双侧入口及四个B方向测试通过，持续保留/整帧替换继续生效。只更新PC，继续使用原version13 BOOT。当前更新包：`output/build/game_app/pc_portal_b_aligned_1/pc_vision_portal_b_aligned.zip`。

2026-10-28持续显示更新（PC build `20261028-continuous-scene-3`，兼容原version13 BOOT）：开始计时且已有真实完整场景后，手部遮挡、漏检、过期帧或连接中断均保留该关上一份完整物块/光路，等待下一份通过检查的新场景整帧替换。模型保持正常亮度，旧光路保持原有STALE样式并停止命中特效；切关、回菜单或结束本关后清理。本条覆盖下文针对运行中电脑场景的250ms缺失/6s清空规则。原始序号、采集时间、时钟区间和显示帧龄保留；旧画面不回送C，不参与通关。首次场景仍来自板端真实姿态。新数据/确认到达立即唤醒，定时处理间隔从20ms缩短到最多10ms；STARTED2与POSE2同批到达时先处理确认再检查姿态，250ms游戏有效性不变。无需更换version13 BOOT，更新并重启Python桥接和Godot即可。

## 当前：15格选关与恢复标记串口入口

当前同一个Godot工程已接 `godot_bridge.py`：选关后上位机发送本关光源并等待板端 `READY2`，点击开始后发送 `START2`，板端回应 `STARTED2` 后才接收 `POSE2`，再进入原C `game_session/ray_game` 和本机TCP美术层。Godot只呈现/发操作请求；不处理相机、标签、姿态防抖、计时或求交。Mirror黑端点、Portal白实心点/圆环、WALL白条规则由板端同一 restored detector处理，不运行AprilTag。位置/方向单位为未标定相机像素，虚拟模型为固定配置尺寸。

选关页为5×3共15格，全部显示物体缩略图且可选择。前三关保留旧工程布局和固定光源；4～15关已生成随机物体、朝向及固定光源，保存于唯一JSON，重启不会洗牌，不保证可解。后12关仅是布局草案，不是相机观测或实景通过证据。板端未接收选关时保留(32,500)测试光源；收到选关后使用电脑传入的发射点和方向。当前同步光源和姿态，HDMI仍是实景诊断光路，电脑C会话独立负责计时/通关；不宣称两端光段和结算已完全一致。

需要重新随机后12关时，从仓库根目录运行 `python -m pc_vision.level_layouts --seed 20261028`；前三关保持不变，结果仍只写入 `game_config.json`，之后重启上位机。下一次选关将发送新的关卡光源。当前配套整合版为version13：`color_test/build/beam_standalone/restored_integrated_1/output/BOOT.BIN`，包含version12 Portal修正和完整握手功能；version10及更旧固件不会确认LEVEL2，开始按钮将保持禁用。

关卡握手为 `LEVEL2 → READY2 → START2 → STARTED2 → POSE2`，`SYNC2`独立周期校时。已排队的关卡、开始或重置命令优先于下一次校时；正在等待的校时最多占用1500ms，失败后先发关卡命令，避免重复校时饿死LEVEL2。`LEVEL2`包含关卡、PC会话代次、发射点、单位方向和随机会话nonce；完整命令59字节，CRC32保护，单次只允许一条命令等待回应，避免超过板端64字节接收FIFO。点坐标使用1280×720相机像素，1/1000像素定点编码；方向按1/1000000编码。它们不是毫米或透视标定数据。

板端在帧边界更新同一个GameBeam并清除旧场景/显示历史；新光源完整提交且通过既有HDMI退休栅栏后才发READY2。READY表示光源已应用，不代表本关实物已齐全。电脑核对关卡/代次/nonce和回显光源后才启用“开始计时”。点击后等待STARTED2再启动同一个C计时器；此前板端继续采集/实景显示，但不发送POSE2。准备画面仅显示配置中的固定光源，不用关卡缩略图补齐实物；首个有效新鲜姿态到达后才更新虚拟物块或参与通关。旧C直接开始接口的准备场景要求保持，串口模式使用明确的已握手开始入口。

控制命令从完整写入串口驱动的实际完成时刻起等待2秒，最多发送3次；排队时间不计入超时，重复排队不重置期限，非完整写入不算发送成功。只有CRC、响应类型、代次、nonce及关卡匹配的确认才结束等待，READY2还需核对光源回显。板端重复命令只重发回应，不重置B确认或运行流。切关/菜单取消未发送的旧命令和旧请求重试，菜单发送RESET2关闭姿态流。串口重连会重新确认光源并恢复已开始的姿态流，180秒计时继续。相机原generation/sequence/captured_ms始终保留，PC代次只用于握手与本机C会话。

在仓库根目录执行。2026-10-28本机核对到的USB-UART为COM9（Silicon Labs CP210x），COM5不存在；换电脑或USB设备后先重新枚举。关闭XCOM等串口助手的连接，再由上位机独占串口：

```powershell
# 主机C编译/检查；不打开UART，不启动Godot或连接板卡
python -m pc_vision.godot_bridge --check
# 只枚举系统端口名称/描述，不打开串口，也不编译C
python -m pc_vision.godot_bridge --list-ports
# 用户复制version13 BOOT并启动板卡，确认HDMI采集画面出现后再运行
# 启动脚本自动生成独立串口日志，默认COM9、115200
& .\pc_vision\start_game.ps1 -SerialPort COM9
# 也可直接启动；日志文件名必须尚不存在
python -m pc_vision.godot_bridge --serial COM9 --baud 115200 --godot .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --serial-log .\pc_vision\output\serial\take01.jsonl
```

需要Python3.10+、pyserial与host C编译器。当前Windows优先使用已安装VS2022 Professional/MSVC（严格/O2 /W4 /WX）；其他环境可用 `--cc` 指定GCC。不依赖PC端OpenCV或AprilTag。串口必须用--serial明确指定；--list-ports只读系统设备列表，不探测或打开各端口。DTR/RTS打开前设为inactive；不执行下载/复位/SD写入。第一次按源码和唯一JSON哈希编译缓存C桥接程序。

启动标识为 `build=20261028-portal-b-aligned-4`。`start_game.ps1`将日志保存到`pc_vision/output/serial/uart_*.jsonl`；控制台输出`UART_TRACE`，日志额外保留原始接收字节。`TX_SENT`含完整发送行、十六进制、实际写入时间和尝试次数；`CONTROL_RX`记录READY2等回应及是否匹配；`SYNC_RX`记录往返耗时和时钟区间是否可用。驱动写入成功不等于板卡收到，必须结合真实回应核对；校时失败或过旧仍不能将姿态放入250ms游戏有效窗口。

上位机源码包为`output/build/game_app/pc_portal_b_aligned_1/pc_vision_portal_b_aligned.zip`，包含串口入口、15关配置、美术资源和同一C游戏核心的部署快照；不含Python、Godot和C编译器。独立解压后可用`start_game.ps1 -GodotPath <已安装Godot的完整路径>`指定引擎，入口会先导入资源。包根目录`START_HERE.txt`含本机启动示例。包入口对旧OpenCV检测器按需加载，纯串口游戏启动不加载OpenCV/NumPy。

2026-10-28有界COM9检查共发送LEVEL2三次、SYNC2六次，接收零字节，未发送START2。用户随后确认该轮板卡尚未启动，因此该记录不能判定已通电板卡握手故障，也不算实际往返通过。本轮只生成整合BOOT和更新上位机，没有再次连接板卡。

进入关卡后，摆放物体不会直接解锁开始按钮；必须串口打开、LEVEL2光源更新获READY2确认，才显示“场景已准备，可以开始”。“未找到串口COMx”表示端口选错或设备未枚举；“串口无法打开”时检查串口助手占用或访问权限；“正在连接控制程序”表示Godot尚未连到Python桥接。完整原始串口错误会在Python控制台以BOARD_SERIAL_ERROR输出，界面显示可操作的中文提示。串口打开本身不代替板端READY2，也不会自动开始计时。

也可分别启动：先运行桥接不带 `--godot`；然后Godot追加 `-- --bridge=127.0.0.1:47632`。只监听本机一个客户端；`--port`可指定其他本机端口。断线重连不重复创建串口所有者；Godot关闭时由启动它的桥接退出并释放电脑串口，不停止或复位板端采集。选择关卡→板端更新光源并确认→点击“开始计时”→接收姿态并更新虚拟物块→C判定命中/超时→结算→下一关。多余或缺失必需类别会被C拒绝，不截断检测数组。

软件验证：`python -m unittest pc_vision.test_board_bridge -v`；Godot交互接口检查：

```powershell
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --headless --path .\pc_vision\godot --script res://tools/test_live_presenter.gd
```

校时/原始帧标记/250ms游戏准入、运行中持续保留与恢复路线见[当前方案](../FINAL_PLAN.md)。软件样例与截图均不代表真实摄像头或实串口通过。下面CLI美术预览仍可独立使用，不带 `--bridge` 时不连接运行会话。

此目录是现有仓库中的 Godot 4 呈现层。菜单、游戏、结算按 1280×720 原生排版，
其他窗口比例等比留边。以下不带 `--bridge` 的模式是独立美术预览，不连接运行会话。
2026-10-28 展示文案调整：选关、游戏、结算页面只显示关卡名称、操作提示和挑战状态，不展示布局来源、随机生成、预览角标或C会话等开发说明。静态参考的 `origin/state`、空采集标记和运行准入仍保留；界面截图不能作为实际运行通过的证据。

## 打开与预览

用 Godot 4 打开 `project.godot`，首次等待素材导入，然后运行主场景。
本轮使用 Godot 4.7.2 官方便携版导入与渲染；不需要 .NET。
仓库根目录也可运行：

```powershell
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --path .\pc_vision\godot
```

菜单中选择关卡、开始和跳过只导航预览界面，并发出带 `art_preview=true` 的信号。
不会操作实物位置、计算计时星级或提交游戏通关。结算页可通过 `--screen=result` 打开。

生成各关静态美术参考（复用唯一配置和现有 C 求解器）：

```powershell
python pc_vision/godot/tools/prepare_art_preview.py
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --path .\pc_vision\godot -- --screen=game --scene=D:/Workspace/AMD_camera/FPGA-main/FPGA-main/output/build/pc_art/references/level_1.json
```

`--screen=menu|game|result` 选择初始页面；`--result=绝对路径` 读取外部结算展示数据；
`--screenshot=绝对PNG路径` 保存实际 viewport 后退出。`--effect-preview` 只在静态关卡参考中
演示第一个 C 光段终点的单次火花，静态参考底栏显示“关卡布局”。截图需要真实图形渲染器，
`--headless` 只用于导入/语法检查，不作为视觉验证。

## 素材与锚点

- `assets/background/`：底图 `landscape.png`、透明云层 `clouds.png`、透明前景 `foliage.png`。
  三张原图均为 1672×941，Godot 在背景层映射到 1280×720；物理平面另用单一等比变换。
  PNG 用内置 imagegen 制作，原始提示词保存为同名 `.prompt.txt`。原图未烘焙 UI、模型或光路。
- `assets/models/`：六类透明 SVG，均为原生矢量美术，像素对应现有世界单位，含透明防裁切边。
  SOURCE 粉、MIRROR 金/浅蓝、PORTAL_A 蓝、PORTAL_B 橙、TARGET 绿、WALL 灰褐。
- `assets/ui/`：primary、secondary、card 各 normal/hover/pressed/disabled 四态，
  一张可伸缩面板，以及实心/空心星星。按钮用 `StyleBoxTexture`，面板用 `NinePatchRect`；
  边距分别 30/32 px，文本不烘焙在素材中。

每个模型 SVG 的 viewBox 直接定义绘制矩形与物理原点，不能把含 padding 的整图缩入物理尺寸。
物理尺寸只读取 `../game_config.json`，不维护第二份游戏配置。

| 模型 | SVG viewBox / 物理原点 | +X 零度方向 |
| --- | --- | --- |
| SOURCE | `-24 -26 68 52` | 质心在 0,0；尖端 +36，后端 −18，非图片中心 |
| MIRROR | `-74 -10 148 20` | 反射中心线沿 +X，有限长 140 |
| WALL | `-84 -19 168 38` | 长轴 +X，原有完整 OBB |
| TARGET | `-36 -36 72 72` | 圆形有效直径 64 |
| PORTAL_A/B | `-86 -32 172 64` | 实心端 −X，空心端 +X；长侧面语义不变 |

字体通过 `SystemFont` 使用 Microsoft YaHei、Noto Sans CJK SC 等已安装中文字体；
没有复制或分发 Windows 字体文件。

## 呈现接口与历史预览边界

`scripts/art_preview.gd` 提供 `present_scene(snapshot)`、`present_result(result)` 和
`command_requested(action, context)`。当前串口桥接直接导出原C会话的权威场景，
普通 GameView 仍只是旧调试入口。

场景字段为 `generation/sequence/captured_ms/level_id/state/models/segments`，可附
`remaining_ms`、`display_status`。模型和完整光段同帧替换，尺寸、锚点、光路使用同一等比变换；
STALE/HELD 等状态减弱画面。传入标记与时钟含义原样保留，界面不拿接收时间重写 `captured_ms`；
现有 scene-v1 的 `capture_ms` 是处理开始时刻，并不是曝光时刻。
新鲜度、受限遮挡、关卡代际、计时与星级由原 Python/C 会话判断。

仅 CLI 美术参考允许 `origin=config_reference_art_preview`、`state=ART_PREVIEW` 且原始标记为空。
这些坐标取自现有配置，光路由原 C 求解器生成；它们不是检测结果，不会送入运行游戏。
`result_layout.json` 只演示外部提供的星数和用时，无评分计算。

## 命中火花

`effects/hit_spark.tscn`：16 粒暖金火花、约 0.32 秒、固定随机种子、插值、±180 px 可见矩形；
默认不发射，单次结束自动释放。无粒子碰撞、拖尾或游戏逻辑。

后端可调用 `present_hit(event)`，字段为 `id/generation/sequence/captured_ms/level_id/position/direction`。
`position/direction` 使用与模型和光段相同的世界坐标。仅游戏页的 LIVE/VALID 场景允许装饰事件，
标记必须与当前完整快照一致；重复、旧代际/关卡/帧、时间标记不符、无效坐标或陈旧状态均拒绝。
切换场景或离开游戏页会清除粒子。该接口不判断命中、不产生通关或星级。

原美术批次未接实时输入；当前桥接已实现并通过软件检查，尚未连接真实板卡。实际截图在 `output/build/pc_art/`，
完整展示代码和素材保存在本目录；输出目录中的参考和结算样例不作为游戏配置。
