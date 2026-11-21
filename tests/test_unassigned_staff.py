# -*- coding: utf-8 -*-
"""未配班檢查：解析班表、保留計畫（時數取最短）、只剩 1 人、成立保留單人數遞減、排程。"""
import unittest
from datetime import date
from unittest.mock import patch

from shared import unassigned_staff as us
from shared import unassigned_staff_schedule as sch

GREY = 'style="background:#616161"'
HTML = (
    "<table><tr><th>日期</th><th>09:00-11:00</th><th>09:00-12:00</th><th>14:00-16:00</th>"
    "<th>14:00-17:00</th><th>09:00-16:00</th><th>19:00-21:00</th></tr>"
    "<tr><td>11-24<br>(二)</td>"
    f"<td><p {GREY}><span>未配班 1 人</span><span>4王小美3</span></p></td>"
    f"<td><p {GREY}><span>未配班 2 人</span><span>48陳大文2</span><span>6檸檬人40</span></p></td>"
    f"<td><p {GREY}><span>未配班 1 人</span><span>8林阿花5</span></p></td>"
    "<td>10-08<br>客人甲 V<br>4張三三5</td>"
    "<td></td>"
    f"<td><p {GREY}><span>未配班 1 人</span><span>8晚班人3</span></p></td></tr>"
    "<tr><td>11-25<br>(三)</td><td></td><td></td><td></td>"
    f"<td><p {GREY}><span>未配班 2 人</span><span>8林阿花5</span><span>4李四四2</span></p></td>"
    f"<td><p {GREY}><span>未配班 1 人</span><span>4全天哥3</span></p></td><td></td></tr>"
    "</table>"
)


class ParseTest(unittest.TestCase):
    def test_summary_groups_and_excludes_lemon_and_evening(self):
        summary = us.summarize(us.parse_week_unassigned(HTML, "2026-11-23"))
        self.assertEqual(summary[("2026-11-24", "上午")], {"王小美": 2, "陳大文": 3})
        self.assertEqual(summary[("2026-11-24", "下午")], {"林阿花": 2})
        self.assertEqual(summary[("2026-11-25", "下午")], {"林阿花": 3, "李四四": 3})
        self.assertEqual(summary[("2026-11-25", "全天")], {"全天哥": 6})
        self.assertNotIn(("2026-11-24", "晚上"), summary)

    def test_plan_uses_shortest_hours(self):
        plan = us.build_plan(us.summarize(us.parse_week_unassigned(HTML, "2026-11-23")))
        first = plan[0]
        self.assertEqual((first["service_date"], first["group"], first["person"], first["hours"], first["period"]),
                         ("2026-11-24", "上午", 2, 2, "09:00-11:00"))
        self.assertEqual([(p["group"], p["person"], p["period"]) for p in plan[1:]],
                         [("下午", 1, "14:00-16:00"), ("下午", 2, "14:00-17:00"), ("全天", 1, "09:00-16:00")])

    def test_single_left_text(self):
        rows = us.single_left(us.summarize(us.parse_week_unassigned(HTML, "2026-11-23")))
        self.assertEqual([r["text"] for r in rows], ["2026/11/24 下午-1", "2026/11/25 全天-1"])

    def test_scan_range_reads_each_week_once_and_filters(self):
        calls = []
        result = us.scan_range(lambda d: calls.append(d) or HTML, "2026-11-25", "2026-11-25")
        self.assertEqual(calls, ["2026-11-23"])
        self.assertEqual({k[0] for k in result}, {"2026-11-25"})


