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

    # 1. 两个模式能切换，并记住
    assert win.current_mode() == "realtime"
    win.mode_buttons["offline"].click()
    assert win.current_mode() == "offline", "切换到离线翻译失败"
    assert config_mod.load_config().last_mode == "offline"
    win.mode_buttons["realtime"].click()
    assert win.current_mode() == "realtime", "切换回实时翻译失败"
    print("模式切换：OK")

    # 2. 齿轮打开设置对话框；「管理场景」打开场景管理标签
    win.settings_button.click()
    assert win.settings_dialog.isVisible()
    assert win.settings_dialog.tabs.currentIndex() == SettingsDialog.TAB_BASIC
    win.settings_dialog.hide()
    win.realtime_page.scene.manage.click()
    assert win.settings_dialog.isVisible()
    assert win.settings_dialog.tabs.currentIndex() == SettingsDialog.TAB_SCENES
    win.settings_dialog.hide()
    print("齿轮设置 / 管理场景：OK")

    # 3. 场景选择：板块 → 子板块，并记住
    rp = win.realtime_page
    rp.scene.section.setCurrentText("游戏")
    assert rp.scene.sub.isEnabled()
    rp.scene.sub.setCurrentIndex(rp.scene.sub.findData("Valorant"))
    assert rp.scene.current_name() == "游戏 → Valorant", rp.scene.current_name()
    assert config_mod.load_config().last_scene == "游戏 → Valorant"
    rp.scene.section.setCurrentText("通用")
    assert not rp.scene.sub.isEnabled()
    print("场景选择：OK")

    # 4. 翻译延迟、音频设备记住
    rp.delay.setValue(7)
    assert config_mod.load_config().realtime_delay_seconds == 7
    assert rp.device.count() >= 1, "设备列表为空"
    print("实时参数：OK，设备：", [rp.device.itemText(i) for i in range(rp.device.count())])

    # 5. 设置保存 → 重新读取
    sp = win.settings_dialog.settings_page
    sp.openai_key.setText("sk-test-openai")
    sp.anthropic_key.setText("sk-ant-test")
    sp.asr_model.setCurrentText("gpt-4o-transcribe")
    sp.translate_provider.setCurrentIndex(sp.translate_provider.findData("openai"))
    sp.translate_model.setCurrentText("gpt-4o-mini")
    sp.source_language.setCurrentIndex(sp.source_language.findData("ja"))
    sp.save_button.click()
    assert sp.status.text() == "已保存。", sp.status.text()
    reloaded = config_mod.load_config()
    assert reloaded.openai_api_key == "sk-test-openai"
    assert reloaded.anthropic_api_key == "sk-ant-test"
    assert reloaded.asr_model == "gpt-4o-transcribe"
    assert reloaded.translate_provider == "openai"
    assert reloaded.translate_model == "gpt-4o-mini"
    assert reloaded.source_language == "ja"
    assert reloaded.realtime_delay_seconds == 7
    print("设置保存与重新读取：OK ->", config_mod.config_path())

    # 6. 重新打开窗口时应回填
    win2 = MainWindow(reloaded)
    sp2 = win2.settings_dialog.settings_page
    assert sp2.openai_key.text() == "sk-test-openai"
    assert sp2.translate_model.currentText() == "gpt-4o-mini"
    assert sp2.source_language.currentData() == "ja"
    assert win2.realtime_page.delay.value() == 7
    assert win2.realtime_page.scene.current_name() == "通用"
    print("重启后设置回填：OK")

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

    win.close()
    win2.close()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
