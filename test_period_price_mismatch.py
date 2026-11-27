from service_pricing import default_config, period_price_mismatch
from shared.line_notice_sheet import build_source_writeback


def _config():
    config = default_config()
    config['enabled'] = True
    rates = {'normal': (600, 600, 700, 700), 'part1': (700, 750, 750, 800), 'part2': (750, 800, 800, 850)}
    dates = {'normal': ('', ''), 'part1': ('2026-12-15', '2027-01-10'), 'part2': ('2027-01-11', '2027-02-05')}
    for key, (vwd, rwd, vwe, rwe) in rates.items():
        period = config['periods'][key]
        period['start'], period['end'] = dates[key]
        period['rates'] = {'vip': {'weekday': vwd, 'weekend': vwe}, 'regular': {'weekday': rwd, 'weekend': rwe}}
    return config


def test_moved_out_of_deep_clean_keeps_old_amount():
    # LC00221437：12/31 大掃除 6000（2人4小時）改到 12/4，金額沒改
    message = period_price_mismatch('2026-12-04', 2, 4, 6000, _config())
    assert message and '大掃除 PART1' in message and '4800' in message and '重新成立訂單' in message


def test_correct_amount_has_no_warning():
    assert period_price_mismatch('2026-12-04', 2, 4, 4800, _config()) is None
    assert period_price_mismatch('2026-12-31', 2, 4, 6000, _config()) is None
    assert period_price_mismatch('2026-12-31', 2, 4, 5600, _config()) is None  # VIP


def test_part1_to_part2_and_weekday_weekend():
    assert '應收 6000' in period_price_mismatch('2027-01-20', 2, 4, 5600, _config())
    assert '假日' in period_price_mismatch('2026-12-01', 2, 4, 5600, _config())  # 12/1 週二，5600 是非大掃除假日價


def test_unrelated_amount_and_disabled_config_skip():
    assert period_price_mismatch('2026-12-04', 2, 4, 4321, _config()) is None
    assert period_price_mismatch('2026-12-04', 2, 4, 6000, default_config()) is None
    assert period_price_mismatch('2026-12-04', 2, '', 6000, _config(), period='09:00-13:00')


def test_sheet_writeback_adds_warning_to_change_check():
    group = {'name': '李婉綾', 'address': 'A', 'service': '', 'entries': [{'row': 2, 'date': '2026-12-04', 'start': '09:00-13:00'}]}
    result = {'group': group, 'text': 'x', 'error': None, 'result': {
        'orders_info': [{'service_date': '2026-12-04', 'period_s': '09:00-13:00'}],
        'price_warnings': ['LC00221437 金額異常：…'],
    }}
    updates, _, _ = build_source_writeback([group], [result], [])
    assert '金額異常' in updates[2]['異動檢查']
