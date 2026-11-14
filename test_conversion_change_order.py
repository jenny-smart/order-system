import unittest
from unittest.mock import patch

import orders  # noqa: F401
import quick_order as q
from memo_system import change_order as co

STAGE1 = {"order_no_a": "LC00220455", "session": object(), "region_a": "台北", "env_name": "prod",
          "payway_a": "信用卡", "member_payload": {}, "target_date_a": "2026-12-10"}
ORDER = {"order_no": "LC00220455", "customer_name": "王小明", "period_text": "09:00 - 16:00",
         "payway": "藍新ATM", "invoice_no": "AB12345678", "line_url": "https://chat.line.biz/x"}


class ConversionChangeOrderTest(unittest.TestCase):
    def run_append(self, refund, charge):
        with patch.object(co, "fetch_order_basic", return_value=dict(ORDER)), \
             patch.object(q, "load_config", return_value={"enabled": False}), \
             patch.object(co, "append_rows_to_sheet", return_value={"written": 1, "errors": [], "start_row": 88}) as app:
            res = q._append_conversion_change_order(STAGE1, "LC00220455+LC00220500", refund, charge)
        return res, app

    def test_refund_row(self):
        res, app = self.run_append(1200, 0)
        self.assertTrue(res["ok"])
        region, rows = app.call_args.args
        row = rows[0]
        self.assertEqual(region, "台北")
        self.assertEqual((row["B"], row["C"], row["G"], row["S"], row["R"]), ("待退款", co.TYPE_REFUND, "LC00220455", 1200, "ATM"))
        self.assertIn("退費 $1200", row["J"])

    def test_charge_row(self):
        res, app = self.run_append(0, 700)
        row = app.call_args.args[1][0]
        self.assertEqual((row["B"], row["C"], row["N"]), ("待收款", co.TYPE_CHARGE, 700))
        self.assertIn("第 88 列", res["message"])

    def test_vip_uses_stored_value_status(self):
        with patch.object(co, "fetch_order_basic", return_value=dict(ORDER, payway="儲值金")), \
             patch.object(q, "load_config", return_value={"enabled": False}), \
             patch.object(co, "append_rows_to_sheet", return_value={"written": 1, "errors": [], "start_row": 9}) as app:
            q._append_conversion_change_order(STAGE1, "A+B", 500, 0)
        row = app.call_args.args[1][0]
        self.assertEqual((row["B"], row["F"]), ("待返儲值金", "VIP"))

    def test_no_diff_skips(self):
        res, app = self.run_append(0, 0)
        self.assertTrue(res.get("skipped"))
        app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
