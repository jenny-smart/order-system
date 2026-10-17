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
    sheet.append_row.return_value = {'updates': {'updatedRange': "'_雲端成單進度'!A4:J4"}}
    progress.sheet = sheet
    progress.publish('成單中', 0, 0, 0, 2, 2, '22')
    progress.publish('完成', 2, 1, 1, 0, 2)
    assert sheet.append_row.call_count == 1
    assert sheet.update.call_args.kwargs['range_name'] == 'A4:J4'
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
         patch.object(cloud, 'Progress') as reporter:
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
