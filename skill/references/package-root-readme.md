# PYNQ 与裸板通用技能包

将 `skill/` 放入完整提交目录；单项使用可仅复制相应技能文件夹。使用索引、适用范围和失败边界见 [skill/README.md](skill/README.md)。

- 8 项独立技能，按任务只加载所需入口及相关参考。
- Overlay 元数据、DMA 布局、累计日志工具只依赖 Python 3.8+ 标准库。
- 离线自检：`python -B skill/scripts/verify_package.py skill`。
- `manifest.json` 保存逐文件 SHA256；`verification.txt` 保存该包的离线检查；`context-size.json` 统计入口字符/字节，不能当作实际推理 token。
- [公开案例与参考来源](skill/references/source-patterns.md)说明设计取舍；没有复制第三方 Skill 的整段指令或实现。
- 本包不含原项目地址/版本约束、聊天记录、固件或系统镜像；工程源码、设计报告与协作记录另行提交。
