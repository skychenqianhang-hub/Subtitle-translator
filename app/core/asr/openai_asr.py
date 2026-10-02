"""OpenAI 语音识别适配器。

三类模型，接口参数不一样：
- whisper-1：有逐句时间戳（verbose_json），language 单数，prompt 提示词
- gpt-transcribe：没有时间戳，languages 复数列表，keywords 关键词列表，prompt 是「关于录音的描述」
- gpt-4o-transcribe / gpt-4o-mini-transcribe：没有时间戳，只支持 json，language 单数，prompt 提示词
没有时间戳的模型，由流程把音频按「一句话一块」切好再送，时间用块的起止。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.asr.base import Segment, Transcriber
from app.core.errors import UserFacingError

_VERBOSE_MODELS = ("whisper-1",)
_KEYWORD_MODELS = ("gpt-transcribe",)
_PUNCT_LEAD = {
    "ja": "こんにちは、今日もよろしくお願いします。",
    "en": "Hello, and welcome back. Let's get started.",
    "zh": "大家好，今天我们开始吧。",
    "ko": "안녕하세요, 오늘도 시작하겠습니다.",
}


def split_terms(text: str) -> list[str]:
    """把「AWP, Mirage, rush B」这种提示拆成关键词列表。"""
    parts = re.split(r"[,，;；\n]+", text or "")
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen and "<" not in p and ">" not in p:
            seen.append(p)
    return seen


class OpenAITranscriber(Transcriber):
    provider = "openai"

    def __init__(self, model: str, api_key: str, timeout: float = 120.0) -> None:
        super().__init__(model)
        if not api_key:
            raise UserFacingError("还没有填 OpenAI 的 API Key。请到右上角「设置 → API Key」填写。")
        import openai
        self.client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=3)

    @property
    def has_timestamps(self) -> bool:
        return self.model in _VERBOSE_MODELS

    def transcribe(self, wav_path: Path, language: str | None = None, prompt: str = "") -> list[Segment]:
        lang = language if language and language != "auto" else None
        kwargs: dict = {"model": self.model}

        if self.model.startswith(_KEYWORD_MODELS):
            if lang:
                kwargs["languages"] = [lang]
            terms = split_terms(prompt)
            if terms:
                kwargs["keywords"] = terms[:100]
        else:
            if lang:
                kwargs["language"] = lang
            terms = ", ".join(split_terms(prompt))
            # whisper 会模仿提示词的风格：给一句带标点的提示，它才会输出标点（日语尤其需要）
            lead = _PUNCT_LEAD.get(lang or "", "")
            full = f"{lead} {terms}".strip() if (lead or terms) else ""
            if full:
                kwargs["prompt"] = full[:800]

        with open(wav_path, "rb") as f:
            if self.has_timestamps:
                resp = self.client.audio.transcriptions.create(
                    file=f, response_format="verbose_json", timestamp_granularities=["segment"], **kwargs
                )
                return _from_verbose(resp)
            resp = self.client.audio.transcriptions.create(file=f, response_format="json", **kwargs)
            text = (getattr(resp, "text", "") or "").strip()
            if not text:
                return []
            return [Segment(0.0, -1.0, text)]   # 没有时间戳：由流程按块起止填时间


def _from_verbose(resp) -> list[Segment]:
    out: list[Segment] = []
    for s in getattr(resp, "segments", None) or []:
        text = (s.text or "").strip()
        if not text:
            continue
        # Whisper 对静音 / 音乐段会瞎编；no_speech_prob 高且置信度低的丢掉
        no_speech = getattr(s, "no_speech_prob", 0.0) or 0.0
        logprob = getattr(s, "avg_logprob", 0.0) or 0.0
        if no_speech > 0.85 and logprob < -1.0:
            continue
        out.append(Segment(float(s.start), float(s.end), text))
    return out
