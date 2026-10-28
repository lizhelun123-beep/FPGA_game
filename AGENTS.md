# AGENTS.md

## 目标与范围

- 2026-10-27 最新恢复决定：以 `b206663` 的第一版完整实景叠加/彩色旧物块检测为参考恢复；恢复前全部非忽略源码与未跟踪文件已存 Git 检查点 `636f4e5a659b6e3e9266e54385f753759bf0ce75`（不含构建输出）。继续 Standalone/core0、虚拟光源 `(32,500)` 向右、五类物体、无 KEY/菜单/关卡。Mirror 为黄色主体加两端黑点，Portal 为蓝/橙主体加白色实心点与圆环，取消 Mirror/Portal 中央白条和 AprilTag 运行依赖；WALL 保留两端白条。当前使用同一 `vision_ps` 的 `VISION_PROFILE_RESTORED`，旧 AprilTag 源与测量配置保留为历史，不自动启用。
- 本次保留 timed B 防抖及 250ms 支持间隔；新观测 PENDING/缺失时，不把旧姿态冒充有效输入。显示可短时保留上一份相机原图及同帧模型/完整光段，保留原始序号/时间并明确 STALE、光线变暗；PENDING 最多6s、明确物体缺失最多250ms。物体持续移走250ms后按新的实测子集提交。沿用当前安全三缓冲/flush/退休栅栏，禁止清屏半成品提交。Portal B 单向出口由唯一 JSON 的 `portal_b_exit_side=1` 定义为 solid→ring 轴的正法向 `(-axis.y,axis.x)`，出射点在同侧长边、方向垂直向外，旋转 B 则出口随之转动；其他调用路径保留原 Portal 配对规则。
- 本次恢复源码/host/ARM 编译及 BOOT 打包沿用已授权范围；用户负责 SD 复制与实景上板。未恢复旧裸板环形指针猜测所有权的复制方式，未授权硬件连接、复位、下载、SD写入或 Vivado。下列三标签/白线定位和 PL 加速方向是此前路线记录，本次默认已被上述旧物块恢复决定覆盖。
- 2026-10-27 用户最新决定：板端实景绘制改为 Cortex-A9/core0 Standalone 裸板，不再以 PYNQ/Linux 为运行或部署依赖。当前交付固定光源 `(32,500)` 向右、五类物体动态交互的最小测试版，无 KEY/菜单/关卡。入口与用户编译步骤见 `color_test/software/vision_ps_baremetal/STANDALONE_BEAM.md`；保留旧 PYNQ 实现作历史参考，后文相关默认路径不覆盖此决定。
- 2026-10-27 最新分工：用户已授权 Codex 编码、主机检查、ARM 编译并生成本测试版 BOOT；由用户复制到 SD 卡和实景上板。这不授权 Vivado 完整构建、硬件连接/下载/复位或 SD 写入。裸板会话没有 Linux boot_id/sudo/systemd；记录输入 XSA/BIT/ELF 身份、启动日志和实际 DMA 停机状态，不能套用 Linux 会话清理命令。
- 2026-10-27 用户允许取消非必需的250ms：当前无关卡裸板光束测试版取消按帧龄拒绝/停机（唯一JSON的`real_scene.beam.max_age_ms=0`），相机原图、模型和光路仍使用同一CPU帧，保留原始时间/序号、实测帧龄显示及所有DMA所有权/超时/异常停机。此例外不修改完整游戏`board_game.scene_max_age_ms=250`，也不代表检测延迟或实时性已改善。
- 2026-10-27 最新性能方向：用户要求加快每帧识别并通过PL加速，明确不取消防抖；继续保留B，不切A、不放宽B的250ms支持间隔、不用旧姿态维持光线伪造通过。build5用户日志显示86帧中55帧PENDING、5帧RESTRICTED，暂无故障停机；先使用build7的原AprilTag四阶段耗时定位PL迁移边界，再完成相应硬件/PS接入。build7仅分项诊断，不是PL加速制品，未改BIT。
- 2026-10-27 Mirror/WALL修正：裸板光束编译以`GAME_BEAM_STANDALONE`使用完整1280×720检测区，取消旧六类相机UI的`center_y<590`和x范围过滤；仍要求检测框与图像相交，颜色/形状/标记/几何及B防抖门槛不变。旧非Standalone路径保留原场地限制。该修正覆盖新的固定光线`y=500`以及更下方的物块位置，不是放宽到任意无效检测。
- 唯一工作区是当前仓库。产品方案以 [`pc_vision/FINAL_PLAN.md`](pc_vision/FINAL_PLAN.md) 为准；状态从 `PROJECT_STATE.md` 的 `Current Goal`、`Delivery Gates and Next Task` 读取。只读当前任务相关段落，冲突时以用户最新决定为准。
- 当前交付为摄像头驱动的两种显示：实景画面叠加光路，以及电脑端完整虚拟游戏。板端复用 Linux/PYNQ 采集、C/C++ 定位、场景适配和现有 HDMI；电脑端复用 NativeGame/C 会话与 `pc_vision/godot/` 呈现层。
- 复用同一检测入口、`game_session`、`ray_game` 和唯一游戏配置；不复制工程，不另建一套检测器、光路规则或游戏状态机。实景与 Godot 是同一有效场景的两种呈现，不要求在 PYNQ 上重新实现电脑游戏美术。
- 优先完成精确姿态/有效边界、固定逻辑光源和实时闭环。显示基线、PL 优化、历史竞赛材料只在直接阻塞交付时处理，不为整理材料扩大范围。

