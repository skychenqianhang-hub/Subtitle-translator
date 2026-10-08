"""软件设置的读写。

设置保存在用户配置目录 %APPDATA%\\SubTranslator\\config.json，
不放在项目文件夹里，避免 API Key 被提交到 git。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR_NAME = "SubTranslator"
CONFIG_VERSION = 4

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
# 术语表的列（和 glossary.GLOSSARY_LANGS 一一对应）
GLOSSARY_LANG_NAMES = {
    "en": "英语",
    "ja": "日语",
    "zh-Hans": "简体中文",
    "zh-Hant": "繁体中文",
    "ko": "韩语",
}
# 视频翻译的输出形式（可多选）
OUTPUT_KINDS = {
    "srt": "字幕文件（.srt）",
    "video": "带字幕的视频（.mp4）",
    "doc": "文档（.txt，完成后自动打开）",
}
# 输出内容：双语 / 仅译文 / 仅原文（仅原文 = 只做语音识别，不调用翻译）
OUTPUT_MODES = {
    "bilingual": "原文 + 译文（双语）",
    "target_only": "仅译文",
    "source_only": "仅原文（只识别，不翻译）",
}
# 译文风格（语气档位）：下拉框显示短名，旁边的说明写清楚适合什么。发给模型的具体要求在 translate/prompt.py
TONES = {
    "casual": "口语",
    "subtitle": "字幕",
    "semiformal": "半正式",
    "formal": "正式",
}
TONE_NOTES = {
    "casual": "照说话人的口气翻，短句，保留语气词；适合直播、聊天、游戏解说。",
    "subtitle": "影视字幕写法：简洁通顺、去掉口头禅；适合上传 B 站 / YouTube 的视频。",
    "semiformal": "通顺的书面口语，不用俚语和网络用语；适合讲座、访谈、新闻。",
    "formal": "书面语，句子完整规范，不带情绪色彩；适合会议、纪录片、公告。",
}
DEFAULT_TONE = {"realtime": "casual", "video": "subtitle"}


def default_download_dir() -> Path:
    videos = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Videos"
    return (videos if videos.exists() else Path.home()) / "字幕翻译器"


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
    realtime_tone: str = "casual"           # 译文风格档位，见 TONES
    # 视频翻译参数
    video_output_mode: str = "bilingual"
    video_tone: str = "subtitle"
    video_output_kinds: list[str] = field(default_factory=lambda: ["srt"])   # srt / video / doc，可多选
    video_subtitle_size: str = "medium"     # small / medium / large（烧进视频时的字号）
    video_subtitle_margin_pct: int = 3      # 字幕离底边的距离（画面高度百分比）
    open_editor_after_run: bool = True      # 处理完自动打开字幕编辑器
    download_dir: str = ""                  # 网址下载的保存位置；空 = 我的视频\字幕翻译器
    subtitle_style: dict = field(default_factory=dict)   # 默认字幕样式（SubtitleStyle.to_dict()），空 = 内置默认
    ui_language: str = ""                   # 界面语言 zh / ja / en；空 = 还没选过
    ui_theme: str = "light"                 # 界面配色，见 app/ui/theme.py 的 PALETTES
    # 界面
    last_mode: str = "realtime"      # "realtime" 或 "video"
    last_scene: str = "通用"         # 例如 "游戏 → Valorant"
    window_geometry: str = ""
    config_version: int = 4

    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def target_language_name(self) -> str:
        """目标语言的名字，按当前界面语言显示（简体中文 / Simplified Chinese / 簡体字中国語）。"""
        from app.i18n import tr
        return tr(TARGET_LANGUAGES.get(self.target_language, self.target_language))

    def effective_asr_model(self) -> str:
        return resolve_asr_model(self.asr_model, self.source_language)

    def effective_download_dir(self) -> Path:
        return Path(self.download_dir) if self.download_dir.strip() else default_download_dir()


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        # 全新安装：界面语言跟随系统
        from app.i18n import detect_system_language
        cfg = Config()
        cfg.ui_language = detect_system_language()
        return cfg
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
    if version < 4:
        old_kind = raw.get("video_output_kind", "srt")
        cfg.video_output_kinds = {"srt": ["srt"], "video": ["video"], "both": ["srt", "video"]}.get(old_kind, ["srt"])
    if cfg.realtime_tone not in TONES:
        cfg.realtime_tone = DEFAULT_TONE["realtime"]
    if cfg.video_tone not in TONES:
        cfg.video_tone = DEFAULT_TONE["video"]
    if not isinstance(cfg.video_output_kinds, list) or not cfg.video_output_kinds:
        cfg.video_output_kinds = ["srt"]
    if not cfg.ui_language:
        cfg.ui_language = "zh"              # 加入多语言之前的老用户：保持中文，不要突然变脸
    cfg.config_version = CONFIG_VERSION
    return cfg


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
