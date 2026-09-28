"""中獎號碼的序列化、快取（遵守 XDG / macOS Caches）。"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .periods import Period, latest_drawn
from .prizes import PeriodData

APP_DIR = "invoice-lottery-tw"
CACHE_FILE = "winning-numbers.json"
TTL_SECONDS = 12 * 3600  # 快取有效時間
MIN_RETRY_SECONDS = 3600  # 應該有新一期卻還沒抓到時，最短重試間隔
SCHEMA_VERSION = 1


def cache_dir(env=None, platform=None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("INVOICE_LOTTERY_CACHE_DIR"):
        return Path(env["INVOICE_LOTTERY_CACHE_DIR"])
    if env.get("XDG_CACHE_HOME"):
        return Path(env["XDG_CACHE_HOME"]) / APP_DIR
    home = Path(env.get("HOME") or os.path.expanduser("~"))
    if platform == "darwin":
        return home / "Library" / "Caches" / APP_DIR
    return home / ".cache" / APP_DIR


def cache_path(**kw) -> Path:
    return cache_dir(**kw) / CACHE_FILE


def period_to_dict(d: PeriodData) -> dict:
    p = d.period
    return {
        "period": p.key,
        "label": p.label,
        "draw_date": p.draw_date.isoformat(),
        "claim_start": p.claim_start.isoformat(),
        "claim_end": p.claim_end.isoformat(),
        "special": d.special,
        "grand": d.grand,
        "first": list(d.first),
        "extra_sixth": list(d.extra_sixth),
    }


def period_from_dict(o: dict) -> PeriodData:
    return PeriodData(
        Period.parse(o["period"]),
        o["special"],
        o["grand"],
        tuple(o["first"]),
        tuple(o.get("extra_sixth", ())),
    )


def dump(periods: list, source: str, now: datetime) -> dict:
    return {
        "version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "periods": [period_to_dict(d) for d in sorted(periods, key=lambda d: d.period, reverse=True)],
    }


def load_dict(o: dict) -> list:
    if not isinstance(o, dict) or "periods" not in o:
        raise ValueError("資料格式不正確")
    return [period_from_dict(x) for x in o["periods"]]


def save_cache(periods: list, source: str, now: datetime, path: Path = None) -> Path:
    path = path or cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dump(periods, source, now), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_cache(path: Path = None):
    """回傳 (periods, generated_at datetime, source)；不存在或壞掉回傳 None。"""
    path = path or cache_path()
    try:
        o = json.loads(path.read_text(encoding="utf-8"))
        periods = load_dict(o)
        at = datetime.strptime(o["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return periods, at, o.get("source", "")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cache_state(periods: list, generated_at: datetime, now: datetime, today: date) -> str:
    """判斷快取狀態：'fresh' 直接用，'stale' 應重新抓取。

    - 超過 TTL（12 小時）→ stale
    - 依今天日期已經開獎的最新一期不在快取裡 → stale，但一小時內不重複重試
    """
    age = (now - generated_at).total_seconds()
    if age < 0:  # 系統時間被調回去
        return "stale"
    expected = latest_drawn(today)
    have = {d.period for d in periods}
    if expected not in have:
        return "stale" if age >= MIN_RETRY_SECONDS else "fresh"
    return "stale" if age >= TTL_SECONDS else "fresh"
