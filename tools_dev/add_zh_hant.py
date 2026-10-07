"""一次性工具：给预置词表补繁体中文列（台港澳服 / 台灣玩家用語）。

来源优先级：
1. 官方译名（valorant_zh_hant.json / cs2_zh_hant.json / odyssey_zh_hant.json，按英文词查）
2. 人工校过的台湾玩家用语（slang_zh_hant.json，按简体值查）
3. OpenCC s2twp 机器转换（opencc_draft.json，按简体值查）
保留注释行；preset_version +1。

用法（项目根目录）：python tools_dev/add_zh_hant.py <放 json 的文件夹>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_FILES = {"Valorant": "valorant_zh_hant.json", "CS2": "cs2_zh_hant.json", "Odyssey": "odyssey_zh_hant.json"}


def flow(row: dict) -> str:
    ordered = {k: row[k] for k in ("en", "ja", "zh-Hans", "zh-Hant", "ko") if k in row}
    return yaml.safe_dump(ordered, default_flow_style=True, allow_unicode=True, width=10000).strip()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def process(name: str, src: Path) -> tuple[int, int, list[str]]:
    path = ROOT / "profiles" / f"{name}.yaml"
    official = {k: v.get("zh_hant", "") for k, v in load(src / OFFICIAL_FILES.get(name, "-")).items()}
    # 官方译名只用在专有名词上；plant / defuse / 攻守方这类战术说法按台湾玩家用语（slang）统一
    skip = {"plant", "defuse", "attackers side", "defenders side", "ultimate / ult"}
    official_lower = {k.lower(): v for k, v in official.items() if v and k.lower() not in skip}
    # 没有英文格的行（ウルト、大招点）按简体值补官方说法
    by_zh = {"大招": official.get("Ultimate / Ult", ""), "大招点": official.get("Ult orb", "")} if name == "Valorant" else {}
    if name == "CS2":
        # 台服 CS2 的武器、地图官方就是英文名（Steam 繁中更新公告、市场都这么写）；装备用官方繁中
        by_zh = {
            "沙鹰": "Desert Eagle", "格洛克": "Glock-18", "双枪": "Dual Berettas", "左轮": "R8 Revolver",
            "鸟狙": "SSG 08", "加利尔": "Galil AR", "法玛斯": "FAMAS", "野牛": "PP-Bizon", "截短霰弹枪": "Sawed-Off",
            "内格夫": "Negev", "电击枪": "Zeus x27", "刀": "軍刀", "拆弹器": "拆彈包", "甲": "防彈背心", "头盔": "頭盔",
            "荒漠迷城": "Mirage", "炼狱小镇": "Inferno", "炙热沙城 2": "Dust II", "核子危机": "Nuke", "远古遗迹": "Ancient",
            "阿努比斯": "Anubis", "殒命大厦": "Vertigo", "死亡游乐园": "Overpass", "列车停放站": "Train",
            "死亡迷城": "Cache", "古堡激战": "Cobblestone", "办公室": "Office",
            "警": "CT", "匪": "T", "警方": "CT 方", "匪方": "T 方", "炸弹": "C4",
            "优先匹配": "優先權模式", "官匹": "競技模式", "加时": "延長賽",
        }
    by_zh = {k: v for k, v in by_zh.items() if v}
    slang = load(src / "slang_zh_hant.json").get(name, {})
    draft = load(src / "opencc_draft.json").get(name, {})
    lines = path.read_text(encoding="utf-8").splitlines()
    filled = missing = 0
    unresolved: list[str] = []
    for i, line in enumerate(lines):
        m = re.match(r"^preset_version:\s*(\d+)", line)
        if m:
            lines[i] = f"preset_version: {int(m.group(1)) + 1}"
            continue
        if not line.startswith("- {"):
            continue
        row = yaml.safe_load(line[2:])
        zh = row.get("zh-Hans")
        if not zh or row.get("zh-Hant"):
            continue
        en = row.get("en", "")
        hant = official_lower.get(en.lower(), "") if (en and name != "CS2") else ""
        if not hant:
            hant = by_zh.get(zh, "") or slang.get(zh, "") or draft.get(zh, "")
        if hant:
            row["zh-Hant"] = hant
            lines[i] = "- " + flow(row)
            filled += 1
        else:
            missing += 1
            unresolved.append(f"{en or row.get('ja')} / {zh}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    yaml.safe_load(path.read_text(encoding="utf-8"))
    return filled, missing, unresolved


def main() -> int:
    src = Path(sys.argv[1])
    for name in ("Valorant", "CS2", "游戏", "Odyssey"):
        filled, missing, unresolved = process(name, src)
        print(f"{name}: filled {filled}, missing {missing}")
        for u in unresolved:
            print("   ", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
