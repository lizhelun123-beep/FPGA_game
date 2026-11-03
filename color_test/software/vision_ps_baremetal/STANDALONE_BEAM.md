# 裸板实景光束测试版

## 2026-10-30 Portal A+B增强、7候选保护与PENDING光线保持（当前version14交付）

当前BOOT：**`color_test/build/beam_standalone/restored_portal_ab_ray_hold_v14_1/output/BOOT.BIN`**，2294992字节，SHA256 `8272b89270c71cd73d5aee56942ecd0747f080dfce8219d532aa36e7b6b86391`。ELF 1009984字节，SHA256 `99f5da42c04e89ee43b8d152c0d4bbba3640dba9b44866027ae93eb32b698f02`。

Portal A 现在与 B 共用径向圆环回退。蓝色或橙色主体仍先经过原 HSV、面积、长宽比和填充率候选；局部圆环还必须满足主体中心颜色、相对亮度、低饱和白色、环带内外对比、向内/向外白色支持和四扇区至少三个支持。完整实心点＋圆环继续优先，径向回退为96可信度，按主体长轴和0.685跨度估计方向；实心白盘、两扇区弧、偏离主体的圆环和第二个独立圆环拒绝。A在环带比例和方向上使用更紧的专用门槛，避免把单独实心点当圆环。

检测器最多可报告16个原始候选。出现7个候选时，重复 Portal A/B 身份进入`INVALID_GEOMETRY`，不会再触发旧的`BAD_ARGUMENT → BEAM_SAFE_STOP`关屏路径。HDMI启动后仍保持显示 DMA 扫描；PENDING、歧义、漏检和采集恢复期间，画面使用当前相机帧，光线使用最后确认的完整模型和光路，亮度保持不变，直到下一份有效场景或明确切关/重置。保留光线不更新采集时间，也不作为当前POSE发送；串口只发送当前观测。新的有效帧会把模型和整段光路一起原子替换。

主机验证通过：Portal A/B 8个旋转的3/4断环、实心优先、双环/实心盘/缺环负例，7候选异常，PENDING和60秒后光线像素保持，精确HSV、GameBeam/ray/timed77、显示重叠和642项三槽 DMA 恢复。Vitis/XSCT2023.1用`-baseline live -tag restored_portal_ab_ray_hold_v14_1 -boot 1`生成，ARM/EABI/DDR/符号/无加载器和BOOT三分区逐字节校验通过，证据在同目录`verification.json`。XSA、BIT、FSBL、生成配置与上一版 ray-hold 固件相同；本轮未连接真实板卡/UART/JTAG、未写SD，实际识别和频闪效果待上板验证。

## 2026-10-30 持续显示并保持光线（上一版version14）

当前BOOT：**`color_test/build/beam_standalone/restored_portal_b_ray_hold_v14_1/output/BOOT.BIN`**，2294992字节，SHA256 `f54199be8589ad77e3e15517cffa3caa89c9e2947fa3a571ebdb8ca7bad8c0f1`。ELF 1008784字节，SHA256 `d25369990649b1e16972b1bacd62cf4b1af4730b65e0954194c0a0959bea2e31`。仍为version14，启动标记为`display_policy=continuous_recover_ray_hold`和`BEAM_HOLD frame=current_camera invalid_scene=last_confirmed_ray brightness=constant timeout=until_next_valid`。

上一版在PENDING或无效输入时主动清空光段，导致确认/待确认交替时光线频闪。本版继续更新当前相机画面，同时从原GameBeam提交缓存保留最后确认的整份模型和光线，亮度不变，等待下一份有效结果整体替换。板端此显示路径不再因旧6s保持期到期而清线；切关、重置仍清理上一会话。画面显示`CAM`当前采集序号与`RAY CURRENT/STALE`光路原始序号和年龄，保持时的光路对应上次确认的位置。保留显示不刷新采集时间，`valid=0/display_stale=1/success=0`；串口单独发送当前真实观测，无效帧不携带旧姿态。共享核心供其他调用者使用的有界显示API仍保留原6s规则。

显示DMA继续正常扫描和三槽交接，故障恢复期间继续输出最后完整提交的画面与光线；正常采集恢复后继续更新相机图和确认结果。沿用上一版不主动停止/释放MM2S、仅恢复采集侧的逻辑。Portal B径向识别、B350、v3协议以及XSA/BIT/FSBL/生成板端配置保持原字节身份。

主机回归通过：PENDING/重复候选/长时间无有效输入期间光线全幅渲染像素与亮度一致，60s后仍保留原始光路时间戳，新的确认结果整体更新，同代次切关和重置不泄漏旧光路；精确HSV、Portal B正负例、GameBeam/ray/timed77、642项假平台显示恢复检查通过。Vitis/XSCT2023.1使用`-baseline live -tag restored_portal_b_ray_hold_v14_1 -boot 1`完成ARM编译/链接及BOOT三分区逐字节校验，同输出目录`verification.json`记录制品身份。本轮未运行真实摄像头/HDMI、未连接UART/JTAG、未写SD；实际频闪消除效果待用户上板验证。

## 2026-10-30 持续显示与自动恢复（上一版version14）

上一版BOOT：**`color_test/build/beam_standalone/restored_portal_b_live_display_v14_2/output/BOOT.BIN`**，2294992字节，SHA256 `6887b2b950d1f4debb35a644fce0cd8055b8f8a1c916f8d0799db58f568ab024`。ELF 1007948字节，SHA256 `3c1da63cf44524c622c3a66461ae22206130dd5f2a16526f59251418a6704eb8`。仍为version14、二进制协议v3、Portal B径向3/4扇区回退和B支持间隔350ms；未修改PL、XSA、BIT、FSBL或板端生成配置。

黑屏根因不是电脑端时间门槛。实际UART日志多次出现第6个原始检测候选：`count=6 -> GAME_BEAM_BAD_ARGUMENT -> BEAM_SAFE_STOP`，随后旧代码主动执行显示停止并确认`display_released=1`。现在检测器仍可完整报告候选，不做静默截断；超过五类唯一物体或重复Portal B按场景歧义`INVALID_GEOMETRY`处理，不再成为致命参数错误。

