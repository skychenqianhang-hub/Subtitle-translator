"""内容场景的临时数据（阶段 3 会改成从 profiles/ 目录读取 YAML）。

结构：板块 → 子板块。「通用」没有子板块。
"""
from __future__ import annotations

DEFAULT_SCENE_TREE: dict[str, list[str]] = {
    "通用": [],
    "游戏": ["Valorant", "CS2"],
    "电影": ["Odyssey"],
}


def scene_tree() -> dict[str, list[str]]:
    return {k: list(v) for k, v in DEFAULT_SCENE_TREE.items()}


def scene_display_name(section: str, sub: str) -> str:
    return f"{section} → {sub}" if sub else section
