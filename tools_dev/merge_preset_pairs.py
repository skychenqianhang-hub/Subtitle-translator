"""一次性工具（接 merge_preset_rows.py）：把分不清谁配谁的英 / 日行按人工指定的配对合并。

配对依据：日文片假名就是英文词的音译（Deagle ↔ デグル、tap ↔ タップ撃ち）。没列出来的保持原样。
用法（项目根目录）：python tools_dev/merge_preset_pairs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

PAIRS: dict[str, list[tuple[str, str]]] = {
    "CS2.yaml": [
        ("Deagle", "デグル"), ("Desert Eagle", "デザートイーグル"), ("Scout", "スカウト"), ("kit", "キット"),
        ("armor", "アーマー"), ("Dust 2", "ダスト2"), ("plant", "プラント"), ("defuse", "ディフューズ"),
        ("rotate", "ローテート"), ("eco", "エコ"), ("force buy", "フォースバイ"), ("trade", "トレード"),
        ("tap", "タップ撃ち"), ("burst", "バースト"), ("smoke", "スモーク"), ("molly", "モリー"),
        ("nade", "グレ"), ("utility", "ユーティリティ"),
    ],
    "Valorant.yaml": [
        ("Brimstone", "ブリムストーン"), ("Killjoy", "キルジョイ"), ("Operator", "オペレーター"),
        ("plant", "プラント"), ("rotate", "ローテート"), ("ability", "アビリティ"), ("utility", "ユーティリティ"),
        ("smoke", "スモーク"), ("first blood", "ファーストブラッド"), ("tap", "タップ撃ち"), ("burst", "バースト"),
        ("comp", "コンポジション"),
    ],
    "游戏.yaml": [
        ("respawn", "リスポーン"), ("cooldown", "クールダウン"), ("headshot", "ヘッドショット"),
        ("camping", "キャンプ"), ("cheater", "チーター"),
    ],
}


def flow(row: dict) -> str:
    return yaml.safe_dump(row, default_flow_style=True, allow_unicode=True, width=10000).strip()


def process(path: Path, pairs: list[tuple[str, str]]) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: dict[int, dict] = {}
    for i, line in enumerate(lines):
        if line.startswith("- {"):
            rows[i] = yaml.safe_load(line[2:])
    done = 0
    for en, ja in pairs:
        ie = next((i for i, r in rows.items() if r.get("en") == en and "ja" not in r), None)
        ij = next((i for i, r in rows.items() if r.get("ja") == ja and "en" not in r), None)
        if ie is None or ij is None:
            print(f"  跳过 {en} / {ja}（找不到或已合并）")
            continue
        assert rows[ie].get("zh-Hans") == rows[ij].get("zh-Hans"), (en, ja)
        rows[ie] = {"en": en, "ja": ja, "zh-Hans": rows[ie]["zh-Hans"]}
        lines[ie] = "- " + flow(rows[ie])
        lines[ij] = None
        del rows[ij]
        done += 1
    path.write_text("\n".join(x for x in lines if x is not None) + "\n", encoding="utf-8")
    yaml.safe_load(path.read_text(encoding="utf-8"))
    return done


def main() -> int:
    for name, pairs in PAIRS.items():
        n = process(ROOT / "profiles" / name, pairs)
        print(f"{name}: merged {n}/{len(pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
