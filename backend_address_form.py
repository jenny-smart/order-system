"""Run the backend's own address button; never infer service areas locally."""
import shutil
from urllib.parse import parse_qs, urlencode, urlparse


def fill_missing_coordinates(post_data, address, geocode):
    """後台頁面送出查詢地區時若經緯度空白（頁面地圖定位失敗），用伺服器端 geocode 補上。

    其他欄位照頁面原樣送出，服務區域仍由後台判斷。回傳（新的 post_data, 補上的 (lat, lng) 或 None）。
    """
    data = parse_qs(post_data or "", keep_blank_values=True)
    if (data.get("lat") or [""])[0].strip() and (data.get("lng") or [""])[0].strip():
        return post_data, None
    lat, lng = geocode(address)
    if not lat or not lng:
        return post_data, None
    data["lat"], data["lng"] = [str(lat)], [str(lng)]
    return urlencode(data, doseq=True), (str(lat), str(lng))


def _address_result(response):
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError('後台查詢地區回覆格式異常')
    if payload.get('return_code') != '0000':
        raise RuntimeError('後台查詢地區回覆：' + str(payload.get('description') or payload.get('message') or payload.get('return_code')))
    area = dict(payload.get('area') or {})
    if not area.get('area_id') or not area.get('company_id'):
        raise RuntimeError('後台查詢地區未回傳服務區域，尚未查班表')
    # Coordinates are those sent by the native button, not an independently selected location.
    sent = parse_qs(response.request.post_data or '')
    for field in ('lat', 'lng'):
        if sent.get(field):
            area[field] = sent[field][0]
    return {**payload, 'area': area}


def orders_has_maps_key():
    try:
        import orders
        return bool(orders.GOOGLE_MAPS_API_KEY)
    except Exception:
        return False


def _native_form_result(page):
    """Read the result exactly as the backend form would use it for later steps."""
    area = page.evaluate(
        """() => {
            const value = selector => (document.querySelector(selector) || {}).value || '';
            return {
                area_id: value('#area_id'),
                company_id: value('#company_id'),
                lat: value('#lat'),
                lng: value('#lng'),
            };
        }"""
    )
    area = dict(area or {})
    if not area.get('area_id') or not area.get('company_id'):
        raise RuntimeError('後台查詢地區未帶入服務區域，尚未查班表')
    return {'return_code': '0000', 'area': area}


def _select_option(page, selector, value):
    """依後台下拉的 value 選取；value 對不到時才比對選項文字（臺／台視為相同）。"""
    matched = page.locator(selector).evaluate(
        """(el, value) => {
            const norm = text => String(text || '').trim().replace(/臺/g, '台');
            const options = Array.from(el.options || []);
            const option = options.find(o => o.value === String(value))
                || options.find(o => norm(o.textContent) === norm(value));
            if (!option) return false;
            el.value = option.value;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(el).trigger('change');
            return true;
        }""",
        str(value),
    )
    if not matched:
        raise RuntimeError(f'後台下拉選單 {selector} 沒有「{value}」選項，尚未查班表')


def _form_state(page):
    """查詢地區失敗時附上表單目前的值，方便判斷卡在哪一步。"""
    try:
        state = page.evaluate(
            """() => {
                const value = selector => (document.querySelector(selector) || {}).value || '';
                return ['#city', '#area', '#address', '#lat', '#lng', '#area_id', '#company_id']
                    .map(selector => selector.slice(1) + '=' + value(selector)).join('，');
            }"""
        )
    except Exception:
        return ''
    return f'（表單狀態：{state}）' if state else ''


