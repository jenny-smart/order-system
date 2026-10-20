# ============================================================
# 檔名：shared/unified_log.py
# 功能：各系統統一執行 Log。寫到主控表（Jenny's Lemonhometools）
#       「order-system執行Log-{年度}」，與 tool-system、orders-system、
#       salary-system 欄位相同，每個系統每年一張；新年度自動建表。
#       寫入失敗只印警告，不影響原本流程。
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo("Asia/Taipei")
MASTER_SPREADSHEET_ID = "1nNAXy6rvBnGR8ACnqKKzKNA4-UwZtZp47i806EPmR_8"
REPO = "order-system"
HEADERS = ["執行時間", "系統", "功能", "執行方式", "區域", "期別/日期", "目標位置", "來源檔案", "結果", "訊息", "執行者"]

_ensured: set[str] = set()


def sheet_title(repo: str = REPO, year: int | None = None) -> str:
    return f"{repo}執行Log-{year or datetime.now(TW_TZ).year}"


def build_row(*, system: str = "訂單系統", function: str = "", run_type: str = "", area: str = "",
              period: str = "", target: str = "", source_file: str = "", status: str = "",
              message: Any = "", operator: str = "") -> list[str]:
    return [datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S"), system, str(function or ""), str(run_type or ""),
            str(area or ""), str(period or ""), str(target or ""), str(source_file or ""), str(status or ""),
            str(message or "")[:2000], str(operator or "")]


def _worksheet(spreadsheet, repo: str):
    title = sheet_title(repo)
    if title in _ensured:
        return spreadsheet.worksheet(title)
    import gspread

    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(HEADERS))
        ws.update(range_name="A1", values=[HEADERS])
        ws.freeze(rows=1)
    _ensured.add(title)
    return ws


def write(*, repo: str = REPO, client=None, **fields: Any) -> None:
    """寫一筆統一 Log；欄位見 build_row。絕不拋出例外。"""
    try:
        if client is None:
            from shared.gsheet import build_gsheet_client

            client = build_gsheet_client()
        spreadsheet = client.open_by_key(os.getenv("MASTER_SPREADSHEET_ID", "").strip() or MASTER_SPREADSHEET_ID)
        _worksheet(spreadsheet, repo).append_row(build_row(**fields), value_input_option="RAW",
                                                  insert_data_option="INSERT_ROWS")
    except Exception as exc:  # Log 寫不進去不能影響主流程
        print(f"[unified_log] 寫入統一執行 Log 失敗（不影響主流程）: {exc}")
