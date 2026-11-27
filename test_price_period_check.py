from datetime import date

from shared import price_period_check as ppc
from test_period_price_mismatch import _config


def _item(text, service_date='2026/12/04', hour=4, staff=0, no='LC00221437'):
    return {'order_no': no, 'row_text': text, 'service_date': service_date, 'hour': hour,
            'period': '09:00-13:00', 'staff_count': staff, 'name': '李婉綾', 'line_url': ''}


def test_card_person_hour_flags_old_deep_clean_amount():
    problem = ppc.check_item(_item('2人4小時\n總金額：$6,000'), _config())
    assert problem and '4800' in problem['問題'] and problem['人時'] == '2人4小時'


def test_staff_count_used_when_card_has_no_person():
    assert ppc.check_item(_item('總金額：$6,000', staff=2), _config())
    assert ppc.check_item(_item('總金額：$4,800', staff=2), _config()) is None


def test_guess_persons_only_when_no_person_fits_current_period():
    problem = ppc.check_item(_item('總金額：$6,000'), _config())
    assert problem and '人數推算' in problem['人時']
    assert ppc.check_item(_item('總金額：$4,800'), _config()) is None


def test_fare_is_excluded_and_discounts_skipped():
    assert ppc.check_item(_item('2人4小時\n總金額：$5,000\n車馬費：$200'), _config()) is None
    assert ppc.check_item(_item('2人4小時\n總金額：$6,200\n車馬費：$200'), _config())


def test_scan_queries_each_day_and_dedupes(monkeypatch):
    from memo_system import memo
    calls = []

    def fake_fetch(session, params):
        calls.append((params['clean_date_s'], params['purchase_status']))
        return [_item('2人4小時\n總金額：$6,000')] if params['purchase_status'] == '1' else []

    monkeypatch.setattr(ppc, '_fetch_list', fake_fetch)
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    result = ppc.scan(None, date(2026, 12, 3), date(2026, 12, 4), '服務日期', config=_config())
    assert len(calls) == 4 and result['scanned'] == 1 and len(result['rows']) == 1
    assert result['rows'][0]['訂單連結'].endswith('orderNo=LC00221437')
