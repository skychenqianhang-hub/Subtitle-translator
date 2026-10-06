"""术语表 / 纠错规则的导入导出：CSV 和 Excel（.xlsx），两列：原文, 译文。"""
from __future__ import annotations

from app.i18n import tr

import csv
from pathlib import Path

from app.core.errors import UserFacingError

_HEADER_WORDS = {"原文", "译文", "source", "target", "term", "translation", "听错", "正确", "wrong", "right", "原词", "改为"}


def _clean_rows(rows: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, (a, b) in enumerate(rows):
        a, b = (a or "").strip(), (b or "").strip()
        if not a:
            continue
        if i == 0 and (a.lower() in _HEADER_WORDS or b.lower() in _HEADER_WORDS):
            continue   # 跳过表头
        out[a] = b
    return out


def import_pairs(path: str | Path) -> dict[str, str]:
    """读 CSV 或 Excel，返回 {原文: 译文}。只看前两列。"""
    p = Path(path)
    if not p.exists():
        raise UserFacingError(tr("找不到文件：{0}", p))
    suffix = p.suffix.lower()
    rows: list[tuple[str, str]] = []
    if suffix in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(p), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            for row in ws.iter_rows(values_only=True):
                if not row:
                    continue
                a = row[0] if len(row) > 0 else ""
                b = row[1] if len(row) > 1 else ""
                rows.append(("" if a is None else str(a), "" if b is None else str(b)))
            wb.close()
        except UserFacingError:
            raise
        except Exception as e:  # noqa: BLE001
            raise UserFacingError(tr("读取 Excel 失败：{0}", e)) from e
    elif suffix in (".csv", ".txt", ".tsv"):
        raw = p.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "gb18030", "shift_jis"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UserFacingError(tr("无法识别这个文件的文字编码，请在 Excel 里另存为 UTF-8 的 CSV。"))
        sample = text[:2000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(text.splitlines(), dialect):
            if not row:
                continue
            a = row[0] if len(row) > 0 else ""
            b = row[1] if len(row) > 1 else ""
            rows.append((a, b))
    else:
        raise UserFacingError(tr("只支持 .csv 和 .xlsx 文件。"))
    result = _clean_rows(rows)
    if not result:
        raise UserFacingError(tr("文件里没有读到任何「原文, 译文」的数据行。"))
    return result


def export_csv(path: str | Path, pairs: dict[str, str], header: tuple[str, str] = ("原文", "译文")) -> Path:
    """导出为 UTF-8（带 BOM）的 CSV，Excel 双击打开不乱码。"""
    p = Path(path)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for k, v in pairs.items():
            w.writerow([k, v])
    return p
