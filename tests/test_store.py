import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from invoice_lottery import catalog, sources, store
from invoice_lottery.periods import Period

from .helpers import fake_fetch, fixture

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 29)


def periods():
    return sources.parse_rss(fixture("invoice.xml"))


class CacheDirTests(unittest.TestCase):
    def test_override(self):
        self.assertEqual(store.cache_dir({"INVOICE_LOTTERY_CACHE_DIR": "/x/y"}, "linux"), Path("/x/y"))

    def test_xdg(self):
        self.assertEqual(store.cache_dir({"XDG_CACHE_HOME": "/xdg", "HOME": "/h"}, "linux"),
                         Path("/xdg/invoice-lottery-tw"))

    def test_xdg_wins_on_mac(self):
        self.assertEqual(store.cache_dir({"XDG_CACHE_HOME": "/xdg", "HOME": "/h"}, "darwin"),
                         Path("/xdg/invoice-lottery-tw"))

    def test_mac_default(self):
        self.assertEqual(store.cache_dir({"HOME": "/h"}, "darwin"), Path("/h/Library/Caches/invoice-lottery-tw"))

    def test_linux_default(self):
        self.assertEqual(store.cache_dir({"HOME": "/h"}, "linux"), Path("/h/.cache/invoice-lottery-tw"))


class RoundTripTests(unittest.TestCase):
    def test_save_and_read(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "sub" / "c.json"
            store.save_cache(periods(), "src", NOW, p)
            got, at, src = store.read_cache(p)
            self.assertEqual(got, sorted(periods(), key=lambda d: d.period, reverse=True))
            self.assertEqual(at, NOW)
            self.assertEqual(src, "src")

    def test_json_shape(self):
        doc = store.dump(periods(), "s", NOW)
        first = doc["periods"][0]
        self.assertEqual(first["period"], "115-07/08")
        self.assertEqual(first["draw_date"], "2026-09-25")
        self.assertEqual(first["claim_end"], "2027-01-05")
        self.assertEqual(doc["generated_at"], "2026-09-29T12:00:00Z")

    def test_missing_and_corrupt(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "c.json"
            self.assertIsNone(store.read_cache(p))
            p.write_text("{not json", encoding="utf-8")
            self.assertIsNone(store.read_cache(p))
            p.write_text(json.dumps({"periods": [{"period": "x"}]}), encoding="utf-8")
            self.assertIsNone(store.read_cache(p))


class CacheStateTests(unittest.TestCase):
    def test_fresh(self):
        self.assertEqual(store.cache_state(periods(), NOW - timedelta(hours=1), NOW, TODAY), "fresh")

    def test_expired_ttl(self):
        self.assertEqual(store.cache_state(periods(), NOW - timedelta(hours=13), NOW, TODAY), "stale")

    def test_ttl_boundary(self):
        self.assertEqual(store.cache_state(periods(), NOW - timedelta(hours=11, minutes=59), NOW, TODAY), "fresh")
        self.assertEqual(store.cache_state(periods(), NOW - timedelta(hours=12), NOW, TODAY), "stale")

    def test_missing_newest_period_triggers_refetch_after_retry_gap(self):
        old = [d for d in periods() if d.period != Period(115, 7)]
        self.assertEqual(store.cache_state(old, NOW - timedelta(minutes=10), NOW, TODAY), "fresh")
        self.assertEqual(store.cache_state(old, NOW - timedelta(hours=2), NOW, TODAY), "stale")

    def test_clock_went_backwards(self):
        self.assertEqual(store.cache_state(periods(), NOW + timedelta(hours=1), NOW, TODAY), "stale")

    def test_before_draw_day_old_cache_is_ok(self):
        # 9/24 還沒開獎，快取裡最新是 115-05/06 也算完整
        old = [d for d in periods() if d.period != Period(115, 7)]
        self.assertEqual(store.cache_state(old, NOW - timedelta(hours=1), NOW, date(2026, 9, 24)), "fresh")


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "c.json"
        self.calls = 0

    def fetch(self, url):
        self.calls += 1
        return fake_fetch(url)

    def down(self, url):
        self.calls += 1
        raise OSError("network is down")

    def test_first_load_fetches_and_writes_cache(self):
        c = catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        self.assertEqual(c.latest, Period(115, 7))
        self.assertTrue(self.cache.exists())
        self.assertGreater(self.calls, 0)

    def test_second_load_uses_cache(self):
        catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        n = self.calls
        c = catalog.load(now=NOW + timedelta(hours=1), fetch=self.fetch, cache_file=self.cache)
        self.assertEqual(self.calls, n)
        self.assertEqual(c.notes, [])

    def test_stale_cache_refetches(self):
        catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        n = self.calls
        catalog.load(now=NOW + timedelta(hours=13), fetch=self.fetch, cache_file=self.cache)
        self.assertGreater(self.calls, n)

    def test_refresh_forces_fetch(self):
        catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        n = self.calls
        catalog.load(refresh=True, now=NOW, fetch=self.fetch, cache_file=self.cache)
        self.assertGreater(self.calls, n)

    def test_network_down_uses_stale_cache_with_note(self):
        catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        c = catalog.load(now=NOW + timedelta(days=3), fetch=self.down, cache_file=self.cache)
        self.assertEqual(c.latest, Period(115, 7))
        self.assertEqual(len(c.notes), 1)
        self.assertIn("快取", c.notes[0])

    def test_network_down_no_cache(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.load(now=NOW, fetch=self.down, cache_file=self.cache)

    def test_offline_never_fetches(self):
        catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        n = self.calls
        catalog.load(offline=True, now=NOW + timedelta(days=30), fetch=self.fetch, cache_file=self.cache)
        self.assertEqual(self.calls, n)

    def test_offline_without_cache(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.load(offline=True, now=NOW, fetch=self.fetch, cache_file=self.cache)
        self.assertEqual(self.calls, 0)

    def test_unknown_period(self):
        c = catalog.load(now=NOW, fetch=self.fetch, cache_file=self.cache)
        with self.assertRaises(catalog.CatalogError) as cm:
            c.get(Period(100, 1))
        self.assertIn("115-07/08", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
