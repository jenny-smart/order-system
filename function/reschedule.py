# -*- coding: utf-8 -*-
"""訂單班表記錄與返回：先記錄目前班表，之後可把訂單返回記錄的班表。

供排班要調班時使用（不需 Google 表單，直接查後台）：
1. 記錄：查執行日期區間的已付款訂單，記下每筆的日期／時段／專員，存到主控試算表
   「班表記錄」分頁（每次記錄一個記錄 ID）。
2. 返回：選一份記錄（可再用返回日期區間篩選記錄的日期），查後台目前狀態後，
   逐筆用「修改日期」改回記錄的日期／時段，馬上到「排班修改」配回記錄的專員並確認姓名，
   才做下一筆；配不回的位置不占其他待返回訂單的專員，全部跑完後再補試
   （沿用颱風假返回原班表的流程）。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import orders
from function import typhoon_sheet_sync as tss
from function import typhoon_transfer as tt


SNAPSHOT_SHEET_TITLE = "班表記錄"
SNAPSHOT_HEADERS = ["記錄ID", "記錄時間", "後台帳號", "執行日期區間", "訂單編號", "姓名", "日期", "時段", "專員"]


def rows_from_orders(orders_found):
    """後台查詢結果 → 記錄用的列（日期／時段／專員）。"""
    rows = []
    for index, row in enumerate(orders_found, 1):
        staff = tt.parse_staff_text(tt.staff_text(row.get("staff", "")))
        rows.append({
            "row": index,
            "order_no": row["order_no"],
            "name": row.get("name", ""),
            "orig_date": row["service_date"],
            "orig_period": row["period"],
            "orig_staff": staff,
            "now_date": row["service_date"],
            "now_period": row["period"],
            "now_staff": list(staff),
            "status": "已記錄",
        })
    return rows


# ---------------------------------------------------------
# 班表記錄（主控試算表「班表記錄」分頁）
# ---------------------------------------------------------

def _snapshot_worksheet(client=None):
    client = client or orders.build_gsheet_client()
    spreadsheet = client.open_by_key(orders.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(SNAPSHOT_SHEET_TITLE)
    except orders.gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SNAPSHOT_SHEET_TITLE, rows=1000, cols=len(SNAPSHOT_HEADERS))
        worksheet.update(range_name="A1", values=[SNAPSHOT_HEADERS])
    return worksheet


def save_snapshot(account, range_label, rows, client=None):
    """存一份班表記錄，回傳記錄 ID。"""
    if not rows:
        raise ValueError("沒有要記錄的訂單")
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    snapshot_id = now.strftime("%Y%m%d-%H%M%S")
    recorded_at = now.strftime("%Y-%m-%d %H:%M")
    values = [
        [snapshot_id, recorded_at, str(account or "").strip(), range_label, r["order_no"], r.get("name", ""),
         r["orig_date"], r["orig_period"], "、".join(r["orig_staff"])]
        for r in rows
    ]
    _snapshot_worksheet(client).append_rows(values, value_input_option="RAW")
    return snapshot_id


def _snapshot_records(client=None):
    values = _snapshot_worksheet(client).get_all_values()
    headers = values[0] if values else SNAPSHOT_HEADERS
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[1:] if row and row[0]]


def list_snapshots(client=None):
    """列出所有班表記錄（新的在前）：[{id, recorded_at, account, range, count}]。"""
    grouped = {}
    for rec in _snapshot_records(client):
        item = grouped.setdefault(rec["記錄ID"], {
            "id": rec["記錄ID"], "recorded_at": rec["記錄時間"], "account": rec["後台帳號"],
            "range": rec["執行日期區間"], "count": 0,
        })
        item["count"] += 1
    return sorted(grouped.values(), key=lambda x: x["id"], reverse=True)


def load_snapshot_items(snapshot_id, date_start=None, date_end=None, client=None):
    """讀一份記錄；有給返回日期區間時，只取記錄日期在區間內的訂單。"""
    items = []
    for rec in _snapshot_records(client):
        if rec["記錄ID"] != snapshot_id:
            continue
        day = tt._normalize_date_text(rec["日期"])
        if date_start and day < str(date_start):
            continue
        if date_end and day > str(date_end):
            continue
        items.append({
            "row": len(items) + 1, "order_no": rec["訂單編號"], "name": rec["姓名"],
            "orig_date": day, "orig_period": rec["時段"], "orig_staff": rec["專員"],
        })
    return items


def plan_return(env_name, backend_email, backend_password, items, progress=None):
    """查後台目前狀態，列出要返回記錄班表的訂單；不修改後台。"""
    rows = tss.plan_restore_items(env_name, backend_email, backend_password, items, progress=progress)
    names = {i["order_no"]: i.get("name", "") for i in items}
    for row in rows:
        row["name"] = row.get("name") or names.get(row["order_no"], "")
    return rows


def execute_return(env_name, backend_email, backend_password, rows, progress=None):
    """逐筆返回記錄的班表（改回日期／時段並配回專員，避免連鎖錯誤）。"""
    return tss.execute_restore(env_name, backend_email, backend_password, rows, progress=progress)
