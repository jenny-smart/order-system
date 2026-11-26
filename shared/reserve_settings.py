# -*- coding: utf-8 -*-
"""未配班成立保留單：自動排程的區間與停止日，存在主控表「參數設定」。

2026-11-26 Jenny：不再改 GitHub 變數，改在「未配班檢查 → ① 成立保留單」頁面設定。
- 參數設定三列（執行系統＝訂單系統、執行功能＝未配班成立保留單、地區＝台北）：
  保留單開始日／保留單結束日／自動成立停止日（YYYY/MM/DD；停止日空白＝不停止）。
- 排程讀取順序：手動執行參數 → 參數設定 → repository variable → 程式預設。
- 停止日當天（含）起排程不再成立保留單；頁面上的手動成立不受影響。
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

PARAM_SHEET = "參數設定"
SYSTEM = "訂單系統"
FUNCTION = "未配班成立保留單"
AREA = "台北"
START_ITEM, END_ITEM, STOP_ITEM = "保留單開始日", "保留單結束日", "自動成立停止日"
ITEMS = (START_ITEM, END_ITEM, STOP_ITEM)
NOTE = "未配班檢查頁面設定（排程每小時讀取）"


def _cell(row: list, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) else ""


def parse_settings(values: list[list]) -> dict[str, str]:
    """參數設定整張表 → {項目: 設定值}；啟用欄（F）為 FALSE 的列略過。"""
    found: dict[str, str] = {}
    for row in values[1:]:
        if (_cell(row, 0), _cell(row, 1)) != (SYSTEM, FUNCTION) or _cell(row, 3) not in ITEMS:
            continue
        if _cell(row, 5).upper() == "FALSE":
            continue
        found[_cell(row, 3)] = _cell(row, 4)
    return found


def plan_writes(values: list[list], settings: dict[str, str]) -> tuple[list[dict], list[list]]:
    """回傳 (既有列要改的儲存格, 要新增的列)。"""
    updates, rows_by_item = [], {}
    for row_no, row in enumerate(values[1:], start=2):
        if (_cell(row, 0), _cell(row, 1)) == (SYSTEM, FUNCTION) and _cell(row, 3) in ITEMS:
            rows_by_item.setdefault(_cell(row, 3), row_no)
    appends = []
    for item in ITEMS:
        value = settings.get(item, "")
        if item in rows_by_item:
            updates.append({"range": f"E{rows_by_item[item]}:F{rows_by_item[item]}", "values": [[value, "TRUE"]]})
        else:
            appends.append([SYSTEM, FUNCTION, AREA, item, value, "TRUE", NOTE, ""])
    return updates, appends


def fmt(day: Optional[date]) -> str:
    return f"{day:%Y/%m/%d}" if day else ""


def _worksheet():
    from shared.gsheet import build_gsheet_client
    from year_roots import _master_id

    return build_gsheet_client().open_by_key(_master_id()).worksheet(PARAM_SHEET)


def load(worksheet_factory: Callable = None, log: Callable[[str], None] = None) -> dict[str, str]:
    """讀參數設定；讀不到時回傳空 dict（排程改用 repository variable／程式預設）。"""
    try:
        return parse_settings((worksheet_factory or _worksheet)().get_all_values())
    except Exception as exc:
        if log:
            log(f"⚠️ 讀取主控表「{PARAM_SHEET}」保留單設定失敗，改用預設值：{type(exc).__name__}: {exc}")
        return {}


def save(start: date, end: date, stop: Optional[date], worksheet_factory: Callable = None) -> None:
    if end < start:
        raise ValueError("結束日不能早於開始日")
    ws = (worksheet_factory or _worksheet)()
    updates, appends = plan_writes(ws.get_all_values(),
                                   {START_ITEM: fmt(start), END_ITEM: fmt(end), STOP_ITEM: fmt(stop)})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    if appends:
        ws.append_rows(appends, value_input_option="RAW")


def stopped(today: date, settings: dict[str, str]) -> Optional[date]:
    """停止日已到（今天 ≥ 停止日）就回傳停止日，否則 None。"""
    from shared.unassigned_reserve_schedule import parse_day

    text = settings.get(STOP_ITEM, "")
    if not text:
        return None
    day = parse_day(text)
    return day if today >= day else None
