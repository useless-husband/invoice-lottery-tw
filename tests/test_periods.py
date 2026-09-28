import unittest
from datetime import date

from invoice_lottery.periods import Period, latest_drawn, parse_date


class ParseTests(unittest.TestCase):
    def test_variants(self):
        for s in ["115-07/08", "115-7/8", "115年07-08月", "115年 07~08月", "11507", "115/07-08"]:
            with self.subTest(s=s):
                self.assertEqual(Period.parse(s), Period(115, 7))

    def test_bad(self):
        for s in ["115-08/09", "115-07/09", "abc", "", "115-13/14", "2026-07/08"]:
            with self.subTest(s=s):
                with self.assertRaises(ValueError):
                    Period.parse(s)

    def test_even_start_month_rejected(self):
        with self.assertRaises(ValueError):
            Period(115, 8)

    def test_key_and_label(self):
        p = Period(115, 1)
        self.assertEqual(p.key, "115-01/02")
        self.assertEqual(p.label, "115年01-02月")
        self.assertEqual(Period.parse(p.key), p)


class FromDateTests(unittest.TestCase):
    def test_every_month(self):
        expected = {1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 5, 7: 7, 8: 7, 9: 9, 10: 9, 11: 11, 12: 11}
        for month, start in expected.items():
            with self.subTest(month=month):
                self.assertEqual(Period.from_date(date(2026, month, 15)), Period(115, start))

    def test_roc_conversion(self):
        self.assertEqual(Period.from_date(date(2026, 7, 1)).roc_year, 115)
        self.assertEqual(Period.from_date(date(2011, 3, 1)).roc_year, 100)
        self.assertEqual(Period.from_date(date(1912, 1, 1)).roc_year, 1)

    def test_year_boundary(self):
        self.assertEqual(Period.from_date(date(2026, 12, 31)), Period(115, 11))
        self.assertEqual(Period.from_date(date(2027, 1, 1)), Period(116, 1))

    def test_contains(self):
        p = Period(115, 7)
        self.assertTrue(p.contains(date(2026, 7, 1)))
        self.assertTrue(p.contains(date(2026, 8, 31)))
        self.assertFalse(p.contains(date(2026, 9, 1)))
        self.assertFalse(p.contains(date(2026, 6, 30)))

    def test_leap_february(self):
        self.assertEqual(Period(117, 1).last_day, date(2028, 2, 29))
        self.assertEqual(Period(115, 1).last_day, date(2026, 2, 28))


class DatesTests(unittest.TestCase):
    def test_draw_and_claim_match_official_page(self):
        # 財政部網頁：115 年 07-08 月 領獎期間自 115/10/06 起至 116/01/05 止
        p = Period(115, 7)
        self.assertEqual(p.draw_date, date(2026, 9, 25))
        self.assertEqual(p.claim_start, date(2026, 10, 6))
        self.assertEqual(p.claim_end, date(2027, 1, 5))

    def test_claim_matches_previous_period_page(self):
        # 115 年 05-06 月：115/08/06 至 115/11/05
        p = Period(115, 5)
        self.assertEqual((p.draw_date, p.claim_start, p.claim_end),
                         (date(2026, 7, 25), date(2026, 8, 6), date(2026, 11, 5)))

    def test_last_period_of_year_crosses_year(self):
        p = Period(115, 11)
        self.assertEqual(p.draw_date, date(2027, 1, 25))
        self.assertEqual(p.claim_start, date(2027, 2, 6))
        self.assertEqual(p.claim_end, date(2027, 5, 5))

    def test_first_period(self):
        p = Period(116, 1)
        self.assertEqual((p.draw_date, p.claim_start, p.claim_end),
                         (date(2027, 3, 25), date(2027, 4, 6), date(2027, 7, 5)))

    def test_next_prev(self):
        self.assertEqual(Period(115, 11).next(), Period(116, 1))
        self.assertEqual(Period(116, 1).prev(), Period(115, 11))
        self.assertEqual(Period(115, 5).next().prev(), Period(115, 5))

    def test_ordering(self):
        self.assertLess(Period(115, 11), Period(116, 1))
        self.assertLess(Period(115, 3), Period(115, 5))

    def test_status(self):
        p = Period(115, 7)
        self.assertEqual(p.status(date(2026, 9, 24)), "pending")
        self.assertEqual(p.status(date(2026, 9, 25)), "claimable")
        self.assertEqual(p.status(date(2027, 1, 5)), "claimable")
        self.assertEqual(p.status(date(2027, 1, 6)), "expired")

    def test_latest_drawn(self):
        self.assertEqual(latest_drawn(date(2026, 9, 24)), Period(115, 5))
        self.assertEqual(latest_drawn(date(2026, 9, 25)), Period(115, 7))
        self.assertEqual(latest_drawn(date(2027, 1, 10)), Period(115, 9))
        self.assertEqual(latest_drawn(date(2027, 1, 25)), Period(115, 11))
        self.assertEqual(latest_drawn(date(2027, 2, 1)), Period(115, 11))


class ParseDateTests(unittest.TestCase):
    def test_ad_formats(self):
        for s in ["2026-07-15", "2026/7/15", "20260715", "2026.07.15"]:
            with self.subTest(s=s):
                self.assertEqual(parse_date(s), date(2026, 7, 15))

    def test_roc_formats(self):
        for s in ["115/07/15", "1150715", "115-7-15"]:
            with self.subTest(s=s):
                self.assertEqual(parse_date(s), date(2026, 7, 15))

    def test_roc_two_digit_year(self):
        self.assertEqual(parse_date("99/12/31"), date(2010, 12, 31))

    def test_bad(self):
        for s in ["2026-02-30", "hello", "", "2026-13-01", "115/00/10"]:
            with self.subTest(s=s):
                with self.assertRaises(ValueError):
                    parse_date(s)


if __name__ == "__main__":
    unittest.main()
