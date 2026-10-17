import unittest
from unittest.mock import Mock, patch
from shared.member_phone_lookup import load_sheet_entries, load_sheet_columns


class SheetColumnTests(unittest.TestCase):
    def test_independent_columns_preserve_row_alignment(self):
        book, ws = Mock(), Mock(title='客戶名單', row_count=100, col_count=10)
        book.fetch_sheet_metadata.side_effect = [
            {'sheets': [{'data': [{'startRow': 9, 'rowData': [
                {'values': [{'formattedValue': '甲'}]}, {}, {'values': [{'formattedValue': '乙'}]},
            ]}]}]},
            {'sheets': [{'data': [{'startRow': 9, 'rowData': [
                {'values': [{'formattedValue': 'https://lin.ee/a'}]}, {},
                {'values': [{'formattedValue': 'https://lin.ee/b'}]},
            ]}]}]},
        ]
        with patch('shared.member_phone_lookup.open_sheet_target', return_value=(book, ws)):
            rows = load_sheet_entries('url', 10, 12, 'B', 'G')
        self.assertEqual([(r['source'], r['name'], r['line']) for r in rows], [
            ('10', '甲', 'https://lin.ee/a'), ('12', '乙', 'https://lin.ee/b')])
        self.assertEqual([c.kwargs['params']['ranges'] for c in book.fetch_sheet_metadata.call_args_list],
                         ["'客戶名單'!B10:B12", "'客戶名單'!G10:G12"])

    def test_headers_include_empty_columns(self):
        ws = Mock(title='客戶', row_count=50, col_count=4)
        ws.get.return_value = [['日期', '', '姓名']]
        with patch('shared.member_phone_lookup.open_sheet_target', return_value=(Mock(), ws)):
            schema = load_sheet_columns('url', 3)
        self.assertEqual(schema['columns'], {'A': '日期', 'B': '', 'C': '姓名', 'D': ''})
        ws.get.assert_called_once_with('A3:D3')

    def test_bounds_prevent_data_read(self):
        book, ws = Mock(), Mock(title='客戶', row_count=5, col_count=2)
        with patch('shared.member_phone_lookup.open_sheet_target', return_value=(book, ws)):
            with self.assertRaises(ValueError):
                load_sheet_entries('url', 2, 4, 'C')
        book.fetch_sheet_metadata.assert_not_called()


if __name__ == '__main__':
    unittest.main()


class OpenSheetTargetTabNameTest(unittest.TestCase):
    def _open(self, titles, url='https://docs.google.com/spreadsheets/d/abc/edit'):
        import sys
        import types
        from types import SimpleNamespace
        import shared.member_phone_lookup as mpl

        book = Mock()
        book.worksheets.return_value = [SimpleNamespace(title=t) for t in titles]
        book.worksheet.side_effect = lambda title: ('ws', title)
        book.get_worksheet_by_id.side_effect = lambda gid: ('gid', gid)
        fake_orders = types.ModuleType('orders')
        fake_orders.build_gsheet_client = lambda: Mock(open_by_key=lambda key: book)
        with patch.dict(sys.modules, {'orders': fake_orders}):
            return mpl.open_sheet_target(url)[1]

    def test_without_gid_uses_named_tab(self):
        self.assertEqual(self._open(['ATM', '評價預約']), ('ws', '評價預約'))
        self.assertEqual(self._open(['評價預約'], 'https://docs.google.com/spreadsheets/d/abc/edit#gid=5'), ('gid', 5))
        with self.assertRaises(ValueError):
            self._open(['ATM'])
