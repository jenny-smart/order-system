# -*- coding: utf-8 -*-
"""排班管理「檸檬人統計」：非保留單訂單裡的檸檬人，依每日上午／下午／全天統計。"""
import unittest
from unittest.mock import MagicMock, patch

from datetime import datetime

from memo_system import shift


def setUpModule():
    # 統計只算明天以後：測試固定「今天」＝2026-11-20
    global _today_patch
    _today_patch = patch.object(shift.memo, "today_tw", return_value=datetime(2026, 11, 20))
    _today_patch.start()


def tearDownModule():
    _today_patch.stop()

HEADER = ("<tr><td></td><td>08:30-12:30</td><td>09:00-12:00</td><td>09:00-18:00</td>"
          "<td>14:00-18:00</td><td>19:00-21:00</td></tr>")
UNASSIGNED = '<p style="background:#616161"><span>未配班 2 人</span><br><span>4檸檬人70</span><br><span>4檸檬人40</span></p>'
HTML = (
    '<input id="date" value="2027-02-01"><table>' + HEADER +
    "<tr><td>02-04<br>(四)</td>"
    "<td><span>11-02</span><br>♂♀ 李先生 V<br>48汪才閔4 X<br>4檸檬人50<br>" + UNASSIGNED + "</td>"
    "<td>11-02<br>趙妍婷 V<br>33黃柏維2 X<br>8張志豪3"
    "<br>11-02<br>檸檬保留 V<br>3偏翮2 X<br>4檸檬人30<br>" + UNASSIGNED + "</td>"
    "<td>11-20<br>林秀娟<br>4檸檬人20<br>4檸檬人60</td>"
    "<td>11-02<br>王櫻娟 V<br>8吳爽1 X<br>11-02<br>莊知霖 V<br>4呂筠蓁2 X<br>4檸檬人10</td>"
    "<td></td></tr>" + HEADER +
    "<tr><td>02-05<br>(五)</td><td>未配班 1 人<br>4檸檬人90</td><td></td><td></td><td></td><td></td></tr>"
    "</table>"
)


class OrderLemonCountTest(unittest.TestCase):
    def test_period_group(self):
        self.assertEqual(shift.period_group("08:30-12:30"), "上午")
        self.assertEqual(shift.period_group("09:00-11:00"), "上午")
        self.assertEqual(shift.period_group("09:00-16:00"), "全天")
        self.assertEqual(shift.period_group("14:00-17:00"), "下午")
        self.assertEqual(shift.period_group("19:00-21:00"), "晚上")

    def test_excludes_reserve_orders_and_unassigned_box(self):
        entries = shift.parse_order_lemon_entries(HTML, "2027-02-01")
        got = {(e["date"], e["group"], e["name"], e["customer"]) for e in entries}
        self.assertEqual(got, {
            ("2027-02-04", "上午", "檸檬人5", "李先生"),
            ("2027-02-04", "全天", "檸檬人2", "林秀娟"),
            ("2027-02-04", "全天", "檸檬人6", "林秀娟"),
            ("2027-02-04", "下午", "檸檬人1", "莊知霖"),
        })

    def test_count_range_per_day(self):
        resp = MagicMock(text=HTML)
        with patch.object(shift.memo, "session_get", return_value=resp):
            result = shift.count_order_lemons_range(None, "2027-02-04", "2027-02-05")
        d4, d5 = result["days"]
        self.assertEqual((d4["上午"], d4["下午"], d4["全天"], d4["合計"]), (1, 1, 2, 4))
        self.assertEqual((d5["上午"], d5["下午"], d5["全天"], d5["合計"]), (0, 0, 0, 0))
        self.assertIn("莊知霖：檸檬人1", d4["明細"])


if __name__ == "__main__":
    unittest.main()


class FormatProgressTest(unittest.TestCase):
    def test_format_matches_line_text(self):
        days = [
            {"日期": "2027-02-16", "上午": 0, "下午": 0, "全天": 0, "晚上": 0},
            {"日期": "2027-02-17", "上午": 1, "下午": 1, "全天": 0, "晚上": 0},
            {"日期": "2027-02-04", "上午": 0, "下午": 1, "全天": 0, "晚上": 0},
        ]
        self.assertEqual(shift.format_lemon_progress(days),
                         "檸檬人待換專員進度：\n02/17-上午-1，下午-1\n02/04-下午-1")


MERGED_SCHEDULE = (
    '<input id="date" value="2026-11-23"><table>'
    "<tr><td></td><td>08:30-12:30</td><td>09:00-12:00</td></tr>"
    "<tr><td>11-23<br>(一)</td>"
    "<td>11-17<br>王上惠<br>4檸檬人10 X<br>4檸檬人20"
    "<br>11-08<br>高鈺欣 N<br>48周延澤2 X<br>48黃麗玲2 D"
    "<br>11-19<br>王上惠<br>48吳承軒5 X<br>463李佳芸1 X<br>4陳蕙琪1</td>"
    "<td>10-04<br>蘇玉珮 V<br>4檸檬人30</td></tr></table>"
)


