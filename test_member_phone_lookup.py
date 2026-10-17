import json
import unittest
from unittest.mock import Mock

from shared.member_phone_lookup import (
    MemberClient, cell_link, line_key, lookup_entries, match_entry,
    parse_member_page, parse_pasted, to_tsv,
)


class MemberLookupTests(unittest.TestCase):
    def setUp(self):
        self.entry = {'source': '188', 'name': '王小明', 'line': ''}
        self.member = {'id': 1, 'name': '王小明', 'phone': '0912345678',
                       'line': 'https://chat.line.biz/account/chat/customer-A'}

    def test_same_name_never_selects_first(self):
        rows = match_entry(self.entry, [self.member, dict(self.member, id=2, phone='0987654321')])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('多筆' in r['比對狀態'] for r in rows))

    def test_chat_id_not_official_account_id(self):
        self.assertNotEqual(line_key(self.member['line']), line_key(self.member['line'].replace('customer-A', 'customer-B')))
        entry = dict(self.entry, line=self.member['line'] + '?from=sheet')
        rows = match_entry(entry, [self.member, dict(self.member, id=2, line=self.member['line'].replace('customer-A', 'customer-B'))])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['手機號碼'], '0912345678')
        self.assertEqual(rows[0]['比對狀態'], '姓名＋LINE 相符')

    def test_line_mismatch_does_not_release_name_match_phone(self):
        result = match_entry(dict(self.entry, line='https://lin.ee/different'), [self.member])[0]
        self.assertEqual(result['手機號碼'], '')
        self.assertIn('LINE 不符', result['比對狀態'])

    def test_partial_name_not_an_exact_match(self):
        self.assertEqual(match_entry(dict(self.entry, name='王小'), [self.member])[0]['手機號碼'], '')

    def test_line_only_does_not_scan_database(self):
        client = Mock()
        result = lookup_entries(client, parse_pasted(self.member['line']))
        client.search.assert_not_called()
        self.assertIn('請補姓名', result[0]['比對狀態'])

    def test_hyperlink_sources_and_ambiguity(self):
        self.assertEqual(cell_link({'userEnteredValue': {'formulaValue': '=HYPERLINK("https://lin.ee/abc","小明")'}}), 'https://lin.ee/abc')
        with self.assertRaises(ValueError):
            cell_link({'textFormatRuns': [{'format': {'link': {'uri': 'https://lin.ee/a'}}}, {'format': {'link': {'uri': 'https://lin.ee/b'}}}]})

    def test_script_parsing_discards_sensitive_unneeded_fields(self):
        data = dict(self.member, autoLogin='SECRET', email='private@example.test')
        html = '<script>const app = {memberList: ' + json.dumps([data]) + ', other: 1}</script><ul class="pagination"><a href="?keyword=x&page=2">Next</a></ul>'
        records, pages = parse_member_page(html)
        self.assertEqual(records, [self.member])
        self.assertEqual(pages, [2])
        with self.assertRaises(ValueError):
            parse_member_page('<form action="/login"></form>')

    def test_search_cap_and_name_is_retained(self):
        client = MemberClient.__new__(MemberClient)
        client.base, client.cache, client.session = 'https://example.test', {}, Mock()
        response = Mock(url='https://example.test/member')
        response.text = '<script>memberList: ' + json.dumps([self.member]) + '</script><ul class="pagination"><a href="https://evil.test/?page=2">Next</a></ul>'
        client.session.get.return_value = response
        records, complete = client.search('王小明', max_pages=1)
        self.assertFalse(complete)
        self.assertEqual(client.session.get.call_args.kwargs['params'], {'keyword': '王小明', 'page': 1})
        self.assertIn('未完整', match_entry(self.entry, records, complete)[0]['比對狀態'])
        with self.assertRaises(ValueError):
            client.search(' ')

    def test_login_redirect_not_no_match(self):
        client = MemberClient.__new__(MemberClient)
        client.base, client.cache, client.session = 'https://example.test', {}, Mock()
        client.session.get.return_value = Mock(url='https://example.test/login')
        with self.assertRaisesRegex(ValueError, '登入已失效'):
            client.search('王小明')

    def test_tsv_preserves_zero_and_escapes_formulas(self):
        rows = match_entry(self.entry, [self.member])
        rows[0]['查詢姓名'] = '=1+1'
        result = to_tsv(rows)
        self.assertIn('0912345678', result)
        self.assertIn("'=1+1", result)

    def test_paste_bounds(self):
        self.assertEqual(parse_pasted('王小明\thttps://lin.ee/test')[0]['name'], '王小明')
        for text in ['', '\n'.join(['王小明'] * 101)]:
            with self.assertRaises(ValueError):
                parse_pasted(text)


if __name__ == '__main__':
    unittest.main()
