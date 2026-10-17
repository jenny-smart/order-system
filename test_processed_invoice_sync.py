import unittest
from unittest.mock import Mock, patch

from memo_system import change_order as c


class ProcessedInvoiceSyncTest(unittest.TestCase):
    def _row(self, note="原發票號碼：AA12345678\n新發票號碼：BB12345678"):
        row = [""] * 31
        row[1] = "已處理發票"
        row[6] = "LC00217035"
        row[10] = note
        row[14] = "BB12345678"
        return row

    @patch.object(c, "get_worksheet")
    def test_scans_processed_invoice_row(self, get_worksheet):
        ws = Mock()
        ws.get_all_values.return_value = [["header"], self._row()]
        get_worksheet.return_value = ws

        items = c.get_pending_rows("台北", row_spec="2")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "finance_note")

    def test_only_prepends_finance_note(self):
        item = {"status": "已處理發票", "raw": self._row()}
        form = {"memoFinance": "原本財務備註", "serviceNote": "原本客服備註"}
        controls = {
            "memoFinance": [{"type": "textarea", "context": "財務備註"}],
            "serviceNote": [{"type": "textarea", "context": "客服備註"}],
        }

        c.apply_sheet_row_to_form(form, controls, item)

        self.assertEqual(form["serviceNote"], "原本客服備註")
        self.assertEqual(
            form["memoFinance"],
            "原發票號碼：AA12345678\n新發票號碼：BB12345678\n原本財務備註",
        )


if __name__ == "__main__":
    unittest.main()
