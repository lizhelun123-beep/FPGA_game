# AX7Z020B Linux 单帧采集诊断

本目录是现有 MIPI 链的 Linux/PYNQ 诊断适配层。单帧入口独立于 HDMI 和
`pc_vision` 检测器，保留 **1280×720、两 lane、RAW10** 传感器配置；DDR
仍为 BGR888，有效行 3840 字节、stride 5760、每帧 4147200 字节、三采集
缓冲合计 12441600 字节。PNG 是现有 PL 图像处理后的 BGR 图像，不是 RAW10
原始数据转储。没有改动采样电路、传感器寄存器表或 C 检测器。

## 当前可交付范围

2026-10-20 离线显示对应检查已加入现有制品入口；当前任务不上板。
选定 XSA 的 BIT/HWH、历史 ZIP 和加载回执字节身份一致，但历史 boot 与最近
观测 boot 不同，**当前加载的 PL 仍为 UNKNOWN**。HWH 确认显示 MM2S 经 HP0、
24-bit 视频流、DRE 开启、三个帧槽；VTC 默认仍为1280×720，不能当成800行模式。
这些事实不核准 Linux 资源独占、实际时钟、DMA 缓存同步或停机释放。

```sh
# 纯离线：输出路径必须不存在；不提取工程、不导入 PYNQ、不访问设备。
python -B -m pynq_vision.prepare_overlay --xsa color_test/color_test.xsa --display-report output/build/game_app/display_binding_20261020/my_display_check.json
```

报告始终保留 `qualified_for_loading=false`、`qualified_for_display=false`；
完整证据见 `output/build/game_app/display_binding_20261020/REVIEW.md`。
现有打包模式 `--output` 不变，不能与 `--display-report` 同用。

2026-10-19 最新内存诊断：用户授权连接并执行所给 PYNQ 脚本，实际版本 **2.6.2**，
allocate 位于 `/home/xilinx/pynq/buffer.py`。该次观测 boot 为
`605cc209-5bd5-4f67-ad32-225a4d740255`；实际启动 FIT、运行内核 GNU Build-ID/
配置和 xlnk 函数地址已对应，实际二进制身份不再缺失。
单个 4 KiB cacheable Xlnk 缓冲的 CPU 写入、两次同步调用及正常释放通过，strace
记录 alloc/sync/free/shutdown ioctl 返回0。**这不是 DMA 一致性或安全后端验收。**
原生显示及 capture CLI 的拒绝门槛不变。完整日志、哈希、已确认的内核安全缺口见
`output/build/game_app/pynq_memory_20261019_REVIEW.md` 和同前缀 manifest。
以下传感器、PL 和时钟记录属于其标明的历史 boot，未在本轮重新检查或操作。

已完成旧版诊断 PL 的受控加载/时钟复位读回，并观察到 OV5640 身份和一次短时
CSI 接收；**完整探针在捕获 VDMA 错误门槛失败**，尚无完整帧或稳定采集验收。
本包不是包含最新采样/CDC 修复的生产 PL，不能证明 FPGA 输入时序闭合。

2026-10-19 传感器检查 boot=`afc17ac5-09cb-4f14-bc0a-1da555c9146a`，当时保持原 BIT 加载。
Linux GPIO960 对应 PS GPIO54/EMIO0，复位低/高各1s；I²C0/e0004000 经已加载
PL 的 EMIO 路由，在地址0x3c 读到 ID `56 40`。复用本目录原有 OV5640 表，
两 lane、1280×720 RAW10 及关键 PLL/格式字段读回通过。一次短时出流后读取
978个长包，CRC=0，各采样点溢出标志未置位；传感器随后待机 `3008=0x42`。
这不等于收到完整帧、证明逐 lane bit/byte 身份或稳定无错误。

捕获 VDMA 的 CR 始终为0x10002（RS=0），但 SR 从0x10001 变为 **0x14811**：
VDMAIntErr、SOFLateErr 和错误中断位，HALTED=1。只读补查确认 VSIZE、HSIZE、
stride 和缓冲地址全为0；与未配置的下游收到视频边界相符，属有依据的推断。
未启用 DMA 不保证状态完全不变。保留原始失败结果，不清错/复位、不重跑出流；
本方案完整检查失败1次，先前串口和采样失败账本均未清零。

该 boot 结束时保留：GPIO960 为本任务导出的 output high，传感器待机，CSI 控制2/包数978/
CRC0，捕获 S2MM 错误原样保留，显示 VDMA 仍停止。I²C 描述符及 COM9 已关闭。
后续安全 DMA 任务也没有分配 CMA、启动 DMA/HDMI、重载 PL、改 PS 时钟或服务。
单帧用户态防护已补上，主机22项及板上 Python3.6 CPU/Fake19项检查通过；
**真实分配器门槛未通过，有效硬件布局、恢复及完整帧尚未执行。**

