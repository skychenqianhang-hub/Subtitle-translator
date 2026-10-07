"""实时翻译流程：抓声音 → 切段 → 识别 → 整句缓冲 → 翻译 → 回调给界面。

线程：
- 抓取线程（LoopbackCapture）把音频塞进队列
- 切段线程：VAD，切出一段就交给识别线程池
- 识别线程池：几段同时识别，结果按顺序交给翻译线程
- 翻译线程：整句缓冲 + 带上下文翻译，结果回调

界面只通过回调拿结果；回调可能来自任意线程，界面那边用 Qt 信号转到主线程。
"""
from __future__ import annotations

from app.i18n import tr

import queue
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from app.config import Config
from app.core.asr.base import Transcriber
from app.core.audio.capture import LoopbackCapture
from app.core.audio.extract import write_wav
from app.core.audio.vad import LiveSegment, Segmenter, StreamingVad
from app.core.cost import CostTracker
from app.core.errors import friendly_message
from app.core.subtitle.models import SubtitleLine
from app.core.translate.base import TranslateRequest, Translator

_END_PUNCT = "。．.!！?？」』…"
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


@dataclass
class LiveCallbacks:
    on_status: Callable[[str], None] = lambda s: None
    on_log: Callable[[str], None] = lambda s: None
    on_source: Callable[[int, SubtitleLine], None] = lambda i, ln: None     # 识别出来（还没翻译）
    on_translated: Callable[[int, SubtitleLine], None] = lambda i, ln: None  # 翻译完成
    on_error: Callable[[str], None] = lambda s: None
    on_level: Callable[[float], None] = lambda v: None                       # 音量（0-1），给界面画电平
    on_scene: Callable[[str, str], None] = lambda name, display: None        # 自动模式下场景切换了


@dataclass
class LiveOptions:
    device_index: int | None = None
    max_segment_seconds: float = 6.0        # 「翻译延迟」
    output_mode: str = "bilingual"
    source_language: str = "auto"
    target_language: str = "zh-Hans"
    asr_prompt: str = ""
    glossary: dict[str, str] = field(default_factory=dict)
    corrections: dict[str, str] = field(default_factory=dict)
    style: str = ""
    scene: str = ""
    tone: str = "casual"                      # 译文风格档位
    context_size: int = 3
    hold_half_sentence_seconds: float = 2.5   # 半句话最多等多久再翻译
    auto_scene: bool = False                  # 场景选了「自动」
    scene_name: str = "通用"                  # 当前场景（自动模式下会变）
    auto_window_lines: int = 14               # 自动判断时看最近多少句
    auto_min_interval: float = 20.0           # 两次切换至少隔多少秒


class SentenceBuffer:
    """半句话先攒着，拼成整句再翻译；超时或停顿太久就直接翻。"""

    def __init__(self, hold_seconds: float = 2.5, max_chars: int = 120) -> None:
        self.hold_seconds = hold_seconds
        self.max_chars = max_chars
        self.pending: SubtitleLine | None = None
        self.pending_since = 0.0

    @staticmethod
    def _ends(text: str) -> bool:
        t = text.rstrip()
        return bool(t) and t[-1] in _END_PUNCT

    @staticmethod
    def _join(a: str, b: str) -> str:
        if _CJK.search(a[-1:]) or _CJK.search(b[:1]):
            return a.rstrip() + b.lstrip()
        return a.rstrip() + " " + b.lstrip()

    def push(self, line: SubtitleLine, now: float) -> list[SubtitleLine]:
        """放进一句识别结果，返回现在可以翻译的整句（0、1 或 2 句）。"""
        out: list[SubtitleLine] = []
        if self.pending is not None:
            gap = line.start - self.pending.end
            if gap <= 1.2 and len(self.pending.source) + len(line.source) <= self.max_chars:
                line = SubtitleLine(self.pending.start, line.end, self._join(self.pending.source, line.source))
            else:
                out.append(self.pending)
            self.pending = None
        if self._ends(line.source) or len(line.source) >= self.max_chars:
            out.append(line)
        else:
            self.pending = line
            self.pending_since = now
        return out

    def poll(self, now: float) -> SubtitleLine | None:
        """半句话等太久了就放出来。"""
        if self.pending is not None and now - self.pending_since >= self.hold_seconds:
            ln, self.pending = self.pending, None
            return ln
        return None

    def flush(self) -> SubtitleLine | None:
        ln, self.pending = self.pending, None
        return ln


