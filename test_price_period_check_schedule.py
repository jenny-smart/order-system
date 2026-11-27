from datetime import date, datetime

from shared import price_period_check as ppc
from shared import price_period_check_schedule as sched
from test_period_price_mismatch import _config


def _row(no='LC1'):
    return {'訂單編號': no, '訂購人': '王小明', '服務日期': '2026/12/04（五）', '服務時段': '09:00-13:00',
            '人時': '2人4小時', '目前金額': 6000, '應收金額': 4800, '差額': '多收 1200',
            '異常類型': '期間價格錯（改期跨大掃除期間）', '服務日計價': '一般客非大掃除平日',
            '目前金額計價': '一般客大掃除1平日', '備註': '', '訂單連結': 'https://x/purchase?orderNo=LC1'}


def test_window_is_previous_day_17_to_today_17():
    assert sched.query_window(date(2026, 11, 28)) == (datetime(2026, 11, 27, 17), datetime(2026, 11, 28, 17))


def test_scan_filters_by_created_time(monkeypatch):
    from memo_system import memo
    def card(no, created):
        return {'order_no': no, 'row_text': f'{created}\n居家清潔\n2人4小時\n總金額：$6,000', 'service_date': '2026/12/04',
                'hour': 4, 'period': '09:00-13:00', 'staff_count': 0, 'name': 'x', 'line_url': '', 'phone': ''}
    cards = [card('LC_OLD', '2026-11-27 16:59:00'), card('LC_IN', '2026-11-27 17:00:00'),
             card('LC_IN2', '2026-11-28 16:59:59'), card('LC_LATE', '2026-11-28 17:00:00')]
    monkeypatch.setattr(ppc, '_fetch_list', lambda s, p: cards if p['purchase_status'] == '1' else [])
    monkeypatch.setattr(memo, 'BASE_URL', 'https://x', raising=False)
    window = sched.query_window(date(2026, 11, 28))
    result = ppc.scan(None, window[0].date(), window[1].date(), config=_config(), created_window=window)
    assert [r['訂單編號'] for r in result['rows']] == ['LC_IN', 'LC_IN2'] and result['scanned'] == 2


def test_calendar_event_shows_results():
    window = sched.query_window(date(2026, 11, 28))
    event = sched.build_calendar_event({'台北': {'rows': [_row()], 'scanned': 30}, '台中': {'rows': [], 'scanned': 5}},
                                       window, datetime(2026, 11, 28, 17, 5))
    assert event['summary'] == '【金額期間檢查】台北 1 筆、台中 0 筆（11/28）'
    assert '區間：11/27 17:00 ～ 11/28 17:00' in event['description']
    assert '目前 6000（一般客大掃除1平日）→ 應收 4800（一般客非大掃除平日），多收 1200' in event['description']


def test_run_writes_calendar(monkeypatch):
    import accounts
    monkeypatch.setattr(accounts, 'ACCOUNTS', {'台北': {'email': 'a', 'password': 'b'}, '台中': {'email': 'c', 'password': 'd'}})
    monkeypatch.setattr(sched, '_log', lambda *a, **k: None)
    written = []
    import shared.notice_calendar as nc
    monkeypatch.setattr(nc, 'write_if_changed', lambda event, ids, factory=None: (written.append(event) or ['ok'], 1))
    out = sched.run(today=date(2026, 11, 28), scan=lambda *a: {'rows': [_row()], 'scanned': 3},
                    calendar_ids=('cal',), log=lambda m: None)
    assert out['台北']['scanned'] == 3 and written and written[0]['summary'].startswith('【金額期間檢查】台北 1 筆、台中 1 筆')
