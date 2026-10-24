import unittest

from memo_system import shift


class ShiftConflictWarningTests(unittest.TestCase):
    def test_extension_combos_are_not_conflicts(self):
        # 全8＋上4：提早到 08:30；全6＋下3／下4：延到 17:00／18:00
        self.assertEqual(shift.check_merged_conflicts({"2027-03-01_all": "8", "2027-03-01_1": "0830-1230"}), [])
        self.assertEqual(shift.check_merged_conflicts({"2027-03-01_all": "6", "2027-03-01_2": "1400-1700"}), [])
        self.assertEqual(shift.check_merged_conflicts({"2027-03-01_all": "6", "2027-03-01_2": "1400-1800"}), [])

    def test_half_day_inside_full_day_still_warns(self):
        self.assertEqual(len(shift.check_merged_conflicts({"2027-03-01_all": "8", "2027-03-01_1": "0900-1200"})), 1)
        self.assertEqual(len(shift.check_merged_conflicts({"2027-03-01_all": "8", "2027-03-01_2": "1400-1800"})), 1)

    def test_half_days_only_no_warning(self):
        self.assertEqual(shift.check_merged_conflicts({"2027-03-01_1": "0830-1230", "2027-03-01_2": "1400-1700"}), [])


if __name__ == "__main__":
    unittest.main()
