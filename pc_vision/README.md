# PC 颜色与 marker 视觉原型

独立于 `color_test/` 的 Python + OpenCV 原型。支持图片、USB 摄像头、视频文件。识别 MIRROR、PORTAL_A、PORTAL_B、TARGET、SOURCE、WALL；无神经网络、YOLO、OCR、ArUco 或多边形顶点数分类。

## 板载定位＋电脑实时游戏

板端使用 OV5640 和现有六类 C 检测器，通过 USB-UART 发送 scene-v1 完整场景。
电脑接收坐标与方向，复用下述固定模型、GameController、GameView 和 canonical
`ray_game.c`。串口模式不启动电脑识别进程，不传整帧视频。模型尺寸固定，位置和
有向角度随检测更新；未标定时采用 1280×720 像素坐标，不能解释为毫米。

在仓库根目录安装依赖并启动（COM5 要替换为人工确认的板卡 USB-UART 端口）：

```powershell
python -m pip install -r pc_vision/requirements.txt
python pc_vision/app.py --game --serial COM5 --baud 115200
# 可选：保存已被界面采用的完整场景，目录必须不存在
python pc_vision/app.py --game --serial COM5 --baud 115200 --output pc_vision/output/live_take01
```

需要 Python 3.10+、NumPy、OpenCV、pyserial 和 PATH 中的 host GCC（Windows 可用
MinGW，或 `--cc PATH`）。首次启动严格编译并按内容缓存同一 C 桥接程序。
UART 为 **115200、8N1、无流控**，与提供的实时固件一致；`--baud` 只配置电脑，
不会改变板端波特率。关闭占用同一端口的串口终端；程序只打开明确指定的端口，
不会扫描其他端口。DTR/RTS 在打开前设为 inactive，不主动复位；USB 转接器实际
电气行为需人工确认。本轮测试使用注入的模拟字节流，未打开真实串口。

接收线程独立于绘图，只保留一份最新完整场景；不逐包排队播放旧位置。解析缓冲
有界，处理半包、粘包、普通日志、CRC/格式错误和重新同步。断线立即清除跟随场景，
每 0.5 s 只重试指定端口；每次重连清掉半包和系统旧缓冲，第一份场景重置稳定历史。
普通日志不参与定位。长时间运行时内存中的结果记录最多 256 条；可选 JSONL
逐条落盘，记录的是界面采用的场景，不保证记录所有接收到的包。

性能诊断固件开启计时时，同一个接收线程/同一个串口额外识别固定 61 B 的 `@PF1`
低频诊断。原 `--output 新目录` 同时保存 `performance.jsonl`，无需第二个串口程序；
无 output 时仅累计接收计数，不缓存诊断历史。记录包含 report/stage_id/stage/n/
total/maximum、连接编号及电脑单调接收时刻。stat 单位为微秒；meta_f0～meta_f5
含帧/包/时刻关联，见应用 README 的“板端场景性能计时”。半行不跨重连，诊断不参与
定位、scene 序号、过期判定或绘图；每份 31 行，服务稀疏时可能超过 5 s 才收齐。
诊断无独立 CRC，按连接/重启分组检查完整性及累计计数一致性。

人工示例（本轮未打开真实串口）：
`python pc_vision/app.py --game --serial COM9 --baud 115200 --output pc_vision/output/perf_take01`。
端口由人工确认，关闭其他同端口终端；固定及移动场景各采集至少 120 s，正常退出，
保留 performance/scenes/metrics、诊断 BOOT 的 validation 及人工操作时间记录。
live_monitor01 前 78 条约 1.09 Hz，当前 466 条快照约 1.23 Hz；尚不能解释具体阶段。
电脑不再频闪不代表板端达成 8～10 Hz 或约 200 ms 响应。

界面底部显示 **LIVE / STALE / DISCONNECTED、Hz RX、场景帧号、RX age**。
Hz RX 按最近十秒实际接收的完整场景计算（最多 128 个时间戳），和绘制 FPS 分开；
STALE 不会强制把已测得的低速接收率置零，断线置零。RX age 是距完整包
接收的电脑单调时钟时间，**不等于曝光到屏幕的端到端延迟**。无效场景显示 STALE
并立即清空；有效场景超过 0.25 s 无更新时显示 STALE，保留上一份完整场景及光线。
默认 6 s 无更新才超时清空，
可用 `--scene-timeout` 或 `game_config.json` 的 `timeout_seconds` 修改。
SOURCE 缺失/方向无效立即清除跟随光线；
其他物体短漏检最多保留 0.25 s 并变暗。暂停/锁定会明确冻结显示，现场跟随验收
应保持 RUNNING、解除锁定。断线或超时不会让旧场景以 LIVE 标识继续运行。

