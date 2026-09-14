import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from datetime import date
from unittest.mock import Mock


class PendingBookingTimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).parent / 'function' / 'order_creation.py').read_text())
        cls.guard = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                         and ast.unparse(node.test).startswith('_pending_before_submit and'))
        cls.code = compile(ast.fix_missing_locations(ast.Module(body=[cls.guard], type_ignores=[])), '<pending form guard>', 'exec')

    def check_form(self, old, current):
        pending = {'form_snapshot': old, 'period_s': '09:00-12:00'}
        state = SimpleNamespace(nc_pending_old=pending)
        st = SimpleNamespace(session_state=state, info=Mock())
        exec(self.code, {'_pending_before_submit': pending, '_nc_form_snapshot': current, 'st': st})
        return state.nc_pending_old

    def test_changed_three_to_four_hours_invalidates_old_booking(self):
        old = {'entries': [{'date': date(2026, 9, 26), 'period': '09:00-12:00', 'hour': 3, 'person': 2}]}
        current = {'entries': [{'date': date(2026, 9, 26), 'period': '08:30-12:30', 'hour': 4, 'person': 2}]}
        self.assertIsNone(self.check_form(old, current))

    def test_unchanged_form_keeps_pending_booking(self):
        form = {'entries': [{'period': '08:30-12:30', 'hour': 4}]}
        self.assertIsNotNone(self.check_form(form, form))

    def test_changed_lemon_switch_invalidates_old_booking(self):
        self.assertIsNone(self.check_form({'allow_lemon': False}, {'allow_lemon': True}))

    def test_batch_shift_mapping_matches_booking_period(self):
        import orders
        self.assertEqual(orders._period_to_shift_code('08:30-12:30'), '上4')
        self.assertEqual(orders._period_to_shift_code('09:00-12:00'), '上3')
