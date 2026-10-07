"""内容场景（Profile）：树状结构，子场景继承父场景；术语表、纠错规则、识别提示词按「合并」继承。

每个场景一个 YAML 文件，放在用户配置目录 %APPDATA%\\SubTranslator\\profiles\\ 下。
程序自带的预置场景在项目的 profiles/ 文件夹里，首次运行时复制过去。
"""
from __future__ import annotations

from app.i18n import tr

import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import config_dir
from app.core.errors import UserFacingError
from app.core.profiles.glossary import Row, glossary_for, merge_rows, normalize_glossary

ROOT_NAME = "通用"
AUTO_SCENE = "__auto__"                 # 场景选「自动」时保存的值
AUTO_LABEL = "自动（按内容判断）"


@dataclass
class Profile:
    name: str
    parent: str | None = None                 # 父场景名；根场景为 None
    asr_model: str | None = None              # None = 继承
    translate_provider: str | None = None     # None = 继承
    translate_model: str | None = None        # None = 继承
    asr_prompt: list[str] = field(default_factory=list)     # 专有名词提示（合并继承）
    corrections: dict[str, str] = field(default_factory=dict)  # 听错 → 正确（合并继承）
    glossary: list[Row] = field(default_factory=list)          # 多语言术语行（合并继承，子覆盖父），见 glossary.py
    style: str | None = None                  # 翻译风格（覆盖继承）
    description: str = ""
    preset_version: int = 0                   # 程序自带预置的版本号；0 = 用户自建
    user_modified: bool = False               # 用户在界面里改过 → 以后预置升级不覆盖

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "parent": self.parent,
            "preset_version": self.preset_version,
            "user_modified": self.user_modified,
            "asr_model": self.asr_model,
            "translate_provider": self.translate_provider,
            "translate_model": self.translate_model,
            "asr_prompt": list(self.asr_prompt),
            "corrections": dict(self.corrections),
            "glossary": [dict(r) for r in self.glossary],
            "style": self.style,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        prompt = d.get("asr_prompt") or []
        if isinstance(prompt, str):
            prompt = [p.strip() for p in re.split(r"[,，;；\n]+", prompt) if p.strip()]
        return cls(
            name=str(d.get("name", "")).strip(),
            parent=(str(d["parent"]).strip() if d.get("parent") else None),
            asr_model=d.get("asr_model") or None,
            translate_provider=d.get("translate_provider") or None,
            translate_model=d.get("translate_model") or None,
            asr_prompt=[str(p) for p in prompt],
            corrections={str(k): str(v) for k, v in (d.get("corrections") or {}).items()},
            glossary=normalize_glossary(d.get("glossary")),
            style=d.get("style") or None,
            description=str(d.get("description") or ""),
            preset_version=int(d.get("preset_version") or 0),
            user_modified=bool(d.get("user_modified", False)),
        )


@dataclass
class EffectiveProfile:
    """继承合并后的结果，交给翻译流程用。"""
    name: str
    path: list[str]                 # 从根到自己，例如 ["通用", "游戏", "Valorant"]
    asr_model: str | None
    translate_provider: str | None
    translate_model: str | None
    asr_prompt: list[str]
    corrections: dict[str, str]
    glossary: list[Row]
    style: str

    def glossary_for(self, source_language: str, target_language: str) -> dict[str, str]:
        """按「原文语言 → 翻译至」拼成交给翻译模型的 {原文词: 译文词}。"""
        return glossary_for(self.glossary, source_language, target_language)

    @property
    def display_name(self) -> str:
        return " → ".join(tr(x) for x in self.path[1:]) if len(self.path) > 1 else tr(self.path[0])


# 预置场景的名字要进翻译清单（下面这个函数不会被调用，只是让提取工具看到这几个词）
_PRESET_SCENE_NAMES = lambda: [tr("通用"), tr("游戏"), tr("电影"), tr("自动（按内容判断）")]  # noqa: E731


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return cleaned or "scene"


def bundled_profiles_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "profiles"


