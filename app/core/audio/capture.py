"""抓取电脑正在播放的声音（WASAPI loopback），转成 16kHz 单声道后交给回调。

用 PortAudio 的回调模式：声音到了系统主动调我们，没声音时不会卡住；停止时先 stop_stream 再 close，
不会出现「一个线程在读、另一个线程关流」导致的崩溃。
"""
from __future__ import annotations

from app.i18n import tr

import threading
from typing import Callable

import numpy as np

from app.core.audio.vad import SAMPLE_RATE
from app.core.errors import UserFacingError

ChunkCb = Callable[[np.ndarray], None]   # float32，16kHz 单声道


def resample(mono: np.ndarray, src_rate: int, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    if src_rate == dst_rate or len(mono) == 0:
        return mono.astype(np.float32, copy=False)
    n_out = int(round(len(mono) * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, mono).astype(np.float32)


class LoopbackCapture:
    """持续读取某个输出设备正在播放的声音。device_index 是 loopback 设备编号（见 audio_devices）。"""

    def __init__(self, device_index: int | None, on_chunk: ChunkCb, frames_per_buffer: int = 2048) -> None:
        self.device_index = device_index
        self.on_chunk = on_chunk
        self.frames_per_buffer = frames_per_buffer
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()
        self._stopping = False
        self.rate = 0
        self.channels = 0
        self.error: str | None = None
        self.frames_received = 0

    def start(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as e:
            raise UserFacingError(tr("音频抓取组件没有装好，请告诉 Claude Code 重新打包。")) from e
        self._pa = pyaudio.PyAudio()
        try:
            if self.device_index is None or self.device_index < 0:
                info = self._pa.get_default_wasapi_loopback()
            else:
                info = self._pa.get_device_info_by_index(self.device_index)
        except Exception as e:  # noqa: BLE001
            self._pa.terminate()
            self._pa = None
            raise UserFacingError(tr("找不到可以抓取的声音设备。请在列表里换一个设备，或点「刷新」。")) from e
        self.rate = int(info["defaultSampleRate"])
        self.channels = max(1, int(info["maxInputChannels"]))
        self._stopping = False

        def callback(in_data, frame_count, time_info, status):
            if self._stopping:
                return (None, pyaudio.paComplete)
            try:
                data = np.frombuffer(in_data, dtype=np.int16)
                if self.channels > 1:
                    data = data.reshape(-1, self.channels).mean(axis=1)
                mono = data.astype(np.float32) / 32768.0
                self.frames_received += len(mono)
                self.on_chunk(resample(mono, self.rate))
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
            return (None, pyaudio.paContinue)

        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=self.channels, rate=self.rate, input=True,
                input_device_index=int(info["index"]), frames_per_buffer=self.frames_per_buffer,
                stream_callback=callback,
            )
            self._stream.start_stream()
        except Exception as e:  # noqa: BLE001
            self._pa.terminate()
            self._pa = None
            raise UserFacingError(tr("打不开声音设备「{0}」：{1}", info.get('name', ''), e)) from e

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            if self._stream is not None:
                try:
                    if self._stream.is_active():
                        self._stream.stop_stream()
                    self._stream.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stream = None
            if self._pa is not None:
                try:
                    self._pa.terminate()
                except Exception:  # noqa: BLE001
                    pass
                self._pa = None
