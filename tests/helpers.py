from pathlib import Path

from invoice_lottery.catalog import Catalog
from invoice_lottery.periods import Period
from invoice_lottery.prizes import PeriodData
from invoice_lottery.sources import parse_rss

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# 財政部 115 年 07-08 月的真實號碼
DATA = PeriodData(
    Period(115, 7), "89996565", "91098182", ("54348835", "44991397", "06595111")
)


def real_catalog() -> Catalog:
    return Catalog(parse_rss(fixture("invoice.xml")), source="fixture")


def fake_fetch(url: str) -> str:
    """模擬網路：依網址回傳 fixture。"""
    name = url.rsplit("/", 1)[-1]
    return fixture(name)
