import json
import unittest
from unittest.mock import Mock
import orders


class SectionRegionTest(unittest.TestCase):
    def response(self, data, status=200):
        return Mock(status_code=status, url='https://example.invalid/ajax/get_section',
                    text=json.dumps(data), json=Mock(return_value=data))

    def test_missing_region_fields_do_not_override_backend_empty_result(self):
        for field in ('area_id', 'company_id'):
            for empty in ('', '0', 0, None):
                with self.subTest(field=field, value=empty):
                    data = {'area_id': '50', 'company_id': '2', field: empty}
                    self.assertEqual(orders._checked_booking_sections_response(self.response([]), data), '[]')

    def test_valid_region_empty_result_remains_backend_availability(self):
        result = orders._checked_booking_sections_response(self.response([]), {'area_id': '50', 'company_id': '2'})
        self.assertEqual(result, '[]')

    def test_coordinates_are_not_required_if_backend_returns_slots(self):
        slots = [{'date': '2026-09-26', 'section': '09:00-11:00', 'cleaner': ['人員A', '人員B']}]
        result = orders._checked_booking_sections_response(self.response(slots), {'area_id': '50', 'company_id': '2', 'lat': '', 'lng': ''})
        self.assertEqual(json.loads(result), slots)

    def test_available_slots_are_accepted_without_region_or_coordinates(self):
        slots = [{'date': '2026-11-11', 'section': '09:00-12:00', 'cleaner': ['人員A', '人員B']}]
        result = orders._checked_booking_sections_response(self.response(slots), {})
        self.assertEqual(json.loads(result), slots)

    def test_http_error_is_not_treated_as_no_staff(self):
        with self.assertRaisesRegex(Exception, 'HTTP 500'):
            orders._checked_booking_sections_response(self.response({}, 500), {})

    def test_both_single_and_batch_queries_return_backend_result_without_region_gate(self):
        for query in (orders.get_all_sections_raw, orders.get_section_raw):
            with self.subTest(query=query.__name__):
                session = Mock()
                session.post.return_value = self.response([])
                args = (session, {'person': '2'}, 'token')
                if query is orders.get_section_raw:
                    args += ('2026-09-26_09:00-11:00',)
                self.assertEqual(query(*args), '[]')
