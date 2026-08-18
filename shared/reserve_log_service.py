# ============================================================
# 檔名：shared/reserve_log_service.py
# 功能：檸檬保留單成立／取消紀錄寫入 Google Sheet；每 10 筆批次 append。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.gsheet import build_gsheet_client

SPREADSHEET_ID = "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE"
SHEET_NAME = "保留單紀錄"
HEADERS = ["操作時間", "操作", "訂單編號", "服務日期", "服務時段", "專員姓名", "訂單金額", "批次ID", "執行結果", "備註"]
DEFAULT_BATCH_SIZE = 10


def _now_tw() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")


def _number(value):
    if value in (None, ""):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group(0)) if m else None


def _first_number(mapping: dict, keys):
    for key in keys:
        if key in mapping:
            n = _number(mapping.get(key))
            if n is not None:
                return n
    return None


def service_amount_from_result(result: dict) -> str:
    """回傳含稅訂單總金額扣除車馬費；找不到時留空，不猜金額。"""
    result = dict(result or {})
    direct = _first_number(result, ["service_amount", "serviceAmount", "clean_amount", "cleanAmount"])
    if direct is not None:
        return str(int(direct)) if direct.is_integer() else str(direct)
    total = _first_number(result, ["order_total", "orderTotal", "total_amount", "totalAmount", "amount", "price", "total"])
    fare = _first_number(result, ["fare", "traffic_fee", "trafficFee", "car_fee", "carFee"]) or 0.0
    if total is None:
        return ""
    amount = total - fare
    return str(int(amount)) if float(amount).is_integer() else str(amount)


def make_log_row(*, operation: str, order_no="", service_date="", period="", staff="", amount="", batch_id="", success=True, note=""):
    return [
        _now_tw(), str(operation or ""), str(order_no or ""), str(service_date or ""),
        str(period or ""), str(staff or ""), str(amount or ""), str(batch_id or ""),
        "成功" if success else "失敗", str(note or ""),
    ]


def append_logs(rows, *, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    rows = [list(r) for r in (rows or []) if r]
    if not rows:
        return {"written": 0, "batches": 0}
    client = build_gsheet_client()
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    current_headers = ws.row_values(1)
    if current_headers[: len(HEADERS)] != HEADERS:
        raise RuntimeError(f"{SHEET_NAME} 欄位格式不符，請確認 A1:J1 標題。")
    size = max(1, int(batch_size or DEFAULT_BATCH_SIZE))
    batches = 0
    for i in range(0, len(rows), size):
        ws.append_rows(rows[i:i + size], value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
        batches += 1
    return {"written": len(rows), "batches": batches}
