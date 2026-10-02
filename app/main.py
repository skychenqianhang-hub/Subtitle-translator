"""字幕翻译器 程序入口。

额外用法（给开发自检用）：SubTranslator.exe --check 结果文件路径
  不开界面，检查打包后的程序能不能加载所有组件，把结果写进文件，正常退出码 0。
"""
import sys


def self_check(out_path: str) -> int:
    lines: list[str] = []
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"OK   {name}" + (f"：{detail}" if detail else ""))
        except Exception as e:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL {name}：{type(e).__name__}: {e}")

    def _ctypes():
        import ctypes  # noqa: F401
        return ""

    def _audio():
        import numpy as np
        import soundfile  # noqa: F401
        from app.core.audio.vad import SileroVad, detect_chunks
        vad = SileroVad()
        regions, _ = detect_chunks(np.zeros(16000, dtype=np.float32), vad)
        return f"VAD 模型已加载，静音检测到 {len(regions)} 段"

    def _ffmpeg():
        from app.tools import find_ffmpeg, find_ffprobe
        f, p = find_ffmpeg(), find_ffprobe()
        if not f or not p:
            raise RuntimeError("找不到 ffmpeg / ffprobe")
        return f

    def _sdks():
        import anthropic
        import openai
        return f"openai {openai.__version__}, anthropic {anthropic.__version__}"

    def _ui():
        from PySide6.QtWidgets import QApplication  # noqa: F401
        from app.ui.main_window import MainWindow  # noqa: F401
        return ""

    step("ctypes", _ctypes)
    step("音频与 VAD", _audio)
    step("ffmpeg", _ffmpeg)
    step("云端 SDK", _sdks)
    step("界面模块", _ui)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n" + ("全部通过" if ok else "有失败项") + "\n")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--check":
        return self_check(sys.argv[2])

    from PySide6.QtWidgets import QApplication

    from app.config import load_config
    from app.ui.main_window import APP_NAME, MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    cfg = load_config()
    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
