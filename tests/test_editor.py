"""字幕编辑器自检（offscreen）：表格编辑、叠加字幕、加入术语表、保存工程、工程读写。

运行：python -m tests.test_editor
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="subtranslator_editor_")
os.environ["APPDATA"] = _tmp

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import config as config_mod  # noqa: E402
from app.core.profiles.store import ProfileStore  # noqa: E402
from app.core.subtitle.ass import to_ass  # noqa: E402
from app.core.subtitle.style import PRESETS, SubtitleStyle, TextStyle, ass_style_line  # noqa: E402
from app.core.subtitle.models import SubtitleLine  # noqa: E402
from app.core.subtitle.project import SubtitleProject, project_path_for  # noqa: E402
from app.ui.subtitle_editor import SubtitleEditorWindow  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    cfg = config_mod.load_config()
    store = ProfileStore(Path(_tmp) / "profiles")

    media = Path(_tmp) / "sample.wav"
    shutil.copy(FIXTURES / "tts_ja.wav", media)
    lines = [
        SubtitleLine(0.0, 1.5, "みなさんこんにちは。", "大家好。"),
        SubtitleLine(2.0, 4.3, "今日はランクマッチをやっていきます。", "今天来打排位赛。"),
        SubtitleLine(4.8, 6.9, "まず設定を確認しますね。", "先检查一下设置。"),
    ]
    project = SubtitleProject(media_path=str(media), lines=lines, source_language="ja", scene="Valorant")

    # 1. 工程读写
    p = project.save()
    assert p == project_path_for(media) and p.exists()
    loaded = SubtitleProject.load(p)
    assert len(loaded.lines) == 3 and loaded.lines[1].target == "今天来打排位赛。" and loaded.scene == "Valorant"
    print("字幕工程读写：OK", p.name)

    # 2. 编辑器：表格内容、按时间定位、叠加字幕
    win = SubtitleEditorWindow(cfg, store, project)
    win.show()
    app.processEvents()
    assert win.table.rowCount() == 3 and win.table.item(1, win.COL_TARGET).text() == "今天来打排位赛。"
    assert win.line_index_at(3.0) == 1 and win.line_index_at(1.8) == -1
    win._on_position(3000)
    app.processEvents()
    assert win._current_row == 1 and win.table.currentRow() == 1
    assert win.box_target.text == "今天来打排位赛。" and win.box_source.text == "今日はランクマッチをやっていきます。"
    assert win.box_target.isVisible() and win.box_source.isVisible()
    win.mode.setCurrentIndex(win.mode.findData("target_only"))
    assert win.box_source.text == "" and not win.box_source.isVisible(), "仅译文时不应显示原文"
    assert config_mod.load_config().video_output_mode == "target_only", "显示设置应保存到全局设置"
    print("播放定位 / 画面字幕块 / 显示模式：OK")

    # 2b. 样式：面板改字号颜色 → 字幕块与工程跟着变；拖动字幕块 → 面板坐标跟着变；ASS 输出带样式
    win.mode.setCurrentIndex(win.mode.findData("bilingual"))
    pt = win.panel_target
    pt.size.setValue(24)
    pt._paint_button(pt.color, "#FFE34D"); pt._emit()
    pt.align.setCurrentIndex(pt.align.findData("left"))
    assert win.sub_style.target.size == 24 and win.sub_style.target.color == "#FFE34D" and win.sub_style.target.align == "left"
    assert win.project.style["target"]["size"] == 24
    frame = win.view.video_rect()
    win.box_target.setPos(frame.left() + frame.width() * 0.10, frame.top() + frame.height() * 0.50)
    assert abs(win.sub_style.target.x_pct - 10.0) < 1.0, win.sub_style.target.x_pct
    assert 50 < win.sub_style.target.y_pct < 75, win.sub_style.target.y_pct
    assert abs(pt.x.value() - win.sub_style.target.x_pct) < 0.2, "面板坐标应跟随拖动"
    win.box_source.wheelEvent(type("E", (), {"delta": lambda self: 120, "accept": lambda self: None})())
    assert win.sub_style.source.size == 14 and win.panel_source.size.value() == 14, "滚轮应改字号"
    ass = to_ass(lines, "bilingual", style=win.sub_style)
    target_line = next(l for l in ass.splitlines() if l.startswith("Style: Target,"))
    assert ",24,&H004DE3FF," in target_line, target_line   # 字体名随系统字体库变化，只查字号和颜色
    assert "{" + "\\" + "an1" + "\\" + "pos(" in ass, "左对齐应生成 \\an1 定位标签：" + ass[-300:]
    assert ass_style_line("X", TextStyle(back_alpha=70)).split(",")[15] == "3", "有底框时 BorderStyle 应为 3"
    win.preset.setCurrentIndex(win.preset.findData("黑底白字"))
    assert win.sub_style.target.back_alpha == 70 and pt.back_alpha.value() == 70
    win._set_default_style()
    assert config_mod.load_config().subtitle_style["target"]["back_alpha"] == 70, "默认样式应写入设置"
    assert SubtitleStyle.from_dict(config_mod.load_config().subtitle_style).target.back_alpha == 70
    assert set(PRESETS) >= {"默认（白字黑边）", "黄字黑边", "黑底白字", "大字"}
    print("样式面板 / 拖动 / 预设 / 默认样式：OK")

    # 3. 修改译文 → 内存里的字幕行跟着变，保存后工程文件更新
    win.table.item(1, win.COL_TARGET).setText("今天打排位。")
    assert lines[1].target == "今天打排位。" and win._dirty
    win.save_project()
    reloaded = SubtitleProject.load(p)
    assert reloaded.lines[1].target == "今天打排位。" and not win._dirty
    assert reloaded.style["target"]["back_alpha"] == 70, "样式应随工程保存"
    print("表格修改与保存：OK")

    # 4. 加入术语表 / 纠错规则（绕过对话框直接走数据）
    win._pair_dialog = lambda *a, **k: ("ランクマッチ", "排位赛")
    win.table.selectRow(1)
    win._add_to_glossary()
    assert store.get("Valorant").glossary["ランクマッチ"] == "排位赛"
    win._pair_dialog = lambda *a, **k: ("ランクマッチ", "ランクマッチ（排位）")
    win._add_correction()
    assert store.get("Valorant").corrections["ランクマッチ"] == "ランクマッチ（排位）"
    print("一键加入术语表 / 纠错：OK")

    # 5. 导出 SRT（绕过文件对话框）
    from PySide6.QtWidgets import QFileDialog
    out = Path(_tmp) / "out.srt"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), ""))
    win.mode.setCurrentIndex(win.mode.findData("target_only"))
    win._export_srt()
    text = out.read_text(encoding="utf-8-sig")
    assert "今天打排位。" in text and "ランクマッチ" not in text, "仅译文模式导出不应含原文"
    print("从编辑器导出 SRT：OK")

    win.close()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
