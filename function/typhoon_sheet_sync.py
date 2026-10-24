# -*- coding: utf-8 -*-
"""颱風假訂單移轉：讀客服的 Google 表單，查後台目前日期／時段，有異動才填入「異動日期／異動時段」欄。

流程：
1. 依設定（試算表 ID、工作表名稱、訂單編號／原日期／原時段／新日期／新時段／
   異動日期／異動時段欄、起始列）讀取表單。
2. 逐筆查後台目前的服務日期／時段，和表單的新日期／新時段比對（compare_sheet_orders）。
   新日期／新時段只讀不改。
3. 客服確認後才寫入（apply_sheet_updates）：
   - 和新日期／新時段不同 → 異動欄填入目前日期／時段；
   - 相同但異動欄還有舊值 → 清成空白；
   - 相同且異動欄空白 → 不動。
   寫入前重讀這些格子，若比對後被手動改過就跳過，不覆蓋。

設定存在主控試算表「颱風移轉設定」分頁，每個後台帳號一列。
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import orders
import quick_order as qo
from function import typhoon_transfer as tt


SETTINGS_SHEET_TITLE = "颱風移轉設定"
SETTING_FIELDS = [
    ("spreadsheet_id", "試算表ID"),
    ("worksheet", "工作表名稱"),
    ("order_col", "訂單編號欄"),
    ("orig_date_col", "原日期欄"),
    ("orig_period_col", "原時段欄"),
    ("new_date_col", "新日期欄"),
    ("new_period_col", "新時段欄"),
    ("change_date_col", "異動日期欄"),
    ("change_period_col", "異動時段欄"),
    ("start_row", "起始列"),
]
SETTINGS_HEADERS = ["後台帳號"] + [label for _key, label in SETTING_FIELDS] + ["更新時間"]
DEFAULT_SETTINGS = {
    "spreadsheet_id": "", "worksheet": "", "order_col": "A",
    "orig_date_col": "F", "orig_period_col": "G",
    "new_date_col": "I", "new_period_col": "J",
    "change_date_col": "L", "change_period_col": "M", "start_row": "2",
}


def _now_text():
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")


def spreadsheet_id_from_text(text):
    """接受試算表網址或 ID。"""
    text = str(text or "").strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    return match.group(1) if match else text


def column_index(letter):
    """欄位英文字母 → 0 起算的索引（A=0、AA=26）。"""
    letter = str(letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", letter):
        raise ValueError(f"欄位請輸入英文字母（例如 A、I、AA），收到：{letter or '空白'}")
    index = 0
    for ch in letter:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def validate_settings(settings):
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    settings["spreadsheet_id"] = spreadsheet_id_from_text(settings["spreadsheet_id"])
    if not settings["spreadsheet_id"]:
        raise ValueError("請輸入 Google 試算表 ID 或網址")
    if not str(settings["worksheet"]).strip():
        raise ValueError("請輸入工作表名稱")
    required = ("order_col", "new_date_col", "new_period_col", "change_date_col", "change_period_col")
    for key in required:
        column_index(settings[key])
    for key in ("orig_date_col", "orig_period_col"):
        if str(settings[key]).strip():
            column_index(settings[key])
    used = [str(settings[k]).strip().upper() for k in required]
    if len(set(used)) != len(used):
        raise ValueError("訂單編號欄、新日期欄、新時段欄、異動日期欄、異動時段欄不可重複")
    protected = {str(settings[k]).strip().upper() for k in ("order_col", "orig_date_col", "orig_period_col", "new_date_col", "new_period_col") if str(settings[k]).strip()}
    for key in ("change_date_col", "change_period_col"):
        if str(settings[key]).strip().upper() in protected:
            raise ValueError("異動日期欄／異動時段欄不可和訂單編號、原日期時段、新日期時段同一欄")
    try:
        start_row = int(settings["start_row"])
    except Exception:
        raise ValueError("起始列請輸入數字")
    if start_row < 1:
        raise ValueError("起始列需大於 0")
    settings["start_row"] = str(start_row)
    return settings


# ---------------------------------------------------------
# 設定暫存（主控試算表「颱風移轉設定」分頁）
# ---------------------------------------------------------

def _settings_worksheet(client=None):
    client = client or orders.build_gsheet_client()
    spreadsheet = client.open_by_key(orders.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(SETTINGS_SHEET_TITLE)
    except orders.gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SETTINGS_SHEET_TITLE, rows=100, cols=len(SETTINGS_HEADERS))
        worksheet.update(range_name="A1", values=[SETTINGS_HEADERS])
    return worksheet


def _row_to_settings(headers, row):
    """依標題名稱讀值，舊版設定（少了新欄位）也讀得到。"""
    by_header = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
    saved = {key: by_header.get(label, "") for key, label in SETTING_FIELDS}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if str(v).strip() != ""}}


def load_settings(account, client=None):
    """讀這個後台帳號上次存的設定；沒有就回傳預設值。"""
    values = _settings_worksheet(client).get_all_values()
    headers = values[0] if values else SETTINGS_HEADERS
    for row in values[1:]:
        if row and row[0].strip() == str(account or "").strip():
            return _row_to_settings(headers, row)
    return dict(DEFAULT_SETTINGS)


def save_settings(account, settings, client=None):
    settings = validate_settings(settings)
    worksheet = _settings_worksheet(client)
    values = worksheet.get_all_values()
    headers = values[0] if values else []
    if headers != SETTINGS_HEADERS:
        # 舊版標題：依標題名稱轉成新格式後整份重寫
        migrated = [SETTINGS_HEADERS]
        for row in values[1:]:
            if row and row[0].strip():
                old = _row_to_settings(headers, row)
                by_header = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
                migrated.append([row[0].strip()] + [str(old[k]) for k, _l in SETTING_FIELDS] + [by_header.get("更新時間", "")])
        worksheet.update(range_name="A1", values=migrated)
        values = migrated
    row_values = [str(account or "").strip()] + [str(settings[key]) for key, _label in SETTING_FIELDS] + [_now_text()]
    for row_no, row in enumerate(values[1:], 2):
        if row and row[0].strip() == row_values[0]:
            worksheet.update(range_name=f"A{row_no}", values=[row_values])
            return settings
    worksheet.append_row(row_values, value_input_option="RAW")
    return settings


# ---------------------------------------------------------
# 比對與寫回
# ---------------------------------------------------------

def _open_target(settings, client=None):
    client = client or orders.build_gsheet_client()
    return client.open_by_key(settings["spreadsheet_id"]).worksheet(settings["worksheet"])


def _cell(row, index):
    return str(row[index]).strip() if index is not None and index < len(row) else ""


def read_sheet_orders(values, settings):
    """從工作表全部值取出要比對的列。"""
    start_row = int(settings["start_row"])
    idx = {key: column_index(settings[key]) if str(settings.get(key, "")).strip() else None
           for key in ("order_col", "orig_date_col", "orig_period_col", "new_date_col", "new_period_col",
                       "change_date_col", "change_period_col")}
    items, seen = [], set()
    for row_no in range(start_row, len(values) + 1):
        row = values[row_no - 1]
        order_no = _cell(row, idx["order_col"])
        if not re.fullmatch(orders.ORDER_NO_REGEX, order_no) or order_no in seen:
            continue
        seen.add(order_no)
        items.append({
            "row": row_no,
            "order_no": order_no,
            "orig_date": _cell(row, idx["orig_date_col"]),
            "orig_period": _cell(row, idx["orig_period_col"]),
            "sheet_date": _cell(row, idx["new_date_col"]),
            "sheet_period": _cell(row, idx["new_period_col"]),
            "change_date": _cell(row, idx["change_date_col"]),
            "change_period": _cell(row, idx["change_period_col"]),
        })
    return items


def _same_date(left, right):
    return tt._normalize_date_text(left) == tt._normalize_date_text(right)


def compare_sheet_orders(env_name, backend_email, backend_password, settings, client=None, progress=None):
    """讀表單並逐筆查後台目前日期／時段；不寫入。"""
    settings = validate_settings(settings)
    worksheet = _open_target(settings, client)
    items = read_sheet_orders(worksheet.get_all_values(), settings)
    session, _base_url = tt._login(env_name, backend_email, backend_password)
    rows = []
    for index, item in enumerate(items, 1):
        if progress:
            progress(index, len(items), item)
        row = {**item, "now_date": "", "now_period": "", "payment_status": "", "status": "", "name": ""}
        try:
            block = qo._fetch_purchase_block_for_order_no(session, item["order_no"])
            lines = block.get("lines", [])
            joined = "\n".join(lines)
            now_date, now_period = qo._parse_service_date_time_loose(joined)
            row["now_date"], row["now_period"] = now_date, tt._compact_period(now_period)
            status_match = re.search(r"付款狀態[：:]\s*([^\n]+)", joined)
            row["payment_status"] = status_match.group(1).strip() if status_match else ""
            for i, line in enumerate(lines):
                if re.fullmatch(r"09\d{8}", str(line).strip()):
                    row["name"] = str(lines[i - 1]).strip() if i else ""
                    break
            if not row["now_date"] or not row["now_period"]:
                row["status"] = "查詢失敗：讀不到目前日期／時段"
            elif _same_date(row["now_date"], item["sheet_date"]) and row["now_period"] == tt._compact_period(item["sheet_period"]):
                row["status"] = "待清除異動欄" if (item["change_date"] or item["change_period"]) else "未變動"
            elif _same_date(row["now_date"], item["change_date"]) and row["now_period"] == tt._compact_period(item["change_period"]):
                row["status"] = "已填異動"
            else:
                row["status"] = "待填異動"
        except Exception as exc:
            row["status"] = f"查詢失敗：{exc}"
        rows.append(row)
    return rows


PENDING_STATUSES = ("待填異動", "待清除異動欄")


def apply_sheet_updates(settings, rows, client=None):
    """寫入異動欄：「待填異動」填入目前日期／時段，「待清除異動欄」清成空白。

    只寫異動日期／異動時段兩欄。寫入前重讀格子；和比對時讀到的值不同
    （比對後被手動改過）或該列訂單編號已變動就跳過。回傳每列結果。
    """
    settings = validate_settings(settings)
    worksheet = _open_target(settings, client)
    values = worksheet.get_all_values()
    order_idx = column_index(settings["order_col"])
    date_idx = column_index(settings["change_date_col"])
    period_idx = column_index(settings["change_period_col"])
    date_col = settings["change_date_col"].strip().upper()
    period_col = settings["change_period_col"].strip().upper()
    updates, results = [], []
    for row in rows:
        if row.get("status") not in PENDING_STATUSES:
            continue
        current = values[row["row"] - 1] if row["row"] - 1 < len(values) else []
        if _cell(current, order_idx) != row["order_no"]:
            results.append({**row, "status": "已跳過：該列訂單編號已變動"})
            continue
        if _cell(current, date_idx) != row["change_date"] or _cell(current, period_idx) != row["change_period"]:
            results.append({**row, "status": "已跳過：比對後異動欄已被修改"})
            continue
        if row["status"] == "待填異動":
            new_values, done = (row["now_date"], row["now_period"]), "已填異動"
        else:
            new_values, done = ("", ""), "已清除異動欄"
        updates.append({"range": f"{date_col}{row['row']}", "values": [[new_values[0]]]})
        updates.append({"range": f"{period_col}{row['row']}", "values": [[new_values[1]]]})
        results.append({**row, "status": done, "change_date": new_values[0], "change_period": new_values[1]})
    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    return results
