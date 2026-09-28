import unittest
from datetime import date

from invoice_lottery.batch import check_rows, parse_csv, total_amount
from invoice_lottery.periods import Period

from .helpers import real_catalog

TODAY = date(2026, 9, 29)


class ParseCsvTests(unittest.TestCase):
    def test_with_header(self):
        rows, errs = parse_csv("號碼,日期\n12345678,2026-07-01\nAB-87654321,115/08/02\n")
        self.assertEqual(errs, [])
        self.assertEqual([r.number for r in rows], ["12345678", "87654321"])
        self.assertEqual(rows[0].date, date(2026, 7, 1))
        self.assertEqual(rows[1].date, date(2026, 8, 2))
        self.assertEqual(rows[0].line, 2)

    def test_no_header_no_date(self):
        rows, errs = parse_csv("12345678\n87654321\n")
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0].date)

    def test_english_header_and_bom(self):
        rows, errs = parse_csv("﻿number,date\n12345678,2026-07-01\n")
        self.assertEqual((len(rows), errs), (1, []))

    def test_blank_and_comment_lines(self):
        rows, errs = parse_csv("\n# 備註\n12345678\n,\n")
        self.assertEqual((len(rows), errs), (1, []))

    def test_bad_number_reported_with_line(self):
        rows, errs = parse_csv("12345678\nabc\n1234\n87654321\n")
        self.assertEqual(len(rows), 2)
        self.assertEqual([e[0] for e in errs], [2, 3])

    def test_bad_date_reported(self):
        rows, errs = parse_csv("12345678,2026-02-30\n87654321,\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(errs[0][0], 1)
        self.assertIn("日期", errs[0][1])

    def test_quoted_and_spaces(self):
        rows, errs = parse_csv('"12345678", 2026-07-01 \n')
        self.assertEqual((len(rows), errs), (1, []))

    def test_extra_columns_ignored(self):
        rows, errs = parse_csv("12345678,2026-07-01,早餐,120\n")
        self.assertEqual((len(rows), errs), (1, []))

    def test_empty_file(self):
        self.assertEqual(parse_csv(""), ([], []))

    def test_header_only(self):
        self.assertEqual(parse_csv("號碼,日期\n"), ([], []))


class CheckRowsTests(unittest.TestCase):
    def setUp(self):
        self.cat = real_catalog()

    def rows(self, text):
        rows, errs = parse_csv(text)
        self.assertEqual(errs, [])
        return rows

    def test_default_latest_period(self):
        res = check_rows(self.rows("54348835\n12345678\n"), self.cat, today=TODAY)
        self.assertEqual([r.status for r in res], ["win", "lose"])
        self.assertEqual(total_amount(res), 200_000)

    def test_date_selects_period(self):
        # 2026-05-10 屬於 115-05/06：該期頭獎 24121106
        res = check_rows(self.rows("24121106,2026-05-10\n54348835,2026-05-10\n"), self.cat, today=TODAY)
        self.assertEqual([r.status for r in res], ["win", "lose"])
        self.assertEqual(res[0].period, Period(115, 5))

    def test_wrong_period_flagged_when_period_given(self):
        res = check_rows(self.rows("54348835,2026-05-10\n"), self.cat, Period(115, 7), TODAY)
        self.assertEqual(res[0].status, "wrong-period")
        self.assertIsNone(res[0].win)
        self.assertIn("115-05/06", res[0].message)

    def test_period_given_and_date_matches(self):
        res = check_rows(self.rows("54348835,2026-08-31\n"), self.cat, Period(115, 7), TODAY)
        self.assertEqual(res[0].status, "win")

    def test_not_yet_drawn(self):
        res = check_rows(self.rows("54348835,2026-09-15\n"), self.cat, today=TODAY)
        self.assertEqual(res[0].status, "no-data")
        self.assertIn("尚未開獎", res[0].message)

    def test_too_old(self):
        res = check_rows(self.rows("54348835,2020-01-15\n"), self.cat, today=TODAY)
        self.assertEqual(res[0].status, "no-data")

    def test_total_amount(self):
        res = check_rows(self.rows("89996565\n91098182\n99999111\n00000000\n"), self.cat, today=TODAY)
        self.assertEqual(total_amount(res), 10_000_000 + 2_000_000 + 200)


if __name__ == "__main__":
    unittest.main()