## 运行约定

- 每关使用固定逻辑光源，发射点和初始方向来自关卡配置；取消实体 SOURCE 检测、定位与方向锁定要求。只固定发射条件，后续传播仍与实物动态交互。修改实体必检清单及开始/重置契约，不能只删实物或只画图标；求解器内部可保留 SOURCE 表达，但不得伪装成摄像头观测。
- 摄像头保持现有两 lane、1280×720、RAW10/BGGR。两个 Portal 已由用户改成三标签：A 为 10/11/12，B 为 20/21/22，字典 `tag36h11 / DICT_APRILTAG_36h11`；主体 8×8 mm，四边各 2 mm 白边，完整贴纸 12×12 mm。Portal 外形 80×25 mm，以实际粘贴中心和朝向建立刚性模板；其余标记默认保留。
- 定位重点是中心、方向与有效边界。联合可见标签角点拟合整体 Portal，不只平均标签中心；区分标签尺寸、物体外形与有效入口。Mirror 为有限反射面，Portal 保留长侧入口和配对传送规则，Target 沿用已有效的圆形边界；颜色外框不自动成为碰撞边界。
- 手移、原地旋转及小角度微调必须反映到同一份有效模型和光路；不用鼠标拖动模型，不用场景注入或 START 绕过实体定位。稳定算法保留连续滤波 A 与死区/迟滞确认 B 两种选项，初版建议 B；在同一段观测比较后决定，不能套用旧 Portal“只有位移才能改方向”规则。
- 相机像素、棋盘毫米和显示像素分别标识，经真实标定转换；中心、方向参考点、有效边界、光路和粒子锚点使用一致变换。模型尺寸由实测模板决定，不随检测 bbox 缩放；历史 `[164,56]` 等虚拟单位不能直接当成毫米。
- 一个游戏会话只有一个权威 `game_session/ray_game` 和一处稳定姿态提交。板端独立游戏或电脑 NativeGame 按本次部署选择；同局双屏共用已提交场景、完整光段、计时和结算，不能分别计算通关。Godot 只呈现权威结果和发送操作请求。
- 实时帧保持 generation、sequence、captured time、level 等原始标记与时钟语义。现有 `scene-v1.capture_ms` 是处理开始时间，不声称是曝光时刻；跨设备明确时钟映射。模型和光路按同一快照替换，过期、缺失、旧关卡或受限遮挡观测不能通关。
- 显示保留与有效性分开：复用 PC 短时保留、STALE 变暗和超时清空，不刷新旧姿态的采集时间；6 s 显示保留不是游戏有效期，C 的 250 ms 新鲜度门限不能为消除闪烁而放宽。定位低频不能靠高刷新动画或无限保持掩盖。
- 板端继续使用一个进程/会话所有者管理 capture 与 display；电脑呈现进程不另开板端采集/设备所有者。CPU 不读写设备仍占用的缓冲；退出、超时和异常先确认相关 DMA HALTED，再释放各自缓冲。保留 cache、stride、span 和同步语义，不猜地址或设备所有权。
- 摄像头、电脑画布、实景叠加与最终 HDMI 统一 1280×720、16:9；1280×800 屏幕保持比例显示，原生桌面全屏可上下各留 40 像素。迁移旧 800 行画布、菜单和鼠标坐标时改同一份布局，不拉伸相机图或变更采集模式。
- Godot 复用现有中文菜单、模型、背景与结算美术，添加沿光段运动的粒子、反射火花和 Portal 进出效果。粒子只读有效光段/命中事件，不参与求交、通关或星级，不能跨越终止点或补画 Portal 间的实线。
- 关卡与计时沿用当前契约：准备不计时；玩家明确开始后每关 180 秒；命中 TARGET 且用时 `<60/<120/<180` 秒为 3/2/1 星，超时为 0 星；可跳关，无持久化和声音。不得截断求解结果制造通关。

