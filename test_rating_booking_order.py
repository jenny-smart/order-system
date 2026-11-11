# -*- coding: utf-8 -*-
"""評價預約成單：日期判讀（各約一單／擇一）、時段沿用與大掃除至少 3 小時、成單流程、寫回。"""
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from shared import rating_booking_order as rbo

TODAY = date(2026, 11, 12)
ADDR = "台北市測試區測試路1號2樓"
LAST = {"order_no": "LC001", "date": "2026-10-01", "time": "09:00 - 11:00", "address": ADDR,
        "clean_type": "居家清潔", "payway": "信用卡", "person": "2", "hour": "2"}
PEAK = {"enabled": True, "periods": {
    "normal": {"start": "", "end": ""},
    "part1": {"start": "2026-12-01", "end": "2027-01-15"},
    "part2": {"start": "2027-01-16", "end": "2027-02-14"}}}


def dates(groups):
    return [[c["date"].isoformat() if c["date"] else None for c in g] for g in groups]


class ParseDatesTest(unittest.TestCase):
    def parse(self, f, g=""):
        return rbo.parse_row(f, g, TODAY)

    def test_list_is_one_order_each_and_or_is_pick_one(self):
        p = self.parse("12/3、12/23、1/6、1/19、2/2或2/3、2/12、2/26 下午")
        self.assertEqual(dates(p["groups"]), [["2026-12-03"], ["2026-12-23"], ["2027-01-06"], ["2027-01-19"],
                                              ["2027-02-02", "2027-02-03"], ["2027-02-12"], ["2027-02-26"]])
        self.assertEqual(p["hints"]["half"], "PM")
        self.assertEqual(p["note"], "")

    def test_range_is_pick_one(self):
        self.assertEqual(dates(self.parse("12/2-12/4")["groups"]), [["2026-12-02", "2026-12-03", "2026-12-04"]])
        self.assertEqual(dates(self.parse("7/13-17")["groups"])[0][-1], "2027-07-17")

    def test_dot_separated_days_are_pick_one(self):
        self.assertEqual(dates(self.parse("1/23.24.30.31")["groups"]),
                         [["2027-01-23", "2027-01-24", "2027-01-30", "2027-01-31"]])

    def test_comma_separated_days_are_one_order_each(self):
        self.assertEqual(dates(self.parse("5/18、21、25、28 早上")["groups"]),
                         [["2027-05-18"], ["2027-05-21"], ["2027-05-25"], ["2027-05-28"]])

    def test_compact_and_iso_dates(self):
        self.assertEqual(dates(self.parse("待約1203")["groups"]), [["2026-12-03"]])
        p = self.parse("2027-01-10 14:00-17:00", "14-17")
        self.assertEqual(dates(p["groups"]), [["2027-01-10"]])
        self.assertEqual(p["hints"]["period"], "14:00-17:00")

    def test_month_only_has_no_date(self):
        for text in ("12月", "1月底"):
            self.assertEqual(dates(self.parse(text)["groups"]), [[None]], text)
        self.assertTrue(self.parse("")["skip"])
        p = self.parse("1/30或2月", "4小")
        self.assertEqual(dates(p["groups"]), [["2027-01-30", None]])
        self.assertEqual(p["hints"]["hour"], 4)

    def test_changed_date_uses_the_later_one(self):
        self.assertEqual(dates(self.parse("11/28改12/5")["groups"]), [["2026-12-05"]])

    def test_recent_past_date_stays_this_year(self):
        self.assertEqual(dates(self.parse("11/5")["groups"]), [["2026-11-05"]])

    def test_marked_rows_are_skipped(self):
        self.assertIn("已約", self.parse("2026-12-16 08:30-12:30", "已約12/30")["skip"])
        self.assertIn("詢問中", self.parse("12/20", "詢問中")["skip"])

    def test_time_column_formats(self):
        for text, period in (("09-12", "09:00-12:00"), ("0830-1230", "08:30-12:30"), ("1400-1700", "14:00-17:00"),
                             ("09-16", "09:00-16:00"), ("0900-1800", "09:00-18:00")):
            self.assertEqual(rbo.parse_hints(text)["period"], period)
        self.assertEqual({k: rbo.parse_hints("3人8小")[k] for k in ("person", "hour")}, {"person": 3, "hour": 8})

    def test_unreadable_text_is_kept_as_note(self):
        self.assertEqual(self.parse("4/2 2女")["note"], "2女")
        self.assertTrue(self.parse("6/2 或6/16 下4 或6/17 全天")["note"])  # 時段寫在個別日期後面，無法判斷


