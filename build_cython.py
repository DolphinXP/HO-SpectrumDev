"""
Cython 编译脚本 — 将关键模块编译为 .pyd 二进制文件以保护源代码

使用方法:
    C:\\miniconda3\\envs\\specdev\\python.exe build_cython.py

编译后再运行 PyInstaller:
    C:\\miniconda3\\envs\\specdev\\python.exe -m PyInstaller app.spec

要求: Visual Studio Build Tools (含 C++ 工作负载)
"""
import sys
import os
import shutil
import glob
from setuptools import setup, Extension
from Cython.Build import cythonize

# 要保护的核心模块（不含入口 main.py 和 UI 层）
PROTECTED_MODULES = [
    "src/data/acquisition.py",
    "src/data/nuc.py",
    "src/analysis/mtf.py",
    "src/analysis/spectral.py",
    "src/device/daheng_device.py",
]


def make_extension(path: str) -> Extension:
    # src/data/acquisition.py  ->  src.data.acquisition
    module_name = path.replace("/", ".").replace("\\", ".").removesuffix(".py")
    return Extension(name=module_name, sources=[path])


def clean_build_artifacts():
    """删除 Cython 生成的临时 C 文件和 build/ 目录"""
    for module_path in PROTECTED_MODULES:
        c_file = module_path.removesuffix(".py") + ".c"
        if os.path.exists(c_file):
            os.remove(c_file)
            print(f"  已删除: {c_file}")
    if os.path.isdir("build"):
        shutil.rmtree("build")
        print("  已删除: build/")


def main():
    existing = [p for p in PROTECTED_MODULES if os.path.exists(p)]
    missing  = [p for p in PROTECTED_MODULES if not os.path.exists(p)]

    if missing:
        print("警告: 以下模块不存在，跳过:")
        for m in missing:
            print(f"  {m}")

    if not existing:
        print("错误: 没有可编译的模块")
        sys.exit(1)

    print(f"编译 {len(existing)} 个模块...\n")

    # 注入 build_ext --inplace 参数
    sys.argv = [sys.argv[0], "build_ext", "--inplace"]

    setup(
        ext_modules=cythonize(
            [make_extension(p) for p in existing],
            compiler_directives={"language_level": "3"},
            quiet=False,
        )
    )

    print("\n清理临时文件...")
    clean_build_artifacts()

    # 列出生成的 .pyd 文件
    pyd_files = []
    for path in existing:
        pattern = path.removesuffix(".py") + "*.pyd"
        pyd_files.extend(glob.glob(pattern))

    print("\n编译完成！生成的 .pyd 文件:")
    for f in pyd_files:
        print(f"  {f}")

    print("\n下一步: 运行 PyInstaller")
    print("  C:\\miniconda3\\envs\\specdev\\python.exe -m PyInstaller app.spec")


if __name__ == "__main__":
    main()