板上 zocl.ko SHA256 为 `a923c535d807917b733611bc26f440fb07a0aec757954bc5436086e809584bee`，
文件 Build-ID 与已加载模块一致。其 CMA 释放分支调用释放函数后仍读取原对象的
bank/size；按 Linux5.4 helper 契约存在释放后读取风险，未执行分配/释放或诱发崩溃。
在线已找到官方 XRT `202010.2.6.655`/提交 `2d6bfe4ce91051d4e5b499d38fc493586dd4859a`
及对应构建配方，其释放顺序与反汇编一致；已保存仅调整统计/释放顺序的最小补丁
`output/build/game_app/camera_dma_20261019_zocl_release.patch`，未编译或装载。
后续已授权的驱动构建任务使用官方69个依赖文件和该补丁，在板上私有目录构建。
**原生构建环境两轮均失败，2/2 已耗尽，未生成修正版 .ko。** 首轮缺少生成的 ARM
`asm/bitsperlong.h`；唯一环境重试在准备标准 Kbuild 工具时遇到
`The configuration requires explicit update.`，未允许静默改配置，未再编译模块。
运行内核用 GCC9.2，板上是 GCC7.3；auto.conf.cmd 还绑定原 Yocto 编译器、链接器、
源码和宿主工具路径，所以仅换一个 GCC9.2 不能算已解决。未卸载/装载模块、分配
DMA、配置有效硬件布局或采集完整帧。最终读回确认原驱动、运行配置和系统构建输入
哈希不变；私有失败目录 `/tmp/codex_camera_dma_driver_3vb6s8kj` 及两轮证据均保留。
当前离线构建包已在两个 Linux 前缀核准，详见下节；原生2/2 不变。唯一下一步是
使用核准的离线交叉 SDK 对修正版 zocl 做一次固定构建及完整静态 ABI/释放路径审查。
本轮没有连接板卡或构建完整驱动；分配器门槛继续关闭。

安装版 PYNQ 默认50MHz参考与当前33.333333MHz不符；PYNQ 登记仍为空，内核
FCLK1/2 树仍是缓存41.67MHz/count0，实际分频推算约142.857141/199.999998MHz。
规范源码的 capture CLI 现在在 PL/设备操作前明确拒绝未核准 DMA 后端；未提供
强制绕过。原 overlay ZIP 中的旧入口未更新，仍会重载/重设时钟并进入未核准
CMA 路径，**不要直接运行旧包**。
持久时钟管理、DMA/cache/生命周期、采样结构闭合及生产顶层仍各有门槛。

最新离线证据：`output/build/kernel_sdk_20261019/REVIEW.md`/`manifest.json`。
此前板端构建证据：`output/build/game_app/camera_dma_driver_20261019_manifest.json`；用户态/
源码审查仍为 `output/build/game_app/camera_dma_20261019_manifest.json`；原传感器证据
仍为 `output/build/game_app/camera_sensor_csi_20261019_manifest.json`，详见
PROJECT_STATE 的 Authorized Runtime Evidence。此前板上回执在
`/tmp/codex_camera_sensor_csi_vdu0omxv/sensor_csi_receipt.json`；保留上轮环境
回执、固件和全部历史失败。下一阶段请保持板卡供电及稳定 UART、摄像头连接。

已有 COM9 只读记录确认板卡运行 PynqLinux 2.6 / Python 3.6 / Linux
5.4.0-xilinx-v2020.1。通用 `boot.py` 的 BaseOverlay 导入失败不等于本工程
摄像头故障。保留当前 Linux 启动卡，不覆盖 BOOT、不修 bootpy、不切换裸机
启动包。原始镜像启动分区实际为 FAT16（MBR 类型字节为 0x0c）；板上启动
文件的字节身份已核准，本次加载来源和已知 IP 读回已核准。

## 最小 xlnk 内存诊断（显式授权后运行）

`check_memory.py` 是诊断入口，导入本模块不会导入 PYNQ。运行要求 root、已观察到的
当前 boot ID、已审阅的 buffer.py/xlnk.py/libcma 哈希，固定只测一个4096字节缓冲。
显式 target 使用实际 Xlnk 实现，不枚举 XRT、不创建 PL-server，不启动 DMA。
它在分配前将当前进程的 SIGSEGV 处理恢复默认，避免实际安装版 PYNQ 的全局 reset
处理器；不修改系统配置。不能把这个诊断当成生产分配器或自动恢复工具。

