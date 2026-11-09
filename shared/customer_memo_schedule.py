# -*- coding: utf-8 -*-
"""客人備註非空白（雲端排程，上班日 10:00）。

由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」（功能代號 customer_memo_daily）
派送 .github/workflows/customer-memo-schedule.yml。

規則：
- 只在上班日執行（config/taiwan_work_calendar.json；週六日＋國定假日不跑，補班日照跑）。
- 查詢區間＝前一上班日 10:00 ～ 今天 10:00（依訂購時間；週一會涵蓋週五 10:00 起整個週末）。
- 台北／台中各用自己的後台帳號查：全部付款狀態、排除代客預訂、客人備註非空白
  （function/customer_memo_query.search_customer_memo_orders，與「客人備註查詢」頁面相同）。
- 貼到該區「內勤工作表單」的「客人備註」分頁最下方：
  訂單編號／客人姓名／客人電話／服務日期／客人備註／客服備註；
  客人電話是 HYPERLINK，點了開後台訂單管理用電話搜尋的結果頁。
  訂單編號已在分頁上的不重複貼；沒有「客人備註」分頁時自動建立並寫標題列。
- 貼完在 jenny@hers.com.tw 行事曆記一則「【客人備註】台北 N 筆、台中 M 筆」（寫不進去改寫
  jenny@lemonclean.com.tw；可用 CUSTOMER_MEMO_CALENDAR_ID 指定），內容列出逐筆訂單與工作表連結。

Actions 紀錄只印各區筆數，不印客戶姓名、電話；逐筆明細寫進工作表與行事曆。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import traceback
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

TOOL_NAME = "客人備註非空白：自動排程"
TZ = ZoneInfo("Asia/Taipei")
RUN_AT = time(10, 0)
REGIONS = ("台北", "台中")
SHEET_CATEGORY = "內勤工作表單"
TAB_TITLE = "客人備註"
HEADER = ["訂單編號", "客人姓名", "客人電話", "服務日期", "客人備註", "客服備註"]
CALENDAR_IDS = ("jenny@hers.com.tw", "jenny@lemonclean.com.tw")
CALENDAR_PREFIX = "【客人備註】"


# ------------------------------------------------------------
# 時間區間
# ------------------------------------------------------------
def previous_workday(day: date, calendar: dict) -> date:
    from shared.weekend_reminder_schedule import is_off_day

    prev = day - timedelta(days=1)
    while is_off_day(prev, calendar):
        prev -= timedelta(days=1)
    return prev


def query_window(today: date, calendar: dict) -> tuple[datetime, datetime]:
    """前一上班日 10:00 ～ 今天 10:00（naive，台北時間）。"""
    start_day = previous_workday(today, calendar)
    return datetime.combine(start_day, RUN_AT), datetime.combine(today, RUN_AT)


# ------------------------------------------------------------
# 工作表
# ------------------------------------------------------------
def phone_search_url(base_url: str, phone: str) -> str:
    """後台訂單管理用電話搜尋的結果頁（參數與後台搜尋列相同，只帶 phone）。"""
    from memo_system import memo

    params = memo.blank_list_params()
    params["phone"] = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return f"{base_url.rstrip('/')}/purchase?{urlencode(params)}"


def _formula_text(value: str) -> str:
    return str(value or "").replace('"', '""')


def build_sheet_rows(rows: list[dict], base_url: str) -> list[list[str]]:
    out = []
    for r in rows:
        phone = str(r.get("電話", "") or "")
        phone_cell = (f'=HYPERLINK("{_formula_text(phone_search_url(base_url, phone))}","{_formula_text(phone)}")'
                      if phone else "")
        out.append([
            str(r.get("訂單號碼", "") or ""),
            str(r.get("客人姓名", "") or ""),
            phone_cell,
            str(r.get("服務日期", "") or ""),
            str(r.get("客人備註", "") or ""),
            str(r.get("客服備註", "") or ""),
        ])
    return out


def last_data_row(col_a: list[str]) -> int:
    """A 欄最後一個有值的列號（去掉尾端空白，不用 get_all_values 長度）。"""
    n = len(col_a)
    while n > 0 and not str(col_a[n - 1]).strip():
        n -= 1
    return n


def get_tab(region: str):
    """該區當年度「內勤工作表單」的「客人備註」分頁；沒有就建立並寫標題列。"""
    from memo_system.memo import with_retry
    from shared.gsheet import build_gsheet_client
    from year_roots import root_file_id

    spreadsheet = build_gsheet_client().open_by_key(root_file_id(SHEET_CATEGORY, region))
    for ws in with_retry(spreadsheet.worksheets):
        if ws.title == TAB_TITLE:
            return spreadsheet, ws
    ws = with_retry(spreadsheet.add_worksheet, title=TAB_TITLE, rows=1000, cols=len(HEADER))
    with_retry(ws.update, values=[HEADER], range_name="A1:F1")
    return spreadsheet, ws


def append_rows(ws, sheet_rows: list[list[str]]) -> int:
    """貼到最下方；訂單編號已在 A 欄的不重複貼。回傳實際貼入筆數。"""
    from memo_system.memo import with_retry

    col_a = with_retry(ws.col_values, 1)
    existing = {str(v).strip() for v in col_a if str(v).strip()}
    new_rows = [r for r in sheet_rows if r[0] and r[0] not in existing]
    if not new_rows:
        return 0
    start = max(last_data_row(col_a), 1) + 1
    end = start + len(new_rows) - 1
    if end > ws.row_count:
        with_retry(ws.add_rows, end - ws.row_count + 100)
    with_retry(ws.update, values=new_rows, range_name=f"A{start}:F{end}", value_input_option="USER_ENTERED")
    return len(new_rows)


# ------------------------------------------------------------
# 行事曆
# ------------------------------------------------------------
def build_calendar_event(result: dict, window: tuple[datetime, datetime], now: datetime) -> dict:
    counts = "、".join(f"{region} {item.get('saved', 0)} 筆" for region, item in result.items())
    lines = [f"區間：{window[0]:%m/%d %H:%M} ～ {window[1]:%m/%d %H:%M}（訂購時間）", ""]
    for region, item in result.items():
        lines.append(f"■ {region}：貼入 {item.get('saved', 0)} 筆" + (f"（{item['error']}）" if item.get("error") else ""))
        if item.get("sheet_url"):
            lines.append(item["sheet_url"])
        for r in item.get("rows") or []:
            memo_text = str(r.get("客人備註", "")).replace("\n", " ")
            lines.append(f"{r.get('訂單號碼', '')} {r.get('客人姓名', '')} {r.get('服務日期', '')}：{memo_text[:60]}")
        lines.append("")
    return dict(
        summary=f"{CALENDAR_PREFIX}{counts}（{now:%m/%d}）",
        description="\n".join(lines).strip(),
        start=now, reminder_minutes=[0], replace_prefix=CALENDAR_PREFIX,
    )


def write_calendar(result: dict, window, now: datetime, service_factory=None) -> list[str]:
    """寫行事曆；失敗只回報，不影響貼表結果。"""
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event

    service_factory = service_factory or _calendar_service
    preferred = os.getenv("CUSTOMER_MEMO_CALENDAR_ID", "").strip()
    calendar_ids = (preferred,) if preferred else CALENDAR_IDS
    try:
        service = service_factory()
    except Exception as exc:
        return [f"⚠️ 無法連線行事曆：{exc}"]
    event = build_calendar_event(result, window, now)
    last_error = None
    for calendar_id in calendar_ids:
        try:
            _insert_event(service, calendar_id, **event)
            return [f"已記入行事曆 {calendar_id}"]
        except Exception as exc:
            last_error = exc
    return [f"⚠️ 記入行事曆失敗：{last_error}"]


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def _log(status: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area="台北／台中",
                      message=message, traceback_text=traceback_text)
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def run(env: str = "prod", today: date | None = None, regions=REGIONS, dry_run: bool = False,
        calendar: dict | None = None, now: datetime | None = None) -> dict:
    from accounts import ACCOUNTS
    from function.customer_memo_query import search_customer_memo_orders
    from memo_system import memo
    from shared.weekend_reminder_schedule import is_off_day, load_work_calendar

    calendar = load_work_calendar() if calendar is None else calendar
    now = now or datetime.now(TZ)
    today = today or now.date()
    if is_off_day(today, calendar):
        print(f"SKIP {today} 不是上班日", flush=True)
        return {"due": False, "today": str(today)}

    window = query_window(today, calendar)
    print(f"WINDOW {window[0]:%Y-%m-%d %H:%M} ～ {window[1]:%Y-%m-%d %H:%M}", flush=True)
    memo.set_env(env)

    result: dict = {}
    for region in regions:
        item = {"rows": [], "saved": 0, "sheet_url": "", "error": ""}
        result[region] = item
        try:
            account = ACCOUNTS.get(region) or {}
            email, password = str(account.get("email") or ""), str(account.get("password") or "")
            if not email or not password:
                raise RuntimeError(f"{region}未設定後台帳密（{region} EMAIL／PASSWORD Secrets）")
            memo.set_runtime_credentials(email, password)
            with contextlib.redirect_stdout(io.StringIO()):  # 明細不印進 Actions 紀錄
                session = memo.login()
                rows = search_customer_memo_orders(
                    window[0].strftime("%Y/%m/%d"), window[1].strftime("%Y/%m/%d"),
                    session=session, created_from=window[0], created_to=window[1],
                )
            item["rows"] = rows
            print(f"QUERY {region} 客人備註非空白 {len(rows)} 筆", flush=True)
            if dry_run:
                continue
            spreadsheet, ws = get_tab(region)
            item["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}"
            item["saved"] = append_rows(ws, build_sheet_rows(rows, memo.BASE_URL))
            print(f"SAVE {region} 貼入 {item['saved']} 筆（重複略過 {len(rows) - item['saved']} 筆）", flush=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)

    messages = [] if dry_run else write_calendar(result, window, now)
    for line in messages:
        print(line, flush=True)

    errors = [f"{r}：{i['error']}" for r, i in result.items() if i["error"]]
    summary = "；".join(f"{r} 查到 {len(i['rows'])} 筆、貼入 {i['saved']} 筆" for r, i in result.items())
    message = f"{window[0]:%m/%d %H:%M}～{window[1]:%m/%d %H:%M}：{summary}" + ("（試跑，未寫入）" if dry_run else "")
    if errors:
        message += "；錯誤 " + "；".join(errors)
    print(f"FINISH {message}", flush=True)
    if not dry_run:
        _log("失敗" if errors else "成功", message)
    if errors and len(errors) == len(result):
        raise RuntimeError("；".join(errors))
    return {"due": True, "window": window, "result": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default="台北,台中", help="逗號分隔，預設台北,台中")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫入工作表、不寫行事曆")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
