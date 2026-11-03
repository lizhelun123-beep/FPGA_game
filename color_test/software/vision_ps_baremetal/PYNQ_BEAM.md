# version14 板端 C 核心的 Linux/PYNQ 迁移入口

## 当前阶段：PYNQ 仿真门槛与运行策略

`pynq_vision/beam_hardware.py` 实现 PYNQ 所有者，`beam_launcher.py` 提供常驻/有界运行入口；Notebook 与命令行使用同一个 `Session`。当前 PYNQ 制品使用主机仿真通过作为板卡交付门槛，真实设备仍由用户按设备流程运行。

- 硬件输入：`output/build/game_app/pynq_beam_hardware_5/` 的匹配 `.bit/.hwh`、`libbeam_pynq.so` 与派生 `hardware.json`。不含新 BOOT 或完整系统镜像。
- ARM 编译候选：`output/build/game_app/pynq_beam_c_5/`；仿真执行 `pynq_vision.tests.test_beam_runtime`，记录 `PASS_PYNQ_SIMULATION_GATE` 和 `PASS_BY_SIMULATION`。
- Notebook：`pynq_vision/notebooks/beam_v14_pynq.ipynb`。检查单元只读文件，实际运行单元需要当前板端准入，支持有界采样和相同入口的持续游戏运行。
- 运行候选包：`output/build/game_app/pynq_beam_runtime_11/pynq_beam_runtime.zip`；解压后保持目录结构。包内只含板端运行依赖，不包含电脑工程、系统库或 BOOT。包的 `verification.json` 使用 `PASS_BY_SIMULATION` 门槛。

### PYNQ 新增运行策略

- 画面提交或退休的瞬时显示错误只重试同一完整画面，保留 ticket、帧缓冲和当前退休栅栏；采集、C 组帧和串口不会因显示错误退出。
- Portal A/B 继续使用 restored 径向环识别：严格实心环置信度100，径向三扇区以上候选置信度96；PYNQ 层对低于96、重复身份或无效轴的候选置为受限，由 GameBeam 保留上一份完整画面。
- PYNQ 场景年龄门槛为600ms，600ms接受、601ms拒绝；代次、序号、原始 captured_ms 和单调时钟检查不变。该门槛只用于 PYNQ 构建，不修改裸板和电脑配置。

### 串口交互契约

板端串口仍由现有 C v3 实现处理。Python 只负责把 UART 字节交给 `beam_pynq_receive`，不导入电脑网页的 `pc_vision`、`aiohttp` 或网页状态机。LEVEL/START/RESET/SYNC 的关卡、generation、nonce 和 READY/STARTED 确认继续由 C 控制状态机校验；`beam_pynq_frame` 把采集端的 generation、sequence、captured_ms 原值传入 C，不能用处理完成时间替换。READY 仍要求完整帧提交并由同一显示所有者确认退休，不能由 Python 单独生成。
- 电脑网页、串口后台、C 游戏会话、v3 协议、唯一 JSON、现用裸板 BOOT/BIT 均不改变。游戏不依赖板卡联网；Jupyter 是开发和实验入口。

### 硬件实现

Python 使用 PYNQ Overlay/MMIO/GPIO 管理匹配的 v14 PL 与相机。进程内时钟参考从 HWH 取 33.333333MHz，解决旧 PYNQ 默认 50MHz 的差异，不修改安装目录或全局配置。设备对象仅使用 PYNQ 的 MMIO/FPGA-manager 路径，不构造 Xlnk/libcma 分配器、不探测 XRT、不执行全局 CMA reset。

两份三槽帧缓冲由 Python 的 `beam_memory.XlnkBuffer` 管理：复用现有检查型 C owner 的 88 字节 xlnk ABI和非缓存映射，逐次检查 ioctl；未知分配/释放结果保留进程，不重试全局 ID、不加载 libcma。CPU 写/读以 ARM barrier 排序；只有实际 RS=0/HALTED 后才能释放。它是独立接线的受限后端，旧 `hardware._require_qualified_dma_backend()` 入口不变，不调用/绕过旧 CameraPipeline。

