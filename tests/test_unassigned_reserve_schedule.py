# -*- coding: utf-8 -*-
"""未配班成立保留單排程：固定區間、地址、彙總。"""
import unittest
from datetime import date
from unittest.mock import patch

from shared import unassigned_reserve_schedule as job


class RangeTest(unittest.TestCase):
    def test_default_range(self):
        with patch.dict("os.environ", {"UNASSIGNED_RESERVE_START": "", "UNASSIGNED_RESERVE_END": ""}):
            self.assertEqual(job.date_range(date(2026, 11, 22)), ("2027-01-22", "2027-02-04"))

    def test_starts_tomorrow_inside_range_and_skips_after(self):
        self.assertEqual(job.date_range(date(2027, 1, 25)), ("2027-01-26", "2027-02-04"))
        self.assertIsNone(job.date_range(date(2027, 2, 4)))

    def test_slash_dates_accepted(self):
        with patch.dict("os.environ", {"UNASSIGNED_RESERVE_START": "2027/01/22", "UNASSIGNED_RESERVE_END": "2027/2/4"}):
            self.assertEqual(job.date_range(date(2026, 11, 22)), ("2027-01-22", "2027-02-04"))
        with self.assertRaises(ValueError):
            job.parse_day("1/22")

    def test_variable_override(self):
        with patch.dict("os.environ", {"UNASSIGNED_RESERVE_START": "2027-01-10", "UNASSIGNED_RESERVE_END": "2027-01-12"}):
            self.assertEqual(job.date_range(date(2026, 11, 22)), ("2027-01-10", "2027-01-12"))


class AddressTest(unittest.TestCase):
    def test_pick_region_keep_address(self):
        addrs = ["台中市北區館前路19號4樓", "台北市大安區信義路四段210號4樓"]
        self.assertEqual(job.pick_address("台北", addrs), "台北市大安區信義路四段210號4樓")
        self.assertEqual(job.pick_address("台中", addrs), "台中市北區館前路19號4樓")
        with self.assertRaises(RuntimeError):
            job.pick_address("台北", ["台中市北區館前路19號4樓"])


class RunTest(unittest.TestCase):
    def test_run_passes_range_and_logs(self):
        seen = []

        def fake(env, region, email, pw, s, e, log):
            seen.append((region, s, e))
            return [{"service_date": "2027-01-22", "group": "上午", "success": True, "order_no": "LC1", "person": 2}]

        with patch.dict("accounts.ACCOUNTS", {"台北": {"email": "a", "password": "b"}}), patch.object(job, "_log"):
            out = job.run(today=date(2026, 11, 22), run_region=fake, log=lambda _t: None, settings={})
        self.assertEqual(seen, [("台北", "2027-01-22", "2027-02-04")])
        self.assertEqual(out["result"]["台北"]["results"][0]["order_no"], "LC1")

    def test_after_range_does_nothing(self):
        out = job.run(today=date(2027, 3, 1), run_region=lambda *a: self.fail("不應執行"), log=lambda _t: None,
                      settings={})
        self.assertIsNone(out["range"])


class SettingsTest(unittest.TestCase):
    HEAD = ["執行系統", "執行功能", "地區", "設定項目", "設定值", "啟用"]

    def test_page_settings_override_variable_and_default(self):
        from shared import reserve_settings as rs

        settings = {rs.START_ITEM: "2028/02/01", rs.END_ITEM: "2028/02/14"}
        with patch.dict("os.environ", {"UNASSIGNED_RESERVE_START": "2027-01-10", "UNASSIGNED_RESERVE_END": "2027-01-12"}):
            self.assertEqual(job.date_range(date(2027, 12, 1), settings=settings), ("2028-02-01", "2028-02-14"))
            self.assertEqual(job.date_range(date(2027, 12, 1), "2028-01-05", "2028-01-06", settings),
                             ("2028-01-05", "2028-01-06"))

    def test_stop_day_skips_schedule(self):
        from shared import reserve_settings as rs

        settings = {rs.START_ITEM: "2027/01/22", rs.END_ITEM: "2027/02/04", rs.STOP_ITEM: "2027/01/28"}
        out = job.run(today=date(2027, 1, 28), run_region=lambda *a: self.fail("停止日後不應執行"),
                      log=lambda _t: None, settings=settings)
        self.assertEqual(out["stopped"], "2027-01-28")
        self.assertIsNone(rs.stopped(date(2027, 1, 27), settings))

    def test_parse_and_plan_writes(self):
        from shared import reserve_settings as rs

        values = [self.HEAD,
                  ["訂單系統", "未配班成立保留單", "台北", rs.START_ITEM, "2027/01/22", "TRUE"],
                  ["訂單系統", "未配班成立保留單", "台北", rs.STOP_ITEM, "2027/01/30", "FALSE"]]
        self.assertEqual(rs.parse_settings(values), {rs.START_ITEM: "2027/01/22"})
        updates, appends = rs.plan_writes(values, {rs.START_ITEM: "2028/02/01", rs.END_ITEM: "2028/02/14",
                                                   rs.STOP_ITEM: ""})
        self.assertEqual(updates, [{"range": "E2:F2", "values": [["2028/02/01", "TRUE"]]},
                                   {"range": "E3:F3", "values": [["", "TRUE"]]}])
        self.assertEqual([a[3:5] for a in appends], [[rs.END_ITEM, "2028/02/14"]])

    def test_save_rejects_reversed_range(self):
        from shared import reserve_settings as rs

        with self.assertRaises(ValueError):
            rs.save(date(2028, 2, 14), date(2028, 2, 1), None, worksheet_factory=lambda: self.fail("不應寫入"))


if __name__ == "__main__":
    unittest.main()
