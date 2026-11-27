"""Shared, tax-inclusive person-hour prices for booking and service changes."""
import copy
import json
import os
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PERIODS = {'normal': '非大掃除', 'part1': '大掃除 PART1', 'part2': '大掃除 PART2'}


def default_config():
    return {'enabled': False, 'periods': {
        key: {'start': '', 'end': '', 'rates': {
            tier: {'weekday': 600, 'weekend': 700} for tier in ('vip', 'regular')
        }} for key in PERIODS
    }}


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).replace('/', '-')[:10])


def validate(config):
    result = copy.deepcopy(config)
    if not isinstance(result.get('enabled'), bool):
        raise ValueError('啟用設定必須為布林值')
    ranges = []
    for key, label in PERIODS.items():
        period = result['periods'][key]
        for tier in ('vip', 'regular'):
            for day in ('weekday', 'weekend'):
                value = period['rates'][tier][day]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f'{label}單價須為大於0、最多小數2位的數字')
                amount = Decimal(str(value))
                if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('0.01')):
                    raise ValueError(f'{label}單價須為大於0、最多小數2位的數字')
        if key != 'normal':
            start, end = period['start'], period['end']
            if bool(start) != bool(end):
                raise ValueError(f'{label}請完整填寫起訖日期')
            if start:
                start, end = as_date(start), as_date(end)
                if start > end:
                    raise ValueError(f'{label}起日不可晚於迄日')
                ranges.append((start, end))
    if len(ranges) == 2 and max(r[0] for r in ranges) <= min(r[1] for r in ranges):
        raise ValueError('PART1與PART2日期不可重疊（含起訖日）')
    return result


SHEET_TITLE = '_服務金額設定'
SHEET_CACHE_SECONDS = 60
_sheet_cache = {'at': 0.0, 'config': None}


def config_path():
    return Path(os.environ.get('SERVICE_PRICING_FILE', Path(__file__).with_name('service_pricing.json')))


def _use_sheet():
    # 明確指定 SERVICE_PRICING_FILE（測試或持久磁碟）時只用檔案。
    return not os.environ.get('SERVICE_PRICING_FILE') and os.environ.get('SERVICE_PRICING_SHEET', '1') != '0'


def _worksheet(create=False):
    from shared.gsheet import build_gsheet_client
    from env import GOOGLE_SHEET_ID
    import gspread
    book = build_gsheet_client().open_by_key(GOOGLE_SHEET_ID)
    try:
        return book.worksheet(SHEET_TITLE)
    except gspread.WorksheetNotFound:
        return book.add_worksheet(SHEET_TITLE, rows=5, cols=2) if create else None


def _read_sheet():
    """回傳 Google Sheet 上的設定；分頁不存在或空白回傳 None。"""
    ws = _worksheet()
    raw = ws.acell('A1').value if ws else ''
    return validate(json.loads(raw)) if raw else None


