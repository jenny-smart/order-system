import unittest
from unittest.mock import patch

import pandas as pd

from function.lemon_staff_replacement import (
    UNQUALIFIED_REASON,
    _batch_entry_conflicts,
    _build_qualification_text,
    _match_names_to_slots,
    _order_from_block,
    _periods_overlap,
    _staff_name_and_rating,
    analyze_lemon_orders,
    build_assignment_plan,
    preferred_gender_label,
    _run_batch_replacements,
)


class LemonStaffReplacementTests(unittest.TestCase):
    def test_parses_lemon_order(self):
        block = {
            "order_no": "LC00234567",
            "lines": [
                "LC00234567",
                "王小明",
                "0912345678",
                "台北市大安區信義路1號",
                "2026-09-10 (四)",
                "09:00 - 12:00",
                "陳專員(5)X檸檬人2(0)",
            ],
        }
        order = _order_from_block(block)
        self.assertEqual(order["service_date"], "2026-09-10")
        self.assertEqual(order["period"], "09:00-12:00")
        self.assertEqual(order["lemon_count"], 1)
        self.assertEqual(order["address"], "台北市大安區信義路1號")

    def test_maps_preferred_gender_labels(self):
        self.assertEqual(preferred_gender_label(0), "不限")
        self.assertEqual(preferred_gender_label(1), "限女")
        self.assertEqual(preferred_gender_label(2), "1女")
        self.assertEqual(preferred_gender_label(3), "限男")
        self.assertEqual(preferred_gender_label(4), "1男")
        self.assertEqual(preferred_gender_label(5), "1男1女")

    def test_builds_qualified_and_unqualified_lists(self):
        qualified, unqualified = _build_qualification_text(
            ["王甲", "李乙", "丁丁"],
            ["王甲", "李乙", "張丙", "丁丁"],
        )
        self.assertEqual(qualified, "丁丁、李乙、王甲")
        self.assertIn("張丙", unqualified)
        self.assertIn(UNQUALIFIED_REASON, unqualified)

    def test_period_overlap_detects_partial_overlap(self):
        self.assertTrue(_periods_overlap("09:00-12:00", "09:00-11:00"))
        self.assertTrue(_periods_overlap("09:00-11:00", "10:00-12:00"))
        self.assertFalse(_periods_overlap("09:00-12:00", "12:00-14:00"))
        self.assertFalse(_periods_overlap("09:00-12:00", "13:00-15:00"))

    def test_batch_entry_conflict_uses_overlap_and_names(self):
        left = {"service_date": "2026-09-10", "period": "09:00-12:00", "selected_names": ["王甲"]}
        right = {"service_date": "2026-09-10", "period": "09:00-11:00", "selected_names": ["王甲"]}
        self.assertTrue(_batch_entry_conflicts(left, right))
        far = {"service_date": "2026-09-10", "period": "12:00-14:00", "selected_names": ["王甲"]}
        self.assertFalse(_batch_entry_conflicts(left, far))

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

    def test_batch_avoids_duplicate_staff_on_same_slot(self):
        orders = [
            {
                "order_no": "LC00100001",
                "phone": "0911111111",
                "service_date": "2026-09-10",
                "period": "09:00-12:00",
                "staff": "檸檬人1(0)",
                "current_staff": ["檸檬人1(0)"],
                "purchase_id": "1000001",
                "lemon_count": 1,
                "people_needed": 1,
                "name": "甲",
                "address": "A",
            },
            {
                "order_no": "LC00100002",
                "phone": "0922222222",
                "service_date": "2026-09-10",
                "period": "09:00-12:00",
                "staff": "檸檬人1(0)",
                "current_staff": ["檸檬人1(0)"],
                "purchase_id": "1000002",
                "lemon_count": 1,
                "people_needed": 1,
                "name": "乙",
                "address": "B",
            },
        ]
        schedule_contexts = {
            "1000001": {
                "ok": True,
                "error": "",
                "recommendations": [
                    {"display": "王甲", "names": ["王甲"]},
                    {"display": "李乙", "names": ["李乙"]},
                    {"display": "陳丙", "names": ["陳丙"]},
                ],
                "candidate_names": ["王甲", "李乙", "陳丙", "丁丁"],
                "candidate_count": 4,
            },
            "1000002": {
                "ok": True,
                "error": "",
                "recommendations": [
                    {"display": "王甲", "names": ["王甲"]},
                    {"display": "張三", "names": ["張三"]},
                    {"display": "李四", "names": ["李四"]},
                ],
                "candidate_names": ["王甲", "張三", "李四", "丁丁"],
                "candidate_count": 4,
            },
        }

        def fake_schedule_context(_session, _base_url, order, limit=3):
            return schedule_contexts[order["purchase_id"]]

        def fake_member_context(_session, phone, member_token, member_cache, token_error=""):
            return {
                "ok": True,
                "error": "",
                "phone": phone,
                "member_id": f"member-{phone}",
                "roster_names": ["王甲", "李乙", "陳丙", "張三", "李四"],
                "preferred_gender_label": "不限",
            }

        with patch("function.lemon_staff_replacement._get_schedule_context", side_effect=fake_schedule_context), \
             patch("function.lemon_staff_replacement._resolve_member_context", side_effect=fake_member_context):
            analyzed = analyze_lemon_orders(None, "", orders, member_token="token")

        self.assertIn("丁丁", analyzed[0]["符合該地址資格人員"])
        self.assertIn("丁丁", analyzed[1]["符合該地址資格人員"])
        self.assertEqual(analyzed[0]["批次預設順位"], "Top1")
        self.assertTrue(analyzed[0]["處理"])
        self.assertEqual(analyzed[1]["批次預設順位"], "Top2")
        self.assertTrue(analyzed[1]["處理"])
        self.assertEqual(analyzed[1]["批次狀態"], "可勾選")

    def test_overlap_orders_prefer_non_conflicting_recommendation(self):
        orders = [
            {
                "order_no": "LC00100010",
                "phone": "0911111111",
                "service_date": "2026-09-10",
                "period": "09:00-12:00",
                "staff": "檸檬人1(0)",
                "current_staff": ["檸檬人1(0)"],
                "purchase_id": "1000010",
                "lemon_count": 1,
                "people_needed": 1,
                "name": "甲",
                "address": "A",
            },
            {
                "order_no": "LC00100011",
                "phone": "0922222222",
                "service_date": "2026-09-10",
                "period": "09:00-11:00",
                "staff": "檸檬人1(0)",
                "current_staff": ["檸檬人1(0)"],
                "purchase_id": "1000011",
                "lemon_count": 1,
                "people_needed": 1,
                "name": "乙",
                "address": "B",
            },
        ]
        schedule_contexts = {
            "1000010": {
                "ok": True,
                "error": "",
                "recommendations": [
                    {"display": "王甲", "names": ["王甲"]},
                    {"display": "李乙", "names": ["李乙"]},
                ],
                "candidate_names": ["王甲", "李乙"],
                "candidate_count": 2,
            },
            "1000011": {
                "ok": True,
                "error": "",
                "recommendations": [
                    {"display": "王甲", "names": ["王甲"]},
                    {"display": "張三", "names": ["張三"]},
                ],
                "candidate_names": ["王甲", "張三"],
                "candidate_count": 2,
            },
        }

        def fake_schedule_context(_session, _base_url, order, limit=3):
            return schedule_contexts[order["purchase_id"]]

        def fake_member_context(_session, phone, member_token, member_cache, token_error=""):
            return {
                "ok": True,
                "error": "",
                "phone": phone,
                "member_id": f"member-{phone}",
                "roster_names": ["王甲", "李乙", "張三"],
                "preferred_gender_label": "不限",
            }

        with patch("function.lemon_staff_replacement._get_schedule_context", side_effect=fake_schedule_context), \
             patch("function.lemon_staff_replacement._resolve_member_context", side_effect=fake_member_context):
            analyzed = analyze_lemon_orders(None, "", orders, member_token="token")

        self.assertEqual(analyzed[0]["批次預設順位"], "Top1")
        self.assertEqual(analyzed[1]["批次預設順位"], "Top2")

    def test_error_rows_are_not_selectable(self):
        order = {
            "order_no": "LC00100003",
            "phone": "0933333333",
            "service_date": "2026-09-10",
            "period": "09:00-12:00",
            "staff": "檸檬人1(0)",
            "current_staff": ["檸檬人1(0)"],
            "purchase_id": "1000003",
            "lemon_count": 1,
            "people_needed": 1,
            "name": "丙",
            "address": "C",
        }

        with patch(
            "function.lemon_staff_replacement._get_schedule_context",
            return_value={
                "ok": False,
                "error": "讀取 schedule/edit 失敗：HTTP 500",
                "recommendations": [],
                "candidate_names": [],
                "candidate_count": 0,
                "slots": [],
                "target_indexes": [],
                "csrf": "",
                "origin_ids": [],
            },
        ), patch(
            "function.lemon_staff_replacement._resolve_member_context",
            return_value={
                "ok": True,
                "error": "",
                "phone": "0933333333",
                "member_id": "member-0933333333",
                "roster_names": ["王甲"],
                "preferred_gender_label": "不限",
            },
        ):
            analyzed = analyze_lemon_orders(None, "", [order], member_token="token")

        self.assertFalse(analyzed[0]["可批次"])
        self.assertFalse(analyzed[0]["處理"])
        self.assertIn("讀取 schedule/edit 失敗", analyzed[0]["批次狀態"])

    def test_analyze_continues_when_one_order_has_too_few_candidates(self):
        orders = [
            {
                "order_no": "LC00100020",
                "phone": "0912345678",
                "service_date": "2026-09-10",
                "period": "09:00-12:00",
                "staff": "檸檬人1(0)、檸檬人2(0)",
                "current_staff": ["檸檬人1(0)", "檸檬人2(0)"],
                "purchase_id": "1000020",
                "lemon_count": 2,
                "people_needed": 2,
                "name": "缺候選",
                "address": "A",
            },
            {
                "order_no": "LC00100021",
                "phone": "0987654321",
                "service_date": "2026-09-11",
                "period": "13:00-15:00",
                "staff": "檸檬人1(0)",
                "current_staff": ["檸檬人1(0)"],
                "purchase_id": "1000021",
                "lemon_count": 1,
                "people_needed": 1,
                "name": "正常",
                "address": "B",
            },
        ]

        def fake_get_schedule_edit_info(_session, _base_url, service_date, purchase_id):
            if purchase_id == "1000020":
                return (
                    "csrf-bad",
                    ["11", "22"],
                    [
                        {"檸檬人1(0)": "s1", "王甲(5)": "s2"},
                        {"檸檬人2(0)": "s3"},
                    ],
                )
            return (
                "csrf-good",
                ["33"],
                [
                    {"檸檬人1(0)": "s4", "李乙(5)": "s5"},
                ],
            )

        def fake_member_context(_session, phone, member_token, member_cache, token_error=""):
            return {
                "ok": True,
                "error": "",
                "phone": phone,
                "member_id": f"member-{phone}",
                "roster_names": ["王甲", "李乙", "陳丙"],
                "preferred_gender_label": "不限",
            }

        with patch("function.lemon_staff_replacement._get_schedule_edit_info", side_effect=fake_get_schedule_edit_info), \
             patch("function.lemon_staff_replacement._resolve_member_context", side_effect=fake_member_context):
            analyzed = analyze_lemon_orders(None, "", orders, member_token="token")

        self.assertEqual(len(analyzed), 2)
        self.assertFalse(analyzed[0]["可批次"])
        self.assertIn("目前真實班表沒有足夠的正式專員可替換", analyzed[0]["批次狀態"])
        self.assertTrue(analyzed[1]["可批次"])
        self.assertEqual(analyzed[1]["批次狀態"], "可勾選")

    def test_manual_conflict_skips_replace_and_allows_other_rows(self):
        analyzed_orders = [
            {
                "order_no": "LC00110001",
                "service_date": "2026-09-10",
                "period": "09:00-12:00",
                "推薦列表": [{"names": ["王甲"]}],
                "批次狀態": "可勾選",
            },
            {
                "order_no": "LC00110002",
                "service_date": "2026-09-10",
                "period": "09:00-11:00",
                "推薦列表": [{"names": ["王甲"]}],
                "批次狀態": "可勾選",
            },
            {
                "order_no": "LC00110003",
                "service_date": "2026-09-10",
                "period": "13:00-15:00",
                "推薦列表": [{"names": ["李乙"]}],
                "批次狀態": "可勾選",
            },
        ]
        edited_df = pd.DataFrame([
            {"處理": True, "採用順位": "Top1"},
            {"處理": True, "採用順位": "Top1"},
            {"處理": True, "採用順位": "Top1"},
        ])

        with patch("function.lemon_staff_replacement.replace_lemon_staff", return_value={"assigned": ["李乙"]}) as mocked_replace:
            results = _run_batch_replacements("env", "email", "password", analyzed_orders, edited_df)

        self.assertEqual(mocked_replace.call_count, 1)
        self.assertEqual(results[0]["結果"], "失敗")
        self.assertIn("重疊", results[0]["原因"])
        self.assertEqual(results[1]["結果"], "失敗")
        self.assertIn("重疊", results[1]["原因"])
        self.assertEqual(results[2]["結果"], "成功")

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
