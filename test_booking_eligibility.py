import pandas as pd

import shared.batch_booking_safety as safety
from shared.booking_eligibility import can_create_order, can_process_row, create_block_reason


BASE = {'姓名': '王小明', '電話': '0912345678', '地址': '台北市大安區仁愛路一段1號',
        '日期': '2027/01/20', '開始時間': '09:00', '結束時間': '12:00', '服務人時': '定期清潔',
        '狀態': '未安排', '訂單編號': '', '預約條件': ''}


def test_shared_rule_requires_blank_order_unarranged_and_no_hold():
    assert can_create_order(BASE)
    assert can_create_order({**BASE, '預約條件': '可約'})
    assert not can_create_order({**BASE, '預約條件': '未回覆'})
    assert not can_create_order({**BASE, '預約條件': '先不約'})  # 舊版值不在任何階段，不約
    assert not can_create_order({**BASE, '狀態': '待確認'})
    assert not can_create_order({**BASE, '訂單編號': 'LC1'})
    assert can_create_order({k: v for k, v in BASE.items() if k != '預約條件'})


def test_rows_with_order_still_processed_for_mail_and_calendar():
    assert can_process_row({**BASE, '訂單編號': 'LC1', '預約條件': '改加'})
    assert not can_process_row({**BASE, '預約條件': '改加'})


def test_reason_is_shown_for_skipped_rows():
    assert create_block_reason({**BASE, '狀態': '暫停'}) == '狀態為「暫停」，非未安排'
    assert create_block_reason({**BASE, '預約條件': '改加'}) == '預約條件「改加」不在本次預約對象'


def test_all_batch_runners_share_recover_filter(monkeypatch):
    rows = [{**BASE, '__sheet_row__': 2},
            {**BASE, '__sheet_row__': 3, '預約條件': '改加'},
            {**BASE, '__sheet_row__': 4, '狀態': '待確認'}]
    monkeypatch.setattr(safety, '_configure_runtime', lambda env: None)
    monkeypatch.setattr(safety._orders, 'load_worksheet', lambda name: (object(), pd.DataFrame(rows)))
    monkeypatch.setattr(safety._orders, 'get_region_by_address', lambda address, accounts: '台北')
    monkeypatch.setattr(safety._orders, 'login', lambda session, email, password: True)
    monkeypatch.setattr(safety, '_row_key', lambda row: ('0912345678', 'addr', '2027-01-20', 'p', 'p'))
    monkeypatch.setattr(safety, '_fetch_phone_blocks', lambda session, phone: [])
    logs = []
    _, remaining, recovered, blocked, _ = safety._recover_before_create(
        'dev', '台北', 'e', 'p', '台北202701', 2, 4, None, ['建單'], logs.append)
    assert remaining == [2] and recovered == [] and blocked == []
    assert any('第 3 列不建單：預約條件「改加」' in line for line in logs)
    assert any('第 4 列不建單：狀態為「待確認」' in line for line in logs)


def test_held_rows_match_filters_used_by_all_three_batches(monkeypatch):
    from types import SimpleNamespace
    import shared.selected_row_status_guard as guard
    hold = '未回覆'
    rows = [{**BASE, '__sheet_row__': 2, '預約條件': hold, '原因': '無班表', '結果': '失敗'},
            {**BASE, '__sheet_row__': 3, '預約條件': hold, '原因': '系統未產生新訂單編號', '結果': ''},
            {**BASE, '__sheet_row__': 4, '預約條件': hold, '狀態': '暫停', '結果': ''},
            {**BASE, '__sheet_row__': 5, '預約條件': hold, '訂單編號': 'LC1', '結果': ''},
            {**BASE, '__sheet_row__': 6, '結果': ''},
            {**BASE, '__sheet_row__': 7, '預約條件': hold, '電話': '', '結果': ''}]
    monkeypatch.setattr(guard, '_load_worksheet_unique', lambda name: (None, pd.DataFrame(rows)))
    batch = SimpleNamespace(_text=lambda v: str(v or '').strip(), get_region_by_address=lambda address, accounts: '台北')
    assert guard._held_rows(batch, 's') == [3]
    assert guard._held_rows(batch, 's', allow_failed=True) == [2, 3]
    assert guard._held_rows(batch, 's', 'no_schedule', allow_failed=True) == [2]
    assert guard._held_rows(batch, 's', 'stored_value', allow_failed=True) == [3]
    assert guard._held_rows(batch, 's', region='台中', allow_failed=True) == []
    assert guard._held_for_request(batch, 's', '台北', rows=[3, 6]) == [3]
    assert guard._held_for_request(batch, 's', '台北', modes=['no_schedule']) == [2]


