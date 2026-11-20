# -*- coding: utf-8 -*-
"""檸檬人統計自動排程：範圍、行事曆內容、兩個行事曆都寫。"""
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from shared import lemon_ren_count_schedule as job

RESULT = {
    "days": [
        {"日期": "2027-02-04", "上午": 0, "下午": 1, "全天": 0, "晚上": 0, "合計": 1},
        {"日期": "2027-02-05", "上午": 0, "下午": 0, "全天": 0, "晚上": 0, "合計": 0},
        {"日期": "2027-02-17", "上午": 1, "下午": 1, "全天": 0, "晚上": 0, "合計": 2},
    ],
    "entries": [],
    "excluded": [{"date": "2026-11-23", "customer": "王上惠", "name": "檸檬人1"}],
}


class LemonRenCountScheduleTest(unittest.TestCase):
    def test_range_current_month_to_plus_3_month_end(self):
        self.assertEqual(job.date_range(date(2026, 11, 20)), ("2026-11-01", "2027-02-28"))
        self.assertEqual(job.date_range(date(2026, 1, 5)), ("2026-01-01", "2026-04-30"))

    def test_calendar_event_text(self):
        now = datetime(2026, 11, 20, 11, 0, tzinfo=job.TZ)
        ev = job.build_calendar_event("台北", RESULT, "2026-11-01", "2027-02-28", now)
        self.assertEqual(ev["summary"], "【檸檬人待換專員】台北 2 天 3 人次（11/20）")
        self.assertTrue(ev["description"].startswith(
            "檸檬人待換專員進度：\n02/04-下午-1\n02/17-上午-1，下午-1\n"))
        self.assertNotIn("王上惠", ev["description"])  # 只放排除後的結果

    def test_writes_both_calendars_and_reports_each(self):
        written = []

        def fake_insert(_service, calendar_id, **_event):
            if calendar_id.startswith("tpe"):
                raise PermissionError("403")
            written.append(calendar_id)

        with patch("shared.atm_match_reconcile_schedule._insert_event", side_effect=fake_insert):
            msgs, ok = job.write_calendar({"summary": "x"}, service_factory=lambda _cid: MagicMock())
        self.assertEqual(ok, 1)
        self.assertEqual(written, ["jenny@lemonclean.com.tw"])
        self.assertTrue(any("tpe@lemonclean.com.tw 失敗" in m for m in msgs))

    def test_run_dry_run(self):
        with patch.dict("accounts.ACCOUNTS", {"台北": {"email": "a", "password": "b"}}), \
             patch.object(job, "_log"):
            out = job.run(today=date(2026, 11, 20), count=lambda *a: RESULT, dry_run=True, log=lambda _t: None)
        self.assertEqual(out["range"], ("2026-11-01", "2027-02-28"))
        self.assertIn("台北", out["result"])


if __name__ == "__main__":
    unittest.main()
