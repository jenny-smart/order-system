# -*- coding: utf-8 -*-
"""清空未配班檸檬人排程：清空範圍、地區略過／失敗判斷。"""
import unittest
from datetime import date
from unittest.mock import patch

from shared import lemon_ren_clear_schedule as lrc

OK = {"found": 3, "people": 2, "cleared_days": 3, "slots": 5, "errors": []}


class RangeTest(unittest.TestCase):
    def test_current_month_to_plus_4_month_end(self):
        self.assertEqual(lrc.date_range(date(2026, 11, 20)), ("2026-11-01", "2027-03-31"))
        self.assertEqual(lrc.date_range(date(2027, 10, 31)), ("2027-10-01", "2028-02-29"))  # 閏年
        self.assertEqual(lrc.date_range(date(2026, 1, 5)), ("2026-01-01", "2026-05-31"))


class RunTest(unittest.TestCase):
    ACCOUNTS = {"台北": {"email": "a@x", "password": "p"}, "台中": {"email": "b@x", "password": "p"},
                "高雄": {"email": "", "password": ""}}

    def run_with(self, clear, regions=("台北", "台中", "高雄")):
        logs = []
        with patch("accounts.ACCOUNTS", self.ACCOUNTS), patch.object(lrc, "_log"):
            out = lrc.run(today=date(2026, 11, 20), regions=regions, clear=clear, log=logs.append)
        return out, logs

    def test_missing_credentials_skipped(self):
        calls = []
        out, logs = self.run_with(lambda env, e, p, s, t, log: calls.append((e, s, t)) or OK)
        self.assertEqual(calls, [("a@x", "2026-11-01", "2027-03-31"), ("b@x", "2026-11-01", "2027-03-31")])
        self.assertTrue(out["result"]["高雄"]["skipped"])
        self.assertIn("台北／清空檸檬人：2 人，3 天有清到資料，移除 5 筆勾選", logs)

    def test_region_error_raises_after_other_regions(self):
        calls = []

        def clear(env, e, p, s, t, log):
            calls.append(e)
            if e == "a@x":
                raise RuntimeError("登入失敗")
            return OK

        with self.assertRaises(RuntimeError):
            self.run_with(clear)
        self.assertEqual(calls, ["a@x", "b@x"])


if __name__ == "__main__":
    unittest.main()
