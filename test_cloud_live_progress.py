# 移植自 orders-system test_cloud_live_progress.py；模組路徑改為 order-system 的 shared/ 與 function/。
from unittest.mock import MagicMock, patch
import shared.cloud_batch_booking as cloud
from shared.cloud_booking_progress import Progress, decode


def test_snapshot_never_invents_invalid_counts():
    assert decode(['key', 'sheet', 'phase', 'bad', 0, 0, 0, 0, '', 'time']) is None
    assert decode(['key', 'sheet', 'phase', -1, 0, 0, 0, 0, '', 'time']) is None
    row = ['123:2', 'sheet', '成單中', '3', '2', '1', '7', '10', '22', 'time']
    assert decode(row)['processed'] == 3
    assert decode(row)['key'] == '123:2'


def test_publisher_updates_one_row_per_attempt_and_contains_no_customer_data():
    with patch.dict('os.environ', {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '2'}):
        progress = Progress('sheet')
    sheet = MagicMock()
    sheet.append_row.return_value = {'updates': {'updatedRange': "'_雲端成單進度'!A4:K4"}}
    progress.sheet = sheet
    progress.publish('成單中', 0, 0, 0, 2, 2, '22')
    progress.publish('完成', 2, 1, 1, 0, 2)
    assert sheet.append_row.call_count == 1
    assert sheet.update.call_args.kwargs['range_name'] == 'A4:K4'
    assert sheet.update.call_args.kwargs['values'][0][:8] == ['123:2', 'sheet', '完成', 2, 1, 1, 0, 2]


def test_progress_storage_failure_does_not_abort_booking():
    progress = Progress('sheet')
    progress.key = '123:1'
    progress.sheet = MagicMock()
    progress.sheet.append_row.side_effect = RuntimeError('private error')
    progress.publish('成單中', 0, 0, 0, 1, 1)


def test_live_group_callback_reports_completed_rows_before_finish():
    rows = [(2, '台北', ''), (3, '台北', '')]
    def pending(sheet, excluded, *args):
        return [row for row in rows if row[0] not in excluded]
    def run_group(**kwargs):
        kwargs['progress_callback'](1, 1, 0, '3')
        kwargs['progress_callback'](2, 1, 1, '')
        return {'success_count': 1, 'fail_count': 1}
    with patch.object(cloud, 'load_pending', side_effect=pending), \
         patch.object(cloud, 'ACCOUNTS', {'台北': {'email': 'test', 'password': 'test'}}), \
         patch.object(cloud, 'run_process_web_hybrid', side_effect=run_group), \
         patch.object(cloud, 'held_rows', return_value=[]), \
         patch.object(cloud, 'Progress') as reporter:
        reporter.return_value.pause_requested.return_value = False
        assert cloud.run('sheet', pause_seconds=0) == 2
    calls = [call.args for call in reporter.return_value.publish.call_args_list]
    assert ('成單中', 1, 1, 0, 1, 2, '3') in calls
    assert calls[-1] == ('部分失敗', 2, 1, 1, 0, 2)


def test_startup_failure_does_not_publish_fake_zero_totals():
    with patch.object(cloud, 'load_pending', side_effect=RuntimeError('credentials')), \
         patch.object(cloud, 'Progress') as reporter:
        try:
            cloud.run('sheet')
        except RuntimeError:
            pass
    reporter.return_value.publish.assert_not_called()


def test_page_renders_attempt_specific_progress_and_failure_snapshot():
    import ast
    from pathlib import Path
    import shared.cloud_booking_progress as cloud_booking_progress
    source = (Path(__file__).parent / 'function' / 'cloud_batch_booking.py').read_text()
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_render_live_progress')
    st = MagicMock()
    st.session_state = {}
    st.columns.return_value = [MagicMock() for _ in range(4)]
    ns = {'st': st}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'ui', 'exec'), ns)
    snapshot = decode(['123:2', 'sheet', '成單中', '3', '2', '1', '7', '10', '22', '2026-10-08 00:30:00'])
    with patch.object(cloud_booking_progress, 'read_progress', return_value=snapshot) as read:
        ns['_render_live_progress']({'id': 123, 'run_attempt': 2, 'status': 'completed', 'conclusion': 'failure'})
    read.assert_called_once_with(123, 2)
    st.columns.return_value[0].metric.assert_called_once_with('已處理', '3 列')
    assert st.session_state['cloud_live_123_2'] == snapshot
    assert '中止前最後回報' in st.caption.call_args.args[0]


