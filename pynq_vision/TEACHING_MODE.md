# PYNQ/Linux 实景教学模式

本功能在原 PYNQ 2.6.2 / Python3.6 Session 上增加鼠标教学层。板端使用 numpy 做轮廓、原图颜色和简单光线关系的统计分析，不安装大语言模型，不训练神经网络。电脑仍运行原串口后台、Web 和唯一 C 游戏会话。

## 先保存的恢复点

`output/build/game_app/pynq_teaching_baseline_20261101_1/` 包含修改前全部 Git 可见源码（含未提交、未跟踪文件），以及当前 `pynq_beam_hardware_5`、`pynq_beam_c_5`、`pynq_beam_runtime_11`。`pre_teaching_source_project.zip` 的 SHA256 为 `7219f9ac516ec6a7643a3450707bdee60d1cbdbd795a0976d06ae0aebaa23b3d`；1267项文件逐项哈希、ZIP CRC与独立恢复通过，解包内容在同目录 `source_project/`。这不是教学功能实现完成后的包，也不是新的系统启动镜像。

## 操作

鼠标接到板卡 USB Host，使用已经确认的 `/dev/input/event*` 路径。只支持相对移动且有左键的鼠标；不猜设备、不停止桌面服务。Linux EVIOCGRAB 独占失败则拒绝进入教学。设备断开、队列溢出或 SYN_DROPPED 会取消当前笔划，重新释放左键后才接受新笔划。[Linux 输入事件语义](https://www.kernel.org/doc/html/latest/input/event-codes.html)。

HDMI工具栏占顶部96行，画面坐标仍为原1280×720，不缩放相机。按顺序完成红色轮廓→绿色特征→黄色光线三个阶段；每次只显示、绘制和擦除当前阶段的笔划，其他阶段的笔划保存在内存中。左键点击工具按钮，在下方实景区域长按左键绘制；松开结束一笔。未满足准入的阶段按钮显示为灰色，点击只给出提醒，不会切换画笔。

| 按钮 | 用途 |
| --- | --- |
| OUTLINE | 红色外轮廓阶段。只描出物块外边界；确认时要求恰好一个完整闭合外轮廓 |
| FEATURE | 绿色特征阶段。红色轮廓确认后开放；描出内部标记、圆环等特征，不能改变外边界 |
| RAYS | 黄色光线阶段。绿色特征确认后开放；不能跳过前面的确认 |
| PEN / ERASER | 画笔／18像素半径局部橡皮。橡皮只擦当前OUTLINE、FEATURE或RAYS层，重叠位置也按所选层处理 |
| CLEAR | 清空当前层。清空/编辑轮廓或特征都会使已分析模型和所有案例失效；另一物块标记层的笔划保留 |
| CONFIRM / ANALYZE | 前两个阶段显示CONFIRM：确认轮廓后自动进入FEATURE，确认特征后自动进入RAYS。光线阶段显示ANALYZE，用于重新分析已保存案例 |
| IN / OUT | 分别录入有方向的入射／出射线；线尾有箭头。IN从远处画到物块，OUT从物块画到远处 |
| SAVE | 保存一组IN/OUT案例。每组各一笔近似直线；保存后清空当前黄色草稿 |
| UNDO | 删除上一组已保存案例并重新分析 |
| NEW | 开始一个新物块模板，清空当前模板及其案例 |
| SEND | 重发当前完整版本；通常会自动传送 |

初始为OUTLINE，先画闭合红色外轮廓。松开左键时立即检查闭合：缺口超过16像素时显示`OUTLINE OPEN GAP ... PX`，并在两个断口画白色提示圈；多个断开分段显示缺口提醒。此时CONFIRM会拒绝，不能进入FEATURE；不会自动补线伪装闭合。缺口修复后显示`OUTLINE CLOSED PRESS CONFIRM`。确认时仍会拒绝过小、自交、多个闭合轮廓或残留的断开分段。

点击CONFIRM确认红色轮廓后，红线隐藏，自动进入FEATURE。此时只用绿色描出特征。绿色特征独立存储，即使它是闭合圆环也不会变成外轮廓；没有红色闭合轮廓时，绿色图案不能代替它。绿色笔划允许线状或环状，不强制每笔闭合；它只记录人工特征位置，不自动宣称识别了圆环/实心点的语义。再次点击CONFIRM确认特征（没有内部特征也须确认该阶段），绿线隐藏，自动进入RAYS。

分析使用独立相机原图，不从红绿黄线或光标取色；中心、方向、实际轮廓和颜色中位数生成电脑端虚拟模板，类别保持UNASSIGNED，不凭圆形/矩形猜游戏物块。回到OUTLINE修改时，后续确认、已分析模型及光线案例失效；回到FEATURE修改时保留已确认轮廓，但特征确认与光线案例失效。原始笔划分层保留，必须按阶段重新确认后才能保存新的光线案例。

红色笔划可在擦除后补画并拼接恢复轮廓；绿色特征单独存为`markers_local`，只用于特征记录与电脑绿色预览。旧脚本`action('OBJECT')`保留为OUTLINE入口，但不会再把其他红色笔划自动解释为特征；已有旧版模板需要在FEATURE中重新录入特征。程序接口在前两个阶段调用`action('ANALYZE')`等同CONFIRM，也必须按顺序各确认一次。NEW同时清空红、绿、黄三层。

进入RAYS后，依次选择IN画一笔、OUT画一笔、SAVE。至少保存三个不同入射方向，相邻用于覆盖的方向相差至少20度。分析比较直通、反射、固定转角、固定出射方向；最大方向残差不超过5度且与次优假设至少相差2度才接受。出入口位置另分同点、固定局部出口、固定局部位移；不能一致解释就输出UNKNOWN。规则confidence只表示拟合残差，并非经过数据集校准的概率。即使三个案例拟合通过，也只得到二维候选规律，不能证明所有方向或所有物体行为。

录入期间保持物块、相机和棋盘静止。每一模板使用固定相机像素坐标和物块局部轴，不包含实时跟踪、毫米标定、纹理/材质重建或跨物块配对学习。移动物块后点NEW重新录入。第一版一次录入一个模板；NEW替换电脑预览中的当前模板。清除后的黄色草稿不影响已保存案例，删除保存案例用UNDO。

## 入口

原命令和Notebook默认不启用教学。仅在实际板端准入、设备确认及本轮硬件操作另行授权后，用原命令增加 `--teaching-mouse /dev/input/eventX`：

```sh
python3 -B -m pynq_vision.beam_launcher --manifest output/build/game_app/pynq_beam_hardware_5/hardware.json --overlay output/build/game_app/pynq_beam_hardware_5/system_wrapper.bit --library output/build/game_app/pynq_beam_hardware_5/libbeam_pynq.so --uart /dev/ttyXXX --i2c-device /dev/i2c-X --run --teaching-mouse /dev/input/eventX
```

路径均须替换为本次已确认的实际设备。文件检查仍用原 `--inspect`；不会打开鼠标、UART或PL。Notebook `pynq_vision/notebooks/beam_teaching_pynq.ipynb` 使用同一个Session，无保存的实测输出。原BOOT、PL、手工JSON和ARM C库不变；既有当前boot保护准入、UART控制台/getty检查、三槽所有权和安全退出要求继续执行。

电脑从原 `pc_vision(1)/pc_vision/start_game.ps1` 启动后台，再点“教学预览”或访问同一后台的 `/teaching`。它复用原BoardInput串口所有者；不要另开串口助手。新板端教学包必须与本次电脑源码配套。页面显示当前录入阶段与未闭合提醒；收到完整快照后，累计预览已确认的轮廓、特征和已保存光线案例，可下载特征JSON、物块模板Python、光线Python/C草案。板端只显示当前正在绘制阶段；电脑结果区用于查看已确认记录。无需板卡联网。断线会标记为未连接，已收到的预览只能作为历史教学数据。

代码只作为文件下载，产品不会exec、编译或自动加载它们。生成函数的输入输出为物块局部像素坐标；有限碰撞边界、Portal身份/配对及正式游戏适配仍由原C核心负责。UNKNOWN导出的函数明确拒绝求解。教学文件不会成为有效POSE、开始命令或通关证据。

## 协议与性能边界

教学使用 `00 FE + COBS(TG/v1/会话/版本/分片号/总数/文档CRC/内容/包CRC) + 00`；现有 `00 FF` wire v3 的版本、类型、控制和姿态含义不变。完整快照以`annotation_layers`明确红色轮廓、绿色特征、黄色光线的职责，以`annotation_stage`及两个确认标志记录当前阶段；轮廓与特征分别通过`outline_local`和`markers_local`传输。共享解析/拟合代码位于 `pynq_vision/teaching_protocol.py` / `teaching_features.py`，电脑导入它们不需要PYNQ或numpy。电脑校验阶段准入、原始序号/时间字符串、轮廓、单位方向和案例一致性；旧版本、缺片、坏CRC、超长或非法数据不会替换预览。

每包内容128字节、文档最多32KiB；每帧最多在原显示退休及v3发送后追加一个教学包。只发布完整版本，无编辑中的半成品；修改会作废未发完的旧版本。完整快照周期重发，SEND可主动重发。没有新增ACK协议，因此完整文档可能需要数秒至数十秒，并受现有采集间隔影响。鼠标独立线程只读输入并排队，光标显示仍随原安全显示循环更新，不承诺高刷新率。笔划、点数、案例、输入事件队列和文档均有上限。

## 验证

```powershell
python -B -m unittest pynq_vision.tests.test_teaching -v
```

新增检查为合成CPU输入及本机HTTP，不代表实际PYNQ鼠标、Overlay、DMA、相机、HDMI或UART已通过。没有接板、改服务、写SD、生成BOOT或运行Vivado。
