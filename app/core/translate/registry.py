"""翻译服务登记表：provider 名 → 适配器。新增服务只改这里。"""
from __future__ import annotations

from app.i18n import tr

from app.config import Config
from app.core.errors import UserFacingError
from app.core.translate.base import Translator


def create_translator(cfg: Config, provider: str | None = None, model: str | None = None) -> Translator:
    provider = provider or cfg.translate_provider
    model = model or cfg.translate_model
    if provider == "anthropic":
        from app.core.translate.anthropic_translate import AnthropicTranslator
        return AnthropicTranslator(model, cfg.anthropic_api_key)
    if provider == "openai":
        from app.core.translate.openai_translate import OpenAITranslator
        return OpenAITranslator(model, cfg.openai_api_key)
    raise UserFacingError(tr("不支持的翻译服务：{0}", provider))