scene-v1 的有效数量零表示本帧确实空场景；valid=0 表示识别/采集不可用；均不携带
旧坐标。帧号为板端处理观测计数（允许跳号），capture_ms 为该观测处理开始时间，
并非曝光时间戳。启动先发送 valid=0、frame=tx=capture_ms=0 的 scene-v1 包作为
重启通知，普通发送从 tx=1 开始。帧号、包序号和毫秒时钟按 u32 环绕比较，重复和
乱序不刷新年龄。漏掉启动通知时，须先静默至少 1 s，再观察三份递增的低序号、
低 uptime（<60 s）包，跨至少 0.1 s，才采纳新 epoch；时间前跳也受电脑时间约束。
协议没有唯一 boot ID，无法从字节本身严格区分任意跨重启重放；本实现依赖 UART
有序传输、重连清缓冲和启动通知。异常时可人工关闭并重新运行上述指定端口命令。

离线验证：`python -m unittest pc_vision.test_game -v`，26 项通过，覆盖 C 编码/
Python 解码、非阻塞有界发送、损坏重同步、旧包/重启/重连/超时、连续移动旋转及
光路、SOURCE 消失、10,000 包最新值、照片/视频/回放和原图片入口；新增单一假串口的
半行诊断保存与 scene 同时接收检查，以及低速输入保持画面、明确丢失/无效/断线清除、
低速 Hz 与 STALE 分离。`perf_20261015_230249` 的前 293 条记录约 0.643 Hz，
间隔中位数 1.50 s、最长 5.313 s；旧 0.25 s 清空规则预计使画面约 82.7% 时间无模型。
保存记录经同一 C 光路离线回放，22,209 次模型和 18,762 次光线检查均未因接收间隔
消失，50 次明确 SOURCE 缺失/方向无效仍清除光线。结果保存在该输出目录的
`flicker_analysis.json`，截图 `flicker_stale_replay.png` 明确标为离线回放；当前运行的
Python 进程需正常退出后重新启动才加载修复，尚未进行重启后的实时验收。未修复或运行
旧六类合成已知失败。板端产物与人工 SD 步骤见
[`vision_ps_baremetal/README.md`](../color_test/software/vision_ps_baremetal/README.md)。
**本轮未操作板卡；真实摄像头跟随、8～10 Hz 更新、约 200 ms 响应和现场稳定性均待实测验收。**

## 照片虚拟游戏第一版

按本次调整，第一版只使用参考照片，不连接板卡。新增 `--game` 模式调用
`color_test/software/vision_ps_baremetal/src/vision_ps.c` 和 `ray_game.c`；保持现有
识别规则、六类映射及物理实现。原有 Python 调试模式继续保留，其下文 SOURCE 等
输出语义只适用于原模式；游戏方向来自当前 C 识别器。

在仓库根目录运行（Python 3.10+，安装原 requirements，并让 host GCC 位于 PATH）：

```powershell
python pc_vision/app.py --game --photos sample_photo
python pc_vision/app.py --game --image sample_photo/075.png --output pc_vision/output/my_game
python pc_vision/app.py --game --video path/to/1280x720.mp4 --input-hz 8 --scene-timeout 1 --output pc_vision/output/my_video
python pc_vision/app.py --game --replay pc_vision/output/my_game/scenes.jsonl
python pc_vision/app.py --game --photos sample_photo --start-photo 001.png --headless --save-frames --output pc_vision/output/my_batch
python -m unittest pc_vision.test_game -v
```

`--output` 必须是新目录，不覆盖现有数据。`--cc PATH` 可指定 GCC。
首次运行以 `-std=c99 -O2 -Wall -Wextra -Werror` 编译 `host_bridge.c` 和原 C 源码；
按源文件内容哈希缓存到 `pc_vision/output/native/`。使用独立进程管道，因此本机
32 位 MinGW 和 64 位 Python 可以配合；无需 DLL 位数匹配。无需 ARM 工具链、
Vivado、ELF、BOOT.bin 或固件加载。照片/文件模式不打开串口；实时 UART 输入见上节。
尚未建立板卡实时更新率或稳定性的测量结论。

默认目录模式从 `077.png` 开始，可用 `--start-photo 073.png`。静态照片不是连续视频：
切换时原子替换整张场景、清除稳定历史，并持续显示当前照片；暂停或锁定时仍可
识别下一张，显示保持固定，解锁/恢复采用最新完整场景。照片无 SOURCE 或 SOURCE
方向无效时显示其他模型并清除光线；需要恰好一个有效 SOURCE 才能发射或锁定。
`025.png` 仍因已知 Portal 环歧义被拒绝，未修正旧六类合成识别失败。

