# ABI、会话和数据寿命

构建端读取目标 ELF/系统依赖，明确 ARM32/AArch64、hard/soft float、动态加载器、libc/libm 的实际符号版本。相同 CPU 型号不保证 SO 可加载。宿主测试库与目标库来自同一源码/配置，但记录各自环境。

绑定最小要求：

```python
import ctypes as C
lib = C.CDLL(library_path)
lib.process.argtypes = [C.POINTER(C.c_uint8), C.c_size_t]
lib.process.restype = C.c_int
```

签名仅作形式示例，按真实头文件替换。跨语言结构使用固定宽度字段，验证 `sizeof/offset`、对齐与 ABI 版本。禁止默认假设 C `long`、Python int 和指针同宽。C++ 通过稳定 C ABI 导出或按工程选用 CFFI。

传数组裸指针前核对 dtype/字节序、shape、strides、对齐、可访问字节范围及写权限；`nbytes` 不证明视图从起始指针连续。ROI、转置或负步长视图按 C 接口显式传步幅，或在设备交还 CPU 后复制为所需连续布局并保持副本存活。NumPy 绑定可用 `ndpointer` 检查 dtype/ndim/shape/flags，不为普通 ctypes 绑定强加 NumPy 依赖。

Python 持有输入存储、回调及上下文直至 C 确认不再使用；C 返回的内部指针需在下一次修改前复制或保持其所有者存活。回调捕获异常并返回明确错误码，不能让 ctypes 将异常当隐式成功。

同一 Session 封装 open/process/close，供 Jupyter 和 CLI 共用；不让两次 Notebook 执行分别占用 UART、DMA 或非可重入检测器。CPU 图像副本必须在设备不再访问且缓存同步后取得。

回归应覆盖：结构不匹配、短缓冲、错误返回、重复 open、回调失败、退出顺序；CPU 夹具只替代输入和时钟，不篡改业务判定。先停设备和确认缓冲可释放，再关闭 C 上下文；失败时不能先卸载回调所在对象。

依据：[PYNQ Python/C 集成](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/python-c_integration.html)、[NumPy ndpointer](https://numpy.org/doc/stable/reference/routines.ctypeslib.html#numpy.ctypeslib.ndpointer)。PYNQ 文档给出 CFFI 路线；ctypes 签名必须另外对照实际 C 头文件。
