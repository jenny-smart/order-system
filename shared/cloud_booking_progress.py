# -*- coding: utf-8 -*-
# 移植自 orders-system cloud_booking_progress.py。
"""One private Sheets snapshot per GitHub run/attempt, without customer data."""
import os
import re
import time
from datetime import datetime, timedelta, timezone

TITLE = '_雲端成單進度'
HEADERS = ['執行識別', '工作表', '階段', '處理列數', '成功列數', '失敗列數', '剩餘列數', '本次目標列數', '目前列號', '更新時間']


def decode(values):
    if len(values) < 10:
        return None
    try:
        counts = [int(value) for value in values[3:8]]
        if any(value < 0 for value in counts):
            return None
    except (TypeError, ValueError):
        return None
    return dict(zip(['key', 'sheet', 'phase', 'processed', 'success', 'failed', 'remaining', 'total', 'rows', 'updated_at'],
                    list(values[:3]) + counts + list(values[8:10])))


def read_progress(run_id, attempt=1):
    import orders
    import gspread
    try:
        sheet = orders.build_gsheet_client().open_by_key(orders.GOOGLE_SHEET_ID).worksheet(TITLE)
    except gspread.WorksheetNotFound:
        return None
    key = f'{run_id}:{attempt}'
    keys = sheet.col_values(1)
    matches = [i for i, value in enumerate(keys, 1) if value == key]
    return decode(sheet.get(f'A{matches[-1]}:J{matches[-1]}')[0]) if matches else None


class Progress:
    def __init__(self, sheet_name):
        self.name = sheet_name
        self.key = f"{os.getenv('GITHUB_RUN_ID', '')}:{os.getenv('GITHUB_RUN_ATTEMPT', '1')}"
        self.sheet = None
        self.row = None
        self.last_published = None

    def publish(self, phase, processed, success, failed, remaining, total, rows=''):
        if self.key.startswith(':'):
            return  # Local runs need no cloud progress table.
        now = time.monotonic()
        if phase == '成單中' and self.last_published is not None and now - self.last_published < 15:
            return
        try:
            import orders
            import gspread
            if self.sheet is None:
                book = orders.build_gsheet_client().open_by_key(orders.GOOGLE_SHEET_ID)
                try:
                    self.sheet = book.worksheet(TITLE)
                except gspread.WorksheetNotFound:
                    self.sheet = book.add_worksheet(title=TITLE, rows=200, cols=10)
                    self.sheet.update(range_name='A1:J1', values=[HEADERS], value_input_option='RAW')
            values = [self.key, self.name, phase, processed, success, failed, remaining, total, rows,
                      datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')]
            if self.row is None:
                result = self.sheet.append_row(values, value_input_option='RAW')
                self.row = int(re.search(r'!A(\d+)', result['updates']['updatedRange']).group(1))
            else:
                self.sheet.update(range_name=f'A{self.row}:J{self.row}', values=[values], value_input_option='RAW')
            self.last_published = time.monotonic()
        except Exception:
            print('PROGRESS_UNAVAILABLE: 無法同步畫面進度；成單流程繼續，請查看日誌。', flush=True)
