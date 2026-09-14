import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
import quick_order as q


class BookingResultTest(unittest.TestCase):
    def setUp(self):
        native = patch('backend_address_form.query_native_address', return_value={'area': {'area_id': '34', 'company_id': '1'}})
        native.start()
        self.addCleanup(native.stop)

    def run_booking(self, candidates, count=0, payway='信用卡', total=2800, fare=0):
        session = Mock()
        session.post.return_value.json.return_value = {'count': count}
        stack = ExitStack()
        self.addCleanup(stack.close)
        def mock(name, **kwargs):
            return stack.enter_context(patch.object(q, name, **kwargs))
        mock('_configure_environment', return_value='https://example.invalid')
        mock('_get_booking_token_for_payway', return_value='token')
        mock('_fetch_csrf_from_url', return_value='token')
        mock('check_contain', return_value={'area': {'area_id': '34', 'company_id': '1'}})
        mock('calculate_hour', return_value={'data': {'hour': 2, 'price': 2286, 'fare': 0}})
        mock('_query_booking_slot_with_lemon_retry', return_value=('[]', 'token', {}))
        mock('list_order_numbers_for_phone', side_effect=[{'OLD'}] + [set(candidates) | {'OLD'}] * 4)
        mock('_fetch_purchase_blocks_for_phone', return_value=[{'order_no': n, 'lines': ['測試地址']} for n in candidates])
        mock('_parse_service_date_time_loose', return_value=('2026-09-20', '09:00-11:00'))
        mock('_extract_payway_line', return_value=payway)
        mock('fetch_order_meta_by_order_no', return_value={})
        mock('_fetch_purchase_block_for_order_no', return_value={'lines': [f'總金額：{total}', f'車馬費：{fare}']})
        mock('_check_order_no_duplicate', return_value=(False, 1))
        stack.enter_context(patch.object(q.time, 'sleep'))
        return q.quick_create_order('dev', payway, '',
            {'session': session, 'phone': '', 'member_payload': {'member': {'member_id': '1'}}},
            '測試地址', '1', '2026-09-20', '09:00-11:00', '2')

    def test_uses_backend_final_total(self):
        result = self.run_booking(['NEW'])
        self.assertEqual(result['order_no'], 'NEW')
        self.assertEqual(result['price_with_tax'], 2800)

    def test_service_amount_excludes_separately_listed_fare(self):
        result = self.run_booking(['NEW'], total=4400, fare=200)
        self.assertEqual(result['order_total'], 4400)
        self.assertEqual(result['service_amount'], 4200)
        self.assertEqual(result['price_with_tax'], 4200)
        self.assertEqual(str(result['fare']), '200')

    def test_never_reuses_old_order(self):
        with self.assertRaisesRegex(Exception, '結果待確認'):
            self.run_booking(['OLD'])

    def test_never_picks_arbitrary_new_order(self):
        with self.assertRaisesRegex(Exception, '結果待確認'):
            self.run_booking(['NEW1', 'NEW2'])

    def test_stored_value_zero_count_is_not_balance_failure(self):
        with self.assertRaisesRegex(Exception, '結果待確認'):
            self.run_booking([], count=0, payway='儲值金')

    def test_stored_value_positive_count_is_failure(self):
        with self.assertRaisesRegex(Exception, '餘額不足'):
            self.run_booking([], count=1, payway='儲值金')

if __name__ == '__main__':
    unittest.main()
