import unittest
from datetime import date
from unittest.mock import patch

from memo_system import atm, change_order as c, host


class MemoHostFallbackTest(unittest.TestCase):
    def setUp(self):
        self.saved = (host.region_sheet, host.service_account, host.regions)

    def tearDown(self):
        host.region_sheet, host.service_account, host.regions = self.saved

    def test_change_order_uses_host_sheet_when_secrets_missing(self):
        host.region_sheet = lambda kind, region: {"spreadsheet_id": f"{kind}-{region}", "gid": 7}
        with patch.object(c, "_secret_value", lambda key, default="": default), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: sid):
            config = c._sheet_config("台北")
        self.assertEqual(config, {"spreadsheet_id": "CHANGE-台北", "gid": 7, "worksheet_title": "清潔異動"})

    def test_secrets_win_over_host(self):
        host.region_sheet = lambda kind, region: {"spreadsheet_id": "host"}
        with patch.object(c, "_secret_value", lambda key, default="": "secret" if key.endswith("SPREADSHEET_ID") else default), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: sid):
            self.assertEqual(c._sheet_config("台北")["spreadsheet_id"], "secret")

    def test_supported_regions_from_host(self):
        host.regions = lambda kind: ["台北", "台中", "火星"]
        self.assertEqual(c.supported_regions(), ["台北", "台中"])

    def test_atm_uses_host_sheet(self):
        host.region_sheet = lambda kind, region: {"spreadsheet_id": f"{kind}-{region}"} if kind == "ATM" else None
        with patch.object(atm, "_secret_text", lambda key: ""), \
             patch.object(atm, "_year_root_id", lambda kind, region, sid: sid):
            self.assertEqual(atm._atm_sheet_config("台中")["spreadsheet_id"], "ATM-台中")

    def test_host_errors_are_ignored(self):
        def boom(*_):
            raise RuntimeError("x")
        host.region_sheet = boom
        host.service_account = boom
        self.assertIsNone(host.lookup_region_sheet("CHANGE", "台北"))
        self.assertIsNone(host.lookup_service_account())


class WeekdayPricingTest(unittest.TestCase):
    def test_national_holiday_on_weekday_is_weekday_price(self):
        # 2026-10-09（週五）國慶連假補假日：價格仍算平日
        result = c.calc_time_change_fee(date(2026, 10, 9), 1, 1)
        self.assertFalse(result["is_weekend"])
        self.assertTrue(result["calc_note"].startswith("平日"))
        self.assertTrue(c.calc_time_change_fee(date(2026, 10, 10), 1, 1)["is_weekend"])


if __name__ == "__main__":
    unittest.main()
