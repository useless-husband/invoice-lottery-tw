"""期別、開獎日與領獎期間的計算（全部使用民國年表示）。

統一發票每兩個月為一期：1-2 月、3-4 月 ... 11-12 月。
開獎日為單數月 25 日（即該期結束後的次月）；領獎期間為開獎後次月 6 日起算三個月。
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

ROC_OFFSET = 1911
WEEKDAYS = "一二三四五六日"

_PERIOD_PATTERNS = [
    # 115-07/08, 115-7/8, 115/07-08
    re.compile(r"^\s*(\d{2,3})\s*[-/]\s*(\d{1,2})\s*[/~\-～]\s*(\d{1,2})\s*$"),
    # 115年07-08月, 115年 07~08月
    re.compile(r"^\s*(\d{2,3})\s*年\s*(\d{1,2})\s*[-~～/]\s*(\d{1,2})\s*月?\s*$"),
]
_SHORT = re.compile(r"^\s*(\d{2,3})(\d{2})\s*$")  # 11507


def add_months(y: int, m: int, n: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + n
    return idx // 12, idx % 12 + 1


def roc_to_ad(roc_year: int) -> int:
    return roc_year + ROC_OFFSET


def ad_to_roc(year: int) -> int:
    return year - ROC_OFFSET


@dataclass(frozen=True, order=True)
class Period:
    roc_year: int
    start_month: int  # 1, 3, 5, 7, 9, 11

    def __post_init__(self) -> None:
        if self.start_month not in (1, 3, 5, 7, 9, 11):
            raise ValueError(f"期別起始月必須是單數月 (1,3,...,11)：{self.start_month}")
        if not 1 <= self.roc_year <= 999:
            raise ValueError(f"不合理的民國年：{self.roc_year}")

    # --- 表示 ---
    @property
    def end_month(self) -> int:
        return self.start_month + 1

    @property
    def key(self) -> str:
        return f"{self.roc_year}-{self.start_month:02d}/{self.end_month:02d}"

    @property
    def label(self) -> str:
        return f"{self.roc_year}年{self.start_month:02d}-{self.end_month:02d}月"

    def __str__(self) -> str:
        return self.key

    # --- 解析 ---
    @classmethod
    def parse(cls, text: str) -> "Period":
        s = str(text).strip()
        for pat in _PERIOD_PATTERNS:
            m = pat.match(s)
            if m:
                y, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if b != a + 1:
                    raise ValueError(f"看不懂的期別：{text!r}（兩個月必須相連，例如 115-07/08）")
                return cls(y, a)
        m = _SHORT.match(s)
        if m:
            return cls(int(m.group(1)), int(m.group(2)))
        raise ValueError(f"看不懂的期別：{text!r}（範例：115-07/08）")

    @classmethod
    def from_date(cls, d: date) -> "Period":
        start = d.month if d.month % 2 == 1 else d.month - 1
        return cls(ad_to_roc(d.year), start)

    # --- 日期計算 ---
    @property
    def draw_date(self) -> date:
        y, m = add_months(roc_to_ad(self.roc_year), self.start_month, 2)
        return date(y, m, 25)

    @property
    def claim_start(self) -> date:
        y, m = add_months(self.draw_date.year, self.draw_date.month, 1)
        return date(y, m, 6)

    @property
    def claim_end(self) -> date:
        y, m = add_months(self.claim_start.year, self.claim_start.month, 3)
        return date(y, m, 5)

    @property
    def first_day(self) -> date:
        return date(roc_to_ad(self.roc_year), self.start_month, 1)

    @property
    def last_day(self) -> date:
        y = roc_to_ad(self.roc_year)
        return date(y, self.end_month, calendar.monthrange(y, self.end_month)[1])

    def contains(self, d: date) -> bool:
        return self.first_day <= d <= self.last_day

    def next(self) -> "Period":
        y, m = add_months(self.roc_year, self.start_month, 2)
        return Period(y, m)

    def prev(self) -> "Period":
        y, m = add_months(self.roc_year, self.start_month, -2)
        return Period(y, m)

    def status(self, today: date) -> str:
        """回傳 'pending'（尚未開獎）、'claimable'（可領獎）或 'expired'（已過期）。"""
        if today < self.draw_date:
            return "pending"
        if today > self.claim_end:
            return "expired"
        return "claimable"


def latest_drawn(today: date) -> Period:
    """依今天日期，回傳最近一期「已開獎」的期別。"""
    p = Period.from_date(today)
    while p.draw_date > today:
        p = p.prev()
    return p


def format_date(d: date) -> str:
    return f"{d.isoformat()}（{WEEKDAYS[d.weekday()]}）"


_DATE_PATTERNS = [
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"),
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),
    re.compile(r"^(\d{2,3})[-/.](\d{1,2})[-/.](\d{1,2})$"),  # 民國 115/07/15
    re.compile(r"^(\d{3})(\d{2})(\d{2})$"),  # 1150715
]


def parse_date(text: str) -> date:
    """解析西元 (2026-07-15 / 2026/7/15 / 20260715) 或民國 (115/07/15 / 1150715) 日期。"""
    s = str(text).strip()
    for pat in _DATE_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1900:
            y = roc_to_ad(y)
        try:
            return date(y, mo, d)
        except ValueError as e:
            raise ValueError(f"不存在的日期：{text!r}") from e
    raise ValueError(f"看不懂的日期：{text!r}（範例：2026-07-15 或 115/07/15）")
