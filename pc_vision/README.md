# PC 颜色与 marker 视觉原型

独立于 `color_test/` 的 Python + OpenCV 原型。支持图片、USB 摄像头、视频文件。识别 MIRROR、PORTAL_A、PORTAL_B、TARGET、SOURCE、WALL；无神经网络、YOLO、OCR、ArUco 或多边形顶点数分类。

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
```

`--output` 必须为不存在的新目录，避免覆盖原图和旧结果。程序不写入输入文件；处理、绘制使用独立副本。输出 `detections.jsonl`、`effective_config.json`；仅在 `--save-frames` 时保存标注 PNG。每帧也向标准输出写 JSON，点击信息写标准错误。视频读取失败视为结束；损坏视频与正常 EOF 无法仅凭 `read()` 区分。摄像头读取失败会报错并释放资源。

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
