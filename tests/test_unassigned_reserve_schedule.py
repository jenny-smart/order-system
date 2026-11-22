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
            out = job.run(today=date(2026, 11, 22), run_region=fake, log=lambda _t: None)
        self.assertEqual(seen, [("台北", "2027-01-22", "2027-02-04")])
        self.assertEqual(out["result"]["台北"]["results"][0]["order_no"], "LC1")

    def test_after_range_does_nothing(self):
        out = job.run(today=date(2027, 3, 1), run_region=lambda *a: self.fail("不應執行"), log=lambda _t: None)
        self.assertIsNone(out["range"])


if __name__ == "__main__":
    unittest.main()
