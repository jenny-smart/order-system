"""Run the backend's own address button; never infer service areas locally."""
import shutil
from urllib.parse import parse_qs, urlparse


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


def query_native_address(session, base_url, member_id, address, clean_type_id):
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
            # Only the native address lookup may write an HTTP request; never submit an order.
            def restrict(route):
                request = route.request
                target = urlparse(request.url)
                if request.method not in ('GET', 'HEAD', 'OPTIONS') and not (
                    target.hostname == hostname and target.path == '/ajax/check_contain'
                ):
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', restrict)
            page.goto(origin + '/booking/single', wait_until='domcontentloaded')
            if '/login' in page.url:
                raise RuntimeError('後台地址查詢登入已失效')
            for selector, value in (('#member_id', member_id), ('#clean_type_id', clean_type_id), ('#address', address)):
                page.locator(selector).evaluate('(el, value) => { el.value = value; }', str(value))
            page.wait_for_function("typeof google !== 'undefined' && google.maps && google.maps.Geocoder")
            try:
                with page.expect_response(lambda r: urlparse(r.url).hostname == hostname and urlparse(r.url).path == '/ajax/check_contain', timeout=30000) as pending:
                    page.locator('.check_contain').click()
                response = pending.value
                if response.status != 200:
                    raise RuntimeError(f'後台查詢地區失敗（HTTP {response.status}）')
                result = _address_result(response)
            except BrowserTimeout as exc:
                message = page.locator('.sweet-alert.visible h2').all_text_contents()
                raise RuntimeError('後台查詢地區未完成：' + ('；'.join(message) or '地址定位未回覆，尚未查班表')) from exc
            # Preserve the backend session's rotated cookies for subsequent requests.
            for cookie in context.cookies([origin]):
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
            return result
        finally:
            browser.close()
