# 当前工程入口地图

这份地图只记录能改变工具选择的仓库事实；具体参数以源码、BD、XDC、XSA 和当前状态为准。

## 硬件

- 工程：`color_test/color_test.xpr`
- Block Design：`color_test/color_test.srcs/sources_1/bd/system/system.bd`
- 约束：`color_test/color_test.srcs/constrs_1/new/`
- 自定义 IP：`color_test/repo/ip/`
- 生产构建/导出：`color_test/tools/build_bitstream.tcl`、`export_xsa.tcl`
- 只读结构检查：`inspect_color_bd.tcl`、`inspect_bd_pins.tcl`、`list_ipdefs.tcl`、`check_ip_status.tcl`

## 软件和运行时

- 裸机/ARM 源码：`color_test/software/vision_ps_baremetal/`
- Vitis 构建入口：`color_test/tools/build_vitis.tcl`、`color_test/software/vision_ps_baremetal/tools/build_vision_ps.tcl`、`color_test/tools/build_camera_recovery.tcl`
- Linux/PYNQ 适配：`pynq_vision/` 与 `color_test/software/vision_ps_baremetal/src/` 的 `game_*`/`vision_*` 模块
- 板端入口：`program_vision_ps_jtag.tcl`、`run_vision_elf_jtag.tcl`、`program_camera_jtag.tcl`
- 游戏与显示定向工具：`game_display_qualify.py`、`game_linux_autostart.py`、`game_sd_boot.py`、`package_game_autostart.py`
- 电脑上位机：`pc_vision/native.py` 的 NativeGame、`scene_protocol.py`、`godot/`；该路径复用同一 C 游戏规则，普通 GameView 为调试画面。
- 产品与配置：`pc_vision/FINAL_PLAN.md`、唯一手工游戏配置 `pc_vision/game_config.json`；每关逻辑发射器与实体检测清单分开。

## 固定基线

- 器件：`xc7z020clg400-2`；维护版本：Vivado/Vitis 2023.1。
- 采集：两 lane、1280×720、RAW10/BGGR。
- 摄像头、电脑游戏画布与最终 HDMI：1280×720、16:9；相机叠加与 Godot 是同一有效场景的不同呈现，美术预览不等于实时游戏通过。
- 旧制品、旧日志和模拟截图只能作为历史参考，除非当前任务重新建立同源绑定。

