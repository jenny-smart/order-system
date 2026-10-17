import unittest
from unittest.mock import MagicMock, patch

import orders


class CalendarDuplicateConsistencyTest(unittest.TestCase):
    def order(self, number='LC001', **changes):
        row = dict(order_no=number, name='測試客人', phone='0912345678',
                   address='台北市大安區測試路1號2樓', region='台北',
                   service_date='2026-10-15', service_time='09:00-12:00')
        row.update(changes)
        return row

    def test_address_and_phone_format_variants_group_together(self):
        first = self.order()
        second = self.order('LC002', address='臺北市大安區測試路１號２樓 ')
        self.assertEqual(orders._calchk_duplicate_groups([first, second]), [[first, second]])
        lines = ['測試客人', '０９１２－３４５－６７８']
        self.assertEqual(orders._calchk_phone_from_lines(lines), '0912345678')
        self.assertEqual(orders._calchk_name_from_lines(lines), '測試客人')

    def test_same_time_different_person_address_date_or_region_is_not_duplicate(self):
        for field, value in [('phone', '0987654321'), ('address', '台北市大安區測試路2號2樓'),
                             ('service_date', '2026-10-16'), ('service_time', '14:00-17:00'),
                             ('region', '台中')]:
            with self.subTest(field=field):
                self.assertEqual(orders._calchk_duplicate_groups([
                    self.order(), self.order('LC002', **{field: value})]), [])

    def test_missing_phone_uses_unambiguous_name_only(self):
        first, second = self.order(), self.order('LC002', phone='')
        self.assertEqual(orders._calchk_duplicate_groups([first, second]), [[first, second]])
        other = self.order('LC003', phone='0987654321')
        self.assertEqual(orders._calchk_duplicate_groups([first, second, other]), [])
        self.assertEqual(orders._calchk_duplicate_groups([
            self.order(phone='', name=''), self.order('LC002', phone='', name='')]), [])

    def test_repeated_fetch_of_same_order_is_not_two_orders(self):
        self.assertEqual(orders._calchk_duplicate_groups([self.order(), self.order()]), [])

    def check(self, addresses, phone='0912-345-678', yellow=True):
        event = dict(id='event1', summary='測試客人,0912345678',
                     location='台北市大安區測試路1號2樓',
                     colorId=orders.COLOR_YELLOW if yellow else '3',
                     start={'dateTime': '2026-10-15T09:00:00+08:00'},
                     end={'dateTime': '2026-10-15T12:00:00+08:00'})
        service = MagicMock()
        service.events.return_value.list.return_value.execute.return_value = {'items': [event]}
        blocks = [dict(order_no=f'LC00{i}', lines=['測試客人', phone, address,
                   '2026-10-15', '09:00-12:00']) for i, address in enumerate(addresses)]
        with patch.object(orders, 'GOOGLE_CALENDAR_MAP', {'台北': 'test'}), \
             patch.object(orders, 'build_gcal_service', return_value=service), \
             patch.object(orders, 'login', return_value=True), \
             patch.object(orders, 'get_region_by_address', return_value='台北'), \
             patch.object(orders, '_fetch_all_purchase_blocks_by_date_range', return_value=blocks):
            return orders.run_backend_calendar_consistency_check(
                'dev', 'test@example.com', 'unused', '2026-10-01', '2026-10-31', region='台北')

    def test_duplicate_orders_have_one_warning_and_neither_is_missing(self):
        for yellow in (True, False):
            with self.subTest(yellow=yellow):
                result = self.check(['台北市大安區測試路1號2樓', '臺北市大安區測試路１號２樓'], yellow=yellow)
                self.assertEqual(len(result['backend_duplicates']), 1)
                self.assertEqual(result['backend_duplicates'][0]['order_nos'], ['LC000', 'LC001'])
                self.assertEqual(result['backend_missing_in_calendar'], [])
                self.assertEqual(result['calendar_missing_in_backend'], [])

    def test_single_normalized_order_matches_calendar(self):
        result = self.check(['臺北市大安區測試路１號２樓'])
        self.assertEqual(result['backend_duplicates'], [])
        self.assertEqual(result['backend_missing_in_calendar'], [])
        self.assertEqual(result['calendar_missing_in_backend'], [])

    def test_real_missing_event_is_still_reported(self):
        result = self.check(['台北市大安區測試路1號2樓'], yellow=False)
        self.assertEqual(result['backend_duplicates'], [])
        self.assertEqual(len(result['backend_missing_in_calendar']), 1)

    def test_error_display_always_contains_required_customer_fields(self):
        cases = [
            {
                'order_no': 'LC001', 'name': '王小明', 'phone': '0912345678',
                'address': '台北市大安區測試路1號', 'issue': '找不到日曆事件',
            },
            {
                'order_nos': ['LC002', 'LC003'], 'name': '陳小華', 'phone': '0987654321',
                'address': '台北市信義區測試路2號', 'issue': '重複訂單',
            },
            {'name': '林小美', 'phone': '0900000000', 'address': '', 'issue': '找不到後台訂單'},
        ]
        displays = [orders.format_calendar_consistency_issue(item) for item in cases]
        for display in displays:
            for label in ('訂單編號：', '姓名：', '電話：', '地址：', '異常：'):
                self.assertIn(label, display)
        self.assertIn('LC002、LC003', displays[1])
        self.assertIn('訂單編號：查無對應後台訂單', displays[2])
        self.assertIn('地址：未提供', displays[2])


if __name__ == '__main__':
    unittest.main()
