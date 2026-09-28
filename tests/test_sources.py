import re
import unittest

from invoice_lottery import sources
from invoice_lottery.periods import Period

from .helpers import fake_fetch, fixture


class RssTests(unittest.TestCase):
    def setUp(self):
        self.items = sources.parse_rss(fixture("invoice.xml"))

    def test_item_count_and_order(self):
        self.assertEqual(len(self.items), 6)
        self.assertEqual(self.items[0].period, Period(115, 7))
        self.assertEqual(self.items[-1].period, Period(114, 9))

    def test_latest_values(self):
        d = self.items[0]
        self.assertEqual(d.special, "89996565")
        self.assertEqual(d.grand, "91098182")
        self.assertEqual(d.first, ("54348835", "44991397", "06595111"))
        self.assertEqual(d.extra_sixth, ())

    def test_leading_zero_preserved(self):
        self.assertIn("06595111", self.items[0].first)
        self.assertEqual(self.items[4].grand, "00507588")

    def test_across_year(self):
        self.assertEqual(self.items[4].period, Period(114, 11))

    def test_invalid_xml(self):
        with self.assertRaises(sources.ParseError):
            sources.parse_rss("<rss><channel>")

    def test_no_items(self):
        with self.assertRaises(sources.ParseError):
            sources.parse_rss("<rss><channel></channel></rss>")

    def test_synthetic_extra_sixth_and_bad_items_skipped(self):
        items = sources.parse_rss(fixture("rss_extra_sixth_synthetic.xml"))
        self.assertEqual(len(items), 1)  # 特別獎位數不對、標題不是期別的兩筆被略過
        self.assertEqual(items[0].period, Period(110, 1))
        self.assertEqual(items[0].extra_sixth, ("123", "456"))
        self.assertEqual(items[0].first, ("33333333", "44444444", "55555555"))


class HtmlTests(unittest.TestCase):
    def test_index(self):
        d = sources.parse_html(fixture("index.html"))
        self.assertEqual(d.period, Period(115, 7))
        self.assertEqual((d.special, d.grand), ("89996565", "91098182"))
        self.assertEqual(d.first, ("54348835", "44991397", "06595111"))

    def test_last_number(self):
        d = sources.parse_html(fixture("lastNumber.html"))
        self.assertEqual(d.period, Period(115, 5))
        self.assertEqual(d.first, ("24121106", "28589937", "83663333"))

    def test_html_agrees_with_rss(self):
        rss = {d.period: d for d in sources.parse_rss(fixture("invoice.xml"))}
        for name in ("index.html", "lastNumber.html"):
            h = sources.parse_html(fixture(name))
            self.assertEqual(h, rss[h.period])

    def test_claim_period_formula_matches_page(self):
        for name in ("index.html", "lastNumber.html"):
            html = fixture(name)
            h = sources.parse_html(html)
            m = re.search(r"領獎期間自(\d+)年(\d+)月(\d+)日起至(\d+)年(\d+)月(\d+)日止", html)
            y1, m1, d1, y2, m2, d2 = map(int, m.groups())
            self.assertEqual((h.period.claim_start.year, h.period.claim_start.month, h.period.claim_start.day),
                             (y1 + 1911, m1, d1))
            self.assertEqual((h.period.claim_end.year, h.period.claim_end.month, h.period.claim_end.day),
                             (y2 + 1911, m2, d2))

    def test_extra_sixth_in_html(self):
        html = fixture("index.html").replace(
            "領獎注意事項", "<tr><td>增開六獎</td><td>123、456</td></tr>領獎注意事項", 1
        )
        d = sources.parse_html(html)
        self.assertEqual(d.extra_sixth, ("123", "456"))

    def test_missing_title(self):
        with self.assertRaises(sources.ParseError):
            sources.parse_html("<html>nothing</html>")

    def test_truncated_page(self):
        html = fixture("index.html")
        with self.assertRaises(sources.ParseError):
            sources.parse_html(html[: html.find(">頭獎<")])


class FetchAllTests(unittest.TestCase):
    def test_all_sources(self):
        items, src = sources.fetch_all(fake_fetch)
        self.assertEqual(len(items), 6)
        self.assertIn("RSS", src)

    def test_rss_down_falls_back_to_html(self):
        def fetch(url):
            if url.endswith("invoice.xml"):
                raise OSError("boom")
            return fake_fetch(url)
        items, src = sources.fetch_all(fetch)
        self.assertEqual([d.period for d in items], [Period(115, 7), Period(115, 5)])
        self.assertIn("備援", src)

    def test_html_down_still_uses_rss(self):
        def fetch(url):
            if url.endswith(".html"):
                raise OSError("boom")
            return fake_fetch(url)
        items, _ = sources.fetch_all(fetch)
        self.assertEqual(len(items), 6)

    def test_rss_garbage_falls_back(self):
        def fetch(url):
            return "<html>oops</html>" if url.endswith("invoice.xml") else fake_fetch(url)
        items, _ = sources.fetch_all(fetch)
        self.assertEqual(len(items), 2)

    def test_everything_down(self):
        def fetch(url):
            raise OSError("no network")
        with self.assertRaises(sources.FetchError) as cm:
            sources.fetch_all(fetch)
        self.assertIn("RSS", str(cm.exception))

    def test_merge_adds_extra_sixth_from_html(self):
        rss = sources.parse_rss(fixture("invoice.xml"))
        html = sources.parse_html(
            fixture("index.html").replace("領獎注意事項", "增開六獎 123 領獎注意事項", 1)
        )
        merged = sources.merge(rss, [html])
        self.assertEqual(merged[0].extra_sixth, ("123",))
        self.assertEqual(len(merged), 6)


class SslContextTests(unittest.TestCase):
    def test_still_verifies(self):
        import ssl
        ctx = sources.make_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)


if __name__ == "__main__":
    unittest.main()
