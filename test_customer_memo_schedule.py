# -*- coding: utf-8 -*-
"""客人備註非空白排程：區間、貼表格式、重複略過、行事曆內容。"""
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from shared import customer_memo_schedule as cms
from function import customer_memo_query as cmq


class ImportOrderTest(unittest.TestCase):
    def test_fresh_interpreter_can_use_gsheet_after_preload(self):
        """全新直譯器（同 GitHub Actions）：先 _preload_modules 再用 shared.gsheet 不可 ImportError。"""
        import subprocess
        import sys
        code = ("import shared.customer_memo_schedule as m; m._preload_modules(); "
                "from shared.gsheet import build_gsheet_client, get_service_account_info; "
                "from shared.atm_match_reconcile_schedule import _calendar_service; "
                "from shared.execution_log_service import log_execution; print('ok')")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        self.assertIn("ok", out.stdout)


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


class NoticeFlagTest(unittest.TestCase):
    A = "台北市士林區至誠路一段152巷6弄4號"

    def item(self, no, notice, payway="信用卡"):
        return {"order_no": no, "name": "魏", "phone": "0987652932", "address": self.A,
                "notice": notice, "payway": payway, "purchase_status": "1"}

    def test_vip_not_stored_value_and_returning_n_tag(self):
        history = [self.item("LC00217726", ""), self.item("LC00220070", "")]
        cands = [
            self.item("LC00220070", "**N-B**\n10/22 減時"),          # 有更早訂單 → 註記
            self.item("LC00220071", "**VIP**二女", payway="ATM"),     # VIP 非儲值金 → 註記
            self.item("LC00220072", "**VIP**二女", payway="儲值金"),  # 不註記
            self.item("LC00220073", "一般備註"),                       # 不註記
        ]
        with patch.object(cmq._memo, "search_all_orders_by_phone", return_value=history):
            out = cmq.find_notice_flag_orders(cands, session=object())
        self.assertEqual([r["訂單號碼"] for r in out], ["LC00220070", "LC00220071"])
        self.assertIn("**N-B** 已非首次服務／本次改為 **O-B**", out[0]["註記"])
        self.assertIn("付款方式：備註標示 VIP／本次 ATM", out[1]["註記"])

    def test_first_service_n_tag_not_flagged(self):
        with patch.object(cmq._memo, "search_all_orders_by_phone", return_value=[self.item("LC5", "")]):
            out = cmq.find_notice_flag_orders([self.item("LC5", "**N-A**首次")], session=object())
        self.assertEqual(out, [])

    def test_notice_sheet_row(self):
        rows = cms.build_notice_sheet_rows([{"訂單號碼": "LC1", "客人姓名": "王", "電話": "0912", "服務日期": "11/15",
                                             "付款方式": "ATM", "註記": "x", "客服備註": "**VIP**"}], "https://b")
        self.assertEqual(len(rows[0]), len(cms.NOTICE_HEADER))
        self.assertEqual(cms.NOTICE_HEADER[0], "註記")
        self.assertEqual(rows[0][0], "x")       # 註記在最前方
        self.assertEqual(rows[0][1], "LC1")
        self.assertTrue(rows[0][3].startswith('=HYPERLINK("https://b/purchase?'))

    def test_append_notice_tab_dedupes_by_order_column_b(self):
        ws = MagicMock(row_count=1000)
        ws.col_values.side_effect = lambda col: {1: ["註記", "x"], 2: ["訂單編號", "LC1"]}[col]
        saved = cms.append_rows(ws, [["x", "LC1"] + [""] * 5, ["y", "LC2"] + [""] * 5],
                                width=7, key_col=cms.NOTICE_KEY_COL)
        self.assertEqual(saved, 1)
        self.assertEqual(ws.update.call_args.kwargs["range_name"], "A3:G3")
        self.assertEqual(ws.update.call_args.kwargs["values"][0][1], "LC2")


class CalendarTest(unittest.TestCase):
    def test_event_summary_includes_notice_count(self):
        result = {"台北": {"saved": 1, "rows": [], "notice_saved": 2,
                           "notice_rows": [{"訂單號碼": "LC1", "客人姓名": "王", "註記": "付款方式：…"}]}}
        ev = cms.build_calendar_event(result, (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10)),
                                      datetime(2026, 11, 10, 10, 5))
        self.assertIn("客服備註需註記 2 筆", ev["summary"])
        self.assertIn("LC1 王：付款方式", ev["description"])

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
