# 移植自 orders-system test_cloud_booking_status.py；模組路徑改為 order-system 的 shared/ 與 function/。
import ast
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).parent / 'function' / 'cloud_batch_booking.py'


def load_status(get):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_latest_run', '_run_summary', '_run_label')]
    ns = {'_github_get': get, 'WORKFLOW': 'booking.yml', 're': re, 'datetime': datetime, 'timezone': timezone, 'timedelta': timedelta}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


def test_status_has_no_run():
    functions = load_status(lambda _: SimpleNamespace(json=lambda: {'workflow_runs': []}))
    assert functions['_latest_run']() is None


@pytest.mark.parametrize('log,expected', [
    ('FINISH attempted=30 success=25 fail=5 remaining=233', (30, 25, 5, 233)),
    ('Traceback: credentials missing', None),
])
def test_summary_distinguishes_partial_completion_from_startup_failure(log, expected):
    def get(path):
        if path.endswith('/jobs'):
            return SimpleNamespace(json=lambda: {'jobs': [{'name': 'booking', 'id': 123}]})
        assert path == 'actions/jobs/123/logs'
        return SimpleNamespace(text=log)
    assert load_status(get)['_run_summary'](456) == expected


def test_run_label_distinguishes_date_number_and_attempt_in_taipei_time():
    label = load_status(None)['_run_label']({'run_number': 42, 'run_attempt': 2,
                                          'created_at': '2026-10-07T16:13:53Z'})
    assert '2026-10-08 00:13:53' in label
    assert '第 42 次執行' in label and '第 2 次嘗試' in label


def test_run_label_handles_missing_time():
    assert '啟動時間未提供' in load_status(None)['_run_label']({'run_number': 42})
