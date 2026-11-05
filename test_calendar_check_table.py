import unittest

from function.calendar_check import build_issue_rows

BASE = 'https://backend.example'


class CalendarCheckTableTest(unittest.TestCase):
    def setUp(self):
        self.result = {
            'backend_duplicates': [dict(order_nos=['LC001', 'LC002'], name='徐雅音', phone='0935973225',
                                        address='新北市板橋區中山路一段176-2號28樓', region='新北',
                                        service_date='2026-12-07', service_time='09:00-12:00',
                                        reason='後台同人同址同時段重複 2 筆', issue='long',
                                        line_url='https://chat.line.biz/x/chat/U1')],
            'backend_missing_in_calendar': [dict(order_no='LC003', name='李明達', phone='',
                                                 address='台北市', region='台北',
                                                 service_date='2026-11-27', service_time='14:00-17:00',
                                                 reason='日曆找不到同人同址同時段的黃色事件', issue='long')],
            'calendar_missing_in_backend': [dict(order_no='', event_summary='王小明-大安,0912345678',
                                                 name='王小明', phone='0912345678', address='大安',
                                                 region='台北', service_date='2026-11-13',
                                                 service_time='09:00-12:00', event_link='https://cal/e1',
                                                 reason='找不到後台訂單', issue='long')],
        }

    def test_duplicates_expand_to_one_row_per_order_with_links(self):
        rows = build_issue_rows(self.result, BASE)['duplicates']
        self.assertEqual([r['訂單編號'] for r in rows],
                         [f'{BASE}/purchase?orderNo=LC001', f'{BASE}/purchase?orderNo=LC002'])
        self.assertEqual(rows[0]['組別'], '第 1 組')
        self.assertTrue(rows[0]['會員'].startswith(f'{BASE}/purchase?'))
        self.assertIn('&phone=0935973225&', rows[0]['會員'])
        self.assertIn('clean_date_s=&', rows[0]['會員'])
        self.assertIn('calendar.google.com', rows[0]['查日曆'])
        self.assertEqual(rows[0]['LINE'], 'https://chat.line.biz/x/chat/U1')
        self.assertIsNone(build_issue_rows(self.result, BASE)['backend_missing'][0]['LINE'])

    def test_line_urls_parsed_from_purchase_list_rows(self):
        import orders
        html = ('<table><tr><td>LC00216800</td><td><a href="https://chat.line.biz/x/chat/U9">LINE</a></td></tr>'
                '<tr><td>LC00219813</td><td>無</td></tr></table>')
        self.assertEqual(orders._line_urls_from_purchase_html(html),
                         {'LC00216800': 'https://chat.line.biz/x/chat/U9'})

    def test_member_link_falls_back_to_name_and_short_reason_used(self):
        row = build_issue_rows(self.result, BASE)['backend_missing'][0]
        self.assertIn('name=李明達', row['會員'])
        self.assertIn('phone=&', row['會員'])
        self.assertEqual(row['異常說明'], '日曆找不到同人同址同時段的黃色事件')

    def test_calendar_only_row_has_event_link_and_no_order_link(self):
        row = build_issue_rows(self.result, BASE)['calendar_missing'][0]
        self.assertIsNone(row['訂單編號'])
        self.assertEqual(row['日曆事件'], 'https://cal/e1')


if __name__ == '__main__':
    unittest.main()
