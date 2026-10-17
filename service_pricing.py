"""Shared, tax-inclusive person-hour prices for booking and service changes."""
import copy
import json
import os
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


def config_path():
    return Path(os.environ.get('SERVICE_PRICING_FILE', Path(__file__).with_name('service_pricing.json')))


def load_config():
    raw = os.environ.get('SERVICE_PRICING_JSON')
    if raw:
        return validate(json.loads(raw))
    path = config_path()
    return validate(json.loads(path.read_text())) if path.exists() else default_config()


def save_config(config):
    config = validate(config)
    if os.environ.get('SERVICE_PRICING_JSON'):
        raise ValueError('本環境由 SERVICE_PRICING_JSON 管理，請更新環境設定')
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
        st.caption('金額單位：含稅元／人時，可輸入小數點後2位。初始600／700僅沿用舊值，請填妥後啟用。日期含起訖日，範圍外適用非大掃除。')
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
                    period['rates'][tier][day] = col.number_input(title, min_value=0.01, value=float(period['rates'][tier][day]), step=0.01, format='%.2f', key=f'price_{key}_{tier}_{day}')
            if st.form_submit_button('儲存服務金額設定'):
                try:
                    save_config(config)
                    st.success('服務金額設定已儲存')
                except (ValueError, KeyError, OSError) as exc:
                    st.error(str(exc))