class ResolveSlotTest(unittest.TestCase):
    def test_uses_last_order_when_sheet_is_blank(self):
        self.assertEqual(rbo.resolve_slot({}, LAST, False)["period"], "09:00-11:00")

    def test_peak_raises_inherited_hours_to_three(self):
        slot = rbo.resolve_slot({}, LAST, True)
        self.assertEqual((slot["period"], slot["hour"]), ("09:00-12:00", 3))
        self.assertIn("3 小時", slot["adjusted"])
        self.assertEqual(rbo.resolve_slot({"half": "PM"}, LAST, True)["period"], "14:00-17:00")

    def test_peak_rejects_written_two_hours(self):
        for hints in ({"period": "09:00-11:00"}, {"hour": 2}):
            with self.assertRaises(rbo.PlanError):
                rbo.resolve_slot(hints, LAST, True)

    def test_written_values_win(self):
        self.assertEqual(rbo.resolve_slot({"period": "14:00-18:00"}, LAST, True)["hour"], 4)
        slot = rbo.resolve_slot({"person": 3, "hour": 8}, LAST, True)
        self.assertEqual((slot["period"], slot["person"]), ("09:00-18:00", 3))
        self.assertEqual(rbo.resolve_slot({"hour": 4}, LAST, False)["period"], "08:30-12:30")

    def test_non_standard_is_rejected(self):
        for hints in ({"period": "10:00-12:00"}, {"hour": 5}, {"half": "FULL"}, {"half": "PM", "hour": 8}):
            with self.assertRaises(rbo.PlanError):
                rbo.resolve_slot(hints, LAST, False)


def make_ctx():
    return {"region": "台北", "env": "prod", "session": MagicMock(), "base_url": "https://b", "today": TODAY,
            "pricing": PEAK}


def customer():
    return {"lookup": {"phone": "0900000000", "session": MagicMock()}, "address": ADDR, "last": LAST,
            "payway": "信用卡", "clean_type": "居家清潔", "clean_type_id": "1"}


def row(f, g="", order="", phone="0900000000", address=ADDR, n=230):
    return {"row": n, "order": order, "name": "測試客", "phone": phone, "address": address,
            "date_text": f, "time_text": g}


class PlanRowTest(unittest.TestCase):
    def plan(self, r):
        with patch.object(rbo, "load_customer", return_value=customer()):
            return rbo.plan_row(make_ctx(), r)

    def test_ready_row_in_peak_gets_three_hours(self):
        plan = self.plan(row("2026-12-18"))
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["groups"][0][0]["slot"]["period"], "09:00-12:00")

    def test_reasons(self):
        self.assertEqual(self.plan(row("12/3", order="LC009"))["status"], "skip")
        self.assertIn("沒有確切日期", self.plan(row("12月"))["reason"])
        self.assertIn("沒有電話", self.plan(row("2026-12-18", phone=""))["reason"])
        self.assertIn("日期已過", self.plan(row("11/5"))["reason"])
        self.assertIn("2女", self.plan(row("12/20 2女"))["reason"])

    def test_or_row_keeps_bookable_dates_when_one_is_month_only(self):
        plan = self.plan(row("1/30或2月", "4小"))
        self.assertEqual(plan["status"], "ready")
        self.assertEqual([bool(c["slot"]) for c in plan["groups"][0]], [True, False])

    def test_customer_lookup_failure_is_reported(self):
        with patch.object(rbo, "load_customer", side_effect=rbo.PlanError("這支電話在後台查無會員")):
            self.assertIn("查無會員", rbo.plan_row(make_ctx(), row("12/20"))["reason"])


