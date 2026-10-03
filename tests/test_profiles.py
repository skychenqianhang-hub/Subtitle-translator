"""场景数据层自检：继承合并、增删改名、文件读写、CSV / Excel 导入导出。

运行：python -m tests.test_profiles
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.core.errors import UserFacingError
from app.core.profiles.glossary_io import export_csv, import_pairs
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
        assert eff.glossary["Jett"] == "捷风" and eff.glossary["GG"] == "GG", "应合并父场景术语"
        assert eff.glossary["ジェット"] == "捷风" and eff.glossary["エコ"] == "经济局", "日文词条也应在"
        assert len(eff.glossary) > 250, len(eff.glossary)
        assert store.resolve("CS2").glossary["Mirage"] == "荒漠迷城" and store.resolve("CS2").glossary["デグル"] == "沙鹰"
        assert eff.style and "游戏" in eff.style, "风格应从「游戏」继承"
        assert "Jett" in eff.asr_prompt and "GG" in eff.asr_prompt
        assert eff.corrections["jet"] == "Jett"
        game = store.get("游戏")
        game.glossary["Jett"] = "父的写法"
        store.save(game)
        assert store.resolve("Valorant").glossary["Jett"] == "捷风", "子场景的写法应优先"
        print("继承合并：OK")

        # 3. 增删改名
        store.create_child("Valorant", "某主播")
        assert store.display_name("某主播") == "游戏 → Valorant → 某主播"
        p = store.get("某主播")
        p.glossary = {"GG": "好局"}
        p.asr_model = "whisper-1"
        store.save(p)
        eff = store.resolve("某主播")
        assert eff.glossary["GG"] == "好局" and eff.glossary["Jett"] == "捷风" and eff.asr_model == "whisper-1"
        try:
            store.create_child("游戏", "某主播")
            raise AssertionError("重名应报错")
        except UserFacingError:
            pass
        store.rename("某主播", "主播A")
        assert store.get("主播A") and not store.get("某主播") and store.resolve("主播A").glossary["GG"] == "好局"
        # 重新读文件，确认都落盘了
        store2 = ProfileStore(Path(td))
        assert store2.resolve("主播A").glossary["GG"] == "好局" and store2.get("主播A").parent == "Valorant"
        store2.delete("游戏")
        assert not store2.get("Valorant") and not store2.get("主播A"), "删父场景应连带删子场景"
        try:
            store2.delete(ROOT_NAME)
            raise AssertionError("根不能删")
        except UserFacingError:
            pass
        print("增删改名与落盘：OK")

        # 4. CSV / Excel 导入导出
        csv_path = Path(td) / "术语.csv"
        export_csv(csv_path, {"AWP": "AWP", "eco": "经济局", "rush B": "冲 B"})
        pairs = import_pairs(csv_path)
        assert pairs == {"AWP": "AWP", "eco": "经济局", "rush B": "冲 B"}, pairs
        # 没有表头、GBK 编码的 CSV
        gbk = Path(td) / "gbk.csv"
        gbk.write_bytes("闪光,flash\n烟,smoke\n".encode("gb18030"))
        assert import_pairs(gbk) == {"闪光": "flash", "烟": "smoke"}
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["原文", "译文"])
        ws.append(["clutch", "残局"])
        ws.append(["ace", "五杀"])
        ws.append([None, "空行跳过"])
        xlsx = Path(td) / "术语.xlsx"
        wb.save(str(xlsx))
        assert import_pairs(xlsx) == {"clutch": "残局", "ace": "五杀"}
        try:
            import_pairs(Path(td) / "不存在.csv")
            raise AssertionError
        except UserFacingError:
            pass
        print("CSV / Excel 导入导出：OK")

        # 5. 预置升级：用户没改过的预置会被新版本覆盖，改过的不动
        store4 = ProfileStore(Path(td))
        cs2 = store4.get("CS2")
        assert cs2 and not cs2.user_modified and cs2.preset_version >= 2
        val = store4.get("Valorant")
        val.glossary["我自己加的"] = "x"
        store4.save(val)                       # 用户改了 Valorant
        import yaml
        for n in ("CS2", "Valorant"):
            f = Path(td) / f"{n}.yaml"
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
            d["preset_version"] = 0           # 假装是旧版本
            d["glossary"] = {"old": "旧"}
            f.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        store5 = ProfileStore(Path(td))
        assert "Mirage" in store5.get("CS2").glossary, "没改过的预置应被升级"
        assert store5.get("Valorant").glossary == {"old": "旧"}, "用户改过的不应被覆盖"
        print("预置升级：OK")

        # 6. 坏文件不影响启动
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
