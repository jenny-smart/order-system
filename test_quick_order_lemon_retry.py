import json
import unittest
from unittest.mock import patch
import quick_order as q

SLOT = '2026-09-26_09:00-12:00'
AVAILABLE = '<input name="date_list[]" value="' + SLOT + '">'


class LemonRetryTest(unittest.TestCase):
    def run_query(self, replies, enabled=True, pre=None):
        with patch.object(q.orders, 'get_all_sections_raw', side_effect=replies) as query, \
             patch.object(q, 'ensure_lemon_cleaner_shifts', return_value=pre or {'success': True, 'assigned': ['檸檬人1', '檸檬人2']}) as shift, \
             patch.object(q, '_get_booking_token_for_payway', return_value='new-token'):
            result = q._query_booking_slot_with_lemon_retry(object(), 'https://example.invalid', '信用卡', {'person': '2'}, 'old-token', SLOT, enabled)
            return result, query, shift

    def test_empty_then_available_refreshes_token_and_requests_two(self):
        result, query, shift = self.run_query(['[]', AVAILABLE])
        self.assertEqual(result[1], 'new-token')
        self.assertEqual(query.call_args.args[2], 'new-token')
        self.assertEqual(shift.call_args.kwargs['person_count'], '2')
        self.assertEqual(shift.call_args.kwargs['period_s'], '09:00-12:00')

    def test_checkbox_without_names_is_accepted_like_batch(self):
        _, query, shift = self.run_query([AVAILABLE])
        shift.assert_not_called()
        query.assert_called_once()

    def test_known_shortage_only_requests_missing_person(self):
        initial = json.dumps([{'date': '2026-09-26', 'section': '09:00-12:00', 'cleaner': ['王小姐']}])
        _, _, shift = self.run_query([initial, AVAILABLE])
        self.assertEqual(shift.call_args.kwargs['person_count'], '1')

    def test_disabled_never_adds_shifts(self):
        with patch.object(q.orders, 'get_all_sections_raw', return_value='[]'), \
             patch.object(q, 'ensure_lemon_cleaner_shifts') as shift:
            with self.assertRaisesRegex(Exception, '後台未回傳可預約時段'):
                q._query_booking_slot_with_lemon_retry(object(), '', 'ATM', {'person': '2'}, '', SLOT, False)
            shift.assert_not_called()

    def test_failed_retry_shows_actual_skip_reason(self):
        with self.assertRaisesRegex(Exception, '檸檬人1：上4衝突'):
            self.run_query(['[]', '[]'], pre={'success': False, 'message': '可用檸檬人不足', 'skipped': [{'name': '檸檬人1', 'reason': '上4衝突'}]})

    def test_quick_uses_batch_shift_implementation(self):
        import shared.cleaner_shift as shifts
        self.assertIs(q.ensure_lemon_cleaner_shifts, shifts.ensure_lemon_cleaner_shifts)
        self.assertIs(q.orders.ensure_lemon_cleaner_shifts, shifts.ensure_lemon_cleaner_shifts)

    def test_retry_refreshes_correct_payment_route(self):
        for payway in ('儲值金', '信用卡', 'ATM'):
            with self.subTest(payway=payway), \
                 patch.object(q.orders, 'get_all_sections_raw', side_effect=['[]', AVAILABLE]), \
                 patch.object(q, 'ensure_lemon_cleaner_shifts', return_value={'success': True}), \
                 patch.object(q, '_get_booking_token_for_payway', return_value='fresh') as refresh:
                q._query_booking_slot_with_lemon_retry('s', 'base', payway, {'person': '2'}, 'old', SLOT, True)
                refresh.assert_called_once_with('s', 'base', payway)

    def test_makeup_orders_forward_auto_shift_switch_to_shared_order(self):
        ctx = {'region': '台北', 'lookup': {}, 'address': '地址', 'member': {},
               'plan': {'coupon_a': 100, 'coupon_b': 100}, 'today_str': '2026-09-14',
               'date_e': '2026-10-14', 'prefix_a': 'a', 'prefix_b': 'b'}
        for fn in (q.stored_value_makeup_create_stored_order, q.stored_value_makeup_create_paid_order):
            for enabled in (False, True):
                with self.subTest(fn=fn.__name__, enabled=enabled), \
                     patch.object(q, '_stored_value_makeup_context', return_value=ctx), \
                     patch.object(q, 'create_coupon', return_value={'coupon_code': 'test'}), \
                     patch.object(q, 'quick_create_order', side_effect=RuntimeError('shared order')) as create:
                    with self.assertRaisesRegex(RuntimeError, 'shared order'):
                        fn(env_name='dev', backend_email='', backend_password='', phone='',
                           clean_type_id='1', service_date='2026-09-26', period_s='09:00-12:00',
                           hour='3', person='2', allow_auto_lemon_shift=enabled)
                    self.assertEqual(create.call_args.kwargs['allow_auto_lemon_shift'], enabled)

    def test_conversion_uses_shared_order_without_separate_address_lookup(self):
        class ReachedSharedOrder(BaseException):
            pass
        stage = {'lemon_result_a': {'success': True}, 'session': object(), 'base_url': 'base',
                 'env_name': 'dev', 'order_no_a': 'TT0001', 'address_a': '新地址', 'payway_a': '儲值金',
                 'region_a': '台北', 'clean_type_id': '1', 'lookup_result': {},
                 'member_payload': {'member': {}}, 'service_amount_a_int': 0, 'person_a': '2'}
        for enabled in (False, True):
            with self.subTest(enabled=enabled), \
                 patch.object(q, 'geocode_address', side_effect=AssertionError('separate geocode')), \
                 patch.object(q, 'quick_create_order', side_effect=ReachedSharedOrder) as create:
                with self.assertRaises(ReachedSharedOrder):
                    q.convert_order_stage2_create_new_orders(stage, [{'date_s': '2026-09-26',
                        'period_s': '09:00-12:00', 'hour': '3', 'person': '2', 'allow_lemon': enabled}])
                self.assertEqual(create.call_args.kwargs['allow_auto_lemon_shift'], enabled)
                self.assertEqual(create.call_args.kwargs['address'], '新地址')
