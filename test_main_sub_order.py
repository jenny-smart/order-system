import unittest
from unittest.mock import patch

import quick_order as qo
from shared import main_sub_order as ms


class SummarizePlanTest(unittest.TestCase):
    def test_lin_case_paid_equals_actual(self):
        # 林佩諆：主單 4人8小時（1 檸檬人）＋優惠券 1人2小時 → 付 30；實際 3人8小時＋2人3小時＝30
        p = ms.summarize_plan(4, 8, 1, 2, [{"person": 2, "hour": 3}])
        self.assertEqual((p["paid_ph"], p["actual_ph"], p["gift_ph"]), (30, 30, 0))
        self.assertEqual(p["errors"], [])

    def test_zhuang_case_gift_two_person_hours(self):
        # 莊博鈞：主單 4人8小時（1 檸檬人）付 32；實際 3人8小時＋2人3小時＋1人4小時＝34，送 2 人時
        p = ms.summarize_plan(4, 8, 1, 0, [{"person": 2, "hour": 3}, {"person": 1, "hour": 4}])
        self.assertEqual((p["paid_ph"], p["actual_ph"], p["gift_ph"]), (32, 34, 2))
        self.assertEqual(p["errors"], [])

    def test_all_lemon_allowed_when_schedule_not_ready(self):
        # 成單時還沒排班：主單 4 位全放檸檬人，其中 1 位佔位，其餘之後由排班人員置換
        p = ms.summarize_plan(4, 8, 4, 0, [{"person": 2, "hour": 3}, {"person": 1, "hour": 4}], placeholder_count=1)
        self.assertEqual(p["errors"], [])
        self.assertEqual((p["paid_ph"], p["actual_ph"], p["gift_ph"]), (32, 34, 2))

    def test_lemon_hours_must_be_less_than_total(self):
        p = ms.summarize_plan(2, 8, 2, 0, [{"person": 0, "hour": 3}], placeholder_count=0)
        self.assertTrue(p["errors"])
        p = ms.summarize_plan(4, 8, 5, 0, [{"person": 2, "hour": 3}])
        self.assertTrue(any("檸檬人數" in e for e in p["errors"]))

    def test_placeholder_cannot_exceed_lemon(self):
        p = ms.summarize_plan(4, 8, 1, 0, [{"person": 2, "hour": 3}], placeholder_count=2)
        self.assertTrue(any("佔位" in e for e in p["errors"]))

    def test_actual_less_than_paid_blocked(self):
        p = ms.summarize_plan(4, 8, 1, 0, [{"person": 1, "hour": 2}])
        self.assertTrue(any("少於客人付費" in e for e in p["errors"]))

    def test_needs_sub_order(self):
        p = ms.summarize_plan(4, 8, 1, 0, [])
        self.assertTrue(any("至少要有 1 筆補單" in e for e in p["errors"]))


class AllPlaceholderTest(unittest.TestCase):
    def test_main_2p3h_actual_1p2h_plus_1p4h(self):
        # 主單 2人3小時全是佔位檸檬人；實際 1人2小時＋1人4小時
        subs = [{"period_s": "09:00-11:00", "person": 1, "hour": 2}, {"period_s": "14:00-18:00", "person": 1, "hour": 4}]
        p = ms.summarize_plan(2, 3, 2, 0, subs, placeholder_count=2)
        self.assertEqual(p["errors"], [])
        self.assertEqual((p["paid_ph"], p["actual_ph"], p["gift_ph"], p["lemon_ph"], p["total_ph"]), (6, 6, 0, 6, 12))
        note = ms.build_merge_note("LC1", ["LC2", "LC3"], 2, "09:00-12:00", 2, subs)
        self.assertEqual(note, "LC1＋LC2＋LC3合併訂單，1人-09-11點＋1人-14-18點")


class MergeNoteTest(unittest.TestCase):
    def test_zhuang_note_time_slots(self):
        subs = [{"period_s": "09:00-12:00", "person": 2}, {"period_s": "14:00-18:00", "person": 1}]
        note = ms.build_merge_note("LC00221474", ["LC00221473", "LC00221475"], 4, "09:00-18:00", 1, subs)
        self.assertEqual(note, "LC00221473＋LC00221474＋LC00221475合併訂單，2人-09-12點＋3人-09-18點＋1人-14-18點")

    def test_lin_note_time_slots(self):
        note = ms.build_merge_note("LC00221393", ["LC00221394"], 4, "09:00-18:00", 1,
                                   [{"period_s": "14:00-17:00", "person": 2}])
        self.assertEqual(note, "LC00221393＋LC00221394合併訂單，3人-09-18點＋2人-14-17點")

    def test_same_slot_people_added(self):
        note = ms.build_merge_note("LC1", ["LC2"], 4, "09:00-18:00", 1, [{"period_s": "09:00-18:00", "person": 2}])
        self.assertEqual(note, "LC1＋LC2合併訂單，5人-09-18點")

    def test_half_hour_slot(self):
        self.assertEqual(ms.period_note_text("08:30-12:30"), "08:30-12:30點")


class FakeResp:
    status_code = 200


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, params=None, data=None, headers=None, allow_redirects=True):
        self.posts.append(data)
        return FakeResp()


class EnsureLemonTest(unittest.TestCase):
    SLOTS = [
        {"王小明": "11", "檸檬人3": "93"},
        {"陳大華": "12", "檸檬人3": "93"},
        {"林美美": "13", "檸檬人3": "93", "檸檬人5": "95"},
        {"張志強": "14", "檸檬人3": "93", "檸檬人5": "95"},
    ]

    def run_ensure(self, slots, origin, after, lemon_count=1):
        session = FakeSession()
        infos = iter([("csrf", origin, slots), ("csrf", after, slots)])
        with patch.object(qo, "_fetch_order_edit_id", return_value="555"), \
             patch.object(qo, "_get_schedule_edit_info", side_effect=lambda *a, **k: next(infos)), \
             patch.object(qo, "_get_unassigned_staff_for_period", return_value={"names": {"檸檬人3", "檸檬人5"}}), \
             patch.object(qo, "_get_occupied_staff_for_period", return_value=set()):
            res = ms.ensure_main_order_lemons(session, "https://x", "LC1", "2026-11-29", "09:00-18:00", lemon_count)
        return res, session

    def test_replaces_last_slot_only_and_keeps_real_staff(self):
        res, session = self.run_ensure(self.SLOTS, ["11", "12", "13", "14"], ["11", "12", "13", "93"])
        self.assertTrue(res["success"], res)
        data = dict(session.posts[0])
        self.assertEqual([data[f"shiftId[{i}]"] for i in range(4)], ["11", "12", "13", "93"])
        self.assertIn("張志強→檸檬人3", res["message"])

    def test_already_has_lemon_no_post(self):
        slots = [dict(s) for s in self.SLOTS]
        res, session = self.run_ensure(slots, ["11", "12", "13", "95"], [])
        self.assertTrue(res["success"])
        self.assertEqual(session.posts, [])

    def test_unknown_current_staff_stops(self):
        res, session = self.run_ensure(self.SLOTS, ["11", "12", "13", "99"], [])
        self.assertFalse(res["success"])
        self.assertEqual(session.posts, [])


if __name__ == "__main__":
    unittest.main()
