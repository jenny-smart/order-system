# 移植自 orders-system test_cloud_failed_candidates.py；模組路徑改為 order-system 的 shared/ 與 function/。
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import shared.booking_eligibility as booking_eligibility


def test_failed_rows_excluded_from_candidates_and_auto_filters():
    source = Path(__file__).parent / 'shared' / 'selected_row_status_guard.py'
    names = {'_scalar', 'normalize_status', '_first_series', '_safe_load_candidates', '_auto_filter_rows', '_mode_mask', '_creatable', '_o_label'}
    tree = ast.parse(source.read_text())
    base = {'姓名': '王小明', '電話': '0912345678', '地址': '台北市',
            '日期': '2026-11-10', '開始時間': '09:00', '結束時間': '12:00',
            '狀態': '未安排', '訂單編號': '', '原因': '無班表；找不到訂單編號'}
    rows = [
        {**base, '__sheet_row__': 2, '結果': ''},
        {**base, '__sheet_row__': 3, '結果': '失敗'},
        {**base, '__sheet_row__': 4, '結果': ' 失敗\u200b '},
        {**base, '__sheet_row__': 5, '結果': '', '狀態': '已安排'},
        {**base, '__sheet_row__': 6, '結果': '失敗', '訂單編號': 'LC123'},
        {**base, '__sheet_row__': 7, '結果': '', '預約條件': '未回覆'},
    ]
    namespace = {'pd': pd, 're': re, '_load_worksheet_unique': lambda _: (None, pd.DataFrame(rows)),
                 'O_BLANK_OPTION': '（O欄空白）', '_ORDER_NO_PATTERN': r'(?:LC|TT|KK)\d+',
                 **{k: getattr(booking_eligibility, k) for k in ('HOLD_COLUMN', 'can_create_order', 'can_process_row', 'normalize_status')}}
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), str(source), 'exec'), namespace)
    batch = SimpleNamespace(REQUIRED_COLUMNS=list(base), _text=lambda v: str(v or '').strip(),
                            _date_text=str, _time_text=str)
    candidates = namespace['_safe_load_candidates'](batch, '台北202611')
    # Keep existing orders available for downstream follow-up, but exclude them from new booking.
    assert candidates['__sheet_row__'].tolist() == [2, 6]
    pending = candidates[candidates['訂單編號'].eq('')]
    assert pending['__sheet_row__'].tolist() == [2]
    for mode in ('no_schedule', 'missing_order'):
        assert namespace['_auto_filter_rows'](batch, '台北202611', mode) == [2]
