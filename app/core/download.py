"""从视频网址下载（YouTube、B 站等），用 yt-dlp。"""
from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Callable

from app.core.errors import Cancelled, UserFacingError
from app.tools import find_ffmpeg

ProgressCb = Callable[[float, str], None]   # (0.0-1.0, 说明)

_URL_RE = re.compile(r"^(https?://|www\.)", re.I)


def looks_like_url(text: str) -> bool:
    return bool(_URL_RE.match((text or "").strip()))


def _js_runtime_args() -> list[str]:
    """YouTube 需要一个 JavaScript 运行环境才能拿到全部清晰度；电脑上有 node 或 deno 就用。"""
    for name in ("node", "deno", "bun"):
        if shutil.which(name):
            return [name]
    return []


def download_video(url: str, out_dir: Path, progress: ProgressCb = lambda p, s: None,
                   cancel: threading.Event | None = None, max_height: int = 1080) -> Path:
    """下载到 out_dir，返回文件路径。已经下载过的直接复用。"""
    try:
        import yt_dlp
    except ImportError as e:
        raise UserFacingError("下载组件没有装好，请告诉 Claude Code 重新打包。") from e

    url = url.strip()
    if not looks_like_url(url):
        raise UserFacingError("这不像一个网址。请粘贴以 http:// 或 https:// 开头的视频链接。")
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/b[height<={max_height}][ext=mp4]/b"
    result: dict[str, str] = {}
    # 视频和音频是两条流分开下载的，各自从 0% 到 100%；这里把它们合成一个只增不减的总进度
    streams: dict[str, float] = {}
    state = {"best": 0.0}

    def hook(d: dict) -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        status = d.get("status")
        name = str(d.get("filename") or "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            streams[name] = max(streams.get(name, 0.0), done / total if total else 0.0)
        elif status == "finished":
            streams[name] = 1.0
            result["file"] = name
        expected = max(2 if "+" in fmt else 1, len(streams))
        overall = sum(streams.values()) / expected
        state["best"] = max(state["best"], min(0.98, overall))
        speed = d.get("speed") or 0
        spd = f"{speed / 1024 / 1024:.1f} MB/s" if speed and status == "downloading" else ""
        if status == "finished" and overall >= 0.999:
            progress(0.99, "下载完成，正在合并音视频")
        else:
            progress(state["best"], f"下载中 {int(state['best'] * 100)}% {spd}".strip())

    def post_hook(d: dict) -> None:
        if d.get("status") == "finished" and d.get("info_dict", {}).get("filepath"):
            result["file"] = d["info_dict"]["filepath"]

    opts = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(title).80s [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "postprocessor_hooks": [post_hook],
        "retries": 3,
    }
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    js = _js_runtime_args()
    if js:
        opts["js_runtimes"] = {js[0]: {}}

    progress(0.0, "正在获取视频信息")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Cancelled:
        raise
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "Unsupported URL" in msg:
            raise UserFacingError("不支持这个网站的链接。") from e
        if "Private video" in msg or "Sign in" in msg or "login" in msg.lower():
            raise UserFacingError("这个视频需要登录或是私密视频，无法下载。") from e
        if "not available" in msg or "unavailable" in msg:
            raise UserFacingError("视频不存在或已被删除。") from e
        if "HTTP Error 4" in msg or "Unable to download" in msg:
            raise UserFacingError("下载失败：网络不通或网站拒绝了请求。可以试试开关代理后重试。") from e
        raise UserFacingError(f"下载失败：{msg.splitlines()[-1][:200]}") from e
    except Exception as e:  # noqa: BLE001
        raise UserFacingError(f"下载失败：{type(e).__name__}: {str(e)[:200]}") from e

    path = result.get("file") or ""
    if not path and info:
        try:
            path = ydl.prepare_filename(info)
        except Exception:  # noqa: BLE001
            path = ""
    p = Path(path) if path else None
    if p is None or not p.exists():
        # 合并后扩展名可能变成 mp4
        cands = sorted(out_dir.glob(f"*[{info.get('id', '')}].*"), key=lambda x: x.stat().st_mtime, reverse=True) if info else []
        cands = [c for c in cands if c.suffix.lower() in (".mp4", ".mkv", ".webm", ".m4a", ".mp3")]
        if not cands:
            raise UserFacingError("下载似乎完成了，但找不到文件。")
        p = cands[0]
    progress(1.0, "下载完成")
    return p
