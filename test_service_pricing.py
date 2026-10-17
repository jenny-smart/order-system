import copy
import json
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch, Mock
import service_pricing as p


def configured():
    config = p.default_config()
    config['enabled'] = True
    for i, key in enumerate(p.PERIODS):
        config['periods'][key]['rates'] = {
            'vip': {'weekday': 500 + i * 100, 'weekend': 550 + i * 100},
            'regular': {'weekday': 800 + i * 100, 'weekend': 850 + i * 100},
        }
    config['periods']['part1'].update(start='2027-01-01', end='2027-01-10')
    config['periods']['part2'].update(start='2027-01-11', end='2027-01-20')
    return config


class PricingTest(unittest.TestCase):
    def test_all_twelve_prices(self):
        config = configured()
        for i, (weekday, weekend) in enumerate([('2026-12-25', '2026-12-26'), ('2027-01-01', '2027-01-02'), ('2027-01-11', '2027-01-16')]):
            for tier, base in [('vip', 500), ('regular', 800)]:
                self.assertEqual(p.unit_price(weekday, tier, config), base + i * 100)
                self.assertEqual(p.unit_price(weekend, tier, config), base + i * 100 + 50)

    def test_decimal_rates_preserve_cents(self):
        config = configured()
        config['periods']['normal']['rates']['vip']['weekday'] = 600.25
        self.assertEqual(p.unit_price('2026-12-25', 'vip', p.validate(config)), 600.25)
        payload = dict(date_s='2026-12-25', hour='4', person='2')
        p.apply_booking_price(payload, 'vip', config)
        self.assertEqual(payload['price'], '4573')
        for invalid in (600.251, 0, -1, float('inf'), float('nan')):
            config['periods']['normal']['rates']['vip']['weekday'] = invalid
            with self.assertRaises(ValueError):
                p.validate(config)

    def test_inclusive_boundaries_and_outside(self):
        config = configured()
        for day, expected in [('2026-12-31','normal'), ('2027-01-01','part1'), ('2027-01-10','part1'), ('2027-01-11','part2'), ('2027-01-20','part2'), ('2027-01-21','normal')]:
            self.assertEqual(p.period_for(day, config), expected)

    def test_customer_rules(self):
        for balance in [-20, 0, 1]:
            self.assertEqual(p.customer_tier('batch', balance), 'vip')
            self.assertEqual(p.customer_tier('new', balance), 'regular')
            self.assertEqual(p.customer_tier('existing', balance), 'vip' if balance > 0 else 'regular')
        self.assertEqual(p.account_balance({'storedValue': 0, 'shoppingValue': 50}), 50)
        with self.assertRaises(ValueError):
            p.account_balance({})

    def test_validation_and_atomic_persistence(self):
        config = configured()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SERVICE_PRICING_FILE': folder + '/prices.json', 'SERVICE_PRICING_JSON': ''}):
            p.save_config(config)
            self.assertEqual(p.load_config(), config)
            bad = copy.deepcopy(config)
            bad['periods']['part2']['start'] = '2027-01-10'
            with self.assertRaises(ValueError):
                p.save_config(bad)
            self.assertEqual(p.load_config(), config)
        bad = copy.deepcopy(config)
        bad['periods']['normal']['rates']['vip']['weekday'] = 0
        with self.assertRaises(ValueError):
            p.validate(bad)

    def test_booking_route_tax_and_fare(self):
        import quick_order as q
        config = configured()
        payload = dict(date_s='2027-01-02', hour='4', person='2', fare='100')
        p.apply_booking_price(payload, 'vip', config)
        self.assertEqual(payload['price'], '4952')  # 650 * 8 / 1.05
        for payway in ['信用卡', 'ATM', '儲值金']:
            sent = q._build_booking_submit_data(payload, 'token', payway, '2027-01-02_08:00-12:00')
            self.assertEqual(sent['price'], '4952')
            self.assertEqual(sent['fare'], '100')

    def test_existing_order_uses_balance_not_payment(self):
        import quick_order as q
        for balance, expected in [(0, '7238'), (20, '4952')]:
            for payway in ['信用卡', 'ATM', '儲值金']:
                with patch.dict(os.environ, {'SERVICE_PRICING_JSON': json.dumps(configured())}), \
                     patch.object(q, '_configure_environment', return_value='https://example.invalid'), \
                     patch.object(q, '_get_booking_token_for_payway', return_value='token'), \
                     patch.object(q, 'resolve_backend_booking_address', return_value=({'address':'test'}, {}, {})), \
                     patch.object(q, 'calculate_hour', return_value={'data': {'price': 1}}), \
                     patch.object(q, '_query_booking_slot_with_lemon_retry', side_effect=RuntimeError('stop')) as query:
                    with self.assertRaisesRegex(RuntimeError, 'stop'):
                        q.quick_create_order('dev', payway, '', {'session': Mock(), 'phone':'0900000000', 'member_payload': {'member': {'member_id':'1'}, 'storedValue': balance}}, 'test', '1', '2027-01-02', '08:00-12:00', '4')
                    self.assertEqual(query.call_args.args[3]['price'], expected)

    def test_makeup_and_time_changes_use_period(self):
        import quick_order as q
        from memo_system import change_order as c
        with patch.dict(os.environ, {'SERVICE_PRICING_JSON': json.dumps(configured())}):
            plan = q.calc_stored_value_plan(100, total_person_hours=8, service_date='2027-01-02')
            self.assertEqual(plan['dummy_price'], 5200)
            self.assertEqual(plan['coupon_a'], 5100)
            self.assertEqual(plan['coupon_b'], 100)
            for balance, rate in [('0', 950), ('1', 650)]:
                result = c.calc_time_change_fee(date(2027,1,2), 1.5, 2, order={'pricing_balance':balance})
                self.assertEqual(result['amount'], rate * 3)

class PricingIntegrationTest(unittest.TestCase):
    def test_change_fee_uses_configured_regular_price(self):
        from memo_system import change_order as c
        order = dict(payway='儲值金', pricing_balance='0', service_hours=4, cleaner_count=2, total=100, travel_fee=0)
        with patch.dict(os.environ, {'SERVICE_PRICING_JSON': json.dumps(configured())}):
            for days, expected in [(4, 0), (3, 2280), (2, 2280), (1, 3800), (0, 3800)]:
                with patch.object(c, '_count_workdays_before', return_value=days):
                    self.assertEqual(c.calc_change_fee(order, date(2027,1,2))['change_fee'], expected)

    def test_zero_balance_skips_stored_order(self):
        import quick_order as q
        ctx = dict(balance=0, plan={}, day_type='週末', address='test', region='台北')
        with patch.object(q, '_stored_value_makeup_context', return_value=ctx), patch.object(q, 'create_coupon') as coupon, patch.object(q, 'quick_create_order') as create:
            result = q.stored_value_makeup_create_stored_order('dev', '', '', '0900000000', '1', '2027-01-02', '08:00-12:00', 4, 2)
            self.assertTrue(result['skipped_stored_order'])
            coupon.assert_not_called()
            create.assert_not_called()

    def test_settings_form_has_twelve_rates_and_saves(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SERVICE_PRICING_FILE': folder + '/prices.json', 'SERVICE_PRICING_JSON': ''}):
            app = AppTest.from_string('import streamlit as st\nfrom service_pricing import render_settings\nrender_settings(st)').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.number_input), 12)
            app.number_input[0].set_value(555.25)
            app.checkbox[0].check()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(p.load_config()['periods']['normal']['rates']['vip']['weekday'], 555.25)


if __name__ == '__main__':
    unittest.main()
