# -*- coding: utf-8 -*-
"""未配班檢查：頁面上可改的排程設定（存主控表）。

2026-11-27 Jenny：在「未配班檢查」頁面改排程，不用到 tool-system／GitHub。
- 排程時間：主控表「排程設定」該功能那列的 D 欄（例「08:30~17:30 每小時」「11:10」「08:30,13:30」），
  tool-system Cloud Schedule Router 每次派送前都會讀，存檔後下一個時段生效。
- 記錄未配班人員的範圍天數：主控表「參數設定」（執行系統＝訂單系統、執行功能＝記錄未配班人員、
  項目＝範圍天數），排程每次執行讀取；沒設定用 14 天。
"""
from __future__ import annotations

import re
from typing import Callable, Optional

SCHEDULE_SHEET = "排程設定"
PARAM_SHEET = "參數設定"
RECORD_KEY = "unassigned_staff_record"
RESERVE_KEY = "unassigned_reserve_create"
SYSTEM, RECORD_FUNCTION, AREA = "訂單系統", "記錄未配班人員", "台北"
DAYS_ITEM = "範圍天數"
DEFAULT_DAYS = 14
_HM = r"(\d{1,2}):(\d{2})"
_RANGE_RE = re.compile(rf"^{_HM}\s*[~～\-－]\s*{_HM}\s*每\s*(\d*)\s*(小時|分鐘|分)$")


def _master():
    from shared.gsheet import build_gsheet_client
    from year_roots import _master_id

    return build_gsheet_client().open_by_key(_master_id())


def _cell(row: list, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) else ""


# ---------------------------------------------------------------------------
# 排程時間（排程設定 D 欄）
# ---------------------------------------------------------------------------
def build_time_text(mode: str, start: str = "", end: str = "", every: str = "每小時", times: list[str] = ()) -> str:
    """頁面選項 → 排程設定 D 欄文字。mode：區間／固定時間。"""
    if mode == "區間":
        return f"{start}~{end} {every}"
    return ",".join(sorted({t for t in times if t}))


def validate_time_text(text: str) -> str:
    """檢查格式（與 tool-system 相同規則）；分鐘須為 10 的倍數（Router 每 10 分鐘派送一次）。回傳錯誤訊息或空字串。"""
    text = str(text or "").strip()
    if not text:
        return "排程時間不能空白"
    for part in re.split(r"[,，、]", text):
        part = part.strip()
        m = _RANGE_RE.match(part)
        if m:
            h1, m1, h2, m2 = (int(m.group(i)) for i in (1, 2, 3, 4))
            if (h1, m1) >= (h2, m2):
                return f"「{part}」結束時間要晚於開始時間"
            n = int(m.group(5) or 1)
            if m.group(6) != "小時" and (n < 10 or n % 10):
                return f"「{part}」間隔分鐘要是 10 的倍數"
            hms = [(h1, m1), (h2, m2)]
        else:
            t = re.fullmatch(_HM, part)
            if not t:
                return f"看不懂「{part}」（例：08:30~17:30 每小時、11:10、08:30,13:30）"
            hms = [(int(t.group(1)), int(t.group(2)))]
        for h, mi in hms:
            if h > 23 or mi > 59:
                return f"「{part}」時間不正確"
            if mi % 10:
                return f"「{part}」分鐘要是 10 的倍數（排程每 10 分鐘派送一次）"
    return ""


def find_schedule_row(values: list[list], key: str) -> Optional[int]:
    for row_no, row in enumerate(values, start=1):
        if _cell(row, 1) == key:
            return row_no
    return None


def load_schedule_time(key: str, worksheet_factory: Callable = None) -> str:
    ws = (worksheet_factory or (lambda: _master().worksheet(SCHEDULE_SHEET)))()
    values = ws.get_all_values()
    row = find_schedule_row(values, key)
    return _cell(values[row - 1], 3) if row else ""


def save_schedule_time(key: str, text: str, worksheet_factory: Callable = None) -> None:
    error = validate_time_text(text)
    if error:
        raise ValueError(error)
    ws = (worksheet_factory or (lambda: _master().worksheet(SCHEDULE_SHEET)))()
    row = find_schedule_row(ws.get_all_values(), key)
    if not row:
        raise RuntimeError(f"主控表「{SCHEDULE_SHEET}」找不到功能代號 {key}")
    ws.batch_update([{"range": f"D{row}", "values": [[text.strip()]]}], value_input_option="RAW")


# ---------------------------------------------------------------------------
# 記錄未配班人員：範圍天數（參數設定）
# ---------------------------------------------------------------------------
def parse_days(values: list[list]) -> Optional[int]:
    for row in values[1:]:
        if (_cell(row, 0), _cell(row, 1), _cell(row, 3)) == (SYSTEM, RECORD_FUNCTION, DAYS_ITEM) \
                and _cell(row, 5).upper() != "FALSE":
            try:
                days = int(float(_cell(row, 4)))
            except ValueError:
                return None
            return days if 1 <= days <= 60 else None
    return None


def load_days(worksheet_factory: Callable = None, log: Callable[[str], None] = None) -> int:
    """參數設定的範圍天數；讀不到或沒設定用 14。"""
    try:
        ws = (worksheet_factory or (lambda: _master().worksheet(PARAM_SHEET)))()
        return parse_days(ws.get_all_values()) or DEFAULT_DAYS
    except Exception as exc:
        if log:
            log(f"⚠️ 讀取主控表「{PARAM_SHEET}」範圍天數失敗，改用 {DEFAULT_DAYS} 天：{type(exc).__name__}: {exc}")
        return DEFAULT_DAYS


def save_days(days: int, worksheet_factory: Callable = None) -> None:
    days = int(days)
    if not 1 <= days <= 60:
        raise ValueError("天數要在 1～60 之間")
    ws = (worksheet_factory or (lambda: _master().worksheet(PARAM_SHEET)))()
    values = ws.get_all_values()
    for row_no, row in enumerate(values[1:], start=2):
        if (_cell(row, 0), _cell(row, 1), _cell(row, 3)) == (SYSTEM, RECORD_FUNCTION, DAYS_ITEM):
            ws.batch_update([{"range": f"E{row_no}:F{row_no}", "values": [[str(days), "TRUE"]]}],
                            value_input_option="RAW")
            return
    ws.append_rows([[SYSTEM, RECORD_FUNCTION, AREA, DAYS_ITEM, str(days), "TRUE",
                     "未配班檢查頁面設定（明天起幾天，排程每次讀取）", ""]], value_input_option="RAW")
