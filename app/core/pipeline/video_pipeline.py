"""视频翻译流程：文件 → 抽音频 → VAD 切块 → 识别 → 整句 → 翻译 → 字幕行。

界面不直接碰任何 API，只调用这里的 run()，通过回调拿进度和日志。
"""
from __future__ import annotations

from app.i18n import tr

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import Config
from app.core.asr.base import Segment, Transcriber
from app.core.audio.extract import extract_pcm, write_wav
from app.core.audio.vad import SAMPLE_RATE, Chunk, SileroVad, detect_chunks, make_utterances
from app.core.cost import CostTracker
from app.core.errors import Cancelled, UserFacingError
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.sentences import merge_into_sentences, split_long_lines
from app.core.translate.base import TranslateRequest, Translator

ProgressCb = Callable[[int, str], None]   # (百分比 0-100, 当前步骤说明)
LogCb = Callable[[str], None]
LinesCb = Callable[[list[SubtitleLine]], None]   # 每拿到一批新字幕行就回调一次（给预览用）


@dataclass
class VideoJob:
    media_path: Path
    output_mode: str = "bilingual"       # bilingual / target_only / source_only
    source_language: str = "auto"
    target_language: str = "zh-Hans"
    asr_prompt: str = ""
    glossary: dict[str, str] = field(default_factory=dict)
    corrections: dict[str, str] = field(default_factory=dict)
    style: str = ""
    scene: str = ""
    tone: str = "subtitle"     # 译文风格档位
    batch_size: int = 15
    context_size: int = 3
    parallel: int = 4          # 同时发几个识别请求
    # 没有时间戳的识别模型：停顿不超过 utterance_gap 秒的说话段合成一块，单块最长 utterance_max_len 秒
    utterance_gap: float = 0.45
    utterance_max_len: float = 12.0