鼠标点击游戏上方按钮：

| 按钮 | 作用 | 快捷键 |
| --- | --- | --- |
| Start/Pause | 暂停/恢复；初始为跟随模式 | 空格 |
| Lock | 固定最新有效完整场景和光线；有过期保留物体时拒绝锁定 | L |
| Unlock | 解锁；若仍暂停，恢复后才替换显示 | U |
| Reset | 清空锁定、稳定历史和光线；照片模式重新识别当前照片 | R |
| Calibrate | 打开无缩放原图进行四点标定 | C |
| Previous / Next | 切换照片 | 左右箭头或 P/N |
| Snapshot | 保存当前游戏截图，需 `--output` | S |

Q 退出；Esc 在标定中取消，否则退出。窗口显示输入状态、接收/显示帧号、数据年龄、
跟随/暂停/锁定状态和光线终止原因。识别在后台线程及独立 C 进程进行，刷新和鼠标
事件在主线程进行；物理使用另一个相同 host 程序进程，避免等待识别进程。

### 坐标、平面标定和固定尺寸

游戏严格区分原图像素、平面坐标和显示像素。输入照片/视频必须是无缩放的
1280×720 BGR 图像，禁止套用缩小图片的坐标。没有标定时使用图像坐标预览，界面
明确显示 `UNCALIBRATED PREVIEW`，这些数值没有真实毫米含义。不会根据照片边框
自动推断实际尺寸或缺失角点；例如 `077.png` 上边部分超出画面，不能可靠点击四角。

已知四角和实际矩形宽高时，保存以下配置（数字必须替换为实际测量；这只是格式）：

```json
{
  "schema": "plane-v1",
  "unit": "mm",
  "image_size": [1280, 720],
  "image_points": [[100,100], [1100,120], [1000,650], [200,620]],
  "plane_size": [600,400]
}
```

加载：`python pc_vision/app.py --game --photos sample_photo --calibration path/to/plane.json`。
手工点击：添加 `--plane-size 实际宽mm 实际高mm --calibration-out 新配置路径`，点击
Calibrate，再在参考窗口依次点击左上、右上、右下、左下。必须构成凸四边形；配置
不覆盖旧文件。更换相机位置后需重新标定。原图没有可靠四角时，继续预览或加载
已知标定坐标，不伪造毫米精度。

中心与方向参考线两端均经过透视映射后重新归一化朝向；SOURCE 使用其发射参考点
和方向，Portal 保留实心圆到圆环的有向轴；MIRROR/WALL 为无向轴。标准 SOURCE
三角形以质心为中心，尖端由固定长度和映射方向重新生成，发射点与绘制尖端相同。