CSI 仅使用 1.1 的四个真实 CSR，不访问 1.2/1.3 的快照寄存器。采集按原 version14 顺序：循环启动并确认三个新 START → 初始 PARK 双 START → 每次旧槽退休后复制独立 CPU 图像；复制前后都核对完整布局、writer 和状态。相机表由原 `ov5640.c` 的 63 项初始化、38 项 720p 配置及19项读回条件生成，包括 C 整数表达式，未启用旧 Python 检测器或另设阈值。

HDMI 参数由 Python 平台回调配置，完整帧提交、两次新 START 退休和 HALTED 停机仍由同一个 C 显示状态机执行。Python 回调异常返回错误，不能被 ctypes 当作隐式成功。采集、C 组帧、显示退休耗时只保留最近最多256个真实样本；首错在停机前保留原样，不扩大故障后的寄存器扫描。

### 文件检查与实际运行入口

以下命令仅核对文件哈希，不导入 PYNQ、不加载 ARM 库、不接触设备：

```text
python -B -m pynq_vision.beam_launcher --manifest output/build/game_app/pynq_beam_hardware_5/hardware.json --overlay output/build/game_app/pynq_beam_hardware_5/system_wrapper.bit --library output/build/game_app/pynq_beam_hardware_5/libbeam_pynq.so --inspect
```

Linux/PYNQ 下的实际运行示例（本轮没有执行）：

```sh
# UART_DEVICE/I2C_DEVICE 必须先填写为本轮已确认的实际设备。
sudo -n python3 -m pynq_vision.beam_launcher \
  --manifest output/build/game_app/pynq_beam_hardware_5/hardware.json \
  --overlay output/build/game_app/pynq_beam_hardware_5/system_wrapper.bit \
  --library output/build/game_app/pynq_beam_hardware_5/libbeam_pynq.so \
  --uart "$UART_DEVICE" --i2c-device "$I2C_DEVICE" --run
```

默认持续运行；`--frames 10` 用于有界硬件实验。SIGINT/SIGTERM/Notebook 中断都进入同一安全停机流程；未确认停机时不会结束所有者。程序在打开前检查 `/proc/consoles`、业务 UART 的现有 FD，以及命令行仍指向该设备的 `agetty/getty/serial-getty` 进程；打开后再用 `O_NOCTTY`、`flock(LOCK_EX|LOCK_NB)` 和 `TIOCEXCL` 锁住设备。内核日志、登录程序或另一个业务进程无法混入 v3 字节流。程序不会停止 getty、改启动参数、禁用服务或写 SD；管理员必须在程序外完成 UART 的控制台/getty 迁移，并在本轮重新检查设备。

### 当前 boot 准入（不提供伪造回执）

实际运行要求 `/run/beam_pynq/admission.json`，以及它绑定的 root 保护证据文件，二者必须由另行获授权的当前板端准入过程产生。本轮没有板卡访问，因此交付包不包含任何 PASS 回执或历史 boot UUID 占位文件。

回执字段：schema=`beam-pynq-mmio-admission-v1`、当前 boot_id、匹配 bit_sha256/hwh_sha256、ps_reference_hz、evidence_path/evidence_sha256。证据文件 schema=`beam-pynq-quiesced-v1`，同一 boot/制品身份，以及 `dma.capture`/`dma.display` 的实际 control/status 数值；必须为 RS0/HALTED1/无错误。二者均检查 root 所有者、普通文件、不可被组/其他用户写入、单链接及哈希。它们只授予读取已知 PL 地址的依据，不代替随后真实状态检查。

运行时另查实际 kernel Build-ID/config/启动 FIT、固定 PYNQ 源文件身份、实际 I2C 路由、其他设备/CMA 所有者、UART 控制台/占用和硬件锁；加载前后检查实际 CSI ABI、DMA 与时钟。没有 force 参数，不从单个 `qualified=true` 或旧日志推定通过。缺少这些实板依据时，拒绝发生在 PYNQ 导入/设备访问前。

### 本轮验证范围

