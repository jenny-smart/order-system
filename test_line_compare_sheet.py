# -*- coding: utf-8 -*-
"""代客預訂 LINE 比對：卡片解析、狀態／代客篩選、貼表格式、重複略過。"""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared import line_compare_sheet as lc

PRICING = {"enabled": False, "periods": {}}  # 未啟用：平日 600／週末 700


def card(no, name="廖彗妤", phone="0953655686", proxy="瑋萱", total="4,800", status="已付款",
         date_text="2026-11-20 (五)", period="09:00 - 13:00", line=True, staff=0):
    proxy_div = f"<div>代客預訂：{proxy}</div>" if proxy is not None else ""
    link = f'<a href="https://chat.line.biz/Uoa/chat/U{no}">LINE</a>' if line else ""
    staff_links = "".join(f'<a href="/schedule/edit/{i}">專員{i}</a>' for i in range(staff))
    return f"""<tr><td>{no}</td><td>{proxy_div}<div>{name}</div><div>{phone}</div><div>a@b.tw</div>
{link}<div>台北市大安區復興南路一段1號</div><div>居家清潔</div></td>
<td><div>{date_text}</div><div>{period}</div>{staff_links}</td>
<td><div>總金額：{total}</div><div>付款方式：信用卡</div><div>付款狀態：{status}</div>
<a href="/purchase/edit/9{no[-3:]}">修改</a></td></tr>"""


def page(*cards):
    return "<table><tbody>" + "".join(cards) + "</tbody></table>"


class CardTest(unittest.TestCase):
    def test_proxy_booker_and_name(self):
        text = "LC002201831\n代客預訂：瑋萱\n廖彗妤\n0953655686"
        self.assertEqual(lc.proxy_booker(text), "瑋萱")
        self.assertEqual(lc.customer_name(text), "廖彗妤")
        self.assertEqual(lc.proxy_booker("LC1\n王小明\n0912345678"), "")
        self.assertFalse(lc.is_proxy("LC1\n王小明"))
        self.assertTrue(lc.is_proxy("代客預約: Jenny"))

    def test_name_keeps_non_chinese_and_long_names(self):
        self.assertEqual(lc.customer_name("代客預訂：Jenny\nMary Chen\n0912345678"), "Mary Chen")
        self.assertEqual(lc.customer_name("代客預訂：Jenny\n0912345678", "備援"), "備援")

    def test_list_page_has_line_url_period_and_amount(self):
        items = lc.parse_list_html(page(card("LC002201831")))
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["line_url"], "https://chat.line.biz/Uoa/chat/ULC002201831")
        self.assertEqual((item["service_date"], item["period"], item["phone"]),
                         ("2026/11/20", "09:00-13:00", "0953655686"))
        self.assertEqual(lc.amount_text(item, PRICING), "4,800（2人）")  # 4800 ÷ (4 小時 × 600)

    def test_dev_order_prefix_is_parsed(self):
        items = lc.parse_list_html(page(card("TT00217785"), card("LC00000009")))
        self.assertEqual([x["order_no"] for x in items], ["TT00217785", "LC00000009"])
        self.assertEqual(items[0]["line_url"], "https://chat.line.biz/Uoa/chat/UTT00217785")
        self.assertEqual((items[0]["service_date"], items[0]["phone"]), ("2026/11/20", "0953655686"))

    def test_persons_weekend_price_fare_and_fallbacks(self):
        weekend = lc.parse_list_html(page(card("LC1", total="5,600", date_text="2026-11-21 (六)")))[0]
        self.assertEqual(lc.amount_text(weekend, PRICING), "5,600（2人）")  # 週末 700
        with_fare = dict(weekend, row_text=weekend["row_text"] + "\n車馬費：200\n", )
        with_fare["row_text"] = with_fare["row_text"].replace("總金額：5,600", "總金額：5,800")
        self.assertEqual(lc.amount_text(with_fare, PRICING), "5,800（2人）")
        odd = lc.parse_list_html(page(card("LC2", total="1,234")))[0]
        self.assertEqual(lc.amount_text(odd, PRICING), "1,234")  # 推不出來只寫金額
        stored = lc.parse_list_html(page(card("LC3", total="0", staff=3)))[0]
        self.assertEqual(lc.amount_text(stored, PRICING), "0（3人）")  # 金額 0 用已配班人數


