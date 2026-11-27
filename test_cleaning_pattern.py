import unittest

import quick_order as qo
from shared import cleaning_pattern as cp

SAMPLE = """評估項目：
31-40p
3房間
2衛浴
廚房
客廳
書房
餐廳
前陽台
4窗戶
3落地窗"""


class PingCodeTest(unittest.TestCase):
    def test_home_codes_match_backend(self):
        # 後台：1=10以下 2=11~20 4=21~40 5=41~60 6=61~80 7=81以上（居家沒有 3）
        self.assertEqual([cp.ping_code(n, "1") for n in (8, 15, 25, 35, 40, 55, 70, 90)],
                         ["1", "2", "4", "4", "4", "5", "6", "7"])

    def test_office_codes_match_backend(self):
        # 辦公室：3=20以下 4=21~40 5=41~60 6=61~80 7=81以上
        self.assertEqual([cp.ping_code(n, "2") for n in (8, 20, 30, 50, 70, 100)], ["3", "3", "4", "5", "6", "7"])

    def test_new_customer_text_ping_range(self):
        r = qo.parse_new_customer_text("王小明\n0912345678\na@b.com\n台北市大安區和平東路1號\n坪數：31-40\n信用卡")
        self.assertEqual((r["ping"], r["ping_number"]), ("4", 40))
        r = qo.parse_new_customer_text("王小明\n0912345678\na@b.com\n台北市大安區和平東路1號\n坪數：28\n信用卡")
        self.assertEqual(r["ping"], "4")  # 舊程式會誤判成 3（辦公室才有的 20以下）


class AssessmentTest(unittest.TestCase):
    def test_home_sample(self):
        r = cp.parse_assessment(SAMPLE, "1")
        self.assertEqual(r["ping"], "4")
        self.assertEqual(r["counts"], {"room": 4, "bathroom": 2, "kitchen": 1, "livingroom": 2, "balcony": 1, "window": 7})
        self.assertEqual(r["unknown"], [])

    def test_office_sample(self):
        r = cp.parse_assessment("15坪\n2辦公室\n會議室\n1廁所\n茶水間\n20座位\n6窗戶\n2百葉窗\n簡易消毒\n半年以上沒打掃", "2")
        self.assertEqual(r["ping"], "3")
        self.assertEqual(r["counts"], {"office": 2, "meetingroom": 1, "toilet": 1, "tearoom": 1, "seat": 20, "window": 6, "shutter": 2})
        self.assertEqual(r["flags"], {"disinfection": "1", "uncleaned": "1"})

    def test_unknown_line_reported(self):
        r = cp.parse_assessment("3房間\n儲藏室要整理", "1")
        self.assertEqual(r["unknown"], ["儲藏室要整理"])

    def test_pet_not_for_office(self):
        r = cp.parse_assessment("有養貓", "2")
        self.assertEqual(r["flags"], {})
        self.assertEqual(r["unknown"], ["有養貓"])

    def test_pattern_fields_zero_other_type(self):
        f = cp.pattern_fields("2", {"office": 2, "room": 3}, {"disinfection": "1", "dyson": "1"}, "4")
        self.assertEqual((f["office"], f["room"], f["disinfection"], f["dyson"], f["ping"]), ("2", "0", "1", "0", "4"))
        self.assertNotIn("uncleaned", f)  # 勾選框沒勾就不送


if __name__ == "__main__":
    unittest.main()
