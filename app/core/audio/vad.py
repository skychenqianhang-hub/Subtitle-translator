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


class StreamingVad:
    """逐帧版 Silero：状态跨帧保留，给实时抓取用。每次喂 512 个采样点（32 毫秒）。"""

    def __init__(self, vad: SileroVad | None = None) -> None:
        self.vad = vad or SileroVad()
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros(CONTEXT, dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)

    def process(self, frame: np.ndarray) -> float:
        if len(frame) < WINDOW:
            frame = np.pad(frame, (0, WINDOW - len(frame)))
        x = np.concatenate([self.context, frame[:WINDOW]]).astype(np.float32)[None, :]
        out, self.state = self.vad.session.run(None, {"input": x, "state": self.state, "sr": self._sr})
        self.context = frame[:WINDOW][-CONTEXT:]
        return float(out[0, 0])


@dataclass
class LiveSegment:
    start: float          # 秒，相对会话开始
    end: float
    samples: np.ndarray   # 16kHz float32


class Segmenter:
    """实时切段：检测到说话就开始攒，停顿够长或攒够最长时长就切出一段。

    - threshold / neg：开始 / 结束说话的概率门槛
    - min_silence：停顿多久算一句结束
    - max_len：一直不停顿时最多攒多少秒（对应界面上的「翻译延迟」）
    - pre_roll：切段时往前多带一点，避免吃掉第一个字
    """

    def __init__(self, vad: StreamingVad | None = None, threshold: float = 0.5, neg: float = 0.35,
                 min_silence: float = 0.6, max_len: float = 6.0, min_speech: float = 0.3, pre_roll: float = 0.4) -> None:
        self.vad = vad or StreamingVad()
        self.threshold, self.neg = threshold, neg
        self.min_silence, self.max_len, self.min_speech, self.pre_roll = min_silence, max_len, min_speech, pre_roll
        self._pending = np.zeros(0, dtype=np.float32)
        self._frames_seen = 0
        self._in_speech = False
        self._buf: list[np.ndarray] = []
        self._buf_start = 0.0
        self._silence_frames = 0
        self._speech_frames = 0
        self._ring: list[np.ndarray] = []   # 最近几帧，用作 pre_roll
        self._ring_max = max(1, int(pre_roll * SAMPLE_RATE / WINDOW))

    @property
    def now(self) -> float:
        return self._frames_seen * WINDOW / SAMPLE_RATE

    def feed(self, samples: np.ndarray) -> list[LiveSegment]:
        """喂任意长度的音频，返回这次切出来的段（可能为空）。"""
        out: list[LiveSegment] = []
        data = np.concatenate([self._pending, samples.astype(np.float32, copy=False)])
        n = len(data) // WINDOW
        for i in range(n):
            frame = data[i * WINDOW:(i + 1) * WINDOW]
            seg = self._process_frame(frame)
            if seg is not None:
                out.append(seg)
        self._pending = data[n * WINDOW:]
        return out

    def _process_frame(self, frame: np.ndarray) -> LiveSegment | None:
        prob = self.vad.process(frame)
        self._frames_seen += 1
        t = self.now
        self._ring.append(frame)
        if len(self._ring) > self._ring_max:
            self._ring.pop(0)
        if not self._in_speech:
            if prob >= self.threshold:
                self._in_speech = True
                self._buf = list(self._ring)
                self._buf_start = t - len(self._ring) * WINDOW / SAMPLE_RATE
                self._silence_frames = 0
                self._speech_frames = 1
            return None
        self._buf.append(frame)
        if prob >= self.threshold:
            self._speech_frames += 1
            self._silence_frames = 0
        elif prob < self.neg:
            self._silence_frames += 1
        duration = t - self._buf_start
        silence = self._silence_frames * WINDOW / SAMPLE_RATE
        if silence >= self.min_silence or duration >= self.max_len:
            return self._close(t, trim_silence=silence >= self.min_silence)
        return None

    def _close(self, t: float, trim_silence: bool) -> LiveSegment | None:
        buf = self._buf
        self._buf = []
        self._in_speech = False
        speech_sec = self._speech_frames * WINDOW / SAMPLE_RATE
        start = self._buf_start
        end = t
        if trim_silence:
            keep = max(1, len(buf) - self._silence_frames + int(0.15 * SAMPLE_RATE / WINDOW))
            buf = buf[:keep]
            end = start + len(buf) * WINDOW / SAMPLE_RATE
        self._silence_frames = 0
        self._speech_frames = 0
        if speech_sec < self.min_speech or not buf:
            return None
        return LiveSegment(start, end, np.concatenate(buf))

    def flush(self) -> LiveSegment | None:
        """停止时把正在攒的半句吐出来。"""
        if self._in_speech and self._buf:
            return self._close(self.now, trim_silence=False)
        return None
