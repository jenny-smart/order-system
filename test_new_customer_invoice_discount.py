import unittest

import quick_order as q


BASE = """訂購人姓名：陳佳吟
訂購人電話：0910828425
訂購人Email：chiayin24@gmail.com
服務地址：108臺北市萬華區華江里環河南路二段250巷42弄5號3
室內坪數 :28
付款方式： 信用卡
"""


class NewCustomerInvoiceDiscountTest(unittest.TestCase):
    def test_mobile_carrier_kept(self):
        parsed = q.parse_new_customer_text(BASE + "發票載具：手機載具\n/1P06KYP")
        self.assertEqual(parsed["carrier"], "/1P06KYP")
        self.assertEqual(parsed["invoice_mode"], "")

    def test_donate_with_code(self):
        parsed = q.parse_new_customer_text(BASE + "發票：捐贈 919")
        self.assertEqual(parsed["invoice_mode"], "捐贈")
        self.assertEqual(parsed["donate_code"], "919")

    def test_paper_invoice(self):
        parsed = q.parse_new_customer_text(BASE + "發票：紙本")
        self.assertEqual(parsed["invoice_mode"], "紙本")
        self.assertEqual(parsed["carrier"], "")

    def test_discount_code(self):
        parsed = q.parse_new_customer_text(BASE + "優惠代碼：LEMON100")
        self.assertEqual(parsed["discount_code"], "LEMON100")

    def test_invoice_payload_supports_donate_and_paper(self):
        self.assertEqual(q._invoice_payload("捐贈", donate_code="919")["invoice_type_override"], "1")
        self.assertEqual(q._invoice_payload("紙本")["carrier_type_id_override"], "4")


class ReadPaywayTest(unittest.TestCase):
    def test_unknown_payway_on_existing_order_does_not_raise(self):
        self.assertEqual(q._extract_payway_line("付款方式：現金"), "")
        self.assertEqual(q._extract_payway_line("付款方式：信用卡"), "信用卡")


if __name__ == "__main__":
    unittest.main()
