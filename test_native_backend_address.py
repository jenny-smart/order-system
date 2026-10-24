import unittest
from unittest.mock import Mock, MagicMock, patch
from backend_address_form import _address_result, _native_form_result
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
        page.evaluate.return_value = {'area_id': '45', 'company_id': '1', 'lat': '25.1', 'lng': '121.1'}
        context.cookies.return_value = []
        with patch('playwright.sync_api.sync_playwright', driver):
            result = query_native_address(requests.Session(), 'https://example.invalid', '1', '測試地址', '1', phone='0912345678')
        page.goto.assert_called_once_with('https://example.invalid/booking/single', wait_until='domcontentloaded')
        page.locator.assert_any_call('.check_contain')
        self.assertEqual(result['area']['area_id'], '45')
        page.expect_response.assert_not_called()
        context.route.assert_not_called()
        browser.close.assert_called_once()

    def test_native_response_uses_backend_area_and_native_request_coordinates(self):
        response = Mock()
        response.json.return_value = {'return_code': '0000', 'area': {'area_id': 45, 'company_id': 1}}
        response.request.post_data = 'lat=25.1&lng=121.1'
        result = _address_result(response)
        self.assertEqual(result['area'], {'area_id': 45, 'company_id': 1, 'lat': '25.1', 'lng': '121.1'})

    def test_native_form_result_uses_backend_ready_fields(self):
        page = Mock()
        page.evaluate.return_value = {'area_id': '45', 'company_id': '1', 'lat': '25.1', 'lng': '121.1'}
        self.assertEqual(_native_form_result(page)['area']['area_id'], '45')

    def test_native_form_result_requires_service_area(self):
        page = Mock()
        page.evaluate.return_value = {'area_id': '', 'company_id': ''}
        with self.assertRaisesRegex(RuntimeError, '服務區域'):
            _native_form_result(page)

    def test_saved_address_selects_dropdown_instead_of_typing_address(self):
        import requests
        from backend_address_form import query_native_address
        driver = MagicMock()
        runtime = driver.return_value.__enter__.return_value
        browser = runtime.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.url = 'https://example.invalid/booking/single'
        page.evaluate.return_value = {'area_id': '45', 'company_id': '1', 'lat': '25.1', 'lng': '121.1'}
        context.cookies.return_value = []
        locators = {}
        page.locator.side_effect = lambda selector: locators.setdefault(selector, MagicMock())
        with patch('playwright.sync_api.sync_playwright', driver):
            query_native_address(
                requests.Session(), 'https://example.invalid', '1', '測試地址', '1',
                address_id='302', phone='0912345678',
            )
        locators['input.get_member'].click.assert_called_once()
        locators['select[name="addressId"]'].evaluate.assert_called_once()
        self.assertNotIn('#address', locators)
        self.assertNotIn('.check_contain', locators)

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

    def test_new_address_uses_backend_native_lookup_without_direct_maps_call(self):
        address = '台北市大安區金華街233號2樓'
        with patch('backend_address_form.query_native_address', return_value={'area': {'area_id': '25', 'company_id': '1'}}) as native, \
             patch.object(q, 'check_contain', side_effect=AssertionError('must not query address')) as direct, \
             patch.object(q, 'geocode_address', side_effect=AssertionError('must not call Google')):
            info, _, _ = q.resolve_backend_booking_address('session', {'member': {'member_id': 1}}, address, 'token', '1')
        direct.assert_not_called()
        native.assert_called_once()
        self.assertEqual(info['address'], address)
        self.assertEqual(info.get('area_id'), '25')

    def test_existing_address_keeps_saved_dropdown_fields_without_lookup(self):
        address = '臺北市大安區金華街233號2樓'
        stored = {'id': 7, 'address': address, 'areaId': '25', 'companyId': '1', 'lat': '25.1', 'lng': '121.1'}
        with patch('backend_address_form.query_native_address', side_effect=AssertionError('saved dropdown must not be located')) as native, \
             patch.object(q, 'check_contain', side_effect=AssertionError('must not query address')) as direct:
            info, _, _ = q.resolve_backend_booking_address('session', {'member': {'member_id': 1, 'memberAddressList': [stored]}}, address, 'token', '1')
        direct.assert_not_called()
        native.assert_not_called()
        self.assertEqual(str(info['area_id']), '25')


class PostalCodeAddressSplitTest(unittest.TestCase):
    def test_leading_postal_code_is_removed_before_city_dropdown(self):
        parts = q._split_booking_address("108臺北市萬華區華江里環河南路二段250巷42弄5號3")
        self.assertEqual(parts["city"], "台北市")
        self.assertEqual(parts["district"], "萬華區")
        self.assertTrue(parts["country_id"])
        self.assertEqual(parts["detail"], "華江里環河南路二段250巷42弄5號3")


if __name__ == "__main__":
    unittest.main()


class NativeNewAddressFormTest(unittest.TestCase):
    def test_new_address_selects_city_district_fills_rest_then_clicks(self):
        import requests
        from backend_address_form import query_native_address
        driver = MagicMock()
        page = driver.return_value.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
        page.url = 'https://example.invalid/booking/single'
        page.evaluate.return_value = {'area_id': '45', 'company_id': '1'}
        driver.return_value.__enter__.return_value.chromium.launch.return_value.new_context.return_value.cookies.return_value = []
        with patch('playwright.sync_api.sync_playwright', driver):
            query_native_address(
                requests.Session(), 'https://example.invalid', '1', '台北市萬華區環河南路二段250巷', '1',
                city='台北市', country_id='13', district='萬華區', address_detail='環河南路二段250巷',
                phone='0912345678',
            )
        selectors = [c.args[0] for c in page.locator.call_args_list]
        # 照後台畫面順序：購買項目 → 手機查詢會員（地址區塊才出現）→ 縣市 → 鄉鎮市區 → 地址 → 查詢地區
        self.assertLess(selectors.index('#clean_type_id'), selectors.index('#phone'))
        self.assertLess(selectors.index('input.get_member'), selectors.index('#city'))
        self.assertLess(selectors.index('#city'), selectors.index('#area'))
        last_address = len(selectors) - 1 - selectors[::-1].index('#address')
        self.assertLess(selectors.index('#area'), last_address)
        self.assertLess(last_address, selectors.index('.check_contain'))
        filled = [c.args[1] for c in page.locator.return_value.evaluate.call_args_list]
        self.assertIn('1', filled)
        self.assertIn('萬華區', filled)
        typed = [c.args[0] for c in page.locator.return_value.fill.call_args_list]
        self.assertEqual(typed, ['0912345678', '', '環河南路二段250巷'])


def test_fill_missing_coordinates_only_when_page_left_them_blank():
    from backend_address_form import fill_missing_coordinates
    from urllib.parse import parse_qs
    geocode = lambda address: ('24.99', '121.50')
    data, coords = fill_missing_coordinates('memberId=1&address=x&lat=&lng=', '新北市中和區中山路二段457號20樓', geocode)
    assert coords == ('24.99', '121.50')
    assert parse_qs(data)['lat'] == ['24.99'] and parse_qs(data)['address'] == ['x']
    same, coords = fill_missing_coordinates('lat=25.0&lng=121.5', 'a', geocode)
    assert (same, coords) == ('lat=25.0&lng=121.5', None)
    same, coords = fill_missing_coordinates('lat=&lng=', 'a', lambda a: (None, None))
    assert coords is None
