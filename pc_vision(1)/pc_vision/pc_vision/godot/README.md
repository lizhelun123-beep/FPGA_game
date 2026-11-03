# PC 首批美术与 720p 布局

## 当前：15格选关与恢复标记串口入口

当前同一个Godot工程已接 `godot_bridge.py`：板端检测及B确认→POSE2串口→原C `game_session/ray_game`→本机TCP→现有美术。Godot只呈现/发操作请求；不处理相机、标签、姿态防抖、计时或求交。Mirror黑端点、Portal白实心点/圆环、WALL白条规则由板端同一 restored detector处理，不运行AprilTag。位置/方向单位为未标定相机像素，虚拟模型为固定配置尺寸。

选关页为5×3共15格，全部显示物体缩略图且可选择。前三关保留旧工程布局和固定光源；4～15关已生成随机物体、朝向及固定光源，保存于唯一JSON，重启不会洗牌，不保证可解。后12关仅是布局草案，不是相机观测或实景通过证据。板端HDMI的(32,500)无关卡测试继续独立运行。此处不宣称HDMI与电脑显示同一局。

需要重新随机后12关时，从仓库根目录运行 `python -m pc_vision.level_layouts --seed 20261028`；前三关保持不变，结果仍只写入 `game_config.json`，之后重启上位机。该操作不改变板端光束配置，本次也无需更换上轮POSE2 BOOT。

在仓库根目录执行（COM5替换为人工确认的板卡端口，关闭占用同端口的终端）：

```powershell
# 主机C编译/检查；不打开UART，不启动Godot或连接板卡
python -m pc_vision.godot_bridge --check
# 用户复制新POSE2 BOOT并启动板卡后，运行上位机
python -m pc_vision.godot_bridge --serial COM9 --baud 115200 --godot .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe
```

需要Python3.10+、pyserial与host C编译器。当前Windows优先使用已安装VS2022 Professional/MSVC（严格/O2 /W4 /WX）；其他环境可用 `--cc` 指定GCC。不依赖PC端OpenCV或AprilTag。不扫描端口，DTR/RTS打开前设为inactive；不执行下载/复位/SD写入。第一次按源码和唯一JSON哈希编译缓存C桥接程序。

也可分别启动：先运行桥接不带 `--godot`；然后Godot追加 `-- --bridge=127.0.0.1:47632`。只监听本机一个客户端；`--port`可指定其他本机端口。断线重连不重复创建串口所有者；Godot关闭时由启动它的桥接退出并释放电脑串口，不停止或复位板端采集。选择关卡→摆放该关所需物体→新鲜完整且未命中时点击“开始计时”→C判定命中/超时→结算→下一关。多余或缺失必需类别会被C拒绝，不截断检测数组。

软件验证：`python -m unittest pc_vision.test_board_bridge -v`；Godot交互接口检查：

```powershell
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --headless --path .\pc_vision\godot --script res://tools/test_live_presenter.gd
```

校时/原始帧标记/250ms游戏准入、短时变暗保留与恢复路线见[当前方案](../FINAL_PLAN.md)。软件样例与截图均不代表真实摄像头或实串口通过。下面CLI美术预览仍可独立使用，不带 `--bridge` 时明确标记为美术预览。

此目录是现有仓库中的 Godot 4 呈现层。菜单、游戏、结算按 1280×720 原生排版，
其他窗口比例等比留边。以下不带 `--bridge` 的模式是独立美术预览，不连接运行会话。
左上/右上预览角标和静态参考标识不得作为运行游戏通过的证据。

## 打开与预览

用 Godot 4 打开 `project.godot`，首次等待素材导入，然后运行主场景。
本轮使用 Godot 4.7.2 官方便携版导入与渲染；不需要 .NET。
仓库根目录也可运行：

```powershell
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --path .\pc_vision\godot
```

菜单中选择关卡、开始和跳过只导航预览界面，并发出带 `art_preview=true` 的信号。
不会操作实物位置、计算计时星级或提交游戏通关。结算页可通过 `--screen=result` 打开。

生成三关静态美术参考（复用唯一配置和现有 C 求解器）：

```powershell
python pc_vision/godot/tools/prepare_art_preview.py
& .\output\tools\godot\Godot_v4.7.2-stable_win64_console.exe --path .\pc_vision\godot -- --screen=game --scene=D:/Workspace/AMD_camera/FPGA-main/FPGA-main/output/build/pc_art/references/level_1.json
```

`--screen=menu|game|result` 选择初始页面；`--result=绝对路径` 读取外部结算展示数据；
`--screenshot=绝对PNG路径` 保存实际 viewport 后退出。`--effect-preview` 只在静态关卡参考中
演示第一个 C 光段终点的单次火花，底栏标明非实时观测。截图需要真实图形渲染器，
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
