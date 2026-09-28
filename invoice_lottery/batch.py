"""批次對獎：解析 CSV（號碼,日期）並比對。"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .catalog import Catalog, CatalogError
from .periods import Period, parse_date
from .prizes import Win, evaluate, normalize_number

HEADER_WORDS = {"號碼", "發票號碼", "發票", "number", "no", "invoice", "num"}


@dataclass
class Row:
    line: int
    number: str
    date: Optional[date] = None


@dataclass
class Result:
    row: Row
    period: Optional[Period]
    status: str  # 'win' | 'lose' | 'wrong-period' | 'no-data'
    win: Optional[Win] = None
    message: str = ""


def parse_csv(text: str) -> tuple:
    """回傳 (rows, errors)。errors 為 [(行號, 訊息)]，壞掉的行不會中止整個檔案。"""
    if text.startswith("﻿"):
        text = text[1:]
    rows, errors = [], []
    reader = csv.reader(io.StringIO(text))
    seen_data = False
    for cells in reader:
        line = reader.line_num
        cells = [c.strip() for c in cells]
        if not any(cells) or cells[0].startswith("#"):
            continue
        if not seen_data and cells[0].lower() in HEADER_WORDS:
            seen_data = True
            continue
        seen_data = True
        try:
            number = normalize_number(cells[0])
        except ValueError as e:
            errors.append((line, str(e)))
            continue
        d = None
        if len(cells) > 1 and cells[1]:
            try:
                d = parse_date(cells[1])
            except ValueError as e:
                errors.append((line, str(e)))
                continue
        rows.append(Row(line, number, d))
    return rows, errors


def check_rows(rows: list, catalog: Catalog, period: Optional[Period] = None, today: Optional[date] = None) -> list:
    """period 指定時：日期不屬於該期的發票標為錯期、不對獎。
    未指定時：有日期就用日期所屬期別，沒日期用最新一期。"""
    results = []
    today = today or date.today()
    for r in rows:
        if period is not None:
            target = period
            if r.date is not None and not target.contains(r.date):
                actual = Period.from_date(r.date)
                results.append(Result(r, actual, "wrong-period",
                                      message=f"發票日期 {r.date} 屬於 {actual.key}，不是 {target.key}"))
                continue
        else:
            target = Period.from_date(r.date) if r.date else catalog.latest
        try:
            data = catalog.get(target)
        except CatalogError:
            msg = f"沒有 {target.key} 的中獎號碼"
            if target.draw_date > today:
                msg = f"{target.key} 尚未開獎（開獎日 {target.draw_date}）"
            results.append(Result(r, target, "no-data", message=msg))
            continue
        win = evaluate(r.number, data)
        results.append(Result(r, target, "win" if win else "lose", win))
    return results


def total_amount(results: list) -> int:
    return sum(x.win.amount for x in results if x.win)
