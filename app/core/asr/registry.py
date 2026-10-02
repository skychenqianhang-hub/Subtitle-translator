"""识别服务登记表：provider 名 → 适配器。新增服务只改这里。"""
from __future__ import annotations

from app.config import Config
from app.core.asr.base import Transcriber
from app.core.errors import UserFacingError


def create_transcriber(cfg: Config, provider: str | None = None, model: str | None = None) -> Transcriber:
    provider = provider or cfg.asr_provider
    model = model or cfg.asr_model
    if provider == "openai":
        from app.core.asr.openai_asr import OpenAITranscriber
        return OpenAITranscriber(model, cfg.openai_api_key)
    raise UserFacingError(f"不支持的识别服务：{provider}")
