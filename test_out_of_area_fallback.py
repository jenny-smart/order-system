import unittest
from unittest.mock import Mock, patch

import orders  # noqa: F401
import quick_order as q

SLOT = '2026-12-30_09:00-18:00'


class OutOfAreaTest(unittest.TestCase):
    def test_lemons_added_but_still_missing_raises_out_of_area(self):
        with patch.object(q.orders, 'get_all_sections_raw', side_effect=['[]', '[]']), \
             patch.object(q, 'count_section_available', return_value=0), \
             patch.object(q, 'ensure_lemon_cleaner_shifts', return_value={'success': True, 'assigned': ['檸檬人1', '檸檬人2'], 'assigned_ids': ['1', '2']}), \
             patch.object(q, '_get_booking_token_for_payway', return_value='t'):
            with self.assertRaises(q.OutOfServiceAreaError):
                q._query_booking_slot_with_lemon_retry(object(), 'b', '信用卡', {'person': '2'}, 't', SLOT, True)

    def test_no_lemons_found_is_plain_failure(self):
        with patch.object(q.orders, 'get_all_sections_raw', side_effect=['[]', '[]']), \
             patch.object(q, 'count_section_available', return_value=0), \
             patch.object(q, 'ensure_lemon_cleaner_shifts', return_value={'success': False, 'assigned': []}), \
             patch.object(q, '_get_booking_token_for_payway', return_value='t'):
            with self.assertRaises(Exception) as ctx:
                q._query_booking_slot_with_lemon_retry(object(), 'b', '信用卡', {'person': '2'}, 't', SLOT, True)
        self.assertNotIsInstance(ctx.exception, q.OutOfServiceAreaError)

    def test_fallback_books_proxy_address_then_restores(self):
        calls = []
        real = {'address': '新北市林口區A路1號', 'area_id': '9', 'lat': '1', 'lng': '2', 'country_id': '3'}

        def impl(*args, **kwargs):
            calls.append(kwargs.get('address', args[4] if len(args) > 4 else None))
            holder = q._BOOKING_ADDRESS_INFO.get()
            if len(calls) == 1:
                holder.update(real)
                raise q.OutOfServiceAreaError('無可預約人力')
            return {'order_no': 'LC001', 'address': q.FALLBACK_BOOKING_ADDRESS, 'session': Mock()}
        with patch.object(q, '_quick_create_order_impl', side_effect=impl), \
             patch.object(q, '_configure_environment', return_value='b'), \
             patch.object(q, '_update_order_address', return_value=(True, '')) as upd:
            res = q.quick_create_order('dev', '信用卡', '台北', {'session': Mock()}, real['address'], '1', '2026-12-30', '09:00-18:00', '8', person='2')
        self.assertEqual(calls, [real['address'], q.FALLBACK_BOOKING_ADDRESS])
        self.assertEqual(upd.call_args.args[3]['address'], real['address'])
        self.assertEqual(res['address'], real['address'])
        self.assertIn('不在服務區域', res['proxy_address_note'])

    def test_update_order_address_posts_area_fields(self):
        page = ('<meta name="csrf-token" content="tok"><input name="address" value="台北市大安區信義路四段210號4樓">'
                '<input name="country_id" value="1">')
        after = '<script>purchase: {"address":"新北市林口區A路1號"}</script>'
        s = Mock()
        s.get.side_effect = [Mock(status_code=200, text=page), Mock(status_code=200, text=after)]
        s.post.return_value = Mock(status_code=302)
        with patch.object(q, '_fetch_order_edit_id', return_value='5'), \
             patch.object(q, '_extract_purchase_json_from_edit_html', side_effect=[{}, {'address': '新北市林口區A路1號'}]):
            ok, why = q._update_order_address(s, 'b', 'LC005', {'address': '新北市林口區A路1號', 'area_id': '9', 'lat': '1', 'lng': '2', 'country_id': '3'})
        self.assertTrue(ok, why)
        data = s.post.call_args.kwargs['data']
        self.assertEqual((data['address'], data['area_id'], data['lat'], data['country_id']), ('新北市林口區A路1號', '9', '1', '3'))


if __name__ == '__main__':
    unittest.main()
