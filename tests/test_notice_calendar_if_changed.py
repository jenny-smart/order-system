# -*- coding: utf-8 -*-
"""未配班人員／未配班保留單行事曆：內容沒變不新增（留最早那則），有變才再新增一則、舊的保留。"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import notice_calendar as nc

TZ = ZoneInfo("Asia/Taipei")


class FakeCalendar:
    def __init__(self):
        self.items, self.deleted = [], 0

    def events(self):
        return self

    def list(self, **kw):
        self._result = {"items": [dict(e) for e in self.items]}
        return self

    def insert(self, calendarId, body, sendUpdates):
        self._result = None
        self.items.append(dict(body, id=str(len(self.items))))
        return self

    def delete(self, **kw):
        self.deleted += 1
        return self

    def execute(self):
        return self._result


def event(text, hour):
    return dict(summary="【未配班剩1人】台北 1 個時段（11/22）", description=text,
                start=datetime(2026, 11, 22, hour, 30, tzinfo=TZ), reminder_minutes=[0],
                replace_prefix="【未配班剩1人】台北")


class IfChangedTest(unittest.TestCase):
    def test_keep_earliest_until_changed(self):
        cal = FakeCalendar()
        msgs, ok = nc.write_if_changed(event("2026/11/24 下午-1", 8), ["cal"], service_factory=lambda _c: cal)
        self.assertEqual((ok, len(cal.items)), (1, 1))
        self.assertIn("已記入", msgs[0])
        for h in (9, 10, 11):  # 沒變：不新增
            msgs, ok = nc.write_if_changed(event("2026/11/24 下午-1", h), ["cal"], service_factory=lambda _c: cal)
        self.assertEqual(len(cal.items), 1)
        self.assertIn("內容沒變", msgs[0])
        self.assertEqual(cal.items[0]["start"]["dateTime"][11:16], "08:30")  # 留最早那則
        nc.write_if_changed(event("2026/11/25 上午-1", 12), ["cal"], service_factory=lambda _c: cal)  # 有變：新增
        self.assertEqual(len(cal.items), 2)
        self.assertEqual(cal.deleted, 0)  # 舊的保留


class ReserveCalendarTest(unittest.TestCase):
    def test_reserve_event_text(self):
        from shared import unassigned_reserve_schedule as job

        now = datetime(2026, 11, 22, 9, 30, tzinfo=TZ)
        ev = job.build_calendar_event("台北", [
            {"success": True, "service_date": "2027-01-23", "group": "上午", "period": "09:00-12:00", "person": 2, "order_no": "LC1"},
            {"success": False, "service_date": "2027-01-25", "group": "全天", "message": "後台查不到可預約人力"},
            {"success": False, "service_date": "2027-01-26", "group": "下午", "message": "已無未配班專員"},
        ], "2027-01-22", "2027-02-04", now)
        self.assertEqual(ev["summary"], "【未配班保留單】台北 成立 1 張、未成立 1 個時段（11/22）")
        self.assertIn("✅ 2027-01-23 上午 09:00-12:00 2人 LC1", ev["description"])
        self.assertIn("❌ 2027-01-25 全天：後台查不到可預約人力", ev["description"])
        self.assertNotIn("已無未配班專員", ev["description"])

    def test_missing_calendar_does_not_fail(self):
        from shared import unassigned_reserve_schedule as job

        self.assertTrue(job.write_calendar({}, calendar_ids=())[0].startswith("⚠️ 尚未設定排程行事曆"))


if __name__ == "__main__":
    unittest.main()
