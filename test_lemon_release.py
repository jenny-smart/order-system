import unittest
from unittest.mock import Mock, patch

import pandas as pd
import orders  # noqa: F401
import shared.cleaner_shift as shifts
import shared.selected_row_status_guard as guard

SCHEDULE = '''<table><tr><th></th><th>14:00-17:00</th><th>14:00-18:00</th></tr>
<tr><td>11-18 (三)</td><td>未配班 4 人 4檸檬人50 4檸檬人40</td>
<td><div>11-09 鄭心怡 4檸檬人10 X 4檸檬人20</div><p>未配班 4 人 4檸檬人50 4檸檬人40 4檸檬人30 48朱可玉4</p></td></tr></table>'''


def sess(html):
    s = Mock()
    s.get.return_value = Mock(status_code=200, text=html)
    return s


class ReleaseTest(unittest.TestCase):
    def test_parse_unassigned_lemons_only_from_unassigned_block(self):
        self.assertEqual(shifts.schedule_unassigned_lemons(sess(SCHEDULE), 'b', '2026-11-18', '14:00-18:00'),
                         {'檸檬人50', '檸檬人40', '檸檬人30'})

    def test_releases_only_unused_added_lemons(self):
        added = [('1', '檸檬人10'), ('2', '檸檬人20'), ('3', '檸檬人30'), ('4', '檸檬人40'), ('5', '檸檬人50')]
        with patch.object(shifts, '_remove_cleaner_shift', return_value=(True, '')) as rm:
            res = shifts.release_unused_lemon_shifts(sess(SCHEDULE), 'b', '2026-11-18', '14:00-18:00', added)
        self.assertEqual(sorted(c.args[3] for c in rm.call_args_list), ['檸檬人30', '檸檬人40', '檸檬人50'])
        self.assertIn('已取消勾班', res['message'])

    def test_unknown_schedule_releases_all_only_when_failed(self):
        s = Mock(); s.get.return_value = Mock(status_code=500, text='')
        with patch.object(shifts, '_remove_cleaner_shift', return_value=(True, '')) as rm:
            shifts.release_unused_lemon_shifts(s, 'b', '2026-11-18', '14:00-18:00', [('1', '檸檬人10')])
            rm.assert_not_called()
            shifts.release_unused_lemon_shifts(s, 'b', '2026-11-18', '14:00-18:00', [('1', '檸檬人10')], order_failed=True)
            rm.assert_called_once()

    def test_failed_order_releases_all_even_if_not_in_unassigned(self):
        with patch.object(shifts, '_remove_cleaner_shift', return_value=(True, '')) as rm:
            shifts.release_unused_lemon_shifts(sess(SCHEDULE), 'b', '2026-11-18', '14:00-18:00',
                                               [('1', '檸檬人1'), ('2', '檸檬人2')], order_failed=True)
        self.assertEqual(rm.call_count, 2)

    def test_remove_keeps_other_shifts(self):
        s = Mock()
        s.post.return_value = Mock(status_code=200)
        states = [('t', {'2026-11-18_2': '1400-1800', '2026-11-19_1': '0900-1200'}, {'_method': 'PUT'}, ''),
                  ('t', {'2026-11-19_1': '0900-1200'}, {}, '')]
        with patch.object(shifts, '_read_shift_state', side_effect=states):
            ok, _ = shifts._remove_cleaner_shift(s, 'b', '9', '檸檬人1', '2026-11-18', '下4')
        self.assertTrue(ok)
        data = s.post.call_args.kwargs['data']
        self.assertNotIn('shift_2026-11-18_2', data)
        self.assertEqual(data['shift_2026-11-19_1'], '0900-1200')
        self.assertEqual(data['_method'], 'PUT')


class BatchReleaseTest(unittest.TestCase):
    def test_batch_releases_after_retry(self):
        from test_batch_booking_safety import _row
        row = pd.Series(_row(2))
        first = {2: {'結果': '失敗', '原因': '無班表', '_查詢班表可派人數': 4}}
        second = {2: {'結果': '成功', '訂單編號': 'LC1'}}
        with patch.object(orders, 'process_one_group', side_effect=[first, second]), \
             patch.object(orders, 'ensure_lemon_cleaner_shifts', return_value={'success': True, 'assigned': ['檸檬人10'], 'assigned_ids': ['1']}), \
             patch.object(orders, 'get_csrf_token', return_value='t2'), \
             patch.object(shifts, 'release_unused_lemon_shifts', return_value={'message': 'x'}) as rel:
            guard.process_one_group_with_lemon_retry(object(), [(2, row)], 't', None, '台北', allow_auto_lemon_shift=True, logger=lambda m: None)
        rel.assert_called_once()
        self.assertEqual(rel.call_args.args[4], [('1', '檸檬人10')])
        self.assertFalse(rel.call_args.kwargs['order_failed'])


if __name__ == '__main__':
    unittest.main()


class QuickReleaseTest(unittest.TestCase):
    def test_quick_releases_tracked_on_failure(self):
        import quick_order as q

        def impl(*a, **k):
            q._LEMON_TRACKER.get().append({'session': 's', 'base_url': 'b', 'date': 'd', 'period': 'p', 'added': [('1', '檸檬人1')]})
            raise Exception('boom')
        with patch.object(q, '_quick_create_order_impl', side_effect=impl), \
             patch.object(q, 'release_unused_lemon_shifts', return_value={'message': '已取消'}) as rel:
            with self.assertRaisesRegex(Exception, 'boom.*已取消'):
                q.quick_create_order('dev')
        self.assertTrue(rel.call_args.kwargs['order_failed'])

    def test_quick_adds_one_more_only_when_still_missing(self):
        import quick_order as q
        SLOT = '2026-11-18_14:00-18:00'
        ok = '[{"date":"2026-11-18","section":"14:00-18:00","cleaner":["a","b","c"]}]'
        steps = [{'success': True, 'assigned': ['檸檬人1'], 'assigned_ids': ['1']},
                 {'success': True, 'assigned': ['檸檬人2'], 'assigned_ids': ['2']}]
        with patch.object(q.orders, 'get_all_sections_raw', side_effect=['[]', '[]', ok]), \
             patch.object(q, 'count_section_available', return_value=2), \
             patch.object(q, 'ensure_lemon_cleaner_shifts', side_effect=steps) as shift, \
             patch.object(q, '_get_booking_token_for_payway', return_value='t'):
            q._query_booking_slot_with_lemon_retry(object(), 'b', '信用卡', {'person': '3'}, 't', SLOT, True)
        self.assertEqual([c.kwargs['person_count'] for c in shift.call_args_list], ['1', '1'])