24 项主机测试通过，其中包含真实主机 C 库调用与模拟寄存器/分配器故障；11 个运行模块和 Notebook 的4个代码单元通过 Python3.6 语法检查。文件检查入口在禁止导入 PYNQ、numpy、OpenCV、aiohttp 和电脑工程的条件下通过。ARM 候选为32位 hard-float 共享库，实际 GLIBC 版本需求最高2.17，未超出目标镜像2.27；50项 C/头文件构建输入与当前源码哈希一致。冻结基线中的313项运行源码/固件输入、原 version14 BOOT 和恢复 ZIP 哈希保持不变。

这些结果只确认软件接线、主机故障模型和 ARM 编译/依赖。PYNQ2.6.2/Python3.6 的实际执行、Overlay 下载、非缓存分配、相机连续采集、HDMI 和真实串口均尚未上板验证；不承诺帧率或完整游戏已通过。运行镜像仍须是匹配 PYNQ/Linux 启动链，不能用旧裸板 BOOT 当作 PYNQ 系统启动包。

```powershell
$env:BEAM_PYNQ_HOST_LIBRARY = (Resolve-Path output/build/game_app/pynq_beam_hw_c_3/beam_pynq_host.dll).Path
$env:BEAM_PYNQ_HARDWARE_DIR = (Resolve-Path output/build/game_app/pynq_beam_hardware_5).Path
python -B -m unittest pynq_vision.tests.test_beam_runtime pynq_vision.tests.test_beam_hardware
```

## 第一阶段记录：C 算法库与入口

本阶段仅迁移板端 C 算法调用和运行入口。电脑串口后台、网页、C 游戏会话、v3 协议、唯一 JSON、原 BOOT/BIT 均保持现状。当前产物不是可直接运行摄像头的完整 PYNQ 交付。

## 已实现

- `src/pynq/beam_pynq.c/.h`：CPU 算法库 ABI，复用原检测器、GameBeam、B 防抖、Portal 规则、v3 编解码、控制状态机和画面保持。检测器使用进程全局工作区，因此只允许一个实例，所有调用串行。
- `src/pynq/beam_pynq_posix.c`：CLOCK_MONOTONIC、显式 UART、115200/8N1、非阻塞读和 100ms 有界整包写。活动内核控制台拒绝打开；打开流程使用 `O_NOCTTY`、`flock` 和 `TIOCEXCL`，关闭时恢复 termios 并释放独占标志。Python 准入还检查尚未打开设备的目标 getty；不停止 getty、不改启动参数或服务。
- `pynq_vision/beam_runtime.py`：只使用 Python 标准库的 3.6 兼容绑定与主循环，不导入电脑 Python、aiohttp、OpenCV 或 PYNQ。PYNQ 硬件所有者由下一阶段绑定，未自动调用旧的 CameraPipeline。
- `tools/build_beam_pynq.py`：从唯一 JSON 的 `real_scene.beam` 生成同一 C 配置，生成主机测试库和 ARM Linux hard-float 共享库。保留 `GAME_BEAM_STANDALONE=1` 的原 720p 检测区编译语义；这不引入 BSP 或裸板设备访问。

正式候选产物为 `output/build/game_app/pynq_beam_c_5/libbeam_pynq.so`；`build.json` 记录工具链、实际库依赖、源文件哈希、仿真门槛和 ELF ABI 检查。

## 硬件边界

库只接收已经安全取得的独立 CPU BGR888 副本，保留原 generation、sequence、captured_ms。它不会加载 Overlay、分配 DMA、猜物理地址或把显示保留当作新观测。检测后使用原始帧标记提交同一 GameBeam；旧画面保留原时间、亮度和光段，新无效 POSE 不携带旧姿态。

每份完整 CPU 画面附带 ticket。硬件显示所有者成功拷贝/提交后调用 `submitted`；只有同一所有者确认实际退休栅栏后才能调用 `retired`，进而产生 READY。ticket 仅核对代次，不能代替硬件完成证据。处理中不应用新的关卡操作。