HDMI启动后，Standalone路径不再调用显示停止或所有者释放。识别歧义、PENDING、短时漏检或其他无效输入时，继续提交当前相机帧，只隐藏旧模型和旧光线；不冻结旧相机图，也不拿旧姿态冒充有效输入。后续任一帧恢复有效后，正常模型与光路自动继续。显示退休读回/超时时，仅在MM2S寄存器仍为RUN且无错误时恢复软件观察器，并重新完成原双START退休证明；不halt、reset、重新配置、关闭输出、释放缓冲或提前复用帧槽。其他主循环异常只安全停止/重启采集S2MM和传感器，MM2S/VTC/时钟/三槽继续运行。若显示DMA自身发生真实硬件故障，软件不能保证物理扫描仍正常，但本路径不会主动把它停掉，而是保留资源等待恢复。

严格主机回归通过，包括全16777216 RGB精确HSV、Portal B正负例、6候选非致命歧义、GameBeam/ray/timed77、显示重叠，以及642项三槽假平台恢复检查：退休超时后仍只有一次配置、无output-off、无release，恢复双START后可继续提交。Vitis/XSCT2023.1以新标签重编译ARM应用和BOOT；ARM hard-float/DDR/持续显示恢复符号/启动策略标记/无动态加载及三个分区逐字节验证通过，证据为同输出目录`verification.json`。XSA、BIT、FSBL和`game_beam_config.c`与上一版Portal B径向BOOT逐文件同哈希。本轮未运行Vivado、未连接板卡/UART/JTAG、未写SD；真实屏幕持续显示和故障恢复仍待用户上板验证。`restored_portal_b_live_display_v14_1`为旧验证器拦下的保留候选，交付只使用`_v14_2`。

启动时应看到`BEAM_RELEASE ... display_policy=continuous_recover`和`BEAM_HOLD frame=current_camera invalid_scene=no_old_geometry ... fault_policy=continue_and_recover_scanout_never_stop`。

## 2026-10-30 Portal B径向圆环增强（上一版version14）

上一版BOOT：**`color_test/build/beam_standalone/restored_portal_b_radial_v14_2/output/BOOT.BIN`**，2294992字节，SHA256 `2efbea6a551bbf33aa760e3a6e74e2721a3df45c3371af36be4ab2c1a1a9eb84`。ELF 1006100字节，SHA256 `7d53404b4e14ac63f4760dea5008ed6f5c97d54aa7c2a83726a6b347baa72ea9`。保持启动标识`BEAM_DIAGNOSTICS version=14`、二进制协议v3、B支持间隔350ms和原PC准入；新增启动字段`b_ring=radial3of4 b_ring_s_max=80 b_span_ratio_x1000=685`。

仍由原橙色HSV、面积、长宽比和填充率先锁定Portal B主体，未放宽橙色阈值。原实心点+圆环连通组件配对继续优先并发布100可信度；仅当该严格路径失败时，B可在主体归一化两端区内使用96可信度径向回退。回退以主体中位亮度建立局部白色V门槛，只在S<=80且内圆橙色占比>=50%、环带白色明显高于中心、四扇区至少3个有支持时成立。两扇区/半圆弧、实心白盘、非橙色中心、第二个独立合格圆环均拒绝。方向仍为solid->ring；缺失实心点时由圆环侧选择橙色主体有向长轴，按`0.685*body_length`估计跨度并取两标记中点。

主机严格回归通过：全16777216 RGB的精确HSV、8个旋转的断环正例、两扇区/实心盘/非橙中心/双圆环负例、Portal A不回退、两个B主体保持歧义拒绝，以及既有GameBeam/ray/timed77/显示退休检查。三张既有HDMI/屏幕参考仍由原严格实心点+圆环路径识别A/B。Vitis/XSCT2023.1以`-baseline live -tag restored_portal_b_radial_v14_2 -boot 1`只重编译ARM应用并打包；XSA、BIT、FSBL及生成配置与原version14冻结输入逐文件同哈希，ARM/EABI/DDR/符号/无动态加载和FSBL+BIT+ELF三分区逐字节校验通过，证据为同输出目录`verification.json`。未运行Vivado、未连接板卡/UART/JTAG、未写SD；真实摄像头断环识别和连续稳定性仍待用户上板验证。`restored_portal_b_radial_v14_1`是收紧唯一圆环规则前保留的构建候选，不是当前交付。

## 2026-10-28 二进制协议v3（version14历史基线）

当前BOOT：**`color_test/build/beam_standalone/restored_binary_v3_1/output/BOOT.BIN`**，2278608字节，SHA256 `4abcf689a6fc933c946851915aceaaca7850e7e457a930c66f098f5229b5fe88`。ELF978496字节，SHA256 `1fe1fd1ad758c2e2c6be676f38e437e3272782fbc7aa18c575e4316e09e76479`。启动标识`BEAM_DIAGNOSTICS version=14`、`BEAM_POSE protocol=3`与`wire=COBS_CRC32`。与PC build `20261028-binary-v3-5`（Godot/网页共享）成对更新，旧v13固件/旧电脑不能识别新协议。

v3升级全部控制/校时/姿态帧；新`beam_wire_protocol.*`有界COBS/CRC32解析，命令<=64字节。原BeamControlState、显示READY栅栏、原始相机时序、B350、Portal修正/出口、恒亮保持及DMA所有权流程保留；无效观测不携带旧姿态。内部原ASCII控制状态表示在发送前转换为二进制，UART输入只接收v3。校时新增板端处理请求/开始回复时戳，不声称已缩短整帧轮询等待。字段/误差界见[协议说明](../../../pc_vision/SERIAL_PROTOCOL.md)。

使用既有Vitis2023.1：`build_game_beam.tcl -baseline live -tag restored_binary_v3_1 -boot 1`，复用frozen-live12平台/FSBL/BIT。严格ARM/EABI/DDR/新协议符号/三BOOT分区逐字节校验通过；日志`output/build/game_app/restored_binary_v3_1_build.log`，身份与分区证据为同输出目录`verification.json`。35项主机检查（含二进制交叉/边界/破坏恢复，环回单项因沙箱10013在获准作用域复核通过）、8项网页、Godot检查通过。940份旧原始日志的量化重放无判定差异。这些不代替新BOOT的板端实时验证。

