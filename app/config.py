"""软件设置的读写。

设置保存在用户配置目录 %APPDATA%\\SubTranslator\\config.json，
不放在项目文件夹里，避免 API Key 被提交到 git。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_DIR_NAME = "SubTranslator"

# 可选的模型列表（界面下拉框用；用户也可以手动输入其他名称）
ASR_MODELS = ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"]
TRANSLATE_PROVIDERS = {
    "anthropic": "Claude（Anthropic）",
    "openai": "GPT（OpenAI）",
}
TRANSLATE_MODELS = {
    "anthropic": ["claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-opus-5"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
}
SOURCE_LANGUAGES = {
    "auto": "自动检测",
    "ja": "日语",
    "en": "英语",
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Config:
    # API Key
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # 默认模型
    asr_provider: str = "openai"
    asr_model: str = "whisper-1"
    translate_provider: str = "anthropic"
    translate_model: str = "claude-sonnet-5"
    # 语言
    source_language: str = "auto"
    # 悬浮字幕窗
    overlay_font_size: int = 28
    overlay_show_source: bool = False
    # 实时翻译参数
    realtime_delay_seconds: int = 5
    audio_device_name: str = ""
    # 界面
    last_mode: str = "realtime"      # "realtime" 或 "offline"
    last_scene: str = "通用"         # 例如 "游戏 → Valorant"
    window_geometry: str = ""

    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Config()
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in raw.items() if k in known})


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
