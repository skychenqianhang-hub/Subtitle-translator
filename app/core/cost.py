"""费用估算：识别按分钟、翻译按 token。价格是 2026-10 的官方标价（美元），模型列表不在表里的按 0 算并标注「未知」。"""
from __future__ import annotations

from dataclasses import dataclass, field

# 识别：美元 / 分钟
ASR_PRICE_PER_MINUTE = {
    "gpt-transcribe": 0.0045,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe-diarize": 0.006,
    "whisper-1": 0.006,
}
# 翻译：美元 / 百万 token（输入, 输出）
TRANSLATE_PRICE_PER_MTOK = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "gpt-6-astra": (10.0, 50.0),
    "gpt-6-luna": (0.1, 0.5),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
}
USD_TO_CNY = 7.1


@dataclass
class CostTracker:
    asr_model: str = ""
    asr_seconds: float = 0.0
    translate_model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    unknown: list[str] = field(default_factory=list)

    def add_asr(self, seconds: float) -> None:
        self.asr_seconds += max(0.0, seconds)

    def add_translate(self, input_tokens: int = 0, output_tokens: int = 0, cache_read_tokens: int = 0) -> None:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.cache_read_tokens += int(cache_read_tokens or 0)

    # ---------- 计算 ----------
    def asr_usd(self) -> float:
        price = ASR_PRICE_PER_MINUTE.get(self.asr_model)
        if price is None:
            if self.asr_model and self.asr_model not in self.unknown:
                self.unknown.append(self.asr_model)
            return 0.0
        return self.asr_seconds / 60 * price

    def translate_usd(self) -> float:
        price = TRANSLATE_PRICE_PER_MTOK.get(self.translate_model)
        if price is None:
            if self.translate_model and self.translate_model not in self.unknown:
                self.unknown.append(self.translate_model)
            return 0.0
        pin, pout = price
        normal_in = max(0, self.input_tokens - self.cache_read_tokens)
        return (normal_in * pin + self.cache_read_tokens * pin * 0.1 + self.output_tokens * pout) / 1_000_000

    def total_usd(self) -> float:
        return self.asr_usd() + self.translate_usd()

    def summary(self) -> str:
        parts = []
        a = self.asr_usd()
        if self.asr_seconds > 0:
            parts.append(f"识别 {self.asr_seconds / 60:.1f} 分钟 ≈ ${a:.4f}")
        t = self.translate_usd()
        if self.input_tokens or self.output_tokens:
            parts.append(f"翻译 {self.input_tokens + self.output_tokens:,} token ≈ ${t:.4f}")
        total = a + t
        text = "；".join(parts) if parts else "本次没有调用云端模型"
        if parts:
            text += f"；合计约 ${total:.4f}（约 ¥{total * USD_TO_CNY:.3f}）"
        if self.unknown:
            text += f"（{', '.join(self.unknown)} 不在价格表里，未计入）"
        return text
