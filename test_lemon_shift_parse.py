import unittest
from unittest.mock import Mock, patch

import orders  # noqa: F401
import shared.cleaner_shift as shifts

PAGE = '''<meta name="csrf-token" content="tok">
<div>專員：<b>檸檬人1</b></div>
<form><input type="hidden" name="_token" value="tok"><input type="hidden" name="_method" value="PUT">
<input type="radio" name="shift_2026-11-18_2" value="4" data-checked="0" onclick="this.checked=true">
<input type="radio" name="shift_2026-11-18_2" value="" checked>
<input type="radio" name="shift_2026-11-18_1" value="3" class="checked">
<input type="radio" name="shift_2026-11-19_2" value="1400-1800" checked>
</form>'''


class ParseTest(unittest.TestCase):
    def test_unchecked_day_is_not_reported_busy(self):
        csrf, fields, codes = shifts._parse_cleaner_shift_page(PAGE, '2026-11-18')
        self.assertEqual(csrf, 'tok')
        self.assertEqual(codes, set())
        self.assertIn(('shift_2026-11-19_2', '1400-1800'), fields)
        self.assertFalse(any(k.startswith('shift_2026-11-18') for k, _ in fields))
        self.assertIn(('_method', 'PUT'), fields)

    def test_real_checked_detected(self):
        _, _, codes = shifts._parse_cleaner_shift_page(PAGE, '2026-11-19')
        self.assertEqual(codes, {'下4'})

    def test_name_parse(self):
        self.assertEqual(shifts._parse_cleaner_name_on_shift_page(PAGE), '檸檬人1')


class MemoSharesParserTest(unittest.TestCase):
    def test_memo_and_orders_use_same_parser(self):
        import memo_system.shift as memo_shift
        self.assertIs(memo_shift.parse_shift_page, shifts.parse_shift_page)
        self.assertIs(memo_shift.build_shift_payload, shifts.build_shift_payload)


class KeepGoingTest(unittest.TestCase):
    def test_keeps_searching_until_filled(self):
        batches = [[('1', '檸檬人1'), ('2', '檸檬人2')],
                   [('1', '檸檬人1'), ('2', '檸檬人2'), ('3', '檸檬人3'), ('4', '檸檬人4')]]
        busy = {'1', '2'}

        def fake_set(_s, _b, cid, name, _d, _c):
            if cid in busy:
                return {'success': False, 'name': name, 'already_checked': True}
            return {'success': True, 'name': name}
        with patch.object(shifts, '_search_lemon_cleaners', side_effect=batches + [batches[-1]]), \
             patch.object(shifts, '_set_cleaner_shift_if_available', side_effect=fake_set):
            r = shifts.ensure_lemon_cleaner_shifts(Mock(), 'b', '2026-11-18', '14:00-18:00', 2)
        self.assertTrue(r['success'])
        self.assertEqual(r['assigned'], ['檸檬人3', '檸檬人4'])

    def test_failure_message_is_summary(self):
        with patch.object(shifts, '_search_lemon_cleaners', return_value=[('1', '檸檬人1')]), \
             patch.object(shifts, '_set_cleaner_shift_if_available', return_value={'success': False, 'already_checked': True}):
            r = shifts.ensure_lemon_cleaner_shifts(Mock(), 'b', '2026-11-18', '14:00-18:00', 2)
        self.assertFalse(r['success'])
        self.assertIn('已檢查 1 位檸檬人', r['message'])
        self.assertIn('1 位該時段已有班', r['message'])


if __name__ == '__main__':
    unittest.main()