`game_config.json` 是默认配置，`--game-config FILE` 可覆盖固定尺寸与稳定参数。
其中新增 `board_game` 是独立 C 三关控制核心的唯一手工配置；当前 PC 照片浏览器仍采用
原行为，不会自动启用三关约束或计时。生成配置、C/C++ 接口及最小离线入口见
[软件 README](../color_test/software/vision_ps_baremetal/README.md#三关游戏控制核心离线)。
现已有标准 C 检测场景适配及外部时间驱动的文本应用入口，见
[适配接口和运行命令](../color_test/software/vision_ps_baremetal/README.md#标准-c-场景适配与离线应用入口)。
它保留原始采集时间/帧序号/派发代次，仅提供未标定恒等映射，不改变本照片浏览器和裸机默认行为。
同一 C 文本入口现支持菜单鼠标事件、显式 evdev 记录解析和单步事件循环，布局仍由此 JSON 生成，
见 [输入与调度](../color_test/software/vision_ps_baremetal/README.md#菜单输入与单步离线事件循环)。
真实 Linux 采集/evdev 设备接入、中文界面、真实标定、显示集成和板端验证仍待完成；
host 通过不代表 Linux 运行验证或板端验收。
`model_sizes` 为 `[长轴长度, 横向宽度]`，TARGET 两值必须相同且代表直径。
未标定时是预览单位，标定后是毫米；默认尺寸是虚拟游戏设计值，不是实物测量，
标定后应按所需虚拟尺寸调整。各帧绝不使用检测 bbox 大小伸缩模型。
显示采用同一份模型顶点等比例缩放。MIRROR 的白色中心线是有限反射面；颜色外框
为装饰。Portal 矩形的长侧面可传送，端面不传送；WALL 为完整 OBB，TARGET 为圆。

物理通过尺度适配复用原 `ray_game.c`，未改其求交代码：默认每平面单位对应 100 个
C ray 单位，求交 epsilon=0.01 平面单位，SOURCE 出射偏移=0.03 平面单位，Portal
出口偏移=0.01 平面单位；画面边界精确为平面宽高。`physics_scale` 可配置，必须
结合最小模型尺寸检查有效精度。固定模型与实物照片的路径可能不同：当前未标定
预览中 `073/074` 直达目标，`075` 反射命中，`076` Portal 后命中，`077` 经 Portal
和 Mirror 后到边界；这不表示更改了原识别/物理引擎的回归结果。

### 视频稳定、场景记录与协议预留

视频/动态场景回放在平面坐标稳定位置和方向。默认位置 EMA=0.45、方向 EMA=0.4，
同类最近邻最大匹配距离=60 平面单位；MIRROR/WALL 消除轴的正负歧义，SOURCE 和
Portal 保留真实有向转动。非 SOURCE 短漏检最多保留 0.25 s，从物体最后实际看到
时间计时，以 `held` 暗色显示且不可锁定；SOURCE 漏检立即清除发射光线。持续无更新
0.25 s 后标为 STALE 并显示上一份完整场景，默认 6 s 后超时清空（可用
`--scene-timeout` 配置）。等待下一帧不会当成漏检；无效完整帧
立即清除跟随场景；锁定和暂停只冻结显示，后台最新场景继续更新和过期。解除锁定
不会恢复超时的旧物体。视频 EOF 继续响应窗口并执行过期处理。

输出 `scenes.jsonl`（完整输入场景和时间、输入名）、`game_results.json`（模型类别和
C 光线路径）、`metrics.json`、生效配置与最终 `game.png`；`--save-frames` 保存每个
场景 PNG。回放不重新识别，无需原照片；四点标定仍需单独加载相同配置。
`--replay-speed` 控制回放速度。图像不进入场景记录；标定用原图窗口。

同一场景编码器/解析器用于离线完整性和 UART 输入；板端发送为可关闭的 opt-in，
源码默认关闭，独立 live 构建开启。仅构建和核对产物，本轮未加载板卡。
格式为 ASCII `@SCN1:<十六进制载荷>:END\r\n`，载荷小端：

| 区域 | 字段及单位 |
| --- | --- |
| 20 字节头 | u8 版本=1、u8 有效标志、u8 数量(0..16)、u8 保留=0；u32 图像帧号、u32 包序号、u32 帧时间ms；u16 图像宽、高px |
| 每物体24字节 | u8 类别、u8 标志、u8 可信度0..100、u8 保留；i16 中心x/y×16；i16 轴x/y×10000；u16 参考长/宽×16；i16 SOURCE尖端x/y×16；i16 SOURCE方向x/y×10000 |
| 类别/标志 | MIRROR=0、PORTAL_A=1、PORTAL_B=2、TARGET=3、SOURCE=4、WALL=5；bit0轴有效、bit1SOURCE方向有效 |
| 完整性 | 载荷末尾 u32 CRC32/IEEE，覆盖头与全部物体，不覆盖CRC本身；长度必须严格匹配数量；无效帧数量为0 |

像素坐标原点左上，x右y下。参考尺寸仅供映射方向参考线，不控制固定虚拟模型大小。
解析器限制缓冲、校验版本/长度/范围/CRC，对半包等待、损坏/日志重同步，连续包分别
提交，断线清除未完成包。未来 UART 必须单独调度包频率和验证启动/重连序号语义。
按工程默认115200、8N1设计核算：包长 `60+48N` 字节，六物体348字节、16物体828
字节，若8 Hz分别占24.2%/57.5%线速，未包含普通日志。这里仅是预算，不是板卡实测。

### 本机验证记录

新增16项测试和原 `test_ray_game.c` focused测试通过；77张参考图成功生成场景与
游戏画面，回放77帧的类别及C光线与照片运行逐项相同。识别平均10.92 ms、最大
32.79 ms；含读图和保存PNG的离线批处理约25.93场景/s。这些是本机离线测量，
不代表板端或串口速率。原六类旧合成测试有已知失败，本任务未运行完整测试套件、
未声称总体通过。实际窗口鼠标体验、实际四点毫米标定、动态视频与板卡实时稳定性
仍需进一步验收；控制器和调度的测试不能代替现场测量。

本次保留记录在 `pc_vision/output/photo_suite_v1/` 与 `replay_suite_v1/`，游戏例图为
`game_000073.png`（直接命中）、`game_000075.png`（反射）、`game_000076.png`（Portal）
和 `game.png`（077完整组合）。`output` 是现有忽略的生成输出位置，不是源代码副本。

## 安装与运行

在仓库根目录运行，推荐 Python 3.10+：

```powershell
python -m venv pc_vision/.venv
pc_vision/.venv/Scripts/python -m pip install -r pc_vision/requirements.txt
pc_vision/.venv/Scripts/python pc_vision/app.py --image "D:/photos/test.png"
pc_vision/.venv/Scripts/python pc_vision/app.py --camera 0
pc_vision/.venv/Scripts/python pc_vision/app.py --video "D:/videos/test.mp4"
```

下文的 `python` 应替换为上述虚拟环境解释器，或先激活该虚拟环境。图片中文路径使用 `imdecode/fromfile` 支持；视频能否解码以及摄像头编号取决于本机 OpenCV 后端。

生成合成图并启动完整调试界面：

```powershell
python pc_vision/test_vision.py --demo
python pc_vision/app.py --image pc_vision/output/demo.png
```

无界面批处理及保存：

```powershell
python pc_vision/app.py --image pc_vision/output/demo.png --headless --output pc_vision/output/run01 --save-frames
python pc_vision/app.py --video "D:/videos/test.mp4" --headless --max-frames 100 --output pc_vision/output/run02
python pc_vision/app.py --camera 0 --width 960 --output pc_vision/output/run03
python pc_vision/app.py --image frame.png --headless --types TARGET --output pc_vision/output/target01
```

`--output` 必须为不存在的新目录，避免覆盖原图和旧结果。程序不写入输入文件；处理、绘制使用独立副本。输出 `detections.jsonl`、`effective_config.json`；仅在 `--save-frames` 时保存标注 PNG。每帧也向标准输出写 JSON，点击信息写标准错误。视频读取失败视为结束；损坏视频与正常 EOF 无法仅凭 `read()` 区分。摄像头读取失败会报错并释放资源。`--types TARGET` 只评估 TARGET，但仍使用同一份绿色主体、白环、黑色中心、轮廓层级、几何和拒绝原因判定；它不是第二套简化算法。

## 模块和流水线

| 文件 | 职责 |
| --- | --- |
| `config.py` | 集中 HSV、形态学、面积、几何、marker、评分和标定参数 |
| `detector.py` | HSV 分割、候选、几何量、marker、Detection 和绘制 |
| `body_refinement.py` | SOURCE 闭合黑边恢复、WALL 周围亮度对比 |
| `app.py` | 输入、调试窗口、像素取样、JSONL 和图像输出 |
| `calibrate.py` | 多图片标注样本统计、阈值建议 |
| `test_vision.py` / `test_integration.py` | 合成正反例、旋转、标定、图片与视频回归 |

流水线：BGR → HSV → 七色 mask 和独立 WALL mask → open/close → 外轮廓候选 → SOURCE 可选黑边恢复 → 面积过滤 → ROI 内 marker → 宽松几何校验 → Detection。

`config.py` 的 `stages` 可逐项配置，也可用命令行临时关闭：

```powershell
python pc_vision/app.py --image pc_vision/output/demo.png --disable open close
python pc_vision/app.py --image pc_vision/output/demo.png --disable markers geometry
```

可选阶段：`hsv segmentation open close candidates area_filter markers geometry source_outline draw`。关闭 HSV、分割或候选后，下游依赖阶段明确跳过，JSON 的 `status` 说明原因；不会悄悄改用 RGB。`--disable source_outline` 仅关闭 SOURCE 外黑边恢复。关闭 marker/几何仅用于消融调试，置信分数上限降低，不能作为正式识别效果。`--headless` 单独关闭所有窗口。

## 物体判定依据

| 类别 | 主特征和 marker | 几何辅助 |
| --- | --- | --- |
| MIRROR | 黄色；主体轮廓内两个分离黑色实心圆，投影分别靠近长轴两端、接近横向中线 | 旋转长宽比、矩形填充率、面积 |
| PORTAL_A | 蓝色；两端分别为白色实心圆和白色圆环，环内仍为蓝色 | 旋转长宽比、填充率、marker 圆度及相对位置 |
| PORTAL_B | 橙色；与 A 同样的 marker，环内为橙色 | 与 A 相同 |
| TARGET | 绿色；靠近主体中心的白色环；孔洞内存在近同心黑色实心圆 | 主体圆度、近等轴；支持黑圆直接填满孔洞 |
| SOURCE | 品红色；无需 marker | 宽松长宽比和填充率；最小包围三角形面积匹配只加少量分，不数顶点、不要求精确三角形 |
| WALL | 独立的低饱和深灰 mask | 长宽比、面积、填充率、深灰占比及周围亮度对比；不查四角 |

marker 使用 `RETR_CCOMP` 层级区分外轮廓和孔洞。实心圆检查前景占比及孔洞面积；圆环检查孔洞比例、圆度与同心程度。marker 搜索被主体外轮廓填充区域约束，不把 bbox 外围背景算进来。黑色边框包围彩色候选时被排除，防止当成额外 WALL。边框和胶囊曲率不作硬性判定，因此这是按颜色与 marker 分类的原型，不能验证所有印刷轮廓细节。

默认 3×3 开闭运算会损失很细的环：远距离目标应先检查 mask，再缩小核、关闭某项形态学，或提高拍摄分辨率。实体尺寸 mm 只用于选择合理的比例；没有相机标定与平面映射时，不输出真实毫米坐标。接触/遮挡的同色物体可能合并，不提供分水岭拆分和跨帧跟踪。

## 输出语义

`detections` 中每个对象严格为：

```json
{"type":"PORTAL_A","center_x":480.0,"center_y":110.0,"bbox_x":380,"bbox_y":80,"bbox_w":201,"bbox_h":61,"angle":0.0,"confidence":0.985}
```

- 坐标为处理图像像素，原点左上，x 向右，y 向下。`--width` 缩放后输出也随之缩放；顶层记录原图与处理图尺寸，可按 x/y 比例换回原图。
- bbox 是最终采用的外轮廓的轴对齐边界。SOURCE 成功恢复闭合黑边时包含外黑边，否则仍使用品红主体；WALL 使用深灰主体，不包含外围浅色边。其余类仍使用主体颜色。中心为该填充外轮廓的面积质心，不扣除 marker 孔洞。
- SOURCE 的面积质心靠近三角形底边，这是正确的几何位置，并非 bbox 中心或尖端。候选中的 `body_bbox` 是最初颜色区域的框，`outline_used` 标明是否恢复了外黑边；黑边不闭合时不推测缺失区域。
- `candidates` 保存所有通过面积过滤的候选，包括被拒绝的候选：bbox、center、area、width/height、rotated_width/height、aspect_ratio、circularity、fill、color_fill 和判定原因。
- `area` 为外轮廓几何面积（像素²，包含孔洞）；`width/height` 为轴对齐尺寸；`aspect_ratio` 为最小旋转矩形长边/短边，避免旋转造成错误。
- 圆度为 `4πA/P²`，填充率为轮廓面积/旋转矩形面积。`color_fill` 是主体颜色 mask 像素/填充轮廓像素。
- angle 单位为度，图像坐标下顺时针为正。MIRROR/WALL/SOURCE 使用长轴，范围 `[-90,90)`，有 180° 歧义；SOURCE 不是三角尖端朝向。Portal 从实心圆指向圆环，范围 `[-180,180]`，允许任意旋转；TARGET 无可辨方向，固定为 0。
- confidence 是规则匹配分数，不是统计概率。SOURCE/WALL 没有强 marker 证据，默认分数较低。阈值须用真实图片验证，不能把合成图上的高分解释为现场准确率。

## 调试窗口与现场调参

`original`：原图副本及点击读数；`HSV masks`：七色和独立 wall 共八种 mask 拼图；`candidate mask`：候选填充区域；`marker mask`：候选内用于验证的黑/白 marker mask；`final result`：通过验证的 bbox、中心、类型、confidence 和 marker 说明。默认不画被拒绝的红框，诊断时加 `--show-rejected`；所有候选和拒绝原因仍保留在 JSON 中。

在 original 或 final result 点击像素，可显示原始 BGR 和 HSV，不读取绘制后的颜色。按 Q/Esc 退出；图片模式按空格/Enter 结束。GUI 用英文标签以避免 OpenCV 默认字体无法显示中文。窗口按处理分辨率显示，屏幕较小时使用 `--width`。

OpenCV H 范围 0..179，S/V 范围 0..255。所有 HSV 区间都在 `config.py`，支持多个区间（例如品红跨 H=0 的部分）。JSON 配置只需写需要覆盖的项，例如：

```json
{"hsv":{"yellow":[[[20,90,70],[36,255,255]]]},"morphology":{"kernel":3},"candidate":{"min_area":200}}
```

使用 `--config my_config.json` 加载。默认值是启动阈值，不能保证适合所有灯光或摄像头。先固定曝光、白平衡和相机高度；检查黄色/橙色、黑色/灰背景、白色/高光的分离情况。对同一实体记录不同位置、旋转和光照的图像，并留一部分图片不参加标定，用于独立验收。

## calibration 模式

不能仅从没有标签的一组图片知道某个像素属于哪种颜色。此模式使用人工确认的 ROI 或二值标注 mask，不使用初始 HSV 阈值预筛样本，避免循环偏差。

1. 复制 `calibration.example.json`，填写真实图片路径与采样矩形 `[x,y,w,h]`。示例坐标是占位值。路径相对于 manifest 文件，可用绝对路径；JSON 的 Windows 路径推荐 `/`。
2. 每个 ROI 只包含指定颜色，避开边框、marker、背景和反光。对同一颜色可重复添加多个图片、多个 ROI。用鼠标像素读数辅助确定坐标。
3. 可用 `{"image":"frame.png","color":"blue","mask":"blue_labels.png"}` 替代矩形。mask 与原图同尺寸，非零像素为人工标签，建议无损 PNG；同时指定 ROI 时取交集。
4. 运行并用新阈值检查未参与标定的图片：

```powershell
python pc_vision/calibrate.py --manifest samples.json --output pc_vision/output/calibration01
python pc_vision/app.py --image "D:/photos/validation.png" --config pc_vision/output/calibration01/hsv_config.json
```

`statistics.json` 给出每色 min/max/mean、P1/P5/P50/P95/P99、样本数量、环形 Hue 均值、Hue 集中度和展开后的 Hue 百分位。min/max 是所有标签像素的精确结果；mean/percentile 超过默认 250000 像素后用固定随机种子的均匀抽样估计，避免无限累积。此实现仍需要一次解码整幅图片和一个 ROI 的临时像素数组。

`hsv_config.json` 用 P1/P99 加 padding 建议区间，处理 Hue 首尾跨界。白/黑不限制 Hue；黑色不限制 S。未采到的颜色列入 `missing_colors`，加载时保留默认阈值。Hue 线性均值仅作原始统计，跨零点优先看 circular_hue_mean；低饱和黑白的 Hue 本身不稳定。混入背景、多峰样本或高光会产生过宽阈值，需要复查标签与 mask，程序不会自行宣称阈值已达到现场精度。

## 相机画面中 WALL / TARGET 漏检的排查

默认阈值来自原型设计，未按某台摄像头的实时画面标定。旧版 WALL 与 marker 共用 `V<=65`，在墙体亮度不均匀时会只识别暗的一半。现在 WALL 使用独立的 `wall.hsv`（默认 `S<=110, V<=120`），黑色 marker 仍使用 `hsv.black`（默认 `V<=65`），两者互不影响。绿色 `S>=70`、白色 `V>=175` 在低对比度画面上仍可能漏掉绿色主体和白色 marker。没有候选框也可能是面积过滤或 mask 连通造成的，不能仅凭截图认定是硬件故障。

WALL 同时要求周围区域的 V 中位数比内部高至少 12（`geometry.WALL.min_surround_contrast`），减少灰色阴影的误检；可通过 `surround_contrast` 字段查看实测差值。这个条件不能完全排除边缘清晰的深色阴影。只有已通过验证的彩色物体才参与墙体重叠排除，未通过 marker 的蓝色偏色候选不会把墙体切短。标定工具的 black 标签仍对应 marker，WALL 范围需单独配置 `wall.hsv`。

SOURCE 的黑边恢复要求 ROI 内存在闭合暗轮廓，其孔洞覆盖至少 85% 的品红主体，外轮廓面积不超过主体的 1.8 倍。它只修正定位，不把三角形顶点数变成分类门槛；黑边断裂、与外部深色物体相连或不符合限制时回退到品红主体。参数集中在 `source_outline`，局部暗轮廓复用 wall mask。

可先加载独立的低对比度试调配置，默认配置不变：

```powershell
python pc_vision/app.py --camera 0 --config pc_vision/camera_low_contrast.json --output pc_vision/output/camera_check01
```

配置将黑色 V 上限设为 115、绿色 S 下限设为 25、白色 V 下限设为 150/S 上限设为 85，并适度降低蓝/橙的 S 下限。它是用于现场比较的起点，**不是从用户截图或真实原始帧统计出的标定结果**。若背景也进入黑色 mask 或绿色 mask，请根据像素读数收紧阈值；不要只为提高召回而不断放宽。不要另加关闭 markers/geometry 的参数来判断正式效果。

在 original/final result 点击墙体内部、旁边背景、绿色主体和黑白 marker。终端除 BGR/HSV 外，还会输出 5×5 邻域 HSV min/max/median，以及每色的 `pass_hsv` 和逐区间失败条件，例如 `V>65`、`S<70`。这些条件是形态学前的单像素阈值检查，不代表整块物体已通过；Hue 跨零时邻域线性中位数只供粗看。

候选 JSON 中包含 `rejection_reasons`、`colored_overlap` 和 marker 的中心/面积/圆度。加 `--show-rejected` 后，最终窗口中拒绝框也标注具体原因：

| 原因 | 应检查 |
| --- | --- |
| `no_black_round_markers` / `no_white_round_markers` | 黑/白阈值、圆形区域大小、模糊与噪声 |
| `no_white_ring` | 白色阈值、环是否断裂或孔洞被闭运算填满 |
| `marker_end_position_failed` | 是否两端都检测到 marker，横向偏移是否过大 |
| `marker_disk_ring_pair_failed` | 是否把环填成实心圆，或实心圆中出现假孔洞 |
| `ring_inner_color_failed` | 环内主体颜色是否仍通过蓝/橙阈值 |
| `ring_center_or_black_failed` | TARGET 环位置、黑色中心、同心程度 |
| `aspect_ratio` / `fill` / `circularity` / `color_fill` | 候选尺寸、形状或颜色占比；查看是否并入阴影背景 |
| `colored_overlap` | 黑色候选主要包围彩色主体，可能是边框；WALL 默认允许少量彩色噪斑，覆盖率超过 10% 才排除 |
| `surround_contrast` | WALL 是否比周围明显更暗，或目标贴边导致无法取得足够背景样本 |

`segmentation_stats` 汇总各 mask 像素数及轮廓的零面积、过小、过大、已评估数量。black/white 仅用于 marker，因此其物体候选计数为 0；墙体计数在 wall 下。找不到某目标时，结合 mask 和这些计数区分“阈值未分出”与“过滤拒绝”。

窗口有焦点时按 **S**，保存当前帧到 `--output` 下的 `snapshot_XXXXXX/`：未标注的输入 `input.png`、处理分辨率原图 `processed.png`、最终图、所有 mask 和 `diagnostics.json`。同一帧不会重复覆盖。重新运行应换新的输出目录。

离线图片或有限帧采集可加 `--save-debug` 自动保存每帧上述数据，磁盘开销较大：

```powershell
python pc_vision/app.py --image "D:/photos/raw.png" --config pc_vision/camera_low_contrast.json --headless --save-debug --output pc_vision/output/image_check01
```

旋转对照应区分：①同一张保存图片用软件旋转 180°（像素值不变，用于查算法方向问题）；②在摄像头前旋转纸张（目标换位置，光照、反光、曝光和透视都可能变化）。本项目已测试低对比度合成目标在四个位置及软件旋转 180° 后的类别/中心一致性。现场仍需保存原始帧对照，不能据此排除所有摄像头或算法问题。

## 测试与移植到 Zynq-7020B

```powershell
python -m unittest discover -s pc_vision -p "test_*.py" -v
```

20 项测试覆盖六类及旋转、缺失/错误 marker、环孔完全为黑色、空心黑框、噪点、输入不变、阶段开关、Hue 跨零、中文路径、图片/视频/标定 CLI、防覆盖、WALL 亮度渐变与蓝色偏色、SOURCE 完整/断裂黑边以及拒绝候选显示。截图只用于读取未被标注遮挡的像素和比较已有框，带绿线/文字的最终结果图不是原始相机帧，不能作为完整准确率验收数据。USB 摄像头、实际鼠标操作和现场照明仍需在目标 PC 验证。

建议的后续分工（本阶段没有修改或综合 FPGA 工程）：

| 放置位置 | 处理与原因 |
| --- | --- |
| PL 优先 | 每像素 RGB→HSV、七色及独立 WALL 范围比较、二值 mask、固定小核腐蚀/膨胀；流水处理规则、可用行缓存。HSV 除法需要定点/查表设计并与 OpenCV 色相量化对齐 |
| PL 后续评估 | 连通域标号、面积、bbox、坐标和/二阶矩统计；可减少 DDR/PS 数据量，但标签等价合并和最坏噪声标签数需专门设计 |
| PS 优先 | ROI 提取、轮廓及孔洞层级、SOURCE 外黑边恢复、WALL 周围中位数对比、圆环/实心圆配对、同心度、长轴角度、几何校验、分类评分、标定、配置与通信 |
| PC 保留 | 调试窗口、样本标注、离线统计与算法回归；确认固定点实现前保留浮点参考结果 |

潜在瓶颈是八路全帧 mask 内存读写和开闭运算、噪声引发的大量轮廓、每候选的孔洞分析/临时 mask 分配、视频解码、GUI 和逐帧 PNG/JSON 写盘。当前 marker 和 SOURCE 外边框分析已限制在 ROI；先通过 `--headless`、关闭绘制/保存、控制处理分辨率比较 `processing_ms`。该时间只含检测与绘制，不含采集、解码、显示和落盘，不能直接等同端到端帧率。

FPGA 端可先实现 HSV+mask+形态学，由 PS 完成候选与 marker；有实测带宽/CPU 压力后再考虑 PL 连通域。不要直接把 OpenCV 轮廓层级和动态内存结构照搬为 RTL。建议验证各阶段 mask 一致性、连通域统计误差、边界和环孔保留情况，再固定阈值及位宽。
