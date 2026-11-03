# 公开案例的设计取舍

查阅日期：2026-11-01。下列链接指向可变的上游内容；本包重新编写指令和工具，只借鉴组织方法，不复制第三方 Skill 或其许可证受限的正文。

| 实际 Skill 案例 | 采用的设计 | 本包的取舍 |
| --- | --- | --- |
| [Anthropic skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) | 入口/参考/脚本分层，任务用例验证 | 8个短入口；不引入评估平台或子智能体依赖 |
| [Anthropic webapp-testing](https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md) | 脚本作为工具调用，先看help而非全文装载 | 复用已有布局/统计工具，新增有界 HWH 提取 |
| [Anthropic mcp-builder](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md) | 专项资料按任务/实现方向选读 | 技术参考直接从入口链接，不强制读全套 |
| [Vercel react-best-practices](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md) | 按问题选规则，细节放独立文件 | 按故障类别路由；不搬入无关React规则或展开全集 |
| [rovinax embedded-architecture](https://github.com/rovinax/embedded-skills/blob/master/skills/embedded-architecture/SKILL.md) | 算法、接口、BSP/平台边界明确 | 用薄平台接口迁移，不强制重排现有仓库目录 |
| [lhbsaa embedded-dev](https://github.com/lhbsaa/embedded-dev-skill/blob/main/SKILL.md) | 面向嵌入式症状选择专项资料 | 不采用自动技能链、强制烧录或过宽的触发描述 |

## 格式与技术依据

- [Agent Skills 规范](https://agentskills.io/specification)：name/description、相对引用与按需披露。每个技能单独安装时不依赖父目录。
- [PYNQ Overlay](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/overlay_tutorial.html)：默认构造可能下载，元数据与驱动绑定按安装版本核对。
- [PYNQ Buffer](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/allocate.html)：设备地址与同步 API；cache 同步不替代设备完成。
- [PYNQ DMA](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/dma.html)：简单模式、长度限制、流末尾 TLAST；不套用到 VDMA。
- [PYNQ Python/C](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/python-c_integration.html)：Python 可调用本地高性能库；另核对 ABI 与寿命。
- [AMD AXI DMA Standalone 示例](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)：驱动、缓存与有界轮询。应用到其他 IP 前重新核对规格。
