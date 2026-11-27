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


def test_scan_reports_progress(monkeypatch):
    from memo_system import memo
    monkeypatch.setattr(ppc, '_fetch_list', lambda session, params: [])
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    calls = []
    ppc.scan(None, date(2026, 11, 11), date(2026, 11, 13), config=_config(), progress=lambda *a: calls.append(a[:2]))
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_same_day_makeup_order_makes_total_correct(monkeypatch):
    # LC00220372 9500－200＝9300（PART1 價）＋ LC00220548 500－200＝300 → 9600＝PART2 假日一般客 2人6小時
    from memo_system import memo
    main = _item('總金額：$9,500\n車馬費：$200', service_date='2027/01/23', hour=6, staff=2, no='LC00220372')
    main['phone'] = '0922561066'
    makeup = _item('總金額：$500\n車馬費：$200', service_date='2027/01/23', hour=6, staff=2, no='LC00220548')

    def fake_fetch(session, params):
        if params.get('phone'):
            return [main, makeup] if params['purchase_status'] == '1' else []
        return [main] if params['purchase_status'] == '1' else []

    monkeypatch.setattr(ppc, '_fetch_list', fake_fetch)
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    config = _config()
    config['periods']['part2']['rates']['regular']['weekend'] = 800
    config['periods']['part1']['rates']['regular']['weekend'] = 775
    result = ppc.scan(None, date(2026, 11, 11), date(2026, 11, 11), config=config)
    assert result['rows'] == []


def test_same_day_total_still_wrong_is_listed(monkeypatch):
    from memo_system import memo
    main = _item('2人4小時\n總金額：$6,000', no='LC1')
    main['phone'] = '0911'
    other = _item('總金額：$100', no='LC2')

    def fake_fetch(session, params):
        if params.get('phone'):
            return [main, other] if params['purchase_status'] == '1' else []
        return [main] if params['purchase_status'] == '1' else []

    monkeypatch.setattr(ppc, '_fetch_list', fake_fetch)
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    result = ppc.scan(None, date(2026, 11, 11), date(2026, 11, 11), config=_config())
    assert len(result['rows']) == 1 and '同日另有 LC2，合計 6100 仍不符' in result['rows'][0]['問題']
    assert '_person' not in result['rows'][0]
