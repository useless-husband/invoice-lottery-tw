import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from invoice_lottery import cli, sources, store
from invoice_lottery.periods import Period

from .helpers import DATA, ROOT, fixture

TODAY = date(2026, 9, 29)


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        store.save_cache(sources.parse_rss(fixture("invoice.xml")), "fixture", datetime.now(timezone.utc),
                         self.dir / store.CACHE_FILE)
        p = mock.patch.dict(os.environ, {"INVOICE_LOTTERY_CACHE_DIR": str(self.dir)})
        p.start()
        self.addCleanup(p.stop)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, today=TODAY)
        return code, out.getvalue(), err.getvalue()


class NumbersTests(CliCase):
    def test_latest(self):
        code, out, _ = self.run_cli("numbers", "--offline")
        self.assertEqual(code, 0)
        for s in ["115年07-08月", "89996565", "91098182", "54348835", "4348835", "835", "2027-01-05"]:
            self.assertIn(s, out)

    def test_specific_period(self):
        code, out, _ = self.run_cli("numbers", "--period", "115-05/06", "--offline")
        self.assertEqual(code, 0)
        self.assertIn("38548029", out)

    def test_unknown_period(self):
        code, _, err = self.run_cli("numbers", "--period", "100-01/02", "--offline")
        self.assertEqual(code, 2)
        self.assertIn("沒有", err)

    def test_bad_period_text(self):
        code, _, err = self.run_cli("numbers", "--period", "hello", "--offline")
        self.assertEqual(code, 2)

    def test_format_numbers_with_extra_sixth(self):
        from invoice_lottery.prizes import PeriodData
        d = PeriodData(Period(110, 1), "11111111", "22222222", ("33333333",), ("123",))
        self.assertIn("增開六獎", cli.format_numbers(d))


class CheckTests(CliCase):
    def test_win_exit_0(self):
        code, out, _ = self.run_cli("check", "89996565", "--offline")
        self.assertEqual(code, 0)
        self.assertIn("特別獎", out)
        self.assertIn("10,000,000", out)

    def test_lose_exit_1(self):
        code, out, _ = self.run_cli("check", "12345678", "--offline")
        self.assertEqual(code, 1)
        self.assertIn("沒中", out)

    def test_bad_number_exit_2(self):
        code, _, err = self.run_cli("check", "1234", "--offline")
        self.assertEqual(code, 2)
        self.assertIn("8 位數字", err)

    def test_wrong_period_warns(self):
        code, out, _ = self.run_cli("check", "54348835", "--period", "115-07/08", "--date", "2026-05-03", "--offline")
        self.assertEqual(code, 2)
        self.assertIn("115-05/06", out)

    def test_date_picks_period(self):
        code, out, _ = self.run_cli("check", "24121106", "--date", "2026-06-01", "--offline")
        self.assertEqual(code, 0)
        self.assertIn("115-05/06", out)

    def test_track_prefix(self):
        code, _, _ = self.run_cli("check", "AB-54348835", "--offline")
        self.assertEqual(code, 0)

    def test_expired_warning(self):
        code, out, _ = self.run_cli("check", "12345678", "--period", "114-09/10", "--offline")
        self.assertIn("領獎期限", out)


class QuickTests(unittest.TestCase):
    def run_quick(self, lines):
        it = iter(lines)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise EOFError

        out = io.StringIO()
        stats = cli.run_quick(DATA, out, fake_input)
        return stats, out.getvalue()

    def test_no_win_moves_on(self):
        stats, out = self.run_quick(["000", "999", "q"])
        self.assertEqual(stats["count"], 2)
        self.assertEqual(out.count("沒中"), 2)

    def test_possible_then_confirm_full(self):
        stats, out = self.run_quick(["835", "54348835", "q"])
        self.assertIn("可能中獎", out)
        self.assertEqual((stats["wins"], stats["total"]), (1, 200_000))

    def test_five_digit_prefix_accepted(self):
        stats, _ = self.run_quick(["835", "54348", "q"])
        self.assertEqual(stats["total"], 200_000)

    def test_false_alarm(self):
        stats, out = self.run_quick(["565", "11111565", "q"])
        self.assertEqual(stats["wins"], 0)
        self.assertIn("整組不同", out)

    def test_wrong_last3_reprompts(self):
        stats, out = self.run_quick(["835", "54348999", "54348835", "q"])
        self.assertIn("不一樣", out)
        self.assertEqual(stats["wins"], 1)

    def test_skip_is_counted_as_unsure(self):
        stats, out = self.run_quick(["835", "", "q"])
        self.assertEqual(stats["unsure"], 1)
        self.assertIn("沒確認", out)

    def test_blank_line_is_ignored(self):
        stats, _ = self.run_quick(["", "  ", "000", "q"])
        self.assertEqual(stats["count"], 1)

    def test_invalid_input(self):
        stats, out = self.run_quick(["12", "abcd", "q"])
        self.assertEqual(stats["count"], 0)
        self.assertEqual(out.count("請輸入 3 位數字"), 2)

    def test_pasting_full_number_works(self):
        stats, _ = self.run_quick(["89996565", "q"])
        self.assertEqual(stats["total"], 10_000_000)

    def test_eof_ends_and_summarises(self):
        stats, out = self.run_quick(["000"])
        self.assertIn("共對了 1 張", out)

    def test_total_summary(self):
        stats, out = self.run_quick(["835", "54348835", "397", "99999397", "q"])
        self.assertEqual(stats["total"], 200_200)
        self.assertIn("200,200", out)

    def test_quit_variants(self):
        for q in ("q", "Q", "quit"):
            stats, _ = self.run_quick([q, "000"])
            self.assertEqual(stats["count"], 0)


