"""命令列介面：invoice numbers / check / quick / batch / export-json"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import __version__, store
from .batch import check_rows, parse_csv, total_amount
from .catalog import Catalog, CatalogError, load
from .periods import Period, format_date, parse_date
from .prizes import (
    LOWER_PRIZES,
    PRIZE_TABLE,
    PeriodData,
    could_win,
    evaluate,
    format_amount,
    normalize_number,
)


def _color(enabled: bool):
    def paint(code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if enabled else s
    return paint


def _use_color(stream) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ


def period_warning(period: Period, today: date) -> Optional[str]:
    st = period.status(today)
    if st == "pending":
        return f"注意：{period.label} 要到 {format_date(period.draw_date)} 才開獎。"
    if st == "expired":
        return f"注意：{period.label} 的領獎期限（{period.claim_end}）已經過了。"
    return None


def describe_period(period: Period) -> str:
    return (
        f"{period.label}（{period.key}）\n"
        f"開獎日 {format_date(period.draw_date)}　"
        f"領獎期間 {period.claim_start} 至 {period.claim_end}"
    )


def format_numbers(data: PeriodData) -> str:
    lines = [describe_period(data.period), ""]
    lines.append(f"特別獎  {format_amount(10_000_000):>10} 元  {data.special}")
    lines.append(f"特獎    {format_amount(2_000_000):>10} 元  {data.grand}")
    lines.append(f"頭獎    {format_amount(200_000):>10} 元  " + "  ".join(data.first))
    for name, amount, digits in LOWER_PRIZES:
        tails = "  ".join(f[-digits:] for f in data.first)
        lines.append(f"{name}    {format_amount(amount):>10} 元  末{digits}碼  {tails}")
    if data.extra_sixth:
        lines.append(f"增開六獎 {format_amount(200):>8} 元  末3碼  " + "  ".join(data.extra_sixth))
    return "\n".join(lines)


def _pick_period(catalog: Catalog, text: Optional[str]) -> Period:
    if text:
        try:
            return Period.parse(text)
        except ValueError as e:
            raise CatalogError(str(e)) from e
    return catalog.latest


def _print_notes(catalog: Catalog, err) -> None:
    for n in catalog.notes:
        print(f"[提示] {n}", file=err)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- commands
def cmd_numbers(args, out, err, catalog: Catalog, today: date) -> int:
    period = _pick_period(catalog, args.period)
    data = catalog.get(period)
    print(format_numbers(data), file=out)
    w = period_warning(period, today)
    if w:
        print("\n" + w, file=out)
    return 0


def cmd_check(args, out, err, catalog: Catalog, today: date) -> int:
    try:
        number = normalize_number(args.number)
        inv_date = parse_date(args.date) if args.date else None
    except ValueError as e:
        print(f"錯誤：{e}", file=err)
        return 2
    if args.period:
        period = _pick_period(catalog, args.period)
    elif inv_date:
        period = Period.from_date(inv_date)
    else:
        period = catalog.latest
    if inv_date and not period.contains(inv_date):
        actual = Period.from_date(inv_date)
        print(f"提醒：這張發票日期 {inv_date} 屬於 {actual.key}，不能拿來對 {period.key}。", file=out)
        return 2
    data = catalog.get(period)
    print(f"對獎期別：{period.label}（{period.key}）", file=out)
    w = period_warning(period, today)
    if w:
        print(w, file=out)
    win = evaluate(number, data)
    if win:
        print(f"{number}  中獎！{win.prize}　{format_amount(win.amount)} 元", file=out)
        return 0
    print(f"{number}  沒中。", file=out)
    return 1


def run_quick(data: PeriodData, out, input_fn: Callable = input) -> dict:
    """快速對獎主迴圈，回傳統計。input_fn 可注入以便測試。"""
    paint = _color(_use_color(out))
    stats = {"count": 0, "wins": 0, "total": 0, "unsure": 0}
    print(f"快速對獎：{data.period.label}　只要輸入發票末三碼再按 Enter；q 離開。", file=out)

    def ask(prompt: str) -> Optional[str]:
        try:
            return input_fn(prompt).strip()
        except EOFError:
            return None

    while True:
        s = ask("末三碼> ")
        if s is None or s.lower() in ("q", "quit", "exit"):
            break
        if s == "":
            continue
        s = s.replace(" ", "")
        full: Optional[str] = None
        if re.fullmatch(r"(?:[A-Za-z]{2}-?)?\d{8}", s):  # 直接貼整組號碼也行
            full = normalize_number(s)
            last3 = full[-3:]
        elif re.fullmatch(r"\d{3}", s):
            last3 = s
        else:
            print("  請輸入 3 位數字（或完整 8 碼）", file=out)
            continue
        stats["count"] += 1
        if full is None:
            if not could_win(last3, data):
                print("  " + paint("2", "沒中"), file=out)
                continue
            print("  " + paint("33", "可能中獎！") + " 請輸入完整 8 碼（或前 5 碼，Enter 略過）", file=out)
            while True:
                t = ask("完整號碼> ")
                if t is None or t.lower() in ("q", "quit", "exit"):
                    stats["unsure"] += 1
                    return _finish(stats, out, paint)
                if t == "":
                    stats["unsure"] += 1
                    print("  略過（未確認）", file=out)
                    break
                t = t.replace(" ", "")
                if re.fullmatch(r"\d{5}", t):
                    t += last3
                try:
                    cand = normalize_number(t)
                except ValueError:
                    print("  請輸入 8 碼或前 5 碼", file=out)
                    continue
                if cand[-3:] != last3:
                    print(f"  末三碼跟剛才的 {last3} 不一樣，請重輸", file=out)
                    continue
                full = cand
                break
            if full is None:
                continue
        win = evaluate(full, data)
        if win:
            stats["wins"] += 1
            stats["total"] += win.amount
            print("  " + paint("1;32", f"中獎！{win.prize} {format_amount(win.amount)} 元") + f"  ({full})", file=out)
        else:
            print("  沒中（末三碼像，但整組不同）", file=out)
    return _finish(stats, out, paint)


def _finish(stats: dict, out, paint) -> dict:
    print(file=out)
    print(f"共對了 {stats['count']} 張，中獎 {stats['wins']} 張，總獎金 {format_amount(stats['total'])} 元。", file=out)
    if stats["unsure"]:
        print(f"另有 {stats['unsure']} 張末三碼相符但沒確認完整號碼，記得補查。", file=out)
    return stats


def cmd_quick(args, out, err, catalog: Catalog, today: date) -> int:
    period = _pick_period(catalog, args.period)
    data = catalog.get(period)
    w = period_warning(period, today)
    if w:
        print(w, file=out)
    run_quick(data, out)
    return 0


def cmd_batch(args, out, err, catalog: Catalog, today: date) -> int:
    path = Path(args.file)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"錯誤：讀不到檔案 {path}：{e.strerror or e}", file=err)
        return 2
    except UnicodeDecodeError:
        print(f"錯誤：{path} 不是 UTF-8 編碼，請另存為 UTF-8 的 CSV。", file=err)
        return 2
    rows, errors = parse_csv(text)
    period = Period.parse(args.period) if args.period else None
    results = check_rows(rows, catalog, period, today)
    wins = [r for r in results if r.status == "win"]
    for r in results:
        if r.status == "wrong-period":
            print(f"第 {r.row.line} 行 {r.row.number}：錯期。{r.message}", file=out)
        elif r.status == "no-data":
            print(f"第 {r.row.line} 行 {r.row.number}：{r.message}", file=out)
    for line, msg in errors:
        print(f"第 {line} 行：略過。{msg}", file=err)
    warned = {}
    for r in results:
        if r.period and r.status in ("win", "lose") and r.period not in warned:
            w = period_warning(r.period, today)
            warned[r.period] = w
            if w:
                print(w, file=out)
    print(file=out)
    if wins:
        print("中獎清單：", file=out)
        for r in sorted(wins, key=lambda r: -r.win.amount):
            print(f"  {r.row.number}  {r.period.key}  {r.win.prize}  {format_amount(r.win.amount)} 元", file=out)
    else:
        print("沒有中獎的發票。", file=out)
    checked = sum(1 for r in results if r.status in ("win", "lose"))
    skipped = len(results) - checked
    print(
        f"\n共 {len(rows)} 張有效、已對獎 {checked} 張、中獎 {len(wins)} 張，"
        f"總獎金 {format_amount(total_amount(results))} 元。",
        file=out,
    )
    if skipped or errors:
        print(f"（{skipped} 張因錯期或缺資料未對獎，{len(errors)} 行格式錯誤被略過）", file=out)
    return 0


def cmd_export_json(args, out, err, catalog: Catalog, today: date) -> int:
    doc = store.dump(list(catalog.by_period.values()), catalog.source, _now())
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-":
        out.write(text)
        return 0
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print(f"已寫入 {p}（{len(doc['periods'])} 期，最新 {catalog.latest.key}）", file=out)
    return 0


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--refresh", action="store_true", help="忽略快取，強制重新抓取")
    common.add_argument("--offline", action="store_true", help="只用快取，不連網")

    p = argparse.ArgumentParser(prog="invoice", description="統一發票對獎小幫手")
    p.add_argument("--version", action="version", version=f"invoice-lottery-tw {__version__}")
    sub = p.add_subparsers(dest="command", metavar="指令")

    s = sub.add_parser("numbers", parents=[common], help="顯示某期中獎號碼")
    s.add_argument("--period", help="期別，例如 115-07/08（預設最新一期）")
    s.set_defaults(func=cmd_numbers)

    s = sub.add_parser("check", parents=[common], help="對單張發票")
    s.add_argument("number", help="8 位數發票號碼（可含字軌，如 AB-12345678）")
    s.add_argument("--period", help="期別，例如 115-07/08（預設最新一期）")
    s.add_argument("--date", help="發票日期；會檢查是否對錯期")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("quick", parents=[common], help="互動式快速對獎（只打末三碼）")
    s.add_argument("--period", help="期別（預設最新一期）")
    s.set_defaults(func=cmd_quick)

    s = sub.add_parser("batch", parents=[common], help="批次對 CSV（欄位：號碼,日期）")
    s.add_argument("file", help="CSV 檔案（UTF-8）")
    s.add_argument("--period", help="固定對這一期；日期不屬於該期的發票會標為錯期")
    s.set_defaults(func=cmd_batch)

    s = sub.add_parser("export-json", parents=[common], help="輸出中獎號碼 JSON（給網頁版用）")
    s.add_argument("output", nargs="?", default="web/data.json", help="輸出檔（預設 web/data.json，- 表示標準輸出）")
    s.set_defaults(func=cmd_export_json)
    return p


def main(argv=None, out=None, err=None, today: Optional[date] = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(out)
        return 0
    try:
        if args.command == "check":  # 先驗證輸入再連網
            normalize_number(args.number)
        catalog = load(refresh=args.refresh, offline=args.offline)
        _print_notes(catalog, err)
        return args.func(args, out, err, catalog, today or datetime.now().date())
    except (CatalogError, ValueError) as e:
        print(f"錯誤：{e}", file=err)
        return 2
    except (KeyboardInterrupt, BrokenPipeError):
        return 130


if __name__ == "__main__":
    sys.exit(main())
