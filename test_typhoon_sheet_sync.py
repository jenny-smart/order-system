import unittest
from unittest.mock import patch

import function.typhoon_sheet_sync as tss
from test_typhoon_transfer import _block


class _Worksheet:
    def __init__(self, values):
        self.values = values
        self.batches = []
        self.updates = []
        self.appended = []

    def get_all_values(self):
        return [list(r) for r in self.values]

    def batch_update(self, data, value_input_option=None):
        self.batches.append((data, value_input_option))

    def update(self, range_name=None, values=None):
        self.updates.append((range_name, values))

    def append_row(self, values, value_input_option=None):
        self.appended.append(values)


class _Client:
    def __init__(self, worksheet):
        self.ws = worksheet

    def open_by_key(self, key):
        client = self

        class Book:
            def worksheet(self, title):
                return client.ws
        return Book()


SETTINGS = {
    "spreadsheet_id": "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0", "worksheet": "颱風",
    "order_col": "A", "orig_date_col": "F", "orig_period_col": "G",
    "new_date_col": "I", "new_period_col": "J",
    "change_date_col": "L", "change_period_col": "M", "start_row": "2",
}
SHEET = [
    ["訂單編號", "姓名", "", "", "", "原日期", "原時段", "服務時數", "新日期", "新時段", "", "異動日期", "異動時段"],
    # 已改到 11/6 → 待填異動
    ["LC00215208", "王璿瑋", "", "", "", "2026-10-23", "08:30-12:30", "4", "2027-03-03", "08:30-12:30", "", "", ""],
    # 和新日期相同、異動欄空白 → 未變動
    ["LC00215218", "余葉菁", "", "", "", "2026-10-23", "14:00-18:00", "4", "2027/3/3", "14:00-18:00", "", "", ""],
    # 查不到 → 查詢失敗
    ["LC00217168", "李憶華", "", "", "", "2026-10-23", "09:00-11:00", "2", "2027-03-01", "09:00-11:00", "", "", ""],
    # 又改回新日期、異動欄還有舊值 → 待清除
    ["LC00217286", "陳世湟", "", "", "", "2026-10-23", "14:00-18:00", "4", "2027-03-01", "14:00-18:00", "", "2026/10/25", "14:00-18:00"],
    # 異動欄已是目前日期 → 已填異動（不寫）
    ["LC00216486", "陳沛希", "", "", "", "2026-10-23", "14:00-17:00", "3", "2027-03-02", "14:00-17:00", "", "2026/10/26", "14:00-17:00"],
    ["", "空白列"],
]


class SettingsTests(unittest.TestCase):
    def test_validate_accepts_url_and_rejects_bad_columns(self):
        settings = tss.validate_settings(SETTINGS)
        self.assertEqual(settings["spreadsheet_id"], "abc123")
        self.assertEqual(tss.column_index("AA"), 26)
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "new_date_col": "1"})
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "new_period_col": "I"})
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "change_date_col": "I"})  # 不可寫到新日期欄
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "change_period_col": "F"})  # 不可寫到原日期欄

    def test_save_then_load_per_account(self):
        ws = _Worksheet([tss.SETTINGS_HEADERS])
        client = _Client(ws)
        tss.save_settings("a@x", SETTINGS, client=client)
        ws.values.append(ws.appended[0])
        loaded = tss.load_settings("a@x", client=client)
        self.assertEqual((loaded["spreadsheet_id"], loaded["worksheet"], loaded["new_date_col"]), ("abc123", "颱風", "I"))
        self.assertEqual(tss.load_settings("b@x", client=client), tss.DEFAULT_SETTINGS)
        tss.save_settings("a@x", {**SETTINGS, "worksheet": "新"}, client=client)
        self.assertEqual(ws.updates[0][0], "A2")


class CompareAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.ws = _Worksheet(SHEET)
        self.client = _Client(self.ws)
        current = {
            "LC00215208": ("2026-11-06", "14:00 - 18:00"),
            "LC00215218": ("2027-03-03", "14:00 - 18:00"),
            "LC00217286": ("2027-03-01", "14:00 - 18:00"),
            "LC00216486": ("2026-10-26", "14:00 - 17:00"),
        }

        def fetch(session, order_no):
            if order_no not in current:
                raise Exception(f"查無訂單：{order_no}")
            return _block(order_no, *current[order_no])

        self.patches = [
            patch.object(tss.tt, "_login", lambda *a: (None, "")),
            patch.object(tss.qo, "_fetch_purchase_block_for_order_no", fetch),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_compare_statuses(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        statuses = [(r["row"], r["status"]) for r in rows]
        self.assertEqual(statuses[0], (2, "待填異動"))
        self.assertEqual(statuses[1], (3, "未變動"))
        self.assertTrue(statuses[2][1].startswith("查詢失敗"))
        self.assertEqual(statuses[3:], [(5, "待清除異動欄"), (6, "已填異動")])
        self.assertEqual(self.ws.batches, [])

    def test_apply_fills_and_clears_only_change_columns(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertEqual([(r["row"], r["status"]) for r in results], [(2, "已填異動"), (5, "已清除異動欄")])
        data, option = self.ws.batches[0]
        self.assertEqual(data, [
            {"range": "L2", "values": [["2026-11-06"]]}, {"range": "M2", "values": [["14:00-18:00"]]},
            {"range": "L5", "values": [[""]]}, {"range": "M5", "values": [[""]]},
        ])
        self.assertEqual(option, "USER_ENTERED")
        self.assertFalse(any(u["range"][0] in "IJ" for u in data))

    def test_apply_skips_change_cells_edited_after_compare(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        self.ws.values[1][11] = "2026-10-30"  # 客服比對後手動填了異動日期
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertEqual(results[0]["status"], "已跳過：比對後異動欄已被修改")
        self.assertEqual([u["range"] for u in self.ws.batches[0][0]], ["L5", "M5"])

    def test_old_settings_row_without_change_columns_still_loads(self):
        old_headers = ["後台帳號", "試算表ID", "工作表名稱", "訂單編號欄", "原日期欄", "原時段欄",
                       "新日期欄", "新時段欄", "起始列", "更新時間"]
        ws = _Worksheet([old_headers, ["a@x", "abc", "颱風", "A", "F", "G", "I", "J", "2", "2026-10-24 09:00"]])
        loaded = tss.load_settings("a@x", client=_Client(ws))
        self.assertEqual((loaded["start_row"], loaded["change_date_col"], loaded["change_period_col"]), ("2", "L", "M"))
        tss.save_settings("a@x", loaded, client=_Client(ws))
        self.assertEqual(ws.updates[0][1][0], tss.SETTINGS_HEADERS)

if __name__ == "__main__":
    unittest.main()
