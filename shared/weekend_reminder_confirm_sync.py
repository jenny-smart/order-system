# -*- coding: utf-8 -*-
"""週末提醒回覆同步：把客人點「確認收到」連結的結果寫回追蹤表與內勤工作表單。

更新記錄：
2026-11-12（新增）
- 由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」（功能代號 weekend_reminder_confirm_sync）
  派送 .github/workflows/weekend-reminder-confirm-sync.yml；建議提醒發送日 10:00 起每小時一次。
- 範圍：「週末服務提醒」追蹤表中服務日期在今天前 2 天～後 14 天、訂單狀態已付款、回覆狀態不是「已回覆」的列。
  沒有符合的列就直接結束，不呼叫 Worker。
- 向 line-lemonsystem Worker 查詢 /api/confirmations/status。已確認的列：
  追蹤表「回覆狀態」改「已回覆」、填「回覆時間」（台北時間）、「回覆備註」加「連結確認」；
  內勤工作表單「週末提醒」分頁同一筆訂單的 I 欄（回覆狀態）空白時填「OK」，K 欄填「連結確認 MM/DD HH:MM」。
  I 欄已有內容（OK／未接／定期…）不覆蓋。
- 合併提醒只有主單有連結：備註「併入 主單號」或「時段重疊不另發：與 主單號 …」的列跟著主單記為已回覆。
- 只記錄點連結確認的客人；直接打字回覆「已收到」的仍由內勤人工填寫。不發送 LINE、不修改後台。

手動執行：
    python -m shared.weekend_reminder_confirm_sync --dry-run
"""
from __future__ import annotations

import argparse
import re
import traceback
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
DAYS_BEFORE = 2
DAYS_AFTER = 14
CONFIRM_NOTE = "連結確認"
STAFF_REPLY_COL = 9       # I 欄：回覆狀態（內勤手填）
STAFF_CONFIRM_COL = 11    # K 欄：連結確認時間
STAFF_CONFIRM_HEADER = "連結確認"
_FOLLOW_RE = re.compile(r"(?:^併入\s*|與\s*)([A-Z]{2}\d+)")


def _key(row) -> str:
    return f"{str(row.get('訂單編號', '')).strip()}|{str(row.get('服務日期', '')).strip()}"


def _in_window(row, today: date) -> bool:
    try:
        service_date = date.fromisoformat(str(row.get("服務日期", "")).strip())
    except ValueError:
        return False
    return today - timedelta(days=DAYS_BEFORE) <= service_date <= today + timedelta(days=DAYS_AFTER)


def candidate_rows(rows, today: date) -> list[dict]:
    return [
        row for row in rows
        if _in_window(row, today)
        and str(row.get("訂單狀態") or "已付款").strip() == "已付款"
        and str(row.get("回覆狀態") or "").strip() != "已回覆"
    ]


def follow_key(row, all_rows) -> str:
    """被併入／不另發的列 → 主單的 key（同一位客人最接近的服務日期）；不是這類列回傳空字串。"""
    from function.weekend_reminders import is_merged_note

    note = str(row.get("回覆備註") or "").strip()
    if not is_merged_note(note):
        return ""
    match = _FOLLOW_RE.search(note)
    if not match:
        return ""
    primary_no = match.group(1)
    same_order = [r for r in all_rows if str(r.get("訂單編號", "")).strip() == primary_no]
    if not same_order:
        return ""
    own_date = str(row.get("服務日期", ""))
    same_order.sort(key=lambda r: (str(r.get("服務日期", "")) != own_date, str(r.get("服務日期", ""))))
    return _key(same_order[0])


