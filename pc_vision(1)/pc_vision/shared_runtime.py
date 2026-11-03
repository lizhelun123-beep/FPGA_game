"""Load the single repository runtime under a private package name.

The duplicate pc_vision directory supplies only the web front end. Relative
imports in the shared package still resolve to the main source/config/C cache.
"""
from functools import lru_cache
import importlib
import importlib.util
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def repository_root():
    for parent in Path(__file__).resolve().parents:
        if ((parent / "pc_vision/godot_bridge.py").is_file() and
                (parent / "color_test/software/vision_ps_baremetal/src/game_session.c").is_file()):
            return parent
    raise RuntimeError("未找到主工程。请将此网页上位机保留在包含 pc_vision 和 color_test 的 FPGA-main 仓库内。")


def canonical_module(name):
    root = repository_root()
    # 教学编解码/拟合与板端共用纯Python模块；此处只加入已定位的同一仓库。
    if str(root) not in sys.path:
        sys.path.append(str(root))
    package_name = "_fpga_canonical_pc"
    if package_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package_name, root / "pc_vision/__init__.py",
            submodule_search_locations=[str(root / "pc_vision")])
        package = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = package
        spec.loader.exec_module(package)
    elif Path(sys.modules[package_name].__file__).resolve().parent != root / "pc_vision":
        raise RuntimeError("Another repository already owns the shared PC runtime")
    return importlib.import_module(f"{package_name}.{name}")
