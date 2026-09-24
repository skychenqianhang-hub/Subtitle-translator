"""字幕翻译器 程序入口。"""
import sys

from PySide6.QtWidgets import QApplication

from app.config import load_config
from app.ui.main_window import APP_NAME, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    cfg = load_config()
    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