def taipei_text(iso_value: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    parsed = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    return parsed.astimezone(TAIPEI).strftime(fmt)


def apply_confirmations(candidates, all_rows, confirmations: dict) -> list[dict]:
    """回傳要寫回追蹤表的列（已套用已回覆／回覆時間／回覆備註）。"""
    updated = []
    for row in candidates:
        confirmed_at = confirmations.get(_key(row)) or confirmations.get(follow_key(row, all_rows))
        if not confirmed_at:
            continue
        new_row = dict(row)
        new_row["回覆狀態"] = "已回覆"
        new_row["回覆時間"] = taipei_text(confirmed_at)
        note = str(row.get("回覆備註") or "").strip()
        if CONFIRM_NOTE not in note:
            new_row["回覆備註"] = f"{note}；{CONFIRM_NOTE}" if note else CONFIRM_NOTE
        updated.append(new_row)
    return updated


def plan_staff_updates(staff_values, updated_rows) -> list[dict]:
    """內勤工作表單「週末提醒」分頁要寫的儲存格（gspread batch_update 格式）。

    staff_values：整張分頁的值（A:B 是 IMPORTRANGE 帶進來的訂單編號、服務日期）。
    用「訂單編號＋服務日期」找列，不假設列號和追蹤表相同。
    """
    from gspread.utils import rowcol_to_a1

    wanted = {_key(row): row for row in updated_rows}
    cells = []
    header = staff_values[0] if staff_values else []
    if wanted and (len(header) < STAFF_CONFIRM_COL or not str(header[STAFF_CONFIRM_COL - 1]).strip()):
        cells.append({"range": rowcol_to_a1(1, STAFF_CONFIRM_COL), "values": [[STAFF_CONFIRM_HEADER]]})
    for index, values in enumerate(staff_values[1:], start=2):
        values = list(values) + [""] * (STAFF_CONFIRM_COL - len(values))
        row = wanted.get(f"{str(values[0]).strip()}|{str(values[1]).strip()}")
        if not row:
            continue
        if not str(values[STAFF_REPLY_COL - 1]).strip():
            cells.append({"range": rowcol_to_a1(index, STAFF_REPLY_COL), "values": [["OK"]]})
        stamp = f"{CONFIRM_NOTE} {datetime.strptime(row['回覆時間'], '%Y-%m-%d %H:%M').strftime('%m/%d %H:%M')}"
        if str(values[STAFF_CONFIRM_COL - 1]).strip() != stamp:
            cells.append({"range": rowcol_to_a1(index, STAFF_CONFIRM_COL), "values": [[stamp]]})
    return cells


def write_staff_sheet(updated_rows) -> int:
    import orders
    from function.weekend_reminders import STAFF_SHEET_AREA, STAFF_SHEET_CATEGORY, STAFF_SHEET_TITLE
    from year_roots import root_file_id

    client = orders.build_gsheet_client()
    worksheet = client.open_by_key(root_file_id(STAFF_SHEET_CATEGORY, STAFF_SHEET_AREA)).worksheet(STAFF_SHEET_TITLE)
    cells = plan_staff_updates(worksheet.get_all_values(), updated_rows)
    if cells:
        if worksheet.col_count < STAFF_CONFIRM_COL:
            worksheet.resize(cols=STAFF_CONFIRM_COL)
        worksheet.batch_update(cells, value_input_option="RAW")
    return len(cells)


def _log(status, date_text, message, traceback_text=""):
    try:
        from shared.execution_log_service import log_execution

        log_execution(
            function_name="週末服務提醒：連結確認同步", status=status, run_type="排程",
            area="台北", date=date_text, message=message, traceback_text=traceback_text,
        )
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def run(today: date | None = None, dry_run: bool = False) -> dict:
    from function.weekend_reminders import load_tracking_rows, save_tracking_rows
    from shared.reminder_confirm import fetch_confirmations

    today = today or datetime.now(TAIPEI).date()
    all_rows = load_tracking_rows()
    candidates = candidate_rows(all_rows, today)
    if not candidates:
        print(f"SKIP {today} 沒有待確認的提醒", flush=True)
        return {"candidates": 0, "confirmed": 0}

    keys = {_key(row) for row in candidates} | {follow_key(row, all_rows) for row in candidates}
    confirmations = fetch_confirmations(keys - {""})
    updated = apply_confirmations(candidates, all_rows, confirmations)
    staff_cells, staff_error = 0, ""
    if updated and not dry_run:
        save_tracking_rows(updated)
        try:
            staff_cells = write_staff_sheet(updated)
        except Exception as exc:  # 追蹤表已寫入；內勤分頁失敗只警告
            staff_error = f"內勤工作表單寫入失敗：{type(exc).__name__}: {exc}"
            print(f"WARN {staff_error}", flush=True)
    # 紀錄只印筆數，不印客戶姓名、電話
    message = (
        f"待確認 {len(candidates)} 筆，本次連結確認 {len(updated)} 筆"
        + ("（試跑，未寫入）" if dry_run else f"，內勤分頁寫入 {staff_cells} 格")
        + (f"；{staff_error}" if staff_error else "")
    )
    print(f"FINISH {message}", flush=True)
    if updated and not dry_run:
        _log("警告" if staff_error else "成功", str(today), message)
    return {"candidates": len(candidates), "confirmed": len(updated), "staff_cells": staff_cells}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default="", help="以這天當作今天（YYYY-MM-DD，測試用）")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫入")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    try:
        run(today=today, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", args.date or str(datetime.now(TAIPEI).date()), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
