# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成不依赖 Python 环境的独立程序。

输出：dist/SubTranslator/SubTranslator.exe（整个文件夹就是成品，可以复制到任何 Windows 电脑）
ffmpeg（精简版）会被复制到 dist/SubTranslator/_internal/bin/。
"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from app.tools import find_ffmpeg_for_bundle  # noqa: E402

binaries = []
ffmpeg_exe = find_ffmpeg_for_bundle()
if not ffmpeg_exe:
    raise SystemExit("打包前需要先安装 ffmpeg（winget install Gyan.FFmpeg.Essentials）")
print("打包使用的 ffmpeg：", ffmpeg_exe, round(os.path.getsize(ffmpeg_exe) / 1e6), "MB")
binaries.append((ffmpeg_exe, "bin"))     # 只带 ffmpeg，不带 ffprobe（时长等信息用 ffmpeg -i 读）

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
    datas=[("profiles", "profiles"), ("app/core/audio/models/silero_vad.onnx", "app/core/audio/models"),
           ("app/locales/en.json", "app/locales"), ("app/locales/ja.json", "app/locales")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "jupyter"],
    noarchive=False,
)
# ---- 瘦身：去掉界面库里用不到的部件 ----
# opengl32sw：没有显卡驱动时的软件 3D 渲染（我们不用 3D）；Quick / Qml / Pdf：没用到的模块
_DROP = ("opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "qt6quick3d",
         "qt63d", "qt6charts", "qt6datavis", "qt6webengine", "qt6designer", "qt6test")


def _keep(entry) -> bool:
    name = os.path.basename(entry[0]).lower()
    return not any(name.startswith(d) or name == d for d in _DROP)


_before = len(a.binaries)
a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if "qml" not in d[0].lower().replace("\\", "/").split("/")]
print("瘦身：去掉", _before - len(a.binaries), "个用不到的界面库文件")

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