def _write_sheet(config):
    ws = _worksheet(create=True)
    ws.update_acell('A1', json.dumps(config, ensure_ascii=False))
    ws.update_acell('B1', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def _read_file():
    path = config_path()
    return validate(json.loads(path.read_text())) if path.exists() else None


def load_config():
    """服務金額設定。

    2026-11-11：原本只存在主機本機 service_pricing.json，Streamlit 每次重新部署
    （合併 PR）都會清掉，設定悄悄退回「未啟用 600／700」，造成大掃除期間訂單轉換
    優惠券以 600 計。改以 Google Sheet「_服務金額設定」A1 為主（快取 60 秒）。
    """
    raw = os.environ.get('SERVICE_PRICING_JSON')
    if raw:
        return validate(json.loads(raw))
    if not _use_sheet():
        return _read_file() or default_config()
    import time
    now = time.monotonic()
    cached = _sheet_cache['config']
    if cached is not None and now - _sheet_cache['at'] < SHEET_CACHE_SECONDS:
        return copy.deepcopy(cached)
    try:
        config = _read_sheet()
    except FileNotFoundError:
        return _read_file() or default_config()  # 無 Google 憑證（本機／測試）：用檔案
    except Exception as exc:
        if cached is not None:
            return copy.deepcopy(cached)  # Sheet 暫時讀不到：沿用上一次成功讀到的設定
        config = _read_file()
        if config is None:
            raise RuntimeError(f'無法讀取服務金額設定（Google Sheet {SHEET_TITLE}）：{exc}') from exc
        return config
    if config is None:
        config = _read_file() or default_config()  # 尚未存到 Sheet：沿用本機舊設定
    _sheet_cache.update(at=now, config=config)
    return copy.deepcopy(config)


def config_source():
    if os.environ.get('SERVICE_PRICING_JSON'):
        return '環境變數 SERVICE_PRICING_JSON'
    return f'Google Sheet「{SHEET_TITLE}」' if _use_sheet() else f'檔案 {config_path()}'


def save_config(config):
    config = validate(config)
    if os.environ.get('SERVICE_PRICING_JSON'):
        raise ValueError('本環境由 SERVICE_PRICING_JSON 管理，請更新環境設定')
    if _use_sheet():
        import time
        _write_sheet(config)
        _sheet_cache.update(at=time.monotonic(), config=copy.deepcopy(config))
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.pricing-')
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def account_balance(payload):
    """get_member's storedValue is the backend's available balance.

    Explicit totalBalance takes precedence; separately returned shoppingValue is
    added only when present. Missing balance is an error, never a non-VIP guess.
    """
    if 'totalBalance' in payload:
        value = Decimal(str(payload['totalBalance']).replace(',', ''))
        if not value.is_finite():
            raise ValueError('會員餘額格式錯誤')
        return value
    if 'storedValue' not in payload or payload['storedValue'] in (None, ''):
        raise ValueError('查無會員儲值金（含購物金）餘額，請重新查詢會員')
    balance = Decimal(str(payload['storedValue']).replace(',', ''))
    if payload.get('shoppingValue') not in (None, ''):
        balance += Decimal(str(payload['shoppingValue']).replace(',', ''))
    if not balance.is_finite():
        raise ValueError('會員餘額格式錯誤')
    return balance


def customer_tier(flow, balance=None):
    if flow == 'batch':
        return 'vip'
    if flow == 'new':
        return 'regular'
    if balance is None:
        raise ValueError('需先查詢儲值金（含購物金）餘額')
    return 'vip' if Decimal(str(balance)) > 0 else 'regular'


def makeup_paid_tier(service_date, balance, config=None):
    """儲值金補價差第二段（客付補差價單）的計價等級。

    年節期間（大掃除 PART1／PART2）總金額一律以一般客（非VIP）計價；
    其他期間沿用舊客規則（有餘額＝VIP）。
    """
    config = config if config is not None else load_config()
    if config['enabled'] and period_for(service_date, config) != 'normal':
        return 'regular'
    return customer_tier('existing', balance)


def period_for(service_date, config):
    day = as_date(service_date)
    for key in ('part1', 'part2'):
        period = config['periods'][key]
        if period['start'] and as_date(period['start']) <= day <= as_date(period['end']):
            return key
    return 'normal'


def unit_price(service_date, tier='regular', config=None, weekend=None):
    config = config if config is not None else load_config()
    day = as_date(service_date)
    weekend = day.weekday() >= 5 if weekend is None else weekend
    if not config['enabled']:
        return 700 if weekend else 600
    period = period_for(day, config)
    return config['periods'][period]['rates'][tier]['weekend' if weekend else 'weekday']


TIER_LABELS = {'vip': 'VIP', 'regular': '一般客'}


def _hours_from_period(period):
    match = re.search(r'(\d{1,2}):(\d{2})\s*[-~～]\s*(\d{1,2}):(\d{2})', str(period or ''))
    if not match:
        return None
    h1, m1, h2, m2 = (int(x) for x in match.groups())
    minutes = (h2 * 60 + m2) - (h1 * 60 + m1)
    return Decimal(minutes) / 60 if minutes > 0 else None


WEEKDAY_NAMES = '一二三四五六日'
PERIOD_SHORT = {'normal': '非大掃除', 'part1': '大掃除1', 'part2': '大掃除2'}
DAY_LABELS = {'weekday': '平日', 'weekend': '假日'}


def price_detail(service_date, person, hour, amount, config=None, period=None, tolerance=2):
    """結構化結果。

    status：'ok'（符合本期間價格）／'other'（剛好是其他期間或平假日的價格＝改期沒重算）／'skip'（無法判斷）。
    status＝'other' 時另有：
      amount 目前金額、tier 依目前金額推定的客戶等級（vip／regular）、
      charged_as 目前金額對應的價格（例「非大掃除平日 VIP 價」）、
      service_as 服務日所屬（例「非大掃除假日」）、
      expected 應收金額（同等級）、expected_all {vip, regular}、diff 應收－目前、
      kind 'period'（期間價格錯，改期跨大掃除期間）／'day'（同期間但平日、假日價格弄反）。
    """
    result = {'status': 'skip'}
    config = config if config is not None else load_config()
    if not config.get('enabled'):
        return result
    try:
        day = as_date(service_date)
        amount = Decimal(str(amount).replace(',', ''))
        person = Decimal(str(person))
        hour = Decimal(str(hour)) if str(hour or '').strip() else _hours_from_period(period)
    except Exception:
        return result
    if not hour or person <= 0 or hour <= 0 or amount <= 0:
        return result

    def total(rate):
        return (Decimal(str(rate)) * person * hour).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    current = period_for(day, config)
    day_key = 'weekend' if day.weekday() >= 5 else 'weekday'
    expected = {tier: total(config['periods'][current]['rates'][tier][day_key]) for tier in TIER_LABELS}
    if any(abs(amount - value) <= tolerance for value in expected.values()):
        return {'status': 'ok'}
    for key, label in PERIODS.items():
        if key != 'normal' and not config['periods'][key]['start']:
            continue
        for other_day in ('weekday', 'weekend'):
            if key == current and other_day == day_key:
                continue
            for tier, tier_label in TIER_LABELS.items():
                if abs(amount - total(config['periods'][key]['rates'][tier][other_day])) <= tolerance:
                    return {
                        'status': 'other', 'amount': int(amount), 'tier': tier,
                        'kind': 'day' if key == current else 'period',
                        'charged_as': f"{PERIOD_SHORT[key]}{DAY_LABELS[other_day]} {tier_label} 價",
                        'service_as': f"{PERIOD_SHORT[current]}{DAY_LABELS[day_key]}",
                        'charged_period': PERIOD_SHORT[key], 'charged_daytype': DAY_LABELS[other_day],
                        'service_period': PERIOD_SHORT[current], 'service_daytype': DAY_LABELS[day_key],
                        'service_day': f"{day.strftime('%Y/%m/%d')}（{WEEKDAY_NAMES[day.weekday()]}）",
                        'expected': int(expected[tier]),
                        'expected_all': {t: int(v) for t, v in expected.items()},
                        'diff': int(expected[tier] - amount),
                    }
    return result


def describe_detail(detail):
    """一句話提醒（LINE 通知等只能顯示文字的地方用）。"""
    diff = detail['diff']
    return (f"金額異常：目前 {detail['amount']} 元是「{detail['charged_as']}」，"
            f"服務日 {detail['service_day']} 屬「{detail['service_as']}」，"
            f"應收 {detail['expected']} 元（{TIER_LABELS[detail['tier']]}），"
            f"{'少收' if diff > 0 else '多收'} {abs(diff)} 元，請重新成立訂單")


def price_status(service_date, person, hour, amount, config=None, period=None, tolerance=2):
    """回傳 (狀態, 提醒文字)；狀態同 price_detail。"""
    detail = price_detail(service_date, person, hour, amount, config, period, tolerance)
    return detail['status'], (describe_detail(detail) if detail['status'] == 'other' else None)


def period_price_mismatch(service_date, person, hour, amount, config=None, period=None, tolerance=2):
    """改期跨期間後金額沒重算的檢查（例：12/31 大掃除 6000 改到 12/4 非大掃除，應為 4800）。

    只有金額剛好等於其他期間／另一種平假日的價格才回傳提醒文字，其餘回傳 None，避免誤報。
    """
    status, message = price_status(service_date, person, hour, amount, config, period, tolerance)
    return message if status == 'other' else None


def apply_booking_price(payload, tier, config=None):
    config = config if config is not None else load_config()
    if config['enabled']:
        amount = Decimal(str(unit_price(payload['date_s'], tier, config))) * Decimal(str(payload['hour'])) * Decimal(str(payload['person']))
        payload['price'] = str((amount / Decimal('1.05')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        payload['price_vvip'] = '0'
    return payload


def render_settings(st):
    with st.expander('服務金額設定：非大掃除／大掃除 PART1／PART2'):
        config = load_config()
        st.caption('金額單位：含稅元／每2人1小時（例：2人1小時共$1350）。初始1200／1400僅沿用舊值，請填妥後啟用。日期含起訖日，範圍外適用非大掃除。')
        st.caption(f'設定儲存於：{config_source()}（重新部署不會遺失）')
        with st.form('service_pricing_settings'):
            config['enabled'] = st.checkbox('啟用自訂服務金額', value=config['enabled'])
            for key, label in PERIODS.items():
                st.markdown(f'**{label}**')
                period = config['periods'][key]
                if key != 'normal':
                    a, b = st.columns(2)
                    period['start'] = a.text_input('開始日期 YYYY-MM-DD（留空停用）', period['start'], key=f'{key}_start')
                    period['end'] = b.text_input('結束日期 YYYY-MM-DD', period['end'], key=f'{key}_end')
                cols = st.columns(4)
                for col, (tier, day, title) in zip(cols, [('vip','weekday','VIP 平日'), ('vip','weekend','VIP 週末'), ('regular','weekday','非VIP 平日'), ('regular','weekend','非VIP 週末')]):
                    # 畫面以「每2人1小時」輸入，內部仍存每人時單價（÷2）。
                    pair = col.number_input(title, min_value=0.02, value=float(period['rates'][tier][day]) * 2, step=1.0, format='%.2f', key=f'price_{key}_{tier}_{day}')
                    period['rates'][tier][day] = float(Decimal(str(pair)) / 2)
            if st.form_submit_button('儲存服務金額設定'):
                try:
                    save_config(config)
                    st.success('服務金額設定已儲存')
                except Exception as exc:
                    st.error(f'儲存失敗：{exc}')
