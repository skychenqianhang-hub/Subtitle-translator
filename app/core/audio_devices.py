"""列出电脑上可以抓取声音的输出设备（扬声器 / 耳机）。

用 WASAPI loopback 抓取某个输出设备正在播放的声音，
所以这里列出的就是 Windows「选择扬声器」里那些设备。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioDevice:
    index: int          # pyaudio 设备编号（loopback 设备）
    name: str           # 显示给用户看的名字
    is_default: bool    # 是否是 Windows 当前默认输出设备


def list_output_devices() -> list[AudioDevice]:
    """返回可抓取的输出设备；默认设备排在最前。抓不到时返回空列表。"""
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        return []

    devices: list[AudioDevice] = []
    try:
        p = pyaudio.PyAudio()
    except Exception:
        return []
    try:
        default_name = ""
        try:
            default_name = p.get_default_wasapi_loopback().get("name", "")
        except Exception:
            pass
        for info in p.get_loopback_device_info_generator():
            raw = str(info.get("name", ""))
            name = raw.replace("[Loopback]", "").strip()
            devices.append(AudioDevice(int(info["index"]), name, raw == default_name))
    except Exception:
        pass
    finally:
        p.terminate()
    devices.sort(key=lambda d: (not d.is_default, d.name))
    return devices