class BatchTests(CliCase):
    def write(self, name, text, encoding="utf-8"):
        p = self.dir / name
        p.write_bytes(text.encode(encoding))
        return str(p)

    def test_batch_summary(self):
        f = self.write("a.csv", "號碼,日期\n54348835,2026-08-01\n12345678,2026-08-02\n99999111,2026-07-03\n")
        code, out, _ = self.run_cli("batch", f, "--offline")
        self.assertEqual(code, 0)
        self.assertIn("中獎清單", out)
        self.assertIn("200,200", out)
        self.assertIn("中獎 2 張", out)

    def test_batch_bad_lines_go_to_stderr(self):
        f = self.write("b.csv", "54348835\nxyz\n")
        code, out, err = self.run_cli("batch", f, "--offline")
        self.assertEqual(code, 0)
        self.assertIn("第 2 行", err)
        self.assertIn("1 行格式錯誤", out)

    def test_batch_wrong_period_reported(self):
        f = self.write("c.csv", "54348835,2026-05-05\n")
        code, out, _ = self.run_cli("batch", f, "--period", "115-07/08", "--offline")
        self.assertIn("錯期", out)
        self.assertIn("沒有中獎", out)

    def test_batch_missing_file(self):
        code, _, err = self.run_cli("batch", str(self.dir / "nope.csv"), "--offline")
        self.assertEqual(code, 2)
        self.assertIn("讀不到檔案", err)

    def test_batch_not_utf8(self):
        f = self.write("big5.csv", "號碼,日期\n54348835,2026-08-01\n", encoding="big5")
        code, _, err = self.run_cli("batch", f, "--offline")
        self.assertEqual(code, 2)
        self.assertIn("UTF-8", err)

    def test_batch_bom_utf8(self):
        f = self.write("bom.csv", "﻿號碼,日期\n54348835,2026-08-01\n")
        code, out, _ = self.run_cli("batch", f, "--offline")
        self.assertIn("中獎 1 張", out)


class ExportTests(CliCase):
    def test_export_file(self):
        target = self.dir / "out" / "data.json"
        code, out, _ = self.run_cli("export-json", str(target), "--offline")
        self.assertEqual(code, 0)
        doc = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(doc["periods"][0]["period"], "115-07/08")
        self.assertEqual(len(doc["periods"]), 6)

    def test_export_stdout(self):
        code, out, _ = self.run_cli("export-json", "-", "--offline")
        self.assertEqual(json.loads(out)["version"], 1)

    def test_no_command_prints_help(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("numbers", out)


class CommittedDataTests(unittest.TestCase):
    def test_web_data_json_is_valid(self):
        doc = json.loads((ROOT / "web" / "data.json").read_text(encoding="utf-8"))
        periods = store.load_dict(doc)
        self.assertGreaterEqual(len(periods), 1)
        for o, d in zip(doc["periods"], periods):
            self.assertEqual(o["draw_date"], d.period.draw_date.isoformat())
            self.assertEqual(o["claim_end"], d.period.claim_end.isoformat())

    def test_no_local_paths_in_repo_text_files(self):
        needle = "/Us" + "ers/" + "macmini" + "2tb"
        for p in ROOT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and p.suffix in {".py", ".md", ".json", ".js", ".html", ".css", ".yml", ".toml"}:
                self.assertNotIn(needle, p.read_text(encoding="utf-8"), str(p))


if __name__ == "__main__":
    unittest.main()