用户复制上述BOOT至SD并启动板卡，关闭旧后台/串口助手后，启动配套Godot或网页程序。正式运行期间只保留一个串口所有者。本轮未连接真实UART、复位、下载或写SD；未运行Vivado，不改相机/PL/DMA，实际吞吐及握手待用户上板。

## 2026-10-28 整合版与上位机调度修正（历史version13）

后续电脑持续显示版为`20261028-continuous-scene-3`：运行中保留上一份完整实测场景，手部遮挡/等待更新不先清屏，新完整场景原子替换；PC立即唤醒/最长10ms轮询。此改动只更新上位机，继续使用本节同一version13 BOOT，板端识别、防抖和保持规则不变，详情见[上位机说明](../../../pc_vision/godot/README.md)。

当前BOOT：**`color_test/build/beam_standalone/restored_integrated_1/output/BOOT.BIN`**，2278608字节，SHA256 `1bfa1e024cdec4cb180b6da24ff1618d3f67b033f30e85e00a474902484af855`。ELF960036字节，SHA256 `8c33dd3971c4127e7c43fec7c73db24674720e00e0b864812925bf7ea5aba8a7`。保留version12低饱和Portal/偏色白标记修正、B350、最后确认画面恒亮保持、全部选关握手及DMA契约；本轮板端只更新启动版本/整合标识，串口调度与超时修正位于电脑端。

启动标识：`BEAM_DIAGNOSTICS version=13`、`BEAM_RELEASE integrated=20261028 portal_profile=low_s_tinted_marks control_protocol=2`，以及既有BEAM_CONTROL/BEAM_PORTAL行。使用Vitis2023.1既有`build_game_beam.tcl -baseline live -tag restored_integrated_1 -boot 1`，复用同一frozen-live12平台/FSBL/BIT；未运行Vivado。严格ARM编译/链接、EABI/DDR/控制符号与三个BOOT分区逐字节检查通过。日志：`output/build/game_app/restored_integrated_1_build.log`；制品身份与分区检查：同输出目录`verification.json`。

上位机build为`20261028-serial-priority-2`：LEVEL2/START2/RESET2优先于周期SYNC2，已在途校时最多等待1500ms后让出；控制超时从完整写入实际完成时刻起计算2秒、最多发送3次。保留CRC/关卡/代次/nonce/光源回显核对及READY后解锁，不强制启用开始。新增实际TX/RX字节JSONL日志。主机21项定向测试、C桥接检查、Python语法和Godot15关/按钮/原子姿态检查通过。

用户确认此前COM9有界检查时板卡没有启动；该轮发送LEVEL2三次/SYNC2六次、零字节接收、未发START2，证据为`output/build/game_app/pc_handshake_com9_20261028_1.jsonl`，不能作为通电后的握手通过或失败。本轮不再打开串口或操作板卡/SD。用户复制上述BOOT并启动板卡后，关闭XCOM等串口助手，再从仓库根目录执行 `& .\pc_vision\start_game.ps1 -SerialPort COM9`；日志自动写入`pc_vision/output/serial/`。选关后光源更新并收到READY2才可开始，按开始后收到STARTED2才计时与传姿态；实际闭环仍待上板。详情见[上位机说明](../../../pc_vision/godot/README.md)。

## 2026-10-28 Portal低饱和主体与偏色白标记（历史version12）

新BOOT为 **`color_test/build/beam_standalone/restored_portal_saturation_1/output/BOOT.BIN`**，2278608字节，SHA256 `c7128ee66fd735fbe3ee4966e15abf96416dcbf7e3c8a00f7f67ef9917d5da85`。ELF960072字节，SHA256 `727efa7ea6255604b1956c1061bc9890e4588b55218668d44f425c56466b4888`。只交付本路径，保留version11串口握手、B350、恒亮同帧保持与既有DMA退出契约。

用户2e48日志的24个采样帧中A仅1次接受、22次主体几何拒绝，B/Mirror/Target均24次接受；aa45日志9个采样帧A全部拒绝、B接受8次，多次INPUT_OK仅含一个B。两段采集间隔218..260ms，未证明存在B350超限。实际v10与v11的检测/稳定器/光路编译对象一致，提交/保持/绘制及capture/display函数机器码相同；本次不是切错检测工程，而是原条件未覆盖新场景。05-56截图为4298、文本到4280，不能称精确同帧。

修正只在restored：蓝色候选S下限40→25以恢复低饱和主体；Portal ROI局部白S上限65优先，若其白掩码与淡色高光主体粘连导致完整标记验证失败，再用原严格40验证。两次均要求原有实心点/有色中心圆环、尺寸关系、位置、对齐、有限跨度和歧义检查；全局白/WALL阈值不变。不延长B支持间隔，不用旧姿态当有效输入，不伪造传送光段。

启动应见 `BEAM_DIAGNOSTICS version=12`、既有BEAM_CONTROL行，以及 `BEAM_PORTAL ... blue_s_min=25 local_white_s_max=65 strict_retry=40`。第一张新照片回放从2物体变为现场4物体，第二张从仅B变为A+B；六张参考分别保持5/5/3/2/4/2实际物体，均求出2段光路及一次传送。所有图保留既有叠加，不是原始相机回放或实板通过。严格MSVC低S/偏色标记8方向、缺环/双实心/彩色标记/灰主体负例、高光严格回退、既有1824Portal入口/核心/timed75/显示UARTHSV检查及20输入+9配置检查通过。

ARM/EABI/DDR/控制符号/无动态加载/无AprilTag与三个BOOT分区逐字节校验通过。构建日志`output/build/game_app/restored_portal_saturation_1_build.log`，制品核对在同输出目录`verification.json`；host日志`output/build/game_app/restored_portal_saturation_host.log`，六图断言回放`output/build/game_app/portal_user_20261028/replay.log`。本次未连接UART/硬件、运行板卡或写SD。用户复制新BOOT后检查version12及连续帧：放稳四物体时raw/support应为0f，单独两个Portal应为06，并检查A/B接受和传送光段；实际稳定性仍待上板。

