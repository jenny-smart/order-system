import unittest
from unittest.mock import Mock, MagicMock, patch
from backend_address_form import _address_result
import quick_order as q


class NativeAddressTest(unittest.TestCase):
    def test_browser_runs_only_native_lookup_and_closes(self):
        import requests
        from backend_address_form import query_native_address
        driver = MagicMock()
        runtime = driver.return_value.__enter__.return_value
        browser = runtime.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.url = 'https://example.invalid/booking/single'
        response = page.expect_response.return_value.__enter__.return_value.value
        response.status = 200
        response.json.return_value = {'return_code': '0000', 'area': {'area_id': 45, 'company_id': 1}}
        response.request.post_data = 'lat=25.1&lng=121.1'
        context.cookies.return_value = []
        with patch('playwright.sync_api.sync_playwright', driver):
            result = query_native_address(requests.Session(), 'https://example.invalid', '1', '測試地址', '1')
        page.goto.assert_called_once_with('https://example.invalid/booking/single', wait_until='domcontentloaded')
        page.locator.assert_any_call('.check_contain')
        self.assertEqual(result['area']['area_id'], 45)
        browser.close.assert_called_once()
        guard = context.route.call_args.args[1]
        route = Mock()
        route.request.method = 'POST'
        route.request.url = 'https://example.invalid/booking/single'
        guard(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    def test_native_response_uses_backend_area_and_native_request_coordinates(self):
        response = Mock()
        response.json.return_value = {'return_code': '0000', 'area': {'area_id': 45, 'company_id': 1}}
        response.request.post_data = 'lat=25.1&lng=121.1'
        result = _address_result(response)
        self.assertEqual(result['area'], {'area_id': 45, 'company_id': 1, 'lat': '25.1', 'lng': '121.1'})

    def test_rejection_preserves_backend_message(self):
        response = Mock()
        response.json.return_value = {'return_code': '1001', 'description': '此地址尚未開放服務'}
        with self.assertRaisesRegex(RuntimeError, '此地址尚未開放服務'):
            _address_result(response)

    def test_missing_region_does_not_reach_schedule(self):
        response = Mock()
        response.json.return_value = {'return_code': '0000', 'area': {}}
        with self.assertRaisesRegex(RuntimeError, '尚未查班表'):
            _address_result(response)

    def test_new_address_uses_native_button_not_empty_coordinate_api(self):
        reply = {'return_code': '0000', 'area': {'area_id': 45, 'company_id': 1, 'lat': '25.1', 'lng': '121.1'}}
        with patch('backend_address_form.query_native_address', return_value=reply) as native, \
             patch.object(q, 'check_contain') as direct, \
             patch.object(q, 'geocode_address') as external:
            info, _, _ = q.resolve_backend_booking_address('session', {'member': {'member_id': 1}}, '測試新地址', 'token', '1')
        native.assert_called_once_with('session', q.orders.BASE_URL, 1, '測試新地址', '1')
        direct.assert_not_called()
        external.assert_not_called()
        self.assertEqual(info['area_id'], 45)
        self.assertEqual(info['lng'], '121.1')

if __name__ == '__main__':
    unittest.main()
