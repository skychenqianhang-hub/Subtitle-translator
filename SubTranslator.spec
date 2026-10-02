# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成不依赖 Python 环境的独立程序。

输出：dist/SubTranslator/SubTranslator.exe（整个文件夹就是成品，可以复制到任何 Windows 电脑）
ffmpeg / ffprobe 会被复制到 dist/SubTranslator/bin/。
"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from app.tools import find_ffmpeg, find_ffprobe  # noqa: E402

binaries = []
for tool in (find_ffmpeg(), find_ffprobe()):
    if not tool:
        raise SystemExit("打包前需要先安装 ffmpeg（找不到 ffmpeg / ffprobe）")
    binaries.append((tool, "bin"))

# conda 环境里 _ctypes.pyd 依赖 Library/bin 下的 ffi.dll，PyInstaller 收集不到，手动带上
import glob
conda_bin = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
for name in ("ffi.dll", "ffi-8.dll", "ffi-7.dll"):
    path = os.path.join(conda_bin, name)
    if os.path.isfile(path):
        binaries.append((path, "."))

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[("profiles", "profiles"), ("app/core/audio/models/silero_vad.onnx", "app/core/audio/models")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "jupyter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubTranslator",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SubTranslator",
)