## 2026-10-28 上位机选关与光源握手（历史version11）

在version10 Portal局部修正版上接入串口控制；原restored检测、B350ms、最后确认画面恒亮保持及DMA所有者/退休规则继续使用同一实现。新BOOT为 **`color_test/build/beam_standalone/restored_pc_handshake_3/output/BOOT.BIN`**，2278608字节，SHA256 `9764b6a9899d78bfa3177ff8d8c6f30c19cb64114f94fee78568e7cd2372e36e`。ELF961140字节，SHA256 `4b1a0400003366f3a5413340c0edf44c792a7305879d7c6ff5710b2cc9746595`。启动应见 `BEAM_DIAGNOSTICS version=11` 及 `BEAM_CONTROL protocol=2 commands=LEVEL2,START2,RESET2 ready=READY2 started=STARTED2 pose_gate=START2`。version10及更旧BOOT保留作历史参考。

板端开机仍采集/绘制默认(32,500)光源，准备期间不输出POSE2。收到CRC有效的LEVEL2后在帧边界更新光源、清除旧场景历史；新画面完整提交并通过既有双START退休栅栏后才回READY2。收到相同关卡代次/nonce的START2才回复STARTED2并放行后续POSE2；RESET2关闭姿态流。重发LEVEL2/START2只重放确认，不重新清空运行状态。PC代次仅识别命令，相机原generation/sequence/captured_ms不改写。LEVEL2采用29字节小端结构`<BQiiiiI`的Base64+CRC32行，总长59字节；同一串口所有者一次只发送一条待确认命令，适配64字节RX FIFO。响应仍为有界ASCII行。字段/电脑操作详见[Godot说明](../../../pc_vision/godot/README.md)。

严格host C测试覆盖光源更新、显示栅栏后READY、开始前姿态关闭、过早START拒绝、重复命令、切关/菜单关闭、PC重启nonce和原始相机标记；Python→C→Python验证紧凑命令/CRC/极值字段。Godot检查覆盖15关内容、按钮准备状态、整帧替换、UTF8、结算；PC测试覆盖时钟/旧帧准入、计时、重连。ARM编译/链接、控制符号、EABI/DDR/无动态加载/无AprilTag和三个BOOT分区逐字节校验通过。构建日志`output/build/game_app/restored_pc_handshake_3_build.log`，制品检查为同输出目录`verification.json`；`restored_pc_handshake_1`保留首次严格编译警告失败记录，`_2`为串口stdio边界flush完善前的中间版本，只交付`_3`。

本次未连接串口/硬件、运行板卡或写SD。用户复制本BOOT后，关闭占用端口的终端并启动上位机，检查选关后HDMI光源改变且开始按钮解锁，按开始后才出现POSE2和虚拟物块更新；切关时重新握手。实际串口/光源刷新/摄像头闭环仍为NOT_BOARD_VERIFIED。电脑完整游戏250ms新鲜度不放宽；板端约300ms采集间隔及实际端到端帧龄仍需实测。当前同步发射条件和姿态，不包含PC权威光段/结算回传，HDMI诊断光路与PC游戏不宣称完全相同。

## 2026-10-28 Portal A/B局部标记与姿态修正（历史version10）

用户反馈Portal A命中中点时较容易传送、偏离中点时常失败。附件串口记录中Portal A多次通过几何却没有标记接受，且没有任何A/B同时接受帧；离线回放两张新截图确认局部白点/圆环亮度低于全局白阈值，主体倾斜时单独PCA中心也会偏离有效入口。此次只修正restored Portal局部识别与姿态，不改变全局白色/WALL阈值、B防抖、固定光源或光路规则。

Portal局部ROI现在使用相对主体的低饱和白标记条件；白点/圆环仍必须满足solid→ring顺序、相对长轴位置、面积比、对齐和歧义拒绝。接受后Portal中心和轴由两端标记的联合中点及solid→ring轴确定，物体长宽仍由主体几何计算。这样入口沿Portal长边移动时不会因主体PCA偏移而被错误地挤到中点；Portal B单向出口仍按JSON的solid→ring正法向。

离线验证：四张截图分别识别5/5/3/2个实际物体；两张新截图均接受Portal A/B，原始求解器各产生2段光路并包含一次传送。主机测试覆盖低V白标记、8种朝向、褪色主体、缺环/双实心负例，以及1824个Portal B长边入口/两侧/切向组合。该结果是主机回放和静态制品验证，不等于实时板端识别。

复制 **`color_test/build/beam_standalone/restored_portal_local_1/output/BOOT.BIN`** 到SD启动分区根目录。大小 **2278608字节**，SHA256 `2cfe709b96a12f1532e83a7050dade536cc39d041fe68d7c34c8f298ec82a965`。ELF大小928172字节，SHA256 `c257baf6af2c97557171a605679d3edc513c3e06696b87559e1a139658ca6742`。启动应见`BEAM_DIAGNOSTICS version=10`、`BEAM_PORTAL white=local_body_relative_v pose=solid_ring_midpoint_axis entry=finite_long_sides`和既有`BEAM_HOLD brightness=constant`。ARM/EABI/DDR/无加载器/无AprilTag及三个BOOT分区校验通过；日志为`output/build/game_app/restored_portal_local_1_build.log`，核对见同输出目录`verification.json`。

本次未连接硬件/串口或写SD。上板后请返回version10启动行、同一时段的`BEAM_DETECT`（尤其`geom_a/mark_a/accept_a`、`geom_b/mark_b/accept_b`）、`BEAM_FRAME`中的raw/supported mask与segments，以及连续POSE2。只有这些实测信息才能判断A偏心命中和Portal传送是否已恢复。

## 2026-10-28 恒亮保持最后确认画面（历史version9）