def test_held_count_is_published_and_old_rows_default_to_zero():
    assert decode(['123:2', 'sheet', '成單中', '3', '2', '1', '7', '10', '22', 'time'])['held'] == 0
    assert decode(['123:2', 'sheet', '成單中', '3', '2', '1', '7', '10', '22', 'time', '4'])['held'] == 4
    rows = [(2, '台北', '')]
    with patch.object(cloud, 'load_pending', side_effect=lambda sheet, excluded, *a: [r for r in rows if r[0] not in excluded]), \
         patch.object(cloud, 'ACCOUNTS', {'台北': {'email': 'test', 'password': 'test'}}), \
         patch.object(cloud, 'run_process_web_hybrid', return_value={'success_count': 1, 'fail_count': 0}), \
         patch.object(cloud, 'held_rows', return_value=[5, 6]), \
         patch.object(cloud, 'Progress') as reporter:
        assert cloud.run('sheet', pause_seconds=0) == 0
    assert reporter.return_value.held == 2


def test_page_shows_held_rows():
    import ast
    from pathlib import Path
    import shared.cloud_booking_progress as cloud_booking_progress
    source = (Path(__file__).parent / 'function' / 'cloud_batch_booking.py').read_text()
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_render_live_progress')
    st = MagicMock()
    st.session_state = {}
    st.columns.return_value = [MagicMock() for _ in range(4)]
    ns = {'st': st}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'ui', 'exec'), ns)
    snapshot = decode(['123:2', 'sheet', '成單中', '3', '2', '1', '7', '10', '22', 'time', '3'])
    with patch.object(cloud_booking_progress, 'read_progress', return_value=snapshot):
        ns['_render_live_progress']({'id': 123, 'run_attempt': 2, 'status': 'in_progress'})
    assert '未選入本次預約對象略過 3 列' in st.info.call_args.args[0]


def test_cloud_stages_env_defaults_and_validates():
    import pytest
    with patch.dict('os.environ', {'STAGES_JSON': ''}):
        assert cloud._stages_from_env() == ['可約']
    with patch.dict('os.environ', {'STAGES_JSON': '["改加", "已確認"]'}):
        assert cloud._stages_from_env() == ['改加', '已確認']
    with patch.dict('os.environ', {'STAGES_JSON': '["先不約"]'}), pytest.raises(SystemExit):
        cloud._stages_from_env()


def test_cloud_main_runs_with_selected_stages():
    from shared.booking_eligibility import current_booking_stages
    seen = []
    with patch.dict('os.environ', {'STAGES_JSON': '["改加"]', 'O_TEXTS_JSON': ''}), \
         patch('sys.argv', ['cloud_batch_booking.py', '--sheet', 's']), \
         patch.object(cloud, 'run', side_effect=lambda *a, **k: seen.append(current_booking_stages()) or 0):
        assert cloud.main() == 0
    assert seen == [('改加',)] and current_booking_stages() == ('可約',)


def test_pause_after_group_stops_cleanly_and_reports_remaining():
    rows = [(2, '台北', ''), (3, '台北', ''), (4, '台北', '')]
    done = set()

    def pending(sheet, excluded, *args):
        return [row for row in rows if row[0] not in excluded and row[0] not in done]

    def run_group(**kwargs):
        assert callable(kwargs['should_stop'])
        done.add(2)
        return {'success_count': 1, 'fail_count': 0, 'total_processed': 1, 'paused': True}

    with patch.object(cloud, 'load_pending', side_effect=pending), \
         patch.object(cloud, 'ACCOUNTS', {'台北': {'email': 'test', 'password': 'test'}}), \
         patch.object(cloud, 'run_process_web_hybrid', side_effect=run_group) as runner, \
         patch.object(cloud, 'held_rows', return_value=[]), \
         patch.object(cloud, 'Progress') as reporter:
        reporter.return_value.held = 0
        assert cloud.run('sheet', chunk_size=2, pause_seconds=0) == 0
    assert runner.call_count == 1
    assert reporter.return_value.publish.call_args.args == ('已暫停', 1, 1, 0, 2, 3)


def test_pause_request_is_read_from_control_column_and_throttled():
    progress = Progress('sheet')
    progress.key = '123:1'
    progress.sheet = MagicMock()
    progress.row = 5
    progress.sheet.get.return_value = [['']]
    with patch('shared.cloud_booking_progress.time.monotonic', side_effect=[100, 105, 111]):
        assert progress.pause_requested() is False
        progress.sheet.get.return_value = [['暫停']]
        assert progress.pause_requested() is False  # 10 秒內不重讀
        assert progress.pause_requested() is True
    progress.sheet.get.assert_called_with('L5')


