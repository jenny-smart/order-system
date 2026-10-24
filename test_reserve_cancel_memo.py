import unittest

import function.reserve_cancel as rc


class ReserveCancelMemoTest(unittest.TestCase):
    def test_already_cancelled_reserve_is_not_listed(self):
        self.assertFalse(rc._memo_matches_filter("取消系統保留單", "僅系統保留單"))
        self.assertFalse(rc._memo_matches_filter("取消系統保留單", "系統保留單或空白"))
        self.assertTrue(rc._memo_matches_filter("取消系統保留單", "全部（僅供查看）"))

    def test_active_reserve_and_blank_are_listed(self):
        self.assertTrue(rc._memo_matches_filter("系統保留單", "僅系統保留單"))
        self.assertTrue(rc._memo_matches_filter("", "系統保留單或空白"))

    def test_proxy_reserve_keyword_matches_active_only(self):
        keyword = rc.proxy_keyword(" 代客保留: 王小明 ")
        self.assertEqual(keyword, "代客保留：王小明")
        self.assertTrue(rc._memo_matches_filter("代客保留：王小明", rc.PROXY_FILTER, keyword))
        self.assertFalse(rc._memo_matches_filter("取消代客保留：王小明", rc.PROXY_FILTER, keyword))
        self.assertFalse(rc._memo_matches_filter("代客保留：李小華", rc.PROXY_FILTER, keyword))
        self.assertFalse(rc._memo_matches_filter("系統保留單", rc.PROXY_FILTER, keyword))
        with self.assertRaises(ValueError):
            rc.proxy_keyword("王小明")

    def test_cancel_proxy_reserve_rechecks_memo_and_prefixes_cancel(self):
        from unittest.mock import patch
        rows = [{"purchase_id": "1", "order_no": "LC1", "service_date": "2026-12-01", "memo_keyword": "代客保留：王小明"},
                {"purchase_id": "2", "order_no": "LC2", "service_date": "2026-12-02", "memo_keyword": "代客保留：王小明"},
                {"purchase_id": "3", "order_no": "LC3", "service_date": "2026-12-03"}]
        memos = {"1": "代客保留：王小明", "2": "取消代客保留：王小明", "3": "系統保留單"}
        calls = []

        def cancel(env, email, password, group, **kw):
            calls.append(([r["order_no"] for r in group], kw["customer_memo"]))
            return [{"order_no": r["order_no"], "ok": True} for r in group]

        with patch.object(rc.co, "_new_logged_in_session", return_value=(None, "")), \
                patch.object(rc.co, "fetch_order_cancel_details", side_effect=lambda s, b, pid: {"memo": memos[pid]}), \
                patch.object(rc.co, "cancel_orders", side_effect=cancel), \
                patch.object(rc, "append_log_rows"):
            results = rc.cancel_reserve_orders("dev", "e", "p", rows, 3)
        self.assertEqual(calls, [(["LC1"], "取消代客保留：王小明"), (["LC3"], "取消系統保留單")])
        skipped = [r for r in results if not r["ok"]]
        self.assertEqual([r["order_no"] for r in skipped], ["LC2"])


if __name__ == "__main__":
    unittest.main()
