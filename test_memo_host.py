import unittest
from datetime import date
from unittest.mock import patch

from memo_system import atm, change_order as c, host


class MemoHostFallbackTest(unittest.TestCase):
    def setUp(self):
        self.saved = (host.region_sheet, host.service_account, host.regions)

    def tearDown(self):
        host.region_sheet, host.service_account, host.regions = self.saved

    def test_change_order_ignores_secrets_and_host_sheet(self):
        host.region_sheet = lambda kind, region: {"spreadsheet_id": "host", "gid": 7}
        calls = []
        with patch.object(c, "_secret_value", lambda key, default="": "secret"), \
             patch("year_roots.root_file_id", lambda cat, area: calls.append((cat, area)) or f"ROOT-{area}"):
            config = c._sheet_config("台北")
            self.assertEqual(c._sheet_config("桃園")["spreadsheet_id"], "ROOT-桃園")
        self.assertEqual(config, {"spreadsheet_id": "ROOT-台北", "gid": None, "worksheet_title": "清潔異動"})
        self.assertEqual(calls, [("內勤工作表單", "台北"), ("服務異動", "桃園")])

    def test_change_order_root_missing_raises(self):
        def missing(cat, area):
            raise FileNotFoundError("找不到")
        with patch("year_roots.root_file_id", missing):
            with self.assertRaises(FileNotFoundError):
                c._sheet_config("台北")

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

    def _get(self, tabs):
        sheet = self.Sheet(tabs)
        sheet.title = "測試檔"
        client = type("C", (), {"open_by_key": lambda self, key: sheet})()
        with patch.object(c, "_sheet_config", lambda region: {"spreadsheet_id": "X", "gid": None, "worksheet_title": "清潔異動"}), \
             patch.object(c, "_get_gspread_client", lambda: client):
            return c.get_worksheet("台北")

    def test_change_order_finds_tab_by_name(self):
        self.assertEqual(self._get({"其他": 1, "清潔異動": 2}).title, "清潔異動")
        # 桃園／新竹服務異動檔：沒有「清潔異動」時用唯一的「訂單金流…異動表」
        self.assertEqual(self._get({"2026訂單金流(加減時/儲值金/其他)異動表": 5, "2025客戶退款": 0}).title,
                         "2026訂單金流(加減時/儲值金/其他)異動表")

    def test_change_order_missing_tab_raises(self):
        with self.assertRaises(RuntimeError):
            self._get({"其他": 0})
        with self.assertRaises(RuntimeError):  # 兩個候選分頁時不猜
            self._get({"2026訂單金流異動表": 1, "2027訂單金流異動表": 2})

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
