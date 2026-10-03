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
CONFIG_VERSION = 3

# ---- 识别模型（2026-10-03 按公开评测整理，见 PLAN.md 阶段 2 备注）----
# 下拉框显示 label，保存 id。"auto" = 按原文语言自动选
ASR_AUTO = "auto"
ASR_MODELS: list[tuple[str, str]] = [
    (ASR_AUTO, "自动：日语用 gpt-4o-transcribe，英语用 gpt-transcribe（推荐）"),
    ("gpt-4o-transcribe", "gpt-4o-transcribe：日语最准（日语测试第一），$0.006/分钟"),
    ("gpt-transcribe", "gpt-transcribe：英语最准（综合榜第一），$0.0045/分钟"),
    ("gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe：最便宜 $0.003/分钟，准确率略低"),
    ("whisper-1", "whisper-1：时间戳最精细，$0.006/分钟，日语偏弱"),
]
ASR_DEFAULT_BY_LANGUAGE = {"ja": "gpt-4o-transcribe", "en": "gpt-transcribe", "zh": "gpt-4o-transcribe",
                           "ko": "gpt-4o-transcribe"}
ASR_DEFAULT_FALLBACK = "gpt-transcribe"


def resolve_asr_model(model: str, source_language: str) -> str:
    """把 "auto" 换成该语言的默认识别模型。"""
    if model and model != ASR_AUTO:
        return model
    return ASR_DEFAULT_BY_LANGUAGE.get(source_language, ASR_DEFAULT_FALLBACK)


# ---- 翻译模型 ----
TRANSLATE_PROVIDERS = {
    "anthropic": "Claude（Anthropic）",
    "openai": "GPT（OpenAI）",
}
TRANSLATE_MODELS: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("claude-sonnet-5-5", "Claude Sonnet 5.5：推荐，$2/$10，一小时视频约 3 毛"),
        ("claude-opus-5-5", "Claude Opus 5.5：质量最高，$4/$20，一小时视频约 6 毛"),
        ("claude-haiku-4-5", "Claude Haiku 4.5：便宜但质量低一档，不推荐"),
    ],
    "openai": [
        ("gpt-6.1-sol", "GPT-6.1 Sol：OpenAI 主力，$2/$10，和 Sonnet 5.5 同价"),
        ("gpt-6-astra", "GPT-6 Astra：OpenAI 最强，$10/$50，很贵"),
        ("gpt-5-mini", "GPT-5 mini：便宜但质量低一档，不推荐"),
    ],
}
DEFAULT_TRANSLATE_MODEL = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-6.1-sol"}


def model_label(provider_models: list[tuple[str, str]], model_id: str) -> str:
    for mid, label in provider_models:
        if mid == model_id:
            return label
    return model_id

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
    asr_model: str = "auto"              # "auto" 或具体模型 id
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
    config_version: int = 3

    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def target_language_name(self) -> str:
        return TARGET_LANGUAGES.get(self.target_language, self.target_language)

    def effective_asr_model(self) -> str:
        return resolve_asr_model(self.asr_model, self.source_language)


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
    # 旧版本设置文件升级（只按版本号升级一次，用户手动改过的不动）
    version = int(raw.get("config_version", 1) or 1)
    if version < 2:
        if cfg.asr_model == "whisper-1":
            cfg.asr_model = "gpt-transcribe"
        if cfg.translate_model in ("claude-opus-5", "claude-sonnet-5", "gpt-4o", "gpt-4o-mini"):
            cfg.translate_model = DEFAULT_TRANSLATE_MODEL.get(cfg.translate_provider, cfg.translate_model)
    if version < 3:
        if cfg.asr_model == "gpt-transcribe":          # 旧默认 → 按语言自动
            cfg.asr_model = ASR_AUTO
        if cfg.translate_model in ("gpt-5", "gpt-4.1"):
            cfg.translate_model = "gpt-6.1-sol"
    cfg.config_version = CONFIG_VERSION
    return cfg


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
