from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubtitleLine:
    start: float
    end: float
    source: str
    target: str = ""
