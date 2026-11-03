# PYNQ virtual15 展示制品

这个入口是与当前 v14 Standalone、电脑端和现有 BOOT 并行的展示制品。它
从 `pc_vision/game_config.json` 生成十五关 C 表，直接使用同一份
`ray_game.c` 计算固定场景的光路，再使用现有 BGR 素材和 PYNQ/Linux 的
720p MM2S 显示通路。

它明确不启动摄像头、OV5640、CSI、S2MM、检测器、串口或采集 worker。逻辑
发射器来自关卡配置，不伪装成摄像头 SOURCE；物块中心、方向和尺寸来自
配置锚点。模型、光线和背景仍由已有 `game_render` 原子合成，显示缓冲仍由
`game_display_prepare_continuous`、三槽提交、flush/barrier 和 HALTED 退出
契约管理。

## LVGL 界面优化层

教程采用 LVGL 8.3.10、RGB565 和 VDMA/DMA。当前 HDMI 链路是 24 位 BGR、
1280×720 和三槽 MM2S，因此没有直接改动现有显示格式。新增的
`src/virtual15_lvgl_ui.c` 是可选叠加层：LVGL 只负责关卡号、状态和倒计时，
输出先在独立的 RGB565 小行缓冲中绘制，再转换为 BGR888 透明叠加到已有场景；
场景、光线、三槽提交和 DMA 退休逻辑保持原样。默认构建使用无依赖 stub，
所以原 `virtual15_1` 行为不变。

准备 LVGL 8.3.x 源码和工程根目录下的 `lv_conf.h` 后，可生成独立的 LVGL
制品：

```powershell
python color_test/software/vision_ps_baremetal/tools/build_virtual15.py `
  --output output/build/game_app/virtual15_lvgl_1 `
  --lvgl-root D:/third_party/lvgl `
  --lvgl-conf color_test/software/vision_ps_baremetal/tools/lvgl_virtual15/lv_conf.h
```

本仓库已用用户提供的 `C:/Users/11967/Downloads/lvgl-8.3.10/lvgl-8.3.10`
完成同样的 LVGL 编译，成品目录为 `output/build/game_app/virtual15_lvgl_2`。

板端命令在已有参数后追加 `--lvgl-ui`。LVGL 版本必须使用 16-bit 色深，
并将 `LV_MEM_SIZE`、字体和动画按板卡内存预算设置；教程中的 24-bit 直接
配置、整帧 DMA 立即 `lv_disp_flush_ready()` 和自行切 VDMA 帧地址都不适用
当前显示契约。未提供 `--lvgl-root` 时，`--lvgl-ui` 会安全退化为无叠加，
不会替换当前画面或改变硬件路径。

## 离线构建与检查

从仓库根目录执行：

```powershell
python color_test/software/vision_ps_baremetal/tools/build_virtual15.py `
  --output output/build/game_app/virtual15_1
```

输出目录包含：

- `frames/level_01.ppm` 到 `level_15.ppm`：主机用同一 C 求解器和渲染器生成的
  1280×720 预览；
- `game_virtual15.elf`：Cortex-A9 hard-float 静态 ARM ELF；
- `virtual15_bundle.zip`：独立 ELF、`game_assets.bin`、生成配置和运行说明；
- `verification.json`：源、素材、ELF 哈希和未进行板卡操作的证据。

主机检查只读文件和内存，不打开 PYNQ、设备或串口。输出中每关的
`segments`/`success` 是当前配置光路结果；第 4～15 关是否可解仍遵循唯一
JSON 的内容状态，不由展示入口偷偷修改。

## 板端命令（仅在单独授权的 HDMI 验证中使用）

```sh
./game_virtual15.elf --virtual15 --assets /path/ray_game_assets/game_assets.bin --seconds 30
./game_virtual15.elf --virtual15 --assets /path/ray_game_assets/game_assets.bin --level 7 --seconds 30
```

没有 `--level` 时每秒切换下一关；指定 `--level` 时保持该关。启动日志会
打印 `camera=0 csi=0 s2mm=0 detector=0`，并在安全退出后打印
`VIRTUAL15_STOP ... owner_can_exit=1`。这只是展示/显示验证，不包含虚拟物体
拖动、动态特效、与电脑端同步或通关协议。

首次板端验证仍必须使用与当前启动环境匹配的 display qualification、独占
显示 lease、缓存/物理地址和 DMA HALTED 检查；本制品不会替换 v14 BOOT、
修改 SD 或复用正在运行的显示 owner。