def test_request_pause_writes_control_cell_for_this_attempt():
    import shared.cloud_booking_progress as cbp
    sheet = MagicMock()
    sheet.col_values.return_value = ['執行識別', '9:1', '123:1', '123:2']
    sheet.col_count = 12
    with patch.object(cbp, '_progress_sheet', return_value=sheet):
        assert cbp.request_pause(123, 2) is True
        assert cbp.request_pause(999, 1) is False
    sheet.update.assert_called_once_with(range_name='L4', values=[['暫停']], value_input_option='RAW')


def test_hybrid_runner_stops_before_next_group_when_paused():
    import pandas as pd
    import shared.hybrid_batch_runner as hybrid
    rows = pd.DataFrame([
        {"__sheet_row__": 2, "姓名": "甲", "服務人時": "2人", "開始時間": "9:00", "結束時間": "12:00", "電話": "0911111111", "地址": "台北市A", "訂單編號": ""},
        {"__sheet_row__": 3, "姓名": "乙", "服務人時": "2人", "開始時間": "9:00", "結束時間": "12:00", "電話": "0922222222", "地址": "台北市B", "訂單編號": ""},
        {"__sheet_row__": 4, "姓名": "丙", "服務人時": "2人", "開始時間": "9:00", "結束時間": "12:00", "電話": "0933333333", "地址": "台北市C", "訂單編號": ""},
    ])
    created = []
    checks = iter([False, True])
    with patch.object(hybrid._safety, '_configure_runtime'), \
         patch.object(hybrid._safety, '_recover_before_create', return_value=(MagicMock(), [2, 3, 4], [], [], 3)), \
         patch.object(hybrid._safety, '_checkpoint'), \
         patch.object(hybrid._orders, 'load_worksheet', return_value=(MagicMock(), rows)), \
         patch.object(hybrid, '_selected_work', return_value=rows), \
         patch.object(hybrid, '_login_once'), \
         patch.object(hybrid, '_run_one_direct', side_effect=lambda s, ws, row_no, *a: created.append(row_no) or {"結果": "成功", "訂單編號": f"T{row_no}"}), \
         patch.object(hybrid, '_result_stats', return_value=(1, 0)):
        result = hybrid.run_process_web_hybrid(
            env_name='dev', region='台北', backend_email='e', backend_password='p', sheet_name='s',
            start_row=2, end_row=4, selected_actions=['建單'], logger=lambda m: None,
            selected_rows=[2, 3, 4], should_stop=lambda: next(checks))
    assert created == [2]
    assert result['paused'] is True and result['total_processed'] == 1


def test_rows_with_different_people_are_not_grouped_together():
    import shared.hybrid_batch_runner as hybrid
    base = {"電話": "0986838278", "地址": "台北市文山區試院路102-2號15樓", "開始時間": "14:00", "結束時間": "17:00"}
    usual = hybrid._phone_address_group_key({**base, "服務人時": ""})
    three = hybrid._phone_address_group_key({**base, "服務人時": "3人3小時"})
    assert usual != three
    assert usual == hybrid._phone_address_group_key({**base, "服務人時": "2人"})


def test_latest_run_falls_back_when_filtered_list_is_empty():
    import function.cloud_batch_booking as ui
    responses = {True: {"workflow_runs": []}, False: {"workflow_runs": [{"id": 17}]}}
    calls = []

    def get(path):
        calls.append(path)
        return MagicMock(json=MagicMock(return_value=responses["branch=main" in path]))

    with patch.object(ui, '_github_get', side_effect=get):
        assert ui._latest_run() == {"id": 17}
    assert len(calls) == 2


def test_cancel_run_posts_cancel_and_accepts_already_finished():
    import function.cloud_batch_booking as ui
    import pytest
    with patch.object(ui, '_token', return_value='t'), patch.object(ui.requests, 'post') as post:
        post.return_value = MagicMock(status_code=202)
        ui._cancel_run(17)
        assert post.call_args.args[0].endswith('/actions/runs/17/cancel')
        post.return_value = MagicMock(status_code=409)
        ui._cancel_run(17)
        post.return_value = MagicMock(status_code=403, text='forbidden')
        with pytest.raises(RuntimeError):
            ui._cancel_run(17)
