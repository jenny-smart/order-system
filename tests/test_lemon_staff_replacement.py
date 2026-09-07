import unittest

from function.lemon_staff_replacement import (
    _match_names_to_slots,
    _order_from_block,
    _staff_name_and_rating,
    build_assignment_plan,
)


class LemonStaffReplacementTests(unittest.TestCase):
    def test_parses_lemon_order(self):
        block = {
            "order_no": "LC00234567",
            "lines": [
                "LC00234567", "王小明", "0912345678", "台北市大安區信義路1號",
                "2026-09-10 (四)", "09:00 - 12:00", "陳專員(5)X檸檬人2(0)",
            ],
        }
        order = _order_from_block(block)
        self.assertEqual(order["service_date"], "2026-09-10")
        self.assertEqual(order["period"], "09:00-12:00")
        self.assertEqual(order["lemon_count"], 1)
        self.assertEqual(order["address"], "台北市大安區信義路1號")

    def test_matches_distinct_people_to_distinct_slots(self):
        slots = [
            {"王甲(5)": "101", "李乙(4)": "102"},
            {"王甲(5)": "201"},
        ]
        matched = _match_names_to_slots(["王甲", "李乙"], slots, [0, 1])
        self.assertEqual(matched[0]["name"], "李乙")
        self.assertEqual(matched[1]["name"], "王甲")

    def test_rejects_duplicate_or_incomplete_selection(self):
        slots = [{"王甲(5)": "101"}, {"王甲(5)": "201"}]
        self.assertIsNone(_match_names_to_slots(["王甲", "王甲"], slots, [0, 1]))

    def test_extracts_rating(self):
        self.assertEqual(_staff_name_and_rating(" 王甲（4.5） "), ("王甲", 4.5))

    def test_missing_similarity_data_does_not_claim_complement(self):
        plans = build_assignment_plan(
            {"people_needed": 2},
            [
                {"name": "王甲", "rating": 5},
                {"name": "李乙", "rating": 4},
            ],
        )
        self.assertEqual(len(plans), 1)
        self.assertNotIn("夥伴組合較互補", plans[0].reasons)


if __name__ == "__main__":
    unittest.main()