def purchase_page(rows):
    trs = "".join(
        f'<tr><td>LC00{i}</td><td><a href="/member?keyword=x">{name}</a>'
        + (f'<label alt="{note}" title="{note}">客服備註</label>' if note else "")
        + "</td></tr>"
        for i, (name, note) in enumerate(rows)
    )
    return f"<table><tbody>{trs}</tbody></table>"


class MergedOrderTest(unittest.TestCase):
    def run_count(self, purchase_rows):
        def fake_get(_session, url, params=None):
            if url.endswith("/schedule"):
                return MagicMock(text=MERGED_SCHEDULE)
            return MagicMock(text=purchase_page(purchase_rows) if params.get("page") == "1" else "")
        with patch.object(shift.memo, "session_get", side_effect=fake_get):
            return shift.count_order_lemons_range(None, "2026-11-23", "2026-11-23")

    def test_same_customer_multi_orders_with_keep_note_excluded(self):
        result = self.run_count([("王上惠", "**2-4**檸檬人勿動"), ("王上惠", ""), ("蘇玉珮", "")])
        day = result["days"][0]
        self.assertEqual((day["上午"], day["合計"]), (1, 1))  # 只剩蘇玉珮的檸檬人3
        self.assertEqual({e["name"] for e in result["excluded"]}, {"檸檬人1", "檸檬人2"})

    def test_multi_orders_without_keep_note_still_counted(self):
        day = self.run_count([("王上惠", "**2-4**"), ("王上惠", "")])["days"][0]
        self.assertEqual(day["上午"], 3)

    def test_single_order_with_keep_note_still_counted(self):
        # 蘇玉珮當天只有一張單：就算備註有勿動也照算（只排除合併訂單）
        day = self.run_count([("王上惠", ""), ("蘇玉珮", "檸檬人勿動")])["days"][0]
        self.assertEqual(day["上午"], 3)


class PurchaseJsonNoticeTest(unittest.TestCase):
    """訂單管理頁是 Vue：客服備註在內嵌 purchaseList JSON，不在表格。"""

    def test_merged_order_excluded_via_json(self):
        import json
        items = [
            {"order_no": "LC1", "name": "王上惠", "notice": "**2-4**檸檬人勿動", "member": {"name": "王上惠"}},
            {"order_no": "LC2", "name": "王上惠", "notice": "", "member": {"name": "王上惠"}},
            {"order_no": "LC3", "name": "蘇玉珮", "notice": "", "member": {"name": "蘇玉珮", "memo": "檸檬人勿動"}},
        ]
        page = "<script>new Vue({data:{purchaseList: " + json.dumps({"data": items}, ensure_ascii=False) + "}})</script>"

        def fake_get(_session, url, params=None):
            if url.endswith("/schedule"):
                return MagicMock(text=MERGED_SCHEDULE)
            return MagicMock(text=page)

        with patch.object(shift.memo, "session_get", side_effect=fake_get):
            result = shift.count_order_lemons_range(None, "2026-11-23", "2026-11-23")
        self.assertEqual(result["days"][0]["上午"], 1)
        self.assertEqual({e["name"] for e in result["excluded"]}, {"檸檬人1", "檸檬人2"})


class ReserveAttributionTest(unittest.TestCase):
    def test_staff_without_area_code_stays_in_reserve_order(self):
        # 檸檬保留單的專員「陳靜怡3」前面沒有區域編號，後面的檸檬人仍屬於保留單
        html = ('<input id="date" value="2027-01-25"><table>'
                "<tr><td></td><td>14:00-17:00</td></tr>"
                "<tr><td>01-29<br>(五)</td>"
                "<td>11-02 11-05<br>檸檬保留 V<br>陳靜怡3 X<br>4檸檬人10"
                "<br>11-03<br>林小明<br>8張志豪3 X<br>4檸檬人20</td></tr></table>")
        got = [(e["customer"], e["name"]) for e in shift.parse_order_lemon_entries(html, "2027-01-25")]
        self.assertEqual(got, [("林小明", "檸檬人2")])

    def test_only_dates_after_today(self):
        resp = MagicMock(text=MERGED_SCHEDULE)  # 11-23 的班表
        with patch.object(shift.memo, "session_get", return_value=resp):
            result = shift.count_order_lemons_range(None, "2026-11-01", "2026-11-23")
        self.assertEqual(result["days"][0]["日期"], "2026-11-21")
        with patch.object(shift.memo, "today_tw", return_value=datetime(2026, 11, 25)):
            self.assertEqual(shift.count_order_lemons_range(None, "2026-11-01", "2026-11-23")["days"], [])