```sh
# 每轮必须另有用户明确板端/内存操作授权，并填入已观察到的当前 boot ID。
sudo -n strace -f -qq -y -e trace=ioctl python3 -u pynq_vision/check_memory.py --run --expect-boot ACTUAL_BOOT_ID
```

真实 `sync_to_device`/`sync_from_device` 返回 None；必须把外部 ioctl 状态另行保存，
不能据此包装成成功。该版 `close()` 不释放；本次 `freebuffer()` 后计数仍1，删除
所有数组引用并 GC 后计数0且实际发送 free。缓冲如曾交设备，任何释放之前仍须
证明设备停止访问；本测试从未向 DMA 提交地址。没有验证失败回滚/跨进程/异常死亡。
同正常测试的成功不消除已确认的实际内核 rollback、owner、完整范围和退出缺口。
按用户最新决定，xlnk 暂记部分完成、非当前阻塞项；暂不继续内核排查或重复小分配。
相关同步/释放缺口留在后续真实 DMA 生命周期验收中，不因离线显示核对而消失。

## 当前内核的离线外部模块 SDK

制品：`output/build/kernel_sdk_20261019/external-module-sdk.tar`，497520640 字节，
SHA256 `ab321525f9669b1894cbd30280c5e2289fb42ab614a69ed505c9c011f33d63df`。
内部 `SDK_README.md`、`install.py` 和锁定哈希给出离线部署与迁移流程；包内含
官方 Yocto3.0.4 GCC9.2.0、原镜像构建输入、完整 ARM 生成头及静态 Kbuild 工具。
核准范围为 x86-64 Linux → 当前 ARM32 内核外部模块；已测 Ubuntu26.04.1/WSL2
两个 ext4 前缀，要求 Python3.12+、glibc>=2.38 和包内列出的宿主工具。
消费包不需要安装主机 GCC/apt/pip，也不访问板卡。不能在板端 ARM 原生消费。

在 Linux 解开外层 tar，先在其中运行 `python3 install.py --verify-only`，再运行
`python3 install.py /absolute/new/private/prefix`。成功后外部模块入口为该前缀下
`build-module /absolute/module/source`；本任务只构建了不可装载的取证模块。
迁移时从包重新安装到新前缀，不直接复制已安装 SDK；官方流程会迁移 ELF 解释器、
加载器、脚本和符号链接。保留全部失败目录，不自动重试。不要执行顶层 prepare、
modules_prepare、oldconfig 或 syncconfig；这些入口没有获得核准。

核准结果：原驱动154个导入 CRC 匹配；两前缀最小模块的3个导入 CRC、module_layout
及导出 CRC 一致，四个 zocl BO 布局值符合原模块反汇编。原11614个文件内容不变，
auto.conf.cmd 原路径保护完整保留，标准外部 M= 构建不包含该保护文件。
首轮缺少 ARM syscall 头而失败，唯一修正重试按原表/规则生成后通过；首次失败制品
和日志均保留。此前板端原生构建2/2 及所有采样失败不清零。这些结果不代替完整
修正版驱动的 ABI/运行验收，更不代替有效 VDMA 布局、完整帧或采样结构闭合。

## 统一交付物与时钟

唯一选定来源是 `color_test/color_test.xsa`，Vivado 2023.1，生成时间
2026-10-04。包装器只解包已有文件，不运行 Vivado、不生成 BIT/XSA。

| 制品 | SHA256（完整值见 manifest.json） |
| --- | --- |
| 源 XSA | `03ae58ac84833591…` |
| XSA 内 `color_test.bit` → `system_wrapper.bit` | `a5a88800af559c2e…` |
| XSA 内 `system.hwh` → `system_wrapper.hwh` | `dc899d44a94c1c98…` |

标准目录 `color_test/build/hw/system_wrapper.bit` 和旧
`output/pynq_overlay/system_wrapper.bit/.hwh` 属于不同制品，均保留原样，不能
混入本包。仅同名或路径相同不足以通过检查。

| PS 时钟 | HWH 请求值 MHz | HWH 实际值与运行时目标 MHz |
| --- | ---: | ---: |
| FCLK0 | 100 | 100 |
| FCLK1 | 150 | 142.857132 |
| FCLK2 | 200 | 200 |

HWH 的 `PCW_ACT_FPGA*` 与 PS 输出端口频率须相符。CSI 视频、Bayer、Gamma、
采集 DMA 均连接 FCLK1；D-PHY RefClk 连接 FCLK2，采集不依赖 HDMI 动态时钟。
HWH 中 RxByteClkHS 的静态属性不是摄像头当前输出频率测量。