按用户要求，板端实景等待下一份有效B确认结果时，保持最后一次确认成功的相机原图、模型和完整光路，光线保持原来的亮黄色；STALE与真实旧帧龄继续显示。保留的generation/sequence/captured_ms不刷新，valid=0/success=0，POSE2仍只发当前确认结果。背景继续来自严格匹配旧帧标记的committed_image，模型和光段整体替换。350ms支持间隔和250ms持续移走确认不变；短暂漏检时不再因旧画面年龄达到250ms就清线，而按已有6000ms绝对保持上限等待新结果。6s到期或会话复位清除，真实移走得到新的有效实测子集后正常替换。此决定覆盖下方历史版本的暗色STALE光线与缺失显示250ms上限，不修改电脑游戏新鲜度或DMA条件。

用户2e36c589日志有475个CRC与语义检查通过的POSE2，180OK/292PENDING/3UNAVAILABLE；474个采集间隔241–295ms、中位267ms，全部小于350ms。但有效性切换244次，原显示会随之亮黄/暗黄交替。采样保留画面的年龄可达2635ms，当前输入帧龄仍242–291ms，故屏幕1300ms不能直接认作摄像头停顿。WALL没有有效观测、PortalB多数标记验证失败仍是独立识别问题，本版不改检测。

复制 **`color_test/build/beam_standalone/restored_hold_bright_1/output/BOOT.BIN`** 到SD启动分区根目录。大小 **2278608字节**，SHA256 `15047740f28e673a6fd62ed3027f2d825354b6b2680726162b72f28bd9f7e6bf`。ELF大小926100字节，SHA256 `b6c53c816faaae82ea793a11ad37104d19db87c5615a032e2a97431d3500cbbc`。启动应见`BEAM_DIAGNOSTICS version=9 ... support_gap_ms=350`与`BEAM_HOLD frame=last_confirmed_camera_and_ray brightness=constant timeout_ms=6000 missing_commit_ms=250 timestamps=original`，POSE2仍为协议2。

严格主机检查通过：1300ms观测间隔下B仍重新确认、旧画面和光线全幅像素/行padding保持一致；未确认姿态不泄漏到旧画面；新确认模型/光路一起更新；短暂缺失保持、6s从旧采集戳到期、复位清除均通过。原精确HSV/restored检测/光路/timed75及显示双START/UART检查通过。ARM编译/链接、EABI/DDR/无加载器/无AprilTag、同源live输入与三个BOOT分区逐字节校验通过；350/6000/250生成配置与version9/BEAM_HOLD标志已核对。日志`output/build/game_app/restored_hold_bright_host.log`和`restored_hold_bright_1_build.log`，同输出目录`verification.json`记录制品身份。

本次未连接硬件/串口或写SD，实际防闪效果待用户上板。重点检查CAMERA与STALE交替时光线亮度不再跳变、画面与光路一致、新确认后整体更新；超6s无有效结果仍可能清除。重编译换新tag，例如`-baseline live -tag restored_hold_bright_2 -boot 1`。

## 2026-10-28 B支持间隔350ms（历史version8）

按用户最后指定的350ms，唯一JSON新增`real_scene.beam.stability_support_gap_ms=350`，由生成配置传给同一timed B。GameBeam配置版本升至3；原timed入口仍默认250ms。相邻真实观测间隔**不超过350ms**可继续确认，**351ms**重新确认；仍须至少两次匹配观测，原死区/迟滞/获取与变化确认时间保留。原始采集戳、实际帧龄、物体缺失处理、安全三缓冲/退休/HALTED不变。这次放宽是支持间隔，不是计算提速；电脑完整游戏`scene_max_age_ms=250`与显示明确缺失250ms是独立规则，本次保持。

用户57e71989日志有151个CRC正确的POSE2（sequence5..155），全为PENDING/valid0；138帧raw2f。150个间隔228–318ms、中位266ms；其中132对连续五类齐全帧的间隔253–268ms，全部大于旧250ms。38份周期统计有35份五类、2份四类、1份两类；检测中位98ms（此前143ms），采集/复制140ms。提速有效，但旧B门槛仍阻塞。另发现全部报文missing_mask带已取消实体SOURCE的0x10，虽然CRC正确，PC严格解码仍会拒绝。现GameBeam及POSE2编码仅输出五类物体的缺失位，真实缺失位保留；协议仍为2。

复制 **`color_test/build/beam_standalone/restored_gap350_1/output/BOOT.BIN`** 到SD启动分区根目录。大小 **2278608字节**，SHA256 `bbbf7fe3bd04b70597aa4fc4ead05f0576a4eb9e30b064ad081a20a6e3b8738a`。ELF大小925892字节，SHA256 `ba8a3836393fc901f963bb24a013bf2e695a629631d29436cc3f31949f6b2b3b`。启动应见`BEAM_DIAGNOSTICS version=8 ... stability=B support_gap_ms=350 ...`，以及`BEAM_POSE protocol=2`。上一个fast_1/version7保持250ms，仅供历史对照。

严格主机五类场景验证266/318/350ms间隔能确认并输出完整光段，351ms重采集且无当前有效光段；复位、真实缺失和原始戳检查通过。原250ms/timed75/精确HSV/检测光路/显示UART检查通过；20输入+9配置+4项C编码到Python协议检查通过。ARM编译/链接、EABI/DDR/无加载器/无AprilTag、同源live输入和三个BOOT分区逐字节校验通过。日志`output/build/game_app/restored_gap350_host.log`、`output/build/game_app/restored_gap350_1_build.log`；身份核对见同输出目录`verification.json`。

本次没有连接串口/硬件或写SD。上板后让五类物体保持可见、静止，检查`valid=1`、`supported_mask=2f`、`segments>0`；首帧PENDING仍正常，移动后须重新确认。若继续无光线，返回version8启动行和连续POSE2/BEAM_FRAME/BEAM_FRAME_COST。实物姿态精度、交互和电脑完整游戏准入仍须实测。重编译换新tag，例如`-baseline live -tag restored_gap350_2 -boot 1`。

## 2026-10-28 无光线定位与等价计算加速（历史version7）

