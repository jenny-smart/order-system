# -*- coding: utf-8 -*-
"""Write reserve-order create/cancel logs to Google Sheets."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

SPREADSHEET_ID = "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE"
WORKSHEET_NAME = "保留單紀錄"
HEADERS = ["操作時間", "操作", "訂單編號", "服務日期", "服務時段", "專員姓名", "訂單金額", "批次ID", "執行結果", "備註"]


def _client():
    """沿用 order-system 共用的 Google 服務帳號連線（含 Sheets 配額節流）。"""
    from shared.gsheet import build_gsheet_client
    return build_gsheet_client()


def _staff_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("staff_name") or item.get("staffName") or item.get("label") or ""
                if name:
                    parts.append(str(name).strip())
            elif item:
                parts.append(str(item).strip())
        return " X ".join([p for p in parts if p])
    if isinstance(value, dict):
        return str(value.get("name") or value.get("staff_name") or value.get("staffName") or value)
    return str(value)


def _amount(value) -> object:
    if value in (None, ""):
        return 0
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except Exception:
        return value


def _worksheet():
    ws = _client().open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    current = ws.row_values(1)
    if current[: len(HEADERS)] != HEADERS:
        ws.update("A1:J1", [HEADERS])
    return ws


def append_log_rows(operation: str, rows: list[dict], batch_id: str = "") -> int:
    """Append only successful create/cancel rows. Returns written row count."""
    payload = []
    now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
    for row in rows or []:
        success = row.get("success")
        if success is None:
            success = row.get("ok")
        # cancel_order may return message-only success rows. Treat explicit False as failure.
        if success is False:
            continue

        amount = (
            row.get("order_amount")
            if row.get("order_amount") not in (None, "")
            else row.get("total_amount")
            if row.get("total_amount") not in (None, "")
            else row.get("amount")
            if row.get("amount") not in (None, "")
            else row.get("price")
        )
        payload.append([
            now,
            operation,
            str(row.get("order_no") or ""),
            str(row.get("service_date") or ""),
            str(row.get("period") or row.get("service_period") or ""),
            _staff_text(row.get("staff") or row.get("staff_names") or row.get("service_staff")),
            _amount(amount),
            str(row.get("batch_id") or batch_id or ""),
            "成功",
            str(row.get("message") or row.get("note_message") or ""),
        ])

    if not payload:
        return 0
    _worksheet().append_rows(payload, value_input_option="USER_ENTERED")
    return len(payload)
