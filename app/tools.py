"""查找外部工具（ffmpeg / ffprobe）。

查找顺序：
1. 打包后的独立程序：exe 旁边 _internal\bin 文件夹（打包时会把 ffmpeg 一起放进去）
2. 系统 PATH
3. winget 的安装目录（winget 装完后，已打开的程序看不到新的 PATH）
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """程序所在目录：打包后是 exe 所在目录，开发时是项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _bundled(exe: str) -> Path | None:
    """打包后 PyInstaller 把附带文件放在 exe 旁边的 _internal 目录（sys._MEIPASS）。"""
    roots = [app_dir()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.insert(0, Path(meipass))
    for root in roots:
        candidate = root / "bin" / exe
        if candidate.is_file():
            return candidate
    return None


def _winget_candidates(exe: str) -> list[Path]:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    root = Path(local) / "Microsoft" / "WinGet"
    found: list[Path] = []
    link = root / "Links" / exe
    if link.exists():
        found.append(link)
    packages = root / "Packages"
    if packages.exists():
        found.extend(packages.glob(f"*FFmpeg*/**/bin/{exe}"))
    return found


def find_tool(name: str) -> str | None:
    """返回 ffmpeg / ffprobe 的完整路径；找不到返回 None。"""
    exe = f"{name}.exe" if os.name == "nt" else name
    bundled = _bundled(exe)
    if bundled:
        return str(bundled)
    on_path = shutil.which(name)
    if on_path:
        return on_path
    for candidate in _winget_candidates(exe):
        if candidate.is_file():
            return str(candidate)
    return None


def find_ffmpeg() -> str | None:
    return find_tool("ffmpeg")


def find_ffprobe() -> str | None:
    return find_tool("ffprobe")


if __name__ == "__main__":
    print("ffmpeg :", find_ffmpeg())
    print("ffprobe:", find_ffprobe())