def test_stored_value_filter_matches_sheet_o_column_text(monkeypatch):
    from types import SimpleNamespace
    import shared.selected_row_status_guard as guard
    columns = ['服務人時', '備註', '姓名', '電話', '地址', '日期', '開始時間', '結束時間', '狀態', '購買項目', '簡訊', '客人備註',
               '訂單編號', '結果', '原因', '沒班表日', '餘額不足', '預約條件']
    def row(no, o, **extra):
        values = {**BASE, '原因': o, '結果': '失敗', **extra}
        return [values.get(c, '') for c in columns] + [no]
    # 與排程工作表相同：N 欄失敗、O 欄原因、P 沒班表日、Q 餘額不足。
    rows = [row(2, '系統未產生新訂單編號'), row(3, '無班表', 沒班表日='2027-01-14'), row(4, '餘額不足'),
            row(5, '', 餘額不足='2027-02-01'), row(6, '系統未產生新訂單編號', 訂單編號='TT1'),
            row(7, '系統未產生新訂單編號', 狀態='暫停'), row(8, '')]
    df = pd.DataFrame(rows, columns=columns + ['__sheet_row__'])
    df['沒班表日期'], df['餘額不足未送'] = df['沒班表日'], df['餘額不足']  # orders.load_worksheet 的欄名別名
    monkeypatch.setattr(guard, '_load_worksheet_unique', lambda name: (None, df))
    batch = SimpleNamespace(_text=lambda v: str(v or '').strip(), get_region_by_address=lambda address, accounts: '台北',
                            REQUIRED_COLUMNS=['姓名', '電話', '地址', '日期', '開始時間', '結束時間', '狀態', '訂單編號'],
                            _date_text=str, _time_text=str)
    assert guard._auto_filter_rows(batch, 's', 'stored_value', allow_failed=True) == [2, 4, 5]
    assert guard._auto_filter_rows(batch, 's', 'no_schedule', allow_failed=True) == [3]
    assert guard._auto_filter_rows(batch, 's', 'both', allow_failed=True) == [2, 3, 4, 5]
    assert guard.filter_mode(True, True) == 'both' and guard.filter_modes('both') == ['no_schedule', 'stored_value']
    assert guard.filter_mode(False, True) == 'stored_value' and guard.filter_modes('all') == []


def test_selected_stages_decide_which_rows_can_be_booked():
    from shared.booking_eligibility import booking_stages, current_booking_stages
    rows = {stage: {**BASE, '預約條件': stage} for stage in ('可約', '改加', '已確認', '未回覆', '')}
    assert not can_create_order({**BASE, '預約條件': '人時不足'})
    with booking_stages(['人時不足']):
        assert can_create_order({**BASE, '預約條件': '人時不足'})
    assert current_booking_stages() == ('可約',)
    assert [s for s, row in rows.items() if can_create_order(row)] == ['可約', '']
    with booking_stages(['改加']):
        assert [s for s, row in rows.items() if can_create_order(row)] == ['改加', '']
    with booking_stages(['可約', '已確認', '未回覆']):
        assert [s for s, row in rows.items() if can_create_order(row)] == ['可約', '已確認', '未回覆', '']
    with booking_stages([]):
        assert [s for s, row in rows.items() if can_create_order(row)] == ['']
    assert current_booking_stages() == ('可約',)


def test_recover_filter_follows_selected_stage(monkeypatch):
    from shared.booking_eligibility import booking_stages
    rows = [{**BASE, '__sheet_row__': 2, '預約條件': '可約'}, {**BASE, '__sheet_row__': 3, '預約條件': '改加'}]
    monkeypatch.setattr(safety, '_configure_runtime', lambda env: None)
    monkeypatch.setattr(safety._orders, 'load_worksheet', lambda name: (object(), pd.DataFrame(rows)))
    monkeypatch.setattr(safety._orders, 'get_region_by_address', lambda address, accounts: '台北')
    monkeypatch.setattr(safety._orders, 'login', lambda session, email, password: True)
    monkeypatch.setattr(safety, '_row_key', lambda row: ('0912345678', 'addr', '2027-01-20', 'p', 'p'))
    monkeypatch.setattr(safety, '_fetch_phone_blocks', lambda session, phone: [])
    with booking_stages(['改加']):
        _, remaining, _, _, _ = safety._recover_before_create('dev', '台北', 'e', 'p', 's', 2, 3, None, ['建單'], print)
    assert remaining == [3]


def test_held_message_groups_skipped_rows_by_stage(monkeypatch):
    import shared.selected_row_status_guard as guard
    rows = [{**BASE, '__sheet_row__': n, '預約條件': stage}
            for n, stage in ((2, '未回覆'), (3, '改加'), (4, '未回覆'), (5, '可約'))]
    monkeypatch.setattr(guard, '_load_worksheet_unique', lambda name: (None, pd.DataFrame(rows)))
    assert guard.held_message(None, 's', [2, 3, 4]) == '未選入本次預約對象略過 3 列（改加 1、未回覆 2）'


