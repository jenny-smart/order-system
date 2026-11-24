# -*- coding: utf-8 -*-
"""官網評價排程：區間、不滿意判斷、清潔客訴列、評價預約列、插入位置、連結整理。"""
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from shared import rating_schedule as rs

BASE = "https://backend.lemonclean.com.tw"
LINE = "https://chat.line.biz/Uxx/chat/Uyy"


class WindowTest(unittest.TestCase):
    def test_tuesday_window_is_monday_0700_to_today_0700(self):
        self.assertEqual(rs.query_window(date(2026, 11, 10), {}),
                         (datetime(2026, 11, 9, 7), datetime(2026, 11, 10, 7)))

    def test_monday_covers_weekend(self):
        self.assertEqual(rs.query_window(date(2026, 11, 9), {})[0], datetime(2026, 11, 6, 7))

    def test_in_window_uses_full_timestamp(self):
        w = rs.query_window(date(2026, 11, 11), {})
        self.assertTrue(rs.in_window("2026-11-11 00:02:43", w))
        self.assertTrue(rs.in_window("2026-11-10 07:00:00", w))
        self.assertFalse(rs.in_window("2026-11-10 06:59:59", w))
        self.assertFalse(rs.in_window("2026-11-11 07:00:00", w))

    def test_off_day_does_not_run(self):
        self.assertFalse(rs.run("complaint", today=date(2026, 11, 8), calendar={})["due"])


HTML = """<td><ul><li>服務滿意度：尚可</li><li>準時到達：有</li><li>服務態度：良好</li>
<li>服務後檢核：無</li><li>從何得知我們的服務：朋友介紹</li></ul>備註：浴室沒擦乾淨</td>"""


class RatingTest(unittest.TestCase):
    def setUp(self):
        self.rating = {"name": "葉妍伶", "order_no": "LC00219424", "rated_at": "2026-11-11 00:02:43",
                       "staff": "謝孟諭 X 吳奭", **rs.parse_rating_content(BeautifulSoup(HTML, "html.parser").td)}

    def test_parse_items_and_note(self):
        self.assertEqual(self.rating["items"]["服務滿意度"], "尚可")
        self.assertEqual(self.rating["note"], "浴室沒擦乾淨")

    def test_unsatisfied(self):
        self.assertTrue(rs.is_unsatisfied(self.rating))
        self.assertTrue(rs.is_unsatisfied({"items": {"服務滿意度": "不滿意"}}))
        self.assertFalse(rs.is_unsatisfied({"items": {"服務滿意度": "滿意"}}))
        self.assertFalse(rs.is_unsatisfied({"items": {"服務滿意度": "其他"}}))
        self.assertFalse(rs.is_unsatisfied({"items": {}}))

    def test_satisfied_with_negative_note_is_registered(self):
        r = {"items": {"服務滿意度": "滿意", "準時到達": "有"}, "note": "浴室鏡子沒擦，希望下次加強", "order_no": "LC1"}
        self.assertIn("沒擦", rs.complaint_reason(r))
        self.assertTrue(rs.complaint_text(r).startswith("【滿意但意見含「沒擦"))

    def test_efficiency_and_unclean_keywords(self):
        self.assertEqual(rs.negative_keywords("效率不太好，廚房也不乾淨"), ["不乾淨", "效率"])
        self.assertEqual(rs.negative_keywords("專員很有效率，效率高"), [])

    def test_satisfied_with_negative_item_is_registered(self):
        r = {"items": {"服務滿意度": "滿意", "準時到達": "無"}, "note": ""}
        self.assertEqual(rs.complaint_reason(r), "滿意但準時到達：無")

    def test_satisfied_and_positive_is_not_registered(self):
        r = {"items": {"服務滿意度": "滿意", "準時到達": "有", "服務態度": "良好", "從何得知我們的服務": "朋友介紹"},
             "note": "非常棒，很感謝"}
        self.assertEqual(rs.complaint_reason(r), "")

    def test_complaint_row(self):
        row = rs.build_complaint_row(self.rating, {"phone": "0966671212", "service_date": "2026/11/10",
                                                  "line_url": LINE}, BASE)
        self.assertEqual(len(row), rs.COMPLAINT_WIDTH)
        self.assertEqual(row[:6], ["官網評價", "", "2026-11-10", 11, "2026-11-11", "三"])
        self.assertEqual(row[6], f'=HYPERLINK("{LINE}","葉妍伶")')
        self.assertTrue(row[7].startswith(f'=HYPERLINK("{BASE}/purchase?'))
        self.assertIn("phone=0966671212", row[7])
        self.assertIn("服務滿意度：尚可", row[9])
        self.assertIn("服務後檢核：無", row[9])
        self.assertNotIn("準時到達", row[9])
        self.assertNotIn("朋友介紹", row[9])
        self.assertIn("備註：浴室沒擦乾淨", row[9])
        self.assertIn("訂單：LC00219424", row[9])
        self.assertEqual(row[12], "謝孟諭 X 吳奭")

    def test_existing_keys_from_content_and_name_date(self):
        values = [["h"], ["h"], ["官網評價", "", "", "", "2026-11-11", "", "葉妍伶", "", "", "…訂單：LC00219424"]]
        orders_seen, name_dates = rs.existing_complaint_keys(values)
        self.assertIn("LC00219424", orders_seen)
        self.assertIn(("2026-11-11", "葉妍伶"), name_dates)

    def test_complaint_insert_after_last_data_not_dropdown_rows(self):
        values = [["客服"], ["客訴來源"], ["line", "B", "2026-10-28", "10", "2026-10-29", "四", "楊雅琪"], [],
                  ["line", "A.清潔速度", "", "", "", "", "", "", "OLD"], ["官網評價", "B.清潔細膩度"]]
        self.assertEqual(rs.last_row_by_columns(values, (3, 5, 7)), 3)


