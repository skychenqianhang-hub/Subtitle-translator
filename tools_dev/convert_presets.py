"""一次性工具：把 profiles/*.yaml 里旧格式的术语表（原文: 译文）改成多语言行，保留注释行，版本号 +1。

用法（项目根目录）：python tools_dev/convert_presets.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.profiles.glossary import normalize_glossary  # noqa: E402

NEW_VERSION = 3


def flow(row: dict) -> str:
    return yaml.safe_dump(row, default_flow_style=True, allow_unicode=True, width=10000).strip()


def convert(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    i = 0
    count = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^preset_version:\s*(\d+)", line)
        if m:
            out.append(f"preset_version: {NEW_VERSION}")
            i += 1
            continue
        if line.startswith("glossary:"):
            if line.strip() == "glossary: {}":
                out.append("glossary: []")
                i += 1
                continue
            out.append("glossary:")
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                raw = lines[i]
                if raw.strip().startswith("#") or not raw.strip():
                    out.append(raw.replace("  #", "#", 1) if raw.startswith("  #") else raw)
                else:
                    pair = yaml.safe_load(raw)
                    assert isinstance(pair, dict) and len(pair) == 1, raw
                    for row in normalize_glossary(pair):
                        out.append("- " + flow(row))
                        count += 1
                i += 1
            continue
        out.append(line)
        i += 1
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    # 验证能读回来
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data.get("glossary"), list)
    assert len(data["glossary"]) == count, (path, len(data["glossary"]), count)
    return count


def main() -> int:
    for f in sorted((ROOT / "profiles").glob("*.yaml")):
        n = convert(f)
        print(f"{f.name}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