Python 主循环接口是 `run(owner, beam, uart, stopping)`，owner 必须实现：

| 方法 | 实际契约 |
| --- | --- |
| `prepare()` | 单所有者准备采集/显示，失败后仍可安全 stop；不创建第二套设备所有者 |
| `capture_cpu()` | 在实际完成、cache 同步及排除设备访问后，返回独立 CPU `CapturedFrame`，不能返回 PynqBuffer/设备视图 |
| `check_capture()` | 按原门限核对实际通道，异常抛错 |
| `submit_cpu(canvas,result)` | 复制完整画面到可用显示槽后返回，禁止直接把 CPU canvas 指针当 DMA 地址 |
| `display_retired(ticket)` | 真正满足现有退休条件返回 True，仍等待返回 False；500ms 等待上限保留 |
| `stop()` / `can_exit()` | 确认相关 DMA RS=0/HALTED 后释放；只有所有资源均可退出才返回 True |

退出时先反复完成 owner 安全停机，再关 UART 和 CPU 库。不能确认停机时保留对象和进程；该策略不承诺抵抗 SIGKILL、OOM 或断电。

**尚未绑定真实 PYNQ capture/display owner。** 旧 `pynq_vision.hardware` 的未核准 DMA 后端拒绝入口保持原样。当前命令行仅支持 `--check`，没有可绕过门槛的 `--run` 或 force 参数。下阶段应适配这一个 owner 接口，而非新建检测器、放宽门限或迁移电脑服务。

## 构建与兼容性

板端运行入口目标是 PYNQ 2.6.2 / Python 3.6，ctypes 为标准库。Python 3.6 语法检查通过不等同于板上解释器已实测。

当前 Windows ARM Linux 编译器为 Vitis 2023.1 附带 GCC 12.2。默认链接器会给 `hypotf` 引入 GLIBC 2.35，不能用于历史镜像的 GLIBC 2.27。现使用只读提取的镜像原始 libm/libc 链接，并检查成品实际版本需求为 GLIBC 2.4、2.7、2.17。没有修改数学算法、伪造版本或覆盖镜像库。

库输入工具只读取哈希匹配的镜像，host 可复用已有 dissect 依赖目录：

```powershell
python -B color_test/software/vision_ps_baremetal/tools/prepare_beam_target_libs.py --image 'C:/Users/11967/Downloads/ax7z020b-2.6.0.img/ax7z020b-2.6.0.img' --output output/build/game_app/NEW_TARGET_LIB_DIR --reader-deps output/build/kernel_sdk_20261019/python_deps
python -B color_test/software/vision_ps_baremetal/tools/build_beam_pynq.py --output output/build/game_app/NEW_C_BUILD_DIR --target-libs output/build/game_app/NEW_TARGET_LIB_DIR
```

输出目录必须不存在。提取的 libc/libm/loader 仅作主机链接输入，**不要复制到板卡覆盖系统库**。未在板上实际加载共享库，因此启动、设备、DMA 和实时交互仍未验收。

## 本地主机验证

```powershell
$env:BEAM_PYNQ_HOST_LIBRARY = (Resolve-Path output/build/game_app/pynq_beam_c_5/beam_pynq_host.dll).Path
python -B -m unittest pynq_vision.tests.test_beam_runtime -v
python -B -m pynq_vision.beam_runtime --library output/build/game_app/pynq_beam_c_5/beam_pynq_host.dll --check
```

9 项新测试是合成 CPU 图像/协议夹具，不是实际摄像头或真实 UART；包括原检测器对 y=640 的 Target、B350/351 边界、整幅保留/6s 到期、无效 POSE 不附旧模型、64 位时间与序号、CRC、旧会话拒绝、显示提交/退休门控和退出顺序。原 restored C 回归另行验证 Portal、反射、防抖和显示保持。POSIX 设备代码本轮只经过 ARM 编译，未实际打开 Linux tty。

失败的 `pynq_beam_c_1`（默认库 GLIBC 2.35）和中间 `_2` 保留，不作为最终候选。原版 version14 BOOT、冻结包和网页文件不得由本库替换。