class WriteComplaintsTest(unittest.TestCase):
    def test_write_inserts_after_last_complaint(self):
        ws = MagicMock()
        values = [["客服"], ["客訴來源"], ["line", "", "2026-10-28", "", "2026-10-29", "", "楊雅琪"], [],
                  ["line", "A.清潔速度"]]
        n = rs.write_complaints({"rows": [["官網評價"]], "values": values, "ws": ws})
        self.assertEqual(n, 1)
        self.assertEqual(ws.insert_rows.call_args.kwargs["row"], 4)


class BookingTest(unittest.TestCase):
    r = {"評價日期": "2026-11-10", "評價時間": "2026-11-10 15:05:45", "姓名": "莊欣瑜", "電話": "0988680803",
         "地址": "台北市", "預約下次日期": "2026-12-05", "預約下次時間": "09:00-12:00",
         "服務日期及時間": "2026-11-08 (日) 09:00 - 12:00", "服務人數": "2人", "訂單編號": "LC00217413", "LINE": LINE}

    def test_taipei_row_follows_header_b_to_k(self):
        row = rs.build_booking_row("台北", self.r, BASE)
        self.assertEqual(len(row), 11)
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], "2026-11-10")
        self.assertEqual(row[2], f'=HYPERLINK("{LINE}","莊欣瑜")')
        self.assertIn("phone=0988680803", row[3])
        self.assertEqual(row[5:], ["2026-12-05", "09:00-12:00", "2026-11-08 (日) 09:00 - 12:00", "2人",
                                   "LC00217413", LINE])

    def test_taichung_row_keeps_its_layout(self):
        row = rs.build_booking_row("台中", self.r, BASE)
        self.assertEqual(row[0], f'=HYPERLINK("{LINE}","莊欣瑜")')
        self.assertEqual(row[1:4], ["台北市", "2026-12-05 09:00-12:00", ""])
        self.assertEqual(row[8], "LC00217413")

    def test_main_list_end_stops_at_blank_gap(self):
        values = [["", "評價日期", "姓名"], ["LC1", "", "甲"], ["LC2", "", "乙"]] + [[]] * 10 + \
                 [["", "", "己開放無時段"], ["", "", "丙"]]
        self.assertEqual(rs.main_list_end(values, 2), 3)

    def test_main_list_end_taichung_no_header(self):
        values = [["甲"], ["乙"], [], [], [], [], [], ["周良保"]]
        self.assertEqual(rs.main_list_end(values, 1), 2)

    def test_insert_uses_inherit_and_user_entered(self):
        ws = MagicMock()
        rs.insert_after(ws, 203, [["x"]])
        kwargs = ws.insert_rows.call_args.kwargs
        self.assertEqual(kwargs["row"], 204)
        self.assertTrue(kwargs["inherit_from_before"])
        self.assertEqual(kwargs["value_input_option"], "USER_ENTERED")


