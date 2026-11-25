"""補檸檬人：已勾班且排在別人訂單裡的檸檬人要換下一位（2026-12-07 上3 實例）。"""
import unittest
from unittest.mock import Mock, patch

import orders  # noqa: F401
import shared.cleaner_shift as shifts

# 比照後台 /schedule：區域編號＋姓名＋星等；檸檬人1、2 在徐雅音的單，檸檬人4 未配班
SCHEDULE = (
    '<input id="date" value="2026-12-07"><table>'
    '<tr><td></td><td>08:30-12:30</td><td>09:00-12:00</td><td>14:00-18:00</td></tr>'
    '<tr><td>12-07<br>(一)</td>'
    '<td>11-04<br>黃千耀 V<br>48宋品鈞3 X<br>48李佩蓉4</td>'
    '<td>11-02<br>徐雅音 V<br>3檸檬人10 X<br>3檸檬人20'
    '<p style="background:#616161"><span>未配班 1 人</span><br><span>3檸檬人40</span></p></td>'
    '<td>11-02<br>王櫻娟 V<br>3檸檬人50 X<br>8吳爽1</td></tr></table>'
)


def sess():
    s = Mock()
    s.get.return_value = Mock(status_code=200, text=SCHEDULE)
    return s


class SkipBusyLemonTest(unittest.TestCase):
    def test_reads_lemons_in_overlapping_orders(self):
        busy = shifts.schedule_lemons_in_orders(sess(), 'b', '2026-12-07', '09:00-12:00')
        self.assertEqual(set(busy), {'檸檬人1', '檸檬人2'})  # 下午的檸檬人5 不重疊

    def test_unassigned_parsed_with_rating_digit(self):
        self.assertEqual(shifts.schedule_unassigned_lemons(sess(), 'b', '2026-12-07', '09:00-12:00'), {'檸檬人4'})

    def test_busy_and_unassigned_lemons_are_not_rechecked(self):
        lemons = [(str(i), f'檸檬人{i}') for i in range(1, 7)]
        with patch.object(shifts, '_search_lemon_cleaners', return_value=lemons), \
             patch.object(shifts, '_set_cleaner_shift_if_available',
                          side_effect=lambda _s, _b, cid, name, _d, _c: {'success': True, 'name': name}) as setter:
            r = shifts.ensure_lemon_cleaner_shifts(sess(), 'b', '2026-12-07', '09:00-12:00', 2)
        self.assertTrue(r['success'])
        self.assertEqual(r['assigned'], ['檸檬人3', '檸檬人5'])
        self.assertEqual([c.args[3] for c in setter.call_args_list], ['檸檬人3', '檸檬人5'])

    def test_unreadable_schedule_falls_back_to_shift_page_check(self):
        s = Mock()
        s.get.return_value = Mock(status_code=500, text='')
        with patch.object(shifts, '_search_lemon_cleaners', return_value=[('1', '檸檬人1')]), \
             patch.object(shifts, '_set_cleaner_shift_if_available', return_value={'success': True, 'name': '檸檬人1'}):
            r = shifts.ensure_lemon_cleaner_shifts(s, 'b', '2026-12-07', '09:00-12:00', 1)
        self.assertEqual(r['assigned'], ['檸檬人1'])


if __name__ == '__main__':
    unittest.main()
