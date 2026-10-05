"""用 ffmpeg 从视频 / 音频文件里抽出 16kHz 单声道音频。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from app.core.errors import UserFacingError
from app.tools import find_ffmpeg

SAMPLE_RATE = 16000

# Windows 下不弹出黑色命令行窗口
_NO_WINDOW = 0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0


def _need(tool: str | None, name: str) -> str:
    if not tool:
        raise UserFacingError(f"找不到 {name}。请把问题告诉 Claude Code，需要重新打包程序。")
    return tool


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:")


def _probe(path: str | Path) -> str:
    """用 ffmpeg -i 读文件信息（输出在 stderr）。不需要单独的 ffprobe。"""
    ffmpeg = _need(find_ffmpeg(), "ffmpeg")
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path)], capture_output=True,
                             creationflags=_NO_WINDOW, timeout=60)
        return out.stderr.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""


def probe_duration(path: str | Path) -> float:
    """返回媒体时长（秒）。拿不到返回 0。"""
    m = _DURATION_RE.search(_probe(path))
    if not m:
        return 0.0
    h, mi, sec = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(sec)


def has_audio_stream(path: str | Path) -> bool:
    info = _probe(path)
    if not info:
        return True   # 探测失败就交给后面的解码去试
    return bool(_AUDIO_RE.search(info))


def extract_pcm(path: str | Path) -> np.ndarray:
    """把文件解码成 16kHz 单声道 float32 数组（范围 -1 到 1）。"""
    src = Path(path)
    if not src.exists():
        raise UserFacingError(f"找不到文件：{src}")
    if not has_audio_stream(src):
        raise UserFacingError("这个文件里没有音轨，无法识别。")
    ffmpeg = _need(find_ffmpeg(), "ffmpeg")
    cmd = [
        ffmpeg, "-v", "error", "-nostdin", "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "ignore").strip().splitlines()
        detail = err[-1] if err else "未知原因"
        raise UserFacingError(f"ffmpeg 无法读取这个文件：{detail}")
    data = np.frombuffer(proc.stdout, dtype=np.int16)
    if data.size == 0:
        raise UserFacingError("这个文件里没有声音内容。")
    return data.astype(np.float32) / 32768.0


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """把 float32 数组写成 16 位 wav 文件。"""
    import soundfile as sf
    sf.write(str(path), samples, sample_rate, subtype="PCM_16")
