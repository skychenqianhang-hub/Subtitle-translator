"""字幕翻译器 程序入口。

阶段 0：只显示一个空白窗口，用来验证环境安装成功。
"""
import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from app.tools import find_ffmpeg

APP_NAME = "字幕翻译器"


def build_window() -> QMainWindow:
    window = QMainWindow()
    window.setWindowTitle(APP_NAME)
    window.resize(900, 600)

    ffmpeg = find_ffmpeg()
    ffmpeg_line = f"ffmpeg：已找到（{ffmpeg}）" if ffmpeg else "ffmpeg：未找到，请告诉 Claude Code"
    label = QLabel(
        "环境安装成功。\n\n"
        f"Python：{sys.version.split()[0]}\n"
        f"{ffmpeg_line}\n\n"
        "阶段 0 完成，等待进入阶段 1（软件骨架）。"
    )
    label.setStyleSheet("font-size: 16px; padding: 40px;")
    window.setCentralWidget(label)
    return window


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
