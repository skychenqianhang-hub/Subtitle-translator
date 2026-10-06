"""识别服务登记表：provider 名 → 适配器。新增服务只改这里。"""
from __future__ import annotations

from app.i18n import tr

from app.config import Config, resolve_asr_model
from app.core.asr.base import Transcriber
from app.core.errors import UserFacingError


def create_transcriber(cfg: Config, provider: str | None = None, model: str | None = None,
                       source_language: str | None = None) -> Transcriber:
    provider = provider or cfg.asr_provider
    model = resolve_asr_model(model or cfg.asr_model, source_language or cfg.source_language)
    if provider == "openai":
        from app.core.asr.openai_asr import OpenAITranscriber
        return OpenAITranscriber(model, cfg.openai_api_key)
    raise UserFacingError(tr("不支持的识别服务：{0}", provider))
