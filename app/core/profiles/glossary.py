"""多语言术语表。

一行 = 同一个词在各语言里的写法，例如 {"en": "Jett", "ja": "ジェット", "zh-Hans": "捷风"}。
翻译时按「原文语言 → 翻译至」取对应两列，拼成 {原文词: 译文词} 交给翻译模型；某格留空就不管这个方向。
旧格式（{原文: 中文译文}）读入时自动转成新格式：原文按文字判断是英文还是日文，译文归到简体中文。
"""
from __future__ import annotations

import re

# 术语表的列，顺序也是界面上的顺序
GLOSSARY_LANGS = ["en", "ja", "zh-Hans", "zh-Hant", "ko"]

_KANA = re.compile(r"[぀-ヿ]")
_HAN = re.compile(r"[㐀-鿿]")
_HANGUL = re.compile(r"[가-힯]")
_LATIN = re.compile(r"[A-Za-z]")

Row = dict[str, str]


def guess_language(text: str, prefer_han: str = "ja") -> str:
    """按文字猜一个词是哪种语言。只有汉字时分不清中日，由 prefer_han 决定。"""
    if _HANGUL.search(text):
        return "ko"
    if _KANA.search(text):
        return "ja"
    if _HAN.search(text):
        return prefer_han
    if _LATIN.search(text):
        return "en"
    return "en"


def source_columns(source_language: str) -> list[str]:
    """原文语言对应术语表里的哪几列。"""
    if source_language == "zh":
        return ["zh-Hans", "zh-Hant"]
    if source_language in GLOSSARY_LANGS:
        return [source_language]
    return list(GLOSSARY_LANGS)          # auto 或不认识的：所有列都算原文


def clean_row(row: dict) -> Row:
    return {str(k): str(v).strip() for k, v in row.items() if k in GLOSSARY_LANGS and v is not None and str(v).strip()}


def normalize_glossary(raw, prefer_han: str = "ja") -> list[Row]:
    """文件里读出来的 glossary（新格式列表或旧格式字典）→ 行列表。"""
    rows: list[Row] = []
    if isinstance(raw, dict):                      # 旧格式：{原文: 译文}，译文是简体中文
        for k, v in raw.items():
            k, v = str(k).strip(), ("" if v is None else str(v)).strip()
            if not k:
                continue
            lang = guess_language(k, prefer_han)
            row = {lang: k}
            if v:
                if v == k:
                    row["zh-Hans"] = v             # 「保留不翻」：各语言写法相同
                elif lang == "zh-Hans":
                    row = {"ja": k, "zh-Hans": v}  # 键和值都是汉字：键按日文处理
                else:
                    row["zh-Hans"] = v
            rows.append(row)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                row = clean_row(item)
                if row:
                    rows.append(row)
    return rows


def _cells(row: Row) -> set[tuple[str, str]]:
    return {(lang, term) for lang, term in row.items() if term}


def _key_cell(row: Row) -> tuple[str, str] | None:
    """一行的「身份」：按列顺序第一个填了的格子。"""
    for lang in GLOSSARY_LANGS:
        if row.get(lang):
            return (lang, row[lang])
    return None


def _same_entry(a: Row, b: Row) -> bool:
    """两行算同一条：某一格相同，而且这一格是其中一行的身份格。
    这样 {en: Jett, zh-Hans: 捷风} 和 {ja: ジェット, zh-Hans: 捷风} 只是译文相同，可以并存；
    子场景的 {en: Jett, zh-Hans: 别的写法} 则会替换父场景的 Jett。"""
    shared = _cells(a) & _cells(b)
    return bool(shared) and bool(shared & {_key_cell(a), _key_cell(b)})


def merge_rows(base: list[Row], override: list[Row]) -> list[Row]:
    """子场景（或导入的表）的行替换父场景里同一条的行；其余追加；完全相同的只留一份。"""
    out = [dict(r) for r in base]
    for new in override:
        if not _cells(new):
            continue
        out = [r for r in out if r != new and not _same_entry(r, new)]
        out.append(dict(new))
    return out


def row_terms(rows: list[Row]) -> set[str]:
    """所有格子里的词（给场景自动判断用）。"""
    return {term for r in rows for term in r.values() if term}


def glossary_for(rows: list[Row], source_language: str, target_language: str) -> dict[str, str]:
    """拼成 {原文词: 译文词}。

    目标格为空时：
    - 这一行填了的格子写法全部相同（例如 AWP / AWP）→ 视为「保留不翻」；
    - 否则找「有任何一格相同」的另一行借它的目标格（Jett ↔ 捷风 ↔ ジェット 这样绕一道）。
    """
    srcs = source_columns(source_language)
    tgt = target_language if target_language in GLOSSARY_LANGS else "zh-Hans"
    # 索引：某一格 → 这一格所在的所有行
    index: dict[tuple[str, str], list[Row]] = {}
    for r in rows:
        for cell in _cells(r):
            index.setdefault(cell, []).append(r)

    def target_of(row: Row) -> str:
        if row.get(tgt):
            return row[tgt]
        values = {v for v in row.values() if v}
        if len(values) == 1 and len(row) >= 2:
            return next(iter(values))
        for cell in _cells(row):
            for other in index.get(cell, []):
                if other is not row and other.get(tgt):
                    return other[tgt]
        return ""

    out: dict[str, str] = {}
    for r in rows:
        t = target_of(r)
        if not t:
            continue
        for lang in srcs:
            term = r.get(lang)
            if term and lang != tgt:
                out[term] = t              # 后面的行（子场景 / 后导入的）优先
    return out
