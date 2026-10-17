import unittest
from unittest.mock import Mock
from shared.member_phone_lookup import backend_keyword, lookup_entries


class LinkBasisTests(unittest.TestCase):
    def setUp(self):
        self.link = 'https://backend.lemonclean.com.tw/member?keyword=%E8%8E%8A%E6%B7%87%E9%88%9E'
        self.member = {'id': 1, 'name': '莊淇鈞', 'phone': '0912345678', 'line': 'https://lin.ee/customer'}
        self.client = Mock()
        self.client.search.return_value = ([self.member], True)

    def test_backend_link_uses_decoded_keyword_not_display_name(self):
        rows = lookup_entries(self.client, [{'name': '別名', 'line': self.link}], basis='backend')
        self.client.search.assert_called_once_with('莊淇鈞')
        self.assertEqual(rows[0]['手機號碼'], '0912345678')
        self.assertEqual(rows[0]['會員姓名'], '莊淇鈞')
        self.assertEqual(rows[0]['查詢姓名'], '別名')
        self.assertNotIn('LINE 不符', rows[0]['比對狀態'])

    def test_invalid_and_unbounded_links_never_search(self):
        for link in ['https://evil.test/member?keyword=x',
                     'https://backend.lemonclean.com.tw/member?keyword=',
                     'https://backend.lemonclean.com.tw/member?keyword=a&keyword=b',
                     'https://backend.lemonclean.com.tw/member/edit/1',
                     'https://lin.ee/test']:
            rows = lookup_entries(self.client, [{'name': '甲', 'line': link}], basis='backend')
            self.assertEqual(rows[0]['手機號碼'], '')
        self.client.search.assert_not_called()

    def test_wrong_mode_gives_actionable_message(self):
        rows = lookup_entries(self.client, [{'name': '甲', 'line': self.link}], basis='line')
        self.client.search.assert_not_called()
        self.assertIn('後台會員連結', rows[0]['比對狀態'])

    def test_backend_link_same_name_remains_ambiguous(self):
        self.client.search.return_value = ([self.member, dict(self.member, id=2, phone='0987654321')], True)
        rows = lookup_entries(self.client, [{'name': '莊淇鈞', 'line': self.link}], basis='backend')
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('多筆' in r['比對狀態'] for r in rows))

    def test_no_link_fallback_is_labeled(self):
        rows = lookup_entries(self.client, [{'name': '莊淇鈞', 'line': ''}], basis='backend')
        self.assertIn('無連結，改以姓名', rows[0]['比對狀態'])

    def test_phone_keyword_matches_phone(self):
        rows = lookup_entries(self.client, [{'name': '姓名', 'line': 'https://backend.lemonclean.com.tw/member?keyword=0912345678'}], basis='backend')
        self.assertEqual(rows[0]['會員姓名'], '莊淇鈞')
        self.assertEqual(rows[0]['手機號碼'], '0912345678')


if __name__ == '__main__':
    unittest.main()