用户提供的09c3b0ef串口记录中，64个连续POSE2报文CRC通过；54帧raw_mask=2f，另10帧缺Mirror或PortalA。16份周期BEAM_FRAME中14份检测到五类、2份四类，但全部PENDING、supported_mask=00、segments=0。63个原始采集时间间隔为285–364ms，中位数300ms，全部超过timed B的250ms支持间隔，导致每次重新确认。检测阶段中位数143ms，采集等待/复制128ms；不是继续放宽颜色阈值能解决的问题。复制文本拼接了报文，CRC通过不代表验证了原串口换行边界；候选齐全也不等于物理姿态精度验收。

本版保留下面version6的B+C分割/标记/显示机制，只优化等价计算：restored HSV使用预先生成的24位整数倒数和乘法，替代Cortex-A9逐像素软件除法；Portal两个全分辨率ROI遍历按行扫描，取消逐像素行列除法/取余。全部16777216种8位RGB的H/S/V与原整数除法路径逐项一致，旧profile仍走原路径。未改250ms支持间隔、时间戳、识别阈值、光路或DMA退休条件。启动应见`BEAM_DIAGNOSTICS version=7`，以及`BEAM_PIPELINE ... hsv_division=exact_reciprocal roi_scan=rowwise ...`；POSE2仍为协议2。

此前制品 **`color_test/build/beam_standalone/restored_bc_fast_1/output/BOOT.BIN`** 已由上方version8取代。大小 **2278608字节**，SHA256 `a57e5f39fa2513176cd8b719ddff8a2b63f95407315a828a88ea2ca575296a8b`。ELF大小925160字节，SHA256 `3de64235823d3eee6ff18e516dfe0cddbd661b1a45c88283be3583f95dc325f9`。严格ARM编译/链接、EABI/DDR/无动态加载/无AprilTag、原live制品身份和三个BOOT分区逐字节校验通过。日志`output/build/game_app/restored_bc_fast_1_build.log`，核对`color_test/build/beam_standalone/restored_bc_fast_1/output/verification.json`。Bootgen overlap提示已按保留live基线检查：FSBL/应用执行内存不重叠，BIT目标为PL配置设备。

精确HSV穷举、restored检测/光路/timed B、显示/UART测试及两张屏幕参考回放通过；20项输入与8项配置检查通过。主机日志`output/build/game_app/restored_exact_hsv_row_host.log`。尚未实板测量加速幅度，不能承诺已经低于250ms或恢复交互。本次未连接串口/硬件或写SD。用户替换BOOT后返回启动version7和连续10–20帧POSE2、BEAM_FRAME_COST、BEAM_FRAME，检查实际capture_gap_ms及是否出现supported_mask、valid=1、segments>0。重新构建必须换新tag，如`-baseline live -tag restored_bc_fast_2 -boot 1`。

## 2026-10-28 B+C：38.5cm高度与循环优化（历史version6）

用户已将相机高度从50cm降至38.5cm。固定镜头/平面下约对应1.30倍投影长度、1.69倍面积；这只是尺度检查依据，不是相机标定或毫米换算。当前仍输出1280×720相机像素，虚拟光源(32,500)向右、PortalB局部正法向出口、timed B及其250ms支持间隔不变。

此前制品 **`color_test/build/beam_standalone/restored_bc_2/output/BOOT.BIN`** 已由上方version7取代，保留用于对照。大小 **2278608字节**，SHA256 `4a95188c75e06210858e1a36eca4fc06649d3025348c17854299864fbfd85fc9`。ELF大小924544字节，SHA256 `53c450aece1a8e229275554883ad22b9ed2b618eaa1ea19b059ae68720d0f13e`。严格ARM/EABI/DDR/无动态加载/无AprilTag与FSBL+BIT+应用三个分区逐字节校验PASS；原live12项制品不变。日志 `output/build/game_app/restored_bc_2_build.log`、制品身份 `color_test/build/beam_standalone/restored_bc_2/output/verification.json`。目录restored_bc_1是计数说明修正前的中间制品。

本次修改只启用在restored profile：

- 黄色/橙色/蓝色按两张屏幕参考的低饱和颜色设置候选范围；白色用低S/高V、不限制无意义的近白色色相。身份仍须主体形状、黑端点或白点/白环及相对位置验证。Mirror拒绝小于1800px的碎片。仅依据屏幕参考，不能称作原始相机实测标定。
- 主体使用每4×4块的平均BGR再转HSV，降低单点噪声；Target复用同一份绿色掩码和原圆形几何检查，取消重复全图HSV。因此version6的`mask_g`就是Target的实际输入掩码；旧version5两者不同。
- 修复Portal全分辨率ROI误用320×180采样网格容量的问题。倾斜物块可能超过原57600像素限制，现使用有界512×512容量及独立工作区；仍拒绝超容量、缺失端点、错误圆环/位置或歧义配对。复用ROI第一次计算的颜色/亮度，避免第二次HSV转换。
- WALL白条面积上限由80改为256采样单元；保留条形状、平行/垂直关系、间距、暗走廊和整物体面积门槛，不启用暗色主体兜底。`cand_w`在restored路径表示白条配对候选数。
- 显示改用`game_display_submit/poll`：完整复制并flush/barrier后提交，在下一帧采集的有界等待中轮询同一显示所有者，仍须观察W1C低电平和两个新的START才能退休。pending期间禁止再次提交或复用；错误/超时仍保留缓冲，确认HALTED后才释放。显示padding在prepare初始化后保留，取消每次无用整槽清零。
- 周期诊断存于2048字节有界队列，在采集等待中非阻塞发送；POSE2/SYNC2之前必须完成整条诊断，保持单UART所有者和报文边界。没有丢弃相机帧或延长B支持时间。

启动应见 `BEAM_DIAGNOSTICS version=6`、`BEAM_POSE protocol=2` 和 `BEAM_PIPELINE averaged_shared_HSV=1 display_retirement=overlap_capture two_START=required diagnostics=bounded_queue`。`BEAM_DETECT`增加本帧sequence；`BEAM_FRAME_COST capture_gap_ms`报告原始采集下界时间间隔。`display_ms`现在只计完整复制/flush/提交，退休等待与下一帧capture_wait_copy_ms重叠，不能把它的小数值当作实际显示延迟。`BEAM_DISPLAY phase=queued`表示提交版本，不声称本行打印时已经扫描到HDMI。