## 当前工作与依赖

- 离线先接入已贴的六个 Portal 标签、实测有效边界和固定逻辑光源契约；复用照片/录像比较 A/B 防抖，特别检查原地旋转、边界擦碰及遮挡恢复。
- 沿既有 `capture_worker` → `game_capture_owner_dispatch`/`game_pump` 路径处理 `PROJECT_STATE.md` 当前连续采集阻塞；不重新执行已停止且没有新信息的 PARK/首帧诊断。离线定位与该阻塞可按依赖穿插推进。
- 将已有 NativeGame 权威状态接入 Godot，迁移剩余 800 行接口到 720p，验证实景/虚拟画面几何一致以及菜单 → 开始 → 交互 → 结算 → 下一关和鼠标输入。
- 选择最便宜的 host/ARM 定向检查后，才安排有明确目的且获授权的板端验证；静态照片、美术预览和编译通过不能代替实时闭环。BOOT、内核、rootfs、SD 和 PL 只在当前任务明确需要且获授权时修改。

## 工作与验证规则

- 默认由单智能体完成任务。只有用户明确允许时，才可创建、启动或委派子智能体；任务复杂、可并行或预期提速不能代替用户授权，且不得超出用户指定的授权范围。
- 先读 `PROJECT_STATE.md` 当前摘要和目标文件，再用 `rg` 做定向检查。保留用户已有修改；不 reset、覆盖或删除未知归属文件。
- 删除或替换仍有价值的旧版 PYNQ 实现/说明前，先确认引用关系并保存可恢复的本地 Git 提交或归档分支，记录提交号；归档必须包含将删除的未提交/未跟踪文件，不能只指向旧 HEAD。本次旧版说明归档为 `codex/archive-pynq-guidance-20261026`（`5da71ab927667959c90ebd93e2c0be96c512697b`）；它不代表已备份所有未提交运行代码。PYNQ 采集、DMA 与硬件安全约定仍服务于最终方案，不因电脑呈现而整目录删除。
- 选择能回答当前问题的最便宜验证：静态/语法 → host 回放或单元检查 → ARM 编译/链接 → 必要的板端运行。没有新增风险就不重复旧测试；不默认运行 Vivado、OOC、完整实现或全量日志扫描。
- 本地源码、文档、host/ARM 定向检查属于当前任务范围。UART/JTAG/SSH 连接、下载/复位/烧录、SD 写入、服务改动、真实板端运行、Vivado 完整构建和 BIT/HWH/XSA 导出需要用户在当前任务明确授权；获得授权后一次性完成直接相关步骤，不为每个命令重复询问，也不自动扩大范围。
- 同一问题连续两次没有新信息就停止该路径，保留失败原因并给出最小下一步；不靠换入口、改阈值或生成更多报告来伪造通过。
- 只在状态、阻塞或下一步实际变化时更新 `PROJECT_STATE.md`。除非用户要求或调试确实需要，不新建 REVIEW、审计、总结、交接或重复 JSON 报告；最终用简短文字说明改动、验证、阻塞和下一步。
- 离线、host、ARM、板端结果分开表述；模拟画面、旧制品和单模块通过不能写成实时摄像头或完整游戏通过。

### Windows Vivado/JTAG 主机固定规则

- Codex 沙箱下不要直接调用安装目录的 `vivado.bat`：其 `pushd "%~dp0"` 会因外部目录切换被拒绝。使用 `color_test/tools/vivado_nocd.bat`，不修改 Vivado 安装目录。
- `hw_server.exe` 与 Vivado 的本机 TCP 连接使用同一个获准的提升权限上下文。普通权限出现 `WinError 10013` 时只提升当前硬件命令，不修改全局 ACL、注册表或防火墙。
- 3121 只允许一个 `hw_server.exe`。启动前检查监听 PID 和完整进程路径；匹配的现有服务直接复用。只有用户授权停止确认路径为 `hw_server.exe` 的遗留实例后，才启动一个受控服务，禁止让 Vivado 自动再拉起第二实例。
- JTAG 排障先做只读 target/device 枚举，再做最小 PL-only 下载并读回 DONE/EOS/CRC；不初始化 PS、不下载 ELF、不写 SD。完整流程和实测证据见 [`color_test/tools/README.md`](color_test/tools/README.md)。

