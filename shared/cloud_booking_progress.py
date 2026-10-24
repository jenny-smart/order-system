# -*- coding: utf-8 -*-
# 移植自 orders-system cloud_booking_progress.py。
"""One private Sheets snapshot per GitHub run/attempt, without customer data."""
import os
import re
import time
from datetime import datetime, timedelta, timezone

TITLE = '_雲端成單進度'
HEADERS = ['執行識別', '工作表', '階段', '處理列數', '成功列數', '失敗列數', '剩餘列數', '本次目標列數', '目前列號', '更新時間',
           '未選對象略過列數', '控制']
PAUSE = '暫停'  # 畫面按「暫停成單」寫入「控制」欄；雲端在下一組開始前看到就停。
PAUSED_PHASE = '已暫停'
PAUSE_CHECK_SECONDS = 10


def decode(values):
    if len(values) < 10:
        return None
    try:
        counts = [int(value) for value in values[3:8]]
        if any(value < 0 for value in counts):
            return None
    except (TypeError, ValueError):
        return None
    snapshot = dict(zip(['key', 'sheet', 'phase', 'processed', 'success', 'failed', 'remaining', 'total', 'rows', 'updated_at'],
                        list(values[:3]) + counts + list(values[8:10])))
    # 舊版進度列沒有第 11 欄；空白或不合法都視為 0。
    try:
        snapshot['held'] = max(int(values[10]), 0) if len(values) > 10 and str(values[10]).strip() else 0
    except (TypeError, ValueError):
        snapshot['held'] = 0
    snapshot['control'] = str(values[11]).strip() if len(values) > 11 else ''
    return snapshot


def _progress_sheet():
    import orders
    import gspread
    try:
        return orders.build_gsheet_client().open_by_key(orders.GOOGLE_SHEET_ID).worksheet(TITLE)
    except gspread.WorksheetNotFound:
        return None


def request_pause(run_id, attempt=1):
    """在該次執行的進度列寫入「暫停」；找不到進度列（尚未開始成單）回傳 False。"""
    sheet = _progress_sheet()
    if sheet is None:
        return False
    key = f'{run_id}:{attempt}'
    matches = [i for i, value in enumerate(sheet.col_values(1), 1) if value == key]
    if not matches:
        return False
    if sheet.col_count < len(HEADERS):
        sheet.resize(cols=len(HEADERS))
    sheet.update(range_name=f'L{matches[-1]}', values=[[PAUSE]], value_input_option='RAW')
    return True


def read_progress(run_id, attempt=1):
    sheet = _progress_sheet()
    if sheet is None:
        return None
    key = f'{run_id}:{attempt}'
    keys = sheet.col_values(1)
    matches = [i for i, value in enumerate(keys, 1) if value == key]
    return decode(sheet.get(f'A{matches[-1]}:L{matches[-1]}')[0]) if matches else None


class Progress:
    def __init__(self, sheet_name):
        self.name = sheet_name
        self.key = f"{os.getenv('GITHUB_RUN_ID', '')}:{os.getenv('GITHUB_RUN_ATTEMPT', '1')}"
        self.sheet = None
        self.row = None
        self.last_published = None
        self.held = 0
        self.last_pause_check = None
        self.paused = False

    def pause_requested(self):
        """畫面是否按了「暫停成單」；最多每 10 秒讀一次，讀不到就當作沒有暫停。"""
        if self.paused:
            return True
        if self.sheet is None or self.row is None:
            return False
        now = time.monotonic()
        if self.last_pause_check is not None and now - self.last_pause_check < PAUSE_CHECK_SECONDS:
            return False
        self.last_pause_check = now
        try:
            values = self.sheet.get(f'L{self.row}')
            self.paused = bool(values and values[0] and str(values[0][0]).strip() == PAUSE)
        except Exception:
            return False
        return self.paused

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
                    self.sheet = book.add_worksheet(title=TITLE, rows=200, cols=len(HEADERS))
                if self.sheet.col_count < len(HEADERS):
                    self.sheet.resize(cols=len(HEADERS))
                self.sheet.update(range_name='A1:L1', values=[HEADERS], value_input_option='RAW')
            values = [self.key, self.name, phase, processed, success, failed, remaining, total, rows,
                      datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'), self.held]
            if self.row is None:
                result = self.sheet.append_row(values, value_input_option='RAW')
                self.row = int(re.search(r'!A(\d+)', result['updates']['updatedRange']).group(1))
            else:
                self.sheet.update(range_name=f'A{self.row}:K{self.row}', values=[values], value_input_option='RAW')
            self.last_published = time.monotonic()
        except Exception:
            print('PROGRESS_UNAVAILABLE: 無法同步畫面進度；成單流程繼續，請查看日誌。', flush=True)
