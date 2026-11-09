import unittest
from unittest.mock import Mock

import orders  # noqa: F401
import shared.cleaner_shift as shifts

SCHEDULE = '''<table><tr><th></th><th>09:00-12:00</th><th>14:00-18:00</th><th>19:00-21:00</th></tr>
<tr><td>11-18 (三)</td><td><p style="background:#616161"><span>未配班 4 人</span></p></td>
<td><p style="background:#616161"><span>未配班 1 人</span><span>48余洛肇1</span></p></td><td></td></tr></table>'''


def session_with(html, status=200):
    s = Mock()
    s.get.return_value = Mock(status_code=status, text=html)
    return s


class ShortfallTest(unittest.TestCase):
    def test_counts_unassigned(self):
        self.assertEqual(shifts.count_schedule_unassigned(session_with(SCHEDULE), 'b', '2026-11-18', '14:00-18:00'), 1)
        self.assertEqual(shifts.count_schedule_unassigned(session_with(SCHEDULE), 'b', '2026-11-18', '19:00-21:00'), 0)

    def test_only_adds_missing(self):
        n, basis = shifts.lemon_shortfall(session_with(SCHEDULE), 'b', '2026-11-18', '14:00-18:00', 3)
        self.assertEqual(n, 2)
        self.assertIn('未配班 1 人', basis)

    def test_unknown_schedule_falls_back(self):
        n, _ = shifts.lemon_shortfall(session_with('', 500), 'b', '2026-11-18', '14:00-18:00', 3, 1)
        self.assertEqual(n, 2)

    def test_enough_on_schedule_but_api_has_no_slot(self):
        n, basis = shifts.lemon_shortfall(session_with(SCHEDULE), 'b', '2026-11-18', '09:00-12:00', 3)
        self.assertEqual(n, 3)
        self.assertIn('服務範圍', basis)


if __name__ == '__main__':
    unittest.main()
