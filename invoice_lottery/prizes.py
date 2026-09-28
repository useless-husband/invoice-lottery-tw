"""獎項規則與比對。

依據財政部「統一發票給獎辦法」與財政部稅務入口網公布之中獎號碼單：
  特別獎 8 碼全對 1,000 萬；特獎 8 碼全對 200 萬；
  頭獎 8 碼全對 20 萬；二獎～六獎為末 7/6/5/4/3 碼與「任一組頭獎號碼」相同，
  依序 4 萬 / 1 萬 / 4 千 / 1 千 / 2 百。
  同一張發票同時符合多個獎項時，只能領最高的一個獎項。
  「增開六獎」為部分期別另行公布的三碼號碼，末三碼相符得 200 元；目前公告未見，
  資料中若有就會支援。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PRIZE_SPECIAL = "特別獎"
PRIZE_GRAND = "特獎"
PRIZE_FIRST = "頭獎"
PRIZE_EXTRA_SIXTH = "增開六獎"

# (名稱, 金額, 需比對的末幾碼；8 = 全部)
PRIZE_TABLE = [
    (PRIZE_SPECIAL, 10_000_000, 8),
    (PRIZE_GRAND, 2_000_000, 8),
    (PRIZE_FIRST, 200_000, 8),
    ("二獎", 40_000, 7),
    ("三獎", 10_000, 6),
    ("四獎", 4_000, 5),
    ("五獎", 1_000, 4),
    ("六獎", 200, 3),
]
LOWER_PRIZES = PRIZE_TABLE[3:]

_NUM8 = re.compile(r"^\d{8}$")


def normalize_number(text: str) -> str:
    """接受 '12345678'、'AB-12345678'、'AB12345678'，回傳 8 位數字字串。"""
    s = str(text).strip().replace(" ", "").replace("-", "")
    m = re.fullmatch(r"(?:[A-Za-z]{2})?(\d{8})", s)
    if not m:
        raise ValueError(f"發票號碼必須是 8 位數字（可含 2 碼英文字軌）：{text!r}")
    return m.group(1)


def is_valid_number(text: str) -> bool:
    try:
        normalize_number(text)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class PeriodData:
    """單一期別的中獎號碼。"""

    period: "object"  # invoice_lottery.periods.Period
    special: str
    grand: str
    first: tuple = ()
    extra_sixth: tuple = ()

    def __post_init__(self) -> None:
        for n in (self.special, self.grand, *self.first):
            if not _NUM8.match(n):
                raise ValueError(f"中獎號碼必須是 8 位數字：{n!r}")
        for n in self.extra_sixth:
            if not re.fullmatch(r"\d{3}", n):
                raise ValueError(f"增開六獎必須是 3 位數字：{n!r}")
        if not self.first:
            raise ValueError("至少要有一組頭獎號碼")


@dataclass(frozen=True)
class Win:
    prize: str
    amount: int
    matched: str  # 相符的中獎號碼（或號碼末幾碼）


def evaluate(number: str, data: PeriodData) -> "Win | None":
    """比對一張發票；沒中回傳 None，中多個獎項只回傳金額最高者。"""
    n = normalize_number(number)
    wins: list[Win] = []
    if n == data.special:
        wins.append(Win(PRIZE_SPECIAL, 10_000_000, data.special))
    if n == data.grand:
        wins.append(Win(PRIZE_GRAND, 2_000_000, data.grand))
    for f in data.first:
        for name, amount, digits in PRIZE_TABLE[2:]:
            if n[-digits:] == f[-digits:]:
                wins.append(Win(name, amount, f[-digits:]))
                break  # 由高到低，命中最高即可
    for e in data.extra_sixth:
        if n[-3:] == e:
            wins.append(Win(PRIZE_EXTRA_SIXTH, 200, e))
    if not wins:
        return None
    return max(wins, key=lambda w: w.amount)


def last3_candidates(data: PeriodData) -> set:
    """所有可能中獎的末三碼（快速模式用）。"""
    s = {data.special[-3:], data.grand[-3:]}
    s.update(f[-3:] for f in data.first)
    s.update(data.extra_sixth)
    return s


def could_win(last3: str, data: PeriodData) -> bool:
    if not re.fullmatch(r"\d{3}", last3):
        raise ValueError(f"末三碼必須是 3 位數字：{last3!r}")
    return last3 in last3_candidates(data)


def format_amount(n: int) -> str:
    return f"{n:,}"
