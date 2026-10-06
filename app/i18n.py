"""界面多语言。

写法：代码里直接写中文，外面包一层 tr()：
    tr("开始处理")                      → 按当前界面语言返回对应文字
    tr("已保存：{0}（{1} 条）", name, n)  → 先翻译模板，再把参数填进去
中文是「源语言」，同时也是翻译表的键；某个语言没有对应翻译时回退到中文，不会报错。
翻译表在 app/locales/<语言>.json，格式 {"中文原文": "译文"}。

界面语言在程序启动时设定一次（main() 里，读完设置之后、加载界面模块之前），
切换语言需要重启程序。自动测试不经过 main()，所以始终是中文。
"""
from __future__ import annotations

import json
import locale
import sys
from pathlib import Path

LANGUAGES = {"zh": "中文", "ja": "日本語", "en": "English"}   # 下拉框里显示各语言自己的写法
DEFAULT_LANGUAGE = "zh"

_current = DEFAULT_LANGUAGE
_table: dict[str, str] = {}


def _locales_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "locales"


def load_table(lang: str) -> dict[str, str]:
    if lang == "zh":
        return {}
    path = _locales_dir() / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, json.JSONDecodeError):
        return {}


def set_language(lang: str) -> str:
    """设定界面语言，返回实际生效的语言代码。"""
    global _current, _table
    if lang not in LANGUAGES:
        lang = DEFAULT_LANGUAGE
    _current = lang
    _table = load_table(lang)
    return lang


def current_language() -> str:
    return _current


def detect_system_language() -> str:
    """按 Windows 的显示语言猜：中文系统 → zh，日文系统 → ja，其他 → en。"""
    code = ""
    try:
        import ctypes
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        code = locale.windows_locale.get(lcid, "") or ""
    except Exception:  # noqa: BLE001
        pass
    if not code:
        try:
            code = (locale.getlocale()[0] or "")
        except Exception:  # noqa: BLE001
            code = ""
    code = code.lower()
    if code.startswith(("zh", "chinese")):
        return "zh"
    if code.startswith(("ja", "japanese")):
        return "ja"
    return "en"


def tr_in(lang: str, text: str, *args) -> str:
    """不改变当前语言，用指定语言翻译一句。"""
    out = load_table(lang).get(text, text) if lang != "zh" else text
    try:
        return out.format(*args) if args else out
    except (IndexError, KeyError, ValueError):
        return text.format(*args) if args else text


def tr(text: str, *args) -> str:
    """翻译一段界面文字。有参数时按 str.format 的位置参数填入。"""
    out = _table.get(text, text) if _table else text
    if args:
        try:
            return out.format(*args)
        except (IndexError, KeyError, ValueError):
            try:
                return text.format(*args)      # 译文的占位符写错了：退回中文模板
            except (IndexError, KeyError, ValueError):
                return out
    return out
