import json
import unittest
from unittest.mock import Mock, patch

from memo_system import atm


class _Response:
    def __init__(self, items):
        self.text = "purchaseList: " + json.dumps({"data": items}, ensure_ascii=False)

    def raise_for_status(self):
        return None


class AtmStatusGuardTests(unittest.TestCase):
    def test_search_keeps_only_pending_orders(self):
        items = [
            {"order_no": "LC001", "purchase_status": 0, "payway": 2, "total": 1000, "fare": 0},
            {"order_no": "LC002", "purchase_status": 2, "payway": 2, "total": 1000, "fare": 0},
            {"order_no": "LC003", "purchase_status": 1, "payway": 2, "total": 1000, "fare": 0},
        ]
        with patch.object(atm.memo, "session_get", return_value=_Response(items)):
            rows = atm.search_atm_unpaid_orders(object(), "2026-10-28")
        self.assertEqual([row["order_no"] for row in rows], ["LC001"])

    def test_default_date_is_today_in_taiwan(self):
        with patch.object(atm, "today_tw", return_value=atm._date(2026, 10, 28)):
            self.assertEqual(atm.default_date_until_tw(), "2026-10-28")

    def test_schedule_flags_cancelled_order_in_column_m(self):
        rows = [["銀行資料"], [], [], [], ["", "", "", "", "", "", "", "", "", "LC001", "王小明", "1000"],
                ["", "", "", "", "", "", "", "", "", "LC002", "李小華", "2000"]]
        ws = Mock()
        ws.get_all_values.return_value = rows
        statuses = {"LC001": 2, "LC002": 0}
        with patch.object(atm, "get_atm_worksheet", return_value=ws), \
             patch.object(atm, "find_purchase_by_order_no", side_effect=lambda _s, no: {"purchase_status": statuses[no]}), \
             patch.object(atm.memo, "with_retry", side_effect=lambda fn, *a, **k: fn(*a, **k)):
            result = atm.flag_cancelled_pending_orders("台北", object())
        self.assertEqual(result, {"checked": 2, "flagged": 1})
        self.assertEqual(ws.batch_update.call_args.args[0], [{"range": "M5", "values": [["取消訂單"]]}])


if __name__ == "__main__":
    unittest.main()
