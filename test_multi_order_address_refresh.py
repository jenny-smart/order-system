import unittest
from unittest.mock import patch

import quick_order as q


class MultiOrderAddressRefreshTest(unittest.TestCase):
    """同一次建立多筆：第 1 筆新增的地址存進後台下拉後，第 2 筆要改選該 addressId。"""

    def test_each_order_compares_against_fresh_member_address_list(self):
        address = '台北市大安區復興南路一段390號'
        stale = {'member': {'member_id': '1', 'memberAddressList': []}, 'storedValue': 0}
        fresh = {'member': {'member_id': '1', 'memberAddressList': [
            {'id': 9, 'address': address, 'areaId': '25', 'companyId': '1', 'purchase': {}},
        ]}, 'storedValue': 5000}
        with patch.object(q, '_configure_environment', return_value='https://example.invalid'), \
             patch.object(q, '_get_booking_token_for_payway', return_value='token'), \
             patch.object(q, 'get_member', return_value=fresh) as lookup, \
             patch('backend_address_form.query_native_address', side_effect=AssertionError('saved address must use dropdown')), \
             patch.object(q, 'calculate_hour', side_effect=RuntimeError('stop')) as calc:
            with self.assertRaisesRegex(RuntimeError, 'stop'):
                q.quick_create_order(
                    'dev', '信用卡', '', {'session': object(), 'phone': '0912345678', 'member_payload': stale},
                    address, '1', '2026-11-06', '09:00-12:00', '3',
                )
        lookup.assert_called_once()
        self.assertEqual(str(calc.call_args.args[1]['addressId']), '9')


if __name__ == '__main__':
    unittest.main()
