# -*- coding: utf-8 -*-
"""合併單人保留單：同時段 2 張以上 1 人保留單 → 取消後重新成立 N 人單。"""
import unittest

from shared import unassigned_staff as us


def row(no, day, period, staff, eligible=True):
    return {"order_no": no, "purchase_id": no, "service_date": day, "period": period, "staff": staff,
            "cancel_eligible": eligible}


ROWS = [
    row("A1", "2027-01-23", "09:00-12:00", "蔡亞諺"),
    row("A2", "2027-01-23", "08:30-12:30", "李佳芸"),      # 同上午組 → 合併
    row("B1", "2027-01-23", "14:00-17:00", "周紹誠"),      # 下午只有 1 張 → 不動
    row("C1", "2027-01-24", "09:00-12:00", "王小美 X 陳大文"),  # 2 人單 → 不算
    row("C2", "2027-01-24", "09:00-11:00", "林阿花"),
    row("D1", "2027-01-25", "09:00-16:00", "甲"),
    row("D2", "2027-01-25", "09:00-18:00", "乙", eligible=False),  # 不可取消 → 不算
]


class FindGroupsTest(unittest.TestCase):
    def test_only_two_or_more_single_person_in_same_group(self):
        groups = us.find_single_reserve_groups("prod", "e", "p", "2027-01-22", "2027-02-04", finder=lambda *a, **k: ROWS)
        self.assertEqual(list(groups), [("2027-01-23", "上午")])
        self.assertEqual([r["order_no"] for r in groups[("2027-01-23", "上午")]], ["A1", "A2"])


class MergeAndCreateTest(unittest.TestCase):
    def test_cancel_then_create_combined(self):
        state = {"rows": list(ROWS), "cancelled": []}

        def finder(*a, **k):
            return [r for r in state["rows"] if r["order_no"] not in state["cancelled"]]

        def canceller(env, e, p, rows, n):
            state["cancelled"] += [r["order_no"] for r in rows]
            return [{**r, "ok": True} for r in rows]

        # 取消後兩人回到未配班：上午 2 人（3、4 小時）
        def get_html(_d):
            return ""

        scans = []

        def fake_scan(get, s, e):
            scans.append((s, e))
            return {("2027-01-23", "上午"): {"蔡亞諺": 3, "李佳芸": 4}} if state["cancelled"] else {}

        created = []

        def creator(**kw):
            created.append([(p["service_date"], p["group"], p["person"], p["hours"]) for p in kw["plan"]])
            state["rows"].append(row("N1", "2027-01-23", "09:00-12:00", "蔡亞諺 X 李佳芸"))
            return [{"success": True, "order_no": "N1"}]

        orig = us.scan_range
        us.scan_range = fake_scan
        try:
            out = us.merge_and_create(env_name="prod", backend_email="e", backend_password="p", lookup_result={},
                                      region="台北", address="x", date_start="2027-01-22", date_end="2027-02-04",
                                      get_html=get_html, finder=finder, canceller=canceller, creator=creator)
        finally:
            us.scan_range = orig
        self.assertEqual(state["cancelled"], ["A1", "A2"])
        self.assertEqual(created, [[("2027-01-23", "上午", 2, 3)]])
        self.assertEqual([c["order_no"] for c in out["cancelled"]], ["A1", "A2"])
        self.assertEqual(out["created"], [{"success": True, "order_no": "N1"}])

    def test_nothing_to_do_scans_once(self):
        calls = []
        orig = us.scan_range
        us.scan_range = lambda *a: calls.append(a) or {}
        try:
            out = us.merge_and_create(env_name="prod", backend_email="e", backend_password="p", lookup_result={},
                                      region="台北", address="x", date_start="2027-01-22", date_end="2027-02-04",
                                      get_html=lambda d: "", finder=lambda *a, **k: [],
                                      canceller=lambda *a: self.fail("不應取消"), creator=lambda **k: self.fail("不應成立"))
        finally:
            us.scan_range = orig
        self.assertEqual(out, {"cancelled": [], "created": []})
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
