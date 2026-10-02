"""视频页界面联动自检：用假适配器在真实的后台线程里跑一遍，验证进度、预览、保存、取消。

运行：python -m tests.test_video_page
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="subtranslator_ui_")
os.environ["APPDATA"] = _tmp

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import config as config_mod  # noqa: E402
from app.core.asr import registry as asr_registry  # noqa: E402
from app.core.translate import registry as tr_registry  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from tests.test_pipeline import FIXTURES, FakeTranscriber, FakeTranslator  # noqa: E402


def wait_until(cond, timeout_ms: int = 60000) -> bool:
    loop = QEventLoop()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(timeout_ms)
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if cond() else None)
    poll.start(50)
    while not cond() and deadline.isActive():
        loop.exec()
    poll.stop()
    return cond()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    # 不弹真实对话框
    QMessageBox.warning = staticmethod(lambda *a, **k: print("  [warning box]", a[2] if len(a) > 2 else a))
    QMessageBox.critical = staticmethod(lambda *a, **k: print("  [error box]", a[2] if len(a) > 2 else a))

    # 假适配器替换真实的登记表
    asr_registry.create_transcriber = lambda cfg, provider=None, model=None: FakeTranscriber()
    tr_registry.create_translator = lambda cfg, provider=None, model=None: FakeTranslator()

    cfg = config_mod.load_config()
    cfg.openai_api_key = "sk-test"
    cfg.anthropic_api_key = "sk-ant-test"
    config_mod.save_config(cfg)

    media = Path(_tmp) / "sample.wav"
    shutil.copy(FIXTURES / "tts_ja.wav", media)

    win = MainWindow(cfg)
    win.show()
    vp = win.video_page

    # 1. 没选文件 → 提示，不启动
    vp.file_edit.setText("")
    vp._start()
    assert not vp.is_running()
    print("空文件校验：OK")

    # 2. 双语完整跑一遍
    vp.file_edit.setText(str(media))
    vp.output_mode.set_current("bilingual")
    vp._start()
    assert vp.is_running() and not vp.start_button.isEnabled()
    assert wait_until(lambda: not vp.is_running()), "处理超时"
    assert vp.progress.value() == 100, vp.progress.value()
    srt = media.with_suffix(".srt")
    assert srt.exists(), "没有生成 SRT"
    text = srt.read_text(encoding="utf-8-sig")
    assert "译：" in text and "-->" in text, text[:200]
    assert "已保存" in vp.result_label.text()
    assert vp.export_button.isEnabled() and vp.start_button.isEnabled()
    print("双语处理 → SRT：OK", srt.name)

    # 3. 仅原文 → .orig.srt，不含译文
    vp.output_mode.set_current("source_only")
    vp._start()
    assert wait_until(lambda: not vp.is_running())
    orig = media.with_suffix(".orig.srt")
    assert orig.exists() and "译：" not in orig.read_text(encoding="utf-8-sig")
    print("仅原文 → .orig.srt：OK")

    # 4. 取消
    vp.output_mode.set_current("bilingual")
    vp._start()
    vp._cancel()
    assert wait_until(lambda: not vp.is_running())
    assert "取消" in vp.status.text(), vp.status.text()
    print("取消：OK")

    win.close()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