class BookGroupTest(unittest.TestCase):
    def group(self, text, g=""):
        with patch.object(rbo, "load_customer", return_value=customer()):
            return rbo.plan_row(make_ctx(), row(text, g))["groups"][0]

    def book(self, group, available, lemon=False, existing=None, create=None):
        qo = MagicMock()
        qo.quick_check_available_slots.side_effect = [[{"available": a}] for a in available]
        qo.quick_create_order.side_effect = create or (lambda **kw: {"order_no": "LC777"})
        with patch.dict("sys.modules", {"quick_order": qo}), \
                patch.object(rbo, "_existing_orders", return_value=existing or {}):
            return rbo.book_group(make_ctx(), customer(), group, lemon), qo

    def test_or_books_first_date_with_a_slot(self):
        out, qo = self.book(self.group("12/2-12/4"), [False, True])
        self.assertEqual(out["order_no"], "LC777")
        self.assertIn("2026-12-03（四） 09:00-12:00 2人3小時", out["text"])
        kwargs = qo.quick_create_order.call_args.kwargs
        self.assertEqual((kwargs["date_s"], kwargs["period_s"], kwargs["payway"]), ("2026-12-03", "09:00-12:00", "信用卡"))
        self.assertFalse(kwargs["allow_auto_lemon_shift"])
        self.assertEqual(qo.quick_create_order.call_count, 1)

    def test_no_slot_reports_every_date_and_does_not_use_lemon_by_default(self):
        out, qo = self.book(self.group("12/2-12/4"), [False, False, False])
        self.assertEqual(out["order_no"], "")
        self.assertEqual(out["text"].count("無時段"), 3)
        qo.quick_create_order.assert_not_called()

    def test_lemon_is_used_only_when_allowed(self):
        out, qo = self.book(self.group("12/2-12/4"), [False, False, False], lemon=True)
        self.assertEqual(out["order_no"], "LC777")
        self.assertTrue(qo.quick_create_order.call_args.kwargs["allow_auto_lemon_shift"])

    def test_existing_order_is_not_booked_again(self):
        out, qo = self.book(self.group("12/2-12/4"), [True], existing={"2026-12-03": "LC555"})
        self.assertEqual(out["order_no"], "")
        self.assertIn("LC555", out["text"])
        qo.quick_create_order.assert_not_called()

    def test_failure_after_submit_stops_without_trying_other_dates(self):
        def boom(**kw):
            raise RuntimeError("找不到新訂單編號")
        out, qo = self.book(self.group("12/2-12/4"), [True, True], create=boom)
        self.assertEqual(out["order_no"], "")
        self.assertIn("請到後台確認", out["text"])
        self.assertEqual(qo.quick_create_order.call_count, 1)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.ws = MagicMock()
        blank = [""] * 12
        self.values = [blank] * 229 + [
            ["", "", "甲", "0900000000", ADDR, "12/3、12/23", "下午"],
            ["", "", "乙", "0900000001", ADDR, "12月", ""],
            ["LC1", "", "丙", "0900000002", ADDR, "12/5", ""],
            ["", "", "大掃除預約"],
        ]
        self.ws.get.return_value = self.values

    def run_it(self, **kw):
        with patch.object(rbo, "load_customer", return_value=customer()), \
                patch.object(rbo, "book_group", side_effect=[{"order_no": "LC10", "text": "成單 A"},
                                                             {"order_no": "LC11", "text": "成單 B"}]), \
                patch("memo_system.memo.with_retry", side_effect=lambda fn, *a, **k: fn(*a, **k)):
            return rbo.run("台北", "230-233", ctx=make_ctx(), ws=self.ws, logger=lambda *a, **k: None, **kw)

    def test_writes_order_numbers_to_a_and_result_to_l(self):
        summary = self.run_it()
        self.assertEqual((summary["orders"], summary["booked_rows"], summary["failed_rows"], summary["skipped_rows"]),
                         (2, 1, 1, 2))
        first, second = [c.args[0] for c in self.ws.batch_update.call_args_list]
        self.assertEqual(first, [{"range": "L230", "values": [["[11/12] 成單 A\n成單 B"]]},
                                 {"range": "A230", "values": [["LC10+LC11"]]}])
        self.assertEqual([u["range"] for u in second], ["L231"])
        self.assertIn("無法成單", second[0]["values"][0][0])

    def test_dry_run_and_dev_do_not_write(self):
        summary = self.run_it(dry_run=True)
        self.assertEqual((summary["ready_rows"], summary["failed_rows"]), (1, 1))
        self.ws.batch_update.assert_not_called()
        self.run_it(env="dev")
        self.ws.batch_update.assert_not_called()


