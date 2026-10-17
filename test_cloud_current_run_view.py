# 移植自 orders-system test_cloud_current_run_view.py；模組路徑改為 order-system 的 shared/ 與 function/。
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def load(st):
    tree = ast.parse((Path(__file__).parent / 'function' / 'cloud_batch_booking.py').read_text())
    names = ('_sync_cloud_settings', '_is_current_run', '_render_cloud_status')
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes: node.decorator_list = []
    ns = {'st': st, 'REPO': 'repo', 'WORKFLOW': 'flow', '_token': lambda: 'token'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'ui', 'exec'), ns)
    return ns


def test_change_settings_detaches_old_result_without_cancelling_job():
    st = SimpleNamespace(session_state={'optimized_cloud_settings': ('old',),
                                       'optimized_cloud_current_run': (1, 1),
                                       'optimized_cloud_dispatch': {}, 'optimized_cloud_history': True})
    ns = load(st)
    ns['_sync_cloud_settings'](('new',))
    assert st.session_state == {'optimized_cloud_settings': ('new',)}
    assert not ns['_is_current_run']({'id': 1, 'run_attempt': 1})


def test_unchanged_settings_preserve_current_execution_result():
    st = SimpleNamespace(session_state={'optimized_cloud_settings': ('same',), 'optimized_cloud_current_run': (1, 2)})
    ns = load(st)
    ns['_sync_cloud_settings'](('same',))
    assert ns['_is_current_run']({'id': 1, 'run_attempt': 2})
    assert not ns['_is_current_run']({'id': 1, 'run_attempt': 1})


def test_completed_history_default_hides_metrics_errors_and_summary_reads():
    st = MagicMock()
    st.session_state = {}
    st.checkbox.return_value = False
    ns = load(st)
    ns['_latest_run'] = lambda: {'id': 1, 'status': 'completed', 'conclusion': 'failure'}
    ns['_render_live_progress'] = MagicMock()
    ns['_run_summary'] = MagicMock()
    ns['_render_cloud_status']()
    ns['_render_live_progress'].assert_not_called()
    ns['_run_summary'].assert_not_called()
    st.error.assert_not_called()
    assert '目前設定尚未啟動' in st.caption.call_args.args[0]


def test_active_background_job_still_shows_progress():
    st = MagicMock()
    st.session_state = {}
    ns = load(st)
    ns['_latest_run'] = lambda: {'id': 1, 'status': 'in_progress', 'html_url': 'url'}
    ns['_run_label'] = lambda run: 'run'
    ns['_render_live_progress'] = MagicMock()
    ns['_render_running_steps'] = MagicMock()
    ns['_render_cloud_status']()
    ns['_render_live_progress'].assert_called_once()
    st.checkbox.assert_not_called()