class LiveSession:
    def __init__(self, cfg: Config, transcriber: Transcriber, translator: Translator | None,
                 options: LiveOptions, callbacks: LiveCallbacks, capture_factory=None,
                 scene_detector=None, scene_resolver=None) -> None:
        """scene_detector / scene_resolver：自动场景用。resolver(name) 返回 EffectiveProfile。"""
        self.cfg = cfg
        self.scene_detector = scene_detector
        self.scene_resolver = scene_resolver
        self._recent_sources: list[str] = []
        self._last_scene_switch = 0.0
        self.transcriber = transcriber
        self.translator = translator
        self.opt = options
        self.cb = callbacks
        self.capture_factory = capture_factory or (lambda on_chunk: LoopbackCapture(options.device_index, on_chunk))
        self.cost = CostTracker(asr_model=transcriber.model, translate_model=translator.model if translator else "")
        self.lines: list[SubtitleLine] = []          # 本场所有字幕（按序号）
        self._audio_q: "queue.Queue[np.ndarray | None]" = queue.Queue()
        self._asr_results: "queue.Queue[tuple[int, SubtitleLine | None]]" = queue.Queue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._pool: ThreadPoolExecutor | None = None
        self._seq = 0
        self._capture: LoopbackCapture | None = None
        self.started_at = 0.0
        self.running = False

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self._stop.clear()
        self.started_at = time.time()
        self._capture = self.capture_factory(self._on_chunk)
        self._capture.start()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="live-asr")
        self._threads = [
            threading.Thread(target=self._segment_loop, name="live-segment", daemon=True),
            threading.Thread(target=self._translate_loop, name="live-translate", daemon=True),
        ]
        for t in self._threads:
            t.start()
        self.running = True
        self.cb.on_status(tr("正在监听"))
        self.cb.on_log(tr("开始：设备 {0}Hz，识别 {1}，翻译 {2}，最长 {3:.0f} 秒切一段", getattr(self._capture, 'rate', '?'), self.transcriber.model, self.translator.model if self.translator else '无', self.opt.max_segment_seconds))

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self._stop.set()
        if self._capture is not None:
            self._capture.stop()
        self._audio_q.put(None)
        for t in self._threads:
            t.join(timeout=15.0)
        if self._pool is not None:
            self._pool.shutdown(wait=True)
        self.cb.on_status(tr("已停止"))
        self.cb.on_log(tr("结束。本次费用：") + self.cost.summary())

    # ------------------------------------------------------------ 抓取 → 切段
    def _on_chunk(self, chunk: np.ndarray) -> None:
        if len(chunk):
            self.cb.on_level(float(min(1.0, np.abs(chunk).max() * 3)))
        self._audio_q.put(chunk)

    def _segment_loop(self) -> None:
        try:
            seg = Segmenter(StreamingVad(), max_len=self.opt.max_segment_seconds)
        except Exception as e:  # noqa: BLE001
            self.cb.on_error(friendly_message(e))
            return
        while True:
            try:
                chunk = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            if chunk is None:
                break
            for s in seg.feed(chunk):
                self._submit(s)
        last = seg.flush()
        if last is not None:
            self._submit(last)
        self._asr_results.put((-1, None))   # 告诉翻译线程：不会再有新段了

    def _submit(self, s: LiveSegment) -> None:
        if self._pool is None:
            return
        idx = self._seq
        self._seq += 1
        self._pool.submit(self._transcribe, idx, s)

    # ------------------------------------------------------------ 识别
    def _transcribe(self, idx: int, s: LiveSegment) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="subtr_live_") as td:
                wav = Path(td) / "seg.wav"
                write_wav(wav, s.samples)
                lang = None if self.opt.source_language == "auto" else self.opt.source_language
                segs = self.transcriber.transcribe(wav, language=lang, prompt=self.opt.asr_prompt)
            self.cost.add_asr(s.end - s.start)
            text = " ".join(x.text.strip() for x in segs if x.text.strip()).strip()
            for wrong, right in self.opt.corrections.items():
                if wrong and wrong in text:
                    text = text.replace(wrong, right)
            line = SubtitleLine(s.start, s.end, text) if text else None
        except Exception as e:  # noqa: BLE001
            self.cb.on_error(tr("识别出错：") + friendly_message(e))
            line = None
        self._asr_results.put((idx, line))

    # ------------------------------------------------------------ 翻译
    def _translate_loop(self) -> None:
        buffer = SentenceBuffer(self.opt.hold_half_sentence_seconds)
        pending: dict[int, SubtitleLine | None] = {}
        next_idx = 0
        finished = False
        while True:
            try:
                idx, line = self._asr_results.get(timeout=0.3)
                if idx == -1:
                    finished = True
                else:
                    pending[idx] = line
            except queue.Empty:
                pass
            # 按顺序取出已完成的段
            while next_idx in pending:
                line = pending.pop(next_idx)
                next_idx += 1
                if line is None:
                    continue
                self.lines.append(line)
                self.cb.on_source(len(self.lines) - 1, line)
                self._maybe_switch_scene(line.source)
                for ready in buffer.push(line, time.time()):
                    self._translate_line(ready)
            held = buffer.poll(time.time())
            if held is not None:
                self._translate_line(held)
            if finished and not pending:
                last = buffer.flush()
                if last is not None:
                    self._translate_line(last)
                break

    def _maybe_switch_scene(self, new_text: str) -> None:
        """自动场景：看最近若干句里哪个场景的特征词最多，证据充分就切换。"""
        if not (self.opt.auto_scene and self.scene_detector and self.scene_resolver):
            return
        self._recent_sources.append(new_text)
        if len(self._recent_sources) > self.opt.auto_window_lines:
            self._recent_sources.pop(0)
        now = time.time()
        if now - self._last_scene_switch < self.opt.auto_min_interval and self._last_scene_switch > 0:
            return
        try:
            chosen = self.scene_detector.choose(" ".join(self._recent_sources), self.opt.scene_name)
        except Exception:  # noqa: BLE001
            return
        if chosen == self.opt.scene_name:
            return
        try:
            prof = self.scene_resolver(chosen)
        except Exception:  # noqa: BLE001
            return
        self.opt.scene_name = chosen
        self.opt.scene = prof.display_name
        self.opt.glossary = prof.glossary_for(self.opt.source_language, self.opt.target_language)
        self.opt.corrections = prof.corrections
        self.opt.asr_prompt = ", ".join(prof.asr_prompt)
        self.opt.style = prof.style
        self._last_scene_switch = now
        self.cb.on_scene(chosen, prof.display_name)
        self.cb.on_log(tr("场景自动切换为：{0}（术语 {1} 条）", prof.display_name, len(prof.glossary)))

    def _translate_line(self, line: SubtitleLine) -> None:
        if self.translator is None or self.opt.output_mode == "source_only":
            self._publish(line, line.source if self.opt.output_mode == "source_only" else "")
            return
        context = [ln.source for ln in self.lines if ln is not line and ln.end <= line.start][-self.opt.context_size:]
        req = TranslateRequest(
            sentences=[line.source], source_language=self.opt.source_language,
            target_language=self.opt.target_language, context=context, glossary=self.opt.glossary,
            style=self.opt.style, scene=self.opt.scene, tone=self.opt.tone,
        )
        try:
            target = self.translator.translate(req)[0]
            u = self.translator.last_usage or {}
            self.cost.add_translate(u.get("input", 0), u.get("output", 0), u.get("cache_read", 0))
        except Exception as e:  # noqa: BLE001
            self.cb.on_error(tr("翻译出错：") + friendly_message(e))
            target = ""
        self._publish(line, target)

    def _publish(self, line: SubtitleLine, target: str) -> None:
        # 整句缓冲可能把几段合成了一句：把对应的原句替换成合并后的这一句
        merged_idx = [i for i, ln in enumerate(self.lines) if ln.start >= line.start and ln.end <= line.end]
        if merged_idx:
            first = merged_idx[0]
            for i in reversed(merged_idx[1:]):
                self.lines.pop(i)
            self.lines[first] = SubtitleLine(line.start, line.end, line.source, target)
            idx = first
        else:
            self.lines.append(SubtitleLine(line.start, line.end, line.source, target))
            idx = len(self.lines) - 1
        self.cb.on_translated(idx, self.lines[idx])
