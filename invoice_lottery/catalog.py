"""取得中獎號碼資料：快取優先、過期才連網、連不上就用舊快取並提示。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from . import sources, store
from .periods import Period


class CatalogError(Exception):
    pass


class Catalog:
    def __init__(self, periods: list, notes: Optional[list] = None, source: str = ""):
        self.by_period = {d.period: d for d in periods}
        self.notes = notes or []
        self.source = source

    def __bool__(self) -> bool:
        return bool(self.by_period)

    @property
    def periods(self) -> list:
        return sorted(self.by_period, reverse=True)

    @property
    def latest(self) -> Period:
        return self.periods[0]

    def get(self, period: Period):
        d = self.by_period.get(period)
        if d is None:
            have = "、".join(p.key for p in self.periods) or "（無）"
            raise CatalogError(
                f"沒有 {period.key} 的中獎號碼資料（目前有：{have}）。"
                "尚未開獎，或是太久以前（官方只提供近幾期）。"
            )
        return d


def load(
    refresh: bool = False,
    offline: bool = False,
    now: Optional[datetime] = None,
    fetch: Callable = sources.fetch_text,
    cache_file=None,
) -> Catalog:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone().date()
    cached = store.read_cache(cache_file)
    notes: list = []

    if cached and not refresh:
        periods, at, source = cached
        if offline or store.cache_state(periods, at, now, today) == "fresh":
            return Catalog(periods, notes, source)

    if offline:
        raise CatalogError("離線模式，但沒有快取。請先在有網路時執行一次 `invoice numbers`。")

    try:
        periods, source = sources.fetch_all(fetch)
    except sources.FetchError as e:
        if cached:
            periods, at, source = cached
            local = at.astimezone().strftime("%Y-%m-%d %H:%M")
            notes.append(f"網路不通，改用 {local} 的快取資料。（{e}）")
            return Catalog(periods, notes, source)
        raise CatalogError(f"{e}；而且沒有可用的快取。") from e

    try:
        store.save_cache(periods, source, now, cache_file)
    except OSError as e:
        notes.append(f"無法寫入快取：{e}")
    return Catalog(periods, notes, source)
