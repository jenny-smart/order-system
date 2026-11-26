# -*- coding: utf-8 -*-
"""未配班檢查頁面設定：排程時間（排程設定 D 欄）、範圍天數（參數設定）。"""
import unittest

from shared import unassigned_settings as us


class FakeWS:
    def __init__(self, values):
        self.values = values
        self.updates, self.appends = [], []

    def get_all_values(self):
        return self.values

    def batch_update(self, updates, value_input_option=None):
        self.updates += updates

    def append_rows(self, rows, value_input_option=None):
        self.appends += rows


class TimeTextTest(unittest.TestCase):
    def test_build(self):
        self.assertEqual(us.build_time_text("區間", "08:30", "17:30", "每小時"), "08:30~17:30 每小時")
        self.assertEqual(us.build_time_text("固定時間", times=["13:30", "08:30"]), "08:30,13:30")

    def test_validate(self):
        for ok in ["08:30~17:30 每小時", "08:30~17:30 每2小時", "09:00~18:00 每30分鐘", "11:10", "08:30,13:30"]:
            self.assertEqual(us.validate_time_text(ok), "", ok)
        for bad in ["", "08:35", "17:30~08:30 每小時", "09:00~18:00 每15分鐘", "abc", "25:00"]:
            self.assertNotEqual(us.validate_time_text(bad), "", bad)

    def test_save_writes_column_d_of_key_row(self):
        ws = FakeWS([["啟用", "功能代號"], ["TRUE", "lemon_ren_count", "x", "11:00"],
                     ["TRUE", "unassigned_staff_record", "y", "08:30~17:30 每小時"]])
        self.assertEqual(us.load_schedule_time("unassigned_staff_record", lambda: ws), "08:30~17:30 每小時")
        us.save_schedule_time("unassigned_staff_record", "09:00~18:00 每2小時", lambda: ws)
        self.assertEqual(ws.updates, [{"range": "D3", "values": [["09:00~18:00 每2小時"]]}])
        with self.assertRaises(ValueError):
            us.save_schedule_time("unassigned_staff_record", "08:35", lambda: ws)
        with self.assertRaises(RuntimeError):
            us.save_schedule_time("nope", "08:30", lambda: ws)


class DaysTest(unittest.TestCase):
    HEAD = ["執行系統", "執行功能", "地區", "項目", "設定值", "啟用", "說明", ""]

    def test_default_and_load(self):
        self.assertEqual(us.load_days(lambda: FakeWS([self.HEAD])), 14)
        ws = FakeWS([self.HEAD, ["訂單系統", "記錄未配班人員", "台北", "範圍天數", "21", "TRUE", "", ""]])
        self.assertEqual(us.load_days(lambda: ws), 21)
        self.assertEqual(us.load_days(lambda: (_ for _ in ()).throw(RuntimeError("x"))), 14)

    def test_save_appends_then_updates(self):
        ws = FakeWS([self.HEAD])
        us.save_days(10, lambda: ws)
        self.assertEqual(ws.appends[0][:6], ["訂單系統", "記錄未配班人員", "台北", "範圍天數", "10", "TRUE"])
        ws2 = FakeWS([self.HEAD, ["訂單系統", "記錄未配班人員", "台北", "範圍天數", "21", "TRUE"]])
        us.save_days(7, lambda: ws2)
        self.assertEqual(ws2.updates, [{"range": "E2:F2", "values": [["7", "TRUE"]]}])
        with self.assertRaises(ValueError):
            us.save_days(0, lambda: ws2)


if __name__ == "__main__":
    unittest.main()
