import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from memo_system import change_order as c


class ChangeFeeCutoffTest(unittest.TestCase):
    def test_cutoff_boundary(self):
        for moment, expected in [(datetime(2026, 10, 6, 17, 29), 2),
                                 (datetime(2026, 10, 6, 17, 30), 2),
                                 (datetime(2026, 10, 6, 17, 30, 1), 1),
                                 (datetime(2026, 10, 6, 18), 1)]:
            with self.subTest(moment=moment):
                self.assertEqual(c._count_workdays_before(date(2026, 10, 8), moment), expected)

    def test_weekends_and_holidays(self):
        for moment in [datetime(2026, 9, 24, 18), datetime(2026, 9, 25, 10),
                       datetime(2026, 9, 26, 10)]:
            self.assertEqual(c._change_processing_date(moment), date(2026, 9, 28))
            self.assertEqual(c._count_workdays_before(date(2026, 9, 29), moment), 1)

    def test_timezone_and_default_clock(self):
        moment = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        self.assertEqual(c._count_workdays_before(date(2026, 10, 8), moment), 1)
        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 6, 18, tzinfo=tz)
        with patch.object(c, 'datetime', FixedClock):
            self.assertEqual(c._count_workdays_before(date(2026, 10, 8)), 1)

    def test_same_day_past_and_date_compatibility(self):
        moment = datetime(2026, 10, 6, 18)
        for service in [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]:
            self.assertEqual(c._count_workdays_before(service, moment), 0)
        self.assertEqual(c._count_workdays_before(date(2026, 10, 8), date(2026, 10, 6)), 2)

    def test_fee_changes_for_vip_and_regular(self):
        for order, expected in [(dict(payway='儲值金'), 900),
                                (dict(payway='ATM'), 1500)]:
            order.update(service_hours=3, cleaner_count=2, total=3200, travel_fee=200)
            with patch('service_pricing.load_config', return_value={'enabled': False}):
                result = c.calc_change_fee(order, date(2026, 10, 8), today=datetime(2026, 10, 6, 18))
            self.assertEqual(result['workdays'], 1)
            self.assertEqual(result['tier'], 'near')
            self.assertEqual(result['change_fee'], expected)


if __name__ == '__main__':
    unittest.main()
