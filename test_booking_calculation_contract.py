import unittest
from unittest.mock import Mock, patch
import quick_order as q


class CalculationContractTest(unittest.TestCase):
    def setUp(self):
        native = patch('backend_address_form.query_native_address', return_value={'area': {'area_id': '25', 'company_id': '1'}})
        native.start()
        self.addCleanup(native.stop)

    def test_calculation_clears_only_hour_without_changing_selected_slot(self):
        session = Mock()
        session.post.return_value = Mock(status_code=200, url='https://example.invalid/ajax/calculate_hour')
        session.post.return_value.json.return_value = {'data': {'hour': 2, 'price': 2286}}
        data = dict(hour='4', person='2', period_s='08:30-12:30', price='999',
                    price_vvip='999', fare='100', area_id='25', company_id='1')
        original = data.copy()
        q.orders.calculate_hour(session, data, 'token')
        sent = session.post.call_args.kwargs['data']
        self.assertEqual(sent['hour'], '')
        for key in ('price', 'price_vvip', 'fare'):
            self.assertEqual(sent[key], original[key])
        self.assertEqual(sent['area_id'], '25')
        self.assertEqual(sent['company_id'], '1')
        self.assertEqual(data, original)

    def test_all_payment_routes_keep_selected_hours_and_backend_price(self):
        for payway in ('信用卡', 'ATM', '儲值金'):
            with self.subTest(payway=payway), \
                 patch.object(q, '_configure_environment', return_value='https://example.invalid'), \
                 patch.object(q, '_get_booking_token_for_payway', return_value='token'), \
                 patch.object(q, 'check_contain', return_value={'area': {'area_id': '25', 'company_id': '1'}}), \
                 patch.object(q, 'calculate_hour', return_value={'data': {'hour': 2, 'price': 2286, 'price_vvip': 0, 'fare': 0}}), \
                 patch.object(q, '_query_booking_slot_with_lemon_retry', side_effect=RuntimeError('stop before write')) as query:
                with self.assertRaisesRegex(RuntimeError, 'stop before write'):
                    q.quick_create_order('dev', payway, '',
                        {'session': object(), 'phone': '', 'member_payload': {'member': {'member_id': '1'}}},
                        '測試地址', '1', '2026-09-26', '08:30-12:30', '4', person='2')
                data = query.call_args.args[3]
                self.assertEqual((data['hour'], data['person'], data['period_s']), ('4', '2', '08:30-12:30'))
                self.assertEqual(data['price'], '2286')
                self.assertEqual((data['area_id'], data['company_id']), ('25', '1'))


if __name__ == '__main__':
    unittest.main()
