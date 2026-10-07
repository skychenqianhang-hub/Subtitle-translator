"""场景数据层自检：继承合并、增删改名、文件读写、多语言术语表、CSV / Excel 导入导出。

运行：python -m tests.test_profiles
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.core.errors import UserFacingError
from app.core.profiles.glossary import glossary_for, guess_language, merge_rows, normalize_glossary
from app.core.profiles.glossary_io import export_glossary, import_glossary
from app.core.profiles.store import ROOT_NAME, Profile, ProfileStore


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        store = ProfileStore(Path(td))
        # 1. 首次运行：从项目 profiles/ 复制预置场景
        names = store.all_names_in_tree_order()
        assert names[0] == ROOT_NAME and "游戏" in names and "Valorant" in names and "CS2" in names, names
        assert store.display_name("Valorant") == "游戏 → Valorant"
        assert store.path("Valorant") == ["通用", "游戏", "Valorant"]
        print("预置场景：OK", names)

        # 2. 继承合并：Valorant 拿到「游戏」的术语 + 自己的；同名以子为准
        eff = store.resolve("Valorant")
        zh = eff.glossary_for("en", "zh-Hans")
        assert zh["Jett"] == "捷风" and zh["GG"] == "GG", "应合并父场景术语"
        ja_zh = eff.glossary_for("ja", "zh-Hans")
        assert ja_zh["ジェット"] == "捷风" and ja_zh["エコ"] == "经济局", "日文词条也应在"
        assert "Jett" not in ja_zh, "原文是日语时不该带英文词条"
        auto = eff.glossary_for("auto", "zh-Hans")
        assert auto["Jett"] == "捷风" and auto["ジェット"] == "捷风"
        assert len(eff.glossary) > 250, len(eff.glossary)
        cs2 = store.resolve("CS2").glossary_for("auto", "zh-Hans")
        assert cs2["Mirage"] == "荒漠迷城" and cs2["デグル"] == "沙鹰"
        assert eff.style and "游戏" in eff.style, "风格应从「游戏」继承"
        assert "Jett" in eff.asr_prompt and "GG" in eff.asr_prompt
        assert eff.corrections["jet"] == "Jett"
        # 繁体中文列：预置里每条有简体的都要有繁体；官方译名用台港澳服的写法
        for n in ("Valorant", "CS2", "游戏", "Odyssey"):
            rows = store.get(n).glossary
            lacking = [r for r in rows if r.get("zh-Hans") and not r.get("zh-Hant")]
            assert not lacking, (n, lacking[:5])
        hant = store.resolve("Valorant").glossary_for("en", "zh-Hant")
        assert hant["Jett"] and hant["Jett"] != "捷风" and hant["Vandal"], hant.get("Jett")
        assert store.resolve("Valorant").glossary_for("ja", "zh-Hant")["ジェット"] == hant["Jett"]
        assert store.resolve("CS2").glossary_for("en", "zh-Hant")["AWP"] == "AWP"
        game = store.get("游戏")
        game.glossary.append({"en": "Jett", "zh-Hans": "父的写法"})
        store.save(game)
        assert store.resolve("Valorant").glossary_for("en", "zh-Hans")["Jett"] == "捷风", "子场景的写法应优先"
        print("继承合并：OK")

        # 3. 多语言：日 → 英 借道中文；保留不翻；空格不管；目标是原文语言时为空
        ja_en = eff.glossary_for("ja", "en")
        assert ja_en["ジェット"] == "Jett", ja_en.get("ジェット")
        assert eff.glossary_for("en", "ja")["Jett"] == "ジェット"
        rows = [{"en": "AWP", "zh-Hans": "AWP"}, {"en": "eco", "zh-Hans": "经济局"}, {"ja": "エコ", "zh-Hans": "经济局"},
                {"en": "only-en"}]
        assert glossary_for(rows, "en", "ja") == {"AWP": "AWP", "eco": "エコ"}, glossary_for(rows, "en", "ja")
        assert glossary_for(rows, "ja", "en") == {"エコ": "eco"}
        assert glossary_for(rows, "zh", "en") == {"经济局": "eco", "AWP": "AWP"}, glossary_for(rows, "zh", "en")
        assert glossary_for(rows, "en", "zh-Hans") == {"AWP": "AWP", "eco": "经济局"}
        assert glossary_for(rows, "en", "zh-Hant") == {"AWP": "AWP"}, "没有繁体格、也借不到就不管"
        # 旧格式自动转换
        legacy = normalize_glossary({"Jett": "捷风", "ジェット": "捷风", "AWP": "AWP", "壁抜き": "穿墙", "": "x"})
        assert legacy == [{"en": "Jett", "zh-Hans": "捷风"}, {"ja": "ジェット", "zh-Hans": "捷风"},
                          {"en": "AWP", "zh-Hans": "AWP"}, {"ja": "壁抜き", "zh-Hans": "穿墙"}], legacy
        assert guess_language("안녕") == "ko" and guess_language("構成") == "ja" and guess_language("構成", "zh-Hans") == "zh-Hans"
        merged = merge_rows([{"en": "Jett", "zh-Hans": "捷风"}, {"en": "Sage", "zh-Hans": "贤者"}],
                            [{"en": "Jett", "ja": "ジェット", "zh-Hans": "捷风"}])
        assert merged == [{"en": "Sage", "zh-Hans": "贤者"}, {"en": "Jett", "ja": "ジェット", "zh-Hans": "捷风"}], merged
        print("多语言术语表：OK")

        # 4. 增删改名
        store.create_child("Valorant", "某主播")
        assert store.display_name("某主播") == "游戏 → Valorant → 某主播"
        p = store.get("某主播")
        p.glossary = [{"en": "GG", "zh-Hans": "好局"}]
        p.asr_model = "whisper-1"
        store.save(p)
        eff = store.resolve("某主播")
        g = eff.glossary_for("en", "zh-Hans")
        assert g["GG"] == "好局" and g["Jett"] == "捷风" and eff.asr_model == "whisper-1"
        try:
            store.create_child("游戏", "某主播")
            raise AssertionError("重名应报错")
        except UserFacingError:
            pass
        store.rename("某主播", "主播A")
        assert store.get("主播A") and not store.get("某主播") and store.resolve("主播A").glossary_for("en", "zh-Hans")["GG"] == "好局"
        # 重新读文件，确认都落盘了，而且文件里术语是一行一条
        store2 = ProfileStore(Path(td))
        assert store2.resolve("主播A").glossary_for("en", "zh-Hans")["GG"] == "好局" and store2.get("主播A").parent == "Valorant"
        text = (Path(td) / "主播A.yaml").read_text(encoding="utf-8")
        assert "- {en: GG, zh-Hans: 好局}" in text, text
        store2.delete("游戏")
        assert not store2.get("Valorant") and not store2.get("主播A"), "删父场景应连带删子场景"
        try:
            store2.delete(ROOT_NAME)
            raise AssertionError("根不能删")
        except UserFacingError:
            pass
        print("增删改名与落盘：OK")

        # 5. CSV / Excel 导入导出
        csv_path = Path(td) / "术语.csv"
        rows = [{"en": "AWP", "zh-Hans": "AWP"}, {"en": "eco", "ja": "エコ", "zh-Hans": "经济局"}, {"en": "rush B", "zh-Hans": "冲 B"}]
        export_glossary(csv_path, rows, {"en": "英语", "ja": "日语", "zh-Hans": "简体中文", "zh-Hant": "繁体中文", "ko": "韩语"})
        assert import_glossary(csv_path) == rows, import_glossary(csv_path)
        # 英文表头也认
        (Path(td) / "en.csv").write_text("English,Japanese,Simplified Chinese\nJett,ジェット,捷风\n", encoding="utf-8")
        assert import_glossary(Path(td) / "en.csv") == [{"en": "Jett", "ja": "ジェット", "zh-Hans": "捷风"}]
        # 旧格式：没有表头、GBK 编码的两列 CSV
        gbk = Path(td) / "gbk.csv"
        gbk.write_bytes("flash,闪光\nスモーク,烟\n".encode("gb18030"))
        assert import_glossary(gbk) == [{"en": "flash", "zh-Hans": "闪光"}, {"ja": "スモーク", "zh-Hans": "烟"}], import_glossary(gbk)
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["原文", "译文"])
        ws.append(["clutch", "残局"])
        ws.append(["ace", "五杀"])
        ws.append([None, "空行跳过"])
        xlsx = Path(td) / "术语.xlsx"
        wb.save(str(xlsx))
        assert import_glossary(xlsx) == [{"en": "clutch", "zh-Hans": "残局"}, {"en": "ace", "zh-Hans": "五杀"}]
        try:
            import_glossary(Path(td) / "不存在.csv")
            raise AssertionError
        except UserFacingError:
            pass
        print("CSV / Excel 导入导出：OK")

        # 6. 预置升级：用户没改过的预置会被新版本覆盖，改过的不动；旧格式文件能读
        store4 = ProfileStore(Path(td))
        cs2 = store4.get("CS2")
        assert cs2 and not cs2.user_modified and cs2.preset_version >= 3
        val = store4.get("Valorant")
        val.glossary.append({"en": "我自己加的", "zh-Hans": "x"})
        store4.save(val)                       # 用户改了 Valorant
        import yaml
        for n in ("CS2", "Valorant"):
            f = Path(td) / f"{n}.yaml"
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
            d["preset_version"] = 0           # 假装是旧版本
            d["glossary"] = {"old": "旧"}      # 旧格式
            f.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        store5 = ProfileStore(Path(td))
        assert "Mirage" in store5.resolve("CS2").glossary_for("en", "zh-Hans"), "没改过的预置应被升级"
        assert store5.get("Valorant").glossary == [{"en": "old", "zh-Hans": "旧"}], "用户改过的不应被覆盖，旧格式应转换"
        print("预置升级：OK")

        # 7. 坏文件不影响启动
        (Path(td) / "坏.yaml").write_text("name: [unclosed", encoding="utf-8")
        store3 = ProfileStore(Path(td))
        assert ROOT_NAME in store3.profiles
        from app.core.asr.openai_asr import terms_for_language
        mixed = ["Jett", "ジェット", "AWP", "KAY/O", "エコ", "Ascent"]
        assert terms_for_language(mixed, "ja") == ["ジェット", "AWP", "KAY/O", "エコ"], terms_for_language(mixed, "ja")
        assert terms_for_language(mixed, "en") == ["Jett", "AWP", "KAY/O", "Ascent"]
        assert terms_for_language(mixed, None) == mixed
        print("提示词按语言过滤：OK")
        print("坏文件容错：OK")
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
