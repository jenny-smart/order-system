import unittest

from quick_order import build_line_message


class CombinedOrderAddressDisplayTest(unittest.TestCase):
    def _result(self, **overrides):
        result = {
            "payway": "信用卡", "region": "台北", "date": "2026-09-10",
            "period_s": "09:00-11:00", "person": "2", "service_amount": "4800",
            "fare": "0", "address": "台北市中山區地址A",
            "order_no": "LC002144601", "all_order_nos": ["LC002144601", "LC002144611"],
            "service_label": "居家清潔",
        }
        result.update(overrides)
        return result

    def test_different_addresses_are_shown_below_each_service_time(self):
        schedule = (
            "2026/09/10 09:00-11:00（2人2小時），共4人時\n"
            "台北市中山區地址A\n"
            "2026/09/14 09:00-11:00（2人2小時），共4人時\n"
            "台北市大安區地址B"
        )

        message = build_line_message(self._result(
            combined_period=schedule, multi_date=True, multi_address=True,
        ))

        self.assertIn(f"服務時間：\n{schedule}", message)
        self.assertNotIn("服務地址：", message)

    def test_same_address_keeps_single_address_line(self):
        message = build_line_message(self._result(
            combined_period="2026/09/10 09:00-11:00（2人2小時），共4人時",
            multi_date=True, multi_address=False,
        ))

        self.assertIn("服務地址：台北市中山區地址A", message)

    def test_stored_value_multiple_dates_start_on_next_line(self):
        schedule = "2026/12/09 14:00-18:00（1人4小時），共4人時\n2026/12/30 14:00-17:00（2人3小時），共6人時"
        message = build_line_message(self._result(
            payway="儲值金", combined_period=schedule, multi_date=True, multi_address=False,
        ))
        self.assertIn(f"服務時間：\n{schedule}", message)


if __name__ == "__main__":
    unittest.main()
