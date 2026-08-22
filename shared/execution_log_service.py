# ============================================================
# 檔名：shared/execution_log_service.py
# 功能：訂單系統各項「異動操作」（建立/取消訂單、寄信、同步日曆、
#       儲存備註狀態…）統一寫入本專案自己的執行 Log 試算表。
#       此 Log 完全獨立於其他系統，不與任何外部系統共用或同步。
# 更新時間：2026-08-22
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import traceback as _traceback_module
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

from shared.gsheet import build_gsheet_client

# 本專案（order-system）自己的主控檔，僅供本系統使用，不與其他系統共用。
SPREADSHEET_ID = "1fj0P232u0A9EGnGdy620TsyfqM2S86EEpGfpyP7Ya90"
SHEET_NAME = "訂單系統執行Log"
HEADERS = ["執行時間", "功能", "執行方式", "區域", "期別/日期", "目標位置", "結果", "訊息"]

_ensured = False


def _now_tw() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_status(status) -> str:
    """把各種可能的狀態值正規化成「成功」或「失敗」。"""
    if isinstance(status, BaseException):
        return "失敗"
    if isinstance(status, bool):
        return "成功" if status else "失敗"
    text = str(status or "").strip().lower()
    if text in ("成功", "success", "ok", "true", "done", "完成"):
        return "成功"
    if text in ("失敗", "fail", "failed", "error", "false", "錯誤"):
        return "失敗"
    # 預設：非空字串視為成功描述，空值視為失敗（避免漏記）
    return "成功" if text else "失敗"


def _ensure_sheet(client):
    """確保工作表存在且有標題列；每個 process 只檢查一次。"""
    global _ensured
    if _ensured:
        return
    sh = client.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.update("A1", [HEADERS])
        _ensured = True
        return

    current_headers = ws.row_values(1)
    if current_headers[: len(HEADERS)] != HEADERS:
        ws.update("A1", [HEADERS])
    _ensured = True


def log_execution(
    *,
    function_name: str,
    status,
    run_type: str = "手動",
    area: str = "",
    date: str = "",
    target: str = "",
    message: str = "",
    traceback_text: str = "",
) -> None:
    """記錄一筆執行 Log。絕不拋出例外——寫入失敗只印警告，不能影響原本流程。"""
    try:
        client = build_gsheet_client()
        _ensure_sheet(client)
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

        result = _normalize_status(status)
        msg = str(message or "")
        if traceback_text:
            msg = f"{msg}\n{traceback_text}".strip()

        row = [
            _now_tw(),
            str(function_name or ""),
            str(run_type or ""),
            str(area or ""),
            str(date or ""),
            str(target or ""),
            result,
            msg,
        ]
        ws.append_row(row, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
    except Exception as e:
        print(f"[execution_log_service] 寫入執行 Log 失敗（不影響主流程）: {e}")
        try:
            print(_traceback_module.format_exc())
        except Exception:
            pass
