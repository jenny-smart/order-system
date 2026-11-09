import json
import unittest
from unittest.mock import patch

import orders  # noqa: F401
import shared.cleaner_shift as shifts

SLOT = '2026-11-18_14:00-18:00'


class ShortfallTest(unittest.TestCase):
    def test_only_adds_missing(self):
        n, basis = shifts.lemon_shortfall(3, 1)
        self.assertEqual(n, 2)
        self.assertIn('可派 1 人', basis)

    def test_none_available_adds_all(self):
        self.assertEqual(shifts.lemon_shortfall(3, 0)[0], 3)

    def test_unknown_falls_back(self):
        self.assertEqual(shifts.lemon_shortfall(3, None, 1)[0], 2)

    def test_section_query_uses_one_person_and_counts(self):
        raw = json.dumps([{'date': '2026-11-18', 'section': '14:00-18:00', 'cleaner': ['甲', '乙']}])
        with patch.object(orders, 'get_all_sections_raw', return_value=raw) as q:
            n = shifts.count_section_available(object(), {'person': '3', 'hour': '4'}, 't', SLOT)
        self.assertEqual(n, 2)
        self.assertEqual(q.call_args.args[1]['person'], '1')

    def test_section_query_slot_missing_is_zero(self):
        with patch.object(orders, 'get_all_sections_raw', return_value='[]'):
            self.assertEqual(shifts.count_section_available(object(), {'person': '3'}, 't', SLOT), 0)


if __name__ == '__main__':
    unittest.main()
