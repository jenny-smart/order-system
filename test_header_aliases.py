import unittest
from unittest.mock import MagicMock, patch

import orders
from shared import gsheet

SCHEDULE_HEADERS = ["服務人時", "備註", "姓名", "電話", "地址", "日期", "開始時間", "結束時間", "狀態", "購買項目",
                    "簡訊實際服務時間", "客人備註", "訂單編號", "結果", "原因", "沒班表日", "餘額不足", "確認信",
                    "日曆改色結果", "日曆改色內容", "日曆原色", "日曆新色", "每月確認", "服務人員", "服務狀態", "車馬費",
                    "客服備註", "代客保留"]


class HeaderAliasTest(unittest.TestCase):
    def test_writeback_uses_existing_short_columns_and_adds_nothing(self):
        ws = MagicMock()
        ws.row_values.return_value = list(SCHEDULE_HEADERS)
        orders.update_sheet_rows(ws, {5: {"結果": "失敗", "沒班表日期": "2027/01/05", "餘額不足未送": "2027/01/12",
                                          "日曆改色原因": "找不到對應日曆事件"}})
        ws.resize.assert_not_called()
        ranges = {u["range"]: u["values"][0][0] for call in ws.batch_update.call_args_list for u in call.args[0]}
        self.assertEqual(ranges["P5"], "2027/01/05")
        self.assertEqual(ranges["Q5"], "2027/01/12")
        self.assertEqual(ranges["T5"], "找不到對應日曆事件")

    def test_reader_sees_short_columns_under_long_names(self):
        ws = MagicMock()
        ws.get_all_values.return_value = [SCHEDULE_HEADERS, [""] * 15 + ["2027/01/05"] + [""] * 12]
        client = MagicMock()
        client.open_by_key.return_value.worksheet.return_value = ws
        with patch.object(gsheet, "build_gsheet_client", return_value=client):
            _, df = orders.load_worksheet("s")
        self.assertEqual(df.iloc[0]["沒班表日期"], "2027/01/05")


if __name__ == "__main__":
    unittest.main()
