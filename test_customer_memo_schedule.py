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
                         (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 8)))

    def test_monday_covers_weekend_from_friday(self):
        self.assertEqual(cms.query_window(date(2026, 11, 9), {})[0], datetime(2026, 11, 6, 8))

    def test_holiday_skipped_back_to_last_workday(self):
        cal = {date(2026, 11, 6): True}  # 週五放假
        self.assertEqual(cms.query_window(date(2026, 11, 9), cal)[0], datetime(2026, 11, 5, 8))

    def test_off_day_does_not_run(self):
        self.assertFalse(cms.run(today=date(2026, 11, 8), calendar={})["due"])


class SheetTest(unittest.TestCase):
    def test_phone_is_hyperlink_to_backend_search(self):
        rows = cms.build_sheet_rows([{"訂單號碼": "LC1", "客人姓名": "王", "電話": "0987652932",
                                      "服務日期": "2026/11/15", "客人備註": "帶拖鞋", "客服備註": ""}],
                                    "https://backend.lemonclean.com.tw", "2026/11/11 10:30")
        self.assertEqual(cms.HEADER, ["備註日期時間", "訂單編號", "訂購人", "電話號碼", "預約日期", "客人備註", "客服備註"])
        self.assertEqual(rows[0][:2], ["2026/11/11 10:30", "LC1"])
        self.assertTrue(rows[0][3].startswith('=HYPERLINK("https://backend.lemonclean.com.tw/purchase?keyword=&name=&phone=0987652932&'))
        self.assertTrue(rows[0][3].endswith(',"0987652932")'))
        self.assertEqual(rows[0][4:], ["2026/11/15", "帶拖鞋", ""])

    def test_append_skips_existing_and_writes_after_last_row(self):
        ws = MagicMock(row_count=1000)
        ws.col_values.return_value = ["訂單編號", "LC1", "LC2", "", ""]
        saved = cms.append_rows(ws, [["LC2", "", "", "", "", "", ""], ["LC3", "", "", "", "", "", ""]])
        self.assertEqual(saved, 1)
        kwargs = ws.update.call_args.kwargs
        self.assertEqual(kwargs["range_name"], "A4:G4")
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

    def test_notice_sheet_row_sections(self):
        rows = [
            {"order_id": "LC3", "customer_name": "魏", "phone": "0987", "address": "A", "service_date": "2026/11/15",
             "purchase_status_name": "已付款", "section": "processed", "has_history": True, "can_autofill": True,
             "own_notice": "**N-A**x", "service_change": "新客標記：**N-A** 已非首次服務／本次改為 **O-A**",
             "source_notice_preview": "【服務異動】…", "latest_same_order_id": "LC1", "latest_same_order_date": "2026/10/31",
             "source_service_items_text": "居家清潔（a）", "service_items_text": "居家清潔（b）",
             "source_service_time_text": "14:00-17:00（3小時）", "service_time_text": "14:00-17:00（3小時）"},
            {"order_id": "LC8", "customer_name": "戴", "phone": "0916", "address": "B", "service_date": "2026/11/15",
             "purchase_status_name": "已付款", "has_history": False, "is_new_order": True, "can_autofill": False,
             "own_notice": "", "service_change": "", "source_notice_preview": ""},
        ]
        out = cms.build_notice_sheet_rows(rows, "https://b", "2026/11/11 10:30")
        self.assertEqual(cms.NOTICE_HEADER, ["備註日期時間", "標記", "訂單編號", "訂購人", "電話號碼", "地址", "服務日期",
                                             "付款狀態", "異動單號", "異動項目", "異動時數", "異動客服備註", "異動註記"])
        self.assertEqual(len(out[0]), len(cms.NOTICE_HEADER))
        self.assertEqual(out[0][:3], ["2026/11/11 10:30", "⚠️ N→O", "LC3"])
        self.assertTrue(out[0][4].startswith('=HYPERLINK("https://b/purchase?'))
        self.assertEqual(out[0][8], "LC1 2026/10/31")      # 異動單號
        self.assertIn("→", out[0][9])                       # 異動項目
        self.assertEqual(out[0][11], "保留原備註＋註記")     # 異動客服備註
        self.assertEqual(out[0][12], "【服務異動】…")         # 異動註記
        self.assertEqual(out[1][1:3], ["② 無相同訂單", "LC8"])
        self.assertEqual(out[1][11], "新客，請填寫")
        self.assertEqual(out[1][9], "")

    def test_section_rows_filtered_by_created_window(self):
        rows = [{"order_id": "A", "created_at": "2026-11-09 09:59:00"},
                {"order_id": "B", "created_at": "2026-11-09 10:00:00", "service_change": ""},
                {"order_id": "C", "created_at": "2026-11-10 09:00:00", "service_change": "付款方式：…",
                 "has_history": False},
                {"order_id": "D", "created_at": ""}]
        out = cms.section_rows_in_window(rows, (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10)))
        self.assertEqual([r["order_id"] for r in out], ["C", "B"])  # 有異動排前面

    def test_append_notice_tab_dedupes_by_order_column_c(self):
        ws = MagicMock(row_count=1000)
        ws.col_values.side_effect = lambda col: {1: ["備註日期時間", "x"], 3: ["訂單編號", "LC1"]}[col]
        w = len(cms.NOTICE_HEADER)
        saved = cms.append_rows(ws, [["x", "①", "LC1"] + [""] * (w - 3), ["", "②", "LC2"] + [""] * (w - 3)],
                                width=w, key_col=cms.NOTICE_KEY_COL)
        self.assertEqual(saved, 1)
        self.assertEqual(ws.update.call_args.kwargs["range_name"], "A3:M3")
        self.assertEqual(ws.update.call_args.kwargs["values"][0][2], "LC2")


