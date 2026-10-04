"""Anthropic Claude 翻译适配器。"""
from __future__ import annotations

from app.core.errors import UserFacingError
from app.core.translate.base import TranslateRequest, Translator
from app.core.translate.prompt import OUTPUT_SCHEMA, parse_translations, system_prompt, user_prompt


class AnthropicTranslator(Translator):
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, timeout: float = 180.0) -> None:
        super().__init__(model)
        if not api_key:
            raise UserFacingError("还没有填 Anthropic 的 API Key。请到右上角「设置 → API Key」填写。")
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=3)

    def translate(self, req: TranslateRequest) -> list[str]:
        if not req.sentences:
            return []
        system = system_prompt(req)
        user = user_prompt(req)
        last_error: Exception | None = None
        for attempt in range(2):
            messages = [{"role": "user", "content": user}]
            if attempt == 1 and last_error:
                messages[0]["content"] += (
                    f"\n\n注意：上一次返回的句数不对（{last_error}）。"
                    f"必须恰好返回 {len(req.sentences)} 条译文，顺序与编号一致。"
                )
            with self.client.messages.stream(
                model=self.model,
                max_tokens=8000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            ) as stream:
                resp = stream.get_final_message()
            u = getattr(resp, "usage", None)
            self.last_usage = {
                "input": int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0)
                         + int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                "output": int(getattr(u, "output_tokens", 0) or 0),
                "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0),
            } if u else {}
            if resp.stop_reason == "refusal":
                raise UserFacingError("Claude 拒绝翻译这段内容（触发了安全策略）。可以换 GPT 试试。")
            text = next((b.text for b in resp.content if b.type == "text"), "")
            try:
                return parse_translations(text, len(req.sentences))
            except ValueError as e:
                last_error = e
        raise UserFacingError(f"翻译结果对不上句数，已重试一次仍失败：{last_error}")