### JTAG/板端调试会话清理协议

- 每次 JTAG、UART 或板端实测开始前，先读取本次 `/proc/sys/kernel/random/boot_id`，不得复用旧脚本中的 boot UUID；执行一次 `sudo -n true` 准入检查，失败时只刷新一次已授权 sudo 会话。
- 先清点并停止上一轮留下的菜单/采集服务和进程：`live_display.el`、`capture_worker.py`、旧的 `ray-game-*` 单元，以及任何仍持有 `/dev/mem`、`/dev/xlnk` 或 CMA 映射的所有者。停止后确认目标 DMA 已 HALTED、RS=0、错误位为 0、摄像头 GPIO 回到安全值，再开始下一轮。
- 每轮运行使用唯一的 claim/stem。运行返回、超时或准入失败后，先把 `/run/game_live_camera/capture` 中的 log/result/first-fault 文件取回主机归档；只有确认没有活动所有者，才删除同一轮残留的 claim/log/result，禁止用旧回执覆盖新证据。
- 菜单恢复、实时采集和 JTAG 下载必须分成三个阶段。采集失败后先完成安全停机和证据抓取，再单独恢复菜单；菜单服务确认 inactive、所有者清空后才能再次启动实时采集或 JTAG。
- 每轮准入只读取能回答当前问题的寄存器。发现 `/dev/mem`/PL 访问触发 Bus error 时立即停止扩展 MMIO 快照，保留板卡状态，改用 UART 的 boot/service/process 只读信息；不得把该异常当作摄像头帧故障，也不得在未确认所有权时复位或清错。
- JTAG 临时加载前后保存 boot UUID、BIT/HWH/ELF 哈希、FPGA load 计数和 hw_server PID；下载失败或串口占用时先释放上轮会话，不重复启动第二个 hw_server，不重复使用未完成运行窗口。
- 调试证据必须按轮次保存到 `output/build/game_app/`，主机归档完成后才允许清理板端临时文件。未触发场景的窗口只记为 NOT_RUN，不得作为摄像头失败或通过。

## 技能使用

- `skill/ray-game-integration/SKILL.md`：处理固定逻辑光源、Portal 多标签精确定位、有效边界、防抖、同局场景一致性或 Godot 正式接入时使用。
- `skill/pynq-dma-contract/SKILL.md`：仅在 capture/display 缓冲、cache、stride、所有权或安全退出是当前问题时使用。
- `skill/stream-perf-analysis/SKILL.md`：仅在实时帧率、处理延迟、新鲜度或遮挡保持期需要已有日志分析时使用。
- `skill/fpga-verification-gates/SKILL.md`：仅在 PL/RTL、AXI、Bayer、时序/CDC 或制品同源性直接阻塞当前闭环时使用。
- `skill/xilinx-project-flow/SKILL.md`：仅处理实际 Vivado/Vitis/XSCT、制品交接或板端工具链阶段；纯定位、配置与电脑美术任务不默认进入该技能。
- 技能默认给出短结论和最小下一步，不自动生成独立报告，不要求填满模板，不替代 `PROJECT_STATE.md`。

## 代码入口

- 检测与场景：`color_test/software/vision_ps_baremetal/src/vision_ps.*`、`game_scene_adapter.*`、`game_session.*`、`ray_game.*`。
- 稳定与标定：同目录 `vision_stabilizer.*`、`pc_vision/game_scene.py`；权威稳定输出只保留一处，平面/内参标定记录与游戏配置用途分开。
- 调度、输入和显示：同目录 `game_app/loop/pump/input/evdev/linux_io/render/linux_display.*`；目录名 `baremetal` 不表示复制一套 Linux 实现。
- 电脑上位机：`pc_vision/scene_protocol.py`、`native.py` 的 NativeGame 和 `godot/`；普通 GameView 为调试显示，Godot 美术预览尚须正式会话桥接。
- 配置：游戏手工配置仅 `pc_vision/game_config.json`，派生配置使用已有生成器；标签打印记录不另作运行配置，校准文件保留其测量数据身份。
- 采集、制品和打包：`pynq_vision/` 现有入口；PL 仅改动与实时采集或显示闭环直接相关的规范源。
