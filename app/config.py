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
CONFIG_VERSION = 2

# 可选的模型列表（界面下拉框用；用户也可以手动输入其他名称）
ASR_MODELS = ["gpt-transcribe", "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"]
TRANSLATE_PROVIDERS = {
    "anthropic": "Claude（Anthropic）",
    "openai": "GPT（OpenAI）",
}
TRANSLATE_MODELS = {
    "anthropic": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-4-5"],
    "openai": ["gpt-5", "gpt-5-mini", "gpt-4.1"],
}
DEFAULT_TRANSLATE_MODEL = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5"}
# 原文语言（语音识别用）
SOURCE_LANGUAGES = {
    "auto": "自动检测",
    "ja": "日语",
    "en": "英语",
    "zh": "中文",
    "ko": "韩语",
}
# 翻译至（目标语言）
TARGET_LANGUAGES = {
    "zh-Hans": "简体中文",
    "zh-Hant": "繁体中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
}
# 视频翻译的输出形式
OUTPUT_KINDS = {
    "srt": "仅字幕文件（.srt）",
    "video": "带字幕的视频（.mp4）",
    "both": "两者都要",
}
# 输出内容：双语 / 仅译文 / 仅原文（仅原文 = 只做语音识别，不调用翻译）
OUTPUT_MODES = {
    "bilingual": "原文 + 译文（双语）",
    "target_only": "仅译文",
    "source_only": "仅原文（只识别，不翻译）",
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
    # 模型（主页上选择，实时 / 视频两页共用）
    asr_provider: str = "openai"
    asr_model: str = "gpt-transcribe"
    translate_provider: str = "anthropic"
    translate_model: str = "claude-sonnet-5-5"
    # 语言
    source_language: str = "auto"
    target_language: str = "zh-Hans"
    # 悬浮字幕窗
    overlay_font_size: int = 28
    # 实时翻译参数
    realtime_delay_seconds: int = 5
    audio_device_name: str = ""
    realtime_output_mode: str = "bilingual"
    # 视频翻译参数
    video_output_mode: str = "bilingual"
    video_output_kind: str = "srt"          # srt / video / both
    video_subtitle_size: str = "medium"     # small / medium / large（烧进视频时的字号）
    # 界面
    last_mode: str = "realtime"      # "realtime" 或 "video"
    last_scene: str = "通用"         # 例如 "游戏 → Valorant"
    window_geometry: str = ""
    config_version: int = 2

    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def target_language_name(self) -> str:
        return TARGET_LANGUAGES.get(self.target_language, self.target_language)


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Config()
    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in raw.items() if k in known})
    # 兼容旧版本的名字
    if raw.get("last_mode") == "offline":
        cfg.last_mode = "video"
    if "offline_output_mode" in raw and "video_output_mode" not in raw:
        cfg.video_output_mode = raw["offline_output_mode"]
    # 2026-10-03 更换默认模型：只对旧版本（没有 config_version）的设置文件升级一次
    if "config_version" not in raw:
        if cfg.asr_model == "whisper-1":
            cfg.asr_model = "gpt-transcribe"
        if cfg.translate_model in ("claude-opus-5", "claude-sonnet-5", "gpt-4o", "gpt-4o-mini"):
            cfg.translate_model = DEFAULT_TRANSLATE_MODEL.get(cfg.translate_provider, cfg.translate_model)
        cfg.config_version = CONFIG_VERSION
    return cfg


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
