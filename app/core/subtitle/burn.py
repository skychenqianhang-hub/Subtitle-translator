"""把字幕烧进视频画面（硬字幕），用 ffmpeg 重新编码视频，声音原样复制。"""
from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from app.core.audio.extract import _NO_WINDOW, probe_duration
from app.core.errors import Cancelled, UserFacingError
from app.core.subtitle.ass import write_ass
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.style import SubtitleStyle
from app.tools import find_ffmpeg

ProgressCb = Callable[[float], None]   # 0.0 - 1.0


def default_video_path(media_path: str | Path, mode: str, target_name: str) -> Path:
    src = Path(media_path)
    tag = {"bilingual": "双语字幕", "source_only": "原文字幕"}.get(mode, f"{target_name}字幕")
    return src.with_name(f"{src.stem}.{tag}.mp4")


def burn_subtitles(
    media_path: str | Path,
    lines: list[SubtitleLine],
    out_path: str | Path,
    mode: str = "bilingual",
    size: str = "medium",
    progress: ProgressCb = lambda p: None,
    cancel: threading.Event | None = None,
    margin_pct: int = 3,
    style: "SubtitleStyle | None" = None,
) -> Path:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise UserFacingError("找不到 ffmpeg，无法生成带字幕的视频。")
    media_path = Path(media_path)
    out_path = Path(out_path)
    duration = probe_duration(media_path) or 0.0

    # ffmpeg 的字幕滤镜对路径里的冒号、括号很敏感，所以把字幕写到临时目录里用最简单的文件名，
    # 并把工作目录切到那里，滤镜只写相对路径。
    with tempfile.TemporaryDirectory(prefix="subtr_burn_") as td:
        ass = Path(td) / "sub.ass"
        write_ass(ass, lines, mode, size, margin_pct, style)
        cmd = [
            ffmpeg, "-y", "-v", "error", "-nostdin", "-nostats", "-progress", "pipe:1",
            "-i", str(media_path),
            "-vf", "ass=sub.ass",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ]
        proc = subprocess.Popen(
            cmd, cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="ignore", creationflags=_NO_WINDOW,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    proc.wait()
                    out_path.unlink(missing_ok=True)
                    raise Cancelled()
                line = line.strip()
                if line.startswith("out_time_us=") and duration > 0:
                    try:
                        us = int(line.split("=", 1)[1])
                        progress(min(0.999, us / 1_000_000 / duration))
                    except ValueError:
                        pass
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode != 0:
            err = (proc.stderr.read() if proc.stderr else "").strip().splitlines()
            detail = err[-1] if err else "未知原因"
            out_path.unlink(missing_ok=True)
            raise UserFacingError(f"生成带字幕的视频失败：{detail}")
    progress(1.0)
    return out_path
