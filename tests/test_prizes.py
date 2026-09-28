import unittest

from invoice_lottery.periods import Period
from invoice_lottery.prizes import (
    PeriodData,
    could_win,
    evaluate,
    format_amount,
    is_valid_number,
    last3_candidates,
    normalize_number,
)

from .helpers import DATA


class NormalizeTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(normalize_number("12345678"), "12345678")

    def test_with_track_letters(self):
        self.assertEqual(normalize_number("AB-12345678"), "12345678")
        self.assertEqual(normalize_number("ab12345678"), "12345678")
        self.assertEqual(normalize_number(" AB 12345678 "), "12345678")

    def test_invalid(self):
        for bad in ["1234567", "123456789", "abcdefgh", "", "A12345678", "ABC12345678"]:
            with self.subTest(bad=bad):
                self.assertFalse(is_valid_number(bad))
                with self.assertRaises(ValueError):
                    normalize_number(bad)


class EvaluateTests(unittest.TestCase):
    def test_special(self):
        w = evaluate("89996565", DATA)
        self.assertEqual((w.prize, w.amount), ("特別獎", 10_000_000))

    def test_grand(self):
        w = evaluate("91098182", DATA)
        self.assertEqual((w.prize, w.amount), ("特獎", 2_000_000))

    def test_first(self):
        for n in DATA.first:
            w = evaluate(n, DATA)
            self.assertEqual((w.prize, w.amount), ("頭獎", 200_000))

    def test_second_to_sixth(self):
        f = "54348835"
        cases = [("94348835", "二獎", 40_000), ("99348835", "三獎", 10_000),
                 ("99948835", "四獎", 4_000), ("99998835", "五獎", 1_000), ("99999835", "六獎", 200)]
        for n, name, amount in cases:
            with self.subTest(n=n):
                w = evaluate(n, DATA)
                self.assertEqual((w.prize, w.amount), (name, amount))

    def test_second_matches_any_first_number(self):
        w = evaluate("10991397", DATA)  # 末 6 碼 991397 屬於第二組頭獎
        self.assertEqual(w.prize, "三獎")

    def test_no_win(self):
        self.assertIsNone(evaluate("12345678", DATA))
        self.assertIsNone(evaluate("00000000", DATA))

    def test_last2_is_not_enough(self):
        self.assertIsNone(evaluate("99999935", DATA))

    def test_boundary_last3_match_only(self):
        # 末 4 碼差一碼：8835 vs 9835 -> 只剩末 3 碼 835 -> 六獎
        self.assertEqual(evaluate("00009835", DATA).prize, "六獎")

    def test_special_number_only_gets_highest_prize(self):
        # 特別獎號碼的末 7 碼剛好等於某頭獎末 7 碼：仍只給特別獎，不重複計算
        data = PeriodData(Period(115, 7), "12345678", "91098182", ("22345678",))
        w = evaluate("12345678", data)
        self.assertEqual((w.prize, w.amount), ("特別獎", 10_000_000))

    def test_special_prize_does_not_award_lower_by_suffix(self):
        # 只有「頭獎」號碼的末幾碼才能對二～六獎；特別獎的末碼不算
        data = PeriodData(Period(115, 7), "89996565", "91098182", ("54348835",))
        self.assertIsNone(evaluate("11111565", data))  # 565 是特別獎末三碼，但不是頭獎
        self.assertIsNone(evaluate("11111182", data))

    def test_first_number_is_not_also_paid_as_lower_prizes(self):
        w = evaluate("54348835", DATA)
        self.assertEqual(w.amount, 200_000)

    def test_same_number_first_and_special_takes_max(self):
        data = PeriodData(Period(115, 7), "11111111", "22222222", ("11111111",))
        self.assertEqual(evaluate("11111111", data).prize, "特別獎")

    def test_picks_highest_across_multiple_first_numbers(self):
        data = PeriodData(Period(115, 7), "00000001", "00000002", ("12345678", "99945678"))
        # 22245678 對第一組末 5 碼 = 四獎，對第二組末 5 碼 = 四獎；改用末 6 碼 345678 對兩組皆為三獎
        self.assertEqual(evaluate("00345678", data).prize, "三獎")
        self.assertEqual(evaluate("11145678", data).prize, "四獎")

    def test_accepts_track_prefix(self):
        self.assertEqual(evaluate("AB-89996565", DATA).prize, "特別獎")

    def test_invalid_number_raises(self):
        with self.assertRaises(ValueError):
            evaluate("123", DATA)


class ExtraSixthTests(unittest.TestCase):
    def setUp(self):
        self.data = PeriodData(Period(110, 1), "11111111", "22222222", ("33333333",), ("123", "456"))

    def test_extra_sixth_wins_200(self):
        w = evaluate("99999123", self.data)
        self.assertEqual((w.prize, w.amount), ("增開六獎", 200))

    def test_extra_sixth_not_in_normal_data(self):
        self.assertIsNone(evaluate("99999123", DATA))

    def test_higher_prize_beats_extra_sixth(self):
        data = PeriodData(Period(110, 1), "11111111", "22222222", ("33333333",), ("333",))
        self.assertEqual(evaluate("99999333", data).prize, "六獎")  # 同為 200，不會重複
        self.assertEqual(evaluate("99933333", data).prize, "四獎")

    def test_could_win_includes_extra(self):
        self.assertTrue(could_win("456", self.data))


class CouldWinTests(unittest.TestCase):
    def test_candidates(self):
        self.assertEqual(last3_candidates(DATA), {"565", "182", "835", "397", "111"})

    def test_could_win(self):
        self.assertTrue(could_win("835", DATA))
        self.assertTrue(could_win("565", DATA))  # 特別獎末三碼也要請使用者輸入完整號碼
        self.assertFalse(could_win("000", DATA))

    def test_could_win_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            could_win("12", DATA)

    def test_every_winner_passes_quick_filter(self):
        # 只要 evaluate 有中，末三碼一定在候選集合裡（快速模式不會漏掉）
        for i in range(0, 100_000_000, 99_991):
            n = f"{i:08d}"
            if evaluate(n, DATA):
                self.assertTrue(could_win(n[-3:], DATA), n)


class DataValidationTests(unittest.TestCase):
    def test_bad_numbers_rejected(self):
        with self.assertRaises(ValueError):
            PeriodData(Period(115, 7), "123", "91098182", ("54348835",))
        with self.assertRaises(ValueError):
            PeriodData(Period(115, 7), "89996565", "91098182", ())
        with self.assertRaises(ValueError):
            PeriodData(Period(115, 7), "89996565", "91098182", ("54348835",), ("12",))

    def test_format_amount(self):
        self.assertEqual(format_amount(10_000_000), "10,000,000")


if __name__ == "__main__":
    unittest.main()
