import unittest
from unittest.mock import patch

import orders
import quick_order as q


ADDRESS = '台北市大安區測試路233號2樓'


class SavedAddressFieldsTest(unittest.TestCase):
    def payload(self, **fields):
        item = {'id': 302, 'address': ADDRESS, 'countryId': 12,
                'companyId': 0, 'areaId': 0, 'lat': 0, 'lng': 0,
                'purchase': {'company_id': 1, 'area_id': 25, 'country_id': 12,
                             'lat': 25.02, 'lng': 121.52}}
        item.update(fields)
        return {'member': {'member_id': 1, 'memberAddressList': [item]}}

    def test_zero_outer_fields_use_same_address_purchase(self):
        for empty in (0, '0', '0.0', '', None):
            with self.subTest(empty=empty):
                info = orders.pick_best_address_info(self.payload(companyId=empty, areaId=empty, lat=empty, lng=empty), ADDRESS)
                self.assertEqual((info['company_id'], info['area_id'], info['lat'], info['lng']), (1, 25, 25.02, 121.52))
                self.assertEqual(info['addressId'], '302')

    def test_valid_outer_fields_take_priority(self):
        info = orders.pick_best_address_info(self.payload(companyId=2, areaId=88, lat=24.9, lng=121.1), ADDRESS)
        self.assertEqual((info['company_id'], info['area_id'], info['lat'], info['lng']), (2, 88, 24.9, 121.1))

    def test_other_address_cannot_supply_saved_fields(self):
        self.assertEqual(orders.pick_best_address_info(self.payload(address='新北市測試路1號'), ADDRESS), {})

    def test_missing_purchase_leaves_fields_empty(self):
        info = orders.pick_best_address_info(self.payload(purchase=None), ADDRESS)
        self.assertEqual((info['area_id'], info['company_id'], info['lat'], info['lng']), ('', '', '', ''))

    def test_saved_coordinates_are_used_without_address_lookup(self):
        with patch.object(q, 'check_contain', side_effect=AssertionError('address lookup must not be called')) as check, \
             patch.object(q, 'geocode_address', side_effect=AssertionError('Google must not be called')), \
             patch('backend_address_form.query_native_address', side_effect=AssertionError('browser must not be launched')):
            info, _, _ = q.resolve_backend_booking_address('session', self.payload(), ADDRESS, 'token', '1')
        check.assert_not_called()
        self.assertEqual((info['area_id'], info['company_id']), (25, 1))

    def test_batch_receives_saved_region_fields(self):
        row = {'購買項目': '居家清潔', '電話': '0900000000', '地址': ADDRESS,
               '開始時間': '09:00', '結束時間': '12:00', '服務人時': '6'}
        with patch.object(orders, 'st', None), \
             patch.object(orders, 'get_member', return_value=self.payload()), \
             patch.object(q, 'check_contain', return_value={}), \
             patch.object(orders, 'prepare_base_order_data', side_effect=RuntimeError('stop before calculation')) as prepare:
            with self.assertRaisesRegex(RuntimeError, 'stop before calculation'):
                orders.process_one_group(object(), [(1, row)], 'token', None, '台北')
        info = prepare.call_args.args[2]
        self.assertEqual((info['area_id'], info['company_id'], info['lat'], info['lng']), (25, 1, 25.02, 121.52))


if __name__ == '__main__':
    unittest.main()
