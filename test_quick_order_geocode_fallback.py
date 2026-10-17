import unittest
from unittest.mock import patch, Mock
import quick_order as q

ADDRESS = '新北市汐止區建成路142巷45弄5號2樓'
AREA_REPLY = {'return_code': '0000', 'area': {'area_id': '25', 'company_id': '2'}}


class BackendAddressTest(unittest.TestCase):
    def resolve(self, reply, items=None, native=None, latlng=('25.1', '121.6')):
        payload = {'member': {'member_id': '1', 'memberAddressList': items or []}}
        native_mock = (patch('backend_address_form.query_native_address', side_effect=native)
                       if isinstance(native, Exception)
                       else patch('backend_address_form.query_native_address', return_value=native or {}))
        with patch.object(q, 'geocode_address', return_value=latlng), \
             patch.object(q, 'check_contain', return_value=reply) as check, \
             native_mock:
            result = q.resolve_backend_booking_address(object(), payload, ADDRESS, 'token', '1')
        return result, check

    def test_new_customer_gets_area_from_address_lookup(self):
        (info, parts, reply), check = self.resolve(AREA_REPLY)
        self.assertEqual(info['area_id'], '25')
        self.assertEqual(info['company_id'], '2')
        self.assertEqual(info['lat'], '25.1')
        self.assertEqual(info['lng'], '121.6')
        self.assertEqual(info['country_id'], '23')
        self.assertFalse(info.get('addressId'))
        check.assert_called_once()

    def test_falls_back_to_native_lookup(self):
        native = {'return_code': '0000', 'area': {'area_id': '30', 'company_id': '3', 'lat': '1', 'lng': '2'}}
        (info, _, _), _ = self.resolve({'return_code': '0000', 'area': {}}, native=native)
        self.assertEqual(info['area_id'], '30')
        self.assertEqual(info['lat'], '1')

    def test_no_area_stops_with_reason(self):
        with self.assertRaisesRegex(Exception, '地址查不到服務區域'):
            self.resolve({'return_code': '1001', 'description': '不在服務範圍'},
                         native=RuntimeError('瀏覽器無法啟動'))

    def test_existing_address_skips_lookup(self):
        (info, _, _), check = self.resolve({}, [{'id': 7, 'address': ADDRESS, 'areaId': 88,
                                                'companyId': 2, 'lat': '25', 'lng': '121'}])
        self.assertEqual(info['addressId'], '7')
        self.assertEqual(info['area_id'], 88)
        check.assert_not_called()

    def test_other_address_is_not_reused(self):
        (info, _, _), _ = self.resolve(AREA_REPLY, [{'id': 7, 'address': '台北市大安區信義路1號',
                                                     'areaId': 99, 'companyId': 1}])
        self.assertFalse(info.get('addressId'))
        self.assertEqual(info['area_id'], '25')

    def test_order_sends_area_to_backend_calculation(self):
        with patch.object(q, '_configure_environment', return_value='https://example.invalid'), \
             patch.object(q, '_get_booking_token_for_payway', return_value='token'), \
             patch.object(q, 'check_contain', return_value=AREA_REPLY), \
             patch.object(q, 'geocode_address', return_value=('25.1', '121.6')), \
             patch.object(q, 'calculate_hour', side_effect=RuntimeError('backend calculation')) as calc:
            with self.assertRaisesRegex(RuntimeError, 'backend calculation'):
                q.quick_create_order('dev', '信用卡', '',
                    {'session': object(), 'phone': '', 'member_payload': {'member': {'member_id': '1'}}},
                    ADDRESS, '1', '2026-09-26', '08:30-12:30', '4')
            data = calc.call_args.args[1]
            self.assertEqual(data['address'], ADDRESS)
            self.assertEqual(data['country_id'], '23')
            self.assertEqual(data['area_id'], '25')
            self.assertEqual(data['company_id'], '2')
            self.assertEqual(data['lat'], '25.1')

    def test_batch_uses_same_backend_address_flow(self):
        row = {'購買項目': '居家清潔', '電話': '', '地址': ADDRESS,
               '開始時間': '08:30', '結束時間': '12:30', '服務人時': '8'}
        with patch.object(q.orders, 'st', None), \
             patch.object(q.orders, 'map_to_system_slot', return_value={'system_slot': '08:30-12:30'}), \
             patch.object(q.orders, 'parse_service_human_hour', return_value=(2, 4)), \
             patch.object(q.orders, 'get_member', return_value={'member': {'member_id': '1'}}), \
             patch.object(q, 'check_contain', return_value=AREA_REPLY), \
             patch.object(q, 'geocode_address', return_value=('25.1', '121.6')), \
             patch.object(q.orders, 'prepare_base_order_data', side_effect=RuntimeError('prepare backend payload')) as prepare:
            with self.assertRaisesRegex(RuntimeError, 'prepare backend payload'):
                q.orders.process_one_group(object(), [(1, row)], 'token', None, '台北')
            info = prepare.call_args.args[2]
            self.assertEqual(info['country_id'], '23')
            self.assertEqual(info['area_id'], '25')

    def test_backend_calculation_error_is_preserved(self):
        response = Mock(status_code=200, url='https://example.invalid/ajax/calculate_hour')
        response.json.return_value = {'return_code': '1001', 'description': '地址不在服務範圍'}
        with self.assertRaisesRegex(Exception, '後台計算時數回覆：地址不在服務範圍'):
            q.orders._booking_backend_response(response, '計算時數')


if __name__ == '__main__':
    unittest.main()
