import unittest
from unittest.mock import Mock, patch

import orders  # noqa: F401  先載入 orders，避免 shared.cleaner_shift 循環匯入
import shared.cleaner_shift as shifts


class LemonShiftConflictTest(unittest.TestCase):
    """檸檬人補班只排除衝突班別，不因當天有其他班就整天排除。"""

    def run_set(self, before, after=None, status=200):
        session = Mock()
        session.post.return_value = Mock(status_code=status)
        replies = [('csrf', [('shift_2026-09-26_1', 'v1')], set(before), '')]
        if after is not None:
            replies.append(('csrf', [], set(after), ''))
        with patch.object(shifts, '_get_cleaner_shift_form_info', side_effect=replies):
            result = shifts._set_cleaner_shift_if_available(session, 'base', '9', '檸檬人4', '2026-09-26', '下3')
        return result, session

    def test_morning_shift_does_not_block_afternoon_target(self):
        result, session = self.run_set({'上3'}, after={'上3', '下3'})
        self.assertTrue(result['success'])
        fields = session.post.call_args.kwargs['data']
        self.assertIn(('shift_2026-09-26_1', 'v1'), fields)
        self.assertIn(('shift_2026-09-26_2', shifts._shift_code_to_value('下3')), fields)

    def test_conflicting_shift_is_excluded(self):
        result, session = self.run_set({'下2'})
        self.assertFalse(result['success'])
        self.assertTrue(result['protected_existing_shift'])
        session.post.assert_not_called()

    def test_full_day_shift_conflicts(self):
        result, session = self.run_set({'全8'})
        self.assertFalse(result['success'])
        session.post.assert_not_called()

    def test_same_target_already_checked_is_skipped(self):
        result, session = self.run_set({'下3'})
        self.assertFalse(result['success'])
        self.assertTrue(result['already_checked'])
        session.post.assert_not_called()

    def test_post_must_be_confirmed_by_reload(self):
        result, _ = self.run_set(set(), after=set())
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