本包的纯文件预检先核对 XSA/BIT/HWH 哈希、地址、manifest 和上述时钟元数据，
失败时不会导入 PYNQ 或下载 PL。未来执行采集时，先下载 PL，再按实际目标设置
FCLK 并读回检查；任一路偏差超过 0.1 MHz、非有限值或异常都会在采集 MMIO、
CMA、GPIO、I²C、摄像头和 DMA 启动前停止。PYNQ 读回值由 PS PLL/分频寄存器
计算，不是示波器测量，不是 MIPI 约 280 MHz HS 时钟、占空比或相对抖动保证。
运行时失败前已发生的 PL 下载/时钟写入不会自动回滚。

PYNQ 先以 `download=False` 解析 HWH；解析器抛异常时才采用已严格核对的
`Bitstream + 显式 MMIO` 路径。解析成功后的地址不符会直接失败，不能借回退
绕过检查。旧解析器兼容回退仍需板端验证。

## PC 离线打包与检查

在仓库根目录执行，输出路径必须不存在，旧目录不会被覆盖：

```powershell
python -m pynq_vision.prepare_overlay `
  --xsa color_test/color_test.xsa `
  --output output/pynq_overlay/linux_capture_03ae58ac `
  --archive output/pynq_overlay/linux_capture_03ae58ac.zip

python -m pynq_vision.app `
  --overlay output/pynq_overlay/linux_capture_03ae58ac/system_wrapper.bit `
  inspect-overlay
```

ZIP 内有一个 `linux_capture_03ae58ac/` 目录，包含完整 XSA、匹配 BIT/HWH、
manifest、诊断模块、本说明和 `SHA256SUMS`。不包含游戏/检测器副本，也不改
SD 启动分区。单帧所需板端依赖为已有 PYNQ、NumPy、OpenCV；无需 dataclasses
或 PC 检测器，不运行依赖升级/安装。

将来经授权转移并解压后，在该目录先做文件检查（以下两条不下载 PL）：

```bash
sha256sum -c SHA256SUMS
python3 -m pynq_vision.app --overlay system_wrapper.bit inspect-overlay
```

## 后续唯一实测入口

**当前入口已关闭，下面命令不可用于绕过分配器门槛。** 当前环境已核准 I²C0/
e0004000、地址0x3c。仍须实现并核准 DMA 后端、当前 PL/时钟复用和安全退出，
然后在该任务板端授权内接通单帧编排；本轮未执行下面的旧接口示例：

```bash
python3 -m pynq_vision.app --overlay system_wrapper.bit \
  capture --i2c-device /dev/i2c-0 --output capture01
```

门槛后的旧编排仍会下载整个选定 PL、写/校验 FCLK、映射采集 VDMA/CSI/Gamma、分配三帧
CMA，保持 Gamma 原选择值 3，复位并配置/启动 OV5640、锁定曝光增益，检查
CSI 长包/CRC/溢出和 VDMA 布局，跳过行 padding，保存一帧无损 PNG。
**不映射或初始化 HDMI dynclk、VTC、显示 VDMA，不分配显示缓冲，不画彩条，
退出时不复位显示 DMA。** 该编排尚未接入安全单帧/当前时钟复用，不能视作已完成。
底层新 one-shot 只在模型中验证：固定 slot0、完整帧后硬件停止，确认 HALTED/RS0
后才同步/复制；停止未确认时保留缓冲，释放须返回明确成功状态。全芯片 BIT 仍
包含原有显示逻辑，本次未生成裁剪 BIT。

结果在新目录中：`frame.png` 和 `capture.json`。后者记录制品身份、时钟前值/
读回值、图像尺寸、非零像素及 CSI/耗时；运行中异常记录 `FAIL`、阶段和错误，
并以非零状态退出。文件预检失败时不创建输出目录。`PASS` 只表示该次单帧软件
检查通过，不表示颜色/几何、链路长期误码、引脚时序或生产基线已验收。

旧 `run` 入口仍需完整仓库的 `pc_vision`，并显式启用原有 720p HDMI 诊断路径；
显示支线当前暂停，本包不将其作为下一步。最终游戏的原生 C/C++、1280×800
纯虚拟画面与分阶段 PL 路线保持不变。

## 离线验证

```powershell
python -m unittest discover -s pynq_vision/tests -v
```

覆盖实际 XSA 解包/哈希/时钟元数据、篡改拒绝、地址检查失败不得回退下载、
时钟异常在采集资源操作前停止、无 HDMI 的完整模拟生命周期、单帧成功/失败
记录，以及原有 RAW10/VDMA/stride 检查。实际 XSA 不在工作区时，制品集成
用例会明确跳过。这里的 mock 检查不是 RTL 仿真、实现或板端采集。
