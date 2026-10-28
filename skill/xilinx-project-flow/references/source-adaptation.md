# 外部参考的适配说明

本 skill 参考 [QingquanYao/xilinx-skill](https://github.com/QingquanYao/xilinx-skill) 的阶段路由、版本先决条件、生成脚本前读取参考资料、输出命令/产物/下一步和跨工具交接思路。

当前仓库只吸收这些通用做法，并把入口改为本项目已有的 `color_test/`、`pynq_vision/`、Linux 游戏 owner 和三项按需验证 skill。外部项目的通用器件清单、PetaLinux/HLS 示例、插件安装方式和 `01_hls/02_vivado/03_vitis/04_petalinux` 目录约定不自动套用；它们只有在用户明确提出且本仓库具备对应输入时才适用。

