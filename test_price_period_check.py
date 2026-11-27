from datetime import date

from shared import price_period_check as ppc
from test_period_price_mismatch import _config


def _item(text, service_date='2026/12/04', hour=4, staff=0, no='LC00221437'):
    return {'order_no': no, 'row_text': '居家清潔\n' + text, 'service_date': service_date, 'hour': hour,
            'period': '09:00-13:00', 'staff_count': staff, 'name': '李婉綾', 'line_url': ''}


def test_card_person_hour_flags_old_deep_clean_amount():
    problem = ppc.check_item(_item('2人4小時\n總金額：$6,000'), _config())
    assert problem and problem['應收金額'] == 4800 and problem['目前金額'] == 6000 and problem['差額'] == '多收 1200'
    assert problem['人時'] == '2人4小時' and problem['異常類型'].startswith('期間價格錯')
    assert (problem['服務日期間'], problem['服務日平假日'], problem['目前金額期間'], problem['目前金額平假日']) == ('非大掃除', '平日', '大掃除1', '平日')


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
    assert len(result['rows']) == 1 and '同日另有 LC2，合計 6100 仍不符' in result['rows'][0]['備註']
    assert '_person' not in result['rows'][0]


def test_partial_refund_is_deducted(monkeypatch):
    # LC00220455：12/10 非大掃除，總金額 9000（PART1 價），已部分退款 1800 → 7200 正確
    from memo_system import memo
    item = _item('總金額：$9,000\n待退狀態：已部分退款', service_date='2026/12/10', hour=6, staff=2, no='LC00220455')

    def fake_fetch(session, params):
        return [dict(item)] if params['purchase_status'] == '1' and not params.get('phone') else []

    def fake_refund(session, it):
        it['_refund'] = 1800
        return True

    monkeypatch.setattr(ppc, '_fetch_list', fake_fetch)
    monkeypatch.setattr(ppc, 'load_adjustments', fake_refund)
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    config = _config()
    config['periods']['part1']['start'] = '2026-12-15'
    result = ppc.scan(None, date(2026, 11, 12), date(2026, 11, 12), config=config)
    assert result['rows'] == []


def test_refund_state_and_full_refund():
    assert ppc.refund_state(_item('待退狀態：已部分退款')) == '已部分退款'
    assert ppc.refund_state(_item('待退狀態：無')) == ''
    assert ppc._net_amount(_item('總金額：$9,000\n待退狀態：已全額退款')) == 0
    it = _item('總金額：$9,000\n車馬費：$200')
    it['_refund'] = 1800
    assert ppc._net_amount(it) == 7000


def test_charge_is_added_and_weekday_weekend_type(monkeypatch):
    it = _item('2人4小時\n總金額：$4,800\n加收狀態：已加收', service_date='2026/12/05')  # 週六
    assert ppc.charge_state(it) == '已加收'
    assert ppc.charge_state(_item('加收狀態：無')) == ''
    problem = ppc.check_item(it, _config())
    assert problem['異常類型'] == '平日／假日價格錯' and problem['應收金額'] == 5600
    it['_charge'] = 800
    assert ppc.check_item(it, _config()) is None


def test_non_home_cleaning_is_skipped():
    it = _item('2人4小時\n總金額：$6,000')
    it['row_text'] = it['row_text'].replace('居家清潔', '沙發水洗')
    assert ppc.check_item(it, _config()) is None
