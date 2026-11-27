import unittest

import quick_order as q

BASE = "訂購人姓名：王小明\n訂購人電話：0912345678\n訂購人Email：a@b.com\n服務地址：台北市大安區仁愛路四段1號\n付款方式：信用卡\n"


class PingCodeTest(unittest.TestCase):
    def test_backend_buckets(self):
        cases = {5: "1", 10: "1", 11: "2", 20: "2", 21: "4", 40: "4",
                 41: "5", 54: "5", 60: "5", 61: "6", 80: "6", 81: "7", 120: "7"}
        for n, code in cases.items():
            self.assertEqual(q.ping_code_from_value(n), code, n)

    def test_office_under_20(self):
        self.assertEqual(q.ping_code_from_value(15, "2"), "3")
        self.assertEqual(q.ping_code_from_value(20, "2"), "3")
        self.assertEqual(q.ping_code_from_value(30, "2"), "4")

    def test_missing_defaults(self):
        self.assertEqual(q.ping_code_from_value(None), "4")
        self.assertEqual(q.ping_code_from_value(""), "4")

    def test_parse_54_ping_with_space_before_colon(self):
        parsed = q.parse_new_customer_text(BASE + "室內坪數 : 54")
        self.assertEqual(parsed["ping_value"], 54)
        self.assertEqual(parsed["ping"], "5")

    def test_parse_without_ping(self):
        parsed = q.parse_new_customer_text(BASE)
        self.assertIsNone(parsed["ping_value"])


if __name__ == "__main__":
    unittest.main()
