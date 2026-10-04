"""翻译器统一接口：一批原文句子 + 上下文 + 术语表 + 风格 → 译文。

新增一家翻译服务 = 新写一个继承 Translator 的类，并在 registry.py 里登记。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslateRequest:
    sentences: list[str]                 # 要翻译的句子（按顺序）
    source_language: str = "auto"        # "ja" / "en" / "auto"
    target_language: str = "zh-Hans"
    context: list[str] = field(default_factory=list)   # 前文（只用于理解，不要翻译）
    glossary: dict[str, str] = field(default_factory=dict)
    style: str = ""
    scene: str = ""


class Translator(ABC):
    provider: str = ""

    def __init__(self, model: str) -> None:
        self.model = model
        # 最近一次调用的用量：{"input": int, "output": int, "cache_read": int}，给费用估算用
        self.last_usage: dict[str, int] = {}

    @abstractmethod
    def translate(self, req: TranslateRequest) -> list[str]:
        """返回与 req.sentences 一一对应的译文列表（长度必须相同）。"""
