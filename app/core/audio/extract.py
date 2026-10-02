"""用 ffmpeg 从视频 / 音频文件里抽出 16kHz 单声道音频。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from app.core.errors import UserFacingError
from app.tools import find_ffmpeg, find_ffprobe

SAMPLE_RATE = 16000

# Windows 下不弹出黑色命令行窗口
_NO_WINDOW = 0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0


def _need(tool: str | None, name: str) -> str:
    if not tool:
        raise UserFacingError(f"找不到 {name}。请把问题告诉 Claude Code，需要重新打包程序。")
    return tool


def probe_duration(path: str | Path) -> float:
    """返回媒体时长（秒）。拿不到返回 0。"""
    ffprobe = _need(find_ffprobe(), "ffprobe")
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=60)
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def has_audio_stream(path: str | Path) -> bool:
    ffprobe = _need(find_ffprobe(), "ffprobe")
    cmd = [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
           "-of", "json", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=60)
        return bool(json.loads(out.stdout).get("streams"))
    except Exception:
        return True  # 探测失败就交给 ffmpeg 去试


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
