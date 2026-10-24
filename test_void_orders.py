import unittest
from unittest.mock import patch

import shared.batch_booking_safety as safety
import orders

REFUNDED = ["TT00217785", "代客預訂：Jenny", "王亭雅", "0912269511", "新北市中和區中山路二段457號20樓",
            "2026-10-22 17:09:54", "居家清潔", "2026-12-14 (一)", "09:00 - 12:00", "總金額：0",
            "付款方式：儲值金", "付款狀態：已退款", "付款日期：2026-10-22 17:09:55",
            "取消人員：Jenny", "取消時間：2026-10-22 23:19:53", "已處理"]
PAID = [line.replace("TT00217785", "TT00217999").replace("已退款", "已付款") for line in REFUNDED
        if not line.startswith(("取消人員", "取消時間"))]


class VoidOrderTest(unittest.TestCase):
    def test_void_detection(self):
        self.assertEqual(orders.card_payment_status(REFUNDED), "已退款")
        self.assertTrue(orders.is_void_card(REFUNDED))
        self.assertTrue(orders.is_void_card([l.replace("已退款", "取消訂單") for l in REFUNDED]))
        self.assertFalse(orders.is_void_card(PAID))
        self.assertFalse(orders.is_void_card([l.replace("已付款", "待付款") for l in PAID]))

    def test_new_order_match_skips_refunded_card(self):
        cards = [{"order_no": "TT00217785", "lines": REFUNDED}, {"order_no": "TT00217999", "lines": PAID}]
        with patch.object(orders, "extract_order_cards_from_purchase_html", return_value=cards):
            self.assertEqual(orders.match_order_from_purchase_page("", "2026-12-14", "09:00-12:00", phone="0912269511"),
                             "TT00217999")
        with patch.object(orders, "extract_order_cards_from_purchase_html", return_value=cards[:1]):
            self.assertIsNone(orders.match_order_from_purchase_page("", "2026-12-14", "09:00-12:00", phone="0912269511"))

    def test_recovery_block_key_marks_void(self):
        self.assertTrue(safety._block_key({"order_no": "TT00217785", "lines": REFUNDED})["void"])
        self.assertFalse(safety._block_key({"order_no": "TT00217999", "lines": PAID})["void"])


if __name__ == "__main__":
    unittest.main()
