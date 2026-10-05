"""场景自动判断：根据识别出来的文字，看哪个场景的专有词出现得最多。

不调用任何云端模型，纯本地、即时、免费。原理：
- 每个场景有自己的「特征词」= 它自己的术语表原文 + 识别提示词 + 纠错规则的正确写法（不含继承来的）
- 只属于一个场景的词分量重（比如 Jett、アセント 只在 Valorant 里），几个场景共有的词分量轻（eco、plant）
- 要有足够多、足够不同的特征词出现才切换；两个兄弟场景分不出高下时退回它们共同的父场景
- 证据不足时保持当前场景不动（防止来回跳）
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.profiles.store import ROOT_NAME, ProfileStore

_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")

MIN_SCORE = 4.0          # 至少这么多分才认定
MIN_DISTINCT = 3         # 至少命中这么多个不同的词
DOMINANCE = 1.5          # 第一名要比第二名高出这么多倍才算分出高下


@dataclass
class _Term:
    text: str
    weight: float
    pattern: re.Pattern | None   # 拉丁词用带边界的正则；中日韩词直接子串匹配


class SceneDetector:
    def __init__(self, store: ProfileStore) -> None:
        self.store = store
        self.terms: dict[str, list[_Term]] = {}
        self._build()

    # ------------------------------------------------------------ 建索引
    def _own_terms(self, name: str) -> set[str]:
        p = self.store.get(name)
        if p is None:
            return set()
        raw = set(p.glossary.keys()) | set(p.asr_prompt) | set(p.corrections.values())
        out: set[str] = set()
        for t in raw:
            t = t.strip()
            if not t:
                continue
            if _CJK.search(t):
                if len(t) >= 2:
                    out.add(t)
            elif len(t) >= 2:
                out.add(t.lower())
        return out

    def _build(self) -> None:
        own = {n: self._own_terms(n) for n in self.store.profiles if n != ROOT_NAME}
        owners: dict[str, int] = {}
        for terms in own.values():
            for t in terms:
                owners[t] = owners.get(t, 0) + 1
        self.terms = {}
        for name, terms in own.items():
            lst: list[_Term] = []
            for t in terms:
                n = owners[t]
                weight = 2.0 if n == 1 else 1.0 / n
                # 很短的拉丁词（AK、CT、T）太容易误中，降权
                if not _CJK.search(t) and len(t) <= 2:
                    weight *= 0.25
                if _CJK.search(t):
                    lst.append(_Term(t, weight, None))
                else:
                    lst.append(_Term(t, weight, re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])")))
            self.terms[name] = lst

    # ------------------------------------------------------------ 打分
    def scores(self, text: str) -> dict[str, tuple[float, int]]:
        """返回 {场景: (分数, 命中的不同词数)}。"""
        lower = text.lower()
        out: dict[str, tuple[float, int]] = {}
        for name, terms in self.terms.items():
            score = 0.0
            distinct = 0
            for t in terms:
                if t.pattern is None:
                    n = text.count(t.text)
                else:
                    n = len(t.pattern.findall(lower))
                if n:
                    distinct += 1
                    score += t.weight * min(n, 3)     # 同一个词反复出现最多算 3 次
            if score > 0:
                out[name] = (score, distinct)
        return out

    def choose(self, text: str, current: str = ROOT_NAME) -> str:
        """根据最近的文字决定用哪个场景；证据不足就返回 current。"""
        sc = self.scores(text)
        strong = {n: s for n, (s, d) in sc.items() if s >= MIN_SCORE and d >= MIN_DISTINCT}
        if not strong:
            return current if current in self.store.profiles else ROOT_NAME
        ranked = sorted(strong.items(), key=lambda kv: kv[1], reverse=True)
        best, best_score = ranked[0]
        # 父子关系的不算竞争（子场景命中多时，父场景的通用词通常也命中）
        rivals = [(n, s) for n, s in ranked[1:] if not self._related(best, n)]
        if not rivals or best_score >= rivals[0][1] * DOMINANCE:
            return self._deepest(best, strong)
        # 分不出高下：退回共同的父场景
        return self._common_parent(best, rivals[0][0])

    def _related(self, a: str, b: str) -> bool:
        pa, pb = self.store.path(a), self.store.path(b)
        return a in pb or b in pa

    def _deepest(self, name: str, strong: dict[str, float]) -> str:
        """如果它的某个后代也有足够证据，用后代（更具体）。"""
        best, best_score = name, 0.0
        for d in self.store.descendants(name):
            if d.name in strong and strong[d.name] > best_score:
                best, best_score = d.name, strong[d.name]
        return best

    def _common_parent(self, a: str, b: str) -> str:
        pa, pb = self.store.path(a), self.store.path(b)
        common = ROOT_NAME
        for x, y in zip(pa, pb):
            if x == y:
                common = x
            else:
                break
        return common