def query_native_address(
    session, base_url, member_id, address, clean_type_id, city="", country_id="",
    address_id="", phone="", address_detail="", district="",
):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    except ImportError as exc:
        raise RuntimeError('後台地址查詢所需瀏覽器尚未安裝，請更新部署套件') from exc
    origin = base_url.rstrip('/')
    hostname = urlparse(origin).hostname
    cookies = []
    for cookie in session.cookies:
        domain = cookie.domain.lstrip('.')
        if domain and not (hostname == domain or hostname.endswith('.' + domain)):
            continue
        cookies.append({'name': cookie.name, 'value': cookie.value,
                        'domain': cookie.domain or hostname, 'path': cookie.path or '/',
                        'secure': cookie.secure})
    with sync_playwright() as runtime:
        executable = shutil.which('chromium') or shutil.which('chromium-browser')
        options = {'headless': True}
        if executable:
            options['executable_path'] = executable
        try:
            browser = runtime.chromium.launch(**options)
        except Exception as exc:
            raise RuntimeError('後台地址查詢瀏覽器無法啟動，請確認部署已安裝 Chromium') from exc
        try:
            context = browser.new_context()
            context.add_cookies(cookies)
            page = context.new_page()
            console_errors = []
            page.on('console', lambda msg: console_errors.append(msg.text) if msg.type in ('error', 'warning') else None)
            filled = {}

            def fill_coordinates(route, request):
                # 頁面地圖定位沒拿到經緯度時，伺服器端補上再送給後台判斷服務區域。
                try:
                    import orders
                    new_data, coords = fill_missing_coordinates(request.post_data, address, orders.geocode_address)
                except Exception:
                    new_data, coords = request.post_data, None
                if coords:
                    filled['coords'] = coords
                    route.continue_(post_data=new_data)
                else:
                    route.continue_()

            page.route('**/ajax/check_contain*', fill_coordinates)
            # Follow the backend page as-is. This helper only fills the form and
            # clicks 查詢地區; it never clicks 計算時數、查詢班表 or 送出.
            page.goto(origin + '/booking/single', wait_until='domcontentloaded')
            if '/login' in page.url:
                raise RuntimeError('後台地址查詢登入已失效')
            try:
                # 照後台畫面順序：選購買項目後才出現手機欄，按「查詢會員」後才出現地址區塊
                # 與「查詢地區」按鈕；購買項目要觸發 change，頁面（Vue）才會記住，否則重繪時被清空。
                _select_option(page, '#clean_type_id', clean_type_id)
                if address_id and not str(phone or '').strip():
                    raise RuntimeError('既有地址必須先用手機查詢會員，不能改走地址輸入欄位')
                page.locator('#phone').fill(str(phone))
                page.locator('input.get_member').click()
                page.wait_for_function("() => String((document.querySelector('#member_id') || {}).value || '').trim()")
                # 舊客有上次訂單時，頁面會在查詢會員 300ms 後帶入上次的縣市／鄉鎮市區，等它跑完再操作。
                page.wait_for_timeout(500)
                if address_id:
                    page.wait_for_function(
                        "addressId => Array.from(document.querySelectorAll('select[name=\"addressId\"] option')).some(o => o.value === String(addressId))",
                        str(address_id),
                    )
                    # 命中舊客下拉地址時只選 addressId；由後台帶入地址、區域與客服備註。
                    page.locator('select[name="addressId"]').evaluate(
                        '(el, value) => { el.value = String(value); el.dispatchEvent(new Event("change", {bubbles:true})); }',
                        str(address_id),
                    )
                else:
                    # 下拉選單沒有該地址，才使用新地址欄位：先選縣市、再選鄉鎮市區，
                    # 剩餘地址填空白欄位，最後按後台自己的「查詢地區」。
                    page.locator('#address').fill('')
                    if city:
                        _select_option(page, '#city', city)
                    if district or country_id:
                        # 鄉鎮市區選項由選縣市後的頁面腳本產生，選項出現後才照畫面文字選取。
                        target = district or country_id
                        try:
                            page.wait_for_function(
                                """value => Array.from(document.querySelectorAll('#area option')).some(
                                    o => o.value === String(value) || o.textContent.trim() === String(value))""",
                                arg=str(target), timeout=15000,
                            )
                        except BrowserTimeout as exc:
                            raise RuntimeError(f'後台鄉鎮市區選單沒有「{target}」（{city}），尚未查班表') from exc
                        _select_option(page, '#area', target)
                    page.locator('#address').fill(str(address_detail or address))
                    # 「查詢地區」由後台頁面用 Google 地圖定位；地圖程式載入前按下不會有任何反應。
                    try:
                        page.wait_for_function(
                            "() => typeof google !== 'undefined' && !!google.maps && typeof google.maps.Geocoder === 'function'",
                            timeout=30000,
                        )
                    except BrowserTimeout as exc:
                        raise RuntimeError('後台頁面的地圖定位尚未載入，無法按查詢地區，尚未查班表') from exc
                    page.locator('.check_contain').click()
                # Follow the backend form state instead of requiring a particular network
                # response. Once these fields exist, the UI itself is ready for 計算時數.
                page.wait_for_function(
                    """() => ['#area_id', '#company_id'].every(selector => {
                        const el = document.querySelector(selector);
                        return el && String(el.value || '').trim();
                    })""",
                    timeout=30000,
                )
                result = _native_form_result(page)
                if filled.get('coords'):
                    result['area']['lat'], result['area']['lng'] = filled['coords']
            except BrowserTimeout as exc:
                message = page.locator('.sweet-alert.visible h2').all_text_contents()
                hint = '；頁面地圖訊息：' + '｜'.join(console_errors[:2]) if console_errors else ''
                if not filled.get('coords') and not orders_has_maps_key():
                    hint += '；伺服器端未設定 GOOGLE_MAPS_API_KEY，無法補經緯度'
                raise RuntimeError(
                    '後台查詢地區未完成：' + ('；'.join(message) or '服務區域欄位未帶入，尚未查班表')
                    + _form_state(page) + hint
                ) from exc
            # Preserve the backend session's rotated cookies for subsequent requests.
            for cookie in context.cookies([origin]):
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
            return result
        finally:
            browser.close()
