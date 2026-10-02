"""阶段 2 自检：不调用任何云端 API，用假的识别器 / 翻译器跑通整条流程。

运行：python -m tests.test_pipeline [可选：一个视频或音频文件路径]
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config import Config  # noqa: E402
from app.core.asr.base import Segment, Transcriber  # noqa: E402
from app.core.audio.extract import SAMPLE_RATE, extract_pcm, write_wav  # noqa: E402
from app.core.audio.vad import SileroVad, detect_chunks, find_speech, make_chunks, make_utterances, SpeechRegion  # noqa: E402
from app.core.errors import Cancelled, UserFacingError, friendly_message  # noqa: E402
from app.core.pipeline.video_pipeline import VideoJob, VideoPipeline  # noqa: E402
from app.core.subtitle.sentences import merge_into_sentences, split_long_lines  # noqa: E402
from app.core.subtitle.srt import fmt_time, to_srt  # noqa: E402
from app.core.translate.base import TranslateRequest, Translator  # noqa: E402
from app.core.translate.prompt import parse_translations, system_prompt, user_prompt  # noqa: E402


class FakeTranscriber(Transcriber):
    provider = "fake"

    def __init__(self) -> None:
        super().__init__("fake")
        self.calls = 0

    def transcribe(self, wav_path: Path, language=None, prompt=""):
        import soundfile as sf
        data, sr = sf.read(str(wav_path))
        dur = len(data) / sr
        self.calls += 1
        # 每块假装识别出两句日语，时间占块的前后两半
        return [
            Segment(0.0, dur / 2, f"これは{self.calls}番目のブロックです。"),
            Segment(dur / 2, dur, "テストの音声なので"),
        ]


class FakeTextTranscriber(Transcriber):
    """模拟 gpt-transcribe：不给时间戳，整块一句话。"""
    provider = "fake"

    def __init__(self) -> None:
        super().__init__("gpt-transcribe")
        self.calls = 0
        self.lock = threading.Lock()

    @property
    def has_timestamps(self) -> bool:
        return False

    def transcribe(self, wav_path: Path, language=None, prompt=""):
        import time
        time.sleep(0.05)
        with self.lock:
            self.calls += 1
            n = self.calls
        return [Segment(0.0, -1.0, f"第{n}块的内容")]


class FakeTranslator(Translator):
    provider = "fake"

    def __init__(self) -> None:
        super().__init__("fake")
        self.requests: list[TranslateRequest] = []

    def translate(self, req: TranslateRequest) -> list[str]:
        self.requests.append(req)
        return [f"译：{s}" for s in req.sentences]


def synth_speech_like(seconds: float) -> np.ndarray:
    """合成一段「像说话」的音频：有声段用带调制的噪声+谐波，中间留静音。"""
    rng = np.random.default_rng(0)
    n = int(seconds * SAMPLE_RATE)
    out = np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SAMPLE_RATE
    # 说话段：0.5-3.0s, 4.0-6.5s, 9.0-11.0s
    for a, b in [(0.5, 3.0), (4.0, 6.5), (9.0, 11.0)]:
        i, j = int(a * SAMPLE_RATE), int(b * SAMPLE_RATE)
        seg_t = t[i:j]
        f0 = 120 + 30 * np.sin(2 * np.pi * 3 * seg_t)
        voiced = sum(np.sin(2 * np.pi * f0 * k * seg_t) / k for k in range(1, 8))
        env = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * seg_t) ** 2
        out[i:j] = (0.25 * voiced * env + 0.02 * rng.standard_normal(j - i)).astype(np.float32)
    return out


def test_vad_logic() -> None:
    # 纯逻辑：概率 → 说话段 → 块
    probs = np.zeros(1000, dtype=np.float32)
    probs[10:100] = 0.9      # 0.32s - 3.2s
    probs[130:200] = 0.9     # 4.16s - 6.4s
    probs[400:420] = 0.9     # 12.8s - 13.4s
    regions = find_speech(probs)
    assert len(regions) == 3, regions
    utts = make_utterances(regions, merge_gap=0.6, max_len=12)
    assert len(utts) == 3, utts
    utts2 = make_utterances([SpeechRegion(0, 1), SpeechRegion(1.3, 2), SpeechRegion(2.4, 40)], max_len=12)
    assert utts2[0].start == 0 and utts2[0].end == 2 and all(u.duration <= 18 for u in utts2), utts2
    from app.core.asr.openai_asr import split_terms
    assert split_terms("AWP, Mirage，rush B;eco\nclutch, AWP") == ["AWP", "Mirage", "rush B", "eco", "clutch"]
    from app.core.subtitle.sentences import split_sentences
    assert split_sentences("Hello there. How are you? Fine!") == ["Hello there.", "How are you?", "Fine!"]
    assert split_sentences("没有句号的文字") == ["没有句号的文字"]
    chunks = make_chunks(regions, max_chunk=90, split_gap=2.0, min_chunk=3.0)
    assert len(chunks) == 2, chunks        # 前两段合并，第三段因停顿 6 秒且已够长而切开
    assert chunks[0].start < 0.4 and chunks[1].start > 12
    # 超长不停顿 → 硬切
    long = make_chunks([SpeechRegion(0, 300)], max_chunk=90)
    assert len(long) >= 3 and all(c.duration <= 108 for c in long)
    print("VAD 切块逻辑：OK")


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_vad_model() -> None:
    vad = SileroVad()
    for name in ("tts_en.wav", "tts_ja.wav"):
        audio = extract_pcm(FIXTURES / name)
        regions, chunks = detect_chunks(audio, vad)
        print(f"  {name} 检测到说话段：", [(round(r.start, 2), round(r.end, 2)) for r in regions])
        assert regions, f"Silero 没有在 {name} 里检测到说话"
        assert chunks and chunks[0].start < 1.0
    silence = np.zeros(SAMPLE_RATE * 5, dtype=np.float32)
    r2, _ = detect_chunks(silence, vad)
    assert not r2, "纯静音不应检测到说话"
    print("Silero VAD 模型：OK")


def test_sentences() -> None:
    segs = [
        Segment(0, 1, "今日は"), Segment(1, 2.2, "いい天気ですね。"), Segment(2.3, 4, "明日も"),
        Segment(4.1, 5, "晴れるでしょう"), Segment(9, 10, "では"), Segment(10, 11, "また。"),
    ]
    lines = merge_into_sentences(segs)
    assert [ln.source for ln in lines] == ["今日はいい天気ですね。", "明日も晴れるでしょう", "ではまた。"], [ln.source for ln in lines]
    assert lines[1].start == 2.3 and lines[1].end == 5
    en = [Segment(0, 1, "Hello there"), Segment(1, 2, "how are you?"), Segment(2, 3, "Fine.")]
    lines = merge_into_sentences(en)
    assert [ln.source for ln in lines] == ["Hello there how are you?", "Fine."]
    long = [Segment(0, 10, "あ" * 30 + "、" + "い" * 30 + "。")]
    parts = split_long_lines(merge_into_sentences(long))
    assert len(parts) == 2 and abs(parts[0].end - parts[1].start) < 1e-6
    # 整块返回的多句话要按句拆开，「よし、」不能粘在上一句尾巴上
    multi = [Segment(0, 10, "みなさんこんにちは。今日はランクマッチをやっていきます。まず設定を確認しますね。よし、ゲームが始まりました。")]
    parts = split_long_lines(merge_into_sentences(multi))
    assert [p.source for p in parts] == ["みなさんこんにちは。", "今日はランクマッチをやっていきます。", "まず設定を確認しますね。", "よし、ゲームが始まりました。"], [p.source for p in parts]
    assert parts[0].start == 0 and abs(parts[-1].end - 10) < 1e-6
    print("整句合并 / 长句拆分：OK")


def test_srt_and_prompt() -> None:
    from app.core.subtitle.models import SubtitleLine
    lines = [SubtitleLine(0.5, 2.0, "こんにちは", "你好"), SubtitleLine(2.5, 4.0, "さようなら", "再见")]
    assert fmt_time(3661.5) == "01:01:01,500"
    srt = to_srt(lines, "bilingual")
    assert "1\n00:00:00,500 --> 00:00:02,000\nこんにちは\n你好" in srt
    assert "再见" not in to_srt(lines, "source_only")
    assert "こんにちは" not in to_srt(lines, "target_only")
    req = TranslateRequest(["a", "b"], "ja", "zh-Hans", context=["前"], glossary={"AWP": "AWP"}, scene="游戏 → CS2")
    assert "必须严格遵守" in system_prompt(req) and "AWP → AWP" in system_prompt(req)
    assert "1. a\n2. b" in user_prompt(req)
    assert parse_translations('{"translations": ["x", "y"]}', 2) == ["x", "y"]
    assert parse_translations("1. x\n2. y", 2) == ["x", "y"]
    try:
        parse_translations("1. x", 2)
        raise AssertionError("句数不符应报错")
    except ValueError:
        pass
    print("SRT / 提示词 / 结果解析：OK")


def test_pipeline(media: Path | None) -> None:
    with tempfile.TemporaryDirectory() as td:
        if media is None:
            media = FIXTURES / "tts_ja.wav"
        samples = extract_pcm(media)
        print(f"  抽出音频 {len(samples) / SAMPLE_RATE:.1f} 秒 来自 {media.name}")
        tr, tl = FakeTranscriber(), FakeTranslator()
        progress: list[tuple[int, str]] = []
        logs: list[str] = []
        pipe = VideoPipeline(Config(), tr, tl, progress=lambda p, s: progress.append((p, s)), log=logs.append)
        job = VideoJob(media_path=media, output_mode="bilingual", source_language="ja", target_language="zh-Hans",
                       corrections={"テスト": "試験"})
        lines = pipe.run(job)
        assert lines and all(ln.target.startswith("译：") for ln in lines)
        assert any("試験" in ln.source for ln in lines), "纠错规则没生效"
        assert progress[-1][0] == 100
        assert tl.requests and tl.requests[0].target_language == "zh-Hans"
        assert all(ln.start < ln.end for ln in lines)
        # 没有时间戳的模型：按一句话一块切，时间来自 VAD，顺序必须和时间一致
        tt = FakeTextTranscriber()
        lines_t = VideoPipeline(Config(), tt, FakeTranslator()).run(
            VideoJob(media_path=media, source_language="ja", utterance_gap=0.3))
        assert tt.calls >= 2, "应切成多块"
        starts = [ln.start for ln in lines_t]
        assert starts == sorted(starts), "并行识别后顺序乱了"
        assert all(ln.end > ln.start for ln in lines_t)
        print(f"  无时间戳模型：{tt.calls} 块 → {len(lines_t)} 句，时间顺序正确")
        # 仅原文：不应调用翻译
        tl2 = FakeTranslator()
        lines2 = VideoPipeline(Config(), FakeTranscriber(), tl2).run(VideoJob(media_path=media, output_mode="source_only"))
        assert lines2 and not tl2.requests and all(not ln.target for ln in lines2)
        # 取消
        ev = threading.Event()
        ev.set()
        try:
            VideoPipeline(Config(), FakeTranscriber(), FakeTranslator(), cancel=ev).run(VideoJob(media_path=media))
            raise AssertionError("应抛出 Cancelled")
        except Cancelled:
            pass
        print(f"流程（识别 {tr.calls} 块 → {len(lines)} 句 → 翻译 {len(tl.requests)} 批）：OK")


def test_errors() -> None:
    assert "找不到文件" in friendly_message(FileNotFoundError("x.mp4"))
    assert friendly_message(UserFacingError("自定义")) == "自定义"
    import openai
    from httpx2 import Request, Response
    resp = Response(401, request=Request("POST", "https://x"))
    assert "API Key" in friendly_message(openai.AuthenticationError("bad", response=resp, body=None))
    try:
        extract_pcm(Path("不存在的文件.mp4"))
        raise AssertionError
    except UserFacingError as e:
        assert "找不到" in str(e)
    print("错误提示：OK")


def main() -> int:
    media = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    test_vad_logic()
    test_vad_model()
    test_sentences()
    test_srt_and_prompt()
    test_errors()
    test_pipeline(media)
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
