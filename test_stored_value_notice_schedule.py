# -*- coding: utf-8 -*-
"""儲值金訂單客服備註空白排程：區間、行事曆內容、訂購時間篩選。"""
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import orders
from shared import stored_value_notice_schedule as svn


class WindowTest(unittest.TestCase):
    def test_tuesday_uses_monday_0800(self):
        self.assertEqual(svn.query_window(date(2026, 11, 10), {}),
                         (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 8)))

    def test_monday_covers_weekend_from_friday(self):
        self.assertEqual(svn.query_window(date(2026, 11, 9), {})[0], datetime(2026, 11, 6, 8))

    def test_holiday_skipped_back_to_last_workday(self):
        self.assertEqual(svn.query_window(date(2026, 11, 9), {date(2026, 11, 6): True})[0], datetime(2026, 11, 5, 8))

    def test_off_day_does_not_run(self):
        self.assertFalse(svn.run(today=date(2026, 11, 8), calendar={})["due"])


ROWS = [{"order_no": "LC00000002", "name": "王小明", "purchase_status": "已付款", "created_time": "2026-11-09 15:30:00"},
        {"order_no": "LC00000003", "name": "", "purchase_status": "待付款", "created_time": "2026-11-10 07:59:00"}]


class RunTest(unittest.TestCase):
    def test_queries_each_region_and_writes_calendar(self):
        calls = []

        def query(env, email, password, window):
            calls.append((env, email, window))
            return ROWS if email == "tp@x" else []

        accounts = {"台北": {"email": "tp@x", "password": "p"}, "台中": {"email": "tc@x", "password": "p"}}
        with patch("accounts.ACCOUNTS", accounts), patch.object(svn, "write_calendar", return_value=["ok"]) as cal, \
                patch.object(svn, "_log"):
            out = svn.run(today=date(2026, 11, 10), calendar={}, query=query, now=datetime(2026, 11, 10, 8, 20, tzinfo=svn.TZ))
        self.assertEqual([c[1] for c in calls], ["tp@x", "tc@x"])
        self.assertEqual(calls[0][2], (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 8)))
        self.assertEqual(len(out["result"]["台北"]["rows"]), 2)
        cal.assert_called_once()

    def test_dry_run_skips_calendar_and_missing_account_is_error(self):
        with patch("accounts.ACCOUNTS", {"台北": {"email": "a", "password": "b"}}), \
                patch.object(svn, "write_calendar") as cal, patch.object(svn, "_log"):
            out = svn.run(today=date(2026, 11, 10), calendar={}, dry_run=True, query=lambda *a: [])
        cal.assert_not_called()
        self.assertIn("未設定後台帳密", out["result"]["台中"]["error"])


class CalendarEventTest(unittest.TestCase):
    def test_event_lists_names(self):
        event = svn.build_calendar_event({"台北": {"rows": ROWS, "error": ""}, "台中": {"rows": [], "error": "X"}},
                                         (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 8)),
                                         datetime(2026, 11, 10, 8, 20, tzinfo=svn.TZ))
        self.assertEqual(event["summary"], "【儲值金客服備註空白】台北 2 筆、台中 0 筆（11/10）")
        self.assertIn("訂購人：王小明、（無姓名）", event["description"])
        self.assertIn("王小明 LC00000002 已付款 11-09 15:30", event["description"])
        self.assertIn("■ 台中：0 筆（X）", event["description"])
        self.assertEqual(event["replace_prefix"], "【儲值金客服備註空白】")

    def test_write_calendar_falls_back_to_second_calendar(self):
        inserted = []

        def insert(service, calendar_id, **event):
            if calendar_id == "jenny@hers.com.tw":
                raise RuntimeError("404")
            inserted.append(calendar_id)

        with patch("shared.atm_match_reconcile_schedule._insert_event", insert):
            msg = svn.write_calendar({"台北": {"rows": [], "error": ""}}, (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 8)),
                                     datetime(2026, 11, 10, 8, 20, tzinfo=svn.TZ), service_factory=lambda cid: MagicMock())
        self.assertEqual(inserted, ["jenny@lemonclean.com.tw"])
        self.assertIn("jenny@lemonclean.com.tw", msg[0])


class CreatedTimeFilterTest(unittest.TestCase):
    def test_extract_created_datetime(self):
        lines = ["LC00000002", "王小明", "0912345678", "2026-11-09 15:30:12", "2026-11-20  (五)"]
        self.assertEqual(orders._extract_created_datetime_from_block_lines(lines), datetime(2026, 11, 9, 15, 30, 12))
        self.assertIsNone(orders._extract_created_datetime_from_block_lines(["沒有時間"]))

    def test_find_pending_filters_by_created_time(self):
        def card(no, created):
            return {"order_no": no, "lines": [no, "王小明", "0912345678", created, "2026-11-20", "付款狀態：已付款"]}

        page = MagicMock(status_code=200, text="")
        with patch.object(orders, "compute_env_url_tuple", return_value=("https://b",) * 10), \
                patch.object(orders, "login", return_value=True), \
                patch.object(orders.requests, "Session") as session_cls, \
                patch.object(orders, "extract_order_cards_from_purchase_html", return_value=[
                    card("LC1", "2026-11-09 07:59:59"), card("LC2", "2026-11-09 08:00:00"),
                    card("LC3", "2026-11-10 07:59:00"), card("LC4", "2026-11-10 08:00:00")]), \
                patch.object(orders, "_extract_notice_map_from_raw_html", return_value={}), \
                patch.object(orders, "_extract_edit_id_map_from_raw_html", return_value={}), \
                patch.object(orders, "_fetch_order_edit_notice", return_value=""):
            session_cls.return_value.get.return_value = page
            rows = orders.find_pending_stored_value_orders(
                "prod", "e", "p", date_s="2026-11-09", date_e="2026-11-10", purchase_status=["0", "1"],
                created_from=datetime(2026, 11, 9, 8), created_to=datetime(2026, 11, 10, 8))
        self.assertEqual([r["order_no"] for r in rows], ["LC2", "LC3"])
        self.assertEqual(rows[0]["created_time"], "2026-11-09 08:00:00")
        self.assertEqual(rows[0]["name"], "王小明")


if __name__ == "__main__":
    unittest.main()
