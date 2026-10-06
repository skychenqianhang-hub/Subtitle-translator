"""界面多语言自检：翻译表齐不齐、占位符对不对、英文 / 日文界面里有没有漏翻的中文。

运行：python -m tests.test_i18n
加 --shots 文件夹 会把三种语言的主窗口、设置窗口截图存进去，方便人工看排版。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import string
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="subtranslator_test_")
os.environ["APPDATA"] = _tmp

from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QFontComboBox, QGroupBox,  # noqa: E402
                               QHeaderView, QLabel, QLineEdit,QTabWidget, QWidget)

from app import config as config_mod  # noqa: E402
from app import i18n  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HAN = re.compile(r"[㐀-鿿]")
KANA = re.compile(r"[぀-ヿ]")


def source_keys() -> list[str]:
    """用开发工具同一套规则，从代码里取出所有需要翻译的文字。"""
    spec = importlib.util.spec_from_file_location("i18n_wrap", ROOT / "tools_dev" / "i18n_wrap.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    keys: list[str] = []
    for rel in tool.FILES:
        keys.extend(tool.extract_wrapped(ROOT / rel))
    for rel in tool.EXTRACT_CONSTANTS_FROM:
        keys.extend(tool.extract_constants(ROOT / rel))
    for rel in tool.EXTRACT_MODULE_CONSTANTS_FROM:
        keys.extend(tool.extract_module_constants(ROOT / rel))
    # 只有含中文的才是界面文字（正则表达式之类的不算）
    return [k for k in dict.fromkeys(keys) if HAN.search(k) and not k.startswith("[")]


def fields_of(template: str) -> list[str]:
    """模板里的占位符，连同格式一起（{0:.1f} 和 {0} 算不同）。"""
    return sorted(f"{name}!{conv or ''}:{spec or ''}" for _, name, spec, conv in string.Formatter().parse(template)
                  if name is not None)


def check_tables() -> None:
    keys = source_keys()
    assert len(keys) > 300, len(keys)
    for lang in ("en", "ja"):
        table = json.loads((ROOT / "app" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in keys if not table.get(k)]
        assert not missing, f"{lang} 缺 {len(missing)} 条翻译：{missing[:8]}"
        for key, value in table.items():
            try:
                a, b = fields_of(key), fields_of(value)
            except ValueError as e:
                raise AssertionError(f"{lang} 花括号写错：{key!r} → {value!r}（{e}）") from None
            assert a == b, f"{lang} 占位符对不上：{key!r} → {value!r}"
        if lang == "en":
            # 「.字幕工程.json」是真实的文件后缀，不能翻
            leftovers = [k for k, v in table.items() if HAN.search(v.replace(".字幕工程.json", ""))]
            assert not leftovers, f"英文翻译里还有中文：{leftovers[:5]}"
        print(f"翻译表 {lang}：{len(table)} 条，代码里的 {len(keys)} 条全部覆盖，占位符一致")


def visible_texts(root: QWidget) -> list[str]:
    out: list[str] = []
    for w in [root] + root.findChildren(QWidget):
        if w.objectName() in ("language_button", "device_combo") or isinstance(w, QFontComboBox):
            continue               # 语言下拉框写各语言自己的名字；设备名是 Windows 给的，不归我们翻
        out.append(w.toolTip())
        out.append(w.windowTitle())
        if isinstance(w, (QLabel, QAbstractButton)):
            out.append(w.text())
        elif isinstance(w, QGroupBox):
            out.append(w.title())
        elif isinstance(w, QLineEdit):
            out.append(w.placeholderText())
        elif isinstance(w, QComboBox):
            out.extend(w.itemText(i) for i in range(w.count()))
        elif isinstance(w, QTabWidget):
            out.extend(w.tabText(i) for i in range(w.count()))
        elif isinstance(w, QHeaderView) and w.model() is not None:
            out.extend(str(w.model().headerData(i, w.orientation()) or "") for i in range(w.count()))
    return [t for t in out if t and "\\" not in t]      # 带反斜杠的是文件夹路径，不是界面文字


def check_ui(app: QApplication, shots: Path | None) -> None:
    from app.ui.main_window import MainWindow

    for lang, video_label, gear_tip in (("zh", "视频翻译", "设置（API Key、场景管理）"),
                                        ("en", "Video", "Settings (API keys, scenes)"),
                                        ("ja", "動画翻訳", "設定（API キー、シーン管理）")):
        i18n.set_language(lang)
        cfg = config_mod.Config()
        win = MainWindow(cfg)
        win.show()
        app.processEvents()
        table = i18n.load_table(lang)
        assert win.mode_buttons["video"].text() == (table.get("视频翻译") or "视频翻译"), win.mode_buttons["video"].text()
        assert win.settings_button.toolTip() == (table.get("设置（API Key、场景管理）") or gear_tip)
        assert win.language_actions[lang].isChecked() and not win.language_actions["en" if lang != "en" else "ja"].isChecked()
        assert [a.text() for a in win.language_menu.actions()] == ["中文", "日本語", "English"]
        # 场景：内部名字不变（存盘、找术语都靠它），显示的名字跟着语言走
        scene = win.realtime_page.scene
        assert scene.section.findData("游戏") >= 0 and scene.section.findData("通用") >= 0
        shown = scene.section.itemText(scene.section.findData("游戏"))
        assert shown == {"zh": "游戏", "en": table.get("游戏"), "ja": table.get("游戏")}[lang], shown
        assert win.store.resolve("Valorant").glossary.get("Jett") == "捷风"
        texts = []
        for mode in ("realtime", "video"):
            win.mode_buttons[mode].click()
            app.processEvents()
            texts += visible_texts(win)
            if shots:
                win.grab().save(str(shots / f"{lang}_{mode}.png"))
        win.settings_button.click()
        dlg = win.settings_dialog
        for tab in range(dlg.tabs.count()):
            dlg.tabs.setCurrentIndex(tab)
            app.processEvents()
            texts += visible_texts(dlg)
            if shots:
                dlg.grab().save(str(shots / f"{lang}_settings{tab}.png"))
        # 字幕编辑器（带两句字幕的工程）
        from app.core.subtitle.models import SubtitleLine
        from app.core.subtitle.project import SubtitleProject
        from app.ui.subtitle_editor import SubtitleEditorWindow
        project = SubtitleProject(media_path="", source_language="ja", scene="Valorant",
                                  lines=[SubtitleLine(0.0, 2.0, "こんにちは", "Hello"),
                                         SubtitleLine(2.0, 4.0, "ランクマッチ", "Ranked match")])
        editor = SubtitleEditorWindow(cfg, win.store, project)
        editor.show()
        app.processEvents()
        texts += visible_texts(editor)
        if shots:
            editor.grab().save(str(shots / f"{lang}_editor.png"))
        editor._dirty = False
        editor.close()
        if lang == "en":
            left = sorted({t for t in texts if HAN.search(t.replace(".字幕工程.json", ""))})
            assert not left, f"英文界面里还有 {len(left)} 处中文：{left[:10]}"
        if lang == "ja":
            # 日文本来就用汉字，只能查「和中文原文一模一样、而且翻译表里有不同译文」的
            same = sorted({t for t in texts if t in table and table[t] != t})
            assert not same, f"日文界面里有没翻的：{same[:10]}"
            assert any(KANA.search(t) for t in texts)
        dlg.hide()
        win.close()
        print(f"界面 {lang}：OK（检查了 {len(texts)} 处文字）")
    i18n.set_language("zh")


def check_misc() -> None:
    # 没有的语言 → 回退中文；占位符；译文缺失 → 原样返回
    assert i18n.set_language("fr") == "zh"
    assert i18n.tr("已保存：{0}", "a.srt") == "已保存：a.srt"
    i18n.set_language("en")
    assert i18n.tr("已保存：{0}", "a.srt") == "Saved: a.srt", i18n.tr("已保存：{0}", "a.srt")
    assert i18n.tr("这句话翻译表里没有") == "这句话翻译表里没有"
    assert i18n.tr_in("ja", "切换界面语言") == "表示言語の切り替え"
    from app.core.cost import CostTracker
    tracker = CostTracker()
    assert not HAN.search(tracker.summary()), tracker.summary()
    cfg = config_mod.Config()
    assert cfg.target_language_name() == "Simplified Chinese", cfg.target_language_name()
    i18n.set_language("zh")
    assert cfg.target_language_name() == "简体中文"
    # 设置文件：全新安装跟随系统；老用户（文件里没有这一项）保持中文；选过的记住
    assert config_mod.load_config().ui_language == i18n.detect_system_language()
    config_mod.save_config(config_mod.Config())
    raw = json.loads(config_mod.config_path().read_text(encoding="utf-8"))
    raw.pop("ui_language")
    config_mod.config_path().write_text(json.dumps(raw), encoding="utf-8")
    assert config_mod.load_config().ui_language == "zh"
    cfg = config_mod.load_config()
    cfg.ui_language = "ja"
    config_mod.save_config(cfg)
    assert config_mod.load_config().ui_language == "ja"
    config_mod.config_path().unlink()
    print("回退 / 占位符 / 设置文件：OK")


def main() -> int:
    shots = None
    if "--shots" in sys.argv:
        shots = Path(sys.argv[sys.argv.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    check_tables()
    check_misc()
    check_ui(app, shots)
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
