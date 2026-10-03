"""阶段 1 骨架自检：不需要显示器，用 offscreen 模式跑。

运行：python -m tests.test_skeleton
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 把设置目录指到临时文件夹，不碰用户真实的 config.json
_tmp = tempfile.mkdtemp(prefix="subtranslator_test_")
os.environ["APPDATA"] = _tmp

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config as config_mod  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.settings_dialog import SettingsDialog  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = config_mod.load_config()
    win = MainWindow(cfg)
    win.show()
    rp, vp = win.realtime_page, win.video_page

    # 1. 两个模式能切换，并记住
    assert win.current_mode() == "realtime"
    win.mode_buttons["video"].click()
    assert win.current_mode() == "video", "切换到视频翻译失败"
    assert config_mod.load_config().last_mode == "video"
    win.mode_buttons["realtime"].click()
    assert win.current_mode() == "realtime", "切换回实时翻译失败"
    assert win.mode_buttons["video"].text() == "视频翻译"
    print("模式切换：OK")

    # 2. 齿轮打开设置对话框；「管理场景」打开场景管理标签
    win.settings_button.click()
    assert win.settings_dialog.isVisible()
    assert win.settings_dialog.tabs.currentIndex() == SettingsDialog.TAB_BASIC
    win.settings_dialog.hide()
    rp.scene.manage.click()
    assert win.settings_dialog.isVisible()
    assert win.settings_dialog.tabs.currentIndex() == SettingsDialog.TAB_SCENES
    win.settings_dialog.hide()
    print("齿轮设置 / 管理场景：OK")

    # 3. 场景选择：板块 → 子板块，并记住
    rp.scene.section.setCurrentText("游戏")
    assert rp.scene.sub.isEnabled()
    rp.scene.sub.setCurrentIndex(rp.scene.sub.findData("Valorant"))
    assert rp.scene.current_name() == "游戏 → Valorant", rp.scene.current_name()
    assert config_mod.load_config().last_scene == "游戏 → Valorant"
    rp.scene.section.setCurrentText("通用")
    assert not rp.scene.sub.isEnabled()
    print("场景选择：OK")

    # 4. 翻译延迟、音频设备
    rp.delay.setValue(7)
    assert config_mod.load_config().realtime_delay_seconds == 7
    assert rp.device.count() >= 1, "设备列表为空"
    rp.refresh_button.click()
    assert rp.device.count() >= 1
    print("实时参数：OK，设备数：", rp.device.count())

    # 5. 主页上的语言与模型：实时页改 → 保存 → 视频页同步
    mp = rp.model_panel
    mp.source_language.setCurrentIndex(mp.source_language.findData("ja"))
    mp.target_language.setCurrentIndex(mp.target_language.findData("en"))
    assert mp.asr_model.currentData() == "auto"
    assert config_mod.load_config().effective_asr_model() == "gpt-4o-transcribe", "日语应自动选 gpt-4o-transcribe"
    mp.asr_model.setCurrentIndex(mp.asr_model.findData("whisper-1"))
    mp.translate_provider.setCurrentIndex(mp.translate_provider.findData("openai"))
    assert mp.translate_model.currentData() == "gpt-6.1-sol", "切换翻译服务后应自动选该服务的默认模型"
    mp.translate_model.setCurrentIndex(mp.translate_model.findData("gpt-5-mini"))
    c = config_mod.load_config()
    assert c.source_language == "ja" and c.target_language == "en", (c.source_language, c.target_language)
    assert c.asr_model == "whisper-1" and c.effective_asr_model() == "whisper-1"
    assert c.translate_provider == "openai" and c.translate_model == "gpt-5-mini"
    vmp = vp.model_panel
    assert vmp.target_language.currentData() == "en", "视频页未同步目标语言"
    assert vmp.translate_model.currentData() == "gpt-5-mini", "视频页未同步翻译模型"
    assert "不推荐" in vmp.translate_model.currentText()
    assert "英语" in vp.output_mode.note.text(), vp.output_mode.note.text()
    # 反向：视频页改 → 实时页同步
    vmp.target_language.setCurrentIndex(vmp.target_language.findData("zh-Hant"))
    assert mp.target_language.currentData() == "zh-Hant", "实时页未同步目标语言"
    assert "繁体中文" in rp.output_mode.note.text()
    print("语言与模型（两页同步）：OK")

    # 6. API Key 保存 → 重新读取
    sp = win.settings_dialog.settings_page
    sp.openai_key.setText("sk-test-openai")
    sp.anthropic_key.setText("sk-ant-test")
    sp.save_button.click()
    assert sp.status.text() == "已保存。", sp.status.text()
    c = config_mod.load_config()
    assert c.openai_api_key == "sk-test-openai" and c.anthropic_api_key == "sk-ant-test"
    assert c.target_language == "zh-Hant" and c.realtime_delay_seconds == 7, "保存 Key 不应覆盖其他设置"
    print("API Key 保存与重新读取：OK ->", config_mod.config_path())

    # 7. 悬浮字幕窗开关与字号
    rp.overlay_button.click()
    assert win.overlay.isVisible(), "悬浮窗未打开"
    assert rp.overlay_button.text() == "关闭悬浮字幕窗"
    before = win.overlay.cfg.overlay_font_size
    win.overlay.bigger.click()
    assert win.overlay.cfg.overlay_font_size == before + 2
    rp.overlay_button.click()
    assert not win.overlay.isVisible(), "悬浮窗未关闭"
    print("悬浮字幕窗：OK")

    # 8. 输出内容：双语 / 仅译文 / 仅原文；实时页驱动悬浮窗；仅原文时翻译相关选项变灰
    assert rp.output_mode.current() == "bilingual"
    win.overlay.show_demo()
    ov = win.overlay
    assert ov.source_label.isVisibleTo(ov) and ov.target_label.isVisibleTo(ov)
    rp.output_mode.set_current("source_only")
    assert config_mod.load_config().realtime_output_mode == "source_only"
    assert ov.source_label.isVisibleTo(ov) and not ov.target_label.isVisibleTo(ov), "仅原文时不应显示译文"
    assert not mp.translate_model.isEnabled() and not mp.target_language.isEnabled(), "仅原文时翻译选项应变灰"
    rp.output_mode.set_current("target_only")
    assert not ov.source_label.isVisibleTo(ov) and ov.target_label.isVisibleTo(ov), "仅译文时不应显示原文"
    assert mp.translate_model.isEnabled()
    ov.hide()
    vp.output_mode.set_current("source_only")
    assert not vmp.translate_model.isEnabled()
    c = config_mod.load_config()
    assert c.video_output_mode == "source_only" and c.realtime_output_mode == "target_only"
    print("输出内容选择：OK")

    # 9. 重新打开窗口时全部回填
    win2 = MainWindow(c)
    assert win2.realtime_page.delay.value() == 7
    assert win2.realtime_page.model_panel.target_language.currentData() == "zh-Hant"
    assert win2.realtime_page.model_panel.translate_model.currentData() == "gpt-5-mini"
    assert win2.realtime_page.output_mode.current() == "target_only"
    assert win2.video_page.output_mode.current() == "source_only"
    assert not win2.video_page.model_panel.translate_model.isEnabled()
    assert win2.settings_dialog.settings_page.openai_key.text() == "sk-test-openai"
    print("重启后设置回填：OK")

    # 10. 旧版本设置文件兼容（offline → video）
    old = config_mod.Config()
    config_mod.save_config(old)
    import json
    p = config_mod.config_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["last_mode"] = "offline"
    raw["offline_output_mode"] = "target_only"
    raw.pop("video_output_mode", None)
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    raw["asr_model"] = "whisper-1"
    raw["translate_model"] = "claude-opus-5"
    raw.pop("config_version", None)
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    c = config_mod.load_config()
    assert c.last_mode == "video" and c.video_output_mode == "target_only"
    assert c.asr_model == "auto" and c.translate_model == "claude-sonnet-5-5", (c.asr_model, c.translate_model)
    # 版本 2 文件：gpt-5 → gpt-6.1-sol
    raw["config_version"] = 2
    raw["translate_provider"] = "openai"
    raw["translate_model"] = "gpt-5"
    raw["asr_model"] = "gpt-transcribe"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    c = config_mod.load_config()
    assert c.translate_model == "gpt-6.1-sol" and c.asr_model == "auto", (c.translate_model, c.asr_model)
    assert c.config_version == 3
    # 新版本文件里用户自己选的 whisper-1 不能被改掉
    c.asr_model = "whisper-1"
    config_mod.save_config(c)
    assert config_mod.load_config().asr_model == "whisper-1"
    print("旧设置兼容：OK")

    win.close()
    win2.close()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