def test_stage_widget_defaults_to_ready_and_sets_current_stages():
    from unittest.mock import MagicMock
    import shared.selected_row_status_guard as guard
    from shared.booking_eligibility import current_booking_stages, set_booking_stages
    st = MagicMock()
    st.multiselect.return_value = ['可約', '改加']
    try:
        assert guard.render_stage_filter(st, 'k') == ['可約', '改加']
        assert st.multiselect.call_args.kwargs['default'] == ['可約']
        assert st.multiselect.call_args.args[1] == ['可約', '改加', '人時不足', '已確認', '未回覆']
        assert current_booking_stages() == ('可約', '改加')
    finally:
        set_booking_stages(('可約',))


def test_lemon_retry_only_reruns_no_slot_rows_and_keeps_booked_rows():
    # 第 840 列第一次就成單、第 843 列無班表：補檸檬人後只重試 843，840 的單號不能被蓋掉。
    from unittest.mock import patch
    import shared.selected_row_status_guard as guard
    calls = []

    def process(session, rows, *args, **kwargs):
        calls.append([row_no for row_no, _ in rows])
        if len(calls) == 1:
            return {840: {"訂單編號": "TT1", "結果": "成功", "原因": ""}, 843: {"結果": "失敗", "原因": "無班表"}}
        return {row_no: {"訂單編號": "TT2", "結果": "成功", "原因": ""} for row_no in calls[-1]}

    rows = [(840, {"日期": "2026/12/14", "開始時間": "14:00", "結束時間": "17:00", "服務人時": ""}),
            (843, {"日期": "2027/01/04", "開始時間": "14:00", "結束時間": "17:00", "服務人時": ""})]
    with patch.object(guard.orders, "process_one_group", side_effect=process), \
         patch.object(guard.orders, "ensure_lemon_cleaner_shifts", return_value={"success": True, "assigned": ["檸檬人1"]}), \
         patch.object(guard.orders, "get_csrf_token", return_value="t"):
        result = guard.process_one_group_with_lemon_retry(None, rows, "t", None, "台北", allow_auto_lemon_shift=True, logger=lambda *_: None)
    assert calls == [[840, 843], [843]]
    assert result[840]["訂單編號"] == "TT1" and result[843]["訂單編號"] == "TT2"


def test_hours_mismatch_reason_only_for_standard_slots_with_different_hours():
    import shared.selected_row_status_guard as guard
    row = lambda a, s, e: {"服務人時": a, "開始時間": s, "結束時間": e}
    assert guard.hours_mismatch_reason(row("2人3小時", "8:30", "12:30")) == "請檢查時數：A欄3小時，時段08:30-12:30為4小時"
    assert guard.hours_mismatch_reason(row("2人4小時", "8:30", "12:30")) == ""
    assert guard.hours_mismatch_reason(row("", "8:30", "12:30")) == ""
    assert guard.hours_mismatch_reason(row("改", "8:30", "12:30")) == ""


def test_no_slot_row_with_mismatched_hours_says_check_hours_and_skips_lemon():
    # 楊明勳：A 欄 2人3小時、時段 08:30-12:30，查不到班表不是真的沒班，補檸檬人也沒用。
    from unittest.mock import patch
    import shared.selected_row_status_guard as guard
    first = {768: {"結果": "失敗", "原因": "無班表", "沒班表日期": "2026-12-18"}}
    rows = [(768, {"日期": "2026/12/18", "開始時間": "8:30", "結束時間": "12:30", "服務人時": "2人3小時"})]
    with patch.object(guard.orders, "process_one_group", return_value=first) as process, \
         patch.object(guard.orders, "ensure_lemon_cleaner_shifts") as lemon:
        result = guard.process_one_group_with_lemon_retry(None, rows, "t", None, "台北", allow_auto_lemon_shift=True, logger=lambda *_: None)
    assert result[768]["原因"] == "請檢查時數：A欄3小時，時段08:30-12:30為4小時"
    assert result[768]["沒班表日期"] == ""
    lemon.assert_not_called()
    assert process.call_count == 1


def test_booked_rows_with_lemon_staff_are_noted_in_no_slot_column():
    from unittest.mock import patch
    import shared.selected_row_status_guard as guard
    first = {12: {"訂單編號": "TT1", "結果": "成功", "原因": "", "服務人員": "檸檬人3,陳靜怡,檸檬人4", "沒班表日期": ""},
             13: {"訂單編號": "TT2", "結果": "成功", "原因": "", "服務人員": "陳靜怡、宋品鈞", "沒班表日期": ""},
             14: {"訂單編號": "", "結果": "失敗", "原因": "系統未產生新訂單編號", "服務人員": "檸檬人1", "沒班表日期": ""}}
    rows = [(n, {"日期": "2027/01/28", "開始時間": "8:30", "結束時間": "12:30", "服務人時": ""}) for n in (12, 13, 14)]
    with patch.object(guard.orders, "process_one_group", return_value=first):
        result = guard.process_one_group_with_lemon_retry(None, rows, "t", None, "台北", allow_auto_lemon_shift=False, logger=lambda *_: None)
    assert result[12]["沒班表日期"] == "檸檬人：檸檬人3、檸檬人4"
    assert result[13]["沒班表日期"] == "" and result[14]["沒班表日期"] == ""