严格MSVC检测/光路/timed B测试、8方向与1.30倍尺度合成测试、缺标记拒绝、显示双START/并行等待/超时保留/HALTED释放及UART背压/完整队列测试PASS；20项构建输入+8项配置检查PASS，11项串口上位机软件测试通过（仅本机TCP回环；首次受沙箱10013限制后单项复核通过）。两张HDMI截图经实际C检测器各输出5类物块；图中已有光线保留，这不是原始帧或板端运行验收。复现主机检查：`python -B color_test/software/vision_ps_baremetal/tools/test_restored_scene.py --photo "参考截图路径"`。

本次未连接UART/JTAG、下载/复位、写SD或运行Vivado。用户上板后返回BEAM_PIPELINE及连续POSE2、BEAM_DETECT、BEAM_FRAME、BEAM_FRAME_COST，重点检查raw_mask是否出现2f、B能否提交supported_mask，以及连续capture_gap_ms是否满足250ms。不能仅凭编译/截图宣称帧率、防抖或刷新问题已经实板解决。重编译使用新的tag，例如 `-baseline live -tag restored_bc_3 -boot 1`。

补充历史路径检查：旧`test_green_target`通过；旧六类`test_vision_ps`在当前代码与保存的Git基线dbea5a9中均以相同的“expected six detections, got1;WALL”失败。基线对照位于`output/build/game_app/restored_bc_legacy_baseline_1/`。保留该既有失败，未放宽旧profile场地/标记条件；本次验证结论是上述restored定向检查通过，不是全部历史用例通过。

## 2026-10-27 串口定位/Godot配套制品（历史version5）

沿用下面的 restored_markers 检测、timed B、250ms支持间隔和安全DMA所有者；新增POSE2报文及只读SYNC2时钟应答，不更换PL。实际入口仍是 `game_beam_standalone.c`，不是另一个检测工程。串口从旧raw scene-v1改为发送原B确认后的完整姿态子集；PENDING/缺失/无效帧不携带旧坐标。相机原图和HDMI的有界STALE保留不变。电脑三关游戏只在电脑原C会话计时/判定；板端固定(32,500)测试仍是独立诊断。

本次带检测阶段统计的配套BOOT：`color_test/build/beam_standalone/restored_uart_godot_diag_1/output/BOOT.BIN`，**2278608字节**，SHA256 `28ABCFD6346357202A0CBCDEDADC1B8E74993F7302752B2D37CA879DF3F7E24D`。ELF SHA256 `A93D9BBC3706177CBC9D621FB96EC69003FF7E337D7521F87B467C934501F1D6`。严格ARM编译/链接、EABI/DDR/无AprilTag与三段逐字节BOOT校验PASS；保留完全相同的历史live XSA/BIT/BSP/FSBL。日志 `output/build/game_app/restored_uart_godot_diag_1_build.log`，制品核对 `output/verification.json`。这是诊断制品，不改变POSE2/version5协议、检测阈值、光路或B防抖。

用户复制**本段BOOT**到SD启动分区根目录，启动后应见 `BEAM_DIAGNOSTICS version=5`、`BEAM_POSE protocol=2 confirmed_only=1 ...` 和每秒一次 `BEAM_DETECT ...`。使用步骤见[Godot上位机](../../../pc_vision/godot/README.md)。旧恢复版restored_markers_1没有新的POSE2/SYNC2协议，不能与新上位机配套。Codex没有连接UART/JTAG、下载/复位、写SD或运行板卡，摄像头速度、B确认节奏、实串口和现场交互仍待用户实测。

`BEAM_DETECT` 中 `mask_y/mask_b/mask_o/mask_g/mask_black/mask_white/mask_wall` 是同一帧 4×4 采样网格中的颜色掩码单元数，不是1280×720原始像素数；`cand_m/a/b/t/w` 是通过最小面积后进入几何检查的候选数；`geom_*` 是几何通过数；`mark_*` 是标记或目标形状通过数；`accept_*` 是最终过滤后输出数。`wall_parts/wall_pairs/wall_accept` 分别是 WALL 白条候选、配对尝试和接受数。颜色掩码全为0表示颜色阈值阶段失败；主体掩码有值而 `cand` 为0表示连通域/面积阶段失败；`geom` 有值而 `mark` 为0表示标记阶段失败；`accept` 才会进入 B 防抖和光路。

报文为 `@POSE2:<十六进制LE payload+CRC32>:END\n`，头52字节，最多5个28字节有效物体，共最长404个串口字符。头含版本、有效性、物体数、restored profile、tx序号、u64 generation/sequence/captured_ms/published_ms、1280×720、beam状态和raw/pending/missing掩码；物体含类别/effective标记/保留字段、f32中心/单位轴/有效长宽。维持原START之前保守时间下界，不声称曝光时刻。发送最长100ms有界超时，5物体理论线路占用约35ms（115200/8N1），耗时保留在UART阶段统计，未宣称为零成本或帧率通过。

SYNC2请求为 `@SYNC2:<8位小写十六进制nonce>\n`；应答为 `@SYNC2:<相同nonce>:<板端单调ms>\r\n`。仅在主循环报文边界服务，不复位/修改摄像头或游戏状态。PC保留整个往返时间形成时钟映射区间；5s失效，包含保守时钟漂移裕量。只有整个区间满足完整游戏250ms门槛时才准入，原板端时间和C映射时间分开保存。软件校时没有曝光精度承诺。

重编译必须使用新目录，例如 `build_game_beam.tcl -baseline live -tag restored_uart_godot_3 -boot 1`；现有目录不覆盖。下面是此前恢复版本的说明，标记/安全规则仍适用，旧BOOT路径不再是串口上位机的当前交付。

## 2026-10-27 恢复第一版实景绘制（历史version4，标记规则沿用）

