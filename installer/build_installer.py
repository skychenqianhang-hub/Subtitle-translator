"""一键出安装包：PyInstaller 打包 → 自检 → Inno Setup 编译。

用法（项目根目录）：python installer/build_installer.py [--skip-pyinstaller]
产物：installer/output/SubTranslator-Setup-<版本>.exe
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.version import __version__  # noqa: E402

ISCC_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def main() -> int:
    os.chdir(ROOT)
    if "--skip-pyinstaller" not in sys.argv:
        print("1/3 PyInstaller 打包……")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "SubTranslator.spec"], check=True)
    exe = ROOT / "dist" / "SubTranslator" / "SubTranslator.exe"
    if not exe.exists():
        print("找不到", exe)
        return 1
    print("2/3 自检……")
    report = ROOT / "dist" / "selfcheck.txt"
    r = subprocess.run([str(exe), "--check", str(report)])
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    if r.returncode != 0 or not text.strip().endswith("全部通过"):
        print(text)
        print("自检没通过，不出安装包。")
        return 1
    iscc = next((p for p in ISCC_CANDIDATES if p.exists()), None)
    if iscc is None:
        print("没找到 Inno Setup（ISCC.exe）。先 winget install JRSoftware.InnoSetup")
        return 1
    print(f"3/3 Inno Setup 编译 {__version__}……")
    subprocess.run([str(iscc), f"/DAppVersion={__version__}", str(ROOT / "installer" / "SubTranslator.iss")], check=True)
    out = ROOT / "installer" / "output" / f"SubTranslator-Setup-{__version__}.exe"
    print("完成：", out, f"{out.stat().st_size / 1e6:.0f} MB" if out.exists() else "（文件不存在？）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
