# -*- coding: utf-8 -*-
"""客人備註非空白排程：區間、貼表格式、重複略過、行事曆內容。"""
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from shared import customer_memo_schedule as cms
from function import customer_memo_query as cmq


class WindowTest(unittest.TestCase):
    def test_tuesday_uses_monday_10(self):
        self.assertEqual(cms.query_window(date(2026, 11, 10), {}),
                         (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10)))

    def test_monday_covers_weekend_from_friday(self):
        self.assertEqual(cms.query_window(date(2026, 11, 9), {})[0], datetime(2026, 11, 6, 10))

    def test_holiday_skipped_back_to_last_workday(self):
        cal = {date(2026, 11, 6): True}  # 週五放假
        self.assertEqual(cms.query_window(date(2026, 11, 9), cal)[0], datetime(2026, 11, 5, 10))

    def test_off_day_does_not_run(self):
        self.assertFalse(cms.run(today=date(2026, 11, 8), calendar={})["due"])


class SheetTest(unittest.TestCase):
    def test_phone_is_hyperlink_to_backend_search(self):
        rows = cms.build_sheet_rows([{"訂單號碼": "LC1", "客人姓名": "王", "電話": "0987652932",
                                      "服務日期": "2026/11/15", "客人備註": "帶拖鞋", "客服備註": ""}],
                                    "https://backend.lemonclean.com.tw")
        self.assertEqual(rows[0][0], "LC1")
        self.assertTrue(rows[0][2].startswith('=HYPERLINK("https://backend.lemonclean.com.tw/purchase?keyword=&name=&phone=0987652932&'))
        self.assertTrue(rows[0][2].endswith(',"0987652932")'))
        self.assertEqual(rows[0][3:], ["2026/11/15", "帶拖鞋", ""])

    def test_append_skips_existing_and_writes_after_last_row(self):
        ws = MagicMock(row_count=1000)
        ws.col_values.return_value = ["訂單編號", "LC1", "LC2", "", ""]
        saved = cms.append_rows(ws, [["LC2", "", "", "", "", ""], ["LC3", "", "", "", "", ""]])
        self.assertEqual(saved, 1)
        kwargs = ws.update.call_args.kwargs
        self.assertEqual(kwargs["range_name"], "A4:F4")
        self.assertEqual(kwargs["value_input_option"], "USER_ENTERED")


class QueryTest(unittest.TestCase):
    def test_created_window_filter(self):
        items = [
            {"order_no": "LC1", "row_text": "LC1\n2026-11-09 09:59:00", "raw_date_obj": datetime(2026, 11, 9)},
            {"order_no": "LC2", "row_text": "LC2\n2026-11-09 10:00:00", "raw_date_obj": datetime(2026, 11, 9)},
            {"order_no": "LC3", "row_text": "LC3\n2026-11-10 10:00:00", "raw_date_obj": datetime(2026, 11, 10)},
        ]

        def enrich(session, xs, **k):
            for x in xs:
                x["customer_memo"] = "備註"
            return xs

        with patch.object(cmq._memo, "fetch_purchase_list_all_pages", return_value=items), \
                patch.object(cmq._memo, "enrich_items_from_detail", side_effect=enrich):
            out = cmq.search_customer_memo_orders("2026/11/09", "2026/11/10", session=object(),
                                                  created_from=datetime(2026, 11, 9, 10),
                                                  created_to=datetime(2026, 11, 10, 10))
        self.assertEqual([r["訂單號碼"] for r in out], ["LC2"])
        self.assertIn("服務日期", out[0])


class CalendarTest(unittest.TestCase):
    def test_event_summary_and_reminder(self):
        result = {"台北": {"saved": 2, "rows": [{"訂單號碼": "LC1", "客人姓名": "王", "服務日期": "11/15", "客人備註": "a"}],
                           "sheet_url": "https://x"}, "台中": {"saved": 0, "rows": []}}
        ev = cms.build_calendar_event(result, (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10)),
                                      datetime(2026, 11, 10, 10, 5))
        self.assertEqual(ev["summary"], "【客人備註】台北 2 筆、台中 0 筆（11/10）")
        self.assertIn("https://x", ev["description"])
        self.assertEqual(ev["reminder_minutes"], [0])


if __name__ == "__main__":
    unittest.main()
