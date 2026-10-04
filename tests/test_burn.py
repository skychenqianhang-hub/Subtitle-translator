"""字幕烧录自检：ASS 生成（含自定义样式）、用 ffmpeg 生成测试视频烧字幕并检查画面。

运行：python -m tests.test_burn
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.subtitle.ass import SIZE_PRESETS, to_ass, wrap_cjk
from app.core.subtitle.burn import burn_subtitles, default_video_path
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.style import SubtitleStyle, TextStyle, ass_style_line
from app.tools import find_ffmpeg

NL = "\\N"   # ASS 的换行标记


def test_ass() -> None:
    lines = [SubtitleLine(0.5, 2.0, "Hello {world}", "你好，世界"), SubtitleLine(2.0, 3.0, "Bye", "")]
    assert SIZE_PRESETS["small"] < SIZE_PRESETS["medium"] < SIZE_PRESETS["large"]
    ass = to_ass(lines, "bilingual", "small")
    assert f"Style: Target,Microsoft YaHei,{SIZE_PRESETS['small']}," in ass
    assert re.search(r"Dialogue: 0,0:00:00\.50,0:00:02\.00,Target,,0,0,0,,\{\\an2\\pos\(\d+,\d+\)\}你好，世界", ass), ass[-400:]
    assert re.search(r"Dialogue: 1,0:00:00\.50,0:00:02\.00,Source,,0,0,0,,\{\\an2\\pos\(\d+,\d+\)\}Hello \(world\)", ass), "花括号必须转义"
    assert re.search(r"Dialogue: 0,0:00:02\.00,0:00:03\.00,Target,,0,0,0,,\{[^}]*\}Bye", ass), "没有译文时只画一行"
    assert "你好" not in to_ass(lines, "source_only") and "Hello" not in to_ass(lines, "target_only")
    # 原文块应在译文块上方（y 更小）
    ys = [int(m) for m in re.findall(r"\\pos\(\d+,(\d+)\)", ass)]
    assert ys[1] < ys[0], ys

    # 自定义样式：字体、颜色、对齐、位置、底框都进 ASS
    st = SubtitleStyle(target=TextStyle(font="SimHei", size=30, color="#FF0000", align="right", x_pct=90, y_pct=50, back_alpha=50))
    a2 = to_ass(lines, "target_only", style=st)
    style_line = next(l for l in a2.splitlines() if l.startswith("Style: Target,"))
    assert style_line.startswith("Style: Target,SimHei,30,&H000000FF,"), style_line
    assert style_line.split(",")[15] == "3", "有底框时 BorderStyle 应为 3：" + style_line
    assert "{\\an3\\pos(576,180)}" in a2, a2[-300:]
    assert ass_style_line("X", TextStyle()).split(",")[15] == "1"

    long = "包裹地球、保护我们免受太阳怒火的是一个巨大的磁性气泡，叫作磁层。"
    wrapped = wrap_cjk(long, 25)
    assert wrapped.count(NL) == 1 and all(len(x) <= 25 for x in wrapped.split(NL)), wrapped
    near = wrap_cjk("今天天气很好，我们一起出去玩吧，好不好呢", 12)
    assert near.split(NL)[0].endswith("，"), "附近有标点时应在标点后断行：" + near
    assert wrap_cjk("short", 10) == "short" and NL not in wrap_cjk("Enveloping our planet and protecting", 10)
    assert default_video_path("a/b.mp4", "bilingual", "简体中文").name == "b.双语字幕.mp4"
    assert default_video_path("a/b.mp4", "target_only", "简体中文").name == "b.简体中文字幕.mp4"
    print("ASS 生成：OK")


def test_burn_frame_has_text() -> None:
    """用 Qt 读一帧，检查画面下方有亮像素（字幕）；再用自定义样式把字幕放到画面上方验证位置生效。"""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    ffmpeg = find_ffmpeg()

    def bright(img: QImage, y0: int, y1: int) -> int:
        return sum(1 for y in range(y0, y1) for x in range(0, 640, 2) if img.pixelColor(x, y).lightness() > 200)

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
        assert bright(img, 260, 360) > 60, f"画面下方没有看到字幕（亮像素 {bright(img, 260, 360)}）"
        assert bright(img, 0, 100) < 20, "画面上方不应有字幕"

        top_style = SubtitleStyle(target=TextStyle(size=24, y_pct=20.0, color="#FFFFFF"))
        out2 = Path(td) / "v.top.mp4"
        burn_subtitles(src, [SubtitleLine(0.0, 2.0, "Hello", "你好世界")], out2, "target_only", style=top_style)
        frame2 = Path(td) / "f2.png"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", "1.0", "-i", str(out2), "-frames:v", "1", str(frame2)], check=True)
        img2 = QImage(str(frame2))
        assert bright(img2, 0, 100) > 60, "自定义样式把字幕放到上方后，上方应有字幕"
        assert bright(img2, 260, 360) < 20, "下方不应再有字幕"
    print("烧录画面检查：OK（默认在下方，自定义样式可移到上方）")


def main() -> int:
    test_ass()
    test_burn_frame_has_text()
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
