"""场景自动判断自检。运行：python -m tests.test_auto_scene"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="subtranslator_auto_")
os.environ["APPDATA"] = _tmp

import numpy as np  # noqa: E402

from app.config import Config  # noqa: E402
from app.core.asr.base import Segment, Transcriber  # noqa: E402
from app.core.audio.extract import extract_pcm  # noqa: E402
from app.core.pipeline.live_pipeline import LiveCallbacks, LiveOptions, LiveSession  # noqa: E402
from app.core.profiles.detect import SceneDetector  # noqa: E402
from app.core.profiles.store import AUTO_SCENE, ProfileStore  # noqa: E402
from tests.test_live import FakeCapture  # noqa: E402
from tests.test_pipeline import FIXTURES, FakeTranslator  # noqa: E402

VAL_EN = ("Jett dashes onto A site on Ascent, Sova uses his recon dart. They plant the Spike. "
          "Reyna gets the clutch with the Vandal, what an ace! Omen smokes heaven, Killjoy turret on B.")
CS_EN = ("He picks up the AWP on Mirage, rush B with a flash and a molly. CT side is saving, "
         "terrorists plant the bomb, the AK-47 spray on Inferno was insane. Dust 2 next, eco round on T side.")
VAL_JA = "ジェットがアセントでウルト使った。ソーヴァのリコンで情報取って、スパイク設置。レイナがクラッチ、ヴァンダルでエース！"
CS_JA = "ミラージュでAWP持って、ラッシュB。フラッシュとモロトフ投げて、ボム設置。デグルでワンタップ、インフェルノのエコラウンド。"
GENERIC_GAME = "GG well played. This ranked match was laggy, my ping is bad. They should nerf that, the buff was too much. MVP again."
UNRELATED = "Today we are going to cook pasta. First boil the water, then add salt and the spaghetti. It takes ten minutes."
MOVIE = "Odysseus sails from Troy back to Ithaca. Penelope waits with Telemachus while Poseidon and Athena watch. Circe and Calypso delay him."


class ScriptedTranscriber(Transcriber):
    """按顺序吐出预先写好的句子。"""
    provider = "fake"

    def __init__(self, script: list[str]) -> None:
        super().__init__("fake")
        self.script = list(script)
        self.i = 0
        self.lock = threading.Lock()
        self.prompts: list[str] = []

    @property
    def has_timestamps(self) -> bool:
        return False

    def transcribe(self, wav_path, language=None, prompt=""):
        with self.lock:
            text = self.script[self.i % len(self.script)]
            self.i += 1
            self.prompts.append(prompt)
        return [Segment(0.0, -1.0, text)]


def main() -> int:
    store = ProfileStore(Path(_tmp) / "profiles")
    det = SceneDetector(store)

    # 1. 判断
    assert det.choose(VAL_EN) == "Valorant", det.scores(VAL_EN)
    assert det.choose(CS_EN) == "CS2", det.scores(CS_EN)
    assert det.choose(VAL_JA) == "Valorant", det.scores(VAL_JA)
    assert det.choose(CS_JA) == "CS2", det.scores(CS_JA)
    assert det.choose(MOVIE) == "Odyssey", det.scores(MOVIE)
    assert det.choose(GENERIC_GAME) == "游戏", det.scores(GENERIC_GAME)
    assert det.choose(UNRELATED) == "通用" and det.choose(UNRELATED, "Valorant") == "Valorant", "证据不足应保持当前场景"
    # 证据不足的一两个词不该切换
    assert det.choose("We split the bill and saved some money.", "通用") == "通用"
    # 两个游戏的词各占一半 → 退回共同的父场景「游戏」
    mixed = det.choose(VAL_EN + " " + CS_EN, "通用")
    assert mixed == "游戏", (mixed, det.scores(VAL_EN + " " + CS_EN))
    print("场景判断：OK（英文 / 日文 Valorant、CS2，电影，通用游戏，无关内容，混合）")

    # 2. 自动模式的保存值与解析
    assert store.display_name(AUTO_SCENE).startswith("自动") and store.resolve(AUTO_SCENE).name == "通用"

    # 3. 实时流程：先 Valorant 后 CS2，应切换两次，且切换后术语表和识别提示词都换了
    audio = np.concatenate([extract_pcm(FIXTURES / "tts_en.wav")] * 4)
    val_lines = ["Jett dashes onto A site on Ascent.", "Sova uses his recon dart, they plant the Spike.",
                 "Reyna gets the clutch with the Vandal.", "Omen smokes heaven, Killjoy turret on B."]
    cs_lines = ["He picks up the AWP on Mirage.", "Rush B with a flash and a molly.",
                "CT side is saving, terrorists plant the bomb.", "The AK-47 spray on Inferno was insane.",
                "Dust 2 next, eco round on T side.", "The AWP on Mirage again, CT side rotate.",
                "Inferno banana, molly and flash, AK-47 and AWP.", "Dust 2 long, CT side with the AWP."]
    tr = ScriptedTranscriber(val_lines + cs_lines + cs_lines)
    tl = FakeTranslator()
    switches: list[str] = []
    opts = LiveOptions(max_segment_seconds=3.0, source_language="en", auto_scene=True, scene_name="通用",
                       auto_min_interval=0.0, auto_window_lines=6, hold_half_sentence_seconds=0.3)
    sess = LiveSession(Config(), tr, tl, opts, LiveCallbacks(on_scene=lambda n, d: switches.append(n)),
                       capture_factory=lambda on_chunk: FakeCapture(audio, on_chunk, speed=10.0),
                       scene_detector=det, scene_resolver=store.resolve)
    sess.start()
    deadline = time.time() + 40
    while time.time() < deadline and not ("Valorant" in switches and "CS2" in switches):
        time.sleep(0.1)
    sess.stop()
    assert "Valorant" in switches, switches
    assert "CS2" in switches and switches.index("Valorant") < switches.index("CS2"), switches
    assert sess.opt.scene_name == "CS2" and "Mirage" in sess.opt.glossary and "AWP" in sess.opt.asr_prompt
    assert any("Mirage" in (r.glossary or {}) for r in tl.requests), "切换后翻译应带上新场景的术语表"
    assert tr.prompts[0] == "" and any("AWP" in p for p in tr.prompts), "切换后识别提示词应换成新场景的"
    print("实时自动切换：OK", switches)

    # 4. 界面：选择器有「自动」，选中后子板块变灰，保存值正确
    from PySide6.QtWidgets import QApplication
    from app import config as config_mod
    from app.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(config_mod.load_config())
    sp = win.realtime_page.scene
    sp.section.setCurrentIndex(sp.section.findData(AUTO_SCENE))
    assert sp.current_name() == AUTO_SCENE and sp.is_auto() and not sp.sub.isEnabled()
    assert config_mod.load_config().last_scene == AUTO_SCENE
    win2 = MainWindow(config_mod.load_config())
    assert win2.realtime_page.scene.current_name() == AUTO_SCENE, "重开后应仍是自动"
    win.close()
    win2.close()
    print("选择器「自动」选项：OK")

    # 5. 视频流程：自动判断后术语表生效
    from app.core.pipeline.video_pipeline import VideoJob, VideoPipeline
    tr2 = ScriptedTranscriber([VAL_EN])
    tl2 = FakeTranslator()
    logs: list[str] = []
    pipe = VideoPipeline(Config(), tr2, tl2, log=logs.append,
                         detect_scene=lambda text: store.resolve(det.choose(text, "通用")))
    pipe.run(VideoJob(media_path=FIXTURES / "tts_en.wav", source_language="en"))
    assert pipe.detected_scene is not None and pipe.detected_scene.name == "Valorant"
    assert tl2.requests and tl2.requests[0].glossary.get("Jett") == "捷风"
    assert any("自动判断场景" in x for x in logs)
    print("视频流程自动场景：OK")

    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