class TabHeaderTest(unittest.TestCase):
    def test_existing_tab_without_header_gets_header(self):
        ws = MagicMock(title="客人備註")
        ws.row_values.return_value = []
        sp = MagicMock()
        sp.worksheets.return_value = [ws]
        cms.get_tab("台中", spreadsheet=sp)
        self.assertEqual(ws.update.call_args.kwargs["values"], [cms.HEADER])
        self.assertEqual(ws.update.call_args.kwargs["range_name"], "A1:G1")

    def test_existing_header_untouched(self):
        ws = MagicMock(title="客人備註")
        ws.row_values.return_value = ["備註日期時間", "訂單編號"]
        sp = MagicMock()
        sp.worksheets.return_value = [ws]
        cms.get_tab("台北", spreadsheet=sp)
        ws.update.assert_not_called()


class NameLineCancelTest(unittest.TestCase):
    ROW = """<table><tbody><tr><td><label>LC00220267</label></td>
<td><a href="/member?keyword=0912345678">Amy Chen 陳</a><br>0912345678<br>
<a href="https://chat.line.biz/U1/chat/abc">LINE</a><br>台北市大安區和平東路一段1號<br>2026-11-11 09:00:00<br>
<span>居家清潔</span><ul><li>清掃坪數 21~40</li></ul></td>
<td>2026-11-20 (五)<br>09:00 - 12:00</td><td>付款狀態：{status}</td><td>未處理</td>
<td><a href="/purchase/edit/1">修改</a></td></tr></tbody></table>"""

    def test_name_from_member_link_and_line_url(self):
        from memo_system import memo
        item = memo.parse_purchase_list_page(self.ROW.format(status="已付款"))[0]
        self.assertEqual(item["name"], "Amy Chen 陳")
        self.assertEqual(item["line_url"], "https://chat.line.biz/U1/chat/abc")

    def test_detail_does_not_override_list_name(self):
        from memo_system import memo
        item = {"name": "Amy Chen 陳", "edit_url": "x"}
        with patch.object(memo, "parse_edit_page", return_value={"customer_name": "清掃坪數"}):
            memo.enrich_item_from_detail(None, item)
        self.assertEqual(item["name"], "Amy Chen 陳")

    def test_cancelled_excluded(self):
        rows = cmq.customer_memo_rows([
            {"order_no": "LC1", "customer_memo": "a", "purchase_status": "2", "purchase_status_name": "取消訂單"},
            {"order_no": "LC2", "customer_memo": "b", "purchase_status": "3"},
            {"order_no": "LC3", "customer_memo": "c", "purchase_status": "1", "line_url": "https://chat.line.biz/x"},
        ])
        self.assertEqual([r["訂單號碼"] for r in rows], ["LC3"])
        win = (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10))
        out = cms.section_rows_in_window([
            {"order_id": "A", "created_at": "2026-11-09 12:00:00", "purchase_status_name": "取消訂單"},
            {"order_id": "B", "created_at": "2026-11-09 12:00:00", "purchase_status_name": "已付款"}], win)
        self.assertEqual([r["order_id"] for r in out], ["B"])

    def test_name_cell_line_hyperlink(self):
        self.assertEqual(cms.name_cell("王", "https://chat.line.biz/x"), '=HYPERLINK("https://chat.line.biz/x","王")')
        self.assertEqual(cms.name_cell("王", ""), "王")
        rows = cms.build_sheet_rows([{"訂單號碼": "LC3", "客人姓名": "王", "電話": "0912", "LINE": "https://chat.line.biz/x"}],
                                    "https://b", "t")
        self.assertTrue(rows[0][2].startswith('=HYPERLINK("https://chat.line.biz/x"'))


class CalendarTest(unittest.TestCase):
    def test_event_summary_includes_notice_count(self):
        result = {"台北": {"saved": 1, "rows": [], "notice_saved": 2, "notice_rows": [
            {"order_id": "LC1", "customer_name": "王", "has_history": False, "own_notice": "**VIP**",
             "service_change": "付款方式：備註標示 VIP／本次 ATM（非儲值金）"},
            {"order_id": "LC2", "customer_name": "李", "has_history": False, "service_change": ""}]}}
        ev = cms.build_calendar_event(result, (datetime(2026, 11, 9, 10), datetime(2026, 11, 10, 10)),
                                      datetime(2026, 11, 10, 10, 5))
        self.assertIn("客服備註 2 筆（異動 1）", ev["summary"])
        self.assertIn("② LC1 王：保留原備註＋註記　⚠️ 付款", ev["description"])
        self.assertIn("無異動 1 筆請看工作表", ev["description"])

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