class VideoPipeline:
    def __init__(
        self,
        cfg: Config,
        transcriber: Transcriber,
        translator: Translator | None,
        progress: ProgressCb = lambda p, s: None,
        log: LogCb = lambda s: None,
        on_lines: LinesCb = lambda lines: None,
        cancel: threading.Event | None = None,
        detect_scene: Callable[[str], object] | None = None,
    ) -> None:
        self.cfg = cfg
        self.transcriber = transcriber
        self.translator = translator
        self.progress = progress
        self.log = log
        self.on_lines = on_lines
        self.cancel = cancel or threading.Event()
        # 场景「自动」：识别完后把全文交给它，返回 EffectiveProfile（或 None 表示不变）
        self.detect_scene = detect_scene
        self.detected_scene = None
        self.cost = CostTracker(asr_model=transcriber.model, translate_model=translator.model if translator else "")

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    # ---------------------------------------------------------------
    def run(self, job: VideoJob) -> list[SubtitleLine]:
        self.progress(0, tr("读取音频"))
        self.log(tr("开始处理：{0}", job.media_path.name))
        samples = extract_pcm(job.media_path)
        total_sec = len(samples) / SAMPLE_RATE
        self.log(tr("音频时长 {0}", _fmt(total_sec)))
        self._check_cancel()

        self.progress(3, tr("检测说话段落"))
        regions, chunks = detect_chunks(samples, SileroVad())
        if not self.transcriber.has_timestamps:
            # 模型不给时间戳：按一句话一块切，块的起止就是字幕时间
            chunks = make_utterances(regions, merge_gap=job.utterance_gap, max_len=job.utterance_max_len)
        speech_sec = sum(r.end - r.start for r in regions)
        self.log(tr("检测到说话 {0}，切成 {1} 块送识别", _fmt(speech_sec), len(chunks)))
        if not chunks:
            raise UserFacingError(tr("没有检测到任何说话的声音。可能是纯音乐，或声音太小。"))
        self._check_cancel()

        # ---- 识别（几块同时发，顺序不变）----
        segments: list[Segment] = []
        done = 0
        with ThreadPoolExecutor(max_workers=job.parallel) as pool:
            futures = [pool.submit(self._transcribe_chunk, samples, ch, job) for ch in chunks]
            for i, fut in enumerate(futures):
                try:
                    segs = fut.result()
                except BaseException:
                    self.cancel.set()
                    for f in futures:
                        f.cancel()
                    raise
                done += 1
                self.progress(5 + int(60 * done / len(chunks)), tr("识别中 {0}/{1}（{2}）", done, len(chunks), _fmt(chunks[i].start)))
                segments.extend(segs)
                if segs:
                    preview = segs[0].text[:40]
                    self.log(f"[{_fmt(chunks[i].start)}] {preview}{'…' if len(segs[0].text) > 40 else ''}")
                self._check_cancel()
        self.cost.add_asr(sum(c.duration for c in chunks))
        self.log(tr("识别完成，共 {0} 个片段", len(segments)))
        if not segments:
            raise UserFacingError(tr("识别结果为空。请检查原文语言是否选对，或者视频里确实没有人说话。"))

        # ---- 场景自动判断（识别完才知道内容是什么）----
        if self.detect_scene is not None:
            try:
                prof = self.detect_scene(" ".join(s.text for s in segments))
            except Exception:  # noqa: BLE001
                prof = None
            if prof is not None:
                self.detected_scene = prof
                job.scene = prof.display_name
                job.glossary = prof.glossary_for(job.source_language, job.target_language)
                job.corrections = prof.corrections
                job.style = prof.style
                self.log(tr("自动判断场景：{0}（术语 {1} 条，纠错 {2} 条）", prof.display_name, len(prof.glossary), len(prof.corrections)))

        # ---- 纠错 + 整句 ----
        if job.corrections:
            for s in segments:
                for wrong, right in job.corrections.items():
                    if wrong and wrong in s.text:
                        s.text = s.text.replace(wrong, right)
        lines = split_long_lines(merge_into_sentences(segments))
        self.log(tr("整理成 {0} 句", len(lines)))
        self.progress(66, tr("整理句子"))
        self.on_lines(lines)

        # ---- 翻译 ----
        if job.output_mode == "source_only" or self.translator is None:
            self.progress(100, tr("完成（仅原文）"))
            return lines
        self._translate_all(lines, job)
        self.progress(100, tr("完成"))
        return lines

    # ---------------------------------------------------------------
    def _transcribe_chunk(self, samples, ch: Chunk, job: VideoJob) -> list[Segment]:
        self._check_cancel()
        a = int(ch.start * SAMPLE_RATE)
        b = int(ch.end * SAMPLE_RATE)
        with tempfile.TemporaryDirectory(prefix="subtr_") as td:
            wav = Path(td) / "chunk.wav"
            write_wav(wav, samples[a:b])
            lang = None if job.source_language == "auto" else job.source_language
            segs = self.transcriber.transcribe(wav, language=lang, prompt=job.asr_prompt)
        out: list[Segment] = []
        for s in segs:
            if s.end < 0:   # 没有时间戳的模型：整块当一句
                out.append(Segment(ch.start, ch.end, s.text))
            else:
                out.append(Segment(ch.start + s.start, min(ch.start + s.end, ch.end + 0.5), s.text))
        return out

    def _translate_all(self, lines: list[SubtitleLine], job: VideoJob) -> None:
        total = len(lines)
        done = 0
        prev_sources: list[str] = []
        for start in range(0, total, job.batch_size):
            self._check_cancel()
            batch = lines[start:start + job.batch_size]
            self.progress(68 + int(30 * done / total), tr("翻译中 {0}-{1}/{2}", done + 1, min(done + len(batch), total), total))
            req = TranslateRequest(
                sentences=[ln.source for ln in batch],
                source_language=job.source_language,
                target_language=job.target_language,
                context=prev_sources[-job.context_size:],
                glossary=job.glossary,
                style=job.style,
                scene=job.scene,
                tone=job.tone,
            )
            translations = self.translator.translate(req)
            u = self.translator.last_usage or {}
            self.cost.add_translate(u.get("input", 0), u.get("output", 0), u.get("cache_read", 0))
            for ln, t in zip(batch, translations):
                ln.target = t
            prev_sources.extend(ln.source for ln in batch)
            done += len(batch)
            self.on_lines(lines)
        self.log(tr("翻译完成，共 {0} 句", total))


def _fmt(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
