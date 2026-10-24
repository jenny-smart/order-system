import unittest
from unittest.mock import patch

import orders
import quick_order as q


ADDRESS = '台北市大安區測試路233號2樓'


class SavedAddressFieldsTest(unittest.TestCase):
    def payload(self, **fields):
        item = {'id': 302, 'address': ADDRESS, 'countryId': 12,
                'companyId': 0, 'areaId': 0, 'lat': 0, 'lng': 0,
                'memo': '此地址客服備註',
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

    def test_saved_address_uses_dropdown_fields_without_native_lookup(self):
        with patch.object(q, 'check_contain', side_effect=AssertionError('address lookup must not be called')) as check, \
             patch.object(q, 'geocode_address', side_effect=AssertionError('Google must not be called')), \
             patch('backend_address_form.query_native_address', side_effect=AssertionError('saved dropdown must not be located')) as native:
            info, _, _ = q.resolve_backend_booking_address('session', self.payload(), ADDRESS, 'token', '1')
        check.assert_not_called()
        native.assert_not_called()
        self.assertEqual((info['area_id'], info['company_id']), (25, 1))
        self.assertEqual((info['lat'], info['lng']), (25.02, 121.52))
        self.assertEqual(info['notice'], '此地址客服備註')

    def test_batch_receives_saved_region_fields(self):
        row = {'購買項目': '居家清潔', '電話': '0900000000', '地址': ADDRESS,
               '開始時間': '09:00', '結束時間': '12:00', '服務人時': '6'}
        with patch.object(orders, 'st', None), \
             patch.object(orders, 'get_member', return_value=self.payload()), \
             patch.object(q, 'check_contain', return_value={}), \
             patch('backend_address_form.query_native_address', side_effect=AssertionError('batch must not launch dropdown browser')), \
             patch.object(orders, 'prepare_base_order_data', side_effect=RuntimeError('stop before calculation')) as prepare:
            with self.assertRaisesRegex(RuntimeError, 'stop before calculation'):
                orders.process_one_group(object(), [(1, row)], 'token', None, '台北')
        info = prepare.call_args.args[2]
        self.assertEqual((info['area_id'], info['company_id'], info['lat'], info['lng']), (25, 1, 25.02, 121.52))

    def test_proxy_row_without_saved_address_uses_native_lookup(self):
        """代客保留：檸檬保留帳號沒有客人地址 → 後台查詢地區取得區域（addressId 留空，送單時另建地址）。"""
        from shared import proxy_reserve
        row = {'購買項目': '居家清潔', '電話': proxy_reserve.RESERVE_PHONE, '地址': '新北市中和區測試路1號',
               '開始時間': '09:00', '結束時間': '12:00', '服務人時': '6', '姓名': '王亭雅',
               proxy_reserve.FLAG_KEY: True, proxy_reserve.NAME_KEY: '王亭雅'}
        native = {'area': {'area_id': 31, 'company_id': 1, 'lat': 25.0, 'lng': 121.5}}
        with patch.object(orders, 'st', None), \
             patch.object(orders, 'get_member', return_value=self.payload()), \
             patch('backend_address_form.query_native_address', return_value=native) as query, \
             patch.object(q, '_validate_area_not_known_bad'), patch.object(q, '_validate_address_before_submit'), \
             patch.object(orders, 'prepare_base_order_data', side_effect=RuntimeError('stop before calculation')) as prepare:
            with self.assertRaisesRegex(RuntimeError, 'stop before calculation'):
                orders.process_one_group(object(), [(1, row)], 'token', None, '台北')
        query.assert_called_once()
        info = prepare.call_args.args[2]
        self.assertEqual((info['area_id'], info['company_id']), (31, 1))
        self.assertEqual(info.get('addressId', ''), '')


if __name__ == '__main__':
    unittest.main()