class BackendLookupTest(unittest.TestCase):
    def setUp(self):
        self.qo = MagicMock()
        self.qo.get_member.return_value = {"member": {"name": "測試客", "memberAddressList": [
            {"address": "新北市別處路9號"}, {"address": "臺北市測試區測試路1號2樓"}]}}
        self.qo.get_customer_paid_orders.return_value = [
            dict(LAST, order_no="LC900", date="2026-12-30", address="臺北市測試區測試路1號2樓"),
            dict(LAST, order_no="LC800", date="2026-10-20", address="臺北市測試區測試路1號2樓", payway="ATM"),
            dict(LAST, order_no="LC700", date="2026-11-01", address="新北市別處路9號"),
        ]

    def load(self, address=ADDR):
        with patch.dict("sys.modules", {"quick_order": self.qo}):
            return rbo.load_customer(make_ctx(), "0900000000", address)

    def test_uses_latest_served_order_at_the_same_address(self):
        c = self.load()
        self.assertEqual((c["last"]["order_no"], c["payway"], c["address"]),
                         ("LC800", "ATM", "臺北市測試區測試路1號2樓"))

    def test_reasons_when_nothing_to_copy(self):
        with self.assertRaisesRegex(rbo.PlanError, "留存地址"):
            self.load("台北市沒有這個地址")
        self.qo.get_customer_paid_orders.return_value = []
        with self.assertRaisesRegex(rbo.PlanError, "沒有上一張"):
            self.load()
        self.qo.get_member.return_value = None
        with self.assertRaisesRegex(rbo.PlanError, "查無會員"):
            self.load()

    def test_existing_orders_ignore_cancelled_and_other_addresses(self):
        self.qo._order_blocks_for_dates.return_value = [
            {"order_no": "LC1", "lines": ["2026-12-03 (四) 09:00 - 12:00", ADDR, "已取消"]},
            {"order_no": "LC2", "lines": ["2026-12-03 (四) 09:00 - 12:00", "新北市別處路9號"]},
            {"order_no": "LC3", "lines": ["2026-12-04 (五) 09:00 - 12:00", ADDR]},
        ]
        self.qo._parse_service_date_time_loose.side_effect = lambda text: (text[:10], "")
        with patch.dict("sys.modules", {"quick_order": self.qo}):
            found = rbo._existing_orders(make_ctx(), customer(), [date(2026, 12, 3), date(2026, 12, 4)])
        self.assertEqual(found, {"2026-12-04": "LC3"})


class HelperTest(unittest.TestCase):
    def test_loose_address(self):
        self.assertEqual(rbo.loose_address("242 臺北市測試路30號8F之3"), rbo.loose_address("台北市測試路30號8樓-3"))

    def test_parse_rows(self):
        self.assertEqual(rbo.parse_rows("230,233，240-242"), [230, 233, 240, 241, 242])
        with self.assertRaises(ValueError):
            rbo.parse_rows("")


if __name__ == "__main__":
    unittest.main()
