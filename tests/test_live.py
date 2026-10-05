"""阶段 5 自检：流式 VAD、实时切段、整句缓冲、实时流程（假抓取 + 假识别 / 翻译）、实时页界面联动。

运行：python -m tests.test_live
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="subtranslator_live_")
os.environ["APPDATA"] = _tmp

from app.config import Config  # noqa: E402
from app.core.audio.capture import resample  # noqa: E402
from app.core.audio.extract import SAMPLE_RATE, extract_pcm  # noqa: E402
from app.core.audio.vad import Segmenter, SileroVad, StreamingVad, WINDOW  # noqa: E402
from app.core.pipeline.live_pipeline import LiveCallbacks, LiveOptions, LiveSession, SentenceBuffer  # noqa: E402
from app.core.subtitle.models import SubtitleLine  # noqa: E402
from tests.test_pipeline import FIXTURES, FakeTextTranscriber, FakeTranslator  # noqa: E402


class FakeCapture:
    """假抓取：把一段音频按真实时间（或加速）切成小块送出去。"""

    def __init__(self, audio: np.ndarray, on_chunk, speed: float = 8.0, chunk: int = 2048) -> None:
        self.audio, self.on_chunk, self.speed, self.chunk = audio, on_chunk, speed, chunk
        self.rate = SAMPLE_RATE
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self) -> None:
        pos = 0
        while pos < len(self.audio) and not self._stop.is_set():
            self.on_chunk(self.audio[pos:pos + self.chunk])
            pos += self.chunk
            time.sleep(self.chunk / SAMPLE_RATE / self.speed)
        # 尾巴补一点静音，让最后一句能切出来
        for _ in range(20):
            if self._stop.is_set():
                break
            self.on_chunk(np.zeros(self.chunk, dtype=np.float32))
            time.sleep(0.01)

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)


def test_streaming_vad() -> None:
    audio = extract_pcm(FIXTURES / "tts_en.wav")
    vad = SileroVad()
    batch = vad.speech_probabilities(audio)
    sv = StreamingVad(vad)
    stream = np.array([sv.process(audio[i * WINDOW:(i + 1) * WINDOW]) for i in range(len(audio) // WINDOW)])
    n = min(len(batch), len(stream))
    assert np.abs(batch[:n] - stream[:n]).max() < 1e-4, "流式和整段的结果应一致"
    print("流式 VAD：OK")


def test_segmenter() -> None:
    audio = extract_pcm(FIXTURES / "tts_en.wav")
    seg = Segmenter(StreamingVad(), max_len=6.0)
    segments = []
    for i in range(0, len(audio), 1600):
        segments.extend(seg.feed(audio[i:i + 1600]))
    last = seg.flush()
    if last:
        segments.append(last)
    assert 3 <= len(segments) <= 8, [(round(s.start, 2), round(s.end, 2)) for s in segments]
    assert all(s.end > s.start and len(s.samples) > SAMPLE_RATE * 0.2 for s in segments)
    assert all(b.start >= a.start for a, b in zip(segments, segments[1:])), "应按时间顺序"
    assert all(s.end - s.start <= 6.3 for s in segments), "不能超过最长时长"
    # 一直不停顿的长音（正弦+噪声不像说话，用重复的说话段拼接）
    long = np.concatenate([audio[int(1 * SAMPLE_RATE):int(3 * SAMPLE_RATE)]] * 6)
    seg2 = Segmenter(StreamingVad(), max_len=4.0, min_silence=5.0)
    out2 = seg2.feed(long)
    assert out2 and all(s.end - s.start <= 4.3 for s in out2), "max_len 应强制切段"
    # 重采样
    r = resample(np.ones(48000, dtype=np.float32), 48000)
    assert len(r) == 16000 and abs(float(r.mean()) - 1.0) < 1e-6
    print(f"实时切段：OK（{len(segments)} 段）")


def test_sentence_buffer() -> None:
    b = SentenceBuffer(hold_seconds=2.0)
    assert b.push(SubtitleLine(0, 1, "今日は"), 0.0) == []           # 半句，攒着
    out = b.push(SubtitleLine(1.2, 2.5, "いい天気ですね。"), 1.0)      # 接上并以句号结尾 → 整句
    assert len(out) == 1 and out[0].source == "今日はいい天気ですね。" and out[0].start == 0 and out[0].end == 2.5
    assert b.push(SubtitleLine(3, 4, "Hello there"), 2.0) == []
    out = b.push(SubtitleLine(6, 7, "Bye."), 3.0)                    # 停顿太久 → 前一句单独放出，后一句完整
    assert [o.source for o in out] == ["Hello there", "Bye."]
    assert b.push(SubtitleLine(8, 9, "half"), 10.0) == [] and b.poll(11.0) is None
    held = b.poll(12.5)
    assert held is not None and held.source == "half", "超时应放出半句"
    assert b.flush() is None
    print("整句缓冲：OK")


def test_live_session() -> None:
    audio = extract_pcm(FIXTURES / "tts_en.wav")
    events: list[tuple[str, object]] = []
    lock = threading.Lock()

    def rec(kind):
        def f(*a):
            with lock:
                events.append((kind, a))
        return f

    cbs = LiveCallbacks(on_status=rec("status"), on_log=rec("log"), on_source=rec("source"),
                        on_translated=rec("translated"), on_error=rec("error"), on_level=rec("level"))
    tr, tl = FakeTextTranscriber(), FakeTranslator()
    opts = LiveOptions(max_segment_seconds=6.0, source_language="en", hold_half_sentence_seconds=0.5)
    sess = LiveSession(Config(), tr, tl, opts, cbs, capture_factory=lambda on_chunk: FakeCapture(audio, on_chunk))
    sess.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        with lock:
            done = sum(1 for k, _ in events if k == "translated")
        if done >= 2 and tr.calls >= 2:
            time.sleep(0.5)
            break
        time.sleep(0.1)
    sess.stop()
    kinds = [k for k, _ in events]
    assert "source" in kinds and "translated" in kinds, kinds
    assert not [a for k, a in events if k == "error"], [a for k, a in events if k == "error"]
    assert sess.lines and all(ln.target.startswith("译：") for ln in sess.lines), sess.lines
    assert sess.cost.asr_seconds > 0 and sess.cost.input_tokens > 0
    assert any(k == "level" for k in kinds)
    starts = [ln.start for ln in sess.lines]
    assert starts == sorted(starts)
    print(f"实时流程：OK（识别 {tr.calls} 段 → {len(sess.lines)} 句，费用：{sess.cost.summary()}）")


def test_realtime_page() -> None:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app import config as config_mod
    from app.core.asr import registry as asr_registry
    from app.core.translate import registry as tr_registry
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.warning = staticmethod(lambda *a, **k: print("  [warning]", a[2] if len(a) > 2 else a))
    QMessageBox.critical = staticmethod(lambda *a, **k: print("  [error]", a[2] if len(a) > 2 else a))
    asr_registry.create_transcriber = lambda cfg, *a, **k: FakeTextTranscriber()
    tr_registry.create_translator = lambda cfg, *a, **k: FakeTranslator()
    cfg = config_mod.load_config()
    cfg.openai_api_key = "sk-test"
    cfg.translate_provider = "openai"
    config_mod.save_config(cfg)
    win = MainWindow(cfg)
    win.show()
    rp = win.realtime_page
    audio = extract_pcm(FIXTURES / "tts_ja.wav")
    rp._make_session = lambda tr, tl, opts, cbs: LiveSession(cfg, tr, tl, opts, cbs,
                                                             capture_factory=lambda on_chunk: FakeCapture(audio, on_chunk))

    def wait(cond, ms=30000):
        loop = QEventLoop()
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(loop.quit)
        t.start(ms)
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if cond() else None)
        poll.start(50)
        while not cond() and t.isActive():
            loop.exec()
        poll.stop()
        return cond()

    rp.start_session()
    assert rp.is_running() and not rp.start_button.isEnabled()
    assert wait(lambda: "译：" in rp.log.toPlainText()), "日志里应出现译文"
    assert win.overlay.isVisible() and "译：" in win.overlay.target_label.text(), win.overlay.target_label.text()
    rp.stop_session()
    assert wait(lambda: not rp.is_running()), "停止超时"
    assert rp.save_button.isEnabled() and rp._session_lines
    from PySide6.QtWidgets import QFileDialog
    out = Path(_tmp) / "live.srt"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), ""))
    rp.save_session()
    assert out.exists() and out.with_suffix(".txt").exists() and "译：" in out.read_text(encoding="utf-8-sig")
    print("实时页界面联动 / 保存本场：OK")
    win.close()


def main() -> int:
    test_streaming_vad()
    test_segmenter()
    test_sentence_buffer()
    test_live_session()
    test_realtime_page()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
