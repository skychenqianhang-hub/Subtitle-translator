"""一次性工具：把预置词表里译名相同的英文行和日文行合成一行（Jett | ジェット | 捷风）。

只合并「这个译名恰好对应 1 个英文词 + 1 个日文词」的情况；一个译名对应多个英文或多个日文词的
（例如 点射 ← tap / burst / タップ撃ち / バースト）分不清谁配谁，保持原样，等人工校对。
合并后的行放在原来英文行的位置，日文行删掉；注释行保留；preset_version +1。

用法（项目根目录）：python tools_dev/merge_preset_rows.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def flow(row: dict) -> str:
    return yaml.safe_dump(row, default_flow_style=True, allow_unicode=True, width=10000).strip()


def process(path: Path) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    # 先收集 glossary 段里的行：(行号, row)
    entries: list[tuple[int, dict]] = []
    in_gl = False
    for i, line in enumerate(lines):
        if line.startswith("glossary:"):
            in_gl = True
            continue
        if in_gl:
            if line.startswith("- "):
                entries.append((i, yaml.safe_load(line[2:])))
            elif line and not line.startswith("#"):
                in_gl = False
    by_zh: dict[str, list[tuple[int, dict]]] = {}
    for i, row in entries:
        if row.get("zh-Hans") and len(row) == 2:
            by_zh.setdefault(row["zh-Hans"], []).append((i, row))
    merged = 0
    ambiguous = 0
    replace: dict[int, dict] = {}
    drop: set[int] = set()
    for zh, group in by_zh.items():
        en = [(i, r) for i, r in group if "en" in r]
        ja = [(i, r) for i, r in group if "ja" in r]
        if not en or not ja:
            continue
        if len(en) == 1 and len(ja) == 1:
            (ie, re_), (ij, rj) = en[0], ja[0]
            replace[ie] = {"en": re_["en"], "ja": rj["ja"], "zh-Hans": zh}
            drop.add(ij)
            merged += 1
        else:
            ambiguous += 1
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in drop:
            continue
        if i in replace:
            out.append("- " + flow(replace[i]))
            continue
        m = re.match(r"^preset_version:\s*(\d+)", line)
        if m and merged:
            out.append(f"preset_version: {int(m.group(1)) + 1}")
            continue
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    yaml.safe_load(path.read_text(encoding="utf-8"))      # 确认还能读
    return merged, ambiguous


def main() -> int:
    for f in sorted((ROOT / "profiles").glob("*.yaml")):
        merged, ambiguous = process(f)
        print(f"{f.name}: merged {merged}, ambiguous {ambiguous}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
