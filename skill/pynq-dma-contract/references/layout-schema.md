# 静态布局格式

`check_layout.py` 接收一个 UTF-8 JSON 文件，根为 `version=1`、非空 `channels` 数组。每个 channel 包含：唯一 name、正整数 width/height/bytes_per_pixel/stride/span/cache_line，及非空 buffers 数组。cache_line 必须为2的幂。每槽包含非负64位设备 address、owner 和 cpu_access。

支持的 owner：idle、device_read、device_write、cpu_read、cpu_write。cpu_access：none、read、write。device或idle状态必须为none；CPU状态必须与read/write匹配。未知所有权拒绝静态通过。脚本只检查填写的描述能否自洽，不证明状态真实存在或状态转换安全。

所有通道使用同一设备地址空间、相同的“每行 stride 字节、分配整 height 行”线性契约。要求 stride≥width×bytes_per_pixel，span≥stride×height；地址、span 对齐 cache_line；每槽范围不重叠且不溢出64位。SPAN包含行填充；该 schema 不适用于最末行只分配有效字节的特殊紧凑契约、平面/压缩/RAW10非整字节像素、SG描述符、别名共享或不同地址域，遇到这些情况需按真实契约改用专门检查。

CLI 退出0表示 PASS_STATIC_DESCRIPTION，退出1表示输入或静态描述被拒绝，错误详情在标准错误。输出明确列出未证明的 cache API、实际 DMA 完成/退休、运行时所有权和安全停机。

`examples/layout.json` 为合成 BGR24：capture 两槽、display 一槽；两通道布局独立。地址只用于主机算术测试，禁止据此配置寄存器。测试还覆盖步幅过小、span不足、重叠、未对齐、冲突访问、布尔值、重复名字与范围溢出等负例。
