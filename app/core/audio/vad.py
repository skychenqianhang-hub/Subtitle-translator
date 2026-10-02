"""语音活动检测（VAD）：找出音频里哪些时间段有人说话，并切成适合送识别的小块。

用 Silero VAD 的 ONNX 模型（随程序打包，约 2MB），只需要 onnxruntime，不需要 torch。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
WINDOW = 512          # Silero 在 16kHz 下每次吃 512 个采样点（32 毫秒）
CONTEXT = 64          # v5 模型要求把上一窗的最后 64 个点拼在前面


@dataclass
class SpeechRegion:
    start: float  # 秒
    end: float


@dataclass
class Chunk:
    """送去识别的一块音频：从 start 到 end（秒），内部可能含短停顿。"""
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def model_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        base / "app" / "core" / "audio" / "models" / "silero_vad.onnx",   # 打包后
        Path(__file__).resolve().parent / "models" / "silero_vad.onnx",    # 开发时
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError("silero_vad.onnx")


class SileroVad:
    def __init__(self) -> None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(model_path()), opts, providers=["CPUExecutionProvider"])

    def speech_probabilities(self, samples: np.ndarray) -> np.ndarray:
        """每 32 毫秒一个「有人说话」的概率。"""
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(CONTEXT, dtype=np.float32)
        sr = np.array(SAMPLE_RATE, dtype=np.int64)
        n = (len(samples) + WINDOW - 1) // WINDOW
        probs = np.zeros(n, dtype=np.float32)
        for i in range(n):
            frame = samples[i * WINDOW:(i + 1) * WINDOW]
            if len(frame) < WINDOW:
                frame = np.pad(frame, (0, WINDOW - len(frame)))
            x = np.concatenate([context, frame]).astype(np.float32)[None, :]
            out, state = self.session.run(None, {"input": x, "state": state, "sr": sr})
            probs[i] = float(out[0, 0])
            context = frame[-CONTEXT:]
        return probs


def find_speech(
    probs: np.ndarray,
    threshold: float = 0.5,
    min_speech: float = 0.25,
    min_silence: float = 0.5,
    pad: float = 0.15,
    total_seconds: float | None = None,
) -> list[SpeechRegion]:
    """把逐帧概率变成说话时间段。"""
    frame = WINDOW / SAMPLE_RATE
    neg = max(threshold - 0.15, 0.01)
    regions: list[SpeechRegion] = []
    in_speech = False
    start = 0.0
    silence_start = 0.0
    for i, p in enumerate(probs):
        t = i * frame
        if p >= threshold and not in_speech:
            in_speech = True
            start = t
        elif in_speech and p < neg:
            if silence_start == 0.0:
                silence_start = t
            elif t - silence_start >= min_silence:
                end = silence_start
                if end - start >= min_speech:
                    regions.append(SpeechRegion(start, end))
                in_speech = False
                silence_start = 0.0
        elif in_speech and p >= threshold:
            silence_start = 0.0
    if in_speech:
        end = len(probs) * frame
        if end - start >= min_speech:
            regions.append(SpeechRegion(start, end))

    limit = total_seconds if total_seconds is not None else len(probs) * frame
    padded: list[SpeechRegion] = []
    for r in regions:
        s, e = max(0.0, r.start - pad), min(limit, r.end + pad)
        if padded and s <= padded[-1].end:
            padded[-1].end = e
        else:
            padded.append(SpeechRegion(s, e))
    return padded


def make_chunks(
    regions: list[SpeechRegion],
    max_chunk: float = 90.0,
    split_gap: float = 2.0,
    min_chunk: float = 15.0,
) -> list[Chunk]:
    """把说话段合并成识别块：
    - 两段之间停顿超过 split_gap 且当前块已够长 → 切开
    - 块长度超过 max_chunk → 切开
    这样每块都是从说话开始到说话结束，不含长静音，Whisper 不容易瞎编。
    """
    chunks: list[Chunk] = []
    cur: Chunk | None = None
    for r in regions:
        if cur is None:
            cur = Chunk(r.start, r.end)
            continue
        gap = r.start - cur.end
        would_be = r.end - cur.start
        if would_be > max_chunk or (gap >= split_gap and cur.duration >= min_chunk):
            chunks.append(cur)
            cur = Chunk(r.start, r.end)
        else:
            cur.end = r.end
    if cur is not None:
        chunks.append(cur)
    # 单个说话段本身就超长（一直没停顿）：硬切
    out: list[Chunk] = []
    for c in chunks:
        while c.duration > max_chunk * 1.2:
            out.append(Chunk(c.start, c.start + max_chunk))
            c = Chunk(c.start + max_chunk, c.end)
        out.append(c)
    return out


def make_utterances(
    regions: list[SpeechRegion],
    merge_gap: float = 0.6,
    max_len: float = 12.0,
) -> list[Chunk]:
    """按「一句话一块」切：停顿小于 merge_gap 的相邻说话段合并，单块不超过 max_len。
    给没有时间戳的识别模型用，块的起止就是字幕时间。"""
    out: list[Chunk] = []
    cur: Chunk | None = None
    for r in regions:
        if cur is None:
            cur = Chunk(r.start, r.end)
            continue
        if r.start - cur.end <= merge_gap and r.end - cur.start <= max_len:
            cur.end = r.end
        else:
            out.append(cur)
            cur = Chunk(r.start, r.end)
    if cur is not None:
        out.append(cur)
    final: list[Chunk] = []
    for c in out:
        while c.duration > max_len * 1.5:
            final.append(Chunk(c.start, c.start + max_len))
            c = Chunk(c.start + max_len, c.end)
        final.append(c)
    return final


def detect_chunks(samples: np.ndarray, vad: SileroVad | None = None, **kw) -> tuple[list[SpeechRegion], list[Chunk]]:
    vad = vad or SileroVad()
    probs = vad.speech_probabilities(samples)
    regions = find_speech(probs, total_seconds=len(samples) / SAMPLE_RATE)
    return regions, make_chunks(regions, **kw)
