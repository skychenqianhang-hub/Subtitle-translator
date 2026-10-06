"""字幕工程文件：把一次处理的结果（字幕行 + 设置）存成 JSON，放在视频旁边。
以后可以直接打开修改、重新导出，不用再识别翻译。"""
from __future__ import annotations

from app.i18n import tr

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.errors import UserFacingError
from app.core.subtitle.models import SubtitleLine

PROJECT_SUFFIX = ".字幕工程.json"


@dataclass
class SubtitleProject:
    media_path: str
    lines: list[SubtitleLine] = field(default_factory=list)
    source_language: str = "auto"
    target_language: str = "zh-Hans"
    scene: str = "通用"
    output_mode: str = "bilingual"
    subtitle_size: str = "medium"
    subtitle_margin_pct: int = 3
    asr_model: str = ""
    translate_model: str = ""
    style: dict = field(default_factory=dict)      # SubtitleStyle.to_dict()；空 = 用默认样式

    @property
    def path(self) -> Path:
        return project_path_for(self.media_path)

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else self.path
        data = asdict(self)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "SubtitleProject":
        p = Path(path)
        if not p.exists():
            raise UserFacingError(tr("找不到字幕工程文件：{0}", p))
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            lines = [SubtitleLine(**ln) for ln in data.pop("lines", [])]
            known = {f for f in cls.__dataclass_fields__}
            return cls(lines=lines, **{k: v for k, v in data.items() if k in known and k != "lines"})
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            raise UserFacingError(tr("字幕工程文件损坏，无法读取：{0}", e)) from e


def project_path_for(media_path: str | Path) -> Path:
    src = Path(media_path)
    return src.with_name(src.stem + PROJECT_SUFFIX)
