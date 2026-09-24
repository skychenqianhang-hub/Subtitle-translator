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

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[("profiles", "profiles")],
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