恢复前的全部非忽略源码/文档已经提交到 Git：`636f4e5a659b6e3e9266e54385f753759bf0ce75`。第一版参考提交为 `b206663ec68634ded1d5d6032af98a7e3535b16a`。本次恢复它的旧物块检测与相机原图光路叠加，继续复用当前 Standalone 安全采集/显示所有者与 timed B，未回退 PL 或旧环形指针复制方式。

唯一配置是 `pc_vision/game_config.json` 的 `real_scene.beam`：`detector_profile=restored_markers`，虚拟光源 `(32,500)`、方向 `(1,0)`，无实体 SOURCE。Mirror 黄色主体加两端黑点；Portal A/B 蓝/橙主体加白色实心点和白色圆环；二者都不需要中央白条或 AprilTag。WALL 暗色主体仍须两端白条；Target 保留绿色圆/环。测量标签模板继续保存在 JSON，当前生成器和运行程序不会读取它们作检测或几何依据。旧物块尺寸仍为相机像素预览，不把历史毫米模板套给旧物块；Mirror 采用旧有限反射段比例0.66，转换一次后模型/求交一致。

`portal_b_exit_side=1` 表示 B 从 solid→ring 有向长轴的正法向 `(-axis.y,axis.x)` 垂直向外射出，与从 A 哪侧入射无关；发射起点位于 B 同一侧长边，并保留入口沿长边的位置。白点在左、白环在右时默认向画面下方；B 的白点在下、白环在上时默认向右。旋转 B 会转动出口。改成 `-1` 可选另一侧，`0` 是原配对变换。该可选策略只由本光束会话启用，原 `ray_game_trace`/`ray_game_trace_from_emitter` 保留旧规则。

每次先构成完整 CPU 画面，再交给原三缓冲显示；不提交只恢复相机背景、尚未画完光线的中间帧。B 的死区/迟滞/确认和250ms支持间隔保持。PENDING 时可显示上一份完整相机帧及其光段，最多6s；明确漏检最多250ms，持续移走250ms后采用新的实测子集。这些保持使用旧帧原始序号/时间、暗色光线和 `STALE` 标识，`valid=0`、不继承成功结果，不将旧光路叠在新相机帧上。无新鲜确认时仍可能不产生有效光线；实际帧率和交互需实板验证。

主机检查入口：`python -B color_test/software/vision_ps_baremetal/tools/test_restored_scene.py`（VS2022 MSVC，`/O2 /W4 /WX`）。覆盖无白条识别与缺标记拒绝、底行物体、旋转、B单向出口、原光线规则、B确认/超间隔重新确认，以及保留/超时/复位/原始帧标记。另有20项输入/制品检查和8项配置检查。

构建使用 Vitis/XSCT2023.1：`build_game_beam.tcl -baseline live -tag restored_markers_1 -boot 1`。当前新输出为 `color_test/build/beam_standalone/restored_markers_1/output/BOOT.BIN`；该目录已存在，重编译须换新 `-tag`。入口只编译本次 C 应用，不编译 AprilTag；核对原 live 的 XSA/BIT/BSP/FSBL 后生成新 BOOT。实际产物身份见 `PROJECT_STATE.md` 当前摘要；下文 build3..9 是先前 AprilTag 版本，不能当成本次恢复制品。

本次 BOOT 大小 **2262224字节**，SHA256：`93d45422b1e39df311036977bb0ea79029849798344885cc41d7754ed4455f5e`。严格 ARM 编译/链接、EABI5硬浮点、DDR边界、无动态加载/无AprilTag符号以及 FSBL+BIT+应用三个分区逐字节校验通过。日志为 `output/build/game_app/restored_markers_1_build.log`，制品核对见同输出目录 `verification.json`。Bootgen overlap 提示与原 live 相同，已确认 FSBL/应用执行内存不重叠；BIT分区目标是PL配置，不是可执行DDR。此结论仅为主机编译/制品检查，尚未实板运行。

用户上板时，只把上述恢复版 `BOOT.BIN` 复制到启动 FAT 分区根目录替换原 BOOT；不复制旧 build9/旧 live BOOT，也不需要 Python/素材/ELF。Codex 未写 SD。自行重编译可用：

```powershell
& "$env:XILINX_VITIS\bin\xsct.bat" `
  .\color_test\software\vision_ps_baremetal\tools\build_game_beam.tcl `
  -baseline live -tag restored_markers_2 -boot 1
```

串口新增 `BEAM_PROFILE restored_markers ... portal_b_exit_side=1`、`BEAM_DIAGNOSTICS version=4` 与 `BEAM_DISPLAY sequence/captured_ms/stale/input_sequence`。`BEAM_FRAME` 是当前输入有效性；`BEAM_DISPLAY` 是实际显示版本，二者在 STALE 保留时序号可以不同。`BEAM_FRAME_COST` 分别记录采集复制、检测、UART、提交、渲染和显示，取消旧 tag/quad 计时。实际物块替换、冷启动、摄像头交互、刷新效果均须由用户上板确认；Codex 不连接硬件或写 SD。

## 先前 Standalone/AprilTag 版本记录

2026-10-27 起，当前实景测试改用 Cortex-A9/core0 Standalone。运行链路为：

`FSBL → 匹配 PL → beam_standalone.elf → OV5640 → CSI/VDMA → CPU BGR 副本 → 原检测器/Portal 联合定位 → game_beam → 原图叠加 → HDMI`

光源固定 `(32,500)`，方向 `(1,0)`，画面 1280×720。支持 Mirror、Portal A/B、Wall、Target；无实体 SOURCE、KEY、菜单、关卡、计时或结算。Target 只终止本帧光线，下一帧继续计算。

固定光源位置由 `pc_vision/game_config.json` 的 `real_scene.beam.emitter_point` 生成；串口启动行也直接打印生成配置，避免日志与实际光路分离。

运行不需要 PYNQ、Linux、Python、rootfs、systemd、boot.py 或运行时素材文件。主机 Python 仅用于构建前检查 XSA、从唯一 `pc_vision/game_config.json` 生成 C 数据；板卡只运行 C。旧 Linux 路径保留为历史参考，没有删除或覆盖。

## 历史已生成的 SD 启动文件（build9，非本次恢复）

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
