"""OpenAI GPT 翻译适配器。"""
from __future__ import annotations

from app.core.errors import UserFacingError
from app.core.translate.base import TranslateRequest, Translator
from app.core.translate.prompt import OUTPUT_SCHEMA, parse_translations, system_prompt, user_prompt


class OpenAITranslator(Translator):
    provider = "openai"

    def __init__(self, model: str, api_key: str, timeout: float = 180.0) -> None:
        super().__init__(model)
        if not api_key:
            raise UserFacingError("还没有填 OpenAI 的 API Key。请到右上角「设置 → API Key」填写。")
        import openai
        self.client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=3)

    def translate(self, req: TranslateRequest) -> list[str]:
        if not req.sentences:
            return []
        system = system_prompt(req)
        user = user_prompt(req)
        last_error: Exception | None = None
        for attempt in range(2):
            content = user
            if attempt == 1 and last_error:
                content += (
                    f"\n\n注意：上一次返回的句数不对（{last_error}）。"
                    f"必须恰好返回 {len(req.sentences)} 条译文，顺序与编号一致。"
                )
            extra: dict = {}
            if self.model.startswith("gpt-5"):
                extra["reasoning_effort"] = "low"   # 字幕翻译不需要长时间思考，省钱也更快
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "translations", "schema": OUTPUT_SCHEMA, "strict": True},
                },
                **extra,
            )
            text = resp.choices[0].message.content or ""
            try:
                return parse_translations(text, len(req.sentences))
            except ValueError as e:
                last_error = e
        raise UserFacingError(f"翻译结果对不上句数，已重试一次仍失败：{last_error}")
