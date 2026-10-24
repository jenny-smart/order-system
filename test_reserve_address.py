import unittest
from unittest.mock import patch

import function.reserve_address as ra

HTML = """<table><tr><td>檸檬保留</td><td>0939592628</td><td>
台北轉換(3,229,150)LC00017658[2,920,400]2018-09-13<br>
台北市大安區信義路四段210號4樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
台中市北區館前路19號4樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
新北市板橋區文化路一段270巷4號2樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
<a>新北市板橋區文化路一段270巷4號2樓 (0) [備註]</a>
</td></tr><tr><td>別人</td><td>0912000000</td><td>台北市某路1號<a>[備註]</a><a><i class="fa fa-trash-o"></i></a></td></tr></table>"""


class ReserveAddressTest(unittest.TestCase):
    def test_parse_only_this_member_trash_addresses(self):
        self.assertEqual(ra.parse_member_addresses(HTML, "0939592628"), [
            "台北市大安區信義路四段210號4樓", "台中市北區館前路19號4樓", "新北市板橋區文化路一段270巷4號2樓"])

    def test_plan_keeps_fixed_and_skips_active_or_incomplete(self):
        addresses = ["台北市大安區信義路四段210號4樓", "臺中市北區館前路19號4樓", "新北市A路1號", "新北市B路2號"]
        plan = ra.plan_cleanup(addresses, {ra.address_key("新北市B路2號"): 2}, True)
        self.assertEqual([p["處理"] for p in plan], ["保留", "保留", ra.DELETE, "跳過"])
        self.assertIn("2 張", plan[3]["原因"])
        incomplete = ra.plan_cleanup(["新北市A路1號"], {}, False)
        self.assertEqual(incomplete[0]["處理"], "跳過")

    def test_delete_never_touches_fixed_addresses(self):
        result = ra.delete_member_addresses("dev", "e", "p", list(ra.KEEP_ADDRESSES))
        self.assertEqual([r["結果"] for r in result], ["未刪除", "未刪除"])

    def test_cleanup_after_cancel_deletes_only_unused_cancelled_addresses(self):
        cancelled = [
            {"ok": True, "memo_keyword": "代客保留：王小明", "address": "新北市A路1號"},
            {"ok": True, "memo_keyword": "代客保留：李小華", "address": "新北市B路2號"},
            {"ok": False, "memo_keyword": "代客保留：陳大文", "address": "新北市C路3號"},
            {"ok": True, "address": "台北市大安區信義路四段210號4樓"},  # 系統保留單不處理
        ]
        member = ["台北市大安區信義路四段210號4樓", "新北市A路1號", "新北市B路2號", "新北市C路3號"]
        with patch.object(ra, "list_member_addresses", return_value=member), \
                patch.object(ra, "active_order_counts", return_value=({ra.address_key("新北市B路2號"): 1}, True)), \
                patch.object(ra, "delete_member_addresses",
                             side_effect=lambda e, m, p, addrs, phone: [{"地址": a, "結果": "已刪除", "說明": ""} for a in addrs]) as deleter:
            result = ra.cleanup_after_cancel("dev", "e", "p", cancelled)
        self.assertEqual(deleter.call_args.args[3], ["新北市A路1號"])
        self.assertEqual({r["地址"]: r["結果"] for r in result}, {"新北市A路1號": "已刪除", "新北市B路2號": "未刪除"})

    def test_no_proxy_rows_means_no_lookup(self):
        with patch.object(ra, "list_member_addresses") as lister:
            self.assertEqual(ra.cleanup_after_cancel("dev", "e", "p", [{"ok": True, "address": "x"}]), [])
        lister.assert_not_called()

    def _counts(self, pages):
        """pages：每頁的訂單卡片 (服務日期, 付款狀態, 地址)。"""
        from types import SimpleNamespace
        calls = []

        def get(url, params=None, **kw):
            calls.append(params)
            page = int(params["page"])
            return SimpleNamespace(status_code=200, text=str(page))

        def cards(text):
            return [{"lines": [], "info": info} for info in (pages[int(text) - 1] if int(text) <= len(pages) else [])]

        def item(block):
            date, status, address = block["info"]
            return {"phone": "0939592628", "service_date": date, "payment_status": status, "address": address}

        session = SimpleNamespace(get=get)
        with patch.object(ra.co, "_new_logged_in_session", return_value=(session, "https://x")), \
                patch.object(ra.orders, "extract_order_cards_from_purchase_html", side_effect=cards), \
                patch.object(ra.co, "_order_from_block", side_effect=item), \
                patch.object(ra, "_today", return_value="2026-12-01"):
            return ra.active_order_counts("dev", "e", "p"), calls

    def test_active_counts_use_phone_only_and_filter_locally(self):
        future = [("2026-12-10", "已付款", "新北市A路1號")] * 18 + [
            ("2026-12-05", "取消訂單", "新北市B路2號"), ("2026-11-30", "已付款", "新北市C路3號")]
        (counts, complete), calls = self._counts([future, [("2026-11-01", "已付款", "新北市D路4號")] * 20])
        self.assertTrue(complete)
        self.assertEqual(counts, {ra.address_key("新北市A路1號"): 18})
        self.assertEqual(calls[0]["clean_date_s"], "")  # 不送日期篩選
        self.assertEqual(calls[0]["orderBy"], "date_clean:desc")

    def test_no_orders_at_all_is_not_treated_as_complete(self):
        (counts, complete), _ = self._counts([[]])
        self.assertEqual((counts, complete), ({}, False))
        self.assertTrue(all(p["處理"] == "跳過" for p in ra.plan_cleanup(["新北市A路1號"], counts, complete)))


if __name__ == "__main__":
    unittest.main()


class CancelPageCleanupTest(unittest.TestCase):
    def test_only_reserve_account_orders_trigger_cleanup(self):
        import function.cancel_order as co
        from contextlib import nullcontext
        area = nullcontext()
        with patch.object(ra, "cleanup_after_cancel", return_value=[{"地址": "x", "結果": "已刪除"}]) as cleanup, \
                patch.object(co.st, "spinner", return_value=nullcontext()):
            self.assertEqual(co._cleanup_reserve_addresses("dev", "e", "p", [{"ok": True, "phone": "0912345678"}], area), [])
            cleanup.assert_not_called()
            result = [{"ok": True, "phone": "0939592628", "address": "新北市A路1號"}]
            self.assertEqual(co._cleanup_reserve_addresses("dev", "e", "p", result, area), [{"地址": "x", "結果": "已刪除"}])
            cleanup.assert_called_once()

    def test_cleanup_after_cancel_accepts_reserve_phone_without_memo_keyword(self):
        cancelled = [{"ok": True, "phone": "0939592628", "address": "新北市A路1號"},
                     {"ok": True, "phone": "0912345678", "address": "新北市B路2號"}]
        with patch.object(ra, "list_member_addresses", return_value=["新北市A路1號", "新北市B路2號"]), \
                patch.object(ra, "active_order_counts", return_value=({}, True)), \
                patch.object(ra, "delete_member_addresses",
                             side_effect=lambda e, m, p, addrs, phone: [{"地址": a, "結果": "已刪除", "說明": ""} for a in addrs]) as deleter:
            ra.cleanup_after_cancel("dev", "e", "p", cancelled)
        self.assertEqual(deleter.call_args.args[3], ["新北市A路1號"])