class SheetToolTest(unittest.TestCase):
    def test_col_index_and_key(self):
        self.assertEqual(rs.col_index("g"), 7)
        self.assertEqual(rs.col_index("AB"), 28)
        with self.assertRaises(ValueError):
            rs.col_index("7")
        key = "1bNcJuFuP--jdpNo2zJKOpvuq-5rSHW3LgGE8HEepf44"
        self.assertEqual(rs.spreadsheet_key(f"https://docs.google.com/spreadsheets/d/{key}/edit#gid=1"), key)
        self.assertEqual(rs.spreadsheet_key(key), key)

    def test_plan_sheet_links_any_sheet(self):
        ws = MagicMock(row_count=100)
        ws.get.return_value = [["姓名", "電話"], ["王", "0911222333"], ["", ""]]
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200, text=f'<a href="{LINE}">LINE</a>')
        ups = rs.plan_sheet_links(ws, session, BASE, 1, 2, 2)
        ranges = {u["range"]: u["values"][0][0] for u in ups}
        self.assertEqual(ranges["A2"], f'=HYPERLINK("{LINE}","王")')
        self.assertIn("phone=0911222333", ranges["B2"])


class RelinkTest(unittest.TestCase):
    def test_phone_and_name_links_skip_existing_formulas(self):
        formulas = [["客服"], ["客訴來源"],
                    ["官網評價", "", "", "", "", "", "陳立康", 965125935],
                    ["line", "", "", "", "", "", '=HYPERLINK("x","已連")', '=HYPERLINK("y","0921")'],
                    ["line", "", "", "", "", "", "無電話", ""]]
        lookup = MagicMock(return_value=LINE)
        ups = rs.relink_updates(formulas, 7, 8, 3, BASE, lookup)
        ranges = {u["range"]: u["values"][0][0] for u in ups}
        self.assertIn("phone=0965125935", ranges["H3"])
        self.assertEqual(ranges["G3"], f'=HYPERLINK("{LINE}","陳立康")')
        self.assertNotIn("G4", ranges)
        self.assertNotIn("H4", ranges)
        self.assertNotIn("G5", ranges)
        lookup.assert_called_once_with("0965125935")

    def test_booking_uses_line_column_without_lookup(self):
        formulas = [["", "評價日期", "姓名"], ["LC1", "", "甲", "0911222333", "", "", "", LINE]]
        lookup = MagicMock(return_value="")
        ups = rs.relink_updates(formulas, 3, 4, 2, BASE, lookup, line_col=8)
        ranges = {u["range"]: u["values"][0][0] for u in ups}
        self.assertEqual(ranges["C2"], f'=HYPERLINK("{LINE}","甲")')
        lookup.assert_not_called()


