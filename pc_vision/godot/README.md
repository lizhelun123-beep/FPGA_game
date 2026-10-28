# PC 首批美术与 720p 布局

此目录是现有仓库中的 Godot 4 呈现层。菜单、游戏、结算按 1280×720 原生排版，
其他窗口比例等比留边。当前是可点击的美术预览，未连接串口或正式 C 游戏会话。
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

## 后续接入边界

`scripts/art_preview.gd` 提供 `present_scene(snapshot)`、`present_result(result)` 和
`command_requested(action, context)`。正式桥接仍须从现有 NativeGame/C 会话导出权威有效场景，
不能用普通 GameView 调试结果冒充完整计时游戏。

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

本批未接实时输入、未启动板端、未新增检测器或规则。实际截图在 `output/build/pc_art/`，
完整展示代码和素材保存在本目录；输出目录中的参考和结算样例不作为游戏配置。