class FetchTest(unittest.TestCase):
    def _session_pages(self, by_status):
        def fake_get(session, url, params=None, **kw):
            html = by_status.get(params["purchase_status"], "") if params["page"] == "1" else page()
            return SimpleNamespace(text=html, raise_for_status=lambda: None)
        return fake_get

    def test_only_proxy_orders_with_queried_status(self):
        pages = {
            "1": page(card("LC00000002"), card("LC00000001", proxy=None)),
            "0": page(card("LC00000003", name="王小明", proxy="Jenny", status="待付款", line=False)),
        }
        logs = []
        with patch("memo_system.memo.session_get", side_effect=self._session_pages(pages)), \
                patch("service_pricing.load_config", return_value=PRICING):
            rows = lc.fetch_proxy_orders(MagicMock(), date(2026, 11, 12), date(2026, 11, 12), log=logs.append)
        self.assertEqual([r["訂單編號"] for r in rows], ["LC00000002", "LC00000003"])
        self.assertEqual(rows[0]["訂購日期"], "2026/11/12")
        self.assertEqual((rows[0]["付款狀態"], rows[0]["代客預約人名"]), ("已付款", "瑋萱"))
        self.assertEqual((rows[1]["付款狀態"], rows[1]["訂購人"], rows[1]["LINE連結"]), ("待付款", "王小明", ""))
        self.assertIn("代客預訂 2 筆", logs[0])

    def test_each_day_is_queried_and_range_is_limited(self):
        seen = []

        def fake_get(session, url, params=None, **kw):
            seen.append((params["date_s"], params["date_e"], params["purchase_status"]))
            return SimpleNamespace(text=page(), raise_for_status=lambda: None)

        with patch("memo_system.memo.session_get", side_effect=fake_get):
            lc.fetch_proxy_orders(MagicMock(), date(2026, 11, 11), date(2026, 11, 12))
        self.assertEqual(seen, [("2026-11-11", "2026-11-11", "1"), ("2026-11-11", "2026-11-11", "0"),
                                ("2026-11-12", "2026-11-12", "1"), ("2026-11-12", "2026-11-12", "0")])
        with self.assertRaises(ValueError):
            lc.fetch_proxy_orders(MagicMock(), date(2026, 11, 12), date(2026, 11, 11))
        with self.assertRaises(ValueError):
            lc.fetch_proxy_orders(MagicMock(), date(2026, 1, 1), date(2026, 3, 1))


class SheetTest(unittest.TestCase):
    ROW = {"訂購日期": "2026/11/12", "訂單編號": "LC002201831", "訂購人": "廖彗妤",
           "LINE連結": "https://chat.line.biz/Uoa/chat/U1", "電話號碼": "0953655686", "服務日期": "2026/11/20",
           "服務時段": "09:00-13:00", "付款狀態": "已付款", "訂單金額（推算人數）": "4,800（2人）", "代客預約人名": "瑋萱"}

    def test_header_and_links(self):
        self.assertEqual(lc.HEADER, ["訂購日期", "訂單編號", "訂購人", "電話號碼", "服務日期", "服務時段", "付款狀態",
                                     "訂單金額（推算人數）", "比對對話結果", "代客預約人名"])
        row = lc.build_sheet_rows([self.ROW], "https://backend.lemonclean.com.tw")[0]
        self.assertEqual(len(row), len(lc.HEADER))
        self.assertEqual(row[:2], ["2026/11/12", "LC002201831"])
        self.assertEqual(row[2], '=HYPERLINK("https://chat.line.biz/Uoa/chat/U1","廖彗妤")')
        self.assertTrue(row[3].startswith('=HYPERLINK("https://backend.lemonclean.com.tw/purchase?'))
        self.assertIn("phone=0953655686", row[3])
        self.assertTrue(row[3].endswith(',"0953655686")'))
        self.assertEqual(row[4:], ["2026/11/20", "09:00-13:00", "已付款", "4,800（2人）", "", "瑋萱"])

    def test_name_without_line_stays_text(self):
        row = lc.build_sheet_rows([dict(self.ROW, **{"LINE連結": ""})], "https://b")[0]
        self.assertEqual(row[2], "廖彗妤")

    def test_plan_skips_orders_already_on_tab_and_write_appends(self):
        ws = MagicMock(row_count=1000, id=7)
        ws.col_values.return_value = ["訂單編號", "LC002201831"]
        other = dict(self.ROW, **{"訂單編號": "LC002201900"})
        with patch.object(lc, "fetch_proxy_orders", return_value=[self.ROW, other]), \
                patch.object(lc, "get_tab", return_value=(SimpleNamespace(id="SID"), ws)):
            result = lc.plan("台北", MagicMock(), "https://b", date(2026, 11, 12), date(2026, 11, 12))
        self.assertEqual([r["狀態"] for r in result["preview"]], ["已在工作表", "新增"])
        self.assertEqual([r["訂單編號"] for r in result["new_rows"]], ["LC002201900"])
        self.assertEqual(result["sheet_url"], "https://docs.google.com/spreadsheets/d/SID/edit#gid=7")
        self.assertEqual(lc.write(result), 1)
        kwargs = ws.update.call_args.kwargs
        self.assertEqual(kwargs["range_name"], "A3:J3")
        self.assertEqual(kwargs["value_input_option"], "USER_ENTERED")

    def test_existing_tab_title_matched_case_insensitively(self):
        sheet = MagicMock()
        sheet.worksheets.return_value = [SimpleNamespace(title="客人備註"), SimpleNamespace(title="LINE比對")]
        with patch("shared.customer_memo_schedule.open_spreadsheet", return_value=sheet), \
                patch("shared.customer_memo_schedule.get_tab", return_value=(sheet, "ws")) as get_tab:
            lc.get_tab("台北")
        self.assertEqual(get_tab.call_args.args[1], "LINE比對")


if __name__ == "__main__":
    unittest.main()