class AddressFillTest(unittest.TestCase):
    ADDR = "新北市汐止區民族二街84巷46號一樓"

    def test_blank_name_phone_filled_from_address(self):
        formulas = [["", "評價日期", "姓名", "電話", "地址"],
                    ["", "", "", "", self.ADDR],
                    ["", "", "已填", "", "台北市內湖區南京東路六段389號7樓"]]
        lookup = MagicMock(return_value="")

        def by_addr(addr):
            if addr == self.ADDR:
                return [{"name": "陳淑惠", "phone": "0939727251", "line_url": LINE, "order_no": "LC1"}]
            return [{"name": "甲", "phone": "0911000000", "line_url": "", "order_no": "LC2"},
                    {"name": "乙", "phone": "0922000000", "line_url": "", "order_no": "LC3"}]

        skipped = []
        ups = rs.relink_updates(formulas, 3, 4, 2, BASE, lookup, address_col=5,
                                address_lookup=by_addr, skipped=skipped)
        ranges = {u["range"]: u for u in ups}
        self.assertEqual(ranges["C2"]["values"][0][0], f'=HYPERLINK("{LINE}","陳淑惠")')
        self.assertIn("phone=0939727251", ranges["D2"]["values"][0][0])
        self.assertEqual(ranges["C2"]["source"], "地址查詢")
        self.assertNotIn("C3", ranges)  # 多位客人：不回填、既有姓名不動
        self.assertNotIn("D3", ranges)
        self.assertEqual(len(skipped), 1)
        self.assertIn("2 位客人", skipped[0]["原因"])
        lookup.assert_not_called()  # LINE 已從地址查詢的訂單取得

    def test_existing_values_not_overwritten_and_no_lookup_when_complete(self):
        formulas = [["王", "0911222333", self.ADDR]]
        by_addr = MagicMock(return_value=[])
        ups = rs.relink_updates(formulas, 1, 2, 1, BASE, MagicMock(return_value=""), address_col=3,
                                address_lookup=by_addr)
        by_addr.assert_not_called()
        self.assertEqual({u["range"] for u in ups}, {"B1"})

    def test_pick_customers_by_address_from_backend_html(self):
        html = f"""<table><tbody><tr><td>LC00123</td><td>代客預訂：Jenny
            <a href="/member?keyword=0939727251">陳淑惠</a><br>0939727251<br>jo99@foxmail.com<br>
            <a href="{LINE}">LINE</a><br>新北市汐止區民族二街84巷46號一樓<br>已付款</td><td>2026-01-26</td></tr>
            <tr><td>LC00124</td><td><a href="/member?keyword=0911000000">別人</a><br>0911000000<br>
            新北市汐止區民族二街84巷46號三樓</td><td>2026-01-20</td></tr></tbody></table>"""
        from memo_system import memo

        people = rs.pick_customers_by_address(memo.parse_purchase_list_page(html), "新北市汐止區民族二街84巷46號一樓 ")
        self.assertEqual(people, [{"name": "陳淑惠", "phone": "0939727251", "line_url": LINE, "order_no": "LC00123"}])
        self.assertEqual(rs.address_key("臺北市 內湖區１號"), "台北市內湖區1號")

    def test_apply_updates_strips_extra_keys(self):
        ws = MagicMock()
        rs.apply_updates(ws, [{"range": "A1", "values": [["x"]], "kind": "name_link", "source": "地址查詢"}])
        self.assertEqual(ws.batch_update.call_args[0][0], [{"range": "A1", "values": [["x"]]}])


class AppendBookingsTest(unittest.TestCase):
    def test_writes_name_phone_address_with_links_and_skips_existing(self):
        from unittest.mock import patch

        ws = MagicMock(row_count=50, id=9)
        ws.get.return_value = [["", "評價日期", "姓名"], ["", "", "舊", "", "", "", "", "", "", "LC0001"]]
        sheet = MagicMock(id="SID")
        r = {"評價日期": "2026-11-20", "姓名": "陳淑惠", "電話": "0939727251", "地址": "新北市汐止區民族二街84巷46號一樓",
             "預約下次日期": "2026-12-01", "預約下次時間": "09:00-12:00", "服務日期及時間": "x", "服務人數": "2人",
             "訂單編號": "LC0002", "LINE": LINE, "評價時間": "2026-11-20 10:00:00"}
        dup = dict(r, 訂單編號="LC0001")
        with patch.object(rs, "get_tab", return_value=(sheet, ws)):
            out = rs.append_bookings("台北", [r, dup], BASE)
        rows = ws.insert_rows.call_args[0][0]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], f'=HYPERLINK("{LINE}","陳淑惠")')
        self.assertIn("phone=0939727251", rows[0][3])
        self.assertEqual(rows[0][4], "新北市汐止區民族二街84巷46號一樓")
        self.assertEqual(out["saved"], 1)
        self.assertEqual(out["existing"], ["LC0001"])


if __name__ == "__main__":
    unittest.main()


def test_result_lines_one_line_per_region():
    from shared import rating_schedule as rs
    result = {"台北": {"found": 2, "saved": 1, "error": ""}, "台中": {"found": 0, "saved": 0, "error": ""}}
    assert rs.result_lines("complaint", result) == ["台北／清潔客訴：新增 1 筆（符合 2 筆，已登記略過 1 筆）",
                                                    "台中／清潔客訴：沒有資料"]
    assert rs.result_lines("booking", {"台北": {"found": 0, "saved": 0, "error": "X: y"}}) == ["台北／評價預約：錯誤 X: y"]
