# 纯绿色 Target 识别

这是一个独立的 OpenCV 程序，用颜色和圆形几何识别实拍图中的纯绿色
target。它不要求旧 `pc_vision` TARGET 规范中的白环或黑心，因此也能识别
纯绿色实心圆和绿色圆环。

当前参数由 2026-10-04 提供的 5 张实拍截图确定：OpenCV HSV 使用
`H=34..70, S>=50, V>=50`，再通过面积、近等轴、圆度和最小外接圆填充率
排除背景绿色噪点及长条/矩形物体。阈值集中在 `config.json`，现场光照改变后
只需修改该文件。

## 文件

- `app.py`：图片、视频和 USB 摄像头命令行入口。
- `detector.py`：HSV mask、形态学、连通轮廓和圆形几何判定。
- `config.json`：现场颜色与几何阈值。
- `tests/test_detector.py`：实心圆、圆环、矩形噪声和无目标回归测试。

## 安装

在仓库根目录运行：

```powershell
python -m pip install -r green_target_recognition/requirements.txt
```

## 使用

识别图片并保存标注图和二值 mask：

```powershell
python green_target_recognition/app.py `
  --image "C:\path\frame.png" `
  --output green_target_recognition/output/frame_detected.png `
  --mask-output green_target_recognition/output/frame_mask.png
```

每帧结果以 JSON 输出到终端；找到目标时进程返回 `0`，未找到时返回 `1`，
参数或输入错误返回 `2`。默认不弹窗，加 `--show` 可显示标注图和 mask。

识别视频：

```powershell
python green_target_recognition/app.py --video input.mp4 `
  --output green_target_recognition/output/detected.mp4
```

识别 USB 摄像头（按 Q 或 Esc 退出）：

```powershell
python green_target_recognition/app.py --camera 0 --show
```

输出文件已存在时程序会拒绝覆盖；明确需要覆盖时加 `--overwrite`。

## 验证

```powershell
python -m unittest discover -s green_target_recognition/tests -v
python -m py_compile green_target_recognition/app.py `
  green_target_recognition/detector.py
```

本目录是 PC/PYNQ Linux 可运行的 OpenCV 参考实现，不会直接修改
`color_test/sd_boot/vision/BOOT.bin`。同一组 HSV/圆形判定已经移植到
`color_test/software/vision_ps_baremetal/src/green_target_detector.c`；当前 SD
镜像已经使用该 TARGET-only C 路径。PC 工具用于阈值调试和与裸机 C 结果做
离线对比。