class CreateReserveTest(unittest.TestCase):
    def test_reduces_person_when_backend_has_fewer(self):
        plan = us.build_plan(us.summarize(us.parse_week_unassigned(HTML, "2026-11-24")))
        plan = [p for p in plan if p["service_date"] == "2026-11-24" and p["group"] == "上午"]
        calls = []

        def stored(env, region, lookup, address, ctype, slots, hour, person="2", extra_fields=None):
            calls.append((tuple(slots), hour, person))
            if person == "2":
                return {"orders": [], "unavailable": list(slots), "not_created": []}
            slot = slots[0]
            d, p = slot.split("_", 1)
            return {"orders": [{"order_no": "LC1", "slot": slot, "date": d, "period_s": p, "staff": "王小美"}],
                    "unavailable": [], "not_created": []}

        logged = []
        results = us.create_reserve_orders(
            env_name="dev", lookup_result={"session": object(), "base_url": "b"}, region="台北", address="x",
            plan=plan, get_html=lambda _d: HTML, create_stored=stored,
            finish=lambda *a: {"customer_memo_ok": True, "order_no": a[2]},
            log_rows=lambda rows, _b: logged.extend(rows))
        self.assertEqual(calls, [(("2026-11-24_09:00-11:00",), "2", "2"), (("2026-11-24_09:00-11:00",), "2", "1")])
        self.assertEqual([(r["success"], r["person"], r["order_no"]) for r in results], [(True, 1, "LC1")])
        self.assertEqual(len(logged), 1)

    def test_stops_when_no_unassigned_left(self):
        plan = [{"service_date": "2026-11-26", "group": "上午", "person": 1}]
        results = us.create_reserve_orders(
            env_name="dev", lookup_result={"session": object(), "base_url": "b"}, region="台北", address="x",
            plan=plan, get_html=lambda _d: HTML, create_stored=lambda *a, **k: self.fail("不應送出"))
        self.assertEqual(results[0]["message"], "已無未配班專員")


class ScheduleTest(unittest.TestCase):
    def _run(self, **kw):
        summary = us.summarize(us.parse_week_unassigned(HTML, "2026-11-23"))
        with patch.dict("accounts.ACCOUNTS", {"台北": {"email": "a", "password": "b"}}), \
             patch("shared.unassigned_staff_schedule._log"):
            return sch.run(today=date(2026, 11, 23), scan=lambda *a: summary, log=lambda _t: None, **kw)

    def test_range_is_next_two_weeks(self):
        self.assertEqual(sch.date_range(date(2026, 11, 23)), ("2026-11-24", "2026-12-07"))

    def test_requires_dedicated_calendar(self):
        with patch.dict("os.environ", {"SCHEDULE_NOTICE_CALENDAR_ID": ""}):
            with self.assertRaises(RuntimeError):
                self._run()

    def test_writes_only_dedicated_calendar(self):
        written = []

        class Svc:
            def events(self):
                return self

            def list(self, **k):
                return self

            def insert(self, calendarId, body, sendUpdates):
                written.append((calendarId, body["summary"], body["description"]))
                return self

            def execute(self):
                return {"items": []}

        with patch.dict("os.environ", {"SCHEDULE_NOTICE_CALENDAR_ID": "notice@group.calendar.google.com"}):
            out = self._run(service_factory=lambda _cid: Svc())
        self.assertEqual([w[0] for w in written], ["notice@group.calendar.google.com"])
        self.assertTrue(written[0][1].startswith("【未配班剩1人】台北 2 個時段"))
        self.assertIn("2026/11/24 下午-1", written[0][2])
        self.assertEqual(len(out["result"]["台北"]["rows"]), 2)


class LemonCountCalendarTest(unittest.TestCase):
    def test_lemon_count_uses_dedicated_calendar_when_set(self):
        from shared import lemon_ren_count_schedule as lrc

        seen = []
        with patch.dict("os.environ", {"SCHEDULE_NOTICE_CALENDAR_ID": "notice@x", "LEMON_REN_COUNT_CALENDAR_IDS": ""}), \
             patch("shared.atm_match_reconcile_schedule._insert_event", side_effect=lambda _s, cid, **_k: seen.append(cid)):
            lrc.write_calendar({}, service_factory=lambda _c: None)
        self.assertEqual(seen, ["notice@x"])


if __name__ == "__main__":
    unittest.main()
