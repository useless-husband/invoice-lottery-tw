"""從財政部稅務入口網抓取並解析中獎號碼。

來源（依序嘗試）：
  1. RSS  https://invoice.etax.nat.gov.tw/invoice.xml   （近 6 期，含特別獎/特獎/頭獎）
  2. 網頁 https://invoice.etax.nat.gov.tw/index.html     （本期）
         https://invoice.etax.nat.gov.tw/lastNumber.html （上一期）
RSS 成功時仍會嘗試用網頁補上「增開六獎」（若有）；網頁失敗不影響結果。
"""
from __future__ import annotations

import os
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable

from .periods import Period
from .prizes import PeriodData

RSS_URL = "https://invoice.etax.nat.gov.tw/invoice.xml"
HTML_URLS = [
    "https://invoice.etax.nat.gov.tw/index.html",
    "https://invoice.etax.nat.gov.tw/lastNumber.html",
]
USER_AGENT = "invoice-lottery-tw/0.1 (+https://github.com/useless-husband/invoice-lottery-tw)"


class FetchError(Exception):
    """所有來源都失敗。"""


class ParseError(ValueError):
    """內容格式看不懂。"""


_CA_BUNDLES = ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"]


def make_ssl_context() -> ssl.SSLContext:
    """仍然完整驗證憑證，但做兩個相容處理：

    1. Python 3.13 預設開啟 VERIFY_X509_STRICT，會拒絕政府憑證（TWCA 簽發，缺 Subject Key
       Identifier），所以關掉這個「嚴格」旗標（鏈與主機名稱仍照常驗證）。
    2. python.org 版 macOS Python 沒有內建 CA 清單時，改讀系統的 CA 檔。
    """
    ctx = ssl.create_default_context()
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    ctx.verify_flags &= ~strict
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        for path in _CA_BUNDLES:
            if os.path.exists(path):
                ctx.load_verify_locations(path)
                break
    return ctx


def fetch_text(url: str, timeout: float = 10.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=make_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _numbers(text: str, width: int) -> tuple:
    return tuple(re.findall(r"(?<!\d)\d{%d}(?!\d)" % width, text))


_RSS_TITLE = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*[~\-～]\s*(\d{1,2})\s*月")


def parse_rss(text: str) -> list:
    """解析 invoice.xml，回傳 PeriodData 清單（新到舊）。格式錯誤的項目會被略過。"""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ParseError(f"RSS 不是合法的 XML：{e}") from e
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = item.findtext("description") or ""
        m = _RSS_TITLE.search(title)
        if not m:
            continue
        try:
            period = Period(int(m.group(1)), int(m.group(2)))
            plain = re.sub(r"<[^>]+>", "\n", desc)
            special = re.search(r"特別獎[：:]\s*(\d{8})", plain)
            grand = re.search(r"特獎[：:]\s*(\d{8})", plain)
            first = re.search(r"頭獎[：:]\s*([\d、,，\s]+)", plain)
            extra = re.search(r"增開六獎[：:]\s*([\d、,，\s]+)", plain)
            if not (special and grand and first):
                continue
            out.append(
                PeriodData(
                    period,
                    special.group(1),
                    grand.group(1),
                    _numbers(first.group(1), 8),
                    _numbers(extra.group(1), 3) if extra else (),
                )
            )
        except ValueError:
            continue
    if not out:
        raise ParseError("RSS 中找不到任何期別的中獎號碼")
    return out


_ACTIVE = re.compile(r'class="etw-on"[^>]*title="(\d{2,3})年(\d{1,2})-(\d{1,2})月中獎號碼單"')


def parse_html(text: str) -> PeriodData:
    """解析 index.html / lastNumber.html（單一期別）。"""
    m = _ACTIVE.search(text)
    if not m:
        raise ParseError("網頁中找不到期別標題")
    period = Period(int(m.group(1)), int(m.group(2)))
    i = text.find(">特別獎<")
    if i < 0:
        raise ParseError("網頁中找不到特別獎")
    body = text[i:]
    end = body.find("領獎注意事項")
    if end > 0:
        body = body[:end]
    # 頭獎的號碼被拆成兩個 <span>，先把標籤去掉再取 8 碼
    def cell(label: str, stop: str) -> str:
        a = body.find(f">{label}<")
        if a < 0:
            return ""
        b = body.find(stop, a)
        seg = body[a: b if b > 0 else len(body)]
        return re.sub(r"<[^>]+>", "", seg)

    special = _numbers(cell("特別獎", ">特獎<"), 8)
    grand = _numbers(cell("特獎", ">頭獎<"), 8)
    first = _numbers(cell("頭獎", "同期統一發票收執聯8位數號碼與頭獎"), 8)
    if not (special and grand and first):
        raise ParseError("網頁中的特別獎/特獎/頭獎號碼不完整")
    extra: tuple = ()
    flat = re.sub(r"<[^>]+>", " ", body)
    em = re.search(r"增開六獎[^\d]{0,20}((?:\d{3}[\s、,，]*)+)", flat)
    if em:
        extra = _numbers(em.group(1), 3)
    return PeriodData(period, special[0], grand[0], first, extra)


def merge(primary: list, extra: list) -> list:
    """以 primary 為主，補上 extra 中缺少的期別，以及增開六獎。"""
    by = {d.period: d for d in primary}
    for d in extra:
        cur = by.get(d.period)
        if cur is None:
            by[d.period] = d
        elif d.extra_sixth and not cur.extra_sixth:
            by[d.period] = PeriodData(cur.period, cur.special, cur.grand, cur.first, d.extra_sixth)
    return sorted(by.values(), key=lambda d: d.period, reverse=True)


def fetch_all(fetch: Callable = fetch_text) -> tuple:
    """回傳 (PeriodData 清單, 來源說明)。所有來源都失敗則丟 FetchError。"""
    errors = []
    rss = []
    try:
        rss = parse_rss(fetch(RSS_URL))
    except Exception as e:  # noqa: BLE001 - 網路與解析錯誤都要能備援
        errors.append(f"RSS：{e}")
    pages = []
    for url in HTML_URLS:
        try:
            pages.append(parse_html(fetch(url)))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url.rsplit('/', 1)[-1]}：{e}")
    if rss and pages:
        return merge(rss, pages), "財政部稅務入口網 RSS + 網頁"
    if rss:
        return merge(rss, []), "財政部稅務入口網 RSS"
    if pages:
        return merge(pages, []), "財政部稅務入口網網頁（備援）"
    raise FetchError("無法取得中獎號碼；" + "；".join(errors))
