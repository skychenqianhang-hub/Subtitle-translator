"""识别器统一接口：音频 → 带时间戳的原文片段。

新增一家识别服务 = 新写一个继承 Transcriber 的类，并在 registry.py 里登记。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float   # 秒，相对整个文件
    end: float
    text: str


class Transcriber(ABC):
    provider: str = ""

    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def has_timestamps(self) -> bool:
        """True：返回的片段自带时间；False：流程要按「一句话一块」切好再送。"""
        return True

    @abstractmethod
    def transcribe(
        self,
        wav_path: Path,
        language: str | None = None,   # "ja" / "en" / None=自动
        prompt: str = "",              # 专有名词提示
    ) -> list[Segment]:
        """识别一个 wav 文件，返回片段（时间相对该文件开头）。"""
