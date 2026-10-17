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


class YearRootSwitchTest(unittest.TestCase):
    def test_root_mode_without_configured_id(self):
        with patch.object(c, "_secret_value", lambda key, default="": default), \
             patch.object(host, "region_sheet", None), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: sid or "ROOT-2027"):
            self.assertEqual(c._sheet_config("台北")["spreadsheet_id"], "ROOT-2027")

    def test_switched_file_drops_old_gid(self):
        secrets = {"CHANGE_ORDER_TAIPEI_SPREADSHEET_ID": "OLD", "CHANGE_ORDER_TAIPEI_GID": "123"}
        with patch.object(c, "_secret_value", lambda key, default="": secrets.get(key, default)), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: "NEW"):
            config = c._sheet_config("台北")
        self.assertEqual((config["spreadsheet_id"], config["gid"]), ("NEW", None))
        with patch.object(c, "_secret_value", lambda key, default="": secrets.get(key, default)), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: sid):
            self.assertEqual(c._sheet_config("台北")["gid"], 123)

    def test_missing_everywhere_raises(self):
        with patch.object(c, "_secret_value", lambda key, default="": default), \
             patch.object(host, "region_sheet", None), \
             patch.object(c, "_year_root_id", lambda kind, region, sid: sid):
            with self.assertRaises(ValueError):
                c._sheet_config("台北")

    def test_atm_switched_file_uses_title(self):
        secrets = {"ATM_TAIPEI_SPREADSHEET_ID": "OLD", "ATM_TAIPEI_GID": "5"}
        with patch.object(atm, "_secret_text", lambda key: secrets.get(key, "")), \
             patch.object(atm, "_year_root_id", lambda kind, region, sid: "NEW"):
            config = atm._atm_sheet_config("台北")
        self.assertEqual((config["spreadsheet_id"], config["gid"]), ("NEW", None))


class WorksheetByNameTest(unittest.TestCase):
    class Sheet:
        def __init__(self, tabs):
            self.tabs = tabs  # {title: id}

        def worksheet(self, title):
            if title not in self.tabs:
                import gspread
                raise gspread.exceptions.WorksheetNotFound(title)
            return ("ws", title)

        def worksheets(self):
            from types import SimpleNamespace
            return [SimpleNamespace(id=i, title=t) for t, i in self.tabs.items()]

        def get_worksheet(self, index):
            return ("first", index)

        def get_worksheet_by_id(self, gid):
            return next((("ws", t) for t, i in self.tabs.items() if i == gid), None)

    def test_change_order_prefers_tab_name_over_gid(self):
        sheet = self.Sheet({"其他": 1, "清潔異動": 2})
        client = type("C", (), {"open_by_key": lambda self, key: sheet})()
        with patch.object(c, "_sheet_config", lambda region: {"spreadsheet_id": "X", "gid": 1, "worksheet_title": "清潔異動"}), \
             patch.object(c, "_get_gspread_client", lambda: client):
            self.assertEqual(c.get_worksheet("台北"), ("ws", "清潔異動"))

    def test_change_order_missing_tab_raises(self):
        sheet = self.Sheet({"其他": 1})
        client = type("C", (), {"open_by_key": lambda self, key: sheet})()
        with patch.object(c, "_sheet_config", lambda region: {"spreadsheet_id": "X", "gid": 5, "worksheet_title": "清潔異動"}), \
             patch.object(c, "_get_gspread_client", lambda: client):
            with self.assertRaises(RuntimeError):
                c.get_worksheet("台北")

    def test_atm_prefers_tab_name_then_gid(self):
        cfg = {"spreadsheet_id": "X", "gid": 9, "worksheet_title": "ATM"}
        with patch.object(atm, "_atm_sheet_config", lambda region: cfg), \
             patch.object(atm, "get_atm_spreadsheet", lambda sid: self.Sheet({"ATM": 3, "舊": 9})):
            self.assertEqual(atm.get_atm_worksheet("台北"), ("ws", "ATM"))
        with patch.object(atm, "_atm_sheet_config", lambda region: cfg), \
             patch.object(atm, "get_atm_spreadsheet", lambda sid: self.Sheet({"改名的ATM": 9})):
            self.assertEqual(atm.get_atm_worksheet("台北"), ("ws", "改名的ATM"))
        with patch.object(atm, "_atm_sheet_config", lambda region: cfg), \
             patch.object(atm, "get_atm_spreadsheet", lambda sid: self.Sheet({"其他": 1})):
            with self.assertRaises(ValueError):
                atm.get_atm_worksheet("台北")


class WeekdayPricingTest(unittest.TestCase):
    def test_national_holiday_on_weekday_is_weekday_price(self):
        # 2026-10-09（週五）國慶連假補假日：價格仍算平日
        result = c.calc_time_change_fee(date(2026, 10, 9), 1, 1)
        self.assertFalse(result["is_weekend"])
        self.assertTrue(result["calc_note"].startswith("平日"))
        self.assertTrue(c.calc_time_change_fee(date(2026, 10, 10), 1, 1)["is_weekend"])


if __name__ == "__main__":
    unittest.main()
