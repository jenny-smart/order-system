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