def user_profiles_dir() -> Path:
    return config_dir() / "profiles"


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory or user_profiles_dir()
        self.profiles: dict[str, Profile] = {}
        self.load()

    # ------------------------------------------------------------ 读写
    def load(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._sync_bundled()
        self.profiles = {}
        for f in sorted(self.dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                p = Profile.from_dict(data)
            except Exception:  # noqa: BLE001  坏文件跳过，不让整个软件起不来
                continue
            if p.name:
                self.profiles[p.name] = p
        if ROOT_NAME not in self.profiles:
            self.profiles[ROOT_NAME] = Profile(name=ROOT_NAME, description="所有场景的父场景")
            self._write(self.profiles[ROOT_NAME])
        # 预置文件里的注释行不会被 YAML 保留，没关系：注释只是给人看的
        # 父场景不存在的，挂到根下
        for p in self.profiles.values():
            if p.name != ROOT_NAME and (p.parent is None or p.parent not in self.profiles):
                p.parent = ROOT_NAME

    def _sync_bundled(self) -> None:
        """把程序自带的预置场景同步到用户目录：
        - 用户目录没有的 → 复制
        - 用户目录有、但用户没改过、且自带版本更新 → 覆盖（这样更新软件时词表也会更新）
        - 用户改过的 → 不动
        """
        src = bundled_profiles_dir()
        if not src.is_dir():
            return
        for f in src.glob("*.yaml"):
            dst = self.dir / f.name
            if not dst.exists():
                shutil.copy(f, dst)
                continue
            try:
                mine = Profile.from_dict(yaml.safe_load(dst.read_text(encoding="utf-8")) or {})
                theirs = Profile.from_dict(yaml.safe_load(f.read_text(encoding="utf-8")) or {})
            except Exception:  # noqa: BLE001
                continue
            if not mine.user_modified and theirs.preset_version > mine.preset_version:
                shutil.copy(f, dst)

    def _path_for(self, name: str) -> Path:
        return self.dir / f"{_safe_filename(name)}.yaml"

    def _write(self, p: Profile) -> None:
        d = p.to_dict()
        rows = d.pop("glossary")
        text = yaml.safe_dump(d, allow_unicode=True, sort_keys=False, default_flow_style=False)
        # 术语表一行一条 {en: Jett, zh-Hans: 捷风}，比每格一行好读
        if rows:
            text += "glossary:\n" + "".join(
                "- " + yaml.safe_dump(r, default_flow_style=True, allow_unicode=True, width=10000).strip() + "\n"
                for r in rows)
        else:
            text += "glossary: []\n"
        self._path_for(p.name).write_text(text, encoding="utf-8")

    def save(self, p: Profile, from_user: bool = True) -> None:
        if not p.name.strip():
            raise UserFacingError(tr("场景名不能为空。"))
        if from_user:
            p.user_modified = True
        self.profiles[p.name] = p
        self._write(p)

    # ------------------------------------------------------------ 结构
    def get(self, name: str) -> Profile | None:
        return self.profiles.get(name)

    def children(self, name: str) -> list[Profile]:
        return sorted((p for p in self.profiles.values() if p.parent == name), key=lambda p: p.name)

    def path(self, name: str) -> list[str]:
        out: list[str] = []
        cur = self.profiles.get(name)
        seen: set[str] = set()
        while cur is not None and cur.name not in seen:
            out.append(cur.name)
            seen.add(cur.name)
            cur = self.profiles.get(cur.parent) if cur.parent else None
        return list(reversed(out))

    def display_name(self, name: str) -> str:
        """给人看的名字：「游戏 → Valorant」。预置场景的名字跟随界面语言，用户自建的原样显示。"""
        if name == AUTO_SCENE:
            return tr(AUTO_LABEL)
        path = self.path(name)
        if len(path) > 1:
            return " → ".join(tr(x) for x in path[1:])
        return tr(path[0]) if path else name

    def descendants(self, name: str) -> list[Profile]:
        out: list[Profile] = []
        for c in self.children(name):
            out.append(c)
            out.extend(self.descendants(c.name))
        return out

    def all_names_in_tree_order(self) -> list[str]:
        return [ROOT_NAME] + [p.name for p in self.descendants(ROOT_NAME)]

    def create_child(self, parent: str, name: str) -> Profile:
        name = name.strip()
        if not name:
            raise UserFacingError(tr("场景名不能为空。"))
        if name in self.profiles:
            raise UserFacingError(tr("已经有一个叫「{0}」的场景了，换个名字。", name))
        if parent not in self.profiles:
            raise UserFacingError(tr("父场景「{0}」不存在。", parent))
        p = Profile(name=name, parent=parent)
        self.save(p)
        return p

    def rename(self, old: str, new: str) -> None:
        new = new.strip()
        if old == ROOT_NAME:
            raise UserFacingError(tr("「通用」是根场景，不能改名。"))
        if not new:
            raise UserFacingError(tr("场景名不能为空。"))
        if new in self.profiles and new != old:
            raise UserFacingError(tr("已经有一个叫「{0}」的场景了。", new))
        p = self.profiles.pop(old)
        self._path_for(old).unlink(missing_ok=True)
        p.name = new
        for c in self.profiles.values():
            if c.parent == old:
                c.parent = new
                self._write(c)
        self.save(p)

    def delete(self, name: str) -> None:
        if name == ROOT_NAME:
            raise UserFacingError(tr("「通用」是根场景，不能删除。"))
        if name not in self.profiles:
            return
        # 子场景一起删
        for d in self.descendants(name):
            self.profiles.pop(d.name, None)
            self._path_for(d.name).unlink(missing_ok=True)
        self.profiles.pop(name, None)
        self._path_for(name).unlink(missing_ok=True)

    # ------------------------------------------------------------ 继承合并
    def resolve(self, name: str) -> EffectiveProfile:
        if name == AUTO_SCENE:
            name = ROOT_NAME               # 自动模式一开始先用「通用」，判断出来再换
        path = self.path(name) or [ROOT_NAME]
        asr_model = translate_provider = translate_model = None
        style = ""
        prompt: list[str] = []
        corrections: dict[str, str] = {}
        glossary: list[Row] = []
        for n in path:                      # 从根到叶，后面的覆盖前面的
            p = self.profiles.get(n)
            if p is None:
                continue
            if p.asr_model:
                asr_model = p.asr_model
            if p.translate_provider:
                translate_provider = p.translate_provider
            if p.translate_model:
                translate_model = p.translate_model
            if p.style:
                style = p.style
            for t in p.asr_prompt:
                if t and t not in prompt:
                    prompt.append(t)
            corrections.update({k: v for k, v in p.corrections.items() if k})
            glossary = merge_rows(glossary, p.glossary)
        return EffectiveProfile(
            name=name, path=path, asr_model=asr_model, translate_provider=translate_provider,
            translate_model=translate_model, asr_prompt=prompt, corrections=corrections,
            glossary=glossary, style=style,
        )
