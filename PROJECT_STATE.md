# Project State

Last updated: 2026-10-24

This file is the current project snapshot. It records conclusions needed by the
next task and intentionally omits command-by-command history.

## Current Goal

- display_decision: User confirms final HDMI1280x720/16:9;1280x800 output is no longer a delivery gate. Existing16:10 panel/EDID facts stay unchanged;preserve aspect ratio. Current800-line logical canvas/assets and720p fitted path are historical implementation;native720 layout/assets/mouse mapping still pending. This decision changes no sensor/CSI mode or test result.
- goal: Offline repair of the camera frame-boundary fault before resuming real075 recognition/pose,hot recovery and longer stability on the existing Linux/nativeC/PL route.
- status: PASS_OFFLINE_LLP_FRAME_BOUNDARY_FIX_NOT_BUILT_OR_BOARD_QUALIFIED. One canonical LLP revision;old-source counterexample reproduced and fixed. Two continuous1280x720 frames plus three existing full-frame/reset recovery cases pass. No new production build or board operation;075 real detection remains unmeasured.
- sd_assets: output/sd_card/ray_game_assets.zip and ray_game_assets/;sd_manifest.json is the file/shape-source record. Existing board-used game_assets.bin unchanged(SHA2567e2d4801073c09ee0f2d39ae8a44d31495052fa13e5c42dd377e283b33030d8c);289 poses+1280x800 background. Exported transparent PNGs/background BGR;existing C draws dynamic UI.
- sd_validation: output/sd_card/verification.json;user copy at E:/ray_game_assets verified:all297 file sizes/SHA256 match,no missing/mismatched/extra files. Original format/geometry/ZIP checks PASS. Agent only read SD;no board operation. Five photo class references recorded;WALL absent from sample_photo001..077,existing canonical wall art retained without photo-acceptance claim.
- photo_scope: user narrowed acceptance to correct display of075/076/077 categories/positions/orientations/rays;solved/unsolved is not acceptance criterion. Same C detector/adapter/rules;no photo background or START bypass.
- photo_evidence: output/build/game_app/photo_levels_1/review.json;board/operation_result.json,visual_confirmation.json. ARM/host compile and97 real-photo/core checks PASS;default menu hash unchanged. Board075/076/077 counts3/4/5 and full effective models/rays match host within0.001 printed units;user confirms all3 positions/orientations/rays correct.
- photo_board: same boot687f9d0c/current BIT reused,0 new loads. One configured90s run actually50.65s;6 level changes/134 submissions. First detector runs207/229/183ms;later251ms>unchanged250ms TTL triggered STOP_NO_RETRY. This does not pass90s stability/full game. No START bypass/TTL extension.
- photo_final: native return1 dueTTL,stop0/owner_can_exit1;independent MM2S CR0x10000/SR0x11001 RUN0/HALTED1/errors0,dynclk0,camera0,no active owner;UART closed. Actual3-store addresses/layout match prior baseline;no global reset/BOOT/service change.
- blocker: New LLP source still needs authorized production timing/CDC/resource gates,new paired artifacts and board validation. Old warm075 SOFLate0x14810 and cold23.335s SOFEarly0x15090 failures remain;the proven offline bug is not yet confirmed as their sole physical cause. No bad frame fed toC;old BIT does not contain this fix.
- evidence: color_test/build/csi_frame_boundary_1/review.json is the offline fix record. Physical failures remain in color_test/build/pl_rate93_production/build_4/review.json and its cited receipts. 0xF4 raw0 remains unusable height evidence(DEBUG12=0);raw samples unchanged.
- fix: LLP queues FS separately,latches SOF with payload,holds stalled sidebands,defers CRC comparison until final registered payload drains,and blocks new headers through completion. Native checksum/catalog/generated-target refresh PASS;generated LLP matches canonical;all2640 HWH parameters match frozen build4. Existing DPHY interburst/CRC-tail source identities7/7 unchanged;its historical regression is reused within its reconstructed-Ref scope.
- safety: requested/current store acknowledgement plus two fresh frame-count START events in free-run mode before old-store reuse;not PARK readback alone. CPU writes only unowned store. Timeout retains all buffers until HALTED.
- memory: actual address readback0x38100000/0x384f4800/0x388e9000;span4147200 per frame,total12441600;HSIZE3840,stride5760,VSIZE720. Matched xlnk cacheable0/noncached mapping and dmb/dsb ordering retained;no cached alias/global reset.
- validation: Capture-only static ARMv7 hard-float owner using existing noncache xlnk allocator compiled;075 effective model centers match retained golden within0.001px;5 directed CSI/one-shot timestamp/ownership tests PASS. Shared-library candidate STOP:requiresGLIBC2.33/2.35;static old-project route retained. Evidence:output/build/game_app/live_camera_1/capture_1/preparation.json.
- board: boot687f9d0c-e8e8-44de-bd01-6589cf2b02c1;one unchanged BIT load,one45s run including6 uninterrupted two-image switches and real mouse menu. User confirmed continuous picture,no obvious tearing/ghosts,cursor and three-level switching normal. Trace logs77 menu frames,2 selections(levels2/3);level1 relies on user observation,not automatic trace coverage.
- performance: full composition average33ms,max43ms. Whole-menu mean1.922 updates/s includes long idle;successive active >=1s telemetry windows showed15-16 frames/window(coarse,not a benchmark). User reported acceptable interaction;no optimization added.
- previous_menu_final_state: native return0/stop0/owner_can_exit1;independent MM2S CR0x10000/SR0x11001 RUN0/HALTED1/errors0;dynclk0,camera reset0,no competing DMA owner,UART closed. Temporary BIT only;BOOT/services unchanged. No VTC access at READY0.
- hardware: Lastconfirmed boot5339b795;bothDMA RS0/HALTED,CSI0/GPIO0/dynclkoff,individualCMArelease/ownerexit0,noactiveowner. Capturestickyfault0x90 preserved. UARTclosed;JTAGtarget/server/manager closed without boardreset;Vivadoexit0. BOOT/SD/kernel/servicesunchanged.
- boundary: stable FCLK1/drain-before-reset;uncertain drain retains buffers and requires verified PS/HP+PL restart. Camera isolated,no scene injection/START bypass. Sampling/CDC/STOP gates unchanged.
- attempts: Historical warm same-cause2STOP and consumed coldload/stream retained. This offline package:1 LLP revision/1 candidate round/3 passing simulations/1 valid old counterexample;entry1,fixture2 and report-parser1 failures retained separately. Native refresh1;0 synth/implementation/paired exports/board operations. TailPark/FrameCnt2 API still never reached on board.
- next: Adapt the existing logical canvas/assets/mouse mapping to final1280x720 offline,without changing scene geometry or camera mode. LLP repair still requires a newly authorized same-source production build/gates/paired artifacts before board qualification. No unchanged hot-branch retry.
- authorization: Latest user confirms final1280x720. This turn records the contract and updates the public snapshot only;no renderer/assets implementation or tests. Hardware pause continues;no production-build/board-test authorization or BOOT/SD/kernel/service changes.

## Retained Goal Context (historical detail; query only)

The following previously accumulated goal context is retained for traceability.
It is not an additional startup reading requirement; use the short Current Goal above and current evidence first.

Deliver the AX7Z020B + AN5641/OV5640 camera-driven, purely virtual Chinese game
on final 1280x720 HDMI, using the existing Linux/PYNQ image and native C/C++.
The first-release contract below and AGENTS.md remain authoritative. Keep two
lanes, 1280x720 RAW10/BGGR and the 15% UI margin. The user confirmed the nominal
configuration identity: AN5641 12 MHz XVCLK, HS140 MHz, 280 Mb/s/lane, byte35 MHz.
This is a source/register-tree calculation, not a physical measurement. Existing
XDC still uses3.571 ns and input0.268/1.518 ns. Coordinated review is complete:
recommended nominal T7.142857ns/UI3.571429ns, input0.535714/3.035714ns with the
same15%UI template; NOT_APPLIED, no receiver admitted. See sampling report section28.
The read-only board check changed no setting; its separately authorized follow-up
applied the existing sensor table in standby. No timing constraint was changed.
External full-PVT/pin guarantees remain UNKNOWN and are not a delivery prerequisite.

**Latest continuation (2026-10-20):** section35 passes the reliable-diagnostic
function and minimal-synthesis structure gates:12102 checks/11 cases,13 report
fixtures; actual one4-stage shared reset chain,0 Critical CDC, synchronous RAM
control and required INITs verified. Common serial clock/real BUFR divide4,
soft/error preservation and direct failure snapshots replace the invalid fixture
assumptions. One carried synthesis is now consumed1/1;3 report-only DCP re-reads
used no resynthesis. All intermediate failures and sections33/34 remain intact.
This is not placed/routed timing, load readiness or receiver admission. PS-pad
pre-opt DRC notices are scoped/reviewed, not waived. Evidence:
`color_test/build/dphy_observer_140/shared_reset_audit/fixture_package/REVIEW.md`.
Recommend one fixed diagnostic implementation, then gated finite board observation
only with explicit authorization. This package ran no implementation/BIT/board
operation; historical full implementations remain2 failed, combined loads0/1.

**Current PL-baseline decision (2026-10-20): STOP CURRENT RX/FIXED ROUTE.**
Existing generated/optimized evidence shows the same BUFIO/BUFR plus data-IDELAY
sampling family, with no evidenced new timing-improvement mechanism. Six LP
IBUF repair the isolated wrapper only; they do not justify another HS-budget
run. Vendor-family2/2 and all historical failures stand. Generation/budget entry
now rejects this route before IP/tool mutation; corrected fixture and artifacts
are retained. No own positive routed budget or accepted replacement exists;
PL baseline remains blocked. No run reopened this stopped design/production route;
the separate legacy control diagnostic below does not qualify it. Decision,
scope and reopening criteria: sampling report section23 and
`color_test/build/dphy_sampling/amd_phy_fixed_probe/fixed_route_stop_manifest.json`.

**Sampling boundary decision (2026-10-20):** user permits offline review of a
calibrated route on the same hardware/pins/input model. For that distinct route,
each declared operating condition must have a verified, reachable setting with
residual margin, selected by an observable calibration procedure that fails
closed. This replaces the single-common-fixed-setting criterion only for the
new calibrated proposal; it accepts no candidate and reopens no stopped run.
The earlier full external-AC evidence-acquisition pass in report section27 remains
CLOSED_NO_RESOURCES; no full-PVT/pin guarantee was obtained. That historical gate
does not prohibit the newly authorized read-only identity/configuration check.
The nominal140 MHz decision supplies a concrete clock-model review basis, not
new jitter/skew/eye guarantees or a passing budget. Existing sampling failures,
AUTO non-admission and the Bank13/global3.3V boundary remain. No generation or
production build is authorized by that sampling-route review. Its scope is
separate from the explicitly authorized legacy control initialization below.

**Prior unconnected UART check (2026-10-20):** user confirmed the board was NOT
connected. A scoped COM9 console check enumerated CP210x; the sandbox open was
denied, and its sole outside-sandbox retry opened at115200/8N1 with DTR/RTS false.
Two seconds passive plus six seconds after one CR received zero bytes; no shell
was confirmed and no diagnostic command, device access, reset or PL load followed.
This is NOT_RUN for board/HS-clock measurement, not a receiver failure. Receipt:
`output/build/game_app/sampling_clock_console_20261020.json`. No further open in
that pass. Later source review and user confirmation established the nominal
140 MHz identity above; no physical frequency measurement followed.

**Initial read-only board check (2026-10-20):** user reports power/UART/camera and
JTAG connected, explicitly authorizing environment/artifact/sensor-configuration
inspection only. COM9/115200/8N1, DTR/RTS false, confirmed the xilinx shell.
Boot c4da3153-6ef5-4e83-a6b2-f3c9909def89 runs Linux5.4.0-xilinx-v2020.1,
Python3.6.5; all four boot-file hashes match retained evidence. After private
sudo validation, root metadata and22 read-only PS SLCR/DEVCFG reads passed.
FPGA manager is unknown; bootpy failed importing BaseOverlay before constructing
it. No current-boot load receipt, PL DT node or GPIO claim was observed. Only the
stock PL server's libcma/SCU mapping was selected in the owner snapshot.
FCLK0/1/2 readback is about100/41.667/41.667 MHz, FPGA_RST_CTRL=0 and
LVL_SHFTR_EN=0. The PS/PL control interface is not enabled; no sensor I2C or
unknown PL-register read followed. Current camera mode and physical HS frequency
remain UNKNOWN. COM9 is closed. The read-only audit stops at NOT_READY_FOR_SENSOR_ACCESS,
not a receiver failure. Evidence and the exact one-load/standby-initialization
proposal are `output/build/game_app/pl_baseline_readonly_20261020_review.md/.json`.
No PYNQ/libcma import by this diagnostic, initialization, PL/JTAG operation,
register write, streaming, DMA or build occurred in that initial audit. The user
subsequently approved exactly its one-load/standby proposal; result follows.

**Authorized temporary load and standby initialization (2026-10-20): PASS.**
On the same boot c4da3153-6ef5-4e83-a6b2-f3c9909def89, exactly one Linux FPGA-manager
load of legacy diagnostic BIT a5a88800/HWH dc899d44/XSA03ae58ac completed. Manager
is operating; LVL_SHFTR_EN=0xf, PL resets released, register-derived FCLK0/1/2
about100/142.857/200 MHz. FCLK0/3 and PLL controls were preserved. OV5640 ID56/40
passed on I2C0/0x3c; the unchanged canonical two-lane1280x720 RAW10 table and all
23 selected mode/PLL/format registers matched, ending in standby3008=42.
The post-GPIO-reset raw snapshot had3008=02 and default2592x1944 registers;
it is not evidence of the unobservable pre-reset mode or zero physical output
during reset. The diagnostic never called start() or wrote3008=02. CSI counters
remained0/0; both VDMAs retained CR10002/SR10001, RS0/HALTED1 and no error bits.
GPIO960 remains explicitly owned, output-high; descriptors and COM9 are closed.
The unique firmware staging file was removed, four boot hashes remained equal,
and the final owner snapshot still selected only the stock PL server's SCU/libcma
mapping. PYNQ-server metadata remained empty; kernel FCLK1/2 bookkeeping remains
stale after direct scoped diagnostic setup, so this is not a production binding.
No streaming start, DMA/CMA, HDMI, JTAG, boot/service change, build or production
source edit occurred. Evidence and retained board receipt location are in
`output/build/game_app/pl_baseline_readonly_20261020_review.md/.json`; one-shot
ledger: `output/build/game_app/pl_baseline_standby_20261020_attempt.json`.
This closes control/configuration readiness only. Physical HS frequency,
sampling/lock behavior and production top-level setup/hold remain unqualified.

**Clock/DDR/input-model review (2026-10-20): COMPLETE, NOT_APPLIED.**
HS140MHz means T=50/7ns, UI=25/7ns and byte35MHz. Keeping the inherited15%UI
pin setup/hold assumption gives min=15/28ns, max=85/28ns and a1.071429ns guaranteed
pin interval. Changing only T while retaining0.268/1.518ns would claim a wider,
asymmetric2.321429ns interval; do not adopt that mixed model. Both DDR clock edges,
both data polarities and both lanes remain constrained; current8-call coverage
form is valid. BD FREQ_HZ is separately stale at336MHz. The declaration assumes
nominal50% duty and the15% pin envelope; physical skew/jitter/DCD remain UNKNOWN,
not a renewed prerequisite to obtaining a baseline under the declared model.
Frozen arithmetic over64 complete historical production paths gives worst
S'≈+0.021214ns/H'≈−0.843286ns and common offset width−0.822071ns; this is not new
STA and does not accept the old fixed receiver. Keep speed/hardware unchanged;
AUTO and stopped FIXED remain unadmitted. No production source/XDC/BD change,
Vivado/simulation or board access occurred in this review. Evidence and next
calibration-mechanism gate: sampling report section28 and
`color_test/reports/dphy_clock_model_20261020.json`.

**Display architecture decision (2026-10-19):** PC-prepared 2D backgrounds and
finite-pose sprites -> SD files -> native C resident assets/CPU composition ->
existing display VDMA/HDMI. AGENTS.md now makes this persistent; no default PL
rasterizer, extra DMA, GPU, kernel migration or boot change. Keep the existing
Linux/PYNQ runtime and camera RAW10/BGGR contract.

**Resident-asset checkpoint (prior offline execution):** stage-2 CPU demo loads three
BGR888 assets once, moves one sprite and switches 0/90-degree pre-rendered poses.
Host strict C99, 40 focused file/blit checks, 3 pixel-exact frame comparisons and
the existing 1,540,479 display fake-platform checks pass; menu hash 1f497c09 stays.
Evidence: `output/build/game_app/sprites/verification.json`, `replay.log`,
`preview.png` and `output/build/game_app/game_sprites_host.txt`.
ARM Linux strict syntax and renderer relocatable object also pass; no ARM
execution/link/glibc compatibility claim. SD read/HDMI/board tests NOT_RUN.
Native display still fails closed before device/CMA access. Run/build/board steps
and seven-question retain/simplify/defer review are in the software README's
offline-sprite section. This demo does not change PL or claim game completion.

**Prior display review (2026-10-19, offline):** XSA/member, stored EDID and three
resident-asset hashes rechecked; supplied B-board/core schematics and both panel
PDFs are present and reviewed. No re-upload of these PDFs is needed. Under the
existing 100 MHz integer clock interface, 82.170 MHz has no exact solution;
nearest 82.000 MHz needs sink acceptance evidence. Native binding stays blocked.
Report/locked inputs: `output/build/game_app/display_review_20261019/REVIEW.md`
and `review.json`; no builds/tests/board operations or production-source changes.

**Current result (2026-10-19, authorized board memory diagnostic):** supplied API
script passes on PYNQ 2.6.2. Actual boot-kernel binary is identified by matching
image.ub hash, running GNU Build-ID/config and xlnk/callee addresses. One 4 KiB
cacheable Xlnk allocation, CPU pattern, two sync calls and normal free pass;
strace records allocation/sync/free/shutdown ioctl returns 0, no global reset.
freebuffer alone retains backing ownership; actual free occurs after array GC.
The matched kernel confirms rollback/owner/range/exit gaps; final display DMA
qualification stays false. **Latest user direction: xlnk is PARTIALLY COMPLETE,
NOT THE CURRENT BLOCKER; no further kernel investigation in this task.** Keep
the existing observations for eventual integration, without reopening kernel
provenance, normal tiny allocations or a replacement allocator/driver branch.
Report: `output/build/game_app/pynq_memory_20261019_REVIEW.md`.
No DMA/camera/HDMI/PL/driver/service changes; COM9 closed.

**Latest display decision (2026-10-19):** controller PCB identity is not a gate.
Saved physical EDID declares VIC4 1280x720/60 and native DTD 1280x800/60.
First test 82.000MHz with native 1650x830 timing (59.875867Hz); tolerance is
decided by a valid physical test, not the -0.207% error alone. No fractional clock
work before a valid failed test. Complete modes/report audit and test criteria:
`output/build/game_app/hdmi_compat_20261019/REVIEW.md` and `edid_modes.json`.

**Latest HDMI diagnostic (2026-10-19):** isolated non-project pure-PL RTL now uses
the schematic-verified U18 50MHz reference, integer MMCM 100/410MHz and BUFR/5
82MHz; no PS/DDR/VDMA/camera/Linux dependency. Revised RTL passes two full raster
frames/reset recovery and actual rgb2dvi/UNISIM startup/forwarded-clock simulation.
Two Vivado design runs are retained: first routed but rejected (missing TMDS LOCs,
two CDC-10); second synthesized and passed all nine pin checks, then stopped on
an overbroad reset-PRE cardinality assertion before place/route. The assertion
scope is now corrected offline; current RTL/constraints do NOT have routed STA,
DRC/CDC acceptance or a BIT. No further build is authorized by the retained
two-round limit. Evidence/ledger: `color_test/build/hdmi_colorbars/REVIEW.md`.

**Current Linux-display preparation:** user confirms the old real-scene project
already works with this screen; reuse its rgb2dvi/HDMI path. This is retained
user-reported legacy screen evidence, not a new matched82MHz/current-BIT test.
Existing resident assets now pass an integrated test through actual C read/blit
and display prepare/start/stop on the existing FAKE platform: three pixel-exact
scan buffers, zero DMA padding, CPU/scan separation, timeout retention and
HALTED-before-free. 7,579 integration checks and original1,540,479 lifecycle
checks pass; menu hash1f497c09 is unchanged. ARM Linux strict syntax also passes.
Evidence: `output/build/game_app/display_asset_submission/REVIEW.md` and
`verification.json`. This does not enable the native backend or assert HDMI.

**Native resource progress (2026-10-20):** authorized COM9 inspection and native
ordinary-file testing complete, port closed. Existing display module now has
acquire/close/read/write implementations behind closed qualification. Native
GCC7.3 strict compile/link and2,105 real Linux file/lock/mmap tests pass; strace
shows no /dev/mem/xlnk/uio/dri/fb access. Test bundle cleaned. No assets/EDID
rerun, CMA allocation, PL register access, DMA, PL load/reset or service change.
Fresh boot `b08d5a7b-1a61-4e19-bf22-32644ef2db44`: FPGA Manager unknown;
Linux clk_summary enables only FCLK0 (not proof of physical FCLK1/2 state).
start_pl_server still maps SCU /dev/mem. Current PL/display clock/HP/exclusive
ownership is not established, so no blind PL MMIO. Evidence and source hashes:
`output/build/game_app/display_interfaces_20261020/REVIEW.md` and manifest.

**Offline binding checkpoint (2026-10-20, latest instruction: no board access):**
The existing overlay inspector now emits a display-only JSON without PYNQ import,
extraction or loading. Selected 03ae58ac XSA/member hashes match the retained ZIP
and historical load manifest. Display MM2S is 32-bit-address/64-bit-memory,
24-bit-stream, DRE enabled, three stores; its path reaches PS HP0. All three C
resource bases match HWH, but C maps only the first4KiB of each64KiB IP range.
VTC power-on is1280x720, not the native800-line mode. Nine focused offline tests
pass, including rejected direction/clock/stream/HP mismatches and overwrite guards.
Evidence: `output/build/game_app/display_binding_20261020/REVIEW.md`,
`display_handoff.json`, `pairing.json` and `offline_tests.log`.
Historical load boot afc17ac5 differs from last-observed b08d5a7b; firmware filename/
size and installed PYNQ sources do not identify the currently loaded PL. The
interrupted PYNQ state query was NOT EXECUTED because automatic approval review
was unavailable due to usage limits. No retry or board operation in this offline
continuation. Qualification stays false; native display C is unchanged here.

**Retained display handoff (deferred during the PL-baseline task):** after renewed explicit board authorization, identify the existing loaded/selected display artifact and
Linux clock/reset/HP/exclusive-owner profile, then finish the six remaining
memory/timing callbacks (allocate/release/flush, configure/output/finish).
The four new callbacks have ordinary-file native evidence, not live-MMIO
acceptance; qualify/--display remain closed. xlnk stays PARTIALLY COMPLETE and
NOT current blocker; no new kernel or EDID work. If current PL/clocks need
loading/initialization, specify those changes before execution; connection alone
does not authorize PL download/reset. Retain all sampling/colorbar failure stops.
Production XPR/BD/default selection unchanged; no old BIT acceptance waiver.

**Unique next step:** no further run of this fixed route. Reconsider only after
a concrete, distinct timing-improvement mechanism has applicable device/local
evidence addressing the common-envelope loss and legal reachable setting.
Review that evidence first; renewed authorization alone, LP repair, tap/phase
changes or IP repackaging do not reopen it. No eligible replacement is selected
and no second branch starts automatically. Offline review needs no board.
Sampling remains NOT CLOSED.
Section21's former pending proposal is adopted only within section22's candidate
boundary, not for production. CMT/BUFG3, external-loop and PHASER stops and the
local/PLL1.4095/1.8835ns failures stand. Existing
HDL/XDC/BOOT and historical sensor/CSI/VDMA failure records are retained; the
current memory diagnostic did not recheck those devices. Offline SDK evidence
`output/build/kernel_sdk_20261019/REVIEW.md` remains separate; corrected zocl/full
DMA/frame and the board-native STOPPED2/2 ledger are not reopened here.

## Board Game First Release Contract

These decisions supersede earlier proposals for reset, touch input, a live
camera background and locked levels in the new board-game release. Existing
PC diagnostic controls remain unchanged. The following rows retain the user's
original 1-20 order; they describe requirements/plans, not completed features.

| No. | Confirmed decision / implementation constraint |
| --- | --- |
| 1 | 玩家用手移动真实物体改变场景；鼠标只操作菜单，不拖动虚拟模型。摄像头保留为真实场景输入。 |
| 2 | HDMI 最终显示纯虚拟游戏，不显示摄像头原图或预览窗口。 |
| 3 | 不再要求先补齐真实引脚最坏情况保证；先按现有输入模型完成 PL 工程时序/CDC 基线，再推进静态 HDMI、鼠标、摄像头驱动游戏。保留已知违例与外部 UNKNOWN，不以能显示替代时序检查，也不宣称全温全压生产保证。 |
| 4 | 板卡型号由用户确认为 **AX7Z020B**，不是另一个 AX7020 型号。 |
| 5 | 采用精简 Linux + 板端原生 C/C++ + PL 的路线；先最小启动/外设，再迁移硬件访问，保留已有 C 算法基准。已有 PYNQ 离线适配不等于已通过板端验收。 |
| 6 | 当前电脑磁盘空间不足，且无可用 PetaLinux 构建环境。本机安装不是运行板端 Linux 游戏的前置条件；优先离线评估已有 AX7Z020B Linux/PYNQ 镜像，核对 USB HID、驱动、设备树、时钟及自定义 PL 兼容性。必要的系统定制再评估其他兼容构建主机，不默认本机安装或完整构建。 |
| 7 | 可以专门购买鼠标。首版选择普通有线 USB HID 鼠标，线端为标准长方形 **USB Type-A 公头**，直接插板卡 USB HOST；推荐罗技 B100 的有线 USB-A 版本。 |
| 8 | 用户最新确认最终HDMI输出1280x720、16:9，1280x800不再是交付要求。现有16:10面板及其原生EDID记录仍保留；画面等比显示、不拉伸，最终模式核准沿用已有EDID及720p证据。显示决定不改变OV5640 MIPI模式。 |
| 9 | 用户确认屏幕为 10.1 寸 IPS 非触摸版，普通尺寸 HDMI 输入，使用 Micro-USB 线接 5 V 充电宝独立供电，报告够用；尚无额定电流/负载稳定性实测记录。 |
| 10 | 摄像头保留现有两lane、1280x720 RAW10/BGGR采集，最终虚拟显示采用1280x720；尺寸相同也不合并采集/显示的stride、缓冲或所有权。无需因显示决定修改传感器或CSI，不要求1280x800采集或显示。 |
| 11 | 输入、识别、游戏状态和显示分开调度；显示刷新率、识别更新率和端到端响应分别测量，不假定 Linux 自动解决当前低识别速率。 |
| 12 | 明确 DDR 缓冲所有权、帧序号、缓存/DMA 同步及读写完成条件，证明安全后才能去掉当前复制路径。纯虚拟背景没有必要复制摄像头图像到显示缓冲。 |
| 13 | 模型、光线、关卡代次和成绩属于一致的场景版本，在帧边界整体提交；鼠标光标独立更新，切关后不得接受旧关卡结果。 |
| 14 | 当前最多 6 个模型、同时最多 5 条光线；首版暂按最多 5 个可见光线段规划。三关模板分别含 3/4/5 个物体，本次离线有解光路分别为 2/2/3 段，未触及上述预算。只有手会短暂遮挡物体，正常物体互不遮挡。特效限制在 sample_photo 中灰色、白边框 A3 纸对应的游戏区域。以上上限和 ROI 需集中配置并支持未来升级。 |
| 15 | 先做 BRAM/DDR 预算，采用 DMA 与局部缓存等合适方案。保留 AGENTS.md 的资源余量和分阶段迁移门槛，不以堆高利用率代替性能收益。 |
| 16 | 保留 C 检测器和 ray_game.c 为行为基准，区分原有回归失败与迁移新增失败；不能宣称当前整体回归或实物稳定性已通过。 |
| 17 | 首版 3 关，布局模板依次为 sample_photo/075.png、076.png、077.png，运动权限见下表。用户确认开始前先把允许操作的实物调整到未通关姿态，照片不强制作为已解起始状态。有效光线碰到 TARGET 即通关。允许跳关，不持久化进度，不加重置按钮。用户已确认每关独立倒计时 180 秒，三关不共享时间，各关分别按本关用时评星。 |
| 18 | 中文界面，参考愤怒的小鸟的卡通配色、大按钮、首页/星级结算/选关布局；保留本项目六类模型和光线玩法。选关页只需 3 个可选按钮，无关卡锁。按用时每分钟减一星，最高 3 星；声音不做。具体评分边界见下方实施建议。 |
| 19 | 按前述建议设计自动启动、异常提示、输入拔插和失效恢复；不得用过期/遮挡保留结果触发新通关。需要在后续明确授权的硬件任务中验收。 |
| 20 | 首版期望 5 天交付，用户可全天投入；必须演示板端虚拟游戏界面、模型/光线绘制和 USB 鼠标。先交付基础闭环；按 2026-10-19 最新决定，显示用电脑预制素材和 ARM 二维合成，不默认增加 PL 绘图/特效框架；不能保证未验证的工期、利用率或帧率。 |

### Recognition, Artwork and Layering Decision (2026-10-19)

本次用户确认的要求仅登记为后续实施约束，不表示已完成识别接入、素材生成或图层验收：

- **识别范围：** 限定当前已有的标记识别/定位模式，沿用旧版在实景画面上绘制光线时的
  标记定位及类别、位置、方向语义。虚拟美术不引入无标记识别、新识别模式或额外实体标记；
  继续通过既有场景适配、A3 坐标映射和关卡运动权限驱动模型及光路。
- **模型计划：** 按 `sample_photo/` 中对应实物的外形、类别特征及朝向制作模型美术，
  离线预渲染为二维 Sprite/离散姿态；075/076/077 仍只规定三关布局和既定运动权限。
  美术素材不能改变定位锚点、物理尺寸/求解几何、有效方向或 TARGET 命中规则。
- **静态背景：** 由 Codex 按已确认卡通风格自主生成，供后续 PC 转换、SD 加载和 DDR
  常驻合成使用；最终不显示相机原图。自主生成要求不等于本轮执行素材生成。
- **图层设置：** 默认从底到顶为静态背景 → 模型 → 光线与游戏区域内特效 → 菜单/计时/
  结算 UI → 鼠标光标。透明区域保留下层，光线与模型接触处保持清晰；特效裁剪在映射后
  的 A3 游戏区域内，游戏层不得遮挡菜单/结算或光标。后续素材与合成验收需检查遮挡、
  透明色键/掩码、背景恢复和切关后的图层一致性。

本轮只更新文档，未修改识别/渲染实现，未生成素材，未执行测试、构建或板端操作；
已有显示绑定阻塞、失败账本及唯一下一步保持不变。

### Central Configuration and Spatial Mapping

`pc_vision/game_config.json` is the hand-maintained authority. Its existing
model sizes/physics scale are reused, and `board_game` now defines templates,
permissions, logical bounds, freshness, timer/stars and model/render budgets.
The remaining display/capture/board/UI names below are planning vocabulary,
not a claim that those interfaces or A3 mapping are implemented:

| Proposed key | Initial value / meaning |
| --- | --- |
| display.width / height / refresh_hz | 1280 / 800 / 60 target; exact timing pending EDID |
| capture.width / height | 1280 / 720 retained baseline |
| scene.max_models | 6 |
| render.max_ray_segments | 5 release-scene limit; checked solutions for the three templates use 2/2/3 segments |
| board.paper_width_mm / paper_height_mm | A3 420 / 297, with configurable orientation |
| board.roi_corners / viewport | Pending camera installation/calibration; no invented pixel corners |
| effects.clip_to_board | true; clip effects to the mapped A3 playfield |
| levels.count / game.duration_seconds | 3 / 180 |
| game.timer_scope | per_level; user-confirmed independent 180-second budget for each level |
| scoring.star_threshold_seconds | 60 / 120 / 180 boundaries, measured from the current level's start |
| game.allow_level_skip / reset_enabled | true / false |
| progress.persist / ui.locale / audio.enabled | false / zh-CN / false |

Keep physical-paper coordinates, capture pixels, logical model/physics units
and display pixels explicit. Use calibrated paper corners and a consistent
mapping into the virtual playfield; preserve proportions rather than stretching
A3 to 16:9 or reinterpreting existing model pixels as millimetres. The earlier
80-pixel toolbar + 1280x720 viewport remains a layout proposal, not a user-fixed
pixel layout. The white paper border is an existing ROI reference, not a new
marker requirement. Level photos are references; live installation still needs
valid ROI/calibration data.

Changing software limits within a built renderer's capacity may be runtime
configuration. Raising PL primitive counts, FIFO sizes, BRAM allocation or
pixel throughput beyond synthesized capacity requires RTL parameter changes,
rebuild and verification. A global configuration cannot create hardware
capacity at runtime. Preserve the existing solver's 17-segment safety capacity;
validate the first-release scene against the 5-segment rendering budget rather
than silently truncating physics or reporting a false TARGET hit.

### Three Level Templates and Motion Rules

The following confirmed contract is implemented in the standalone C control
core, not yet wired into the current photo browser/GameController or Linux
board application. The user has
confirmed that these are layout templates: before timed play, manually place
the allowed objects in an unsolved pose. Do not rotate/move objects in software
to invent an initial puzzle, and do not auto-start/auto-clear from a solved
reference photograph.

The user explicitly confirms that 077.png is NOT a correct-answer photograph
and does NOT need to hit TARGET. Preserve it as the third-level layout; a miss
in this reference is not a defect to repair. Do not move its template objects,
change the solver/detector or replace the image to make the reference pass.

| Level | Layout reference | Fixed position and orientation | Rotation only | Free translation and rotation |
| --- | --- | --- | --- | --- |
| 1 | [075.png](sample_photo/075.png) | MIRROR, TARGET | SOURCE | none |
| 2 | [076.png](sample_photo/076.png) | SOURCE, TARGET | none | PORTAL_A, PORTAL_B |
| 3 | [077.png](sample_photo/077.png) | SOURCE, TARGET, PORTAL_A, PORTAL_B | none | MIRROR |

Use the canonical detector's class identities (PORTAL_A/PORTAL_B), not position
or enumeration order, to bind the two portals. Classes absent from a level's
template are not additional playable objects. Represent the three permissions
explicitly in the future canonical level configuration, e.g. fixed,
rotate_only and free; do not encode them as a vague single movable flag.

- fixed: effective center = template anchor, effective axis = template axis.
- rotate_only: effective center = template anchor, effective axis = fresh
  measured orientation. Measured translation, including small incidental hand
  movement, must not move the virtual center or accumulate anchor drift.
- free: effective center and axis both follow the valid measured pose within
  the mapped A3 playfield. Level 3's MIRROR is free, not rotation-only.

First rectify/map the camera pose into the chosen game coordinate system,
then apply the level permissions before position matching/stabilization and
ray construction. Filter only permitted degrees of freedom and keep anchors
exact. The detector may still locate an object internally to estimate its
orientation; its measured center is not a game-position update in rotate_only
mode. Recompute SOURCE tip and MIRROR endpoints from the effective center,
axis and fixed model size. Feed these same effective models to both rendering
and the unchanged C ray solver; never draw at an anchor but trace from the
raw measured center/tip.

Create anchors from the mapped reference layout/calibration and keep them
constant during play. A fresh camera frame must not redefine fixed anchors.
The current photographs are unscaled 1280x720 references, not a completed A3
calibration or hardware-coordinate acceptance. The original physical-game
input/freshness and occlusion rules still apply; do not substitute a solved
template pose for an unseen movable object and thereby trigger a false win.

Recommended preparation flow: select level -> arrange allowed physical objects
-> receive a fresh, valid unsolved effective scene -> explicit start -> timed
play. Preparation does not consume game time. If the effective scene already
hits TARGET, prompt the player to adjust an allowed object before starting.
This is manual setup, not a reset/replay control or automatic physical restore.

Offline reference check using the current canonical C detector and ray solver:
075 has 3 objects and hits MIRROR/TARGET in 2 segments; 076 has 4 objects and
hits PORTAL_A/TARGET in 2 segments. The original 077 has 5 objects and currently
hits PORTAL_A/MIRROR then terminates at BOUNDARY, which is acceptable for this
user-confirmed unsolved layout. A separate offline MIRROR-only adjustment
demonstrated one possible 3-segment solution with all four fixed objects
unchanged. That existence check does not define a required answer pose, an
initial pose or a replacement layout. Level-template acceptance must not
require the original 077 reference to return success=true. Existing detector
test expectations belong to their own regression context; do not silently
rewrite them as part of this level specification. No detector/physics repair
or full regression is claimed.

The focused C session tests now cover fixed-object translation/rotation immunity,
SOURCE-only rotation without center drift (including derived tip), independent
Portal class binding, MIRROR-only movement, missing/duplicate identities,
freshness and generation isolation. These are host results, not live-board
acceptance or evidence that the entire detector regression passes.

### Timer Rules and Occlusion/UI Defaults

The user confirms an independent 180-second budget for EACH level; the three
levels do not share a timer or carry remaining time between them. Each level
is scored from its own elapsed play time:
elapsed <60 s = 3 stars; 60 <= elapsed <120 s = 2; 120 <= elapsed <180 s = 1;
elapsed >=180 s = timeout/failure, 0 stars. Use a monotonic clock and the actual
valid-hit time, not rounded display seconds or render frame counts. A newly
selected level receives its own full budget when explicitly started after
physical preparation. The standalone C session implements these rules; Linux
clock/input and Chinese UI integration remain pending.

Recommended flow: home -> three-button level selection -> physical setup/ready
-> explicit start -> timed play -> success/stars or timeout -> level selection
or next level. Preparation should not consume play time. No reset/replay button
that pretends to restore physical objects. Keep any displayed session stars in
RAM only. Pausing, settings-menu timer behaviour and timeout retry details are
not user-confirmed; a simple first-release proposal is that settings/occlusion
do not pause a running clock and retry returns through level selection.

Handle short hand occlusion with bounded freshness/visibility rules; do not add
a separate hand-detection project. A held or stale scene may support continuity
of presentation but cannot independently produce a new win. Recovery must use
a fresh, valid complete scene. Preserve the existing golden detector and default
dropout behaviour until a focused game-input policy change is implemented and
verified. Any fresh-hit confirmation must have a defined, measured latency.

UI reference images (visual references, not level-start photos or implemented
assets; omit shop/advertising/currency/locked-level mechanics):
- [Home](.codex-remote-attachments/01a14274-5365-7b71-8680-2f6a8db95b8b/2ce66379-629c-4026-832a-99f1240864fb/1-1000061291.jpg)
- [Stars/results](.codex-remote-attachments/01a14274-5365-7b71-8680-2f6a8db95b8b/2ce66379-629c-4026-832a-99f1240864fb/2-1000061293.jpg)
- [Level selection](.codex-remote-attachments/01a14274-5365-7b71-8680-2f6a8db95b8b/2ce66379-629c-4026-832a-99f1240864fb/3-1000061292.jpg)

### Three-Level Control Core (Implemented Offline)

- API: `game_session_init/select/submit/start/tick/snapshot` in existing software
  `src/game_session.h/.c`. Reuses `SceneObject` and unchanged `ray_game_trace`;
  existing `RayGameLevel` remains the diagnostic/bare-metal scene mechanism,
  without imposing its source-lock states on the new timed session.
- Config: extend only `pc_vision/game_config.json`; standard-library-only
  `tools/generate_game_config.py` emits a C table and C/C++ declaration under
  `output/build/game_session/`. Generated tables are not hand-maintained or
  production-source copies. Default anchors were extracted with the current
  canonical C detector and identity plane mapping from unscaled 075/076/077.
  Bounds are 1279 x 719 **uncalibrated preview units**, sizes are existing fixed
  virtual sizes, physics_scale=100. No A3 pixel corners or mm transform exists.
  A future calibrated caller must prepare anchors and observations in the same
  space before session initialization; it must not redefine anchors per frame.
- Flow: select any level -> PREPARING -> explicit start from fresh unsolved
  scene -> RUNNING -> CLEARED/TIMED_OUT. Preparation is untimed; solved input
  reports `GAME_NEED_UNSOLVED`. Each selection clears all geometry, score and
  timer and issues a new generation, including revisiting the same level.
  No reset UI, persistence, audio, pause or hardware access was added.
- Input contract: mapped complete observations, exactly one of every configured
  class, valid measured directions, no held/predicted objects; default maximum
  capture age is **250 ms inclusive**, configurable. Capture times and sequences
  strictly increase within a generation. Use the same externally supplied
  uint64 monotonic millisecond timeline for capture and calls. Stamp generation
  at dispatch; never relabel old asynchronous work with the new generation.
  Missing/duplicate/invalid geometry clears the candidate; replay/old-generation
  frames cannot create a win. A new post-start capture is required. This policy
  is intentionally separate from the unchanged legacy 6 s presentation timeout
  and 0.25 s dropout hold; measured Linux latency may require revisiting the
  new freshness budget, without accepting retained poses as new observations.
- Geometry/output: apply fixed/rotate_only/free after mapping, before tracing;
  regenerate SOURCE tip and use finite MIRROR center/axis/length. One snapshot
  holds the effective models, complete ray, generation and score for rendering.
  The caller serializes updates and commits a copy at its frame boundary.
  Scale adaptation preserves the existing epsilon=0.01, SOURCE offset=0.03 and
  Portal offset=0.01 logical units. Full 17-segment solver storage is retained;
  a separate `render_budget_exceeded` flag reports >5 segments without truncating
  physics or changing the true TARGET result. Rendering must handle that flag.
- Timing: tick even without frames; occlusion never pauses the clock. Timeout
  wins when delivery/tick time reaches 180000 ms; a frame cannot revive timeout
  even if captured before deadline. Before timeout, a fresh hit scores by its
  capture time (not delivery/display rounding). Terminal model/ray/score freeze
  until selection. This is serialized control state, not a thread-safe renderer.
- Verification: C99 `-Wall -Wextra -Werror -pedantic -fsyntax-only` first, then
  focused optimized host C tests using the generated table and actual C solver:
  **261 assertions passed**. A C++ caller also compiled, linked the C core/table
  and ran successfully. The existing PC config loader/defaults and deterministic
  generation check passed. Tests cover the motion/flow/boundary/freshness cases, original 077
  BOUNDARY, and a separate MIRROR-only 3-segment solution. See software README
  for the command. Known WinError 623 affected sandbox native launches; each
  affected command was retried once outside the sandbox and succeeded.
- Standard C adapter/application: `src/game_scene_adapter.h/.c` and
  `src/game_app.h/.c` now connect canonical `VisionDetection[]` through unchanged
  `ray_game_scene_from_detections`, pose mapping and `GameSceneInput` into the
  existing session. Only supplied mapping is explicitly
  `uncalibrated_preview`, calibrated=0, identity; a versioned pose callback
  reserves the real-calibration boundary. Config and mapping spaces must match;
  future calibrated anchors/model units must be prepared before initialization.
  No A3 corners/mm transform, detector, solver or rule implementation was added.
  Permissions, sizes, SOURCE tip and physics scale remain owned by the core.
- Adapter validity: preserve original uint64 capture ms, frame sequence and
  capture/dispatch generation, including invalid results. No delivery-time
  refresh or relabel, no truncation/template completion. SOURCE requires its
  valid directed vector; other classes require finite nonzero axes and upstream
  reliability. Reject unknown classes and invalid axes before legacy conversion
  can substitute WALL/angle. Any retained/predicted pose sets frame.held.
  Invalid new observations reach the core to consume sequence/clear candidates;
  missing/duplicate identities, freshness, old generation and terminal state
  precedence stay in game_session.
- Offline app: select/submit/explicit start/no-input tick and copied snapshot,
  with capture-dispatch stamping and text serialization of the same complete
  model/ray/generation/score version. `tools/game_offline.c` accepts external
  stdin commands and detection rows; no system clock, devices, GUI, auto-start
  or auto-generated pose. `tools/test_game_app.ps1` generates config and builds
  only under `output/build/game_app/`; static C99 gate passed, adapter/app
  **519 assertions** and unchanged three-level core **261 assertions** passed
  with simulated time. Tests use detection-pose fixtures from generated anchors,
  not a new detector/photo acceptance claim. Covers invalid/held/stale/missing/
  duplicate observations, delayed old tasks, no-input timeout, original unsolved
  077 and coherent snapshots re-traced through the canonical solver. Independent
  stdin text replay also passed original 077, >32-bit time/sequence, explicit
  start and no-input timeout; transcript: `output/build/game_app/offline_smoke.txt`.
  Initial
  GCC launch hit the recorded Windows DLL relocation failure; the sole
  infrastructure retry outside sandbox launched successfully. Fixed MinGW's
  non-ISO scanf macro by using standard C strtoull in the text entry.
- Menu/input loop: `src/game_input.h/.c`, `game_evdev.h/.c`, `game_loop.h/.c`
  reuse game_app/session; no new detector, solver, timer, score or motion rules.
  Release on the same pressed button/generation emits one select/start action;
  repeats, drag-in and reconnect-held input cannot activate it. Menu availability
  derives from the latest snapshot. Disconnect cancels a click; reconnect needs
  a release, and neither changes timer policy. Mouse never changes model poses.
  Shared `board_game.menu` JSON layout generates `game_default_menu_layout` for
  future rendering; its 1280x800 pixel canvas is independent of camera/game units
  and does not prove a display mode.
- Every external-time loop step ticks first (including NULL/rejected events),
  processes one event and publishes a complete copied game snapshot plus derived
  menu view. Batch callers serialize events at the same time and publish last.
  Dispatch returns the original uint64 capture/sequence/generation stamp; results
  submit it unchanged, so old tasks cannot replace a selected scene. The existing
  app text serializer now also accepts an already published snapshot copy.
- Evdev seam explicitly decodes little-endian 16-byte records with 32-bit time
  words or 24-byte records with 64-bit time words, independent of Windows structs
  or libc time_t/time64. Target UAPI size/offsets must still be verified. Relative
  motion and left edges remain ordered until SYN_REPORT; repeat value 2 is ignored.
  SYN_DROPPED/queue overflow cancels pending input, discards through the next
  SYN_REPORT, then awaits explicit device-state synchronization. Early recovery
  requests are ignored. This portable decoder performs no Linux syscalls;
  the separately described game_linux_io adapter supplies unexecuted syscall code.
- Existing `game_offline.c` is still the sole offline app entry; it now replays
  pointer/left/connection events, explicit evdev hex records and dispatch stamps
  alongside the original select/start/frame/tick commands. No auto-start, solved
  runtime pose generation or template completion. `test_game_app.ps1` remains the
  focused entry and writes only `output/build/game_app/`. Strict C99 static gate
  and simulated-time host tests passed: core **261**, adapter/app **519**, new
  input/loop **692 assertions**. Original smoke plus **64-step stdin replay**
  (22 menu/dispatch + 21 per evdev layout) passed, including truncated-record
  rejection. New transcripts: `offline_input.txt`, `offline_evdev_LE32.txt`,
  `offline_evdev_LE64.txt` in that build directory. Tests cover input/sync/one-click,
  blocked start, old tasks, idle timeout, disconnect/reconnect, capture-time score
  and coherent copied models/rays/generation/score. One initial sandbox GCC DLL
  relocation failure was retried once outside sandbox successfully.
- `game_evdev_stream_*` now owns partial bytes per explicit layout/connection
  epoch and handles fragmented/multiple records through the existing decoder
  and normalizer. Detach/new epoch clears partial bytes, unfinished reports and
  pending clicks. Malformed records use the dropped-report recovery protocol;
  no recovery while a trailing discarded record is partial. EOF/disconnect/read
  errors latch until connection changes, so a permanently true link cannot
  resurrect stale input. No-data and EINTR preserve valid partial records.
- `game_pump.h/.c` adds versioned injectable monotonic clock, connection epoch,
  read, deadline wait, state-resync, completion and publication callbacks. One
  owner serializes all updates through game_loop_step: at most four reads of
  192 bytes and four completions per batch, tick before/after I/O and publish
  one full snapshot. Idle calls wait_until (also after EINTR-only batches);
  deadline is min(now + JSON pump_tick_ms=10, running timeout). Callbacks other
  than wait must be bounded/nonblocking; readiness must not spin on latched EOF.
  Neither unplug nor recovery selects/starts/resets/pauses the game.
- Completion arrays are borrowed only through the synchronous submit, before
  the next poll; no result pointer is queued. Original capture ms, sequence and
  dispatch generation stay with the task unchanged. Retained publication is a
  value copy. The text entry's one-slot completion mailbox owns its array and
  rejects overwrite; pump_frame queues the explicitly supplied original stamp.
- Same game_offline entry now supports pump_begin/bytes/io/link/resync/run and
  pump_frame, alongside the existing text protocol. Replay uses simulated clock,
  reads/waits and whole-snapshot publication, not a second app or game state.
  Final focused verification: strict C99 static check; core **261**, adapter/app
  **519**, input/loop **692**, pump **271558 assertions**; original smoke and
  **102 stdin steps** including both stream-layout pump replays passed. Covers
  idle exact timeout, input/EINTR floods yielding to completions/ticks, bounded
  result drain, resync ordering, buffer reuse, old tasks and coherent ray/score.
  Transcripts remain under output/build/game_app, including offline_pump_LE32.txt
  and offline_pump_LE64.txt. First static GCC launch hit the known Windows DLL
  relocation failure; one same-command retry outside sandbox succeeded, and
  subsequent checks used that working path. No photo full regression, complete
  build, actual sleep, dependency install, Linux runtime or hardware test ran.
- Snapshot rendering: `game_render.h/.c` consumes one complete `GameLoopOutput`
  (snapshot + derived menu) and the shared JSON layout. Pure 1280x800 BGR888
  virtual background, six canonical models/rays, Chinese menus/status, timer,
  stars, pointer, disconnect/invalid/stale warnings; no camera pixels, ticking,
  tracing, score policy or second state machine. Same half-open button rects
  own drawing and hit regions. Uncalibrated logical coordinates map uniformly
  into the JSON viewport; no A3/mm calibration is invented.
- `vision_overlay` now owns shared capacity/stride-aware raster primitives and
  canonical model expressions; legacy APIs remain. Size/overflow, finite
  coordinates and clipping are checked before bounded loops/conversions.
  Original CC0 16x16 short-label glyphs require no external/system font.
  `render_budget_exceeded` draws ALL published solver segments, displays an
  explicit warning and returns `GAME_RENDER_FULL_RAY`; physics is unchanged.
- The unique text entry adds `render PATH.ppm`, with no tick or state mutation.
  In pump mode it exports ONLY the last actual publication, not intermediate
  events or queued completions. P6 RGB conversion checks I/O; only active BGR
  pixels are read/written and row padding is preserved. New render parameters
  stay in `pc_vision/game_config.json`, emitted by the existing generator.
- Verification: strict C99 static gate passed; original core 261, app/adapter
  519, input/loop 692 and pump 271558 assertions remain passing. Renderer guard,
  overflow, adversarial clipping, immutability, coherent-field, menu-edge and
  state tests passed: **639725 assertions** (including byte guards;
  output/build/game_app/game_render_host.txt).
  Existing fixed-scene geometry/BGR/stride/guards/clipping/software-commit tests
  also passed after the shared primitive change; no photo regression ran.
  Original smoke + 102 text steps remain passing. Added pump-to-PPM replay:
  13 exports, two byte-identical text/image runs, publication/queue isolation,
  clear/switch/old-task rejection, disconnect/stale/timeout. Transcripts, replay
  input, image hashes and PPM/optional PNG previews are under output/build/game_app.
  Representative images were opened for visual QA; original label glyphs were
  refined for legibility. Budget preview is a renderer capacity fixture, not a
  detected/solved scene. Initial sandbox GCC DLL relocation was retried once
  outside sandbox; successful host checks used that path. No sleep, install,
  complete build, syscall/backend or hardware access was performed.
- Native Linux input seam: `game_linux_io.h/.c` supplies actual Linux
  open/read/poll/close/CLOCK_MONOTONIC and evdev capability/key-state ioctls,
  behind an injectable versioned call table. Native branch is excluded on host;
  tests use fake calls only. Init checks compiled input_event widths/offsets/
  endianness, but this is not target-kernel/runtime ABI acceptance. Explicit
  device path/open only; no discovery, automatic reopen, grab or new app entry.
  Input fd is owned, wake fd borrowed/drained by owner. Successive opens always
  issue a new epoch, even when fd is reused. EOF/errors detach before idle poll;
  bounded EINTR, remaining-deadline polling and held-key resync reuse the pump.
- Clock failure now has a reserved GAME_PUMP_CLOCK_ERROR=UINT64_MAX sentinel;
  the existing pump rejects it before ticking/consuming new input/publication.
  Failed/backwards clocks latch in the adapter and require return to owner.
  This small protected-module change is covered by original pump regression and
  explicit injected failure before/after a read; no game/ray/timer rules changed.
- Linux seam verification: strict host C99 and ARM Linux branch C99 checks pass;
  **161 fake-syscall assertions** pass. Original 261/519/692/271558/639725 tests,
  smoke, 102 text steps and 13 two-run deterministic images remain passing.
  Existing compiler emitted a 4804-byte ELF32 LE ARM relocatable object only;
  no linked application, actual syscall, target execution, glibc 2.27 compatibility
  or hardware claim. Current cross sysroot remains glibc 2.36. Reports/object are
  output/build/game_app/game_linux_io_host.txt, game_linux_io.arm.o and
  game_linux_io_arm_check.json. Same test_game_app.ps1 owns host tests and
  optional -LinuxStaticOnly check; no install, real sleep or full build ran.
- Native target diagnostic (`tests/game_linux_native_probe.c`, driven explicitly
  by `tools/test_game_linux_native.py`): image-native GCC 7.3 passes strict C99
  syntax checks before linking the existing input/loop/pump/app/core sources.
  The 161 injected-syscall assertions pass on both Windows host and ARM board.
  Native binary is ELF32 little-endian ARM EABI5 hard-float, loader
  /lib/ld-linux-armhf.so.3, maximum required symbol version GLIBC_2.17 on the
  image's glibc 2.27. The newer host cross-sysroot remains unqualified.
  Native compilation exposed old Linux headers without input_event_sec/usec;
  local member selectors now use legacy time.tv_sec/usec when the UAPI aliases
  are absent, retaining all byte-layout checks. Modern ARM headers also pass.
  Actual initialization/open/capability ioctl/key query/monotonic clock/read/
  poll/close ran with /dev/input/event0. UAPI is 16 bytes, type/code/value at
  8/10/12, sizeof(long)=4. Physical mouse-to-menu acceptance now PASSES on the
  first newly authorized click-only attempt, after the actual interactive-ready
  marker was received and relayed to the user. Three real down/up pairs produced
  two first-level selections (initial release protection retained), generation=2,
  PREPARING, remaining=180000, stars/models/rays/elapsed=0. 336 bytes/21 complete
  records, 7 SYN_REPORTs; 1820 coherent publications, zero consistency/record
  failures. Explicit start returned GAME_INVALID_SCENE=8, as required without
  observations. Actual cursor (239,113) stayed inside the shared first button.
  The diagnostic's optional --clicks-only requires three pairs/two selections,
  needs no motion, and stops early on acceptance; normal motion mode is retained.
  Its ARM strict C99 check and image-native strict compile/link/161 assertions
  passed before this run. Serial readiness forwarding is now board exercised.
  Earlier two windows did not pass selection (zero events, then only one pair);
  their logs remain evidence, including real X=383/Y=525 motion and ~3.4 ms
  process CPU per 800 ms idle. No further attempts ran after success.
  Probe seeds only the cursor at shared first-button center (240,114), injects
  no detection scene or menu selection. Each mode requires real reports and
  selections before it can pass. Logs and session/result/analysis JSON are in
  output/build/game_app/game_linux_native_*; first compile failure is retained.
  Prior failed-acceptance windows are retained, and the selected board /tmp test
  bundle is removed; COM9 is closed. No device permissions/services changed.
- Still required: real Linux capture backend, production native owner wiring,
  calibrated A3 mapping, display backend and real hotplug recovery,
  frame-boundary publication, and separately authorized board acceptance. The
  native input diagnostic qualifies only its own ARM binary/input seam; it does
  not qualify a production renderer/display binary, framebuffer/DRM path or
  1280x800 timing. Static-display Explore conditions and the minimal next scope
  are recorded in PYNQ Migration Status. Known full-regression failures remain
  separate.

### Delivery Gates and Next Task

Final display decision:1280x720/16:9;1280x800 output is no longer required. Existing800-line canvas/assets/fitted720 path remain historical facts;native720 UI/assets/mouse mapping need adaptation. No new build or board result follows from this contract change.

**Current decision (2026-10-24): OFFLINE LLP FIX PASS;not built or board qualified. Old-source actual-FIFO counterexample proves blocked-payload SOF mutation,next-frame SOF loss and premature CRC comparison. One source revision passes boundary stress,two continuous720-line frames and three legacy full-frame/reset-recovery cases. Checksum/catalog/target refreshed;generated LLP identical and2640 HWH parameters unchanged. Physical hotSOFLate/cold23.335sSOFEarly failures and same-cause2STOP remain;no real075 C frame yet. Hardware paused;new production build and board qualification require fresh explicit authorization. Offline evidence:color_test/build/csi_frame_boundary_1/review.json;physical evidence:color_test/build/pl_rate93_production/build_4/review.json.**
Current evidence:`output/build/game_app/live_camera_1/review.json`.
Primary evidence:`output/build/game_app/photo_levels_1/review.json`;
retained continuous baseline:`output/build/game_app/menu_continuous_1/review.json`.
Previous route audit:`color_test/reports/PL_baseline_diagnosis.md`.

| Baseline | Actual state | Remaining gate |
| --- | --- | --- |
| A pure-PL colorbars | PARTIAL;old FAIL/STOP retained | Optional diagnostic;not required for B/C. |
| B PS/DDR->VDMA->HDMI | Scoped720p static,continuous software switching/mouse and safe-stop PASS;final signal target now720p | Broader startup/recovery and same-source final720p package acceptance. |
| C SD assets->DDR->HDMI | SD assets,720p continuous menu and075/076/077 virtual drawing/user confirmation PASS | Native720 UI/assets/mouse mapping,processing/TTL limit and full game acceptance. |
| D MIPI->CSI->VDMA | Offline LLP SOF/CRC boundary repair PASS;physical warm/cold failures retained,safe-stop confirmed | New authorized same-source production gates/artifacts,then board qualification;real075 not measured. |

Retained photo evidence used fixed_build_4 on historical boot687f9d0c.
Photo scope is drawing,not solved-state or full game acceptance. Real C detector
consumes lossless075/076/077 BGR inputs;no photo background or fake observations.
Board categories/effective poses/full rays match host;all3 screens confirmed by
user. Default renderer/menu path and three-store ownership mechanism retained.

One configured90s run stopped at50.65s on detector251ms>TTL250ms. Native return1
is a freshness stop,not a completed90s pass;no retry or validity extension.
Independent stop0/owner_can_exit1,HALTED/errors0,camera0,clock0,no active owner;
UART closed. Frame addresses/HSIZE/stride/height match retained baseline.
BOOT/services unchanged. Detailed limits and corrections are in photo review.

Photo drawing/SD distribution remain complete:output/sd_card/ray_game_assets.zip.
Authorized fixed-rate diagnostic completed:one load,one0.248247s explicit stream.
Measured93.312..93.344Mb/s/lane;old-boot cleanup standby0x42/GPIO960out0/no owner.
After reboot only UART identity read;root/ownership pending;UART closed.
Camera cells restored from this repository into the canonical BD;display retained.
Prior metadata2/2 STOP resumed;native preparation11/source identity PASS.
Build1 rejected64 unsafe status-counter inputs plusResetBridge aliases;build2 fixes verified.
Build2 implementation1 completed;raw hold-1.111/-1.097ns uses obsolete IP data window.
Builds2/3 used;prior failures retained;both-state corrected-model STA/CDC/DRC/resources PASS.
Native repaired entry and equivalent hardware inventories verified;no new full build required.
Gated BIT/HWH/XSA export1/1 complete:color_test/build/pl_rate93_production/build_2/export/artifacts.json.
Current production startup PASS:output/build/game_app/live_camera_1/startup_1/startup_receipt.json.
Capture allocator preparation blocked before upload byexpiredsudo;UART closed,sensor0,DMA/CMA/live0.
Afteruser refresh onlyone same-path retry;capture/backend/ABI/throughput gates remain before live run.
Prior TTL failure,sampling counters and stable-FCLK1/drain/retain rules remain.

### Retained Sampling Evidence and Failure Ledger

Section27 (2026-10-20): evaluation-only recommendation is pathA evidence-first
model qualification; no model/hardware adoption or design run. Bank13 supply
change is rejected as the default minimal fix; retimer interposer is conditional
fallback. No executable closure route yet. See `sampling_release_paths_review.json`.

Section26 (2026-10-20): the one new mechanism reviewed is XAPP523-style4x
oversampling DRU. Offline admission NO_GO_DECLARED_MODEL; one feasibility review,
zero implementation/design runs. See `other_sampling_mechanism_review.json`.
The0.5UI algorithm prerequisite is not guaranteed by the retained0.299916UI
model. No old family is reopened; no universal oversampling/device limit claimed.

Section25 (2026-10-20): exact-version metadata/interface admission review of
AMD4.3rev6 RX/AUTO completed, BLOCKED_NOT_ADMITTED; no budget/generation/design
attempt and no new failure allocation. Evidence: `calibration_admission_review.json`.
Missing electrical and calibration contracts are explicit; no candidate switch.

Section23 (2026-10-20): formal NO_GO/STOP for the current complete RX/FIXED
BUFIO/BUFR/data-IDELAY route. Existing evidence provides no distinct compensation
or correlated-delay improvement; LP IBUF fixes packaging, not an evidenced HS
common-window mechanism. Section10's negative tap5 unplaced budget is historical,
not a measurement of tap1; no claim that all vendor/FPGA structures are impossible.
No new design verification/failure count; family2/2 and all prior stops retained.
Config/budget entry is blocked; read-only historical query remains available.
Section22's authorization-only retry next step is superseded. Evidence:
`amd_phy_fixed_probe/fixed_route_stop_manifest.json` and report section23.

LP-buffer follow-up (2026-10-20): user authorized only six IBUF in the existing
AMD fixture, preserving all other settings. Added2 clock-LP plus2 per data lane,
HSUL_12/IBUF_LOW_PWR=TRUE, with named P/N and lane indices unchanged. Static
connection/scope audit PASS; no new design run or reopening of vendor-family2/2.
Historical optimized DCP/admission failure is retained and does not cover this
source edit. Evidence: section22 follow-up and `lp_ibuf_edit_manifest.json`.

Section22 (2026-10-20): candidate-only adoption of complete AMD4.3rev6 RX/FIXED;
internal D/NONE restriction lifted only inside this isolated candidate, with no
production selection or protocol/CDC/input-model waiver. Exact Oct19 generation
is found and reused (17 parameters PASS). One read-only optimized-DCP audit:
66 PASS/6 FAIL, all failures are missing LP IBUF. Actual clock is IBUFDS ->
BUFIO/BUFR4; data is IBUFDS -> VAR_LOAD constant1 -> ISERDES DDLY/BOTH, no CMT.
Real RDY has live internal reset endpoints; this does not qualify recovery/CDC.
Historical records omitted from section21's closeout are now retained explicitly:
generation precondition correction1, parameter-audit correction1, budget gate
rejection before synth1, then one synth/opt/place attempt stopped on six
Place30-188 LP UnBuffered IOs. No route or own sampling budget; vendor family
used2/2 rounds (section10 first, this historical seed second), no automatic retry.
Current task has no new design round or generation/synthesis/optimization/place/
route/function/OOC/production/board run. Only the read-only Vivado DCP query ran.
Restricted process creation failed twice (0x80070020), path stopped; ordinary
Windows query completed with no retry. Evidence: section22 and
`amd_phy_fixed_probe/adoption_structure_manifest.json` under the existing build.

Section21 was a proposal-only closeout with adoption pending at that time.
Its246 prior evidence hashes and17 source-hash observations remain historical;
the later generation/implementation records above are not retroactively claimed
as section21 execution. Full IP packaging cannot restart a stopped CMT/BUFG scheme.

Section20: PHASER family phase-reference tracking reviewed, offline admission
rejection1. No new synth/route/simulation/OOC/board run and no clock scan.237 prior
evidence/source inputs and7 local-source hashes unchanged. Legacy/current source
versions and inaccessible2023.1 documentation receipts are explicitly separated.

Section19: true external-network feedback has device-rule basis and concrete
same-bank package/core mapping, but this bare LVDS_25 output loop is rejected by
the supplied3.3V Bank13 schematic and lacks common-gap improvement evidence.
Offline admission rejection1, new implementation/verification runs0; all225
protected inputs unchanged. No automatic second electrical variant or family retry.

Section18 closes the offline feasibility review: no qualified new mechanism;
three-revision CMT/BUFG family stays STOPPED. No additional design verification,
Vivado or board run; all failure counts below unchanged.202 protected inputs
(prior evidence, latest PLL artifacts/manifest and source files) hash unchanged.

Latest fixed PLL result is section17: one routed implementation, ZHOLD,
128 complete own paths; literal Fast/Slow/common +0.0935/+0.4715/-1.8835 ns.
Fixed -90/-22.5 seed fails setup. 49 audit checks PASS,149 prior files unchanged.
CMT/BUFG revision3 conservatively STOPPED; no functional/OOC/board continuation.
All earlier evidence below remains historical and does not qualify this PLL.

**采样候选结论：** `BUFH_DDIRECT_M3` 的默认关闭规范 RTL、双配置原语/协议
夹具和独立控制器故障注入已经实现。当前源码的定向功能检查通过，保持真实
ClockLane/DataLane、LP、IDELAYCTRL/RDY 和既有 CDC 桥。16 个 offset/RF 调度
实际覆盖每 lane/config 的全部 8 种对齐及 R/F 两类；对齐与边沿相关，未证明
16 种独立物理组合。细节、命令、延迟和证据见采样方案第 8 节。
生产仍默认 BUFIO/BUFR＋IDELAY，候选独立参数贯穿顶层；旧强制关闭 MMCM
的连接保留。输入模型、采集模式、软件与已通过三项 CDC 修复保持现状。

功能准入后按扩大的非板端授权执行过一个固定 180°/45° 最小 OOC：真实
12 个 HS/LP pins 可布线，但 64 项相邻 bit 配对审计得到 Fast 窗口 +0.550 ns、
Slow -0.407 ns、共同 -0.932 ns；WNS/TNS=-2.230/-4.451 ns，WHS/THS=+0.120/0 ns。
该版还有 1 项 CDC-10。已将 capture_hold 改为 RefClk 寄存输出，并修复候选
未 ready 分支可能绕过 100 us T_INIT 的问题；最新功能复验通过，CDC 修复的
工具分类尚未验证。修订后的 OOC 两次在辅助进程读取 vendor common.tcl
失败；中断后一次单线程验证又在读取本次 realtime Tcl 时失败，均未完成综合。
当时按 AGENTS §7 停止该运行路径；这三次历史失败仍保留。
`reports/dphy_sampling_ooc/audit.json` 已标记 current_rtl_covered=false，不能将
15:52 的旧报告/检查点当作 16:12 功能通过源码的 OOC 验收。GCC 不是当前阻塞。
受限展开两次失败、首轮 1 ps 精度/68 interval 失败、首个 OOC 的时序/CDC
失败和后续三次工具启动失败均保留，不因修订或新会话清零。

**本轮结构预算准入未通过（2026-10-18）。** 仅以原生 Vivado 2023.1 从旧
固定 routed DCP 读取原语/网络延迟；没有重现已解决的综合脚本读取问题。
Slow 时钟差0.501 ns拆为网络0.404、原语0.097；其它旧项冻结时只允许
0.0935 ns，理想删除网络差仍约-0.0035 ns，且共同窗口另缺0.932 ns。
MMCM/HPC→BUFIO/BUFR 的连接在官方规则下合法，但输出侧冻结旧项筛选
最多只支持0.243 ns改善，仍缺0.1645 ns；内部反馈的新补偿/U/aperture
及跨角点改善无本地证据。按用户「无可信改善依据不启动昂贵构建」条件，
未修改规范RTL、未执行新UNISIM/OOC/生产顶层，不能报结构修订完成。
审计工具新增独立历史预算模式及4项回归，15/15 PASS；只输出到既有build，
没有覆写旧audit/CDC/时序/DCP。精确命令、失败查询和边界见采样报告第9节。
当前RTL的capture_hold CDC分类仍UNKNOWN；生产默认、三项CDC及T_INIT保留。
**当时下一项设计任务：** 找到有器件/工具依据、能同时闭合Slow与全角点有效
包络的新采样时钟连接；不能把旧aperture/U/残差移植成预测值。现候选不再
相位/tap扫描或完整构建；本轮未消除阶段1采样阻塞。失败账本完整继承。

**ALINX 2023.1结构比较与新预算筛选（2026-10-18后续）：** 复用已存厂商
配置，合法生成CSI-2 RX 5.3并定向综合其D-PHY 4.3 Rev.6；实际连接为
时钟IBUFDS直入BUFIO/BUFR÷4，数据VAR_LOAD IDELAY(tap=5)→ISERDES DDLY，
没有时钟IDELAY或MMCM。厂商LP在RefClk fabric同步，BUFR CLR=0；当前规范
默认仍是BUFIO/BUFR＋IDELAY、MMCM关闭，已有LP/CDC/启动处理不能自动替换。
未布局工具查询覆盖64主配对＋64额外STA路径，使用本轮3.571/0.268/1.518 ns：
Fast/Slow/共同窗口=+0.093/-0.055/-0.704 ns，U=0.035 ns/侧；零网络冻结
原语反事实仍为Slow -0.017、共同 -0.371 ns。不能把未布局与旧routed差值
报告成实际改善。没有可信正预算，按用户门禁未选择新RTL候选，不运行新
UNISIM/候选OOC/生产顶层；采样阻塞未解除，不扫描厂商tap或复制其2ns约束。
生成的CDC waiver/false path仅作文本比较，未加载或集成；规范RTL/XDC、
capture_hold/T_INIT和生产默认保持。新增独立vendor预算解析及5项回归，
20/20 PASS。脚本/日志/manifest在`color_test/build/dphy_sampling/`，
合法生成的诊断IP、结构DCP和未布局报告在`build/dphy_sampling/vendor_reference/`，
未加入生产工程，不是工程副本或第二套生产接收器。详见采样报告第10节。
三次定向Vivado入口均成功，沿用已恢复的原生控制台方式；不重查旧工具问题。
旧audit/CDC/timing/routed DCP哈希未变，最新capture_hold CDC仍UNKNOWN；
继承全部失败账本，当时无新规范结构验证轮次。后续固定HPC探针结果见下段；
不等待外部物理保证或无依据构建。

**内部反馈＋HPC单次固定预算探针（2026-10-18，历史）：** 当轮明确允许功能门禁前
的一次最小综合/布局/布线。复用已有原语harness和规范HS_Deserializer，固定
M=3/D=1、串行/3→专用HPC→BUFIO、字节/12→专用HPC→BUFR(BYPASS)、
CLKFBOUT直回CLKFBIN、两数据D直采、初始0°/0°。真实12个HS/LP引脚可合法
布线；两HS＋四LP ISERDES保留，串行12个CLK/CLKB pins、字节约124负载，
未包含完整ClockLane/SFEN/PPI。工具将默认ZHOLD自动选为INTERNAL，内部反馈
走CLKFBOUT2IN；无手工补偿/路由放宽/时序例外。

新routed Fast/Slow/共同窗口=**0.000/−0.275/−2.175 ns，预算FAIL**。
同角点Slow时钟差0.369=IBUF0.040＋MMCM0.004＋BUFIO0.096＋网络/打印残差0.229 ns；
共同差2.725=0.505＋0.027＋0.836＋1.357 ns。新每侧U=0.142 ns；Slow与共同
有符号aperture为0.105/0.117 ns，数据差+0.053/−0.416 ns。64主配对＋64额外
STA路径保持绝对bit边沿，不折返或换bit；Fast的零窗口也无量化/布线余量。
内部反馈不抵消输入与前向网络；Slow窗口比历史BUFH改善0.132 ns，共同反而
恶化1.243 ns，不能把不同控制/字节负载的harness对比当生产收益。

单次探针执行/合法性PASS，但预算准入FAIL；自然UNISIM、独立控制注入、规范
接收器选择、接收器OOC及生产顶层均NOT_RUN。没有新bit/byte延迟、启动/恢复
或波形证据。探针post-place LUT/FF/slice=174/134/69、BRAM/DSP=0，1MMCM/
1BUFIO/1BUFR/1RefClk BUFG，DRC零Error、两项原有类别Warning，351可路由网全完成。
摘要WNS/TNS=−2.385/−4.769、WHS/THS=−3.653/−7.290 ns；setup负项及1项CDC-10
来自历史测试guard。它不是已寄存修复的规范capture_hold，不能替代其UNKNOWN
分类或宣称CDC通过。OOC虚拟边界仍有3输入/21输出无delay，不作全顶层验收。

设计账本：固定结构尝试1，预算否决后停止，无扫描/重布线；受限启动一次在
vendor launcher报Access is denied、setupEnv/loader定位失败，未进入Vivado；
按已知普通Windows/原生控制台/仓库根/synth.maxThreads=2入口执行成功。
再开同一个DCP仅读取Fast/Slow网延迟，不是第二次设计尝试。离线解析新增时
字面UI字段/断言与新增检查顺序各有一次失败，已分别修复并保留输出，最终24/24 PASS；
无输入约束放宽或设计失败转PASS。全部历史失败仍保留。

命令、完整路径/反馈/HPC分解和范围见采样报告第11节；日志、routed DCP、
budget、CDC/资源及`hpc_internal_manifest.json`在`color_test/build/dphy_sampling/`。
规范7个RTL/XDC、旧audit/CDC/timing/routed DCP哈希均与前轮manifest相同。
生产仍默认BUFIO/BUFR＋IDELAY、MMCM关闭，三项CDC、capture_hold和T_INIT均保留；
没有生产候选开关、BIT/HWH/XSA、板端操作或Git提交。
**当时唯一下一步：** 停止内部反馈结构，只审查一个能补偿输入/前向路径的具体合法
反馈连接及其新预算；须净消除Slow至少0.275 ns、共同至少2.175 ns缺口并保留
布线/相位量化余量及固定bit身份，才可进入实现。本轮未开展第二拓扑，阶段1
采样阻塞未解除，也不重新等待供应商/眼图/全PVT资料。

**BUFG反馈＋匹配BUFG＋D直采预算（2026-10-18，最后完整routed预算）：** 按当轮明确授权只执行
一次固定0°/0°、M=3/D=1、串行/3、字节/12的最小综合/布局/布线。沿用普通
Windows、仓库根、继承控制台句柄和synth.maxThreads=2，首次即完成；无环境失败。
真实12个HS/LP pins、两HS/四LP ISERDES、串行12个CLK/CLKB pins及字节124负载保留。
MMCM_X0Y0；反馈/串行/字节为BUFGCTRL_X0Y3/1/0，RefClk另用X0Y2。
默认关闭的诊断参数只存在既有SV harness，不改规范接收器或生产选择。
声明/optimized/placed/routed均为ZHOLD，无手工补偿、约束放宽、路由覆盖或例外。

本次自己的routed报告得到Fast **+0.550 ns**、Slow **−0.407 ns**、共同
**−0.932 ns**，预算FAIL并停止。共同限制为Slow lane1/N/data-rise/capture-fall
setup与Fast lane0/P/data-rise/capture-rise hold。全部64主配对＋64附加路径完整，
绝对setup=UI、hold=0关联保留，不折返/换bit。新时钟差Fast/Slow/共同为
−0.387/+0.501/+0.639 ns；U=0.142 ns/侧；共同数据差0.517、aperture0.028 ns。
字面UI复算缺口为Slow0.4075、共同0.9325 ns；3位打印约0.5 ps残差不是余量。
共同窗口为空，不选择相位格点，不进入功能/启动/恢复、接收器OOC或第二拓扑。
具体反馈与前向网络、D端口aperture及损耗分解见采样报告第12节。

探针post-place LUT/FF/slice=173/134/68，BRAM/DSP=0、1MMCM/4BUFG/6ISERDES，
351/351网完成，DRC零Error、RTSTAT-10/ZPS7-1两Warning。摘要WNS/TNS=
−5.847/−16.145 ns、WHS/THS=+0.159/0；数据输入单独WNS/TNS=−2.230/−4.451，
WHS=+1.298。更差的setup摘要和Critical CDC-10来自历史测试guard异步控制，
不能冒充新规范capture_hold结果。虚拟边界3输入/21输出无delay，完整控制省略，
aSettled=1；无功能、启动、bit/byte配对或延迟验收。已接受三项CDC、capture_hold、
100 us T_INIT和720p RAW10/BGGR均未改，无BIT/HWH/XSA、生产构建或板卡操作。

失败账本继承全部历史；新增设计尝试1，连接合法/布线完成、正预算FAIL，无重跑。
初次报告请求6位小数被Vivado 12-2333告警回退为3位（36条），原日志保留；入口
已按工具上限改成3位，未因此重跑实现或覆写原报告，不是环境/设计启动失败。
离线29/29首次通过；11项规范/旧OOC及29项前轮HPC制品哈希逐一未变。
日志/DCP/报告/预算及manifest在`color_test/build/dphy_sampling/`。
**当时唯一下一步：** 本连接停止；离线审查一项有器件/工具依据的剩余相关延迟修正，
先以本次新路径消除Slow>0.4075 ns、共同>0.9325 ns缺口并留出量化/布线余量，
再提出独立的下一轮验证。没有正共同预算前不值得继续功能整合或重跑本结构。

**共享反馈/串行BUFG的准入执行（2026-10-19，初次阶段）：** 用户要求按上一轮方案
执行；只选择CLKFBOUT经同一个BUFG同时驱动CLKFBIN及串行采样、CLKOUT1经
另一BUFG驱动字节时钟的具体连接。默认关闭参数仅在既有诊断harness；M=3、
D=1、字节/12、声明0°/0°。这计入BUFG反馈系列尝试2，保留第12节尝试1失败。
先运行综合/opt后未布局模型查询；未达到可信正预算就不布局布线。普通Windows、
仓库根、继承控制台、synth.maxThreads=2成功进入工具并完成综合/opt，零Error/
Critical Warning；optimized补偿ZHOLD。12个HS/LP引脚赋值及原输入模型保留，
两HS/四LP ISERDES、3BUFG/1MMCM/0IDELAY结构检查通过；未证明实际布局可达。

初次入口在比较层级net对象时断言“D sampler is not on the shared feedback/serial
net”；从同一optimized DCP恢复一次，只读查询仍被同因断言拦住。工具导出的
展开leaf清单包含CLKFBIN及全部12个CLK/CLKB；问题是验证入口网络比较失败，
不能归类为工具环境故障或负窗口设计结论。按AGENTS§7同因两次停止，保留两份
日志、DCP和原stage。已改为展开leaf名称成员检查，离线核对成员完整；修正后
Vivado入口NOT_RUN。新sampling_corners/budget不存在，Fast/Slow/共同窗口、
实际U、D aperture及相位格点均UNKNOWN，无布局/布线、功能/CDC或接收器OOC。
34/34离线审计回归PASS，其中新增5项使用明确标记的合成解析fixture；未移植成
新结构预算。69项前轮制品/规范文件哈希保持，生产默认/CDC/capture_hold/T_INIT
未改；无BIT/HWH/XSA、生产构建、板卡操作或Git提交。

证据、命令、入口失败账本和来源边界见采样报告第13节及既有build中的
`shared_feedback_model_manifest.json`。**当时唯一下一步（已在下段执行）：** 获得明确继续停止路径的
授权后，仅读取本次`shared_feedback_model/probe_optimized.dcp`，用修正后的
`--shared-feedback-model-query`导出自身完整路径并判断预算；不重新综合、清零
尝试次数或直接布局布线。当前阶段1采样阻塞仍未解除。

**授权后的同DCP只读复核（2026-10-19，当前）：** 用户明确要求只读现有检查点，
不重新综合。修正leaf成员检查后一次运行成功，导出本连接自己的128条路径，
64主相邻配对＋64额外检查完整，实际终点D、串行源CLKFBOUT，绝对bit身份保留。
这是Optimized未布局模型，新Fast/Slow/共同窗口为**+0.591/−0.279/−1.136 ns**；
字面模型为+0.5915/−0.2795/−1.1365 ns，U=0.136 ns/侧。新时钟差为
−0.416/+0.385/+0.855 ns，Slow/common有符号D aperture为0.105/0.028 ns。
反馈和采样共用BUFG未消除缺口；预算FAIL，系列尝试2停止，无布局或功能整合。
冻结本次全部原语/补偿/U/aperture后理想清零网络，Slow仍−0.0695 ns、共同
−1.8685 ns，不支持只缩短布线的修订；不是其它结构的理论上限。最小净解除量
为Slow>0.2795、共同>1.1365 ns，另留实际布线/可达相位余量。

36/36离线回归PASS（新增真实Optimized报告验证及混合状态拒绝），没有新仿真/
CDC或物理验收。首次离线解析因状态标签Optimized被旧Synthesized-only检查
拒绝，继发摘要读取缺失budget文件；已修正并保留记录，未改输入模型或借旧
路径填数。原两次入口失败、历史负预算全部保留；84项前轮证据身份逐项未变，
DCP SHA256仍89d618b9c7f43af6e391115c5a98dc792ec4605abb9824cf4897028f9131aae9。
本轮仅更新导出入口的receipt文件名以保留旧失败清单、审计模式和定向回归，
规范RTL/生产选择不变，无综合/opt/place/route/BIT/HWH/XSA/板卡操作。

完整分项、限制路径、原日志和哈希见采样报告第13节的授权恢复结果，以及
`shared_feedback_resume_manifest.json`。

**局部源同步/D直采校准离线审查（2026-10-19，历史阶段）：** 复核AMD 7系列规则、
规范实现和已登记检查点/报告；候选具体为时钟IBUFDS→受控时钟IDELAY→同源
BUFIO串行/BUFR÷4字节，数据IBUFDS→D/NONE。该组合没有自己的检查点；现存
局部结构走DDLY，现存D直采结构经过MMCM，不能拼接其U/aperture/布线填出
新窗口。Fast/Slow/共同窗口均UNKNOWN，每角点正窗口尚未证明，当前共同门禁
保持不变，校准验收尚未采用。源同步及D直采有减少损耗项的机制依据，但时钟
IDELAY基础延迟、min/max分散、有限延迟范围和跨角点关系仍须实际取证。

200 MHz参考下标称tap=78.125 ps，0..31相对tap0跨度2.421875 ns。建议预算设计
目标（未作为新验收门槛）：量化最坏半步39.0625 ps＋每侧25 ps预留，窗口
>128.125 ps，再增加2倍未量化的校准/漂移误差。即全部相关损耗包络<407.375 ps，
另扣上述误差；正窗口还必须落在合法有限tap范围，不能负相移按UI折返换bit。
相对于第12节字面旧预算，达到该目标须Slow净改善>0.535625 ns、共同>1.060625 ns；
相对第13节未布局模型则为>0.407625/>1.264625 ns。它们是目标宽度的代数差额，
不是预测新拓扑收益。校准不能用理想平移修复角点内空窗口；每角点分别可选设置
也不等于当前要求的共同设置，不能扣除无依据的相关性或uncertainty。

本次仅离线重算第13节现存报告，完整输出与既有budget.json逐字段一致；保留
64主＋64额外配对及绝对bit身份。99项旧证据哈希未变；四个诊断/审计源码哈希
与本轮前快照一致，未运行的局部探针草稿已撤除。未启动Vivado或消耗新的设计
验证轮次；无综合/opt/place/route、扫描、功能/CDC验收、制品或板卡操作。
第14节及`local_clock_review.json`/`local_clock_review_manifest.json`保留定量条件、
官方来源、启动/校准验收缺口和本次边界。**当时唯一下一步（已在下段执行）：** 在明确解除本轮沿用的
“不重新综合”限制后，只为这个局部D直采连接取得一份固定设置、自身完整路径的
最小预算证据；不先写校准控制器，不进入第二拓扑或生产整合。当前阶段1仍被
采样预算阻塞，不把离线审查写成采样闭合。

**明确授权后的局部时钟/D直采固定探针（2026-10-19，当前）：** 用户解除“不重新
综合”，仅授权一个固定最小预算探针。现有入口增加默认关闭LOCAL_CLOCK_PROBE；
VARIABLE时钟IDELAY tap0、200 MHz、CLOCK/HIGH_PERFORMANCE，CE/INC/LD绑0，
同一延迟源接BUFIO与BUFR÷4；两lane数据为D/NONE，无MMCM。一次普通Windows、
仓库根目录、继承控制台句柄的Vivado 2023.1运行完整成功，checksum=1ddf3a63；
真实12个Bank13 HS/LP pins合法，349/349可路由网完成、0路由错误。保留六ISERDES、
124字节时钟sinks；完整ClockLane/SFEN/PPI、校准及生产控制未集成。

新报告自己的64主＋64额外路径完整保留绝对bit身份。Fast区间[-1.181,-1.053] ns、
Slow[-2.658,-2.590] ns，打印宽度+0.128/+0.068 ns；字面输入模型为
**+0.1275/+0.0675 ns，首次取得这个组合的每角点正窗口证据**。共同区间为空，
字面宽度**−1.4095 ns**，共同门槛FAIL不变。新U=0.035 ns/侧，PE/DJ=0；没有用
旧DDLY/MMCM数值拼接。Fast/Slow setup均限制于lane1/N/data-rise/capture-fall；
Fast hold为lane0/P/data-rise/capture-fall，Slow hold为lane0/P/data-rise/capture-rise，
共同是Fast setup/Slow hold。tap0最坏hold=-1.053/-2.590 ns，两窗口均需提前，
非负延迟型tap格点不可达；没有按UI/T折返或重配bit，未测其它tap。

共同损耗ΔD/ΔC/U合计/aperture为−0.416/2.174/0.070/0.117 ns，需净改善
>1.4095 ns才到零宽。冻结本次原语/U/aperture、逐行清零自身网络反事实仍为
Fast/Slow/共同+0.2465/+0.1475/−1.0125 ns，不支持只缩短路由闭合共同门槛；
不是其它拓扑的物理上限。若沿用第14节未采用的标称量化＋25 ps/侧设计目标，
还需Slow>0.060625 ns、共同>1.537625 ns净宽度改善，另加2E；E仍UNKNOWN。

夹具全局WNS/TNS=-2.034/-4.035 ns（RefClk到byte guard恢复路径），WHS/THS=
−2.590/−5.164 ns（D输入）；Critical CDC-10=1属于历史guard的组合capture_hold。
无新增豁免；参考/reset端口OOC未路由、缺少部分控制I/O约束、TIMING-6/7/8/18
以及RTSTAT-10/ZPS7-1等边界均保留，不据此签署接收器OOC或生产STA/CDC。规范
注册capture_hold、100 us T_INIT和已接受CDC源码哈希未变。placed资源174 LUT、
134 FF、65 slice、0 BRAM/DSP、1 BUFG/BUFIO/BUFR/IDELAY/IDELAYCTRL、6 ISERDES。

42/42离线审计回归PASS（含本次真实路径和拒绝缺维度/换bit/错误结构/不完整报告），
103项旧证据哈希未变。本次环境PASS，无工具失败/重试；设计尝试1预算FAIL后停止，
所有历史失败及新预算失败保留。无校准控制器、功能验收、后续拓扑、扫描、生产
构建/制品或板卡操作。证据与哈希见采样报告第15节及local_clock_probe_manifest.json。
**后续合并任务结果（2026-10-19）：** 预算修正→完整接收器功能/启动恢复→接收器
OOC已按同一连续授权处理，内部门槛和全部历史停止条件保留。本轮只审一项
“固定MMCM提前＋BUFIO反馈补偿”修正；UG472不支持BUFIO输出返回CLKFBIN。
只读打开第15节原routed DCP，沿实际BUFIO_X0Y1/O完整向下遍历402个节点、
300个I/O时钟sink，四个MMCM CLKFBIN目标均不可达。合法性FAIL，无新结构预算；
未启动新的综合/布局/布线、功能/启动恢复或接收器OOC，未自动换第二拓扑。
原128条路径重解析与budget.json逐字段相同，137项旧证据/规范/诊断入口哈希不变。
受限launcher首次Access is denied/setupEnv/loader失败；按本轮授权仅重试一次
既有普通Windows继承控制台方式，查询成功退出0。查询的末端无下游节点告警
及synth.maxThreads恢复提示保留，不是负预算或新RTL时序/CDC验收。
第16节及structure_budget_review_manifest.json保存本轮证据；local-clock尝试1、
BUFG反馈系列尝试2和其它历史失败不清零，新增设计实现次数0。
**唯一下一步：** 先提出一个器件规则允许、且有本机实现依据同时处理提前可达性
及共同包络的固定补偿连接，再取得该连接自身的预算。保持输入模型和共同门槛，
不重试已否决BUFIO反馈、不写校准控制器。阶段1仍阻塞，采样结构未闭合；本次
否决不证明所有拓扑均无解，也不新增供应商/眼图等待条件。

**综合运行脚本读取恢复（2026-10-18，独立授权任务）：** 三种方法依次为
受限进程启动、普通 Windows＋原单线程入口、普通 Windows＋双线程入口。
第一种在 batch launcher 报 Access is denied；第二种虽通过单寄存器双线程
探针，实际单线程接收器仍在 unimacro_verilog.tcl 读取失败；第三种实际综合
一度通过，但相同设置复核再次失败，因此不能认定线程数已修复根因。
随后按用户授权绕开原 Python 文件重定向启动链：普通 PowerShell 从仓库根
直接调用 vendor launcher，通过；将控制台句柄继承和根目录启动固化进既有
`run_dphy_sampling_test.py` 后，最终 `ooc-synth` 再次通过。两次均为
checksum=71cdf1a7、133 Warnings、0 Critical Warnings、0 Errors，约16秒综合。
精确的底层间歇性读取原因仍未定位；当前结论是已有实测可用的绕行路径，
不是文件缺失、普遍 ACL 修复或所有 Vivado 工作流已恢复的保证。
证据：`color_test/build/vivado_runtime/dphy_sampling/direct_vivado.log`、
`vivado.log` 和 `last_run.json`（SYNTH_ONLY_COMPLETE、输入/launcher 哈希、
implementation_covered=false）。失败另存 threads1_*、threads2_redirected_*；
第三种首次通过另存 threads2_initial_*。单寄存器探针在
`color_test/tools/check_vivado_runtime.tcl`，其通过日志在
`color_test/build/vivado_runtime/normal_threads2/`。
旧 audit.json、timing.rpt、cdc.rpt 和 candidate_routed.dcp 的 SHA256 均未改变。
本轮只解除阶段1的工具读取阻塞；没有重新接受候选、重跑仿真/布局布线或
生成 BIT/XSA，没有板端操作、全局 Codex 配置/ACL 改动或工程副本。
工具使用与直接启动回退命令见 `color_test/tools/README.md`。
下一项仍是采样结构预算修订；最新 RTL 的 OOC/CDC 分类仍未完成。

阶段 1 涉及 `color_test/repo/ip/MIPI_D_PHY_RX/hdl/`、现有相关 XDC、
`color_test/tools/analyze_dphy_sampling.tcl`、`audit_dphy_contract.py` 和
`color_test/sim/` 中的现有定向入口；报告放 `color_test/reports/`。
阶段 2-3 继续使用 `vision_ps_baremetal/src/game_linux_display.*`、
`game_render.*`、`game_input.*`、`game_evdev.*`、`game_linux_io.*` 和现有
`tools/game_linux_static_menu.c`，不写第二套渲染器/输入系统。
阶段 4 复用 `pynq_vision/`、已有打包器与 `output/pynq_overlay/`；阶段 5-6
复用 `vision_ps.*`、`game_scene_adapter.*`、`game_session.*`、`ray_game.*` 和
唯一手工配置 `pc_vision/game_config.json`，无需重建 Linux 或切换裸机。

采样改动风险为边沿/bit 配对、字节延迟、锁定/复位与首包；显示风险为分配/
缓存/DMA 所有权及模式时序；联合路径风险为 DDR 竞争、识别过期与代次混用。
每轮只解决一个具体问题，保留已有工作路径。后续每方案最多两轮验证，失败先
分析修订，累计三次修订仍失败则暂停；没有具体假设不重复完整构建。
当前场景有效期仍是配置中的 250 ms；先测量瓶颈，再按 C 优化、影子 feature
tap、与 C 对照的顺序增加必要 PL 加速，不能自动延长有效期或用旧帧触发胜利。
不增加摄像头到显示背景的复制；持续运行中的缓冲优化必须先证明安全。
已有鼠标/软件测试不重跑以冒充新进展；完整板端闭环仍未完成。
计划不授权板端操作、服务修改、SD 写入或完整构建，也不恢复 Windows 显示支线。
不承诺五天完成或预先宣称帧率；按阶段证据更新状态。

The 6,140,747,776-byte image remains available. Offline inspection supports
reusing it as a candidate runtime with its own native ARM GCC/G++ 7.3; a new
local PetaLinux installation is unnecessary for the next software step. PYNQ
does not require the game/physics application to be rewritten in Python.
Image provenance, exact AX7Z020B revision/FSBL compatibility and board operation
are not fully established. Resolve the stale BIT/HWH/XSA and FCLK contracts
recorded below before any custom PL load. Board USB/HDMI/VDMA/camera and
cache/clock checks remain separate, explicitly authorized hardware work.

Only if necessary customization cannot be achieved with the existing image
and matching tools, evaluate a separate Linux build host or appropriately
provisioned storage for a version-matched PetaLinux environment. AMD's 2023.1
host requirement lists 100 GB free disk space; this is a build-environment
requirement, not the board-game runtime footprint. Do not start installation,
large downloads or full system builds as an automatic workaround for low disk
space. Record exact image/tool versions, paths, limitations and the next task
in existing docs.
Keep the canonical Vivado project here; do not copy it into ~/workspace or
create a nested checkout. Linux tools/build caches may require their own native
filesystem location, which is not a second copy of the FPGA project. No SD,
JTAG, UART, PL programming or board test follows automatically from this
assessment or any later environment installation.

Research references: [PetaLinux 2023.1 requirements](https://docs.amd.com/r/2023.1-English/ug1144-petalinux-tools-reference-guide/Installation-Requirements),
[Logitech B100 USB-A/Linux specifications](https://www.logitech.com/en-ca/products/mice/b100-usb-business-mouse.910-001439.html),
[OBS canvas/output settings](https://obsproject.com/kb/obs-studio-overview),
[OBS capture-device settings](https://obsproject.com/kb/video-capture-sources),
[OmniVision OV5640 datasheet, vendor-hosted copy](https://files.waveshare.com/upload/d/da/OV5640_DataSheet.pdf).
OV5640 supports more than 720p, but a 1280x800 RAW10 MIPI mode is not validated
by changing OBS. Current source selects cfg_720p_60fps and verifies 720 lines;
preserve this baseline for the first pure-virtual-display release.

## Existing PC/UART Baseline

The preceding PC game task addressed model/ray flicker using read-only
monitoring of the existing Python process and offline replay. No new serial connection or
board operation is authorized. Board stage timing remains available; its
current saved records show slow detection and sparse UART service, which need
a separate firmware task.
Existing OV5640 -> UART -> PC integration is complete offline. Earlier logs
show 1.1-1.2 Hz and the current perf snapshot shows 0.643 Hz, below the 8 Hz
target. Stage reports have now been received; firmware optimization remains
open. Camera/six-class recognition,
thresholds, markers, canonical ray physics and the HDMI path are preserved.
`VISION_SCENE_STREAM_ENABLE=0` remains the source default; canonical build mode
`live` selects camera/fixed=0, minimal=0, green-only=0, streaming=1 at target 8 Hz.
The stream extends the existing scene_protocol owner, with one immutable active
packet and one latest replaceable observation, 64-byte nonblocking FIFO polls,
no catch-up queue and a 65%-baud traffic ceiling based on actual packet size.
Main's verbose diagnostics are disabled only in live mode. Six objects are
348 bytes/packet: 2784 B/s at 8 Hz, 24.2% of 115200/8N1. These are calculations,
not measured board performance. No frame video is transmitted.

PC command from repository root:
`python pc_vision/app.py --game --serial COM5 --baud 115200` (replace COM5 with
the manually identified UART). Requirements now include pyserial; host GCC,
NumPy and OpenCV remain required. Serial starts only for explicit --serial,
does not enumerate ports, and uses a physics-only NativeVision process.
Existing GameController/fixed models/GameView/canonical ray_game.c are reused.
Centers and directed angles follow the board's 1280x720 pixel observations;
sizes remain fixed. RX and drawing are separate; the mailbox holds one newest
complete scene, rate history 128 timestamps, result history 256 entries.
The view shows LIVE/STALE/DISCONNECTED, scene frame, actual Hz RX and RX age.
RX age is time since complete reception, not end-to-end exposure latency.

Invalid recognition/capture sends valid=0/count=0; valid empty sends
valid=1/count=0. SOURCE absence immediately removes following rays; other
objects retain the existing bounded 0.25 s observed-dropout policy, then expire.
No new complete scene for 0.25 s marks STALE but retains the last complete
models/rays; default scene timeout is now 6 s, configurable with
--scene-timeout/timeout_seconds. Pause/lock explicitly freeze display while
input continues.
Boot sends an existing scene-v1 invalid frame=tx=time=0 announcement; ordinary
tx starts at 1. PC rejects duplicates/reordering with u32 wrap handling, clears
partial/OS backlog on reconnect, and can recover a missed boot announcement
after silence plus three coherent low-uptime observations. scene-v1 has no
unique boot ID: arbitrary cross-epoch replay cannot be perfectly distinguished;
UART ordering, boot announcements and connection buffer clearing are assumed.
Photos/video/replay remain available and visibly marked as file/photo input.

Offline verification: all 26 focused pc_vision.test_game tests pass, including
strict C encoder/scheduler vs Python decoder, splits/logs/CRC/resync, sequence,
restart/reconnect/timeouts, slow complete-scene retention and measured low-rate
Hz independent of STALE, moving/rotating fixed models and C rays, SOURCE
loss, 10,000-input bounded latest delivery, photo/video/replay and original
image CLI. Existing extracted-main display/capture fault injection passes.
Old six-class synthetic known failures were not run or fixed; no overall
repository regression pass is claimed. Host GCC required its single permitted
outside-sandbox retry after WinError 623. ARM compile/link succeeded in sandbox
but size failed to launch; the same canonical entry succeeded on its single
outside-sandbox retry. No alternate toolchain/project/platform was introduced.

Strict live ARM build: text/data/bss=140599/3264/32459536, ELF32 little-endian ARM
EABI5 hard-float, existing BSP, -O2 -g3 -Wall -Wextra -Werror and existing
linker/spec/libraries. Delivery is independent under
`color_test/build/vision_ps_baremetal/output/live/`: ELF/MAP, arm_build.log,
BOOT.bin, explicit boot.bif, bootgen.log, validation.json and host_game_tests.log.
ELF is 874540 bytes, SHA256
`50391dab817447b9248e36e2596a8a0a6943360c52a81ee0df49c46e5e7d9698`.
BOOT SHA256 `f1200d4c4cc0ae4bb245e9193a1e9fc57c4e75687bf350b22ff4bb4e99bde47b`.
offline_validation.json summarizes checks; latest_scene_test.log proves the
10,000-input final display frame/center, ray_game_host.log retains the existing
C ray pass, and simulated_game.png is a visually checked software preview
explicitly marked SIMULATED INPUT / NO BOARD, never a camera/HDMI capture.
The packaging tool `tools/package_live_boot.py` checks the prior validated
input manifest, refuses BOOT overwrite, and supports --verify-only. All eight
XSA/BSP/BIT/FSBL/PS-init fingerprints match fixed_scene_validation.json. XSA
embedded BIT equals platform hw/color_test.bit. Direct BOOT parsing verifies
boot/partition checksums, exactly three non-overlapping file partitions,
FSBL and new application PT_LOAD bytes and the BIT payload after container
removal/32-bit byte swap. Bootgen emits the existing BIT memory-range overlap
warnings; generated file partition ranges and exact payload equality pass.
Prior camera/fixed/unlabelled ELFs and old BOOTs are preserved. Root
build/hw/system_wrapper.bit is still mismatched and must never enter this BIF.

No Vivado, BIT/XSA generation, real serial/JTAG/board connection, download,
SD write, reset, commit or push occurred. Next human task: use the independently
verified live BOOT with the documented matched inputs; SD boot and explicit
COM connection; one object/class, SOURCE+TARGET -> MIRROR -> Portal A/B; move,
rotate, remove SOURCE, occlude, unplug/reconnect and restart while measuring.
Target localization is 8-10 Hz, aiming around 200 ms motion response; real
camera following, end-to-end latency and field stability are NOT validated.
Detailed commands, input hashes and human SD steps are in the application and
pc_vision READMEs. Keep these checks separate from deferred PL timing/CDC work.

## Reusable Competition Skills

`skill/README.md` indexes three submission skills: `pynq-dma-contract`,
`stream-perf-analysis`, and `fpga-verification-gates`. They extract reusable
Overlay/buffer checks, cumulative performance analysis, and layered acceptance
criteria from the current design and saved observations. No production source,
build, process, serial connection, or board state was changed for this work.
The standalone Python analyzer uses a configurable stage contract. A bundled
62-row excerpt of complete reports 24/25 reproduces all 19 comparable timing
stages in the saved flicker analysis; 13 synthetic/CLI boundary tests pass.
All three skills pass the skill-creator validator. PYNQ hardware, cross-board
reuse, overall detector regressions and production timing/CDC remain unverified
or failing as recorded elsewhere; no competition acceptance is claimed.

## PC Game Flicker

- Read-only outside-sandbox CIM confirms PID 43584 runs the user's COM9/115200
  command with output `pc_vision/output/perf_20261015_230249`. Sandboxed
  Get-Process could not see it; this was not evidence of process exit. The
  existing process remains on the old imported code and was not restarted.
- Snapshot: first 293 UI-adopted scenes span 454.328 s, 0.643 Hz; receive gaps
  median 1.50 s, maximum 5.313 s, all valid. Fifty scenes lack a usable SOURCE.
  These logs do not prove wire loss or exposure-to-display latency.
- Root cause: tick expired every current track after dropout_seconds=0.25,
  confusing silence between complete scenes with observed missing objects.
  That rule predicts empty geometry for 82.7% of this snapshot's duration.
- Current tracks now remain until the configurable 6 s scene timeout;
  explicitly missing non-SOURCE tracks retain only the original 0.25 s TTL.
  SOURCE loss, invalid frames and disconnect still clear following rays.
  STALE at 0.25 s and fresh-only locking remain. RX Hz uses a bounded 10 s
  window and is no longer forced to zero merely because the scene is stale.
- All 26 game tests pass, including slow gaps through 5.313 s, explicit loss,
  timeout override, disconnect, pause/lock, C physics and file CLI regressions.
  A sandbox file-CLI subprocess failure passed on the single permitted
  outside-sandbox retry. Saved-scene replay with actual C physics has zero
  receive-silence blanks in 22,209 model / 18,762 ray checks at 20 ms steps;
  all 50 explicit SOURCE-loss checks pass. The stale playfield is pixel-equal
  to its fresh version. Evidence: `flicker_analysis.json` and the visually
  checked, explicitly offline `flicker_stale_replay.png` in that output folder.
- Complete performance report 24->25 deltas show detect_six 450.0 ms,
  process 480.0 ms, UART poll gap 240.0 ms and FIFO span 1102.3 ms mean;
  these are different metrics with different counts, not additive costs.
  No detector/firmware/FPGA changes were made. Live acceptance after a human
  normal exit/restart remains open; input throughput is still below 8 Hz.

## Live Scene Performance Investigation

- Evidence snapshot: `output/perf_live_20261015/existing_log_analysis.json`
  under `color_test/build/vision_ps_baremetal/`. First 78 live_monitor01 records:
  70.360 s, 1.094 Hz, RX median/max 812/1828 ms, processing-start delta median
  883 ms, tx deltas all 1, valid all true. Current 466-row snapshot: 378.797 s,
  1.228 Hz, RX median 750 ms, one tx delta 2. These UI-adopted logs cannot prove
  wire loss. capture_ms is VisionRunOnce entry, not exposure or function cost.
- Path: CameraStart -> VisionRunOnce -> CameraCheck -> repeat; capture overlaps
  CPU work. Existing capture/color/processing globals remain; color includes
  publish and processing stops before overlay/flush/display. UART polls are at
  publish, after display and main's existing waits. Driver waits are unchanged.
- New `vision_perf.c/.h` counts n, u64 total and maximum us for capture wait,
  invalidate, pixel check, safe copy, six-class detection, ray, overlay, flush,
  display acknowledgement, publish, encode, FIFO CPU service, poll gap, queue
  age, FIFO span, observed wire-idle upper bound, process/loop/recovery/sleep,
  report service and retry/failure/hold events. Algorithms, thresholds, markers,
  canonical physics, display driver, cache/ownership rules are unchanged.
- VISION_PERF_ENABLE=0 remains default, with no new clock reads/storage/output.
  Canonical perf mode selects full live, requires matching existing BSP reuse,
  and refuses existing diagnostic ELF/MAP/BOOT. Report period is configurable
  5000..60000 ms; this image selects 5000 ms and target 8 Hz.
- One frozen snapshot (25 stats + 6 associations), fixed 61 B rows, no printf,
  allocation, per-frame logs or historical queue. Diagnostics and scene share
  64 B per poll; only admit at a scene boundary with FIFO/shifter empty, and
  finish any partial row before another scene. Pending scenes cannot starve
  diagnostics. At most 1891 B/report, start spacing >=5 s (~378 B/s, 3.3% baud
  capacity); sparse service may take longer. Extra bytes consume FIFO service
  budget, so zero perturbation is not claimed. Frame/tx and processing-start,
  publish, first/last FIFO, idle observation, replacement/full/unobserved counts
  and byte totals are associated. TXEMPTY && !TACTIVE is a polling upper bound,
  never precise physical send time. Missing wire observations remain unknown.
- Nested process/loop/recovery/sleep and time spans cannot be added to leaf
  costs. Compare complete reports in one boot epoch: delta total / delta n;
  cumulative maxima cannot be differenced. Exclude startup/recovery windows.
  Same PC receiver/port saves performance.jsonl with --output, bounded tails,
  partial reset on reconnect and no diagnostic effect on scene freshness.
  Diagnostics have no separate CRC; check complete groups and consistency.
- Offline: strict fake-clock/FIFO tests pass stats/64-bit totals, frozen reports,
  FIFO full, partial diagnostics, pending-scene fairness, shared 64 B budget,
  packet framing, idle upper bounds, all splits/reconnect/large logs and
  byte-identical off/on transport without scheduled reports. Existing default
  capture/display fault injection passes; all 23 PC game tests pass, including
  same fake-port diagnostic persistence. All test subprocesses had timeouts.
  MinGW WinError 623 was resolved by one same-command outside-sandbox retry;
  fixed hex formatting avoids legacy MinGW 64-bit printf incompatibility.
- Independent perf output holds validation.json, matched_inputs.json, test/
  build logs and preserved_live_hashes.json. Original live outputs remain.
  Final canonical ARM compile/link/size passed Cortex-A9/VFPv3 hard-float,
  -O2 -g3 -Wall -Wextra -Werror with the existing linker/spec/libraries; ELF32
  EABI5 hard-float, text/data/bss=146719/3268/32461072, ELF 910384 B, SHA256
  b6c1538ccf8edd93103e511434036434de415dbdb63f85035fdf5007b21a22d9.
  BOOT 2262224 B, SHA256
  4f2e8716ff17f731d2e66120dc6ea129bf86475f67ff5cffcc0014b9fc04d906.
  All eight baseline input fingerprints and XSA embedded BIT equality passed
  before/after build. BOOT has exactly three checked, non-overlapping file
  partitions with exact FSBL PT_LOAD / matched platform BIT / new ELF PT_LOAD
  bytes. Existing Bootgen memory-range warnings remain; file/payload checks
  passed. All 12 original live files retain their initial hashes. No Vivado,
  BIT/XSA/platform generation, serial/JTAG/board operation, SD write, reset,
  commit or push. Temporary host translation units/executables were removed.
  Application README defines stages/metadata and human collection: same PC
  receiver, fixed scene >=120 s, moving scene >=120 s, >=3 complete reports.
- Remaining hypotheses: detector CPU cost, copy/cache cost, display waits,
  sparse FIFO service, recovery/retry waits. Only if FIFO/poll gap dominates,
  consider bounded service points in a later task; if detection dominates,
  profile internals before changing algorithms. No HDMI/class/copy removal,
  architecture/PL migration or unsolicited hardware follow-up in this task.
  计时功能已实现并离线验证，性能根因仍待板端数据确认。

## Fixed-Scene and Photo References

The second-stage fixed-scene offline validation and both strict ARM application
builds are complete. Hardware acceptance remains open. The opt-in HDMI demo
is implemented in the existing `main.c`, `vision_overlay.c/.h` and
`vision_ps_config.h`; `VISION_FIXED_SCENE_DEMO=0` preserves the camera default.
Enable it with 1 and keep `VISION_MINIMAL_TEST=VISION_GREEN_TARGET_ONLY=0`.
Camera GPIO/I2C/Gamma/capture initialization, CameraStart/CameraCheck and
recognition are excluded in this mode. No detector or physics rules changed.

The scene uses logical 1280x720 pixels and the PC model sizes/style, with an
identity mapping from the uncalibrated PC plane [0,1279] x [0,719], excluding
its GUI margins. Fixed centers are SOURCE (160,540), MIRROR (420,540), WALL
(660,550), TARGET (1100,300), A (420,300), B (860,300). The executed host path is
rightward SOURCE -> -45-degree finite MIRROR -> upward A -> rightward B exit
-> TARGET; three segments, two interactions, success=1, RAY_GAME_TARGET,
hit order MIRROR/PORTAL_A/TARGET. Segments are (199,540)->(420,540),
(420,539)->(420,328), and (889,300)->(1068,300); B exit surface is (888,300).
No early WALL or boundary hit. SOURCE tip (196,540), 3-pixel origin offset and
1-pixel epsilon all use logical pixels. Mirror length 140 is already effective.

Existing display startup confirms park on frame 1; the new branch traces and
draws once into idle frame 2, using BGR888/5760 stride/3840 active bytes per
line, flushes the 4,147,200-byte span and reuses acknowledged DisplayChangeFrame.
The steady loop only sleeps. No framebuffer was added; camera buffer layout,
safe copy and cache handling remain in the default branch. Active display data
is 2,764,800 bytes/frame (165,888,000 bytes/s at 60 Hz); no steady CPU frame
write/copy or capture traffic is added in fixed mode. These are contract
calculations, not measured throughput.

The focused host entry `tools/test_host.ps1 -FixedSceneOnly` extends existing
`tests/test_ray_game.c`, extracting actual `main.c::FixedScenePresent` with
display stubs and linking unchanged `ray_game.c`/`vision_overlay.c`. Strict
`-std=c99 -O2 -Wall -Wextra -Werror`, fixed path assertions (0.02 px intersection
tolerance; right/up/right directions), existing ray tests, BGR888/1280x720/5760
stride, row padding, buffer guards, four-corner model/cross-edge ray clipping,
and invalid dimensions/stride rejection pass. Model-only checks cover finite
MIRROR endpoints, SOURCE tip and Portal solid->ring axis; trace and drawing
receive the same constructed objects. The actual buffer PNG was visually
inspected: `color_test/build/vision_ps_baremetal/output/fixed_scene.png` is a
software preview, NOT HDMI capture. Commit stubs only check software selection
and failure handling, not real cache flush/VDMA acknowledgement.

`tools/build_vision_ps.tcl` supports VISION_REUSE_BSP=1 and VISION_BUILD_MODE=both
(or camera/fixed), with handoff/XSA equality checks and nonzero Tcl failure
propagation. The original platform-generation path remains when reuse is unset.
Both modes pass canonical strict ARM compile/link/size: Cortex-A9/VFPv3 hard-float
`-O2 -g3 -Wall -Wextra -Werror`, same Xilinx.spec/linker script/libxil/libgcc/libc/libm,
existing BSP, VISION_MINIMAL_TEST=VISION_GREEN_TARGET_ONLY=0. Source default stays
camera. No production scene, detector, threshold, physics or display driver fix
was needed; only focused test/build entry points and documentation changed.

New independent outputs under `color_test/build/vision_ps_baremetal/output/`:

- `camera/vision_ps_baremetal.elf` and `.map`: ELF 856,524 bytes, size
  text/data/bss=142,479/3,264/32,457,296; SHA256
  `7f2bf17c9bbbd50e474d825f51c430055b02719f5a7bba5525854cf155f2daf5`.
- `fixed/vision_ps_baremetal.elf` and `.map`: ELF 562,716 bytes, size
  text/data/bss=89,935/2,816/18,687,872; SHA256
  `e6654a5101b83e5bba73f51e1c98ad477f28762ad1689797d94d1f7ec487bd0c`.
  ELF32/EABI5 hard-float confirmed; fixed ELF has ray/scene drawing but no
  detector, CameraStart/CameraCheck, PsGpioSetup or captureAux.
- `fixed_scene_host.log` and `fixed_scene_validation.json` retain focused
  evidence/fingerprints. Temporary include/EXE/BGR were removed.

Root XSA and platform hw/export copies are byte-identical, SHA256
`03ae58ac8483359101e5286931effb0d84544f4b9b6c215572ff88653011e0c8`. BSP
addresses match XSA HWH (MM2S 0x43010000, S2MM 0x43000000, dynclk 0x43C00000);
stdout is UART1. Matching BIT is explicitly
`color_test/build/vision_ps_baremetal/vision_ps_platform/hw/color_test.bit`,
SHA256 `a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55`,
identical to XSA embedded BIT. Root `color_test/build/hw/system_wrapper.bit`
has SHA256 `212715e66e209e3ca6f60c97dcf6504d67d6dec297238b06a71897a38c2b1f32`
and is NOT matched to these applications; do not mix it with this XSA.
Neither BIT was modified. Existing platform FSBL remains SHA256
`c204dd713eb00693a916453700bf024e85019257856f59686956474842ceafc4`;
hw/ps7_init.tcl matches XSA. Old unlabelled ELF/MAP and existing BOOT remain
unchanged and are not the new fixed-scene delivery.

First sandbox MinGW launch failed with WinError 623; the same host command
passed on its single outside-sandbox retry. First ARM camera compile/link passed
but sandbox size launch failed (invalid argument); the same build entry passed
both modes on its single outside-sandbox retry. No alternate toolchain or copy.

No Vivado, simulation, BIT/XSA/BOOT regeneration, serial/JTAG/board connection,
programming, SD write or reset occurred. No overall project regression or HDMI
validation is claimed; old six-class synthetic failure was not run/fixed.
Next separately authorized board task: mode-specific ELF with above matched
BIT/PS init (and FSBL if later packaging SD BOOT), fixed startup without camera,
color/stride/geometry, real frame 1->2 park acknowledgement/cache behavior,
sustained HDMI and camera baseline acceptance. Existing download scripts select
old unlabelled ELF by default. Real mm calibration remains deferred; the live
UART integration is described above. HDMI sustained display and hardware
frame switching are still unverified; this round did not operate the board.

The first-stage offline photo virtual game remains an uncalibrated PC preview,
using only `sample_photo` without board connection.
`pc_vision/app.py --game --photos sample_photo` opens an independent game window
using the current canonical C six-class detector and `ray_game.c`, via one host
C bridge executable with separate recognition and physics processes. No Python
physics engine, project copy, board operation, Vivado run, firmware build/load,
or production main/config/HDMI change was made in that first stage. Existing
user work is preserved. PC preview completion does not validate physical
calibration or a real-time localization chain.

Game scenes use fixed configurable models, homography-mapped centers and
direction reference points, equal display scale, bounded dynamic stability,
pause/resume, fresh-scene lock/unlock, reset, photo browsing and snapshots.
Still photographs replace independently and do not expire; video/replay
dropouts expire from the object's last observation, SOURCE absence immediately
clears rays, and stale dynamic input clears live models then marks timeout.
Locked/paused display remains frozen while new input and expiry continue.
Four-point `plane-v1` calibration can be saved/loaded; real rectangle dimensions
and reliably visible/known four corners were not supplied, so the default is
explicitly uncalibrated preview. Do not treat default model sizes as measured mm.

Offline evidence: Python syntax and strict C bridge build pass; 16 new focused
game tests plus existing `test_ray_game.c` pass. All 77 photos render and all
77 recorded scene/ray results replay identically. On this Windows PC, C photo
recognition averaged 10.92 ms (max 32.79 ms); batch processing including PNG
output was 25.93 scenes/s, not a board/UART rate. Current fixed-model preview
hits TARGET for 073/074, MIRROR+TARGET for 075, PORTAL_A+TARGET for 076; 077 hits
PORTAL_A then MIRROR and terminates at the boundary. This intentional fixed
geometry/uncalibrated preview is not required to reproduce the raw photo's ray.
025 retains the known ambiguous Portal rejection. Old synthetic six-class
failure remains untouched; no overall regression pass is claimed.

Outputs: `pc_vision/output/photo_suite_v1/{scenes.jsonl,game_results.json,
metrics.json,game.png}` and selected 073/075/076 PNGs; matching replay evidence
is in `pc_vision/output/replay_suite_v1/`. `scene_protocol.c/.h` and the PC parser
define versioned complete integer scenes with CRC32 for offline records/future
UART integration; production UART output is not attached in this first version.
The native bridge uses processes because the existing MinGW is 32-bit and Python
is 64-bit. The restricted sandbox prevented launching that GCC (Windows error
623); strict builds and host runs succeeded outside it. The superseded DLL
attempt was removed, leaving one canonical process bridge implementation.

Remaining acceptance: actual GUI mouse/window experience, measured four-point
mm calibration, dynamic video stability, and later explicitly scoped UART
firmware integration. Live cadence evidence now exists above; stage timing,
wire-loss attribution and end-to-end latency remain unmeasured.

The deferred architecture migration targets a staged `PL streaming pixel
processing + PS scene decision` split. The transparent AXI4-Stream feature tap
now reproduces the PS detector's 4x sampling phase, exact integer HSV, and
eight class-mask thresholds. Multiplication, exact quotient correction, HSV
normalization, and class comparison are separate pipeline stages; focused OOC
timing passes the 142.857 MHz target at `WNS=+0.211 ns`. Production CSI debug
generation is disabled. The exact static MIPI input delays and generic
synchronizer-first-stage constraint now load correctly, but routed global
signoff still fails MIPI setup/hold and contains seven Critical CDC findings.
An exhaustive in-memory routed-DCP analysis has now ruled out an IDELAY-tap-only
fix in the current BUFIO topology; no failing candidate was applied to RTL.
The isolated matched-BUFG/MMCM compensation candidate also has no tested common
sampling window. Its reset controller passes behavioral tests but remains an
experimental fixture, not an enabled production clock path.
The feature tap and feature VDMA therefore have not been inserted in shadow
mode. No PS runtime, JTAG, SD, or board operation was performed for this
migration.

The current offline task addresses the reported live symptom that rays react
to WALL/TARGET but appear to pass through the changed Mirror/Portal markers.
The production C type mapping, intersections, and all real ray scenes already
pass offline, so their stable physics was not retuned without live evidence.
Instead, firmware identity and end-to-end observability are now explicit:
UART prints build `PORTAL_RAY_R2_20261013`, each `OBJECT` line includes the
collision center/axis/size, and `RAY_SUMMARY` reports detected and hit masks.
The HDMI status line now shows `R2`, current `DET` class flags, and committed
ray `HIT` flags. This separates stale-image or marker-recognition failure from
a true collision-geometry miss on the next board run. The focused ray-game and
extracted-main video-pipeline tests pass; the real-photo result remains 76/77
with all ray scenes `054`-`077` passing. The old synthetic six-class fixture
still has its documented `WALL`-only failure and was not changed in this task.

The retained 77-image fixed-camera Portal/ray regression covers
`sample_photo/001.png` through `077.png`. The canonical C detector and ray
fixture now pass 76/77 images: `001`-`024` and `026`-`077` pass, including every
ray scene from `054` through `077`; only `025` is rejected because its Portal
ring remains ambiguous, as explicitly accepted for this build. Portal endpoint
roles are determined from separate solid-dot, central-line, and ring evidence,
and SOURCE direction uses the attached white-axis/companion-body geometry.
The strict ARM ELF and three-partition `sd_boot/vision/BOOT.bin` have been
rebuilt with the R2 diagnostics. Bootgen generation passed, but the current image has not been reverse-
read or independently payload-matched because two documented `-read` command
forms were rejected during command-line parsing. The BIT was reused unchanged.
No Vivado, JTAG, SD-card, or board operation was performed.

The focused green-TARGET, ray-game, and vision-stabilizer host tests pass. The
older synthetic six-class fixture still fails at runtime with `expected six
detections, got 1` (`WALL` only); it uses the older marker fixture and was not
used to override the current 77-photo result. The separate SOURCE real-photo
test was not rerun because its external `--samples-dir` dataset is not present.

The current camera-recovery task is complete offline. Recovery now resets and
re-enables both real Digilent D-PHY and CSI AXI-Lite control interfaces on each
attempt, reads back the OV5640 MIPI/RAW10/PLL/720p contract, emits staged fault
boundaries, and reports the fallback framebuffer and display-MM2S state. The
current D-PHY register map exposes only control and version; it cannot report
HS activity, stop state, or lane errors, so a zero CSI long-packet count still
cannot distinguish sensor/physical-link/D-PHY/CSI-decode failure without a PL
observation point. No Bayer, Gamma, white-balance, recognition, SOURCE/TARGET,
HDMI RTL, JTAG, or board operation was changed or performed.

The recovery platform/BSP and FSBL were recreated from the current
`color_test/color_test.xsa`; the generated platform XSA and embedded BIT match
the root XSA and `build/hw/system_wrapper.bit` byte-for-byte. Vitis rebuilt
`camera_recovery.elf`, and Bootgen rebuilt `sd_boot/recovery/BOOT.bin` from the
new FSBL, current BIT, and new ELF. Bootgen reads three partitions with exactly
those names. Host fault-injection checks pass. The only build diagnostic is the
existing BSP `xtime_l.c` informational `#pragma message`; Bootgen reports its
usual Zynq partition-range overlap warnings and completes successfully.

Keep PYNQ board work paused. The Bayer contract is BGGR/Xilinx phase 3 and has
now been confirmed by the latest red/blue hardware captures. The PL
white-balance validation point was changed from R/G/B 1.5/1.0/1.5 to unity,
and a new BIT/XSA, ELF, and `sd_boot/vision/BOOT.bin` were built offline. The
current image has since been reported successful by the user, although the
HDMI/UART evidence and negative-scene calibration have not been retained for
independent review. A separate PC/PYNQ OpenCV utility recognizes the supplied
pure-green circular target from the five real-scene screenshots without
requiring the former white-ring/black-center marker.

The bare-metal pure-green TARGET integration is now complete offline. The new
sampled HSV/component module and HDMI/UART call path pass the synthetic tests
and the five-image C/Python comparison. The former apparent Python/GCC timeout
was a Codex sandbox denial on GCC output files, not a compiler or detector
hang; a staged diagnostic run outside that sandbox completed in about one
second. Vitis rebuilt the strict ARM ELF and Bootgen packaged the matched FSBL,
BIT, and ELF into `sd_boot/vision/BOOT.bin`. Direct Zynq-7000 header parsing and
payload comparison verify all three partitions. The new image has not been
copied to SD or run on hardware by Codex; the user subsequently reported that
the current result succeeded, but no HDMI/UART acceptance record was supplied
for independent review. A self-contained delivery snapshot is being kept in
`green_target/` with the rebuild inputs, verified boot artifacts, PC reference,
and five real-image regression samples.

The earlier six-class Portal-MVP baseline was rebuilt offline for Zynq-7020.
Its strict ARM ELF and a new three-partition
`sd_boot/vision/BOOT.bin` are verified below. No JTAG, `hw_server`, SD-card, PL,
or board operation was performed.

A self-contained `detector/` delivery folder now packages the six-class source,
PC references, necessary Vivado project inputs, XSA, matched FSBL/BIT/ELF/BOOT,
and all 30 supplied 50 cm real-image samples. Generated Vivado/Vitis caches and
temporary test outputs are excluded.

The six-class bare-metal path now also contains the Portal ray-game MVP.
`VisionDetection[]` is converted to framebuffer-independent `SceneObject[]`;
`ray_game.c` selects the nearest forward intersection and emits clipped
`RaySegment[]` for finite mirrors, oriented WALL OBBs, paired bidirectional
Portals, TARGET success, the screen boundary, and a 16-interaction limit.
`vision_overlay.c` only renders the segments with a black outline and yellow
core plus a small status bar. Detection boxes, labels/confidence, center crosses,
and success effects are disabled on the default game path.

The current source keeps mandatory two-part SOURCE recognition and OBB boundary
physics, but the production game path no longer calls the all-object temporal
stabilizer. The first valid raw SOURCE scene enters `ACTIVE` and commits a ray
in the same frame; subsequent valid scenes replace it immediately. A detector
or scene-conversion failure retains the last display ray, but a successfully
detected scene without SOURCE clears it immediately and returns to
`ACQUIRE_SOURCE`. This prevents the white playfield border in `001` or an
orange Portal ring from visually inheriting the previous SOURCE ray. SOURCE
movement and non-SOURCE object disappearance still recompute in the same frame.

SOURCE part collection now keeps the existing fixed limit of 64 color parts
and 64 white parts but divides the sampled frame into a 4x4 grid with four
replaceable slots per region. Within a region, higher-support components replace
smaller fragments, so row-major discovery order no longer reserves all slots
for the top of a warm scene. `VISION_TRACE` reports total, kept, and overflow
counts plus the 16 per-region counts for each part type. Strict host tests,
including a bottom-frame marker hidden behind more than 64 earlier color and
white fragments under the former collector, pass. The 30-image marked-SOURCE
regression remains 20 accepted and 10 intentionally ambiguous rejections with
the same 9.3-degree mean and 31.6-degree maximum error. No SOURCE pairing,
validation, selection, or direction rule changed, and no Vivado, BIT, or board
operation was performed for this collector change.

TARGET is an immediate, non-blocking `target_reached` latch. Its terminating
segment is committed and remains visible on repeated identical frames; later
valid scenes can replace the ray without moving SOURCE. Portal transfer now
projects direction onto the entry solid-to-ring axis and its 90-degree normal,
rebuilds from the exit basis, preserves signed longitudinal position, switches
the exit side, normalizes direction, and offsets the new origin along that
direction. Strict ray-game and extracted-main host tests pass.

The direct raw-detector complete-video gate now passes. Real flip-frame traces
showed that independently shifted scalar endpoint ROIs could score a solid as a
ring and a ring arc as a solid; black-center evidence was not responsible. A
local full-resolution white-component topology check now resolves direction
only when both scalar assignments are already valid and the component evidence
is decisive. The 75.767 s capture has zero raw Portal-axis flips in 3,836
stationary steps, 2,241 ACTIVE frames with no zero ray, 218 Portal transfers
within 0.86 px, one TARGET event, and zero MIRROR residual. Strict host tests and
all ten Portal A/B static PC/C checks pass. The current strict ARM ELF and
`sd_boot/vision/BOOT.bin` have now been rebuilt and payload-verified from this
source; no PL generation, SD copy, JTAG, or board operation was performed.

## Six-Class Recognition Sample Intake

- The completed pure-green `TARGET` path is the protected baseline. Samples for
  all five additional classes (`MIRROR`, `PORTAL_A`, `PORTAL_B`, `WALL`, and
  `SOURCE`) have now been supplied, and six-class implementation is authorized.
  Development remains in
  `color_test/software/vision_ps_baremetal/`; do not edit the delivery snapshot
  until implementation and regression checks are complete.
- All target and object captures use a camera height of 50 cm.
- The five original unmarked `SOURCE` single-object PNG screenshots are retained
  as negative references. They were received on 2026-10-05.
  `102258` is center, `102343` upper-left, `102330` upper-right, `102316`
  lower-right, and `102358` lower-left. The files remain in the user's
  `Pictures/Screenshots` directory. Their PNG canvas dimensions vary, while the
  user confirmed the source HDMI signal was unscaled 1280x720. They are no
  longer valid SOURCE inputs: the generic SOURCE path is disabled and an
  unmarked warm component must not produce any SOURCE detection or ray.
- The current TARGET-only overlay reports zero detections in all five SOURCE
  views and about 36-37 ms processing time. UART text is intentionally excluded
  from the five-class sample intake and will not be requested. The triangle
  appears orange-brown under the current imaging path, not strongly magenta;
  final classification must use measured scene color and triangle geometry,
  especially to avoid confusion with orange `PORTAL_B`.
- The revised SOURCE has a white band covering the non-emitting side, leaving
  one orange-red corner as the emission side. Thirty real references cover five
  positions at 0, -45, -90, -165, and -180 degrees, plus the supplied +45,
  +90, +135, mixed-object, and near-border captures. The dedicated sampled-grid
  detector pairs adjacent orange-red and bright low-saturation components,
  defines direction as white-centroid to color-centroid, and takes a robust
  front-region projection along that vector as the tip. Candidate support is gated by
  area, gap, ratio, aspect, fill, and centroid separation; ranking favors
  compact filled pairs so large wood/highlight regions cannot win by area alone.
  The former “narrow endpoint is the tip” assumption and diagnostic API were
  removed. Distance and materially different lighting coverage remain open.
- SOURCE local full-resolution refinement feasibility is now established
  offline without changing the production detector. Across all 30 real S0
  captures and 16 step=4 phases, the unchanged target pair passed coarse gates
  in 292/480 phases. A complete-pair-triggered ROI recovered only 293/480,
  while a retained SOURCE-color-triggered step=1 ROI recovered the same full
  color/white pair in 480/480; +16 px completely covered all 480 current real
  pairs. Refined per-image white-count CV had median 0 and worst 0.00694, and
  white PCA phase-angle span had median 0 and worst 0.742 degrees. The 188
  coarse pair failures almost always retained both parts (187 color and all
  188 white); 172 included sampled color-axis failure, confirming coarse
  representation instability rather than physical white-band disappearance.
  Full-resolution PCA, attachment, center ratio, and taper still overlap hard
  negatives or reject real positives, so no new hard structure gate is
  justified. Architecture B is the recommended experimental patch direction,
  but a fixed +16 px color-only margin is not scale-general in synthetic
  fixtures. On the 30 real positives plus ten real hard negatives, B +16 used
  27.57 ROIs and 16,972 ROI pixels per phase-frame on average (1.84% of
  1280x720), with 46 ROIs and 90,712 pixels worst case. The existing C SOURCE
  regression remains 20 accepted / 10 fail-closed. Raw evidence and the full
  conclusion are under `output/source_local_refinement/`; no production source,
  model, Vivado, BIT, BOOT.bin, or hardware operation changed.
- The Architecture-B formal-patch experiment is implemented in `vision_ps.c`
  behind the host-only `VISION_SOURCE_REFINEMENT_DIAGNOSTICS` build. Normal
  builds continue to use the existing fail-closed SOURCE detector because the
  experimental acceptance is not regression-safe. The path uses every retained
  coarse color part as a trigger, a margin of
  `clamp(ceil(3/8 * max(color_bbox_w,color_bbox_h)),12,24)` pixels, optional
  nearby coarse-white extension plus 8 pixels, and a bounded 240x240 retry only
  for a large color whose refined white is clipped. Each ROI is at most 57,600
  pixels and reuses existing static masks, visited storage, queue, wall-marker
  scratch, and integral storage; production code uses no dynamic allocation.
- In the formal C 16-phase run, the experimental path accepted real S0 in
  480/480 phases and scale fixtures in 48/48. The selected pair matched and its
  ROI fully covered the reference in 478/480 real phases; two phases selected a
  different plausible local pair even though all color triggers were refined.
  The broad sanity-only acceptance failed the required negative regressions:
  the ten default-phase expected rejects became 10/10 accepts, unmarked SOURCE
  was accepted in 66/80 phases, real Portal-B in 42/80, real WALL in 77/80,
  HN_TRI_WHITE/HN_CENTER_RATIO/HN_CLUTTER in 16/16 each, and one Mirror capture
  in 5/16. No PCA, white-normal, attachment, taper, or narrow center-ratio gate
  was added to conceal these failures. On real S0 it averaged 30.97 ROIs and
  86,848 pixels per phase-frame (9.42% of 1280x720), with P95 126,776 and worst
  272,107; across the complete matrix the averages were 20.27 ROIs and 62,872
  pixels (6.82%). The maximum single ROI was exactly 57,600 pixels. Default host
  tests and the 20-accepted/10-rejected real SOURCE regression still pass.
  Detailed per-phase evidence and false-positive geometry are in
  `output/source_architecture_b_patch/`. This experiment is not ready for board
  validation; the next SOURCE task is a negative-discriminating representation,
  not threshold tuning on PCA/attachment/taper.
- `WALL`: the former unmarked references (`103059`, `103148`, `103117`,
  `103108`, and `103154`) were superseded on 2026-10-05 by five captures of a
  revised WALL with one inset white transverse bar at each end. `121951` is
  center, `122033` upper-left, `122022` upper-right, `122014` lower-right, and
  `122040` lower-left. The white bars remain separated from the outer boundary
  by a dark border, so they can form a rotation-independent marker pair while
  the dark body stays connected. These five stamps are now the authoritative
  WALL entries in `tests/test_six_class_real.py`; the old images remain useful
  only as unmarked-WALL negative/fallback evidence.
- WALL position coverage is complete. Rotation, distance, lighting,
  multi-object, and confusing-background coverage remain open.
- Before the marker implementation, the legacy dark-body WALL detector was
  baselined against the five revised references: PC and C both detected WALL
  in 0/5, and C also reported a background `PORTAL_B` in lower-left `122040`.
  The cropped image dimensions range from 411x273 to 498x292. This established
  that the revised object must be generated from the two white transverse bars
  and validated by the dark region between them, rather than relying only on
  the legacy adaptive dark component.
- The revised WALL detector now pairs two elongated bright components only when
  their sizes agree, axes are parallel, both bars are transverse to their
  center-to-center line, spacing is plausible, and at least 70% of the central
  corridor is dark. Its geometry is rotation-independent; the old adaptive
  dark-body detector remains as an unmarked-WALL fallback. C uses a stronger
  sampled-grid local-brightness delta than PC because a weak delta lets
  diagonally interpolated body edges bridge both markers at 4x sampling.
- `PORTAL_A`: five single-object PNG screenshots were received on 2026-10-05.
  `103731` is center, `103754` upper-left, `103747` upper-right, `103739`
  lower-right, and `103801` lower-left. Their cropped dimensions vary from
  582x407 to 643x432. The body appears as a blue-gray elongated rounded bar.
  Each view clearly shows a white ring at the left end and a white solid dot at
  the right end, providing both a Portal validation pattern and an orientation
  cue. `PORTAL_A` and `PORTAL_B` should share this geometry detector and differ
  only by measured body color.
- PORTAL_A position coverage is complete. Rotation, distance, lighting,
  multi-object, and confusing-background coverage remain open.
- `PORTAL_B`: five single-object PNG screenshots were received on 2026-10-05.
  `103926` is center, `103948` upper-left, `103942` upper-right, `103934`
  lower-right, and `103956` lower-left. The cropped images are 610-747 pixels
  wide and 416-467 pixels high. The body appears tan/orange. All five views
  show the white solid dot at the left end and the white ring at the right end,
  opposite the supplied PORTAL_A pose.
- Both Portal classes must support arbitrary in-plane rotation. The common
  detector must derive the body major axis, inspect both endpoints along that
  axis for exactly one solid dot and one ring, and use their identities for
  orientation without assuming a fixed left/right order. Only measured body
  color may distinguish `PORTAL_A` from `PORTAL_B`.
- PORTAL_B position coverage is complete. Real rotated-view, distance,
  lighting, multi-object, and confusing-background coverage remain open.
- `MIRROR`: five single-object PNG screenshots were received on 2026-10-05.
  `105348` is center, `105418` upper-left, `105409` upper-right, `105401`
  lower-right, and `105426` lower-left. The cropped images are 576-670 pixels
  wide and 386-461 pixels high. The body appears pale yellow/cream with square
  corners and one dark solid circular marker near each end, distinguishing its
  endpoint pattern and silhouette from the two Portal classes.
- MIRROR position coverage is complete. Rotation, distance, lighting,
  multi-object, and confusing-background coverage remain open.
- Real-image sampling established the active color ranges: SOURCE H=11..19,
  S>=126, V>=73; WALL V<=54 despite high warm-color saturation; PORTAL_B
  H=16..20/S>=108/V>=86; MIRROR H=19..24/S>=95/V>=99; and PORTAL_A requires
  both a washed-blue range and a low-value warm-shadow range. White Portal
  markers require a substantially lower V threshold than the former synthetic
  defaults. The C and PC threshold tables now reflect these observations.
- The current implementation adds `vision_detect_objects_bgr888()` for the
  five non-TARGET classes and makes `vision_detect_bgr888()` merge that result
  with the dedicated pure-green TARGET detector, then sort and suppress strong
  bbox overlaps. Generic morphology now operates on the 320x180 sampled grid
  instead of full resolution, oriented fill uses the component major/minor
  axes, area is consistently estimated in full-resolution pixels, the active
  main path is six-class, and UART uses `OBJECT class=...` records. Synthetic
  Portal rotation cases cover 0, 30, 60, 90, 135, and -45 degrees.
- BLACK/WHITE marker bits are now preserved across body-mask morphology, so a
  one-cell sampled Portal ring is not erased. Portal direction now evaluates
  both endpoint assignments at both configured offsets and selects the
  strongest solid-to-ring evidence instead of accepting the first weak match;
  this fixes the former 135-degree to -45-degree reversal. Strict compilation
  and the complete C synthetic executable pass, including Portal angles 0, 30,
  60, 90, 135, and -45 degrees, WALL angles 0, 35, 90, and 155 degrees, the
  unmarked brightness-gradient WALL fallback, and Overlay clipping/padding.
- The isolated PC/C parity suite was run outside the sandbox and passed all five
  tests after recording the intended sampled-grid minimum-area tolerance and
  excluding the obsolete marker-based PC TARGET fixture (the dedicated green
  TARGET tests remain authoritative).
- `tests/test_six_class_real.py` now provides a repeatable 25-image PC/C check
  over the supplied 50 cm captures. Its first run established the real baseline:
  C detected SOURCE 5/5, WALL 4/5, PORTAL_A 2/5, PORTAL_B 4/5, and MIRROR 0/5.
  Most extra C detections were vertical/dark image-edge regions classified as
  WALL. Trace evidence showed that the 4x sampled endpoint test missed thin
  Portal rings and some Mirror disks; PORTAL_A `103754` also had sampled aspect
  1.94, just below the former 2.0 limit.
- The current detector samples endpoint markers from the original
  full-resolution BGR frame, permits Portal aspect down to 1.8, recognizes
  Mirror disks by local endpoint contrast as well as absolute black, lowers the
  real-scene white-marker floor to V=70, adds SOURCE compactness/minimum-size
  gates, and replaces the global WALL mask with a local-brightness mask plus a
  50 cm area range. The PC reference preserves raw thin marker masks and applies
  corresponding adaptive black/WALL logic.
- The PC synthetic WALL diagnosis showed that adaptive segmentation retained
  13,251 of 13,255 raw dark pixels and produced `color_fill=1.0`; its only
  rejection was `class_max_area`. The old fixture occupied 18.4% of its small
  frame, unlike the supplied 50 cm captures. The fixture now occupies about
  4.6%, and the production maximum was restored to 5%. PC/C parity then passed
  all five tests.
- Endpoint validation now tries both 0.44 and 0.37 of the sampled major-axis
  length. This covers the real endpoint position and the synthetic geometry
  without making orientation axis-aligned. The PC reference has an equivalent
  sampled Portal fallback when a thin or low-contrast ring does not form a
  closed contour. WALL local contrast is now 10 with a 2.0 minimum aspect.
  Real regression also validates the expected center/upper-left/upper-right/
  lower-right/lower-left quadrant, preventing a background shadow from passing
  in place of the object.
- After the revised WALL implementation, the formal PC/C parity suite passes
  5/5 and the PC synthetic suite passes 8/8, including WALL at 0, 35, 90, and
  155 degrees. Both PC and C find the intended WALL with the correct quadrant
  in all five revised real references. PC produces exactly one WALL in 5/5; C
  is exact in 4/5 and produces WALL plus the already-baselined, spatially
  separate background `PORTAL_B` on `122040`. Neither implementation produces
  a WALL on the other 20 supplied SOURCE/Portal/Mirror images. The subsequent
  first full 25-image diagnostic batch was exact for PC in 23/25 and C in
  19/25. The `122040` false `PORTAL_B` had only 1,360 sampled-area pixels,
  versus 2,096 pixels for the smallest valid 50 cm Portal, so both PC and C now
  enforce a 1,800-pixel Portal minimum. The repeated full batch before
  low-light endpoint work was exact for PC in 23/25 and C in 20/25: `122040`
  contained only WALL, while all five real PORTAL_B views remained 5/5. The
  failures were PC PORTAL_A `103754`/`103801`; C PORTAL_A
  `103731`/`103754`/`103801`; and C MIRROR `105418`/`105426`.
- Low-light attempt 1 added inner endpoint offsets (0.30 and 0.25 of the major
  axis) plus a sampled-ring topology margin. It fixes the two PC PORTAL_A
  misses and preserves the 8/8 PC synthetic suite, but does not recover the C
  misses because the 4x sampled body axis and each endpoint's best longitudinal
  offset differ. Low-light attempt 2 adds +/-0.15 minor-axis compensation and
  independently retains each endpoint's best evidence. All five unique
  low-light captures then pass PC/C (`103731`, `103754`, `103801`, `105418`,
  and `105426`), but the complete C synthetic executable rejects the change
  with `invalid two-disk portal accepted`: evidence from different sample
  positions can be combined into a false solid-plus-ring assignment. Per the
  two-attempt stop rule, no third algorithm change or full 25-image batch was
  run. The next task should require a coherent solid/ring pairing across nearby
  longitudinal/transverse samples instead of independently combining endpoint
  maxima. No ARM build, Bootgen, or hardware operation is claimed.
- The requested coherent-pair follow-up was attempted twice. First, Portal and
  Mirror endpoint evidence was restricted to sample pairs whose longitudinal
  and transverse grid indices differ by at most one; the strict C executable
  still failed with `invalid two-disk portal accepted` because sampling just
  outside a solid disk creates a ring-like annulus in the adjacent cell.
  Second, a ring candidate was suppressed when the same endpoint had solid
  evidence in its immediate sample neighborhood. The strict executable stopped
  earlier in its rotation loop with `rotated portal angle=0 missing/wrong
  (-180)`, so the later two-disk negative was not reached in that run. The
  exclusion suppresses valid ring evidence under shifted sampling and leaves a
  reversed assignment.
  Work stopped at the two-attempt limit before low-light or full real-image
  reruns. A future task should classify ring topology within one physical
  center (for example, balanced annulus support around the center) rather than
  infer marker identity from neighboring center samples.
- The single-center topology follow-up measured each marker annulus in four
  screen quadrants. Refined centers for the three low-light PORTAL_A rings had
  opposite-quadrant support of 0.79, 0.53, and at least 0.29; the six synthetic
  rotated rings measured about 0.31--0.40, while both endpoints of the
  synthetic two-disk negative measured 0.00. Attempt 1 therefore required
  0.10 opposite-quadrant support and ran a fine center search only after the
  coarse Portal path failed. Strict C regression passed, as did four of the
  five unique low-light captures, but C still missed `103731` because only one
  half of that real ring is visible.
- Attempt 2 added endpoint-axis outward/inward annulus statistics. `103731` has
  0.31--0.42 outward white support and 0.00 inward support at the outer sample;
  the two-disk negative has 0.00 outward and 0.40--0.47 inward support there.
  A partial ring is therefore accepted only at a major-axis offset of at least
  0.40, with at least 0.15 outward support and a 0.10 outward-over-inward
  margin. Strict C regression, the 8/8 PC suite, and all five unique low-light
  PC/C checks pass. The full host script then passed C and green TARGET but
  timed out while entering parity at 120 seconds; isolated parity also produced
  no result before a 300-second timeout, so parity is not claimed. The complete
  25-image real batch is exact for PC in 25/25 and C in 24/25: C correctly
  detects WALL on `122022` but adds a separate false `PORTAL_B`. Work stopped
  at the two-attempt limit. The next task should diagnose only that `122022`
  refined-ring false positive and the fallback performance cost before any
  further threshold change. No ARM build, Bootgen, or hardware operation is
  claimed.
- The two remaining host issues are now closed without changing any global
  recognition threshold. On WALL reference `122022`, PC and C both form a
  warm-color component at the left image edge. PC measures bbox `(0,4,54,267)`,
  area 10,361.5, aspect 5.02, fill 0.735, circularity 0.276, passes geometry,
  and first rejects it at marker validation with `no_white_round_markers`. The
  4x C mask measures bbox `(0,4,120,264)`, area 13,248, aspect 2.86, fill 0.63,
  circularity 0.13, and angle 85 degrees. Its coarse marker pair fails, but the
  fine single-center fallback had synthesized a solid/ring assignment from the
  image-edge brightness transitions. Fine Portal fallback is now allowed only
  for components fully inside the sampled frame; the coarse path remains
  available at frame edges. `122022` consequently reports only WALL.
- The parity timeouts were a test-environment location fault, not an algorithm
  loop or large input. `test_pc_parity.py` created and executed its probe below
  repository `color_test/build`, which stalls in the current restricted host;
  the same probe in system TEMP compiles in about 1.06 s and a scalar call
  returns in about 0.18 s. The parity fixture now uses the default system
  temporary directory. Per-case wall-clock times (each isolated run includes
  compilation) were 1.988 s for BGR/HSV, 3.949 s for threshold/Hue-wrap,
  1.846 s for synthetic classes, 1.651 s for combined/frame-edge, and 1.656 s
  for minimum-area quantization. Threshold/Hue-wrap is the slowest because it
  launches the short-lived probe repeatedly. The normal one-compile parity run
  passes 5/5 in 4.728 s (4.323 s inside unittest).
- Final offline regression passes: strict C host tests including the two-solid-
  disk Portal negative and all Portal rotations; green TARGET host tests; PC
  synthetic 8/8; parity 5/5; the five unique low-light PC/C checks 5/5; and the
  complete real-image batch PC/C 25/25. The recognition algorithm and test logic
  were not changed during the subsequent ARM build and Bootgen task.

## PYNQ Migration Status

### Offline Image Assessment (2026-10-16)

Decision: reuse the existing image as a **candidate Linux runtime**, with native
C/C++ and staged PL work. No demonstrated need to rebuild the kernel/rootfs or
install PetaLinux on this PC. Boot is now confirmed by authorized COM9 diagnostics;
exact board revision, custom PL operation and 1280x800/60 Hz remain **unverified**.
This is not complete board-game acceptance.

### Authorized Runtime Evidence (2026-10-17)

Latest offline SDK result (2026-10-19; no board access):

- Full local image SHA256bcee01b8... matches the earlier audited image. Extracted
  .config, Module.symvers and generated autoconf/compile/ARM offsets/bounds match
  the recorded running kernel. Original zocl SHA256a923c535... has154 imported
  CRCs all matching this symbol table; no substitute symbol table was generated.
- Official Yocto3.0.4 GCC9.2.0/binutils2.32 and reviewed official relocation
  scripts were used in two independent private ext4 prefixes. This matches the
  compiler version, not original Xilinx binary identity. QEMU/Sato user headers,
  DT/kernel/rootfs are not board inputs; target compilation uses -nostdinc and
  -msoft-float with the frozen kernel headers. GCC12/Arm9.2.1 were not substituted.
- Generated generic-y wrappers plus ARM generated-y syscall/machine headers
  from exact packaged tables/rules; static x86-64 fixdep/genksyms/modpost/
  mk_elfconfig and178 ARM devicetable definitions. All11614 original files remain
  unchanged after preparation and after each external-module probe build.
- auto.conf.cmd and its original path/command guards are preserved verbatim.
  Standard external M= mode uses immutable config inputs and does not include
  that guard file; top-level prepare/syncconfig/internal builds remain unsupported.
  No guard removal, forged compiler identity or silent config regeneration.
- Both prefixes produce ARM32 EABI modules with the exact current vermagic;
  all3 probe imports match CRCs and the probe export CRC is0xeabe998c in both.
  Compile-time checks match prior zocl disassembly: BO sizeof248, bank236,
  flags240, gem_base.size136. These are scoped build-context checks; modpost
  importing CRCs from Module.symvers alone would not independently prove layouts.
- SDK environment check attempt1 failed missing asm/unistd-eabi.h; failed tree,
  prepared archive and raw error log retained. Exact ARM generated-y completion
  was its sole retry, and passed both prefixes. Separate host /tmp tmpfs loss
  was corrected once into persistent private /var/tmp. Native2/2 and all prior
  board/sampling failures remain; no corrected-driver validation was attempted.
- Portable bundle `output/build/kernel_sdk_20261019/external-module-sdk.tar`,
  SHA256ab321525f9669b1894cbd30280c5e2289fb42ab614a69ed505c9c011f33d63df,
  includes offline installer, prepared inputs/helpers, host make, locked hashes
  and migration procedure. Tested Ubuntu26.04.1/WSL2 x86-64; requires Linux,
  Python3.12+, glibc>=2.38, case-sensitive filesystem and stated host utilities.
  Five host negative-evidence tests pass. No global installation/config change,
  native third attempt, full zocl build, device open, module load or DMA occurred.
- Sources/commands/receipts/ELF+CRC+path review/hashes/remaining gates are bound
  in `output/build/kernel_sdk_20261019/manifest.json` and `REVIEW.md`.

Latest corrected-driver build result (2026-10-19; environment path STOPPED2/2):

- User explicitly authorized building/ABI-qualifying the corrected driver and,
  after qualification, valid-layout/complete-frame capture. Reused ordinary
  Windows COM9 Console without control-line changes. This round ran as Linux
  user1000; no sudo credential, PYNQ/libcma import, DRM/xlnk open, module unload/
  load, MMIO, reset, stream, allocation, DMA or PL/clock/display write occurred.
- Preflight retained the same boot and zocl refcnt0/kds_mode0. Running IKCONFIG
  equals installed build .config SHA256f2fa6d9b...; Module.symvers SHA25691f20404...
  and generated autoconf/compile/offset headers exist. Native GCC is7.3.0; the
  kernel was built with GCC9.2.0. fixdep/modpost and standard generated ARM
  wrappers are absent, but their source/rules and native bison/flex are present.
- Downloaded only69 required zocl/common-driver/header files from official
  commit2d6bfe4ce91051d4e5b499d38fc493586dd4859a. Every file's Git blob SHA1 was
  checked against that commit's tree; bundle SHA256
  9eb8b0457d71528e1a9af090eb83e3d676ee03281c4e98730a2ef3c8a40b1bd0.
  Applied the previously reviewed single release-order correction and bound
  its source hash. No other driver behavior or production source was changed.
  Staged at `/tmp/codex_camera_dma_driver_3vb6s8kj`; copied only the47,028,510B
  installed header/build input tree there for isolation, not the FPGA project.
- Environment attempt1: external-module make entered kds_core/cu_hls compile,
  then failed `asm/bitsperlong.h: No such file or directory`. No zocl release
  function or .ko was compiled. Full log SHA256d1fc8006... retained as
  external_module_build.log; no automatic retry.
- After reading exact Kbuild rules, used the sole environment retry in the same
  private tree. Added a private tools-only target for standard scripts/ARM
  wrapper generation; normalized only private input timestamps because the
  board clock predates packaged files. No system clock or installed file change.
  `KCONFIG_NOSILENTUPDATE=1` prevented a silent .config rewrite. fixdep/Kconfig
  tools built, then syncconfig refused: **The configuration requires explicit
  update.** Log SHA256ab678631... in private_kbuild_tools.log. Module compilation
  was not reached in attempt2; no bypass/reconfiguration/third build was run.
- Final readback proves more than a GCC version issue: installed auto.conf.cmd
  has FORCE guards for the old arm-xilinx-linux-gnueabi GCC9.2 compiler command,
  linker, srctree and host-tool command, including ALINX's original Yocto paths.
  A nominal GCC9.2 binary alone is not a demonstrated solution. Need a relocatable,
  prepared external-module build context with the exact config/generated inputs/
  symbol CRCs and a reviewed relocation/toolchain procedure. No ABI gate can be
  signed from matching release text, source patch or userspace-model tests.
- Same boot; corrected zocl.ko absent. Original module SHA256a923c535... and loaded
  Build-ID54740b32... unchanged, refcnt0; FPGA state operating. Original kernel
  .config/Module.symvers/autoconf/compile hashes unchanged, private .config still
  equals system/running config. Private failed receipts/logs retained; no frame
  buffer, module checkpoint or image is fabricated. Previous sampling and board
  failure ledgers remain; this patch has0 actual ABI/runtime design validations,
  while this native build environment has2/2 failures and0 retries left.
- Evidence: `output/build/game_app/camera_dma_driver_20261019_manifest.json`/
  analysis and hash-bound sources/build worker. Raw log/JSON stems (common
  game_linux_native_camera_baseline_ prefix): dma_driver_preflight_20261019_1b047f32,
  dma_driver_build_20261019_b70f0c10, dma_driver_status_20261019_6ceb7c21,
  dma_driver_prepare_inputs_20261019_cdf66d08,
  dma_driver_environment_retry_20261019_c1861a23,
  dma_driver_status_20261019_0fcd5253, dma_driver_final_read_20261019_fd19cd1f.
  Prior source/patch/CPU tests and initial sensor failure manifests remain intact.

Latest DMA-path result (2026-10-19; userspace tests PASS, allocator gate BLOCKED):

- Current scope authorized safe single-frame DMA and valid-layout/full-frame
  acceptance using the already loaded design. Read-only COM9 discovery and
  module inspection retained the same boot and did not open DRM/xlnk devices,
  import PYNQ/libcma, allocate a BO, start DMA, clear VDMA errors, stream the
  sensor, reload PL or change clocks/HDMI/services. CPU-only files were staged
  under a private /tmp directory. No complete hardware frame was acquired.
- `/dev/dri/renderD128` binds the active zocl module, not an HDMI allocator
  inferred from the DRM node name. File SHA256a923c535d807917b733611bc26f440fb07a0aec757954bc5436086e809584bee,
  109428 bytes, Build-ID54740b32e41e76742339732afed28f80b84b01bc matches the
  running module note. Version2018.2.1/srcversion533BB7E5866E52F63B9ACCB and
  vermagic5.4.0-xilinx-v2020.1 were recorded. Installed XRT userspace reports
  2.6.0/2d6bfe4ce91051d4e5b499d38fc493586dd4859a; it does not prove kernel
  module source equivalence. Targeted /usr/src and DKMS source paths and package
  ownership yielded no matching source/build package; broader absence is not claimed.
- The actual ELF ioctl table and functions establish create/map/sync/info ABI
  and per-file GEM lookup. However, CMA `zocl_free_bo` calls
  drm_gem_cma_free_object at0x4c2c, then loads bank/size from the same r4 object
  at0x4c30/0x4c48. Linux5.4's documented helper frees the object, so this is an
  unresolved read-after-release risk, not a qualified safe release backend.
  Reference: https://raw.githubusercontent.com/torvalds/linux/v5.4/drivers/gpu/drm/drm_gem_cma_helper.c .
  The running kernel helper body/source is not independently matched here;
  no allocation/free or crash was executed. Save fields before freeing and
  verify the matching kernel helper, rollback, GEM/VMA references and process
  exit ownership before admitting this path. No kernel patch/replacement was made.
  Legacy libcma/xlnk lifetime/sync gates remain unresolved; no dma_heap,
  udmabuf/u-dma-buf or uio_dmem alternative was found in the targeted interfaces.
- User authorized online source lookup. Official XRT tag202010.2.6.655 resolves
  to2d6bfe4ce91051d4e5b499d38fc493586dd4859a. PYNQv2.6.0 qemu.sh selects that
  tag; its pre.sh builds zocl via PetaLinux. The official meta-xilinx
  rel-v2020.1 zocl recipe names the same commit. That source's CMA free/stat
  order matches the observed instructions, while current upstream places the
  statistics before free. Saved `camera_dma_20261019_zocl_release.patch` moves
  only that statistics call before free; unique source hunk checked offline,
  not compiled, installed or exercised. References and fetched-file hashes in
  `camera_dma_20261019_official_sources.json`/release metadata. This identifies
  a concrete correction without proving the old module's complete build inputs.
  Kernel build .config equals running IKCONFIG (SHA256f2fa6d9b...); Module.symvers
  and System.map exist, but no vmlinux, prepared fixdep/modpost executables or
  targeted kernel .c files were found. It is a header build tree, not a
  complete verified driver build environment. No system/module change was made.
- Canonical `pynq_vision/vdma.py` now checks whole nonoverlapping 32-bit frame
  spans and actual buffer capacity before MMIO, offers fixed slot0/FrameCntEn hardware one-shot setup,
  requires complete+HALTED+RS0 before CPU copy and no new errors afterward, rejects active-ring copy and
  missing/void/failed cache status, and covers EOLLateErr. Stop confirms HALTED
  without resetting/clearing the failed channel. `hardware.py` refuses an
  unqualified backend before PL/device actions and retains owners on stop or
  release failure; an unknown release outcome blocks automatic retry, including
  subsequent close calls. Original startup failure stage is retained. There is no
  allocator backend, current-clock reuse orchestration or process keeper yet.
  The legacy orchestration remains inaccessible behind this gate; one-shot
  register logic is tested in models, not admitted as an operational capture path.
- Host `test_offline` + `test_diagnostic`:22 PASS. Board Python3.6.5 CPU/Fake-only
  suite:19 PASS,0 failures/errors, with PYNQ import blocked and no recorded
  relevant device-open attempts. The task source ZIP SHA256 is
  7eb4c794300bbbafd3b269b882a85c4fc77e5b81591bb4a94c3fb32be577b0ad
  (revision3; revision1/2 ZIP/checker/results retained).
  This is not a replacement overlay bundle or hardware DMA/cache proof. Original
  BIT/HWH/XSA/ZIP remain unchanged. Hardware layout/recovery/full frame NOT_RUN.
- Failure ledger: actual allocator/DMA runs0; no new sampling-design attempt.
  One unsupported named-objdump batch and one Python3.6 zero-width parser
  failure are retained; corrected supported disassembly/parser succeeded once.
  These inspection failures do not reset prior UART2/2, no-DMA probe1 failed
  round or sampling counts. No same-method allocation retry was attempted.
- Evidence: `output/build/game_app/camera_dma_20261019_analysis.json` and manifest;
  raw `game_linux_native_camera_baseline_dma_preflight_20261019_d816bfdb`,
  `zocl_inspect_20261019_fab92d3e`, `zocl_binary_20261019_d5ca37a7` (parser fail),
  `zocl_binary_20261019_dca7510e`, `zocl_abi_20261019_796a8505`,
  `zocl_table_20261019_e23d876b`, `zocl_source_paths_20261019_d6e6cc99`,
  `dma_cpu_check_20261019_4701fdc2` (r1), `dma_cpu_check_20261019_b1976ac7` (r2),
  `dma_cpu_check_20261019_237f1606` (r3),
  `zocl_build_inputs_20261019_c38d04b0`, `kernel_dma_sources_20261019_4afae7a7`
  .log/.json (same prefix, failed parser has only .log). Prior sensor failure/
  initialization receipts remain authoritative. Web fetch cache misses are
  retained as retrieval failures; direct official GitHub API reads succeeded.

Latest sensor/CSI result (2026-10-19; observations pass, whole probe FAIL):

- User explicitly authorized current-environment sensor identity and CSI outflow.
  Reused COM9 Console (DTR/RTS false), existing OV5640 module and hash-bound
  environment helper definitions; no PYNQ/libcma import, PL reload, PS-clock
  rewrite or DMA/CMA. Same bootafc17ac5-09cb-4f14-bc0a-1da555c9146a. Preflight
  log/JSON `game_linux_native_camera_baseline_sensor_preflight_20261019_622469cc`:
  GPIO controller906..1023, labelzynq_gpio, parente000a000, initially unclaimed;
  installed PYNQ maps EMIO0=base+54. HWH routes one camera GPIO and PS I2C0 EMIO;
  actual adapter0 is e0004000. Only GPIO960 and I2C0 address0x3c were selected;
  no bus scan or I2C1 access. Scope used a cooperative task lock/owner snapshot.
- Exported only GPIO960, set active-low0/output low for1s then high for1s.
  Sensor ID300A/B=56/40. Reused unchanged `pynq_vision/ov5640.py` SHA537c9df9...
  to configure existing two-lane720p RAW10; canonical RAW expected fields and
  PLL/lane/timing fields read back as requested. No sensor table or detector
  change. Sensor standby3008=42 was verified before the single burst.
- Reset/enabled CSI once before start using existing control3->2 sequence.
  Baseline packet/CRC0. Sensor left standby3008=02; first positive sample showed
  six long packets and CRC0, control2. Standby3008=42 was then read back; after
  settling the counter was978 and stayed978 across100ms, CRC0, control2 with no
  sampled overflow flag. Polling and synchronous serial event logging mean this
  is a bounded observation, not precisely timed exposure/HS-clock measurement.
  Long packets are LLP boundaries, not complete frames, per-lane byte proof or
  stable clean throughput. No frame buffer was allocated or read.
- Overall probe returned nonzero/`pass=false` at the unchanged-DMA-state guard
  (one validation round, no automatic reset/retry). Capture S2MM CR10002 (RS0),
  SR10001->14811. Read-only follow-up found mask810: VDMAIntErr bit4 and
  SOFLateErr bit11, plus Err_Irq bit14; HALTED remains1. Display CR10002/SR10001
  unchanged. This is a real failure, not a harmless status counter difference;
  raw failed receipt/checker was not reclassified or relaxed to pass.
- Two post-failure read-only stages, without a new stream or reset:
  `game_linux_native_camera_baseline_sensor_post_read_20261019_4063ecd0` and
  `game_linux_native_camera_baseline_sensor_layout_read_20261019_c451c5b0`.
  S2MM VSIZE(A0), HSIZE(A4), stride(A8), three start addresses(AC/B0/B4) all0.
  AMD PG020v6.3 S2MM_VDMASR defines these error bits and geometry conditions:
  https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMASR-S2MM-VDMA-Status-Register-Offset-34h .
  Inference: consistent with an unconfigured downstream receiving a video
  boundary. This does not prove the precise internal cycle cause or memory DMA.
  RS0/HALTED1 alone does not guarantee that incoming video cannot set errors.
- Source/raw failed log/receipt:
  `output/build/game_app/camera_sensor_csi_20261019.py` and
  `game_linux_native_camera_baseline_sensor_csi_20261019_963d7ae4.log/.json`.
  Board `/tmp/codex_camera_sensor_csi_vdu0omxv/sensor_csi_receipt.json` retains
 140 I2C operations, failure traceback and every recorded counter; summary and
  sources in `camera_sensor_csi_20261019_analysis.json`/manifest. Sensor standby,
  GPIO960 exported/output high owned by this task, I2C FD and host UART closed.
  No post-burst CSI reset, VDMA clear/recovery, service/BOOT/SD mutation or build.
  PS controls remained unchanged. Previous PL receipt/firmware remain retained.
- Next outcome is safe full-frame capture: resolve allocator/cache/lifecycle and
  current-clock ownership/reuse, then valid geometry/buffers and controlled
  capture-channel recovery. Do not discard current errors, rerun the no-DMA
  helper over its owned GPIO or infer that old sampling STA/CDC is now passing.
  The no-DMA scheme has one failed whole-probe round; historical transport and
  sampling failure counts are unchanged. Keep board power/UART/camera for next
  authorized stage. No complete frame, restart/recovery, current-source OOC or
  production/game acceptance is claimed.

Prior controlled-initialization result (2026-10-19, PASS for scoped environment):

- The user reported stable UART restored and explicitly requested another
  controlled load/init/readback. This external change reopened the stopped
  transport path; prior failures remain2/2 in their original ledger. Reconnection
  required no retry: a normal xilinx shell was confirmed, no residual receiver
  ACK was seen, and sudo worked. Read-only log/JSON
  `game_linux_native_camera_baseline_environment_reconnect_20261019_dd172931`:
  bootafc17ac5-09cb-4f14-bc0a-1da555c9146a, uptime126.78s, same kernel and all
  four boot-file hashes. No board reset or service mutation was performed.
- One complete upload then succeeded with no additional transport retry. Exact
  original ZIP SHA4528301e... and all15 payload hashes passed on the board;
  the converted1994080-byte BIN SHA355a914c... matches host conversion. Loaded
  the existing diagnostic BIT SHAa5a88800.../HWHdc899d44.../XSA03ae58ac... once,
  without a build or PYNQ/libcma import. Before writing, stock start_pl_server
  PID265 had only its libcma/SCU map, no selected open descriptors; registered
  bitfile/timestamp and seven dictionaries were empty. A cooperative lock and
  this snapshot scope the diagnostic; they do not enforce system-wide exclusion.
- Kernel-manager full-load write returned operating; PCAP INT_STS changed
  0x20000->0x20004, LVL_SHFTR_EN0->0xf. After asserting PL reset bits0xf,
  stopping/redividing/restarting FCLK1/2 and releasing reset, FPGA_RST_CTRL=0;
  FCLK1/2_CLK_CTRL=0x00100700/0x00100500. Readback using current33333333Hz
  ps_clk and999999990Hz IO PLL gives99.999999/142.8571414286/199.999998MHz.
  FCLK0/3 and PLL controls stayed unchanged; gate bit0 at0xf8000178/188/198=0.
  SLCR values remained equal after a further200ms. No CPU/DDR/PLL/HP or GPIO write.
- Known PL AXI-Lite reads passed: D-PHY control/version=0x2/0x00010002;
  CSI control/version=0x2/0x00010001, long_packets=0, crc_errors=0, no overflow.
  Capture S2MM and display MM2S each have CR0x00010002 (RS0), SR0x00010001
  (HALTED1, no checked error bits); absent VDMA directions were not treated as
  active channels. Zero CSI counts are a pre-stream baseline, not video health
  or complete-frame acceptance. No sensor/GPIO/I2C, DMA/CMA or HDMI start.
- Important limit: hardware FCLK gate bits were already0 even before this
  run, despite kernel enable/prepare0. A kernel count alone does not prove an
  electrically stopped clock. Direct diagnostic writes leave kernel FCLK1/2
  cached rates at41.666667MHz/count0 and create no kernel consumer. PYNQ server
  metadata is deliberately unchanged; it cannot identify this kernel-loaded PL.
  The installed PYNQ Clocks default50MHz reference also differs from deployed
  ps_clk. Do not invoke the existing pipeline's reload/clock/allocator path to
  infer this environment. Persistent Linux clock/PL ownership remains open.
- Raw log and complete receipt:
  `game_linux_native_camera_baseline_environment_initialize_20261019_71122612.log/.json`.
  Board receipt `/tmp/codex_camera_environment___bs1s8s/receipt.json`, retained
  firmware `/lib/firmware/codex_camera_codex_camera_environment___bs1s8s.bin`.
  Receipt binds this boot, original artifact hashes, one load and all readbacks;
  no FPGA configuration readback/hash claim is made beyond controlled source,
  successful load and known IP reads. UART is closed on the host. Keep power,
  UART and camera for the next sensor/CSI baseline; bootpy/BOOT/SD are unchanged.
  RDY, physical HS clock, SoT/bit-byte identity, frames, recovery, current-source
  timing/CDC/resources and production/game acceptance were not exercised.
  No sampling failure count was added or reset. Sampling structure remains open.

Prior controlled-initialization result (retained; stopped before PL load):

- After the user privately validated sudo again, the root upload bootstrap
  correctly stopped on changed boot ID before upload or writes. Log
  `game_linux_native_camera_baseline_environment_initialize_20261019_e43624e1.log`.
  A fresh root read succeeded, log/JSON
  `game_linux_native_camera_baseline_environment_current_20261019_fb41a1d8`:
  boot235389e6-301b-4f9d-94bf-d6b5051503a4, uptime98.84s, same kernel, four
  matching boot-file hashes, manager=unknown. Clock tree ps_clk33333333Hz,
  iopll999999990Hz; FCLK0~100MHz enabled, FCLK1/2~41.666667MHz with enable/prepare0.
  No PS/PL MMIO was performed in this refreshed identity read.
- The initialization upload then received17 block ACKs and failed in the host
  serial flush with `ClearCommError failed (PermissionError(13, access denied,
  None,5))`; log `game_linux_native_camera_baseline_environment_initialize_20261019_71e18b5a.log`.
  The sole same-method retry failed opening COM9 with FileNotFoundError2.
  Subsequent read-only Win32_SerialPort inventory returned no entries. STOP:
  environment transport attempts2/2, no third open or alternate-port workaround.
  The retry exception occurred before Console construction completed, so no
  retry serial transcript exists; its observed stderr is recorded in
  `camera_environment_20261019_transport_failures.json`.
- Upload never reached END/hash verification/extraction: the first17 chunks
  existed only in the known receiver's memory. Actual PL loads=0, PS clock/reset
  writes=0; initialize.py and its current-boot ownership/IP checks never ran.
  No sensor/GPIO/I2C, DMA/CMA, SD/service mutation. The root receiver was pending
  on disconnection; its original600s alarm does not prove observed termination
  or restored tty echo. Confirm foreground on restored UART, never assume a
  clean shell or reset the board merely to recover this diagnostic.
- No sampling design-validation count is added or reset. Restore the stable
  UART connection, requalify boot/foreground, and review the environment stop
  before further transfer. The scoped PL authorization already exists.
  Additional host checks in `camera_environment_20261019_resume_checks.json`
  validate Python3.6 syntax and the deployed clock-summary rate column (three
  count columns; rate index4=33333333). These remain host checks, not board passes.

Earlier preparation and intermediate-boot evidence (retained):

- Current authorization is one PL load -> clock/reset initialization -> readback;
  no new build, sensor/I2C/GPIO, DMA/CMA, SD or service mutation. The root
  `environment_preflight` invocation stopped with `sudo: a password is required`
  before its program ran. Log `game_linux_native_camera_baseline_environment_preflight_20261019_8a4596de.log`
  retains that access failure (one attempt, resolved by user validation before
  the resumed run). This does not reset or add a sampling-design attempt.
- A subsequent user-level, file-only preflight succeeded once, log/JSON
  `game_linux_native_camera_baseline_environment_preflight_20261019_56e4f0e4`.
  That intermediate boot ID was `055f4429-4fcc-48ef-85b6-23843717f534`, uptime380.99s; the
  earlier privileged observations below are explicitly prior-boot evidence.
  All four boot-card hashes still match. Manager state=unknown; firmware sysfs
  mode0200 confirms a write-only root interface, not an attribute to reread.
  No legacy fclk sysfs interface exists; configfs overlay directory is empty.
- Saved installed `pynq/ps.py` and `pl_server/device.py`. PYNQ's Zynq reference
  default is50MHz, while the earlier kernel clock tree showed33.333333MHz;
  do not accept library frequency readback as independent proof. Prepared probe
  checks the current kernel reference, PLL source/lock and divisors, leaves
  CPU/DDR/PLL/HP and FCLK0/3 configuration unchanged, and records independent
  hardware gate bits. It does not import PYNQ/libcma or register kernel clock
  consumers. Kernel-manager success, reset/level-shifter values, clocks, IP
  versions/default controls and halted implemented VDMA channels must all pass.
- Host static checks passed: Python3.6 syntax, exact BIT header/part and 32-bit
  word swap against a byte reference, truncated BIT rejection, and upload-protocol
  dry run. These are host checks only. Probe, checks and input snapshot are
  `output/build/game_app/camera_environment_initialize_20261019.py`,
  `camera_environment_20261019_static_checks.json` and
  `camera_environment_20261019_inputs.json`; the existing baseline evidence driver
  owns COM9 transport and preserves raw transcripts. At that preparation
  checkpoint no upload/load had occurred; resumed incomplete upload is recorded above.

Prior-boot 2026-10-19 COM9 baseline checkpoint (new execution at that time):

- Reused the existing Console transport, 115200/8N1, no handshake, DTR/RTS false.
  Restricted open failed once with Windows access denied; the sole ordinary
  Windows retry succeeded. Four seconds of passive silence followed by one CR
  produced the actual logged-in xilinx shell. No unknown foreground program was
  interrupted. Runtime is Linux 5.4.0-xilinx-v2020.1, armv7l, PynqLinux 2.6,
  Python 3.6.5, uid1000; uptime was 169.51 s at first query, 224.77 s at snapshot.
- Actual-card SHA256: BOOT.BIN `06c7ab259073472dc8b0f3ee07819f11924a8752970beeb6dd370d9d9c0054b4`,
  image.ub `07132df1bf965dee030141712c686937004bae88f5aea7bff1ceca184158b797`,
  boot.scr `03e395686fe2e059f45b03ec072034915918c3caf16477e2f7868a1f274de6b7`,
  boot.py `d48c69ddd86f124c1fb89483c30b1b8c5b3caba57f0899c976ed5efcb4201333`.
  All four equal the previously inspected local image bytes, resolving that
  card-file identity gap; the running kernel's exact xlnk implementation and
  loaded PL identity are not established by those hashes.
- FPGA manager state=unknown, no amba_pl children/video4linux class entries.
  start_pl_server PID270 exists. These observations do not prove that PL is
  physically unconfigured or identify a bitstream. Read the existing server's
  metadata using the installed protocol after privileged access; avoid importing
  PYNQ, whose active Xlnk device construction loads the allocator.
- Current bootpy is failed, ExecMainStatus=1, with the BaseOverlay import failure
  before construction. Preserve this startup scene; no service repair/restart.
  /dev/i2c-0 maps to PS e0004000, /dev/i2c-1 to e0005000. Selected diagnostic HWH
  routes camera I2C0 via EMIO, so device-node existence is not a physical route
  check. No I2C scan or transfer occurred. CmaTotal/Free=131072/47256 KiB at this
  snapshot; no allocation/cache/lifecycle acceptance is implied.
- Initial `sudo -n true` required a password. The user completed `sudo -v`
  privately and released COM9; the same task then ran privileged metadata and
  PS-register reads successfully with uid0, same boot ID. The original denial is
  retained; no credential was requested or logged. `privileged_identity` and
  `ps_profile` ran once each and returned0 without stage retries. The firmware
  sysfs attribute remained unreadable even as root; both earlier unprivileged
  and this privileged denial are retained, with no further attribute retry.
- The existing PYNQ server reports bitfile_name="", timestamp=null, all IP/GPIO/
  hierarchy/memory dictionaries empty. The exact installed read-property protocol
  returned unchanged state, continued=1; no PYNQ/libcma import, dictionary reset,
  server stop or kernel PL configuration was performed. This proves absent
  registered provenance, not physical emptiness of PL. FPGA manager stays unknown.
- Kernel FCLK0 is~100MHz with enable/prepare1; FCLK1/2/3 are~41.666667MHz with
  enable/prepare0. Actual SLCR reads: FPGA0_CLK_CTRL=0x00200500,
  FPGA1/2/3_CLK_CTRL=0x00101800, FPGA_RST_CTRL=0, LVL_SHFTR_EN=0.
  DEVCFG_CTRL/INT_STS/STATUS=0x4e00e07f/0x00020000/0x40000a30. INT_STS lacks
  the DONE event bit; it is not a bitstream identity or independent proof that
  no design remains physically configured. SLCR/DEVCFG were mapped PROT_READ
  through O_RDONLY /dev/mem; no register writes or unknown PL-address reads.
- At this snapshot only start_pl_server PID270 maps libcma and /dev/mem at
  0xf8f00000; no camera/VDMA/I2C/xlnk descriptor was observed. Kernel iomem has
  no PL claims at the candidate camera addresses; that absence does not grant
  ownership. PS/PL level shifters are disabled and required clock configuration
  is absent, so camera-register access/capture is not a qualified next action
  in the unchanged current state. No CSI/VDMA error count, frame or recovery
  test was attempted; these remain NOT_TESTED, not zero errors or PASS.
- Existing capture diagnostic source XSA03ae58ac.../BITa5a88800.../HWHdc899d44...
  remains a traceable historical diagnostic, not the current-source PL baseline.
  All15 SHA256SUMS entries match. Before any full-frame run, retain the existing
  allocator/cache/ownership/stop gates; the current capture CLI's unconditional
  buffer release after a failed DMA reset and ring-wrap blind spot are not
  acceptable evidence of safe lifecycle. No alternative allocator or fix was
  implemented here. The next proposed state-changing step is temporary PL/clock/
  sensor initialization followed by CSI stream checks, requiring explicit
  authorization beyond checking the previously loaded design. No BOOT/service
  repair, SD replacement, bare-metal PS initialization or production build.
- Host raw/structured evidence: `game_linux_native_camera_baseline_prompt_20261019_0ce891e9.log`
  and `game_linux_native_camera_baseline_identity_20261019_2c37a6f1.log/.json`;
  resumed stages are `game_linux_native_camera_baseline_privileged_identity_20261019_8635d6e6.log/.json`
  and `game_linux_native_camera_baseline_ps_profile_20261019_b22402b1.log/.json`.
  Original manifests stay unchanged; resume inputs/analysis/manifest bind the
  new evidence. COM9 is closed; no board files, package installs, PL load,
  register writes, PL MMIO, sensor start, DMA/CMA, global configuration or Git
  operation occurred. The known PS control reads above are actual MMIO and are
  not mislabeled as pure file parsing.

The following 2026-10-17 bullets remain historical evidence:

- COM9 at 115200 8N1 reaches the logged-in xilinx console. Running kernel is
  5.4.0-xilinx-v2020.1, armv7l; PynqLinux 2.6/Ubuntu 18.04, glibc 2.27,
  native GCC 7.3. Rootfs has about 23 GiB free; CmaTotal is 128 MiB.
  /dev/xlnk and i2c-0/1 exist; these interfaces were not exercised. Device tree
  identifies ax7z020, not independently the precise B revision.
- PixArt USB Optical Mouse (093a:2510) enumerates via hid-generic as
  /dev/input/event0 (root:input 0660). An authorized 30-second Python read
  captured 5917 complete 16-byte records, including X/Y and two left down/up
  pairs. Native C compile/layout/idle evidence and pending live linkage are
  recorded in Three-Level Control Core above. Native C also received actual
  X/Y/left reports and published coherent snapshots; three-click native
  selection/invalid-scene-start acceptance now passes. No chmod, group or udev changes.
- Stock bootpy.service is enabled but failed: /boot/boot.py cannot import
  BaseOverlay. No service/boot-file changes were made. DRM card0 is zocl-drm,
  with no display connector or fb0; this does not establish HDMI output.
  Board wall date is incorrect; game timing uses CLOCK_MONOTONIC. Existing
  unclean FAT/journal warnings were recorded without repair. No automatic PL
  load, hardware configuration or filesystem repair is authorized by this test.
- Raw/readable diagnostics and analyses: output/build/game_app/com9_linux_20261017*,
  com9_mouse_20261017* and game_linux_native_*. Only a selected temporary C test
  bundle is compiled under board /tmp; no repository/image copy or dependency
  installation. Production capture/display/frame submission remain pending.

### Offline SD / Camera Test Entry Correspondence

Status: local file/partition/interface audit complete; the Linux capture-only
diagnostic bundle is now prepared and checked offline. Board execution remains
gated by production PL and Linux resource qualification. Correspondence evidence:
`output/build/game_app/sd_camera_correspondence_20261018.json`. This task only
extracted the selected existing XSA and packaged software; no Vivado build,
BIT/XSA generation, BOOT change, image mount/write, serial or board operation.

- The local ALINX image's FAT16 boot files were read directly at their existing
  offsets, without copying or hashing the entire 6.14 GB image. `BOOT.BIN`
  (859464 bytes, SHA256 `06c7ab25...`) has valid headers and three PS/data
  partitions, including U-Boot 2020.01; no recognized `0x20` PL configuration
  partition was found. `boot.scr` loads `image.ub` and boots Linux. `boot.py`
  imports generic `BaseOverlay("base.bit")` for an LED example, not this
  repository's MIPI application; the prior COM9 journal confirms import failure
  before that Overlay constructor. This does not prove that no other PL owner
  has ever configured the running board.
- Prior board evidence agrees with this Linux image's kernel/runtime and
  `BOOT.BIN`/`image.ub` sizes, but actual-card file hashes were not collected.
  Byte identity and the currently loaded PL remain UNKNOWN. The report records
  expected hashes for `/boot/BOOT.BIN`, `/boot/image.ub`, `/boot/boot.scr` and
  `/boot/boot.py` for a later explicitly authorized read-only comparison.
- `color_test/color_test.xsa` is the 2026-10-04 Vivado 2023.1 handoff. Its embedded
  BIT (`a5a88800...`) equals `vision_ps_platform/hw/color_test.bit`; the standard
  `color_test/build/hw/system_wrapper.bit` (`212715e6...`) differs. Existing
  `output/pynq_overlay` BIT/HWH (`d7a78a25...`/`9b5dbf04...`) matched the adapter's
  former hash constants, but differ from today's XSA; that directory's manifest
  names the XSA path from an older generation. A path match is not provenance.
  All existing artifacts are preserved. The new diagnostic below extracts only
  today's XSA pair and now rejects those old artifacts.
- Current HWH matches all seven adapter register address/span contracts, two
  D-PHY/CSI lanes, 10-bit Bayer input, three frame stores and 24-bit active
  capture/display streams. Basic software geometry remains 1280x720 BGR888,
  stride 5760, 4147200 bytes/frame. This is metadata/source agreement, not pixel,
  board, pin-timing or current-source RTL acceptance.
- Both old and current HWH record actual FCLK1=142.857132 MHz. The former
  `FCLK_MHZ=(100,150,200)` mismatch is corrected to actual `(100,142.857132,200)`;
  HWH requested values and actual PS output-port values are checked separately.
  Future runtime setup writes those actual targets and rejects nonfinite or
  >0.1 MHz readback error before capture MMIO/CMA/GPIO/I2C/DMA activity. PL load
  and clock writes already precede this runtime guard and are not rolled back.
  PYNQ readback is PS PLL/divider-register-derived, not a measured oscillator
  tolerance, MIPI HS clock, duty cycle or relative-jitter guarantee.
- The existing `output/live/BOOT.bin` under `color_test/build/vision_ps_baremetal`
  is a distinct standalone diagnostic bundle, not a Linux process or the current
  card's boot package. Reused canonical `verify_boot()` and `check_inputs()`
  read-only: all three FSBL/BIT/app payloads equal their named inputs; eight
  platform fingerprints and four output fingerprints match. Six of 28 recorded
  C sources and five of ten PC sources have changed since that manifest. Thus
  this is an internally coherent historical bundle, not a current-source or
  production signoff. No packaging CLI was invoked, because even its
  `--verify-only` mode rewrites `validation.json`.
- Separately, the existing legacy `color_test/sd_boot/vision/BOOT.bin` is
  2181586 bytes (`2d9dc992...`), not the formerly recorded 2245840-byte image.
  Its headers/checksums parse, but the last partition declares end 2181776,
  190 bytes beyond EOF. The cause is unknown; preserve it and do not load,
  append bytes, repack or treat its BIF as evidence of actual payload identity.
  This is a PC-side legacy artifact, not a finding that the running Linux card
  is damaged. Historical successful BOOT records below do not qualify this file.

Concrete entry map:

| Entry | Role and current gate |
| --- | --- |
| `pynq_vision.hardware.inspect_overlay_files()` / CLI `inspect-overlay` | File-only strict XSA/BIT/HWH/manifest/address/actual-clock checks; no PYNQ import or PL load. Rejects old/mixed artifacts. |
| `pynq_vision.app ... capture --i2c-device <verified bus> --output <new directory>` | Offline-prepared single-frame entry; board execution still gated. Downloads selected PL, sets/checks FCLKs, allocates three capture frames, retains Gamma=3, resets/configures/starts RAW10 OV5640 and S2MM. No HDMI clock/VTC/display-MMIO/buffers/start/reset. It is an active camera test, not a passive query. |
| `color_test/build/vision_ps_baremetal/output/live/BOOT.bin` | Historical matched standalone boot route; requires a separately reviewed boot change, not execution from the Linux shell. Not approved for immediate loading. |
| `color_test/sd_boot/vision/BOOT.bin` | Header/file-length inconsistency; rejected as a current test input and preserved untouched. |

Prepared diagnostic: `output/pynq_overlay/linux_capture_03ae58ac.zip`
(1645746 bytes, SHA256 `4528301eab4b82f3d2fa58047d44d240fe5c19d43da28dc661e080b6ba45e789`),
with its unpacked sibling directory. Manifest v2 binds the complete source XSA
(`03ae58ac...`), embedded BIT/HWH, addresses, clocks and unchanged 720p RAW10/
BGR888/stride contract. `SHA256SUMS` covers 15 payload files. The old output root
is untouched. Canonical owners: `pynq_vision/constants.py`, `hardware.py`,
`prepare_overlay.py`, `app.py`, `README.md`, `__init__.py`, and
`tests/test_diagnostic.py`. Capture does not import the PC detector; legacy run
explicitly opts into its existing display path and remains paused. Capture
requires a supplied, verified I2C bus; it no longer guesses `/dev/i2c-0`.
Success saves PNG and capture.json; runtime failures save FAIL/stage/error and
return failure. An artifact preflight failure creates no capture output or
hardware side effects. Parsed PYNQ address disagreement can no longer trigger
the compatibility fallback download.

Offline verification: **14/14 Python tests PASS**, including real selected-XSA
packaging, bad hashes/manifest/XML clocks/addresses, no fallback on parsed-address
failure, bad clock readbacks before capture resources, no-HDMI lifecycle and
single-frame success/failure logs. All ten adapter modules pass Python 3.6
grammar parsing; execution used host Python 3.12, not board Python 3.6.
Evidence: `output/build/game_app/linux_capture_offline_validation_20261018.json`.
The actual ZIP was temporarily extracted in existing output space, all payloads
matched, and isolated file inspection passed with PYNQ/PC detector/OpenCV imports
prohibited. Evidence: `output/build/game_app/linux_capture_bundle_validation_20261018.json`.
These are host software/XML/hash/mocks checks, not RTL simulation, OOC,
implementation, measured clocks, board capture or production acceptance.

Later Linux readiness task, stage 4 after the engineering baseline:
with explicit current-task hardware authorization, perform a
bounded read-only Linux readiness check for this exact bundle: actual boot-file/
PL identity, camera I2C routing, PS PLL/FCLK/reset/HP ownership and available CMA/
cache support. Do not scan I2C, fix services, download PL or start the camera in
that readiness task. Evidence owners are the selected manifest and this section;
no RTL/XDC or capture-mode change. Pass only with a concrete resource/identity
mapping and accepted model-based timing/CDC/artifact evidence before separately
authorized active capture; full physical worst-case closure is outside the current
gate. The old bundle is a correspondence reference, not the new stage-1 BIT.
Existing first-frame,
cache/DMA-stop/release and runtime compatibility risks remain unqualified.
Preparing this bundle does not qualify the PL baseline or authorize execution.

### HDMI Compatibility Acceptance Revision (2026-10-19, Offline)

User replaces controller-model identification with saved EDID declaration plus
physical compatibility acceptance. AGENTS.md now records this lasting rule and
pure-PL colorbar-before-Linux order. No new production HDL/BD/XDC/C change.
`color_test/tools/check_hdmi_edid.py` decodes the complete saved physical EDID:
no established/standard modes,2 native-timing DTD copies and8 SVDs (including
VIC4 1280x720/60). The native CTA DTD remains1280x800,82.170MHz,1650x830,+/+.
First test82.000MHz/59.875867Hz using all native porches/polarities; it is a test
candidate, not presumed compatible. Do not mix the separate vendor EDID.
VIC16 native marking and110MHz range vs148.5MHz SVD inconsistency are retained.

Evidence/complete table, selected waveform, reference-clock/startup caveat,
reversible test steps, success/failure criteria and separate Linux callbacks:
`output/build/game_app/hdmi_compat_20261019/REVIEW.md`, `edid_modes.json`,
`pl_report_audit.json`. Current BD has no VDMA-free colorbar source. Existing
debug is a VDMA/ILA chain, and its program entry resets PS/starts baremetal code;
do not reuse it under this task. Reports cover74.286MHz, not82MHz; production
setup/hold failures and7 Critical CDC persist, debug setup fails. No qualifying
82MHz timing/DRC/BIT exists. Independent diagnostic preparation can proceed
without declaring camera sampling or Linux DMA qualified. No Vivado/build/board
run here; physical test needs explicit new scope and matched diagnostic release.

### Actual PYNQ/xlnk API and Memory Diagnostic (2026-10-19)

Current evidence: `output/build/game_app/pynq_memory_20261019_REVIEW.md` and
hash manifest `pynq_memory_20261019_manifest.json`. User explicitly authorized
board connection, exact API script and a minimal memory test. Current boot
`605cc209-5bd5-4f67-ad32-225a4d740255`; PYNQ2.6.2 from /home/xilinx/pynq.
Actual installed buffer/xlnk/device sources and libcma hashes are retained.
Running GNU Build-ID `83e702eeb9e31cc76bef7e013bae379fd2de4f93`, complete kernel
notes, config hash and actual symbol addresses match the decompressed hash-matched
boot FIT. Exact binary xlnk implementation is identified, without inventing its
unavailable source commit. This supersedes the older unmatched-driver statements.

One native test of `pynq_vision/check_memory.py`: 4096-byte cacheable Xlnk target,
CPU pattern and normal release pass; strace allocation 0x5802, two cache 0x5818,
free 0x5803 and shutdown 0x5864 each return0. Actual global reset0x5865 absent.
Public sync/free still provide no status. freebuffer leaves Buffer Count1;
array deletion/GC reduces it to0 and performs the free ioctl. CPU same-mapping
readback is not DMA/cache-visibility proof; global CMA counts are not exact
reclamation proof. Matched kernel confirms no fd/PID/DMA owner check on free,
incomplete cache range validation, allocation failure rollback gaps and no fd-close
buffer reclaim. SIGSEGV global-reset handler was disabled within test process.
No invalid-ID/OOM/SIGKILL/failure injection, DMA, PL/module or system configuration
operation occurred. Native display and capture safety gates stay closed.

Original user script exit0: `game_linux_native_memory_api_20261019_c3f6a2a5.log`;
test exit0: `game_linux_native_memory_test_20261019_ecc7855a.log` plus
`pynq_memory_test_20261019.json`. Source SHA256 `8813bc6b...7a4e82` is fixed in
the receipt. Host Python3.6 syntax check passed; no FPGA build. COM9 restricted
open and offline objdump DLL-start each failed once then passed the sole ordinary
environment retry; host command-length guard refused one transmission before
any board test. Actual board test rounds1, failures0. Historical stopped native
build2/2, UART, zocl and sampling ledgers remain unchanged. All COM9 sessions closed.

### Resident-Asset Display Qualification Review (2026-10-19, Offline)

Current review: `output/build/game_app/display_review_20261019/REVIEW.md` and
hash-locked `review.json`; existing qualification JSON has a separate
`offline_review_20261019` entry. XSA/member pairing, stored physical EDID
checksums/native DTD and asset lengths/hashes agree. No hardware qualification.
Supplied B-board/core schematics now establish the expected positive/negative
HDMI pin chain; implemented I/O and physical revision linkage remain open.
Both screen PDFs are available but describe different LVDS-monitor/MIPI-panel
interfaces; neither supplies the actual HDMI controller's complete mode/tolerance
applicability. Integer clock model yields 82.000 MHz (-2068.882 ppm) nearest to
82.170 MHz; tolerance UNKNOWN, approved mode/dividers/VTC remain null. Fractional
hardware feasibility was not reviewed. Do not treat the nearest value as enabled.
Latest card-file hash correspondence and kernel SDK are reused as historical
progress, not exact xlnk implementation or safe display allocator proof. No
native callbacks can be enabled from these materials. No software/PL source
change, compile/test rerun, Windows display setting or board operation occurred;
all earlier failure ledgers remain. Existing copy seam suffices after platform
qualification; no duplicate renderer, engineering copy or new DMA was added.

### Native C Static Menu Display: Safe Linux Adapter Checkpoint (2026-10-17)

**Status: recorded host and image-native software bundles passed; display operation
awaits vendor timing, artifact gates and the qualified Linux platform binding
(2026-10-17).** No HDMI integration or on-screen acceptance. The target
is native **1280x800**, 1:1 BGR888, HSIZE=3840, VSIZE=800, stride=5760,
span=4,608,000 bytes. Do not default to 720p. The still-gated bring-up proposal is
an image-native C owner with exclusive display MMIO, feeding the existing
`axi_vdma_0 -> v_axi4s_vid_out_0 -> rgb2dvi_0` chain. Keep the renderer/game core
unchanged. Installed libcma does not currently meet the backend contract;
the official-source audit below does not qualify a binding. Qualify the complete
native mode from real panel timings before display operation. 720p is permitted only with explicit sink support and a
specific diagnostic need; it cannot pass native-mode acceptance.
Do not start a DRM/fbdev/kernel migration for
this milestone. There is **no currently qualified BIT for immediate loading**.
These historical results apply only to the recorded bundles, not automatically
to the current source tree or hardware. This offline closure updates evidence
and gates only; it does not enable the native binding.

Implementation checkpoint:

- `src/game_linux_display.h/.c`: v2 platform lifecycle, qualification before
  acquire (including library load/device open), partial-acquire cleanup, one
  immutable strided buffer, flush/barriers before arm and VSIZE-last commit.
  Stop orders confirmed HALTED -> output/finish -> individual buffer release ->
  platform close. Failed release/close retains the remaining owner; retries do
  not double-free. `owner_can_exit` and `owner_drain` keep the final caller in a
  retry/wait loop until all task resources are released, including wait errors.
  Fake platform checks resource unwind order and unrelated-resource preservation.
- Partial Linux adapter in those same canonical files implements CLOCK_MONOTONIC,
  nanosleep and ARM `dsb sy`. Native preflight is unconditionally UNQUALIFIED;
  no caller flag or force path exists. Resource callbacks remain blocked, with
  **no dlopen/libcma/device/MMIO implementation**. No timing/clock/VTC values were
  invented. The qualified native binding is **not complete/enabled**. The final
  owner loop does not supply the still-unreviewed Linux signal/kill/exit policy;
  it cannot preserve memory across SIGKILL/OOM/power loss. No atexit/dlclose
  fallback is permitted while retained.
- Added `tools/game_linux_static_menu.c`: existing generated config, game_loop/app
  initial whole snapshot at fixed time 0, canonical renderer/font, exactly one
  CPU render. `--check` performs no devices; `--display` returns blocked (exit 3)
  before any CMA/display operation. It must not emit READY until a real qualified
  binding and successful display start exist.
- `tests/test_game_linux_display.c` and `tools/test_game_app.ps1 -DisplayOnly`:
  the previously recorded strict C99 check and host fake platform run passed
  **1,540,479 checks**. Added closed native preflight with instrumented zero
  load/open/map/allocation side effects, partial-acquire failures, reverse cleanup,
  cache failure prohibiting commit, retained owner on unconfirmed HALTED, cleanup
  failure retries, and final-owner waiting even when wait fails. CPU entry
  hash is `1f497c09`; one complete render, unchanged snapshot and unqualified
  display refusal (exit 3) passed. No canonical renderer/game/input changes.
- Existing `tools/test_game_linux_native.py` confirms the actual
  `xilinx@pynq:~$` prompt before transfer/commands; no Ctrl-C on an unconfirmed
  prompt timeout. Image GCC **7.3.0** strict C99 build, both links,
  **1,540,483 fake-platform checks**, one CPU render and display refusal passed.
  The four extra native checks exercise Linux monotonic wait/barrier callbacks.
  ELF imports are checked before either CPU executable runs: no libcma dependency
  or loader/device entry points. Host menu import table also has no CMA DLL.
  Native hash `1f497c09` matches host. Menu ELF is ARM EABI5 hard-float, loader
  `/lib/ld-linux-armhf.so.3`; CLOCK_MONOTONIC adds a **GLIBC_2.17** requirement
  (previous baseline maximum 2.4), still compatible with image glibc 2.27.
  In this log the separate `libcma_abi` link-only ELF requires only GLIBC_2.4;
  that probe's version table must not be attributed to the menu ELF.
  Installed libcma header/type and link-only ABI probe passed with **-lcma
  -pthread**; its NEEDED list includes libcma.so/libpthread.so.0/libc.so.6.
  The CMA-linked probe was **never executed**. No proof of real
  allocation/cache safety is inferred from this link. Success evidence:
  `output/build/game_app/game_linux_native_display-prepare_428ba986.log` and
  `game_linux_display_native_session.json` (bundle SHA256
  `f7548935bf55814bca012211de9a5fc07f1d61e00cd1429dd963a53c8891988f`).
  `/tmp/codex_game_display_gjorybn8` was cleaned through the exact task manifest.
  The session records `cleaned=true`; this is historical cleanup evidence, not
  a new board check. COM9 was closed. No additional mouse/input or offline-image
  export test ran. No build or test was rerun for this offline closure.
- During the earlier 2026-10-17 inspection, COM9 initially had no bytes because
  the board was unpowered (user confirmed).
  After power-on, boot/autologin completed; read-only shell and library inspection
  succeeded. COM9 was closed. Logs: `output/build/game_app/`
  `game_linux_native_display_console_c68a4bfd.log`,
  `game_linux_native_display_inspect_5011150d.log`,
  `game_linux_native_display_cma_impl_1bca339a.log`.
- Installed `/usr/lib/libcma.so` SHA256
  `126301f9575d119f3b12e41bc2ce26df79a0fdae210169da3bf4b6548dd1fdd3`:
  readelf relocations resolve init-array 0x19f14 to framework_open (0x30d8),
  which calls xlnkOpen -> context init -> xlnkCounterMap -> hook/trace init.
  CounterMap opens `/dev/mem` and maps 0xf8f00000/4096 bytes (string at 0x84ec,
  call sequence 0x7cac..0x7d34). Thus even dlopen/DT_NEEDED can access devices
  before main. PL init/shutdown and platform hooks are no-ops in this binary;
  xlnkOpen initializes spinlocks/bookkeeping and has exit(-1) failure paths.
- Fini-array 0x19f1c resolves to framework_close (0x3128): shutdown hook ->
  decrement process-local reference -> trace/hook cleanup -> xlnkClose when zero.
  xlnkClose (0x54a0) walks the library's allocation table, calls xlnkFreeBuf for
  nonzero entries, then issues **0xc0045864** and closes its fd (>0 branch).
  This is broader than a task-local release. **The running kernel's ioctl meaning
  and cross-process scope remain unproven** (official candidate semantics below):
  matching kernel UTS header exists but
  installed APF directory has only Kconfig/Makefile; xlnk.c/.h/.o, vmlinux and
  the checked xlnk.ko path are absent. The official PYNQ configuration builds APF
  in; an absent .ko alone establishes neither driver absence nor a source match.
  Need matching driver implementation/binary provenance.
- Allocation: nonzero cacheable -> sds_alloc_cacheable -> xlnkAllocBuf (flag 1);
  zero -> sds_alloc_non_cacheable -> xlnkAllocBufInternal (flag 0). Internal
  allocation sends 0xc0045802 and mmaps the returned handle; error returns NULL
  despite the header's -1 comment. The mmap-failure return has no visible handle
  release: failure-atomic ownership is unproven. Physical lookup returns 0 on
  miss, otherwise table physical base + offset. Driver physical alignment/cache
  mapping attributes are not proven; keep 64-byte/32-bit/span validation and do
  not assume the uncached flag avoids synchronization. xlnkFreeBuf clears local
  bookkeeping, munmaps, issues 0xc0045803 without checking results; cma_free is
  void, so successful task-local release is also not observable through this API.
- Cache: cma_flush_cache ignores virtual pointer, forwards physical/size to
  xlnkFlushCache (0x6590), issues 0xc0045818 and logs negative ioctl status;
  public return is void. Neither return, errno nor absence of stderr proves
  success. A status-returning, driver-verified sync contract (or proven mapping
  coherency) is required; real flush remains blocked. Open failure may exit(-1),
  another reason to avoid any library call after an uncertain DMA halt.
  No installed-library load, allocation, reset, flush or free was executed.
  Read-only evidence under `output/build/game_app/`:
  `game_linux_native_display_cma_safety_ef492a8c.log`,
  `game_linux_native_display_cma_driver_5fd66116.log`,
  `game_linux_native_display_cma_sources_73fa2b18.log`; earlier cache/allocation
  disassembly remains `game_linux_native_display_cma_impl_1bca339a.log`.
- Official-source audit: [PYNQ v2.6.0 release](https://github.com/Xilinx/PYNQ/releases/tag/v2.6.0)
  identifies PetaLinux 2020.1. PYNQ commit
  `86c52c29f1de2df8812ca11f0ecbd694473b15ac`,
  `sdbuild/packages/libsds/libcma/libcma.so.32` (Git blob
  `9ce6ae2901f1f2faa7331cf58c3edc6e806e8643`, 57,048 bytes), fetched and hashed
  in host memory only, has the **same SHA256 as the installed library above**.
  This establishes the library binary match, not the kernel driver match.
  The wrapper/Makefile do not expose the statically linked SDS runtime source.
- Official kernel candidate: `Xilinx/linux-xlnx` tag `xilinx-v2020.1` resolves to
  commit `043f8a226a752a1dd11f7ff64cee6dbe7334d394`.
  [drivers/staging/apf/xlnk-ioctl.h L10-L34](https://github.com/Xilinx/linux-xlnx/blob/043f8a226a752a1dd11f7ff64cee6dbe7334d394/drivers/staging/apf/xlnk-ioctl.h#L10-L34)
  and [xlnk.c L1456-L1575](https://github.com/Xilinx/linux-xlnx/blob/043f8a226a752a1dd11f7ff64cee6dbe7334d394/drivers/staging/apf/xlnk.c#L1456-L1575)
  show that, for the 32-bit ABI, **0xc0045864 is XLNK_IOCSHUTDOWN**, dispatched
  to `xlnk_shutdown`, a no-op returning 0. **0xc0045865 is XLNK_IOCRECRES**:
  it calls the global buffer-pool sweep and, if CONFIG_XILINX_DMA_APF, the
  all-channel release function. Do not conflate them or infer a DMA halt.
- Candidate-only findings: allocation has pool-full/copy_to_user failure paths
  without rollback; failed mmap does not free the handle. Single-buffer free
  uses a global ID without fd/PID ownership or active-mapping/DMA checks.
  Cache ioctl returns status but lacks full-range/owner validation; libcma loses
  that status and free status. mmap selects pgprot_noncached only for flag 0;
  ARM CMA alignment is delegated to the DMA allocator. Final fd release is a
  no-op and VMA close only decrements a counter: no process-exit buffer reclaim
  is implemented there. Normal library destruction can still free its table;
  abnormal-exit leaks are not safe DMA retention. Exact paths, line ranges,
  source links and the contract assessment are in the existing
  [software README](color_test/software/vision_ps_baremetal/README.md#libcmaxlnk-官方证据与资格判定).
- **Historical 2026-10-17 identity gate (superseded by the 2026-10-19 matched
  binary evidence above; safety remains blocked):** provide the actual boot-kernel
  artifact and a hash/build-ID-linked build manifest (source commit, patches,
  .config and matching built-in xlnk object/vmlinux or equivalent verifiable
  driver binary). Existing UTS/version/name/ioctl matches cannot establish this.
  The unchanged library cannot supply failure-atomic allocation and observable
  per-buffer free/cache success. A later scoped review must address those
  interfaces and driver rollback/ownership if confirmed, plus signal/exit policy;
  a userspace status wrapper alone cannot repair kernel-side leaks. No alternate
  allocator or driver change was added. Native preflight stays **UNQUALIFIED**.
  This offline consistency closure reused prior logs and the recorded official
  audit; no rebuild/fake-platform test,
  COM9, library load/execution, CMA, display or board operation was performed.
- i2c-0 is PS e0004000; i2c-1 is PS e0005000. Loaded FPGA Manager state remains
  unknown, so adapter identity alone does not establish current HDMI EMIO/DDC
  routing. **No I2C transaction or bus scan** was performed.
- Board/image evidence update (2026-10-17): the user confirms an ALINX
  **AX7Z020B** and an ALINX-official image supplied for that board. The supplied
  PCB photograph independently shows the **AX7Z020B** baseboard and **AC7Z020**
  core-module labels. Photo source:
  `C:/Users/11967/Documents/Tencent Files/1196779973/nt_qq/nt_data/Pic/2026-10/Ori/0270f1d11dae05b7bd321501e8c52483.jpg`,
  SHA256 `5083c6df04a91e5a951039f9663a20aa423545db00ba2e5b6ee8859cb43e417e`.
  Board model and user-reported image provider are no longer missing inputs;
  the photo does not establish the PCB revision, and the provider statement
  does not link the actual boot-kernel binary to xlnk source/configuration.
- Offline HDMI pin comparison: `color_test.xpr` registers the existing
  `color_test/color_test.srcs/constrs_1/new/hdmi_out.xdc`. Its six explicit
  PACKAGE_PIN assignments agree with the HDMI table in the
  [ALINX online manual](https://ax7z020b-20231-v101.readthedocs.io/zh-cn/latest/7Z020UserManual_CN/AX7Z020UserManual.html):
  clock P=U13, data P[0..2]=W14/Y18/Y16, DDC SCL=V18 and SDA=V17.
  This AX7Z020B tutorial site serves a manual whose body is labelled AX7Z020;
  it is a family-level pin reference, not proof of this PCB revision. The
  [B-specific schematic](https://github.com/alinxalinx/AX7Z020B_2023.1/blob/master/Hardware/01_SCH/ax7z010B_ax7z020B_SCH.pdf)
  is located but its contents were not inspected. The source XDC has no explicit
  PACKAGE_PIN assignments for the four TMDS negative pins; their implemented
  differential-pair placement was not checked. No selected-BIT I/O report or
  generation-matched constraint provenance was supplied. This source-only
  comparison leaves `board_revision_pin_provenance_verified=false`; XDC/RTL/BIT
  and all runtime resources were untouched.
- Sink description: Yongxin LCD Taobao store, 10.1-inch IPS, non-touch,
  HDMI/Type-C/VGA with speakers; exact controller/panel model remains unconfirmed.
  The earlier no-timing-source conclusion is superseded by the two distinct
  EDID candidates below; neither is an accepted FPGA runtime mode. No CVT/GTF
  values were invented. XSA member hashes still match the recorded
  pair below; other candidate hashes remain different. Board pin provenance,
  generation-matched STA/CDC and Linux FCLK1/reset/HP ownership remain gates.
- Authorized PC-only readout (2026-10-17 17:22 +08:00): the active HDMI target
  is Windows `HHD65B1`, name `9032AB54`, driven by the RTX 4060 Laptop GPU.
  QueryDisplayConfig reports a cloned desktop with the BOE internal panel;
  the external target is **1920x1080@60 Hz, 148.500 MHz, totals 2200x1125**.
  This is not a native 1280x800 acceptance run. That API does not expose H/V
  polarity; current transmitted polarity remains unmeasured/unreported.
  No display settings were changed and no FPGA/COM9/I2C interface was used.
  The first sandbox CIM query was denied; its single unsandboxed retry succeeded.
- Windows driver-reported EDID: base and extension blocks were obtained through
  `WmiGetMonitorRawEEdidV1Block`, matched the active target's registry bytes,
  and both 128-byte checksums are zero. No `EDID_OVERRIDE` registry key was found
  for that target; this does not rule out every possible driver override/cache.
  The local CIM schema declares a **Boolean** return and both reads returned
  true with 128-byte payloads. The first numeric-status check rejected true;
  one diagnostic base retry plus schema inspection resolved that mismatch.
  No bus freshness or electrical signal measurement is inferred from WMI.
  Full 256 bytes and source/observation details are preserved in qualification
  JSON `pc_display_observation`; EDID SHA256
  `d79382d3db4fbd4673422d1de34002d88a85bcc6d9bc12d9a792bca46edf540d`.
- The physical-display EDID's CTA native DTD at byte 155 declares progressive
  **1280x800@60 Hz, pixel clock 82.170 MHz**: H active/front/sync/back/total
  **1280/110/40/220/1650**; V **800/5/5/20/830**. Flags **0x1e** explicitly
  select digital separate sync, **H positive / V positive**. The base DTD has
  the same dimensions/clock but flags 0x00; retain that internal discrepancy.
  EDID range descriptor: V 48..85 Hz, H 31..79 kHz, max pixel clock 110 MHz.
- The vendor file `C:/Users/11967/Downloads/37280042682660_1280x800_Only(1).c`
  (file SHA256 `2b4fc35261d5d91dd671ac1cd665ed652b2239a670e1bff7e4cc0b39fe6bc46c`)
  contains another valid-checksum EDID, SHA256
  `4f3b60b1be38384b16f7e9d7ea585e119d6b6676f9a14656692ba05483c36d64`:
  **83.760 MHz**, H **1280/72/128/200/1680**, V **800/3/6/22/831**, about
  **59.9966 Hz**, flags 0x04 without a valid independent H/V polarity declaration.
  Do not mix its clock/porches with the physical-display CTA polarity. Prioritize
  the physical-display candidate for a separate mode review and PC native-mode
  check; no custom mode, four-polarity test or screen-image acceptance ran here.
  FPGA panel/mode gates remain false and approved native timing/clock/VTC fields
  remain null pending review; the immutable 1280x800 BGR888/5760-stride contract
  and software verification batches remain unchanged.
- PC native-mode attempt (2026-10-17 17:35-17:38 +08:00): target identity/path
  still matches `HHD65B1 / 9032AB54`. Saved the complete initial active paths,
  modes, DEVMODE and scale in JSON `pc_native_mode_validation_history` before
  requesting extension; existing system enumeration lists 1280x800 at 60 Hz.
  Inactive DISPLAY5 exposed no modes, so extension was attempted first with both
  original target signals preserved. Sandbox validation returned access denied
  (5); the single unsandboxed retry validated (0), but APPLY returned invalid
  parameter (87). Review identified a caller error: APPLY and restore incorrectly
  used 0xC0 (VALIDATE|APPLY), omitting USE_SUPPLIED_DISPLAY_CONFIG. Microsoft
  requires mutually exclusive VALIDATE/APPLY; correct supplied-config APPLY would
  be 0xA0. No corrected call was made after the two failed attempts. The 1280x800
  selection stage was **not reached**; neither driver rejection nor unsupported
  timing is established. Stop without another API/UI route or polarity tests.
  Restore used the same invalid flags and returned 87; it was not successful.
  Subsequent
  raw active paths/modes exactly match the initial snapshot. The small screen
  remains cloned **1920x1080@60 Hz, 148.500 MHz, totals 2200x1125**; internal
  BOE0C29 remains 1920x1080 at 34685000/240864 Hz (about 144.002425 Hz),
  346.850 MHz, totals 2080x1158, scale 100%. No configuration change remains.
  Actual H/V polarity is **unmeasured**; H+/V+ remains only the reused CTA
  declaration. Complete-image/cropping/offset/flicker confirmation and a photo
  after about 30 seconds of native display remain pending because native mode
  was not reached. No FPGA menu, pixel-for-pixel or HDMI integration acceptance.
  A separate task can correct the call flags and perform the authorized extension
  and native-mode readback; no build, software test or board operation ran here.
- Corrected PC-only attempt (2026-10-17 17:50-17:51 +08:00; independent JSON
  history record): used named USE_SUPPLIED_DISPLAY_CONFIG (0x20), VALIDATE
  (0x40), APPLY (0x80), composing **0x60** for validation and **0xA0** for
  application/rollback. No ALLOW_CHANGES, SAVE_TO_DATABASE, custom timing or
  generic topology switch. Fresh initial paths/modes, current DEVMODE and
  scale were saved; identity was unchanged, so both existing EDIDs were reused.
  Initial validation returned access denied (5) in the sandbox; one same-method
  unsandboxed retry returned 0. This validation alone was not rollback proof.
  Extension validation and application both returned **0**. The request retained
  the internal source/position and both original target signals, placing the
  small screen at (1920,0). Readback showed independent DISPLAY5 (NVIDIA) and
  DISPLAY1 (Intel): internal resolution, signal, exact refresh and position were
  unchanged, but its scale became **125% instead of 100%**, with adapter/source
  reassignment. Stopped immediately; no fresh extended-source mode enumeration
  or 1280x800 selection/application was reached, and no alternate route was tried.
  Rollback using saved supplied configuration and **0xA0 returned 0**; active
  path/mode bytes, current DEVMODE and scale readback exactly matched the initial
  snapshot. Final small screen is cloned **1920x1080 progressive, 60/1 Hz,
  148.500 MHz, totals 2200x1125**; internal is 1920x1080,
  34685000/240864 Hz (about 144.002425 Hz), scale **100%**. No change is retained.
  Neither 1280x800 output size nor the exact **82.170 MHz / 1650x830 / 60 Hz**
  CTA candidate was demonstrated; this does not establish native-mode rejection.
  Actual H/V polarity remains **unmeasured**; H+/V+ is the reused EDID CTA 0x1e
  declaration only. Native image/cropping/offset/flicker confirmation and a
  stable-30-second photo remain pending because native mode was not reached.
  Current PC blocker is preserving internal 100% scale across extension;
  investigate only in a separately scoped task. All FPGA gates/binding remain
  blocked/unchanged. No builds, software tests, new scripts or board actions.
- `output/build/game_app/game_linux_display_qualification.json` records full
  current XSA/member hashes, display addresses, HWH clock evidence and native
  buffer geometry. It explicitly sets loading/display qualification false and
  unknown panel/native clock/VTC data to null; same-archive pairing is not STA
  acceptance. It does not extract or replace the old overlay package.
  Its `software_verification` now follows only prepare batch `428ba986` and the
  matching session: **1,540,483** checks, menu GLIBC **2.17**, bundle SHA256
  `f7548935bf55814bca012211de9a5fc07f1d61e00cd1429dd963a53c8891988f`.
  `software_verification_provenance` gives a source for each field, including
  the single render/hash/unchanged snapshot and session-only cleanup assertion.
  The superseded `242832ca` record is preserved verbatim in
  `software_verification_history`, un-revalidated and never merged into this batch;
  original logs/session are unchanged. JSON parsing and field cross-checks are
  evidence consistency checks, not current-source or display qualification.

Qualification gaps (2026-10-19 latest priority: xlnk PARTIALLY COMPLETE and NOT
the current blocker, kernel work deferred; final qualification flags remain
false and approved native timing/clock values remain null):

| Gate | Current conclusion | Existing evidence | Missing material | Pass condition | Next work | Authorization boundary |
| --- | --- | --- | --- | --- | --- | --- |
| Boot kernel / xlnk identity | PARTIALLY COMPLETE overall; identity established, NOT current blocker | Current boot FIT hash, full GNU notes/Build-ID/config match, actual xlnk/callee addresses and disassembly; memory report/manifest | No repeat image-origin/source-manifest request needed | Identity evidence retained; final DMA acceptance remains separate | Deferred by user; no further kernel investigation | No stopped build retry, new kernel or module replacement |
| Allocation / sync / per-buffer free / ownership | Normal4KiB evidence retained; non-current-blocking follow-up | Current installed API, matched kernel and strace successful alloc/sync/free; delayed GC release observed | Later native-integration status/ownership validation; no new kernel investigation now | Full-span sync/free status and safe ownership still required before actual DMA release | Defer; continue asset-to-display integration and existing native callback/profile work | No driver/library replacement or extra DMA authorized |
| Signal / normal exit / abnormal death | Owner drain loop alone is insufficient | Matched-kernel fd/VMA close lacks reclaim; installed SIGSEGV handler calls global reset; SIGKILL/OOM bypass cleanup | Reviewed lifecycle policy covering HALTED, retained resources and abnormal-death containment | HALTED precedes release; errors retain ownership; enforceable policy covers signals, normal exit and SIGKILL/OOM without treating leaks as safe retention | Offline policy review before acquire can be enabled | No atexit/dlclose shortcut; implementation and board validation need separate scope/permission |
| Panel compatibility / full native mode | Controller identity is not a gate;82MHz/native DTD waveform is first physical candidate, VIC4 link fallback declared | Saved physical EDID fully parsed; complete timing table and report audit in hdmi_compat_20261019 | Matched pure-PL diagnostic BIT/timing/DRC/clock/pin evidence and valid30-second physical screen result | Stable complete native82MHz image under recorded conditions; do not infer acceptance from error size or720p success | Prepare reversible VDMA-free diagnostic, no fractional work before valid failed test; PC scale path stays stopped | Build/download/initialization needs explicit scope; EDID review does not enable Linux binding |
| BIT/HWH/XSA / board / pins | Same-archive hashes rechecked; expected B-board/core HDMI P/N pin chain established; exact revision/release pins pending | Uploaded Rev1.0 schematics visually reviewed; six explicit source XDC pins agree; offline review gives all expected N pins | Same-generation build/export and implemented I/O/constraint provenance, physical PCB revision correspondence | Trace accepted BIT/HWH/XSA and all active pins to actual board revision | Review missing revision/implemented evidence; no repeated generic schematic/model request | No constraint edit, repackaging, loading or build |
| Same-generation STA / CDC | Acceptance absent; other generations' negative reports cannot qualify this XSA | Recorded production/debug timing failures below, scoped to their generations | Hash/build-linked routed setup/hold and CDC reports, constraints and tool provenance for selected artifacts | Nonnegative setup/hold slack and totals; reviewed accepted CDC with valid constraints, no waived path to hide failure | Offline report review; PL repair only as a separate task if needed | No synthesis/implementation/bitstream or automatic PL repair |
| Linux clock / reset / HP | Initialization and runtime/handoff compatibility unqualified | HWH FCLK values; earlier Linux snapshot had FCLK1 disabled | Reviewed 2020.1-runtime/2023.1-handoff clock/reset/HP profile, shared effects and ownership plan | Proven compatible initialization and bounded readiness under an exclusive approved owner | Offline profile review after artifact evidence | No bare-metal PS init, MMIO, clock/reset/HP or service changes |
| Current resource exclusivity | Historical snapshot is not runtime exclusion | Earlier iomem/fd/maps snapshot; start_pl_server and failed bootpy observations | Enforceable ownership/locking and autoload exclusion plan plus separately authorized current-state evidence | Prevent competing kernel/userspace/inherited-PL owners throughout use | Review ownership plan before any later runtime validation | No new board diagnostics, device opens or service changes in this task |

Minimum next work is the existing Linux resource callback/profile integration;
the user confirms the old real-scene HDMI path works with the screen. Retain this
legacy evidence without claiming the current82MHz artifact/physical test passed.
Asset-to-display lifecycle integration now passes offline; see
`output/build/game_app/display_asset_submission/REVIEW.md`. No controller-model
or supplier-tolerance document is required. xlnk is partially complete and not
the current blocker: preserve its follow-up items, do not deepen kernel work.
Actual native safety and accepted production release remain separate final gates.
The supplied schematics, both screen PDFs, stored EDIDs, image/card-file hashes,
kernel configuration and offline SDK are already available; do not request them
again. Current exact binary correspondence is now in the memory report; it closes
identity, not the confirmed driver safety or PL release gates. The prior offline
review did not reconnect; the later explicitly authorized memory task did, as
recorded above. No stopped-path retry or alternate allocator was attempted.

- Next: continue the existing Linux native resource callbacks and an identified
  existing HDMI artifact/clock/reset/HP ownership profile. Do not restart xlnk
  kernel investigation, EDID parsing or the stopped diagnostic build automatically.
  Do not start PL timing repair/full builds under
  this task. No load/display/CMA/service/boot/camera/input operation was performed
  in this offline closure.
  Linux platform binding and 1280x800 screen acceptance remain pending.
  No project copy, duplicate game/
  render/config/font implementation or production-source build output was added.

Original Explore read-only board evidence (2026-10-17 snapshot, before the native
software build and later library audit; historical observations only):

- COM9/115200, DTR/RTS false; only shell/sysfs/proc/DT/source reads. Initial
  sandbox COM9 open returned Windows access denied; its sole retry outside the
  sandbox succeeded. COM9 is closed. No input resampling, device-node open,
  Overlay import/load, MMIO access, CMA allocation, VDMA operation, camera access,
  service/boot change, reboot, install or build was performed by this review.
- `/dev/dri/card0` and renderD128 bind `zocl-drm`, compatible `xlnx,zocl`;
  no connector entries, `/dev/fb*`, framebuffer class device or `/proc/fb` entry.
  Generic DRM/KMS helpers are enabled, but DRM_XLNX_PL_DISP and FB_XILINX are not.
  Loaded out-of-tree zocl exists despite CONFIG_DRM_ZOCL being unset; card0 is
  compute infrastructure, not an established scanout endpoint.
- Live DT has no display VDMA/VTC/dynclk binding. `/dev/uio0` is `fabric`, bound
  to uio_pdrv_genirq, map0 **0x40000000 + 0x10000**; it neither maps the display
  blocks nor proves a display interrupt. Do not reuse this UIO for VDMA/vblank.
- Root `/proc/iomem` lists no claim at 0x43010000, 0x43c00000 or 0x43c10000.
  A root /proc fd/maps snapshot found no xlnk/UIO/DRM handle or mapping and only
  PID 300 (`start_pl_server`)'s /dev/mem mapping at 0xf8f00000 (outside those
  blocks). These are point-in-time observations, not proof against future owners
  or inherited running PL. FPGA Manager state is `unknown`; do not assume the
  custom BIT is already loaded or infer register safety from an unclaimed range.
- Kernel clock summary: FCLK0 ~99,999,999 Hz, enable/prepare=1; FCLK1/2/3 each
  ~41,666,667 Hz, enable/prepare=0. Thus the required display FCLK1 is not enabled
  according to this snapshot. This is kernel-reported state, not a pin measurement.
  bootpy.service remains failed (exit status 1); its known BaseOverlay import
  failure was not repaired. Plan exclusive runtime clock/reset ownership before
  any PL/display operation; do not run bare-metal PS init under Linux.
- CmaTotal=131072 KiB, CmaFree=43224 KiB at inspection. Installed
  `/usr/include/libxlnk_cma.h` and `/usr/lib/libcma.so` expose cma_alloc,
  cma_get_phy_addr, cma_free, cma_flush_cache and cma_invalidate_cache. Installed
  PYNQ xlnk.py passes virtual address, physical address and byte count to those
  cache APIs. `/dev/xlnk` is root:root 0600; `/dev/mem` is root:kmem 0640,
  so plan an explicitly authorized privileged diagnostic, without chmod/udev
  changes. Availability/free space do not prove allocation, DMA visibility or
  safe allocator initialization. The image's old objdump rejects symbol-valued
  `--disassemble`; that attempted static library inspection added no function
  evidence and was not pursued then. The later `cma_safety`/`cma_driver` audit
  above supersedes the then-open initialization question: constructor device
  access is established. Running-driver correspondence remains open.
- Raw evidence: `output/build/game_app/com9_display_readonly_20261017.log`,
  `com9_display_resources_20261017.log`, `com9_display_owners_20261017.log`,
  `com9_display_libcma_20261017.log`. No board files were created.

Candidate selection and interface contract:

| Candidate | Provenance / decision |
| --- | --- |
| `color_test/color_test.xsa` | Sole handoff reference for the proposed native backend: Vivado 2023.1, generated 2026-10-04 20:56:56, xc7z020clg400-2, members `color_test.bit` and `system.hwh`; recorded SHA256 a5a88800... / dc899d44.... These members form a same-generation pair, but no matching clean timing/CDC acceptance is established. Do not authorize loading from pair equality alone. |
| `color_test/build/hw/system_wrapper.bit` | Recorded SHA256 212715e6...; differs from XSA BIT, predates corrected publication gate and is not an accepted production artifact. Do not combine with the XSA HWH. |
| `output/pynq_overlay/system_wrapper.bit/.hwh` | Existing manifest was generated 2026-10-02 10:16:05, hashes d7a78a25... / 9b5dbf04...; historical same-generation package, not today's XSA export. Preserve it; do not overwrite or treat stale constants as qualification. |
| `color_test/build/hdmi_output_debug/system_wrapper_hdmi_debug.bit` | Recorded 71abe204...; WNS=-2.564 ns, TNS=-178.036 ns; debug resources and no qualified paired handoff. Exclude. |

The current production routed report remains WNS=-0.247 ns, TNS=-0.481 ns,
WHS=-1.111 ns, THS=-2.208 ns, with seven Critical CDC findings as already
recorded under Current Problem. It did not publish a replacement BIT/XSA. These
results belong to their recorded generations, not automatically to the older
XSA payload. No repeat synthesis/implementation/tap investigation was run.
Under AGENTS.md, negative timing cannot be accepted because the menu bypasses
camera traffic; obtain generation-matched timing/CDC evidence or resolve the PL
release in a separate task. Do not build a display-only alternative here.

Targeted inspection of the XSA HWH confirms display VDMA 6.3 at 0x43010000,
span 64 KiB, MM2S only, simple register mode (no SG), three stores, 32-bit
addresses, 64-bit DDR data, 24-bit AXIS and MM2S DRE. Control/dynclk reference
uses FCLK0=100 MHz; MM2S, HP interconnect and video AXIS use actual handoff
FCLK1=142.857132 MHz. Video-out has asynchronous pixel-clock crossing; VTC
0x43c10000 and rgb2dvi use dynclk 0x43c00000 PixelClk, with external SerialClk
at 5x pixel clock. HWH's static pixel-clock annotation of 100 MHz is not the
runtime HDMI rate. Existing Python FCLK_MHZ=(100,150,200) is inconsistent with
attainable handoff rates and cannot be copied as a strict runtime check. FCLK2
is not required by this display-only chain; leave camera configuration outside
this milestone. Validate shared reset/clock effects before enabling FCLK1.

Minimal software/buffer/commit contract (portable seam implemented; native binding blocked):

1. Obtain one complete initial `GameLoopOutput` through existing game_loop/app
   APIs and generated `game_default_*` configuration; render it once with
   `game_render` into a CPU-owned 1280x800 BGR888 VisionCanvas. No evdev open,
   pump/input run, detections, automatic selection/start, timer animation or
   camera image is needed for the static acceptance. Preserve snapshot fields
   and use an explicit fixed initial time for this diagnostic.
2. Render the complete 1280x800 menu **1:1**, with no scaling or cropping.
   Native mode needs its own complete sink/clock/VTC/MM2S qualification, not
   the 720p settings with height changed. Conditional 720p diagnostics would
   require 1152x720 uniform scaling and x=64 black bars, explicit sink support
   and focused tests. That optional adapter is not implemented in this version.
3. Only after boot-kernel provenance and the status/rollback/ownership/exit gates
   pass may a separately reviewed existing allocator path provide one owned
   cacheable CMA scanout. The installed libcma API is not approved as-is; any
   required interface or driver correction needs a separate scoped review.
   Validate the proven failure convention, nonzero address/range below 4 GiB,
   at least 64-byte alignment and arithmetic bounds.
   Keep the established stride **5760**, HSIZE **3840**, VSIZE **800**:
   span=4,608,000 bytes, active=3,072,000 bytes. Initialize padding as well.
   The CPU scratch canvas is 3,072,000 bytes in ordinary memory. Only one CMA
   scanout is needed for a frozen image; do not allocate a capture ring.
4. Ownership is CPU_PREPARING -> DEVICE_READ_ONLY -> DMA_HALTED -> FREE.
   Finish the 1:1 render/strided copy and synchronize the full owned allocation
   through a driver-verified status-returning interface, or prove mapping
   coherency, then perform the required ARM device ordering barrier before
   arming MM2S. Existing void `cma_flush_cache` cannot establish success; errno
   or absence of stderr cannot turn it into a successful callback.
   Volatile, msync and a C pointer cast do not
   replace cache synchronization or obtain a DMA address. No invalidate is
   needed for this CPU-write/device-read-only buffer. Verify the installed
   path's initialization/error/cache semantics first; never call a global
   xlnk reset or reclaim other owners' CMA as an allocation workaround.
5. After the separately authorized loader establishes the approved pair and
   clocks/resets, map only MM2S/dynclk/VTC from the validated handoff. Configure
   the verified native sink timing with bounded lock/reset waits. In MM2S park mode
   select store 0; program all three store-address slots with the same frozen
   valid buffer (no circular traversal), configure stride/HSIZE, and write
   VSIZE last to commit/start. Retain backpressure/TUSER/TLAST behavior of the
   existing hardware; no AXIS or RTL change. Keep output timing disabled until
   complete buffer/configuration is ready. Poll bounded status only in that
   future authorized task; do not assume an exported video-out lock/IRQ exists.
6. This is a single initial whole-frame submission; while scanout runs the CPU
   never writes or frees the buffer, so there is no runtime page-flip race.
   Hold the process/buffer for a bounded observation interval, then stop MM2S
   and confirm HALTED before observable, individually owned free/unmap. A failed
   release must preserve retryable ownership. The signal/normal/abnormal-exit
   policy must already be qualified; the owner loop alone does not supply it.
   If halt cannot be confirmed, retain
   the allocation/owner and report failure instead of freeing an active buffer.
   A VDMA frame boundary is not proof of physical HDMI vblank. Later live menus
   require a separately tested multi-buffer owner with pending/current tracking
   and acknowledgement before reuse; do not promote existing park_read() alone
   into a tear-free publication guarantee.

The register commit/start order follows AMD PG020
[Programming Sequence](https://docs.amd.com/r/en-US/pg020_axi_vdma/Programming-Sequence);
park reference and current-store fields are described in
[PARK_PTR_REG](https://docs.amd.com/r/en-US/pg020_axi_vdma/PARK_PTR_REG-Park-Pointer-Register-Offset-28h).
The installed API shape agrees with the versioned
[PYNQ 2.6 Xlnk source](https://pynq.readthedocs.io/en/v2.6.1/_modules/pynq/xlnk.html),
which documents API shape only. The later official-binary SHA256 match above
establishes libcma identity; neither source proves the running driver's identity
or qualifies the existing library's sync/free/exit behavior.

At a hypothetical 60 Hz this static native MM2S would read 184.320 MB/s active
payload (276.480 MB/s conservatively counting the padded address span); these
are capacity estimates, not confirmed sink refresh. Camera payload is zero.
CPU rendering/copy/flush is one-time, not a steady-state
frame copy. Actual transfer traffic/refresh remains unmeasured. This bounded
bring-up exception does not replace the AGENTS.md streaming/PL-overlay target.

Mode and physical gates:

- 720p is **not the default experiment**. Only after explicit sink support and
  a diagnostic need may its historical VTC/dynclk sequence be considered. It specifies
  active 1280x720, totals 1650x750, H sync 1390..1430, V sync 724..729, positive
  polarity. The software nominal target is 74.25 MHz; current `system.xdc`
  models dividers 52/(7*2) followed by /5, approximately **74.285714 MHz** and
  **60.02886 Hz** at a 100 MHz reference. That current source model does not
  prove the selected older BIT's runtime divider. Resolve the handoff/register/
  constraint agreement and confirm that the actual sink accepts this mode
  before starting it; do not claim measured exact 60 Hz.
- The earlier no-EDID observation applies before the authorized PC readout above.
  Physical-display and vendor candidates now exist, with different timing/flags.
  No FPGA-side EDID/I2C transaction was performed. For 1280x800 require reviewed
  pixel clock, H/V totals, porches, sync widths/polarities, refresh and sink range.
  Recalculate dynclk, VTC, MM2S height/span and timing coverage together; do not
  invent CVT/GTF values or copy 720p timings with only the active height changed.
  Keep native 1:1 presentation. The candidate
  BIT's ability to run that mode is still unqualified.
- Human connection: verified board revision/pin compatibility, powered display
  or capture sink with documented target-mode support, HDMI cable from the board's
  **HDMI OUT** (TMDS source, not HDMI IN) to that sink, and correct input selected.
  COM9 remains the diagnostic console. `hdmi_out.xdc` assigns TMDS positive
  pins U13/W14/Y18/Y16 and DDC V18/V17; HWH routes DDC to PS I2C1 EMIO, but this
  is not proof of Linux adapter numbering or a working EDID path. HPD/OEN are
  commented out in that XDC: do not promise automatic hotplug. No rewiring or
  camera connection is needed for this test; do not disturb powered hardware.

Implementation responsibilities and remaining acceptance (resume on request):

| Exact file / operation | Smallest responsibility |
| --- | --- |
| `color_test/software/vision_ps_baremetal/src/game_linux_display.h/.c` | Implemented native-only versioned contract and injected MMIO/CMA/clock/wait calls, 1:1 copy, ownership, cache/commit/shutdown. Real Linux platform binding remains blocked. No game or input rules. |
| `color_test/software/vision_ps_baremetal/tools/game_linux_static_menu.c` | Implemented single initial copied snapshot and canonical CPU render; --display fails closed pending qualification/binding. The offline text entry remains unchanged. |
| `color_test/software/vision_ps_baremetal/tests/test_game_linux_display.c`; existing `tools/test_game_app.ps1` | Host and native fake-platform checks for byte order, stride/guards/overflow, exact mode bounds, snapshot, flush-before-arm, VSIZE-last, no active writes/free, callback failures and bounded deadlines. No 720p adapter or hardware proof. |
| Existing `pynq_vision/prepare_overlay.py`, `pynq_vision/video.py`, `pynq_vision/vdma.py`; C `src/dynclk/`, `src/display_ctrl/`, `src/vdma.c` | Packaging/register references only. Do not invoke CameraPipeline or bare-metal MMIO/cache/DDR code under Linux. Reuse the existing packager only after artifact acceptance, with an explicitly reviewed output destination; preserve the current stale package. |
| `output/build/game_app/` | Generated config, native build/logs and one versioned manifest binding full BIT/HWH/XSA hashes, part, addresses, actual clocks, mode/dividers, stride, timing-report provenance. No binaries/generated files in src. |
| `PROJECT_STATE.md`; software README when usage is implemented | Record achieved evidence and exact native build/manual-run command. No service/autostart installation. |

The display seam/entry host and native tests passed as recorded above with
image-native GCC 7.3 (`-std=c99 -Wall -Wextra -Werror -pedantic`, existing core/
render sources, generated game_config.c, `-lm`). The separate installed-header
libcma ABI probe links `-lcma -pthread` and is not executed. ELF hard-float loader
and menu maximum required GLIBC_2.17 were inspected in batch `428ba986`; the
separate libcma link probe's maximum is GLIBC_2.4. These historical bundle
results do not qualify current source or real display execution. The single-source
JSON, game_render/font, input/core, legacy
bare-metal and PC code need no changes for this scope.

Before board execution require: a same-generation pair with accepted setup/hold/
CDC and board pin provenance; reviewed Linux-safe FCLK0/FCLK1/reset/HP-port
initialization and compatible 2020.1 runtime/2023.1 handoff; a qualified observable
allocation/sync/free/exit path for the owned span (unchanged libcma is insufficient);
current exclusive userspace/kernel
ownership (including the running start_pl_server) plus an autoload exclusion
plan for the already-failed bootpy service; and connected sink/mode evidence.
Any PL programming, clock/MMIO/VDMA operation,
service suppression or EDID transaction needs explicit authorization in that
implementation task. Do not bundle timing repair, full FPGA/Linux builds,
service changes or camera work into the software-only step.

Board acceptance then requires serial records of exact artifacts/mode/physical
buffer/stride/status, bounded dynclk lock and error-free repeated MM2S frames,
a physical screen/capture photograph with complete Chinese menu/bars, correct
BGR colors and all edges, stable display for the agreed interval (propose 30 s),
and confirmed MM2S halt before owner release. Record measured refresh separately
from the nominal target. A PPM, successful render, or VDMA status alone is not
HDMI acceptance. Native 1280x800 is required for this milestone; a temporary
720p pass cannot replace it. Native input-to-live-menu updates, real vblank flips,
mouse hotplug, camera/detection/A3 calibration and full-game acceptance remain
outside this static milestone. Current implementation limits are recorded above.

### Offline Image Details

These are historical offline-image observations preceding the later native build
and library audit above. Image metadata alone does not identify the booted kernel
or establish current runtime ownership; later evidence supersedes the explicitly
updated C/CMA/I2C conclusions below.

- File: `C:\Users\11967\Downloads\ax7z020b-2.6.0.img\ax7z020b-2.6.0.img`;
  6,140,747,776 bytes (6.14 GB / 5.719 GiB), last modified
  `2023-07-10 04:33:27 UTC`. Size matches the prior record; no partition-table
  recheck, image copy, mount or image write was performed.
- First recorded full-image SHA256:
  `BCEE01B865196F8F433E4D17DC8D854D428C1C0A462C6080BA29C022524F1EDD`.
  There was no previous full hash to prove byte-for-byte identity with the
  earlier inspection, nor a recorded publisher checksum. The later user statement
  identifies ALINX as the official supplier; no boot-kernel build link follows
  from that statement alone.
- Read-only Python offset reads used the already documented partition offsets.
  Opening boot files exposed a prior documentation error: the boot filesystem
  BPB says **FAT16**, despite the recorded MBR type `0x0c`. The prior FAT32
  description (also in `pynq_vision/README.md`) is superseded by this evidence;
  it is not evidence that the image changed. Boot files are `BOOT.BIN`
  (859,464 bytes), `image.ub` (5,878,536), `boot.scr` (1,636), `boot.py` (994).
- Image `/home/xilinx/REVISION`: `Release 2023_07_10 3af0198`,
  `Board 2023_07_10 3af0198 https://github.com/Xilinx/PYNQ.git`.
  This is internal build metadata. The later user statement supplies the image
  origin: an ALINX-official board-specific AX7Z020B image. At the original offline
  inspection, no download-origin alternate stream, release page or vendor checksum
  was recorded. The local `C:\Users\11967\Downloads\AX7Z020B教程.html` indexes
  ALINX AX7Z020B 2023.1 material and links
  `https://github.com/alinxalinx/AX7Z020B_2023.1`; it does not establish image
  provenance by itself. The user confirmation now supplies provider/board origin,
  while the actual boot-kernel source/patch/configuration/driver link remains open.
  Referenced repository `doc/` material is absent in this checkout.
  The previously inspected `21_ov5640_sd.zip` has no recoverable path in the
  current records and was not searched for recursively or re-inspected. Its
  DVP/RGB565 IP/BIT/XSA/BOOT.BIN remain reference-only.

| Area | Offline evidence and limit |
| --- | --- |
| Board/boot | Historical image-only evidence: FIT DT `/chosen/pynq_board="ax7z020"`, root compatible `xlnx,zynq-7000`, 1 GiB memory, base BIT `7z020clg400`/Vivado 2020.1, USB reset MIO46 matching the XSA, U-Boot 2020.01. The later photo/user evidence above establishes the AX7Z020B model and user-reported official image origin. PCB revision, DDR/FSBL setup and selected-BIT pin compatibility remain unqualified; the model letter B is not an exact PCB revision. |
| Kernel/DT | `image.ub` embeds Linux `5.4.0-xilinx-v2020.1`, SMP PREEMPT, built 2023-07-10 with GCC 9.2.0. Kernel and DT FIT SHA1 checks both pass. Embedded IKCONFIG exactly matches `/lib/modules/5.4.0-xilinx-v2020.1/build/.config`; module release agrees. DT payload SHA256 `6eada838c42d16261a305e9ca4c00ff528a0a9a134519a4438d68d8b21484c04`. |
| Rootfs | `/etc/os-release`: PynqLinux 2.6 (WFH), Ubuntu 18.04/bionic base; Python package PYNQ **2.6.2**, Python 3.6; dpkg records glibc **2.27**, armhf. Filename 2.6.0 does not mean the Python package is 2.6.0. |
| USB mouse | Kernel has USB, ChipIdea HOST, ULPI, HID, HID_GENERIC, USB_HID, INPUT_EVDEV built in. DT USB0 `e0002000` enabled, ULPI PHY has `drv-vbus`, reset GPIO46; USB1 disabled. `dr_mode` is absent, so role/VBUS/reset/enumeration still need board checks. `INPUT_MOUSEDEV` is disabled: use `/dev/input/event*`, REL_X/REL_Y, BTN_LEFT and SYN_REPORT, not `/dev/input/mice`. |
| Native C/C++ | At offline inspection, `/usr/bin/gcc` and `g++` resolve to ARM GCC/G++ **7.3.0-16ubuntu3**; make **4.1**, headers/libraries and ARM EABI5 hard-float loader are present. The then-unrun native C build/CPU execution was subsequently completed for recorded bundle `f7548935...` in `prepare_428ba986` above; that does not verify today's source tree or a C++ build. |
| Host cross compiler | Existing `D:\Xilinx\Vitis\2023.1\gnu\aarch32\nt\gcc-arm-linux-gnueabi\bin\arm-linux-gnueabihf-gcc.exe` runs; reports GCC **12.2.0**, target `arm-xilinx-linux-gnueabi`. Its Cortex-A9 HF/NEON sysroot has **glibc 2.36**, so its default sysroot is not proven compatible with this 2.27 runtime. Prefer image-native GCC; a later cross build needs an image-matched armhf sysroot plus ELF symbol-version checks. `arm-none-eabi`/standalone BSP is not a Linux toolchain. |
| CMA/DMA/cache | Offline config has CMA/DMA_CMA, **128 MiB**, built-in XLNK/APF/Xilinx DMA and DT `/xlnk`; header/library API presence only. Later Explore recorded `/dev/xlnk` and CmaTotal/free, and the official libcma SHA256 match plus `-lcma -pthread` link-only ABI check were established above. Actual allocation/DMA visibility/ownership were never tested; running driver is unmatched and void sync/free, failure and destructor behavior do not qualify unchanged libcma. Use only a separately reviewed path after those gates pass. |
| I2C/GPIO/FCLK/PL load | Offline config enables Cadence I2C, GPIO, DEVMEM, FPGA Manager and overlays; DT initially enables FCLK0 only. Later Explore identified i2c-0=e0004000 and i2c-1=e0005000; physical routing and current PL state remain unqualified. PYNQ clock MMIO capability and disabled optional `CONFIG_XILINX_FCLK` do not establish safe clock/reset/HP ownership or qualify FCLK1/2 operation. |
| Display driver/UI | Generic DRM/X server and FreeType development files exist, but `DRM_XLNX_PL_DISP` and `FB_XILINX` are disabled, and this DT has no custom VDMA/VTC/dynclk nodes. No proven `/dev/fb0`, DRM connector, V4L2 camera or SDL display path exists for our PL. No confirmed Chinese font was found in the inspected TrueType/OpenType families; provide a licensed CJK font/subset or small glyph atlas. |

`bootpy.service` is enabled through `basic.target.wants` and executes
`/boot/boot.py`. That script **attempts** `BaseOverlay("base.bit")` and LED
access. The installed `pynq/overlays/base/` contains only `base.bit`, with no
BaseOverlay implementation/HWH there. Stock boot behavior may fail or contend
with a later PL owner; do not claim a first boot is Overlay-free. A future
authorized SD/boot task must prepare a reversible way to suppress this service
before a diagnostic boot; no image/service was changed here.

### Custom PL and Software Reuse

- Current XSA HWH still maps capture/display VDMA to
  `0x43000000/0x43010000`, dynclk/VTC to `0x43c00000/0x43c10000`, D-PHY/CSI
  to `0x43c20000/0x43c30000`, Gamma to `0x43c40000`. Both VDMAs have three
  stores, 32-bit addresses and 24-bit pixel streams. DT does not bind these
  addresses: existing exclusive MMIO control is a plausible first path, not a
  verified Linux driver integration. Do not share registers with another driver.
- **Selected diagnostic delivery:** XSA (Vivado 2023.1, generated 2026-10-04) contains
  BIT SHA256 `a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55`
  and HWH `dc899d44a94c1c98ffd6b7178e64f78ff6576ff3e4889759b291b659baba347c`.
  Current standard BIT is `212715e66e209e3ca6f60c97dcf6504d67d6dec297238b06a71897a38c2b1f32`;
  old `output/pynq_overlay/` BIT/HWH are `d7a78a25...` / `9b5dbf04...`, now rejected
  by the adapter. The former same-XSA/standard-BIT equality statement is obsolete.
  All originals are preserved; `output/pynq_overlay/linux_capture_03ae58ac/`
  carries the exact selected XSA and pair, manifest v2 and code checksums.
  `prepare_overlay` refuses existing output/archive paths. This historical
  handoff's coherence does not establish equality to current RTL or PL signoff.
- **Clock metadata reconciled; runtime gate open:** adapter targets HWH actual
  `(100,142.857132,200)` and checks requested/actual/output-port metadata before
  hardware. Future runtime PS clock readbacks must be finite and within 0.1 MHz
  before capture resources start. This is not physical MIPI-clock measurement.
  HWH-parser fallback does not establish clock/reset, PS initialization, HP
  ownership or Vivado-version compatibility.
- Reuse the canonical C `vision_ps.c`, `green_target_detector.c`, `ray_game.c`
  and stabilization/scene structures. Core inspection shows standard C/math
  dependencies; retain their existing semantics and known regression limits.
  `vision_overlay.c` has reusable stride-aware BGR model/ray primitives, but
  its English/digit 5x7 font is now reused beside an original short-label Chinese
  bitmap font by the offline game renderer. No new detector or solver
  is needed. The current Python PYNQ demo still imports `pc_vision`; it is a
  diagnostic adapter, not the selected native game's mandatory runtime.
- The portable `game_session.c/.h` and generated three-level configuration
  provide the offline rule/timer layer. Standard C `game_scene_adapter` and
  `game_app` provide detection conversion, an explicitly uncalibrated identity
  mapping and coherent text snapshots. `game_input`, `game_evdev`, `game_loop`
  now provide host-tested menu actions, explicit wire parsing/normalization and
  external-time serial steps. game_pump adds a bounded continuous scheduler with
  injected clock/read/wait/completion callbacks and byte-stream recovery through
  the same text entry. Simulated host verification is recorded above. The
  game_linux_io adapter now also has limited image-native compile/runtime/UAPI
  evidence, real mouse-byte publication and successful physical C menu selection.
  Real Linux capture and display/platform integration remain pending. Portable
  modules retain no Linux/BSP/OpenCV dependency; PC/bare-metal defaults are
  unchanged. Neither host checks nor the input diagnostic accept the full game.
- Port hardware access, not algorithms: replace standalone XAxiVdma/XVtc/XIicPs,
  XGpioPs, Xil cache calls, fixed linker DDR addresses, UART and timer glue with
  Linux MMIO, CMA/cache APIs, i2c-dev, GPIO, evdev and monotonic timing. Reuse
  `pynq_vision/` register sequences, RAW10 table, health checks and stride rules;
  do not transplant its Python capture-copy/HDMI overlay loop as the final game.
- Current diagnostic checks pass 14 adapter tests on the host, with the selected
  XSA and headless lifecycle mocks; see the diagnostic evidence above. The older
  22 shared Python checks remain historical and were not rerun for this task.
  Production MIPI setup/hold and seven Critical CDC failures remain open as
  recorded in Current Problem; this assessment does not authorize a build.

### 1280x800, Budget and Next Task

- Keep capture at 1280x720 RAW10/BGGR, BGR888 DDR, active row 3,840 bytes and
  stride 5,760. Separate capture and display dimensions/strides; current Python
  constants, views and fixed 74.25 MHz/720p VTC tables cannot select 800 lines.
  Obtain panel EDID or a vendor timing table (totals, porches, sync polarities,
  pixel clock); derive dynclk/MMCM values, VTC and MM2S height/stride together.
  Check video-out/rgb2dvi clock/range constraints. Whether the existing BIT can
  run that mode without RTL changes is unverified. No sensor-mode change needed.
- Three capture buffers use 12,441,600 bytes. Three 800-line BGR buffers need
  9,216,000 bytes at stride 3,840, or 13,824,000 at stride 5,760: combined
  **20.65-25.05 MiB**, excluding alignment/metadata. Configured 128 MiB CMA is
  nominally sufficient; actual allocation still needs measurement. At an upper
  bound of 60 capture + 60 display frames/s, active VDMA payload is
  **350.208 MB/s** (165.888 capture + 184.320 display); counting entire padded
  allocations gives a conservative **525.312 MB/s** span budget. Padding is not
  necessarily transferred by VDMA; CPU/cache/PL traffic is additional. Do not
  add a camera-to-display copy for the purely virtual background. Keep ownership
  safety until proven; resident PC-prepared sprites and simple CPU composition
  serve bring-up and the demo. PL rasterization is not a planned prerequisite;
  only measured insufficiency can justify a separate local optimization review.
  Neither 60 Hz nor recognition FPS is proven.
- Host free-space snapshot: C about **19.8 GiB**, D **47.7 GiB**. Assessment
  used existing Python 3.12 + pyelftools, direct read-only FAT/ext/FIT parsing,
  and existing Vitis compiler metadata; **no disk extraction or large copy**.
  For native application work reserve **0.1-0.5 GiB** host output/assets/logs and
  **0.3-0.5 GiB** additional SD rootfs space. The unexpanded image has about
  0.91 GiB free blocks, about 0.63 GiB excluding ext reserved blocks. Reuse the
  existing image; no second 5.719 GiB image required. A future matched minimal
  cross-sysroot may need **0.5-2 GiB** extra; these are planning allowances, not
  measured install requirements. Existing Vitis needs no new installation.
- **Later Linux integration task (after the engineering baseline):** retain the implemented three-level C
  rule core, standard C scene adapter, menu input, injectable runtime pump and
  unique offline text entry; retain the passed C physical selection seam, implement
  capture and display/platform glue, and reconcile artifact/clock
  ownership with the accepted stage-1 artifacts. Integrate canonical detector/ray/model code
  through the existing external-input/time API and versioned platform interfaces.
  Plan stock bootpy suppression and obtain panel timing; the offline UI
  already supplies an original distributable short-label Chinese font. Continue with image-native GCC, or first
  prepare a matching 2.27 armhf cross-sysroot; verify dynamic loader/symbol
  versions. Do not use the default 2.36 sysroot as a compatibility claim.
- **Separate hardware authorization:** stock autoload policy/configuration,
  real unplug/replug, exclusive MMIO/CMA/cache/VDMA ownership and any custom PL
  load remain separate tasks. Basic boot, mouse enumeration/Python events and
  native C compile/idle smoke evidence have been collected. Then validate static
  virtual HDMI then 1280x800 mode, and finally 720p camera + existing C detector
  and rays. Measure refresh, render time, recognition rate and mouse latency
  separately. Any write/probe/PL load needs that task's explicit authorization.
- Missing evidence: original image release/checksum and exact B-board/FSBL
  source or PS init, located board manual/reference ZIP, panel EDID/timings,
  custom-PL/capture/display board logs; original short-label Chinese assets are now supplied. Rebuild only if a required driver/
  kernel ABI, unavoidable PS initialization or validated display path cannot be
  supplied through existing runtime/user-space/DT changes. A DT-only or
  application/asset change does not by itself justify rebuilding Linux. If
  kernel work is proven necessary, assess a separate version-matched Linux
  build host and provision its storage there; no local PetaLinux fallback.
  None of these gates establishes the five-day delivery time.

## Minimal Vision Recognition Test

- Historical bare-metal SD layout is described by
  `color_test/sd_boot/vision/boot.bif`; the BIF alone does not establish the
  present BOOT payload. The current adjacent `BOOT.bin` fails the offline
  partition-range check (190 bytes past EOF), and its standard-BIT input differs
  from the current XSA/platform BIT. Do not use it as a current matched image.
  The separately verified historical `output/live` bundle and current Linux
  card are distinct routes; see Offline SD / Camera Test Entry Correspondence.
  No SD image was changed by this audit.
- Hardware: AX7Z020B / XC7Z020.
- Camera: OV5640 MIPI through the existing CSI-2/VDMA path.
- Resolution: 1280x720 active pixels.
- Pixel format: BGR888 in PS DDR; PL stream channel order is RGB.
- Capture buffer: three-frame S2MM ring; runtime address is exported by the
  probe. Active bytes per row are 3840 and buffer allocation is 4,147,200 bytes.
- Stride: 5760 bytes. The minimal probe addresses every pixel as
  `frame + y * stride + x * 3` and never treats active pixels as a tightly
  packed whole frame.
- Cache handling: S2MM capture is invalidated over `stride * height` before CPU
  access; the CPU-written display frame and the JTAG probe export are flushed
  before DMA/debug reads.
- Target: a pure-green solid circle or annulus. No white ring, black center, or
  other marker is required; the active path disables the generic six-class
  detector and calls the dedicated TARGET-only interface.
- Algorithm: stride-aware BGR888 sampling at step 4, integer OpenCV-scale HSV
  thresholding at H=34..70/S>=50/V>=50, sampled-grid cross open/close,
  8-neighbor components, area/aspect/fill/ellipse-coverage filtering, and
  full-resolution bbox/centroid reconstruction. The ring hole is deliberately
  excluded from the circularity decision.
- HSV calibration: the initial threshold passes all five supplied screenshots.
  Exposure, white balance, threshold margin, and false-positive behavior remain
  unverified on the live OV5640 stream.
- Processing time: the host C probe processed each supplied screenshot in
  about 0.03-0.04 seconds. The new detector has not been timed on Cortex-A9 at
  1280x720, so no board FPS is claimed.
- Host test: PASS for low-contrast solid green circle, green annulus, rectangle
  rejection, small-noise rejection, gray background, and all five supplied
  real screenshots. Each real screenshot produced exactly one C TARGET within
  the configured Python center/bbox tolerances.
- Build: PASS with ARM `-Wall -Wextra -Werror`; current TARGET-only ELF size is
  680,876 bytes, SHA256
  `F599AFEE650C52A9325AE94AF5A8C50584283D9846E1A21EB6E8398468F59CA1`,
  with text/data/bss 102455/3264/31532928 bytes. It contains
  `green_target_detect_bgr888`, `vision_overlay`, the TARGET UART format, and
  the pure-green startup string; it does not contain `CALIBRATION_REQUIRED`.
- Real-board result: capture-buffer PASS. With the verified debug BIT and one
  first-frame breakpoint, CSI reported 18,268 long packets, zero CRC errors,
  and running/error-free S2MM/MM2S. The first B/G/R means were 39/18/1 with
  1,852,614 nonzero channel bytes. After a deliberate scene change and a
  breakpoint-free 3-second run, the means changed to 243/165/207 with 2,758,803
  nonzero bytes; all four non-corner fixed samples changed substantially. CSI
  reached 2,342,537 packets with zero CRC errors and eight frames presented.
- Three-color diagnosis of the superseded RGGB BIT showed red-card B/G/R
  248/122/114 and blue-card 197/164/249, with matching wrong HDMI colors. This
  established an R/B Bayer-phase inversion before DDR.
- The latest BGGR/1.5x-RB hardware round measured red B/G/R 46.5/70/172.5,
  green 82/89.5/123, and blue 170.5/100/124.5. Red and blue orientation is
  correct, confirming BGGR and excluding a downstream R/B swap. Green failed
  the final display criterion; removing the known 1.5x R/B gain makes the
  inferred pre-WB means approximately 31/70/115, 55/89.5/82, and
  113.7/100/83, with the expected R/G/B dominance respectively.
- The user reports a successful live result with the current image. No saved
  HDMI frame, TARGET UART line, processing-time log, or negative-scene run was
  supplied, so quantitative live threshold/false-positive qualification is
  still open; do not use the wrong-color captures as calibration data.

## Architecture

- Hardware: AX7Z020B (`Zynq-7020B`) board with OV5640 MIPI camera.
- Capture format: 1280×720 RAW10. The sensor configuration is fixed to
  `0x4300=0x00`, `0x5000=0x06`, `0x5001=0x00`, and `0x501f=0x03`.
- The restored reference window is X `(0,2619)` and Y `(8,1947)`, with
  `0x3820=0x46` and `0x3821=0x01`. Including mirror/flip and crop parity, the
  effective CFA at the BayerToRGB input origin is BGGR (Xilinx phase 3).
- Capture path: `D-PHY -> CSI-2 -> BayerToRGB -> Gamma -> RGB unity-gain
  validation / optional color highlight -> capture VDMA S2MM -> PS DDR`.
- Game display: `PC offline backgrounds/finite-pose sprites -> SD files -> PS
  resident DDR + game snapshot -> CPU BGR888 copy/key + simple lines -> existing
  display VDMA MM2S -> video-out/rgb2dvi -> HDMI`. No camera background, GPU,
  PL game rasterizer or extra display DMA. Exact Linux binding is still gated.
- Stream color order after Bayer conversion is RGB; PS frame memory is BGR888,
  1280×720 with a 5760-byte stride.
- Legacy bare-metal capture uses a three-frame ring and a CPU safety copy;
  PYNQ Python frame diagnostics are retained, not the final game renderer.
  The target Linux game reuses the C detector/core. Capture/full-frame need
  follows the detector; display assets never require capture RGB. The current
  static display seam owns one immutable scan buffer; dynamic buffer switching
  remains unqualified. A park write/readback alone is not a reuse guarantee.
- Current host is Windows/PowerShell, canonical repository
  `D:\Workspace\AMD_camera\FPGA-main\FPGA-main`. Use its existing Vivado/Vitis;
  do not copy the project or assume WSL.

## Known Working

- `tests/test_sample_photo_regression.py` compiles and drives the real C
  detector, `ray_game_scene_from_detections`, and `ray_game_trace`; it accepts
  all 77 expected detection sets and currently passes 62 complete paths.
- The focused `test_ray_game.c` host executable passes after changing MIRROR
  physics to a finite reflecting segment and making duplicate Portal A or B
  pairs fail closed.
- OV5640 I²C control responds with sensor ID `56 40`; this verifies control
  access only, not MIPI video delivery.
- HDMI diagnostic color bars, display VDMA, dynamic pixel clock, and 1280×720
  VTC timing have worked on hardware.
- The camera recovery application has been downloaded successfully with
  `tools/program_camera_jtag.tcl`. In that verified run, CSI long-packet count
  increased from `0x000F7904` to `0x000FA5A1` in 500 ms, CRC remained clean,
  and capture/display VDMA operated normally.
- The accepted downstream contract remains `TDATA[23:16]=R`,
  `TDATA[15:8]=G`, and `TDATA[7:0]=B`. Hardware results with the BGGR BIT show
  red-card R dominance and blue-card B dominance, confirming the phase and
  downstream order. The newer unity-gain BIT is not yet hardware-confirmed.
- Sensor-side color ISP/CIP is disabled for RAW capture; PL owns demosaic,
  Gamma, white balance, and optional highlighting. Gamma selection is 1.8.
- RGB2DVI clock constraints now describe SerialClk and PixelClk as synchronous
  siblings from the same MMCM output path. The relevant implementation removed
  `TIMING-36`/`TIMING-30`, and directed setup/hold paths from TMDS encoder data
  to all OSERDES data inputs passed.
- Host verification has passed for the previously recorded camera-recovery,
  PC vision, PC/C parity, detector/overlay, and video-pipeline checks. The
  current strict ARM build passed with `-Wall -Wextra -Werror`; text/data/bss
  are `136895/3264/32462032` bytes. The camera-recovery host test now times out
  in this environment, as recorded above.
- The first repository cleanup removed only reproducible session/cache debris.
  Uncertain images, Vivado sources, build products, and boot artifacts were
  preserved.

## Current Problem

The following full-capture notes are retained historical evidence; current display
priority and acceptance are defined by Current Goal and Delivery Gates above.

- **Current PL-baseline result:** current complete RX/FIXED route formally
  STOPPED_NO_NEW_TIMING_MECHANISM (section23). LP-corrected fixture is preserved;
  no repeat implementation is scheduled, and no eligible replacement exists.
  No own positive routed/common budget or full-receiver acceptance exists.
  Production defaults, CDC repairs and historical failure counts remain.
  Section26 completes the single alternative-mechanism review:4x oversampling
  XAPP523 DRU fails its minimum-eye prerequisite under the unchanged model;
  no budget or actual implementation follows. AUTO remains unadmitted under
  section25. Section24's hardware/model boundary and all old stops remain active.

- **Current display milestone:** resident Sprite CPU composition is implemented;
  actual xlnk binary and one 4 KiB normal API/syscall test are now established.
  SD/HDMI still waits for safe status/rollback/owner/exit repair, the existing
  native binding, accepted PL release and panel/clock qualification. No display
  or DMA ran during the memory diagnostic; no new PL renderer is justified.

- **Retained historical production evidence (no production rerun this task):** the saved production timing evidence
  still fails MIPI setup/hold (WNS=-0.247 ns, WHS=-1.111 ns), and
  `reports/dphy_contract_gate.json` marks the production topology ineligible:
  coverage 64/64 and STA pairing verified, but fixed-setting timing, physical
  budget and startup bit identity all fail/remain unverified. The user has removed
  physical worst-case guarantee closure from current acceptance; the gate JSON
  still records its original stricter criteria and is not rewritten as passing.
  These are existing reports, not a new implementation of today's CDC-repaired
  sources. Repeating builds or reusing the historical XSA is not a timing repair.
  The bounded cHSSettled/PPI/HS-lock acceptances remain complete; a new full
  production report must eventually incorporate them. No failing tap setting,
  timing exception or relaxed margin is an acceptable baseline repair.
  The earlier default-off candidate was BUFH_DDIRECT_M3 (D bypass plus local matched
  MMCM/BUFH clocks); its complete rationale and go/no-go bounds are in
  `reports/dphy_sampling_proposal.md`. Its current RTL passes directed primitive/
  full-LP/SoT/startup tests. A preceding fixed OOC proved legal 12-pin routing but
  rejected the D-port common window (-0.932 ns, Slow alone -0.407 ns) and reported
  one CDC-10. The capture-reset request is now registered; current CDC classification
  remains unverified. Three revised launches historically failed in the synthesis
  runtime; the launch path has since recovered, but no new budget justified a
  current canonical OOC. Old report freshness is explicitly rejected. The latest
  ALINX/AMD generated structure was inspected successfully; its unplaced common
  window is -0.704 ns (zero-network frozen-primitive example -0.371 ns), so it
  supplies no credible positive-budget candidate. Stop phase/tap tuning; next
  establish a specific new structure's correlated delay/compensation budget.
  Do not wait for supplier intake or measurement, or claim the proposal passes.
  The implementation reuses canonical RTL, default-off candidate parameters,
  the hierarchy-aware IODELAY_GROUP selector and focused simulation/OOC wrappers.
  Input constraints, production configuration, BIT/XSA and board state are
  unchanged. Full physical/PVT qualification remains unclaimed.

- The PL feature tap is functionally verified and OOC timing closed, but the
  production top level is not timing/CDC clean. Vivado accepted literal MIPI
  delays `-min 0.268 ns` and `-max 1.518 ns` on both DDR edges and direct,
  control-flow-free constraints to every `oSyncStages_reg[0]/D`. The routed
  result is `WNS=-0.247 ns`, `TNS=-0.481 ns`, `WHS=-1.111 ns`, and
  `THS=-2.208 ns`, with two setup and two hold failures, all from the two MIPI
  data lanes through IBUFDS/IDELAYE2 into ISERDESE2. The worst setup endpoint
  is lane 1 `DDLY` with the expected `1.518 ns` input delay; the worst hold
  endpoint is lane 0 `DDLY` with the expected `0.268 ns` input delay.
  `SyncOverflowStatus` is now correctly reported as `CDC-3 Info`, but the
  saved pre-fix top-level CDC report has seven Critical findings: two `CDC-7`
  paths where each lane's `cHSSettled` asynchronously clears the one-stage
  settled synchronizer,
  three `CDC-10` paths from registered CSI lane-enable data through
  combinational fan-out to the D-PHY clock/lane synchronizers, and two
  `CDC-11` paths where the synchronized HS-clock lock state fans out to the two
  lane reset bridges. The build gate stopped before publishing a new BIT/XSA.
  Per the two-attempt rule, no further implementation run or shadow-mode
  integration was attempted. The follow-up sampling-window task reopened the
  existing routed DCP without synthesis, implementation, BIT/XSA publication,
  or hardware activity. `tools/analyze_dphy_sampling.tcl` checked all 1,024
  clock/data tap pairs (0..31) with unchanged input delays, primitive modes,
  and routing. Both lanes have zero feasible settings, even when their data
  taps may differ. With clock taps=0, both lanes need data taps<=9 for setup
  and >=29 for hold. The best worst-transition/DDR-edge/corner slack remains
  -0.759 ns for lane 0 (clock/data taps 0/18) and -0.754 ns for lane 1 (0/17).
  These are failing diagnostic candidates, not approved configurations; the
  production clock/data taps remain 0/12. The canonical lane ties IDELAY
  LD/CE/INC low, so the data delay does not perform runtime calibration.
  Reports are `reports/dphy_sampling_{baseline,methodology}.rpt`,
  `reports/dphy_sampling_taps.csv`, and `reports/dphy_sampling_window.txt`.
  The refreshed methodology report locates both TIMING-1 findings in the
  HDMI runtime MMCM/BUFR clock model, not in D-PHY; they remain a separate issue.

  The cHSSettled-only repair now replaces the single-stage `SyncAsyncSettled`
  in canonical `MIPI_D_PHY_RX/hdl/HS_Deserializer.vhd` with the existing
  two-stage `ResetBridge(kPolarity='0')`. `aSettled=0` clears both stages
  asynchronously, including while DivClk is stopped; `aSettled=1` releases
  dSettled only on the second subsequent DivClk rising edge. A stopped clock
  alone does not clear a previously high dSettled; the existing upstream
  clock-loss/reset logic must drive cHSSettled low. No clock detector, settle
  threshold, lane FSM, sampling configuration or constraint changed.

  Verification: canonical two-lane HS_Deserializer behavioral simulation
  passes 210 checks, including startup, stopped-low/high byte clocks, a short
  clear pulse entirely between byte edges, independent lane clearing,
  16 release-to-next-edge intervals, and reset/restart at the deserializer
  boundary. D-PHY-only OOC synthesis completed using the production XCI's
  two lanes, AXI-Lite enabled, no MMCM/debug, independent LP inputs and
  200 MHz RefClk. With the existing XDC unchanged, the actual CDC report
  classifies each cHSSettled crossing as `CDC-9 Info`, depth 2; both exact
  source/destination rows were checked and neither remains `CDC-7`.
  Evidence: `reports/dphy_settled_cdc.rpt`,
  `reports/dphy_settled_simulation.txt`, and `build/dphy_settled/` logs;
  reproducible entry: `sim/run_dphy_settled_test.tcl` (optional `sim` argument
  skips synthesis). An initial XSim observation-path error was corrected;
  the later post-report primitive/property assertion was replaced with the
  path/depth CDC checks. Only one OOC synthesis was run.

  Regression boundary: release is one byte-clock period later than before
  (14.284 ns at 280.034 MHz DDR/8). Digital reset checks do not prove analog
  metastability behavior, the complete lane FSM/LP/SoT, earliest first-payload
  retention, sensor clock detection, or hardware recovery. The previous
  routed setup/hold failures and top-level CDC-10/CDC-11 findings remain
  unresolved; this OOC boundary cannot re-accept their counts or the full
  production CDC report. No tap/phase sweep, full synthesis/implementation,
  BIT/XSA publication, project regeneration or board operation was run.

  Lane-enable directed acceptance (simulation + bounded CDC PASS; not production-qualified):
  Canonical CSI PPI_Clock_Enable registers clock/data enables from the same
  `vEnable and video_aresetn` expression on video_aclk/clk_fpga_1 (150 MHz,
  6.667 ns). Its comment explicitly requires simultaneous enable to avoid
  initial packet loss. BD connects CSI rx_mipi_ppi directly to D_PHY_PPI;
  RefClk is clk_fpga_2 (200 MHz, 5 ns). Originally the foreign PPI AND local
  software/RDY gates caused three CDC-10 paths. The rejected provisional
  per-lane input synchronizers instead caused three Critical CDC-11 paths:
  equivalent real CSI launch registers merged into csi_rx/aDEnableInt_reg[1],
  while all three ASYNC_REG receive chains remained.

  Canonical MIPI_DPHY_Receiver.vhd now has opt-in kPPISharedEnable (false by
  default in RTL/IP metadata). Only when ALL active PPI enables are the SAME
  source control may this be true. aClkEnable crosses SyncPPIClkEnable once;
  stage 2 drives rClkEnable/rDataEnable in RefClk. Current CSI-connected BD,
  local XCI and harness explicitly set true; IP XGUI propagates the parameter.
  Simulation asserts equal active input enables each RefClk edge in shared
  mode. Independent PPI users keep false: each lane retains its own input ->
  two-stage synchronizer -> gate. Default and per-lane port mappings were
  statically checked; matching values in one test alone never justify sharing.

  Software enable, real IDELAYCTRL RDY, three logical AND gates, all three
  original SyncAsyncEnable chains and FSM/reset receivers remain. No lane FSM,
  clock recovery, cHSSettled RTL, sampling/input delays, XDC, false_path or
  waiver changed. No substituted CSI sender, forced target control, hidden
  hierarchy or deleted receiver was used for acceptance. Digital latency:
  - PPI -> cEnable originally 2 RefClk capture edges; provisional/current paths
    both 4 edges. This revision adds zero latency; relative to original,
    +2 periods = 10 ns. CSI first registers vEnable/video reset on video_aclk;
    stopped video holds that register, including if video reset changes.
  - AXI xEnable -> rSoftEnable is 2 RefClk edges, then 2 through the original
    lane chain (4 total); rSoftEnable -> cEnable remains 2. RDY -> gate is
    combinational, RDY -> cEnable remains 2 edges. No pulse stretching added.
    Counts describe digital depth, not an analog metastability bound.
  - New PPI/original enable stages initialize zero, with no direct reset.
    Existing external/software ResetBridge assertion is asynchronous, release
    synchronous; IDELAYCTRL reset remains RefClk-synchronous. Stopped RefClk
    holds enable stages; reset/RDY may change the gate without immediately
    changing cEnable. HS/real BUFR byte-clock stop does not stop RefClk control.
    Recovery still requires existing explicit reset; no new recovery policy.

  Harness sim/dphy_lane_enable_harness.vhd retains canonical CSI launch FFs,
  complete two-lane D-PHY, AXI control and UNISIM IDELAYCTRL/BUFIO/BUFR. Changed
  RTL/harness were recompiled into a matching shared-mode snapshot. Scheduled
  events, duplicate-event avoidance, binary AXI control words and LP polarity
  aLP(1)=LP_p/aLP(0)=LP_n, HS request 11 -> 01 -> 00 are preserved. Only RDY is
  forced for digital fault injection; launch/gates/receive stages are observed.
  All 1,959 checks pass: enable/disable, captured/uncaptured pulses, every manual
  edge of PPI/software/original two-stage chains, shared stage-2 distribution,
  actual three cEnable/cIntRst receivers, software/RDY interleaving,
  video/external/software reset, stopped video, RefClk stopped low/high,
  HS stop/restart and actual BUFIO/BUFR clock activity. Previous 2,096 included
  two extra PPI chains; scenarios/assertions remain, with stage-2 distribution
  now checked each manual edge. After removing RDY injection, real UNISIM
  startup/reset, low/high RefClk loss and explicit-reset reacquisition pass.
  This is not analog calibration, automatic recovery, earliest-SoT/first-payload
  or hardware signoff. The resolved XSim immediate-force cause was not retried.

  Exactly ONE new minimal CSI -> D-PHY OOC synthesis ran with ordinary rebuilt
  hierarchy/equivalent-register merging. Actual csi_rx/aDEnableInt_reg[1]/Q
  drives only SyncPPIClkEnable stage 1 inside PHY (other endpoints are harness
  observation ports). Stage 1 drives ONLY stage 2. Stage 2, software stage 2
  and IDELAYCTRL RDY feed a real LUT3 AND INIT=8'h80. Three equivalent logical
  gates merge into ONE physical LUT3; its output feeds THREE retained original
  two-stage SyncAsyncEnable chains on RefClk. All three FSM/reset branches
  were traced through actual gates/FFs, not accepted from name/report counts.
  Audit retains Boolean ASYNC_REG handling, final-index-only replacement and
  all_fanin clock-pin observations, and additionally checks sender loads,
  first-stage isolation, shared stage-2 gate inputs and original ASYNC_REG FFs.

  ALL THREE target PPI branches PASS: common crossing CDC-3 Info depth 2, no
  target CDC-10 or other Critical CDC. Both exact cHSSettled ->
  SyncAsyncSettled/SyncAsyncx rows remain CDC-9 Info depth 2. Bounded report
  still has exactly TWO Critical CDC-11 rows: pre-existing HS-lock -> per-lane
  RxClkActiveHSResetBridge; untouched in THAT pre-HS baseline. The refreshed
  candidate results and completed bounded structural acceptance are below.
  This is not a refreshed production count;
  saved top-level report is unchanged. Entry sim/run_dphy_lane_enable_test.tcl
  (sim/cdc/audit; audit reopens only its DCP). Evidence:
  reports/dphy_lane_enable_{simulation.txt,cdc.rpt,structure.txt} and
  build/dphy_lane_enable/{simulation.log,lane_enable_synth.dcp,cdc_console.log}.
  Initial sandbox launcher access denial was resolved by its one permitted
  retry outside the sandbox; no project copy or shell workaround.

  Gap: supplementary independent-mode elaboration did NOT reach simulation.
  Two xelab.bat generic-argument attempts failed: unquoted '=' split the value
  into design unit work.false; quoting left a literal quote in the generic
  name (XSIM 43-3281). Stopped at two attempts and removed the unsuccessful
  optional runner entry. Evidence: build/dphy_lane_enable/independent_elaborate.log
  and independent_console*.log. Remaining hypothesis is Windows batch argument
  forwarding, not demonstrated independent RTL failure. No third attempt or
  unequal per-lane dynamic coverage is claimed; independent semantics have
  static mapping/default evidence only. Real-CSI shared-mode acceptance above
  completed independently of this supplementary gap.

  Boundary: unresolved csi_rx/LLP_inst/{DataFIFO,LineBufferFIFO} black boxes
  are outside the enable cones. Existing unscoped IODELAY_GROUP matches no
  nested PHY cells in the harness. Neither affects traced enable clocks/cones
  or cHSSettled evidence, but neither permits complete CSI datapath, placement
  or production timing signoff. Production IP/BD output products still need
  regeneration and full production timing/CDC review in a later authorized
  baseline task; existing build flow refreshes IP/catalog and BD targets.
  No full synthesis, implementation, BIT/XSA, settled simulation rerun, board
  operation, commit or push was performed. Delivery order remains qualified
  PL baseline -> board static-game HDMI -> mouse -> camera-driven gameplay.

  HS-lock shared-bridge repair (bounded simulation/structure/CDC PASS):
  Pre-candidate evidence: reopened the former PPI DCP without synthesis. Full
  fan-out of ClockLane/HSClockingX/SyncAsyncLocked/oSyncStages_reg[1]/Q WAS
  ClockLane/SyncAsyncLocked stage-0 D, both stages' PRE in EACH data-lane
  RxClkActiveHSResetBridge, and harness clk_active. Launch is the real BUFR
  byte_clk; all three internal branches receive on RefClk/clk_fpga_2. The raw
  activity source clears asynchronously on cBUFR_Rst and releases after two
  real BUFR rising edges. In no-MMCM mode cBUFR_Rst registers cHSRst on RefClk;
  there is no independent missing-HS-clock watchdog. Evidence preserved in
  build/dphy_lane_enable/hs_lock_before.{txt,log,jou}.

  Canonical DPHY_LaneSCNN now owns one ResetBridge(kPolarity='0') from raw
  HS activity to RefClk cRxClkActiveHS. MIPI_DPHY_Receiver distributes this
  internal signal to both DPHY_LaneSFEN instances. SFEN cHSClkRst is its inverse;
  former identical per-lane bridges are removed, not the receiving logic.
  ClockLane's existing SyncAsyncLocked now consumes the shared output and
  retains its own cHSRst, two FFs and falling-edge history/FSM. Per-lane enable,
  LP/FSM, cHSReset, cHSSettled and valid/Serdes/settled bridges are unchanged.
  Top-level/PPI interfaces, HS_Clocking, clock recovery FSM/thresholds, PPI
  sharing/gates, RDY/software control, HS_Deserializer, sampling and XDC are
  unchanged. Internal SCNN adds cRxClkActiveHS output; internal SFEN replaces
  aRxClkActiveHS with the explicitly RefClk-domain cRxClkActiveHS input.

  Digital latency (source semantics; dynamic coverage distinguished below):
  - Raw HS activity falling -> both cHSClkRst=1, cHSReset=1, cHSSettled=0,
    SyncAsyncValid=00 and downstream asynchronous reset/settled assertions
    remains asynchronous, including with RefClk/BUFR stopped; no edge added.
  - Raw rising -> data cHSClkRst release remains TWO RefClk capture edges.
    Lane FSM/settle conditions still determine cHSReset/cHSSettled release;
    SerdesReset and SyncAsyncSettled still require two actual byte edges.
  - ClockLane status rising changes TWO -> FOUR RefClk edges (+10 ns at
    200 MHz); falling stays TWO, or immediate via its own cHSRst. No change
    to external aRxClkActiveHS/raw two-byte-edge generation. Four directed
    relock phases verify the two/four-edge release relationship. Local reset
    preemption, active-lane reset/recovery and real BUFR stop/restart pass below;
    independent raw loss with cHSRst=0 is not reachable in this no-MMCM harness.
  - Startup common activity initializes 0 (data resets asserted). External/
    software reset keeps the existing core -> RDY/enable -> cHSRst -> registered
    BUFR-reset path. With RefClk stopped, those synchronous portions cannot
    advance. RefClk stop alone holds the bridge; HS/BUFR stop alone can hold
    raw lock high. An actual raw low still asserts the bridge asynchronously.
    No automatic clock-loss detection/recovery capability is claimed.

  Review of the previous stop: its RDY hold-low assumption was unsupported;
  its real-recovery test also reused enter_hs's manual RefClk stop/restart, then
  asserted cHSReset without observing lane LP/enable/FSM prerequisites. Keep
  manual timing only for edge-count isolation; real recovery now leaves the
  existing RefClk waveform continuous. With this sole stimulus timing change,
  the old 153.856856 us lane-entry failure no longer occurs. This implicates the
  test helper, not an established RTL defect; the exact previous RDY transient
  was not recorded and must not be invented as measured root-cause evidence.
  Canonical RTL, harness, generics, recovery policy/thresholds and XDC unchanged.

  check/runner Tcl now records LP/raw/filtered values, enable, FSM/next state,
  counter and bridge/history/q/loss values, including on assertion failure.
  It asserts lane prerequisites at LP-11/01/00 instead of relying only on delays.
  Software/PPI recovery waits through real 100 us initialization and re-enters
  the actual receive FSM; a recovered shared lock alone is insufficient.
  Pass markers are collected from actual output lines, not echoed Tcl source;
  failed XSim runs automatically write an explicit failure/partial report.
  sim-reuse verified all source path/size/mtime and compile configuration with
  the unchanged harness/default shared generic. No compile/elaboration rerun.

  Final directed simulation PASS: 4,673 checks (1,959 PPI + 2,696 HS + 18 startup).
  - PPI protects the actual CSI sender, three enables, software/RDY gates,
    video/external/software reset and stopped-control-clock cases.
  - Four relock phases (0.2/1.4/2.6/4.8 ns) verify raw 00/01/11 over two REAL
    BUFR rising edges, shared 00/01/11 over two RefClk edges, ClockLane history
    00/00/01/11 over four edges, with cHSRst=0, no loss pulse and stHS_Clk held.
    The added ClockLane 10 ns is accepted for these bounded digital scenarios.
  - Four reachable short locks preload real LP exit by 4/5/6/7 RefClk edges;
    raw is high at 5/4/3/2 subsequent capture instants. Local cHSRst preempts
    history rise, FSM reaches stStop, then actual cBUFR_Rst clears raw and shared
    plus both lanes' asynchronous resets without another capture edge.
  - Real external reset/RDY recovery, full data initialization, LP handshake,
    both stHS_Rcv states, cHSReset=0/cHSSettled=1 and downstream bridges pass.
    Independent LP resets assert one lane while the other remains settled.
  - Actual BUFR output stopped at BOTH 0 and 1, then explicitly checked held;
    HS input is held at 1 in BOTH cases, proving output phase coverage. Raw
    remains 1 on HS stop; stopping RefClk at either level holds controls.
    External reset reaches rIntRst asynchronously but raw holds until RefClk
    resumes; local cHSRst clears history/loss asserts, then registered BUFR reset
    clears raw and every shared/data reset, even with no byte edges. Restart
    passes real RDY reset/recovery and both data FSMs re-enter receive.
  - Software reset and PPI disable are exercised from actual stHS_Rcv, stop the
    real BUFR while BUFIO keeps running, then recover both lanes through full
    init/LP/FSM and SerdesReset=00, settled bridge=11, dLogicRst=0, valid sync=00.
  - No forced HS lock, sync stage, reset receiver or derived clock. RDY injection
    is confined to manual RefClk isolation and removed before real recovery.
    No independent missing-HS-clock watchdog was added. dValid remains 0 with
    constant test data: payload/SoT/valid=1 and analog reception are NOT tested.

  One minimal CSI -> D-PHY OOC synthesis completed (checksum c10535b2); new
  lane_enable_synth.dcp is the CANDIDATE, not the former 19:01:57 PPI baseline.
  New report_cdc: zero Critical rows, no CDC-11; raw byte-clock activity ->
  ClockLane shared bridge is CDC-9 Info depth 2. PPI remains CDC-3 Info depth 2
  and both exact cHSSettled paths remain CDC-9 Info depth 2. Two pre-existing
  CDC-26 Warning rows remain; no waiver, false-path expansion or RTL/name lock.
  The PPI structural audit passes all three actual receiver branches and gates.

  Final HS structural acceptance PASS on the SAME synthesized DCP. Audit now
  checks uniqueness then extracts the native object with lindex before scalar
  path construction/comparison. Do not return the whole one-object collection
  (it can add braces), or cast to plain NAME (get_property needs the native
  Vivado object type). The initial NAME-string attempt failed; native single
  objects passed the full audit. Keep clock polarity on pin IS_INVERTED=0;
  IS_C_INVERTED is not supported on the synthesized FDCE cell.
  - Real BUFR byte-domain raw/Q has exactly two shared-bridge CLR endpoints
    plus harness clk_active. No direct ClockLane or DataLane bypass remains.
  - Unique shared FDCE ASYNC_REG stages use rising RefClk, common active-low
    raw -> LUT1 inverter -> CLR, stage-0 D=1 and both CE=1. First-stage Q drives
    only second-stage D. The tool recognizes CDC-9 Info depth 2.
  - Shared second-stage Q has exactly NINE endpoints: ClockLane history stage-0
    D and both lanes' cHSReset PRE, cHSSettled CLR and two valid-chain CLRs.
    Both ClockLane history stages retain their local cHSRst (enable + FSM),
    q and loss/FSM fan-out. Each lane retains enable, LP/FSM reset/settled
    conditions and both two-stage ASYNC_REG byte reset/settled bridges.
  - PPI still passes all three real receiver/gate cones, CDC-3 Info depth 2.
    Both exact cHSSettled CDC-9 depth-2 rows and zero Critical CDC are asserted.
  Only audit mode ran: DCP SHA-256 de77244ccd83bcc0feb49bfd4011c45bd3d4b91d439bd4a3b68b2be5e2d30654
  and the prior simulation report SHA-256 are unchanged. No new simulation,
  elaboration, synthesis, constraints, RTL, harness or generic changes.

  Evidence: reports/dphy_lane_enable_{simulation.txt,cdc.rpt,structure.txt};
  build/dphy_lane_enable/{simulation.log,lane_enable_synth.dcp,
  hs_lock_review_sim*,hs_lock_review_cdc*,hs_lock_review_audit*,
  hs_lock_query.txt,hs_lock_query.log,hs_lock_name_audit*}. The refreshed structure
  report ends in DPHY_HS_LOCK_CDC_PASS with complete actual receiving-cone evidence.
  FIFO black boxes csi_rx/LLP_inst/{DataFIFO,LineBufferFIFO} and unmatched nested
  IODELAY_GROUP selectors still preclude complete CSI datapath, placement and
  production timing signoff. Sampling, HDMI, game and display binding untouched.
  No full build, implementation, BIT/XSA, board operation, commit or push.
  This bounded HS-lock task is complete; no further HS replay/build is indicated.
  Other production blockers remain paused until a separately scoped user task.

  The separately authorized compensation-topology task verified the source
  contract: `vision_ps_baremetal/src/ov5640.c` writes `0x4800=0x14` (bit 5
  clear: clock not gated between packets); the 720p array does not overwrite
  it. This is intended continuous HS operation, not live waveform evidence.
  Reset/standby and clock failure may still stop HS. UG472 requires reset
  after loss of MMCM LOCKED and forbids using unlocked outputs. DS187 specifies
  5 ns minimum reset and 100 us maximum lock time, far beyond the existing
  95 ns clock-settle timer, so relock cannot be assumed to fit one HS entry.
  `sim/run_dphy_clock_ooc.tcl` runs a test-only reset guard and non-project
  OOC fixture, reusing canonical `HS_Deserializer`. Startup/warm reset must
  assert `request_reset`; all reset counters run on always-on 200 MHz RefClk,
  reset is stretched to 40 ns, LOCKED is qualified, and capture reset asserts
  without byte-clock edges and releases through two byte-clock stages.
  Behavioral simulation passes injected 100 us startup/relock delays,
  stopped byte-clock loss, a latched short loss, and warm reset. This does
  not simulate analog MMCM acquisition, IDELAYCTRL RDY/reset sequencing, or
  the full LP/SoT state machine.
  The candidate uses M=3,D=1,VCO=840.101 MHz, outputs /3 and /12 through
  matched BUFGs and a BUFG feedback path; the unfinished production MMCM
  branch remains untouched/off. Isolated synthesis/place/route completes.
  With unchanged 0.268/1.518 ns input delays, all 768 tested phase/tap pairs
  (24 serial phases at 15-degree intervals x 32 taps) fail a common window.
  Each lane also has zero passing phase/tap pairs. Best margin is -3.070
  ns at serial phase=0 degrees/data taps=0; this is a rejected candidate,
  not evidence that every alternative compensation topology is impossible.
  The initial routed phase=60 degrees/taps=12 input path has setup=-5.346 ns:
  0.595 ns launch/capture requirement, -1.441 ns destination-clock insertion,
  and 2.708 ns internal data delay. Global WNS=-6.081 ns belongs to asynchronous
  RefClk-to-byte reset logic; it is not the sampling-window result.
  The fixture consumes 190 LUTs, 128 FFs, one MMCM, four BUFGs and two IDELAYs
  (no debug cores). OOC methodology includes asynchronous RefClk-to-byte
  reset warnings; its un-routed refclk/reset boundary and ignored output
  initializer also require review before any production reuse. Outputs live
  under `build/dphy_clock_ooc/` and `reports/dphy_clock_ooc_*`; no canonical
  RTL, sensor configuration, production project, BIT/XSA or board was changed.
  Reference sources: Digilent OV5640 config, Linux OV5640 bit-5 definition,
  AMD UG471/UG472 and DS187; do not interpret a passing guard test as packet
  retention or first-frame acceptance after clock restart.

  The contract/bit audit now records the user-confirmed hardware: ALINX 7020B,
  ALINX AN5641 OV5640 (module model now explicitly confirmed by the user) and
  15 cm 15p FPC. The sensor-module PCB revision, transmitter
  per-edge guarantees, module/carrier/FPC relative delay, relative jitter and
  duty-cycle bounds remain UNKNOWN; cable length alone is not differential
  data-to-clock skew. `tools/audit_dphy_contract.py` parses existing reports
  offline, reconstructs 34 signed setup/hold paths, and emits four lane/edge
  budget rows without treating missing terms as zero. The current model's
  guaranteed pin eye is 0.5355 ns; its physical applicability is unverified.
  Production setup is limited by Fast and hold by Slow corners. At clock/data
  taps=0/12, the common additional-capture-shift necessary interval is
  [0.247,-1.111] ns (empty by 1.358 ns); it is a diagnostic bound with fixed
  bit pairing, not a programmable phase or timing exception. Existing OOC
  detailed paths give [5.346,3.554] ns (empty by 1.792 ns), but only detail
  lane1/fall setup and lane0/fall hold; other lane/edge/corner paths are missing.
  At OOC phase=0/tap=0 each lane's aggregate window is empty by 1.518 ns.
  Q8->raw(7), WordAlignment, then LaneSFEN.MakeLSF restore chronological bits
  to PPI bit0 first. SoT 0xB8 becomes raw 0x1D. A host algebra check passes
  64 payload/word-offset cases across offsets 0..7; this does not verify RTL
  startup, LP, soft SoT matches or packet retention. The OOC phase60 default
  STA pairs ideal C1 with b1, while production zero-phase C1 pairs with b0;
  actual captured bit identity/first payload R/F phase remains unproven.
  Reports: `reports/dphy_contract_audit.md`, `dphy_contract_paths.csv`,
  `dphy_external_budget.csv`, and `dphy_capture_bit_map.csv`. No constraints,
  RTL, builds or board state changed; migration stays paused.

  The sampling evidence tooling now adds `analyze_dphy_sampling.tcl
  --corners-only`: ONE successful reopen of the existing production routed DCP,
  32 fixed-setting report requests, no sweep/property/constraint changes, build
  or DCP save. The initial sandbox launch failed before Vivado started; the
  same command succeeded on its single permitted external retry. DCP SHA256
  remains 9680cfbc9e400b6300be5dbe9f065b0a351b4c686159b8be1f44a6ba4626876e.
  Vivado reported three decimal places (the unsupported six-digit request
  fell back to three; the script option is corrected without another query).
  The completed report contains 128 production paths: 64 primary adjacent-bit
  checks (setup=UI, hold=0) and 64 additional, weaker DDR checks (setup=T,
  hold=-UI). The audit preserves and labels both; additional checks cannot
  replace the primary bit association or manufacture a window by cycle modulo.
  All 64 lane/P-N/Fast-Slow/capture-edge/data-transition/setup-hold coverage
  items have their primary path, and the zero-phase STA bit association passes.

  At unchanged clock/data taps=0/12, lane0 Fast's diagnostic shift interval is
  [0.234,0.012] ns and lane1 Fast's is [0.247,0.025] ns: both empty by 0.222 ns.
  Slow intervals are [-0.746,-1.111] ns and [-0.732,-1.097] ns: both empty by
  0.365 ns. Thus the current setting has empty within-corner windows as well as
  the known all-lane cross-corner interval [0.247,-1.111] ns. It is not merely
  a mismatch between otherwise-open Fast/Slow windows. These are fixed-bit
  diagnostic shifts, not programmable phases or a new tap sweep; they do not
  rule out every other setting or sampling architecture.

  `audit_dphy_contract.py --corners-report reports/dphy_sampling_corners.rpt`
  reconstructs 130 signed paths including the two unchanged OOC details,
  splits data/clock primitive and residual contributions, and reports per-corner
  and cross-corner coverage/windows. Clock residual includes route/source/CPR
  terms and is not additional jitter. Physical budget and startup/first-byte bit
  identity remain unverified; `candidate_eligible=false`. OOC remains rejected,
  with only 2/64 detailed coverage items; no OOC reopen or run was performed.
  Interrupted reports fail closed. Offline parser/gate regression and original
  64-case bit algebra pass; see `sim/test_dphy_contract_audit.py`. Outputs extend
  the existing `reports/dphy_contract_*` owner with coverage/window CSVs and a
  versioned gate JSON, plus `reports/dphy_sampling_corners.{rpt,log}`. No RTL,
  XDC, IP/BD, sensor mode, software, CDC bridge, BIT/XSA or board state changed.

  Physical-contract research is DEFERRED outside the current engineering/game
  acceptance. The four rows below are retained as UNKNOWN, not zero. The former
  supplier/measurement-before-topology rule is superseded by the user's scope
  change and the updated Delivery Gates and Next Task. No new source search is
  required to start the model-based offline design. The attempt policy remains
  at most two validation attempts per proposed
  scheme, then failure analysis and a revised scheme, with at most three scheme
  revisions. The old missing-parameter stop applies to any future request for
  physical qualification, not the current roadmap. No topology-validation
  attempts or scheme revisions have been made in the research/planning tasks;
  no automatic retry/build is pending.

  Source findings: the [ALINX AN5641 manual](https://www.alinx.com/public/upload/file/AN5641_UG.pdf)
  is indexed as a 15-pin, 1.0 mm pitch, two-lane OV5640 module. The user now
  confirms AN5641 as the actual module model; its PCB revision remains unknown.
  An [official English manual](https://alinx.com/public/upload/file/AN5641_User_Manual.pdf)
  is also indexed. The manual-reading blocker is now resolved for the English
  manual: the official URL returns gzip-compressed JavaScript access-verification
  HTML rather than PDF bytes to direct retrieval. That is a source-access issue,
  not evidence of a corrupt or unparseable PDF. The browser exposed the
  [CodeRobin product page's manual link](https://coderobin.com/products/alinx-an5641-5mp-ov5640-mipi-camera-module)
  to the [published ALINX manual copy](https://raw.githubusercontent.com/fpgauk/pdf/main/alinx/an5641/AN5641_User_Manual.pdf).
  Browser link download succeeded; the copy is retained at
  `output/pdf/AN5641_User_Manual.pdf` (388465 bytes, 6 pages, unencrypted;
  SHA256 af737ccb66c996c760bcc1c6d55847c36672ed5231bd4038de3c02a7b5cb9672).
  This is a distributor-published copy, not a hash match against the currently
  inaccessible official download. Both pypdf and Poppler read it successfully;
  searchable text is in the adjacent `.txt`, and all six 150-dpi rendered page
  screenshots `output/pdf/AN5641-page-{1..6}.png` were visually reviewed.
  Page 4 contains the pin table and connector schematic; pages 5-6 show cable
  connection photographs. The complete six-page copy has no per-edge MIPI
  output-eye, relative-jitter, duty-cycle or propagation-skew guarantees needed
  by the four-row budget. Reading is fixed; the physical-contract task remains
  paused. The official B-specific carrier schematic has now been retrieved and
  visually audited as described below.
  Reuse the local PDF; use text extraction for search and rendered screenshots
  for tables/diagrams or absent text, rather than repeatedly treating a web
  parser failure as document unreadability. Provenance is in the adjacent
  `AN5641_User_Manual.provenance.json`. No FPGA implementation or board action.
  The readable [OmniVision OV5640 specification v2.01, vendor-hosted copy](https://files.waveshare.com/upload/d/da/OV5640_DataSheet.pdf)
  section 6.7 (PDF page 96) gives MIPI lane/register information and refers
  further detail to the sensor FAE; it does not establish the four required
  output-eye guarantees. Table 8-5 (PDF page 166) describes XVCLK input-jitter
  tolerance, not MIPI data-to-clock output jitter. DVP/SCCB timing and generic
  D-PHY compliance assumptions cannot replace this missing module/link contract.

  Additional official carrier evidence: the ALINX repository's
  [AX7Z010B/AX7Z020B schematic](https://github.com/alinxalinx/AX7Z020B_2023.1/blob/master/Hardware/01_SCH/ax7z010B_ax7z020B_SCH.pdf)
  is retained at `output/pdf/ax7z010B_ax7z020B_SCH.pdf` (342045 bytes, 14 pages;
  SHA256 bae1c24b07068db9637f9087ebda3a3290a086feae25aae775310d5aa54ac07b).
  Pages 2 and 13 were text-extracted and rendered, then visually reviewed;
  connector/net labels and resistor values are legible despite Poppler font
  warnings. The title block identifies revision 1.0, November 25, 2022; the
  installed hardware revision is still unconfirmed. J23's two HS data pairs
  and clock pair route towards core-board connector J1. Page 13 shows 150-ohm
  cross-pair resistors R114/R116/R117 and separate 100-ohm LP branch resistors
  R113/R115/R118/R120/R119/R121. Equal nominal resistor values do not bound
  data-minus-clock propagation, branch loading or receiver crossing times.
  The official `Hardware/02_PCB` directory also publishes the B-specific carrier
  `AX7Z010B_AX7Z020B_Allegro.brd`; it has not been downloaded or electrically
  modeled. Its availability alone gives no qualified trace-delay interval or
  module/FPC/core-board timing guarantee. The same repository's
  `Hardware/04_datasheet/Sensor` contains only LM75, not OV5640/AN5641 output
  timing. Targeted AN5641 skew/jitter/duty-cycle searches did not supply the
  missing guarantees; unrelated boards' levels, reference-clock specifications
  and generic D-PHY values were not adopted. New evidence closes a source-access
  gap, not any of the four numerical pin-budget rows. Research is paused again
  at the missing-parameter gate, with topology attempts/revisions still 0/0.

  Targeted source coverage: AN5641 skew/jitter/timing and FPC propagation,
  OV5640 MIPI transmitter eye/skew, output relative jitter, clock duty/half-period
  and stable-clock/first-packet timing. No applicable worst-case guarantee was
  obtained. Additional public source research now resolved two new primary-text
  leads, both downloaded as actual readable PDF bytes under `output/pdf`:
  - `OV5640_Product_Specification_v2.33.pdf`: 177 pages, 2021-01-27 revision,
    [LCSC-hosted manufacturer document](https://datasheet.lcsc.com/datasheet/pdf/319eb7b75101a9e4b6ca032e4eae2b9c.pdf?productCode=C5182161),
    2,045,018 bytes. Section 6.7/table 6-8 (PDF pages 92-94) gives MIPI control
    registers and directs further questions to OmniVision FAE; section 8.4/table
    8-5 (PDF page 164) gives XVCLK input-period jitter, not MIPI output-relative
    jitter. No applicable four-row output eye/half-period guarantee was found.
  - `OV5640_MIPI_Application_Notes_R2.15.pdf`: 66 pages, 2012-02-21 revision,
    [public copy of manufacturer application note](https://file.hstatic.net/1000180878/file/auto_focus_camera_module_application_notes__with_mipi_interface__r2.15.pdf),
    6,904,351 bytes. Section 4.5 (PDF page 29) documents stream on/off via
    `0x4202=0x00/0x0f`. It does NOT establish stable continuous HS clock while
    stream-off, its interaction with `0x4800=0x14`, or a stable-clock-to-first-SoT
    minimum in this RAW10 mode. This is a supplier-confirmation lead, not an
    approved startup sequence, sampling topology or software change.
  Both copies have adjacent provenance JSON (source URLs, byte counts, SHA256,
  revision and reviewed pages), targeted text extracts and rendered page PNGs.
  Tables/section 6.7 on pages 92/164 and stream control on page 29 were visually
  verified. Poppler's two font warnings on the application note do not obscure
  the relevant register values. Neither copy is hash-verified against a sensor
  manufacturer endpoint or qualified for the installed AN5641 PCB revision.
  AN5641 manuals/carrier schematics remain the inherited connectivity evidence.
  The remaining NXP AN13573 lead was checked against the official search-indexed
  text of [revision 1.1, 2024-08-13](https://www.nxp.com/docs/en/application-note/AN13573.pdf).
  Indexed section 6.1/table 20/figure 58 describes a 720p 16-bpp example at
  approximately 168 MHz HS clock, not this AN5641 RAW10/approximately 280 MHz
  actual link. Its configuration and startup waveform examples do not close
  any missing row. Full PDF retrieval remains unverified: the web reader hit a
  20,622,036-byte content-size limit; direct download was sandbox-blocked and
  its single approved retry returned HTTP 404. No PDF/provenance/screenshot file
  was created, no figure was visually verified, and no numerical guarantee
  depends on this source. These are retrieval limits, not a corrupt-PDF finding.
  No further equivalent download retry, unchanged generic-manual re-audit or
  FPGA run is pending. All four physical rows remain UNKNOWN. They no longer
  block model-based sampling design under current acceptance; Linux resource
  inspection still cannot replace them as physical timing evidence.

  **Optional supplier intake, outside current delivery:** public documentation
  has not closed the actual-link guarantee. A future supplier/FAE response can
  improve the evidence, but no user consultation or reply is required for the
  current roadmap. Codex owns interpretation if new material becomes available.
  ALINX's [official documentation contact](https://docs.alinx.com/wiki/AMD-Dev-Board/RFSoC/AXW47/AXW47-User-Manual.html#contact-information)
  publishes `technical@alinx.com` (company support contact, not a model-specific
  timing guarantee). Request actual-hardware MIPI AC/eye/link-skew and startup
  evidence below; do not ask the user to research general manuals again. Ask FAE
  specifically whether stream-off can leave stable HS clock running so capture
  can lock before stream-on. If these guarantees are unavailable, request an
  explicit statement of missing coverage and a supplier-supported, timing-verified
  AX7Z020B/AN5641 reference receiver with its operating conditions and constraints;
  a demo that merely displays video is not production timing qualification.

  Inherited AN5641 CD/customer evidence: the user identifies these materials as
  already analyzed during earlier real-scene ray-overlay work. The switch to a
  pure virtual game does not invalidate matching camera configuration/capture/
  recognition evidence; old preview/overlay display acceptance remains separate.
  `C:/Users/11967/Downloads/CD.rar` is 291748482 bytes, SHA256
  `9ec699eacae655c85e8b75a68b7d49b1e7c044fbd1cde80beeda7e23a82197b2`.
  Its 3143-member inventory and seven selected text members were streamed with
  Windows bsdtar (CP936 listing), without extracting/copying/executing a project.
  This CD's `project/ax7z020/22_an5641_mipi_hdmi` is the older custom-DPHY
  reference, distinct from the public AMD-IP implementation described below.
  The original 720p table explicitly comments MIPISCLK=280M; registers
  0x3034/35/36/37, 0x3108 and 0x4837 all match the current Linux diagnostic table.
  Its XCI selects two lanes, no MMCM. The saved 2017.4 routed report dated
  2020-03-19 has WNS=0.726/WHS=0.034 ns but reports 13469 no-clock register pins
  rooted at dphy_hs_clock_clk_p, 21599 unconstrained max-delay pins and eight
  inputs with no delay. It therefore does NOT establish MIPI timing signoff;
  do not restore its incomplete clock/delay model or old CDC exceptions.
  The re-supplied ALINX support chat replies 'frequency should be 270MHz' and
  '540Mbps' to the official 1280x720 RAW10/two-lane question, and says the Vivado
  CSI IP configured lane rate is intentionally higher to retain headroom. This
  answers the nominal-frequency/configured-rate question; do not ask it again
  as if no reply exists. It is not a measured clock or a min/max tolerance,
  four-row eye/skew/jitter/duty-cycle/link guarantee or first-SoT guarantee.
  Reconcile the support reply's applicable register/clock-source revision with
  the CD/current mode before changing any constraint; IP capability configuration
  is not the physical clock constraint. Screenshot retained as
  `output/pdf/AN5641_support_270MHz_540Mbps_20261018.jpg`; original chat date is
  not visible. Archive hashes/member provenance, six register comparisons and
  exact report checks are in `output/pdf/AN5641_CD_20261018.inventory.json`,
  `AN5641_CD_selected_reference_20261018.json` and
  `AN5641_CD_support_reuse_review_20261018.json`. The old conversation title
  was not located in the available recent/first archived listings; no full-history
  retrieval is claimed. No RTL/XDC/mode/build/board action. Four pin rows remain
  unverified; no replacement sampling topology is selected.

  Actual-link/startup follow-up closes two remaining CD source checks. The
  one-page AN5641 module schematic (2019-10-16, revision left as <RevCode>)
  shows the three HS pairs and power/reset circuitry, but no trace/FPC delay,
  eye, relative-jitter, duty-cycle or first-SoT bound. Its X1 is labelled 12 MHz
  and external-clock resistor R9 is NC; this identifies a documented circuit,
  not the installed module revision, oscillator tolerance or actual HS clock.
  The three-page Digilent D-PHY receiver 1.0 guide (2017-12-15) documents
  BUFIO/BUFR /4 and a different 672 Mb/s-per-lane example; its tested-throughput
  statement is not an AN5641/FPC transmitter guarantee. Text extraction and
  rendered schematic/page-2 diagram are legible despite font warnings. Exact
  PDFs, text, PNGs and hashes are under `output/pdf/AN5641_CD_*`, with source
  members in `AN5641_CD_link_startup_20261018.provenance.json`.
  Targeted public searches still supply no applicable actual-link AC guarantee.
  The upstream Linux OV5640 driver provides stream controls but uses different
  MIPI interface/idle settings; neither it nor continuous-clock register intent
  guarantees stable HS clock during this mode's stream-off or a minimum lead to
  the first SoT. This source check does not authorize a startup sequence change.
  All four rows and the three supplier startup guarantees below remain UNKNOWN.
  The research task used 0 topology attempts/revisions. Physical research is
  deferred; the next unique task is model-based offline sampling design, not a
  supplier request, generic-manual search, build or board probe.

  Uploaded ALINX material review: eight supplied PDFs comprise six unique byte
  contents (the HLS pair and Linux-application pair are exact duplicates). All
  six are readable; 278 pages were text-extracted, with relevant diagrams/tables
  visually reviewed. The three AX7Z020B manuals agree on the page-32 MIPI HS
  pins Y7/Y6, W11/Y11 and U9/U8; they do not supply the missing AC bounds. The
  two 42-page V1.0 manuals differ in normalized text on pages 7/16/18/41, while
  their page-32 rendered images are byte-identical. Document dates/revisions
  still do not establish the installed PCB revision. Linux application V1.06,
  pages 7 and 49-53, uses PetaLinux 2017.4 and the AN5642 binocular parallel
  cmos_vsync/href/pclk/data -> 16-bit YUV422/VDMA/V4L2 path, not this AN5641
  MIPI RAW10 receiver. HLS V1.03 is an SDx 2017.4/AN5642-family tutorial; the
  SD restore PDF describes image writing only. Neither supplies pin guarantees.
  Source hashes/duplicate mapping/page text and selected PNGs are retained under
  `output/pdf/ALINX_uploaded_materials_20261018.*` and `uploaded_alinx_*`.

  A NEW official implementation lead was also obtained directly, so the user
  need not locate another public reference archive: ALINX
  [22_an5641_mipi_hdmi](https://github.com/alinxalinx/AX7Z020B_2023.1/tree/master/course_s2_vitis/22_an5641_mipi_hdmi).
  Read only three text blobs from its Vivado/auto_create_project subtree (tree
  SHA `5d25996c5e691aba5b37327b6de2446b96f17ffa`): create_project.tcl,
  pl_config.tcl and src/constraints/mipi.xdc. The reference uses AMD MIPI CSI-2
  RX Subsystem 5.3, two lanes, RAW10, FIXED calibration and configured
  C_HS_LINE_RATE/DPY_LINE_RATE=1000; its physical HS pins match. That configured
  rate is not a measurement or guarantee for the current approximately 280 MHz
  HS clock. Its IP/register/VDMA layout differs from the custom receiver, and
  its pin-only mipi.xdc does not close the four timing rows. No qualified timing
  report, applicable end-to-end eye, or first-SoT guarantee was obtained. Thus
  it is a source-comparison lead, not an approved migration/topology or baseline.
  Complete selected text, immutable blob SHAs and SHA256s are retained in
  `output/pdf/ALINX_AN5641_official_reference_intake_20261018.json`. At that intake,
  no reference Tcl was executed or project created. The later explicitly
  authorized comparison has now generated the matching AMD IP configuration in
  an in-memory diagnostic project and legally synthesized only its PHY. The
  vendor full-project Tcl was not executed or cloned; no production replacement,
  BIT download or hardware operation followed. Its new unplaced budget is
  rejected as detailed in the sampling proposal section 10 and Delivery Gates.
  Remaining supplier intake is still the actual-link timing/startup package
  below; do not ask for more copies of general HLS/Linux/board manuals.

  **Four-row physical contract (all times at FPGA package pins, ns):**

  | Lane / clock reference edge | Clock P/N | Data P/N | TX earliest/latest | Link data-minus-clock delta min/max | Relative jitter early/late | Clock high min/max; low min/max; frequency tolerance | Status |
  |---|---|---|---|---|---|---|---|
  | lane0 / rise | Y7/Y6 | W11/Y11 | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN; UNKNOWN/UNKNOWN; UNKNOWN | UNVERIFIED |
  | lane0 / fall | Y7/Y6 | W11/Y11 | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN; UNKNOWN/UNKNOWN; UNKNOWN | UNVERIFIED |
  | lane1 / rise | Y7/Y6 | U9/U8 | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN; UNKNOWN/UNKNOWN; UNKNOWN | UNVERIFIED |
  | lane1 / fall | Y7/Y6 | U9/U8 | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN; UNKNOWN/UNKNOWN; UNKNOWN | UNVERIFIED |

  These are physical reference-clock edges, not the CSV's internal capture-edge
  selector. Every cell must cover both P/N conductors and both data transition
  directions, or a documented worst-case envelope; that coverage is UNKNOWN too.
  TX/clock-bound source version, actual sensor/module/carrier/core-board revisions,
  15 cm 15-pin FPC part number, voltage/temperature/load coverage and jitter
  inclusion are UNKNOWN. Manual revision does not identify the installed PCB.
  The module, FPC, connectors, carrier and core-board propagation intervals are
  individually UNKNOWN; the link column denotes their bounded combined effect.
  Neither equal resistor values nor cable length establishes those intervals.
  The retained `dphy_external_budget.csv` is an inherited model: its 3.571 ns
  period, 1.7855 ns UI, 0.268/1.518 ns input limits and 0.5355 ns pin eye are
  NOT measured or supplier-qualified physical values. Reports and XDC were only
  read; they were not regenerated or edited to present UNKNOWN terms as zero.

  **Optional material for future physical qualification (not a resume gate):**

  These document types are not required by the current board-game acceptance.

  1. Supplier identification of installed AN5641 sensor/module PCB revision,
     carrier/core-board revisions and FPC/connector part numbers, or a written
     statement that the supplied timing envelope covers all of those variants.
  2. Prefer ONE supplier-qualified end-to-end timing/eye specification at the
     above FPGA pins for existing two-lane 720p RAW10 / approximately 280 MHz HS
     clock operation. It must give the four rows' earliest/latest transitions
     (or equivalent setup/hold), P/N and transition coverage, bounded relative
     jitter, high/low half-period min/max and frequency tolerance, with supply,
     temperature, receiver termination/load, crossing definition and source
     revision. State which uncertainty terms are already included. If this
     document is unavailable, request the OV5640/AN5641 MIPI transmitter AC
     specification/FAE guarantee plus qualified combined link delta min/max;
     only if needed, obtain module/FPC/connector/carrier/core-board propagation
     characterization or SI signoff for the actual revisions. No need to model
     segments separately when a qualified combined guarantee subsumes them.
  3. Supplier startup/restart sequencing guarantee for this register mode:
     shortest stable-HS-clock-to-first-SoT interval, stop/restart conditions and
     whether the transmitter can defer the first packet until the receiver MMCM
     has locked and capture reset has released. All three remain UNKNOWN.
     Existing `0x4800=0x14` expresses continuous-clock intent only. The inherited
     95 ns settle timer cannot stand in for the documented 100 us maximum MMCM
     lock budget, reset/qualification and byte-domain release latency.

  For exclusive TX/link/jitter terms only, pin earliest = TX earliest + delta
  min - early relative jitter, and pin latest = TX latest + delta max + late
  relative jitter, using the same specified reference edge/crossing. A supplied
  pin envelope that already includes jitter replaces those component terms;
  do not add them again. RMS alone is not a deterministic bound, XVCLK input
  tolerance is not MIPI output relative jitter, nominal frequency/50% drawings
  do not bound either half-cycle, and internal primitive/route/CPR terms already
  in the signed path budget are not additional external uncertainty.

  **Current next task:** follow Delivery Gates and Next Task. The four rows stay
  UNKNOWN/UNVERIFIED and optional intake no longer blocks a new offline candidate
  under the unchanged 0.268/1.518 ns model and 15% UI margin. Explain legal primitive
  connectivity, window-width/corner improvement, bit/byte alignment and startup
  assumptions. Do not repeat rejected scans. Directed LP/SoT/first-payload/reset
  simulation, all 64 OOC coverage items and full engineering timing/CDC/resource
  acceptance follow in separately scoped tasks; no pin guarantee is inferred.
  Keep the two-round/three-revision limits and accepted cHSSettled/PPI/HS-lock
  boundaries. Supplier consultation and external measurement are not pending
  actions. This planning task changes only PROJECT_STATE, with no RTL/XDC/IP/BD,
  software/mode change, Vivado/DCP operation, BIT/XSA or board/interface action.

- The 77-image path regression is not yet green. `054`, `055`, `059`, and
  `061` miss an expected MIRROR; `057` and `058` falsely hit one; `066` and
  `067` enter Portal A although they should go to the boundary; `074` reaches
  TARGET; and `076`/`077` do not reach TARGET after transfer. `033`, `034`,
  `038`, and `040` also reverse the static Portal solid-to-ring axis.
- Two SOURCE-direction refinements were tried and reverted because neither
  preserved the full source set. Do not tune them further without a separate,
  evidence-led task. The current samples do not establish that a board-plane
  homography is necessary: the grid images have not yielded a 0.5 cm reference
  comparison, and the observed endpoint errors are still entangled with SOURCE
  direction and marker localization.
- Hardware captures from the superseded RGGB BIT proved that effective BGGR
  sensor data was decoded as RGGB, swapping red and blue before DDR. The PL
  Bayer mapping and build-source refresh are corrected, but intentionally have
  not been verified on the board.
- The visible stutter is independently explained by the full-frame diagnostic
  CPU scan: color processing takes about 399-429 ms per frame, limiting the
  presentation loop to roughly 2.26-2.42 FPS. This task did not change the
  recognition algorithm or diagnostic scan.
- The first MicroSD cold-boot log exposed a software health-check race: after
  one second of valid capture, `CameraObserve` replaced the CSI counter baseline
  but left an older S2MM frame-completion bit set. `CameraCheck` then returned
  immediately on `21600 -> 21600` and falsely rejected the error-free first
  attempt. Later reset attempts introduced CRC and VDMA frame-size errors.
- Source now clears the stale W1C frame-completion indication at the start of
  every observation window and bounds startup/runtime recovery. The correction
  is built into the current ELF and `sd_boot/vision/BOOT.bin`; it has not run on
  hardware.
- Camera delivery has failed intermittently after cold power-up or reset. A
  failed run showed stationary CSI long-packet count and retained color bars;
  reset has also restored traffic without changing the image, cable, or power.
- The latest `vision_ps_baremetal` black-screen guards have now reached a first
  camera-frame commit on the board under controlled JTAG startup. Codex did not
  independently observe the physical HDMI image or recognition overlay.
- Recognition behavior has synthetic tests, five real screenshot regressions,
  and a user-reported successful live result. The live result has no retained
  HDMI/UART evidence, so field accuracy and false-positive behavior are not
  independently established.
- The PYNQ image now boots and has limited native C input smoke evidence;
  see PYNQ Migration Status. CmaTotal and I2C node numbering are observed,
  while actual DMA allocation, runtime Overlay imports, HWH/wiring compatibility,
  Overlay/VDMA/CSI, saved-frame color and board FPS remain unverified.
- Known PS/PC differences remain: 4× coordinate/area quantization, connected
  components instead of contours, approximate orientation/perimeter and WALL
  overlap, limited marker hierarchy checks, and no SOURCE black-border
  recovery. These limit accuracy claims until real-scene evaluation.
- Global timing analysis still contains existing MIPI/debug-related no-clock
  and unconstrained endpoint findings. The last recorded report had 1699
  no-clock objects and 2370 unconstrained internal endpoints, plus dynamic-MMCM
  methodology warnings. These are not evidence of a proven RGB2DVI data-path
  failure.
- White-balance gains remain a baseline and require gray-card calibration.
  Optical blur still requires mechanical focus unless the module is confirmed
  to include a powered VCM with the correct AF firmware.

## Debug Evidence: Confirmed Facts

- Current ELF: `color_test/build/vision_ps_baremetal/output/vision_ps_baremetal.elf`.
  The rebuilt image contains the BGGR startup contract string and is matched to
  the new XSA. Symbol addresses from older ELF builds must not be reused as
  current breakpoint evidence.
- Previous hardware observation: main executed and CPU was once stopped in
  UART TXFULL polling. No matched LR/UART/CSI/VDMA snapshot was available;
  this observation does not establish black-screen causality.
- Build script explicitly selects `ps7_uart_1` for stdout; BSP defines stdout
  as `0xe0001000`. main prints before application-level UART initialization.
  Generated `ps7_init.tcl` contains UART1 baud/control writes and the debug
  programming flow calls ps7_init before downloading the ELF. Actual register
  state and physical serial wiring remain unconfirmed.
- Startup includes five seconds of bars and at least two seconds of GPIO
  delays, plus configuration/processing. An eight-second arbitrary CPU halt
  cannot establish whether CameraStart was reached.
- Debug script now uses ELF symbols for function breakpoints and current-ELF
  objdump call-site parsing for internal milestones. It validates CPU0 stop
  reason AND PC before reporting a stage hit. First-frame commit additionally
  requires `vision_frames_presented == 1`, resolved from the ELF symbol table.
- A staged hardware run hit main, the CameraStart call and entry, GPIO-delay/I2C
  and sensor-configuration milestones, CameraCheck, and VisionRunOnce with exact
  breakpoint PCs and matching backtraces. At CameraCheck the CSI long-packet
  count was 21,574 with zero CRC errors; at VisionRunOnce it was 45,783 with
  zero CRC errors and S2MM running without an error status.
- The staged run did not reach the commit breakpoint within 60 seconds. Its two
  timeout snapshots 500 ms apart were unchanged in `sensor_configure`/`usleep`,
  after recovery had restarted CameraStart; CSI was 378, CRC was 1, and S2MM was
  halted with error status. This is breakpoint-perturbed behavior, not a proven
  cold-start failure.
- A separate low-interference `first-frame` run reached PC `0x00111b38` at
  `VisionRunOnce()+984` (`main.c:310`) with `vision_frames_presented=1`, CSI
  long packets 18,720, CRC 0, and running/error-free S2MM and MM2S status.
  UART1 SR was `0xA` (TXFULL clear), and no snapshot or backtrace was inside
  `XUartPs_SendByte`.

## Current Hypotheses

- UART blocking did not reproduce in the staged or first-frame runs. The old
  UART polling observation remains unpaired with a same-run snapshot and is not
  established as either a root cause or a recurring fault.
- Controlled JTAG startup successfully committed a frame, so it does not
  reproduce the reported intermittent black screen. Do not modify BSP, outbyte,
  or MIPI RTL without a matched failed-start capture identifying the stalled node.

## Missing Evidence

- A matched capture from a genuine failed cold start/reset remains missing;
  repeat controlled and cold-start runs are needed to establish intermittency.
- Physical HDMI image/overlay observation and UART1 connector/MIO routing remain
  unconfirmed by Codex even though the JTAG first-frame commit succeeded.
- CSI long-packet count is not an independent valid-frame counter. S2MM frame
  completion and software validation provide the current frame evidence.
- Register snapshots are sequential, not atomic; PL continues during CPU halt.
  Breakpoints perturb startup and can cause overflow or change reproducibility.

## Important Files

- `AGENTS.md`: repository working rules for Codex.
- `color_test/color_test.xpr` and
  `color_test/color_test.srcs/sources_1/bd/system/system.bd`: main Vivado project
  and block design.
- `color_test/color_test.srcs/constrs_1/new/system.xdc`: top-level constraints,
  including the corrected runtime RGB2DVI clock relationship.
- `color_test/rtl/axis_color_highlight.v`: PL white-balance/highlight stage.
- `color_test/software/mipi_hdmi/mipi_hdmi/src/main.c`: camera recovery program.
- `color_test/software/vision_ps_baremetal/`: current PS vision application,
  tests, build scripts, and its detailed changelog.
- `color_test/tools/build_bitstream.tcl` and
  `color_test/tools/build_camera_recovery.tcl`: controlled build entry points.
- `color_test/tools/program_camera_jtag.tcl`: protected full JTAG programming
  flow with BIT/XSA/ELF freshness checks.
- `color_test/sim/test_camera_recovery.py`,
  `color_test/sim/tb_axis_color_highlight.sv`, and
  `color_test/sim/tb_axis_color_isp.sv`: focused recovery/color verification.
- `pc_vision/`: PC reference detector and thresholds used for PS parity.
- `pynq_vision/`: Linux/PYNQ hardware adapter, board CLI, offline tests,
  environment checker, overlay packager, and staged operator instructions.

The canonical Bayer implementation is
`color_test/repo/ip/AXI_BayerToRGB/hdl/AXI_BayerToRGB.vhd`; Vivado synthesizes a
generated `color_test.gen/.../ipshared/<hash>/hdl/AXI_BayerToRGB.vhd` copy. The
BIT build script updates the packaged-IP checksum, rebuilds the IP catalog,
upgrades the BD instance, and resets generated targets before OOC synthesis so
the generated copy cannot silently retain stale Bayer logic. Do not compensate
a Bayer phase error by swapping downstream RGB channels.

## Changes Made

- Camera setup and stream start were separated; recovery has bounded attempts,
  VDMA reset timeouts, CSI/CRC/frame checks, and a diagnostic-bar fallback.
- The SD cold-boot false-negative fix now snapshots CSI counters, clears any
  pre-window S2MM completion, waits for a fresh completion, stops infinite
  camera reinitialization after bounded recovery, and reports the actual
  three-buffer S2MM addresses.
- RAW10 sensor verification, PL demosaic/Gamma/white balance, build freshness
  checks, and protected JTAG programming were added.
- The BayerToRGB demosaic now implements effective BGGR/Xilinx phase 3 while
  preserving RGB AXI output and BGR888 DDR layout. OV5640 setup restores the
  reference crop and verifies crop, mirror/flip, and RAW register readback.
- `tools/build_bitstream.tcl` now refreshes the packaged Bayer IP checksum and
  regenerates its BD target before launching synthesis, preventing Vivado from
  reusing the former RGGB `ipshared` source.
- `axis_color_highlight.v` now uses explicit R/G/B 1.0/1.0/1.0 pass-through
  gains for the white-balance validation point. Bayer, Gamma, highlighting,
  AXI handshaking, DDR layout, and recognition thresholds are unchanged.
- `vision_ps_baremetal` gained full-frame ownership, PC-aligned HSV/component
  detection, HDMI overlay, bounded dynamic-clock waits, and safer PS-only ELF
  download behavior that does not reinitialize PS clocks/DDR.
- `vision_ps_baremetal` now also has a dedicated pure-green solid-circle/ring
  TARGET detector and active TARGET-only main-loop path. Its real-image harness
  reports each compile/run stage and enforces subprocess timeouts so sandbox or
  tool-launch failures cannot masquerade as detector hangs.
- The latest offline black-screen protection distinguishes display startup from
  first camera-frame commit, validates S2MM completion, preserves the last good
  display frame, and keeps the diagnostic loop alive after capture failures.
- RGB2DVI runtime clock constraints were corrected and reimplemented.
- The PYNQ migration added a same-XSA Overlay packager and a Python hardware
  adapter while keeping `pc_vision` as the single OpenCV detector. The board
  path defaults to TARGET-only and records capture/cache/copy/OpenCV/HDMI/total
  timings.
- A separate `sd_boot/vision/boot.bif` now packages the matched standalone FSBL,
  standard BIT, and `vision_ps_baremetal.elf` without overwriting either legacy
  SD image.
- The temporal path now confirms all six object classes independently, applies
  SOURCE hysteresis/non-consecutive sampling and Portal signed-direction lock,
  and requires three topology/geometry-consistent candidate rays before one
  atomic display-ray commit. TARGET is a non-blocking latch.
- `green_target_recognition/` is a self-contained OpenCV image/video/camera
  utility for the supplied pure-green solid-circle or annular target. It uses
  scene-derived HSV plus connected-contour circular geometry and leaves the
  existing bare-metal detector and `BOOT.bin` unchanged.
- `green_target/` is a user-requested delivery snapshot. It preserves the
  relative repository layout needed by the host regression, Vitis build, and
  Bootgen BIF; includes the five real screenshots and matched FSBL/BIT/ELF/
  `BOOT.bin`; and excludes Vivado/Vitis caches, generated IP netlists, run
  directories, reports, logs, and captures. The original paths remain the
  canonical development implementation.
- `detector/` is the current six-class delivery package. It preserves the paths
  required by the host tests, XPR/XSA-based rebuild, ARM build, and Bootgen;
  includes the 25 non-TARGET and five TARGET 50 cm captures; and provides a
  package README, `VERIFY.ps1`, and a complete `SHA256SUMS.txt` manifest.
  Canonical development remains outside this copied delivery folder.
- Repository workflow rules now define focused startup checks, generated-file
  boundaries, WSL/Windows cooperation, Vivado cost control, infrastructure
  failure handling, Git review, and concise state maintenance. `.gitattributes`
  defines stable LF/CRLF behavior without bulk renormalization.

## Verification

- The repartitioned `axis_vision_features` focused simulation passed with 240
  transparent video beats, 15 sampled feature beats, independent randomized
  backpressure, exact HSV/mask comparison, and 0 failures. The existing focused
  simulations also remained green: `axis_color_highlight` completed 17 checks
  with 0 failures and `axis_color_isp` passed. OOC synthesis completed with 0
  errors at `WNS=+0.211 ns`, using about 500 LUTs, 321 FFs, 4 DSP48E1s, and
  0 BRAM.
- Production CSI synthesis confirmed `kDebug=0`; its synthesized logic used
  660 registers and no ILA instance resources, and no production `.ltx` was
  emitted. The focused CSI overflow simulation passed. Two top-level
  implementation attempts failed the timing gate as recorded under Current
  Problem. The build script now reports clock interaction/CDC, checks both
  setup and hold slack, and publishes BIT/LTX/XSA only after both timing gates
  pass. The existing `build/hw/system_wrapper.bit` predates that corrected
  publication order and is not an accepted production artifact; the XSA was
  not replaced.

- Hardware-confirmed: the old RGGB BIT inverted R/B before DDR; the following
  BGGR/1.5x-RB BIT corrected red and blue orientation but made the green card
  R-dominant after fixed white balance. No hardware result is claimed for the
  new unity-gain BIT.
- Focused Vivado simulations pass: `axis_color_highlight` completed 17 checks
  with 0 failures, and `axis_color_isp` confirmed unity RGB pass-through.
- Green-target offline verification passes the Python synthetic regressions,
  the strict host C solid/ring/rejection tests, and all five supplied real-scene
  C/Python comparisons. The C results were centers (133,382), (135,58),
  (638,49), (726,387), and (458,231); every image produced exactly one TARGET.
- Current strict host verification passes `-std=c99 -O2 -Wall -Wextra
  -Werror` for six-class/source/overlay, green TARGET, ray-game, and the retained
  standalone temporal-stabilizer tests. Production no longer calls that
  stabilizer. Ray tests cover MIRROR near-face/end-cap normals, WALL and TARGET
  termination, first-frame SOURCE drawing, immediate SOURCE/object updates,
  missing Portal display, parallel same/reversed Portal axes, 90-degree and
  30/-55-degree axes, A-to-B/B-to-A transfer, solid/ring local-coordinate
  preservation, side switching, outward direction, and exit non-rehit.
  `test_video_pipeline.py` also passes the direct first-frame path and confirms
  no SOURCE-move clear or inventory gate. The PC reference's main suite passes.
- The generic SOURCE path is disabled and the synthetic unmarked warm triangle
  is rejected. Tightening only the dedicated marker-pair shape-support floor
  rejects the former wrong `222735` pairing without changing any protected
  color threshold. The 30-image marked-SOURCE run now accepts 20 valid frames,
  all within the existing 38-degree direction tolerance, and explicitly rejects
  10 clipped/weak/ambiguous samples. Mean direction error is 9.3 degrees and the
  maximum is 31.6 degrees. Do not reuse the earlier 30/30 claim. Synthetic
  marked rotations still pass.
- Fifteen retained real PORTAL_A/PORTAL_B/MIRROR images pass PC/C recognition
  after the direction and geometry changes. The SOURCE parity fixture now uses
  a black shell around separate colored and white marker regions, and both PC
  and C recognize its SOURCE category. PC now derives the complete two-part
  marker center and bbox from the colour seed plus white region enclosed by the
  same black shell, matching C without widening the 5-pixel parity tolerance.
  SOURCE parity passes 5/5. The post-change 30-image real regression remains
  20 accepted, 10 explicitly rejected, mean error 9.3 degrees, maximum 31.6
  degrees, with no wrong direction; no production threshold changed.
- `tests/test_portal_video_regression.py` and its C bridge were added to run the
  production detector, stabilizer and ray game frame by frame and measure the
  requested SOURCE P95, marker support, Portal flips/local position/side, and
  MIRROR boundary residual. Visual Studio 2022 Professional supplies a native
  x64 C compiler. The runner now loads its environment through a temporary
  one-layer command script, invokes `cl.exe` directly with `/W4 /WX`, and
  releases the loaded DLL before automatic cleanup. The complete 10126-frame
  2026-10-06 capture passes: SOURCE direction P95 is 0.55 degrees across 2887
  stationary steps with no unsupported marker; 988 Portal transitions have
  0.00 px maximum local-position error with no side error; and 565 MIRROR hits
  have 0.00 px maximum boundary residual. No consecutive Portal pair met the
  runner's <=20 px stationary filter (`portal_steps=0`), so its separate
  frame-to-frame 180-degree-flip metric was not exercised.
- The current ARM size total of 32,457,936 B for zero-initialized storage is
  expected: the map has `.bss` 32,435,404 B plus an 8,196 B aligned heap and
  14,336 B combined stacks. Three 6,220,800 B `frameBuf` stores and two equal
  `captureAux` stores account for 31,104,000 B; detector grids/queues and driver
  state, including the 864-byte persistent `ray_level`, account for the
  remainder. DDR spans `0x00100000..0x40000000`, while BSS/heap/stacks end at
  `0x02018510`. Capture buffers are disjoint from the two
  active display buffers; `frameBuf[0]` is intentionally capture-ring slot 0.
  No fixed DDR overlap is present.
- The real SOURCE regression's default `--max-error` is explicitly 38 degrees,
  so its 31.6-degree maximum passes the existing coarse directed-pose criterion.
  The independent video stability criterion is much tighter and passes at
  0.55-degree P95. No SOURCE threshold was changed for either result.
- The `tests/test_video_pipeline.py` timeout is resolved. Stage probes showed
  source reads in 0.001 s, macro extraction in <0.001 s, function/source
  generation in 0.003 s, and static assertions in 0.001 s. The hang occurred
  before source writing because Python `TemporaryDirectory(dir=project/build)`
  could not create a directory in the environment-mediated generated build
  tree and did not return an exception. An isolated `mkdtemp` probe reproduced
  the stall, while OS-temp creation took 3 ms. Temporary HOST files now use the
  OS temp directory, each external command has a bounded timeout and visible
  output, and the strict generated unit uses `-O2 -Wall -Wextra -Werror`.
  Final timing was 0.789 s for GCC compile/link, 5.680 s for the executable,
  and 6.484 s total; camera health, ownership, retained-frame behavior, ACTIVE
  SOURCE dropout/jump, and candidate-invalid persistence all pass.
- The 135.000--165.000 s window of
  `C:/Users/11967/Videos/2026-10-06 10-24-54.mp4` passes using a 5 s warmup and
  every 13th 30 fps frame, matching about 2.31 processing cycles/s. It decoded
  1,050 frames and processed 81 cycles, with 69 measured cycles and 65 ACTIVE
  cycles. Fifteen ACTIVE cycles had no current SOURCE and 13 candidate-invalid
  events occurred, but `active_zero_ray_frames=0`; there were no unexpected
  SOURCE relocks, locked-SOURCE changes, unconfirmed clears, or zero-display
  invalid frames. Twenty-two complete display-ray changes committed atomically.
  The former approximately 150 s disappearance did not recur. No TARGET hit
  occurred in this window, so the two-hit lifecycle remains covered by strict
  host unit tests rather than this video slice.
- The direct-path 75.767 s `2026-10-06 23-56-00.mp4` regression decodes all
  2,272 frames and records 2,241 ACTIVE frames, zero active zero-ray frames,
  zero display clears, one non-blocking TARGET event, SOURCE direction P95
  2.42 degrees, 218 Portal transfers with 0.86 px maximum local-position error,
  no Portal side errors, and 327 MIRROR hits with 0.00 px boundary residual.
  Raw signed-Portal-axis flips are now 0 in 3,836 stationary steps without a
  persistent direction lock or temporal vote. The local endpoint-component
  check reduced the same-video baseline from 82 to 7 on its first adjustment
  and to 0 on its second and final adjustment.
- The `green_target/` delivery snapshot was verified independently of the
  original application path: its copied source trees and boot artifacts match
  the originals by SHA256, all `.xpr`/BIF inputs exist, and its bundled five
  screenshots pass the strict GCC C/Python regression. `SHA256SUMS.txt` covers
  every delivered file except itself. Temporary probe files and Python caches
  were removed after verification.
- The `detector/` package was verified independently from inside the copied
  directory. Strict C and green TARGET host tests pass; PC/C parity passes 5/5;
  the copied five-class samples pass PC/C 25/25; and the copied TARGET samples
  pass 5/5. Every copied source/artifact tree matches its canonical input by
  SHA256, all XPR and BIF inputs exist, and no `.Xil`, cache, runs, generated-IP,
  log, `__pycache__`, or test-build output remains. Its manifest covers every
  delivered file except `SHA256SUMS.txt` itself.
- Vivado-confirmed for the unity build: the white-balance OOC run synthesized
  the canonical `rtl/axis_color_highlight.v`; OOC synthesis, top synthesis,
  implementation, and bitstream generation completed. The new BIT is
  1,994,204 bytes with SHA256
  `A5A88800AF559C2E95AD67453DEAB7D4EC5BDFEAA3ECCDDC7279F0F2F64F3E55`.
  Existing global timing still fails with WNS -2.822 ns, TNS -177.369 ns, and
  83 setup endpoints.
- Previously offline-confirmed on the pre-MVP source: recovery, PC vision,
  video-pipeline fault injection, and ARM strict build checks listed below.
  Current detector/overlay, PC/C parity, and ray-game host results are the new
  runs recorded above; do not treat the earlier video-pipeline result as a
  successful rerun of the current extraction test.
- The current PS-only ARM build uses the unchanged XSA/existing BSP and the exact
  compiler, linker script, libraries, and strict flags from
  `tools/build_vision_ps.tcl`: Cortex-A9 VFPv3 hard-float
  `-O2 -Wall -Wextra -Werror`, linked with `-lxil -lgcc -lc -lm`. The known
  generated-platform permission path was not retried because XSA and PL
  interfaces are unchanged. The result is ARM ELF32, little-endian, EABI5
  hard-float. The linked symbols include `ray_game_scene_from_detections`,
  `ray_game_trace`, and `vision_detect_bgr888`; the unused legacy
  `vision_stabilizer_update` is absent from the linked ELF.
- The current
  `color_test/build/vision_ps_baremetal/output/vision_ps_baremetal.elf` is
  856,464 bytes, timestamp 2026-10-13 10:16:22 +08:00, SHA256
  `453C559EE7EE7050EE0183A854DFBDA05D69DDCC5B69F1C2B23C2178A1A6AFC5`.
  ARM size is text=142,479, data=3,264, bss=32,457,296 bytes. Its timestamp is
  later than the latest Portal source timestamp, and its hash differs from the
  superseded ELF.
  The effective FSBL is
  `color_test/build/vision_ps_baremetal/vision_ps_platform/zynq_fsbl/fsbl.elf`, 472,824
  bytes, timestamp 2026-10-13 10:15:53 +08:00, SHA256
  `C204DD713EB00693A916453700BF024E85019257856F59686956474842CEAFC4`.
  The BIT used by that earlier BOOT build is retained at
  `color_test/build/vision_ps_baremetal/vision_ps_platform/hw/color_test.bit`, 1,994,204 bytes;
  the root `build/hw/system_wrapper.bit` has since changed (see Current Goal).
  timestamp 2026-10-04 20:56:34.519 +08:00, SHA256
  `A5A88800AF559C2E95AD67453DEAB7D4EC5BDFEAA3ECCDDC7279F0F2F64F3E55`;
  no BIT was regenerated. The repository `color_test.xsa` and the platform's
  exported, `hw`, and `tempdsa` copies are all 998,809 bytes, timestamp
  2026-10-04 20:57:02.045 +08:00, SHA256
  `03AE58AC8483359101E5286931EFFB0D84544F4B9B6C215572FF88653011E0C8`;
  `platform.spr` points to that unchanged handoff, and the FSBL content hash is
  unchanged.
- Bootgen 2023.1 ran from `color_test/sd_boot/vision` as
  `bootgen.bat -arch zynq -image boot.bif -o BOOT.bin -w on`; it returned 0 and
  reported successful generation, with only the existing partition-memory-range
  overlap warnings. The replacement `BOOT.bin` is 2,245,840 bytes, timestamp
  2026-10-13 10:16:32 +08:00, SHA256
  `30B532FE6325312CDDE6438040228FB4580FCB5371E9ED2D5D42DFED6C543AE4`,
  different from the superseded image SHA256
  `627F886AF2CE67BEC124DE09CB199684AF2891AEF93A9A564EA9E85575CE4D8C`.
  Its `boot.bif` names the FSBL, unchanged BIT, and current level-state ELF
  above, in that order. Two attempts to invoke the documented Bootgen `-read`
  mode both failed during command-line parsing, so the current BOOT has a
  successful generation result but no fresh partition-table or payload-equality
  verification. The focused ray-game, 77-photo, extracted-main video-pipeline,
  and strict ARM gates pass. Hardware and SD boot are NOT PERFORMED, and the
  image has not been copied to SD.
- PYNQ historical checks: partition/signature inspection, the then-matched
  BIT/HWH pair, 22 shared detector tests, 5 adapter tests and Python compilation.
  Today's image/kernel/config/FIT/ELF checks and stale-artifact/FCLK findings
  are in PYNQ Migration Status. Historical hashes do not qualify the current
  standard BIT or XSA; no board-side PYNQ result is claimed.
- Hardware-confirmed in this task: standard matched BIT/ELF JTAG programming;
  staged startup through VisionRunOnce; and low-interference first-frame commit.
  Still unconfirmed: visible HDMI overlay and real-scene recognition accuracy.
- The HDMI debug bitstream was rebuilt outside the Codex sandbox from the current
  `system_wrapper_opt.dcp`. The 2026-10-02 17:28:25 output has SHA256
  `71ABE20440B9095D34B69E9ADABA465F0C266524BB24E0334E731EFD55E58EBC`.
  DRC has 0 errors/0 critical warnings and 21 warnings. Timing is not clean:
  WNS is -2.564 ns and TNS is -178.036 ns across 85 setup endpoints, matching
  the existing base implementation's unresolved cross-clock class rather than
  a new debug-core-only failure.
- The standard camera BIT/XSA/PS-init/ELF freshness gate passed after regenerating
  the camera-recovery platform and ELF from the current XSA. No file was
  downloaded: XSCT saw the Digilent cable twice but both scans reported
  `DR shift through all ones` and exposed no APU/device target.

## Do Not Investigate Again Without New Evidence

- A valid OV5640 ID does not prove the MIPI lanes are delivering frames.
- Gamma AXI-Lite read data is fixed at `0`; `3` is the written 1/1.8 selection,
  so a readback of `0` is not a startup failure.
- Do not enable sensor CIP/AWB/CCM while PL performs RAW demosaic and color work.
- The accepted channel contract is RGB on AXI stream and BGR888 in PS memory;
  do not swap channels to hide a Bayer phase error.
- The old CPU stop at `0x0010b4c0` was the `_exit` loop from the old
  `mipi_hdmi.elf`, not proof of a PL or camera fault.
- A Hardware Target shutdown is a debug-connection event, not direct evidence of
  camera failure.
- PixelClk and SerialClk are sibling clocks derived from the dynamic MMCM path;
  the former `PixelClk -> SerialClk x5` generated-clock model was incorrect and
  has already been fixed.
- Sharpening or Gamma cannot repair optical defocus. Confirm lens/VCM hardware
  before adding autofocus code.

## Remaining Issues

- Finish the production timing/CDC baseline before shadow mode. The exact
  literal input delays and broad synchronizer-first-stage selector are now
  proven active and must be preserved; do not relax the documented 15% UI
  margin or waive the remaining Critical CDC paths merely to make reports green.
  The two cHSSettled CDC-7 paths are repaired and verified as CDC-9 Info at
  the canonical D-PHY OOC boundary and retained in the CSI/D-PHY integration
  audit. All three PPI lane-enable branches now pass directed simulation and
  bounded shared-CSI CDC acceptance (CDC-3 Info depth 2 before RefClk fan-out).
  HS-lock now also passes bounded full structure/CDC acceptance after native
  single-object audit normalization on the existing DCP: both target CDC-11 are
  gone (one shared CDC-9 Info depth 2, zero Critical CDC); ClockLane and both
  DataLane receiver cones are retained. Prior directed simulation passes 4,673
  checks; final audit required no sim/synthesis rerun (details in Current Problem).
  This HS task is complete. The fixed-setting sampling evidence task is also
  complete; sampling RTL repair, HDMI timing and Linux display binding remain
  pending separately scoped work.
  The sampling-window analysis rules out tap-only tuning of the existing
  routed topology, and the isolated matched-BUFG/MMCM candidate is rejected.
  Fixed-setting corner evidence now shows that both lanes also lack a
  within-corner diagnostic window at taps=0/12 (Fast -0.222 ns, Slow -0.365 ns),
  not just a cross-corner intersection. Do not repeat this evidence query or
  infer that temperature-dependent tap selection alone fixes the current setting.
  The user has removed physical worst-case qualification from the current
  delivery. Four pin rows and supplier startup guarantees remain UNKNOWN and
  deferred, not an active wait gate. The model-based offline proposal is now
  BUFH_DDIRECT_M3; GCC launch and fixture precision/capture faults are resolved.
  Current directed functional evidence passes (72 primitive lane/cases, separate
  22 controller lane/cases and 33 assertions). The preceding fixed OOC supplies
  actual D-port/BUFH evidence but rejects the common window (-0.932 ns). Current
  registered capture-reset RTL still lacks OOC/CDC reclassification: two helper
  runtime failures and one single-thread failure exhausted that historical run
  path. A separately authorized recovery now passes synthesis-only via the
  native-console launch path; implementation/CDC acceptance is still pending. Do not
  repeat scans or proceed to full builds. The subsequent structure-budget task
  rejected routing-only/HPC optimism before RTL changes: Slow clock-network
  difference is 0.404 ns and primitive difference 0.097 ns versus a frozen-term
  allowance of 0.0935 ns; joint closure still needs independent evidence. Its
  executable budget diagnostic passes 15 tests, without new structure acceptance.
  Report/source freshness is checked; old reports cannot qualify current RTL.
  The latest explicitly authorized one-seed internal-feedback/HPC routed probe
  is also rejected: Fast/Slow/common=0.000/-0.275/-2.175 ns. Vivado selected
  INTERNAL and legal dedicated HPC, but the full cross-corner delay did not
  close. This attempt is stopped; new functional/receiver-OOC/production-top
  gates are NOT_RUN. See proposal section 11 and the current Delivery Gates
  for the unique next feedback-budget review; retain all preceding failures.
  External/startup assumptions are not measured
  guarantees. Preserve
  the 15% UI margins and do not add multicycle/false-path exceptions merely
  to make sampling timing pass. A later sampling-specific task must establish
  a legally clocked, latency-compensated sampling topology and prove a common window,
  including the sensor's HS-clock continuity, reset/relock and first-byte
  requirements. Do not enable the unfinished MMCM path by changing an IP
  parameter alone: the top-level lane instance forces it off and its existing
  60 MHz/MMCM constants do not model the 280.034 MHz input. Keep the input-delay
  contract and current working RTL until a replacement has focused evidence;
  no passing sampling repair is claimed by the diagnostic sweep. The
  PPI lane-enable paths pass at the bounded shared-CSI boundary; HS-lock CDC
  classification and full structural acceptance are repaired there.
  The
  settled bridge's extra byte-cycle latency still needs earliest-SoT/first-payload acceptance before
  production readiness. Only after non-negative top-level setup/hold slack
  and reviewed CDC results should work proceed in order: feature tap + feature VDMA shadow
  mode, frame-by-frame comparison with the C golden model, PS consumption of
  the PL feature map, then shared frame ring and PL overlay.

- `tools/test_host.ps1` now includes the sample-photo fixture, but its current
  run stops earlier in `test_vision_ps` (`expected six detections, got 2:
  WALL, PORTAL_B`). Preserve that synthetic regression and resolve it together
  with the pending 77-image direction/path failures; do not treat the runner
  as passing.
- The optional legacy `pc_vision/test_body_localization.py` is not part of the
  strict host gate and currently passes 1/6: three old WALL localization cases
  and two old SOURCE outline/broken-border expectations fail. The SOURCE
  outline state was already false before this task's center-only change, and
  WALL acceptance code was untouched. Keep this as a separate test-maintenance
  task rather than expanding the completed parity/runner work.
- Protect the current uncommitted `pc_vision/`, `vision_ps_baremetal/`, test, and
  hardware changes. Do not delete cleanup audit classes B/D without review.
- Preserve the Bayer packaged-IP checksum/catalog/target-refresh sequence in
  `tools/build_bitstream.tcl`; otherwise Vivado can synthesize a stale generated
  `ipshared` copy instead of the canonical VHDL.
- Classify the remaining global MIPI/debug timing constraints separately from
  the already-verified RGB2DVI paths.
- Decide separately whether to flatten the existing outer-directory/nested-Git
  layout. Do not move or copy the Vivado project as part of an unrelated task.
- Linux/PYNQ hardware validation awaits explicit authorization. Follow PYNQ
  Migration Status: prepare stock bootpy suppression, verify boot/native C/
  mouse/CMA first, and reconcile BIT/HWH/FCLK ownership before custom PL loading.
  Do not install/upgrade packages or reopen the paused hardware path automatically.
- Live-board acceptance remains open for the new pure-green detector: confirm
  OV5640 exposure/color stability, HDMI bbox/center/label visibility, UART
  throttling and coordinates, false positives, processing time, and sustained
  frame behavior before treating the offline thresholds as field-qualified.
- Portal ray-game hardware acceptance remains deliberately unperformed. On a
  later authorized board task, verify SOURCE direction at distance/lighting
  extremes, real HDMI line alignment, mirror/Portal geometry, false marker
  pairs, processing time, state-transition UART logs, SOURCE dropout retention,
  TARGET-confirmed ray retention, SOURCE-move clearing, and a live
  `vision_active_zero_ray_frames == 0`.
  The white band is the required physical SOURCE marker. The current 30-image
  run has no wrong direction among 20 accepted frames and safely rejects 10
  ambiguous frames, so broader distance/lighting coverage remains useful.
- The strict ARM ELF and `sd_boot/vision/BOOT.bin` now represent the current
  direct source tree and Portal endpoint-component correction. Bootgen header
  readback and exact application PT_LOAD comparison pass; FSBL and BIT hashes
  remain unchanged, and the linked ELF contains no legacy stabilizer entry
  point. SD copying, JTAG, SD boot, and hardware acceptance remain deliberately
  unperformed.
- Deferred higher-level work remains: full-resolution local ROI refinement,
  board-plane homography, common-ray prefix comparison/suffix-only updates, and
  high-rate ROI scans near the displayed ray. The current whole-ray atomic swap
  is intentional. Offline Portal direction results do not justify adding a new
  physical marker now; reconsider only if later authorized live tests show
  solid/ring ambiguity under real rotation or lighting.

## Next Bare-Metal SD Confirmation

No board operation was performed by Codex for the pure-green integration. The
user reports that the current result succeeded. The next useful human record is
a saved HDMI image plus one throttled UART TARGET line from the successful SD
cold boot, followed by a gray-background and rectangle rejection check. Do not
reuse the former `CALIBRATION_REQUIRED` UART expectation for this image.

## Legacy Bare-Metal Hardware Verification

The board has now enumerated as `arm_dap`, `xc7z020`, debug hub, APU, and both
Cortex-A9 cores. The canonical `color_test/tools/program_camera_jtag.tcl`
successfully downloaded the matched standard BIT/ELF before the debug flow.
The staged and first-frame modes of
`color_test/software/vision_ps_baremetal/tools/program_hdmi_output_debug_jtag.tcl`
(default `stages`, or argument `first-frame` for one final breakpoint). Preserve
console output externally with the visible HDMI result and startup condition.
The script resets/programs/initializes PS; it is a controlled JTAG startup,
not evidence of an untouched SD cold boot. Plan genuine cold-boot attachment
separately if controlled JTAG startup cannot reproduce the symptom.

Stages: main -> first CameraStart call pending -> CameraStart entry -> GPIO
reset delays done / I2C init pending -> sensor configuration pending ->
CameraCheck entry -> validated frame processing -> first display commit.
Configuration-pending is before sensor_configure; CameraCheck entry proves the
preceding configuration/start path returned successfully, not that video flows.
Each stage waits up to 60 seconds for its own breakpoint; timeout is an
unconfirmed stage, collects two snapshots 500 ms apart with CPU halted, and
ends the flow. Successful final commit also leaves CPU stopped.

Snapshots record PC/LR/SP/CPSR/backtrace, UART1 CR/SR, CSI control/status,
long-packet/CRC counters, capture S2MM CR/SR/park, display MM2S CR/SR, and
ELF-resolved presented-frame count. Use stage progression and counter changes
to select one next debugging branch. For UART stalls, use backtrace plus LR;
LR alone may point inside xil_printf/outbyte rather than the originating print.
Repeat with first-frame mode to assess intermediate-breakpoint perturbation.

## Debug Infrastructure Verification and Limits

- Windows Vivado/Vitis/XSCT 2023.1 is installed under `D:/Xilinx`. Two
  debug-bitstream build attempts stopped at the same `implement_debug_core`
  OOC-launch boundary: all three runs had empty `.vivado.begin.rst` files, no
  `runme.log`/`.vds`/end/error status, stationary CPU, and no advancing file
  timestamps. Both per-run `.Xil` session directories were removed after their
  processes were stopped; `impl_1` and its DCPs were preserved.
- Vivado 2023.1's generated `ISEWrap.js` queries `Win32_Processor` and
  `Win32_ComputerSystem` before establishing OOC run status. Both queries return
  access denied inside the Codex sandbox and succeed outside it. The one
  authorized build outside the sandbox created non-empty OOC begin records,
  active `runme.log`/`.vds` files, completed all three debug-IP syntheses, and
  finished place/route/bitstream generation. This confirms sandbox/WMI access as
  the cause of the first two OOC launch hangs.
- After the cable was reconnected, `hw_server`/XSCT enumerated `arm_dap`,
  `xc7z020`, debug hub, APU, and both Cortex-A9 cores. The canonical JTAG script
  then completed standard BIT/ELF programming. The debug script subsequently
  programmed the fresh debug bitstream and vision ELF and obtained the staged
  and first-frame evidence recorded above.
- Debug-script preflight rejects missing/ambiguous ELF stage calls before
  connecting; uncertain stop formats fail closed instead of claiming a hit.
- No UART guard has been implemented; no black-screen root cause is claimed.
