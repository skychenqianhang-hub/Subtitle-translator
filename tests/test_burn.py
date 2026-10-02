"""字幕烧录自检：用 ffmpeg 生成一段 3 秒的测试视频，把双语字幕烧进去，检查输出。

运行：python -m tests.test_burn
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.subtitle.ass import SIZE_PRESETS, to_ass
from app.core.subtitle.burn import burn_subtitles, default_video_path
from app.core.subtitle.models import SubtitleLine
from app.tools import find_ffmpeg


def test_ass() -> None:
    lines = [SubtitleLine(0.5, 2.0, "Hello {world}", "你好，世界"), SubtitleLine(2.0, 3.0, "Bye", "")]
    assert SIZE_PRESETS["small"] < SIZE_PRESETS["medium"] < SIZE_PRESETS["large"]
    ass = to_ass(lines, "bilingual", "small")
    assert f"Style: Target,Microsoft YaHei,{SIZE_PRESETS['small']}," in ass
    assert "Dialogue: 0,0:00:00.50,0:00:02.00,Target,,0,0,0,,你好，世界" in ass
    import re
    m = re.search(r"Dialogue: 1,0:00:00\.50,0:00:02\.00,Source,,0,0,(\d+),,Hello \(world\)", ass)
    assert m, "花括号必须转义，且原文行要有抬高的边距"
    assert int(m.group(1)) > 24, "双语时原文行应抬高到译文上方"
    assert "Dialogue: 0,0:00:02.00,0:00:03.00,Single,,0,0,0,,Bye" in ass, "没有译文时用单行样式"
    assert "你好" not in to_ass(lines, "source_only") and "Hello" not in to_ass(lines, "target_only")
    from app.core.subtitle.ass import wrap_cjk
    long = "包裹地球、保护我们免受太阳怒火的是一个巨大的磁性气泡，叫作磁层。"
    wrapped = wrap_cjk(long, 25)
    assert wrapped.count("\\N") == 1 and all(len(x) <= 25 for x in wrapped.split("\\N")), wrapped
    near = wrap_cjk("今天天气很好，我们一起出去玩吧，好不好呢", 12)
    assert near.split("\\N")[0].endswith("，"), "附近有标点时应在标点后断行：" + near
    assert wrap_cjk("short", 10) == "short" and "\\N" not in wrap_cjk("Enveloping our planet and protecting", 10)
    assert default_video_path("a/b.mp4", "bilingual", "简体中文").name == "b.双语字幕.mp4"
    assert default_video_path("a/b.mp4", "target_only", "简体中文").name == "b.简体中文字幕.mp4"
    print("ASS 生成：OK")


def test_burn_frame_has_text() -> None:
    """用 Qt 读一帧，检查画面下方有亮像素（字幕）。"""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    ffmpeg = find_ffmpeg()
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "v.mp4"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=640x360:d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
        out = Path(td) / "v.sub.mp4"
        burn_subtitles(src, [SubtitleLine(0.0, 2.0, "Hello", "你好世界")], out, "bilingual", "large")
        frame = Path(td) / "f.png"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", "1.0", "-i", str(out), "-frames:v", "1", str(frame)], check=True)
        img = QImage(str(frame))
        assert not img.isNull()
        bright_bottom = sum(1 for y in range(260, 360) for x in range(0, 640, 2) if img.pixelColor(x, y).lightness() > 200)
        bright_top = sum(1 for y in range(0, 100) for x in range(0, 640, 2) if img.pixelColor(x, y).lightness() > 200)
        assert bright_bottom > 60, f"画面下方没有看到字幕（亮像素 {bright_bottom}）"
        assert bright_top < 20, "画面上方不应有字幕"
    print(f"烧录画面检查：OK（下方亮像素 {bright_bottom}）")


def main() -> int:
    test_ass()
    test_burn_frame_has_text()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
