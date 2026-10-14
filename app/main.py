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
        import subprocess
        import tempfile
        from pathlib import Path
        from app.core.audio.extract import _NO_WINDOW, has_audio_stream, probe_duration
        from app.tools import find_ffmpeg
        f = find_ffmpeg()
        if not f:
            raise RuntimeError("找不到 ffmpeg")
        # 实际跑一遍：生成 1 秒测试视频 → 读时长和音轨 → 确认有烧字幕和 H.264 编码能力
        with tempfile.TemporaryDirectory() as td:
            v = Path(td) / "t.mp4"
            r = subprocess.run([f, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1",
                                "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264",
                                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)],
                               capture_output=True, creationflags=_NO_WINDOW, timeout=60)
            if r.returncode != 0 or not v.exists():
                raise RuntimeError("ffmpeg 不能编码 H.264：" + r.stderr.decode("utf-8", "ignore")[-200:])
            d = probe_duration(v)
            if not (0.5 < d < 2.0) or not has_audio_stream(v):
                raise RuntimeError(f"读视频信息不对：时长 {d}")
            filters = subprocess.run([f, "-hide_banner", "-filters"], capture_output=True, creationflags=_NO_WINDOW,
                                     timeout=60).stdout.decode("utf-8", "ignore")
            if " ass " not in filters:
                raise RuntimeError("这个 ffmpeg 没有烧字幕（ass）功能")
        size = Path(f).stat().st_size / 1e6
        return f"{f}（{size:.0f}MB，可编码 H.264、可烧字幕、可读时长）"

    def _sdks():
        import anthropic
        import openai
        return f"openai {openai.__version__}, anthropic {anthropic.__version__}"

    def _ui():
        from PySide6.QtWidgets import QApplication  # noqa: F401
        from app.ui.main_window import MainWindow  # noqa: F401
        return ""

    def _languages():
        from app import i18n
        sizes = {lang: len(i18n.load_table(lang)) for lang in ("en", "ja")}
        if min(sizes.values()) < 300:
            raise RuntimeError(f"界面翻译表没有带上：{sizes}")
        return f"英语 {sizes['en']} 条，日语 {sizes['ja']} 条"

    def _media():
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication
        from PySide6.QtMultimedia import QMediaFormat, QMediaPlayer  # noqa: F401
        from PySide6.QtMultimediaWidgets import QGraphicsVideoItem  # noqa: F401
        app = QApplication.instance() or QApplication([])
        fmts = QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode)
        if not fmts:
            raise RuntimeError("播放器没有可用的解码器")
        # 真的加载一个文件，确认播放器后端和画面组件都能工作
        import subprocess
        import tempfile
        import time
        from pathlib import Path
        from PySide6.QtMultimedia import QAudioOutput
        from app.core.audio.extract import _NO_WINDOW
        from app.tools import find_ffmpeg
        with tempfile.TemporaryDirectory() as td:
            v = Path(td) / "p.mp4"
            subprocess.run([find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)],
                           capture_output=True, creationflags=_NO_WINDOW, timeout=60)
            player = QMediaPlayer()
            out = QAudioOutput()
            item = QGraphicsVideoItem()
            player.setAudioOutput(out)
            player.setVideoOutput(item)
            player.setSource(QUrl.fromLocalFile(str(v)))
            deadline = time.time() + 8
            while time.time() < deadline and player.duration() <= 0 and player.error() == QMediaPlayer.Error.NoError:
                app.processEvents()
                time.sleep(0.05)
            dur, err = player.duration(), player.errorString()
            player.stop()
            player.setSource(QUrl())
            app.processEvents()
        if dur <= 0:
            raise RuntimeError("播放器加载视频失败：" + (err or "超时"))
        return f"可解码 {len(fmts)} 种格式，加载测试视频成功（{dur / 1000:.1f} 秒）"

    step("ctypes", _ctypes)
    step("音频与 VAD", _audio)
    step("ffmpeg", _ffmpeg)
    step("云端 SDK", _sdks)
    step("界面模块", _ui)
    step("界面语言", _languages)
    step("视频播放器", _media)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n" + ("全部通过" if ok else "有失败项") + "\n")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] in ("--version", "-v"):
        from app.version import __version__
        print(__version__)
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == "--check":
        return self_check(sys.argv[2])

    from PySide6.QtWidgets import QApplication

    from app import i18n
    from app.config import load_config

    # 先读设置、定下界面语言，再加载界面模块（界面文字在加载时就按语言取好了）
    cfg = load_config()
    i18n.set_language(cfg.ui_language)
    from app.ui.main_window import APP_NAME, MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(i18n.tr(APP_NAME))
    from app.ui.theme import apply_theme
    apply_theme(app, cfg.ui_theme)
    if i18n.current_language() == "ja":
        # 中文系统的默认字体会把日文汉字画成中文写法（直、選 等字形不同），日文界面换成日文字体
        font = app.font()
        font.setFamilies(["Yu Gothic UI", "Meiryo UI", font.family()])
        app.setFont(font)
    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
