# -*- coding: utf-8 -*-
"""客人備註非空白（雲端排程，上班日 08:40，區間截到 08:30）。

更新記錄：
2026-11-11
- 欄位改成內勤工作表單上 Jenny 訂的標題，兩個分頁 A 欄都是「備註日期時間」（排程寫入時間）：
  客人備註：備註日期時間／訂單編號／訂購人／電話號碼／預約日期／客人備註／客服備註
  客服備註：備註日期時間／標記／訂單編號／訂購人／電話號碼／地址／服務日期／付款狀態／
            異動單號／異動項目／異動時數／異動客服備註／異動註記
  標記＝異動類別（⚠️ 付款／項目／時間／N→O），沒有異動時寫分類（①②③）。
  分頁已存在但第 1 列空白時補寫標題列。
- 修正行事曆 404：服務帳號沒有 jenny@hers.com.tw 行事曆的寫入權，改優先用 Jenny 本人授權
  （GOOGLE_HERS_CALENDAR_REFRESH_TOKEN＋GOOGLE_OAUTH_CLIENT_ID／SECRET，與 tool-system 相同）。
- 「客服備註」分頁改寫「訂單客服備註」頁面的①②③三區結果（同一套查詢：購買日期＝前一上班日～
  今天、付款狀態全部，再依訂購時間篩前一上班日 08:30～今天 08:30）：
  異動（最前方）／分類／訂單編號／客戶／客人電話（搜尋連結）／地址／服務日期／付款狀態／狀態／
  參照訂單／服務項目（前次→本次）／服務時間（前次→本次）／客服備註（將寫入）。
  只寫工作表，不改後台客服備註（寫入仍在訂單客服備註頁面勾選執行）。
- 修正 ImportError（circular import）：shared.gsheet 匯入時會 import orders，而 orders 又
  從 shared.gsheet 匯入；排程直接先載入 shared.gsheet 就會失敗（貼表、行事曆、執行 Log 全部
  寫不進去）。改成開始前先 import orders（_preload_modules），與 Streamlit 端的載入順序相同。


由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」（功能代號 customer_memo_daily）
派送 .github/workflows/customer-memo-schedule.yml。

規則：
- 只在上班日執行（config/taiwan_work_calendar.json；週六日＋國定假日不跑，補班日照跑）。
- 查詢區間＝前一上班日 08:30 ～ 今天 08:30（依訂購時間；週一會涵蓋週五 08:30 起整個週末；截止時間＝RUN_AT）。
- 台北／台中各用自己的後台帳號查：全部付款狀態、排除代客預訂、客人備註非空白
  （function/customer_memo_query.search_customer_memo_orders，與「客人備註查詢」頁面相同）。
- 貼到該區「內勤工作表單」的「客人備註」分頁最下方：
  訂單編號／客人姓名／客人電話／服務日期／客人備註／客服備註；
  客人電話是 HYPERLINK，點了開後台訂單管理用電話搜尋的結果頁。
  訂單編號已在分頁上的不重複貼；沒有「客人備註」分頁時自動建立並寫標題列。
- 另外跑「訂單客服備註」的①②③查詢（①有相同訂單／②無相同訂單／③已處理但 VIP 非儲值金或 **N-
  已非首次）→ 貼到同一個內勤工作表單的「客服備註」分頁，欄位與頁面列表相同，異動欄最前方。
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
RUN_AT = time(8, 30)  # 2026-11-12 起：主控表「排程設定」customer_memo_daily 排 08:40，區間截到 08:30
REGIONS = ("台北", "台中")
SHEET_CATEGORY = "內勤工作表單"
TAB_TITLE = "客人備註"
HEADER = ["備註日期時間", "訂單編號", "訂購人", "電話號碼", "預約日期", "客人備註", "客服備註"]
KEY_COL = 2  # 「客人備註」分頁的訂單編號在 B 欄
NOTICE_TAB_TITLE = "客服備註"
NOTICE_HEADER = ["備註日期時間", "標記", "訂單編號", "訂購人", "電話號碼", "地址", "服務日期", "付款狀態",
                 "異動單號", "異動項目", "異動時數", "異動客服備註", "異動註記"]
NOTICE_KEY_COL = 3  # 「客服備註」分頁的訂單編號在 C 欄
CALENDAR_IDS = ("jenny@hers.com.tw", "jenny@lemonclean.com.tw")
CALENDAR_PREFIX = "【客人備註】"


def _preload_modules() -> None:
    """先載入 orders，再用 shared.gsheet（shared.gsheet ↔ orders 互相 import，順序反了會失敗）。"""
    import orders  # noqa: F401
    import shared.gsheet  # noqa: F401


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
    """前一上班日 RUN_AT ～ 今天 RUN_AT（目前 08:30，naive，台北時間）。"""
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


def phone_cell(base_url: str, phone: str) -> str:
    phone = str(phone or "")
    return (f'=HYPERLINK("{_formula_text(phone_search_url(base_url, phone))}","{_formula_text(phone)}")'
            if phone else "")


def stamp_text(now: datetime | None = None) -> str:
    """A 欄「備註日期時間」：排程寫入的台北時間。"""
    return (now or datetime.now(TZ)).astimezone(TZ).strftime("%Y/%m/%d %H:%M")


def build_sheet_rows(rows: list[dict], base_url: str, stamp: str = "") -> list[list[str]]:
    """「客人備註」分頁的列。"""
    return [[
        stamp,
        str(r.get("訂單號碼", "") or ""),
        str(r.get("客人姓名", "") or ""),
        phone_cell(base_url, r.get("電話", "")),
        str(r.get("服務日期", "") or ""),
        str(r.get("客人備註", "") or ""),
        str(r.get("客服備註", "") or ""),
    ] for r in rows]


def build_notice_sheet_rows(rows: list[dict], base_url: str, stamp: str = "") -> list[list[str]]:
    """「客服備註」分頁的列：訂單客服備註①②③預覽列（欄位同工作表標題）。"""
    from memo_system import memo

    out = []
    for r in rows:
        ref_no = r.get("source_order_id") or r.get("latest_same_order_id", "")
        ref_dt = r.get("source_service_date") or r.get("latest_same_order_date", "")
        has_ref = bool(ref_no) or r.get("section") == "processed"
        out.append([
            stamp,
            memo.preview_change_kinds(r) or memo.preview_section_label(r),          # 標記
            str(r.get("order_id", "") or ""),                                        # 訂單編號
            str(r.get("customer_name", "") or ""),                                   # 訂購人
            phone_cell(base_url, r.get("phone", "")),                                # 電話號碼
            str(r.get("address", "") or ""),                                         # 地址
            str(r.get("service_date", "") or ""),                                    # 服務日期
            str(r.get("purchase_status_name", "") or ""),                            # 付款狀態
            f"{ref_no} {ref_dt}".strip(),                                            # 異動單號
            (f"{r.get('source_service_items_text', '') or '-'} → {r.get('service_items_text', '') or '-'}" if has_ref else ""),
            (f"{r.get('source_service_time_text', '') or '-'} → {r.get('service_time_text', '') or '-'}" if has_ref else ""),
            memo.preview_status_text(r),                                             # 異動客服備註
            str(r.get("source_notice_preview", "") or ""),                           # 異動註記
        ])
    return out


def section_rows_in_window(rows: list[dict], window: tuple[datetime, datetime]) -> list[dict]:
    """訂單客服備註預覽列中，訂購時間在 [window) 內的（沒有訂購時間的是代客預訂，略過）。"""
    out = []
    for r in rows:
        text = str(r.get("created_at", "") or "")
        try:
            created = datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if window[0] <= created < window[1]:
            out.append(r)
    order = {"③": 0, "①": 1, "②": 2}
    from memo_system import memo
    out.sort(key=lambda r: (0 if r.get("service_change") else 1,
                            order.get(memo.preview_section_label(r)[:1], 9), str(r.get("order_id", ""))))
    return out


def last_data_row(col_a: list[str]) -> int:
    """A 欄最後一個有值的列號（去掉尾端空白，不用 get_all_values 長度）。"""
    n = len(col_a)
    while n > 0 and not str(col_a[n - 1]).strip():
        n -= 1
    return n


def _col_letter(n: int) -> str:
    return chr(ord("A") + n - 1)


def open_spreadsheet(region: str):
    from shared.gsheet import build_gsheet_client
    from year_roots import root_file_id

    return build_gsheet_client().open_by_key(root_file_id(SHEET_CATEGORY, region))


def get_tab(region: str, title: str = TAB_TITLE, header: list[str] = HEADER, spreadsheet=None):
    """該區當年度「內勤工作表單」的指定分頁；沒有就建立並寫標題列。"""
    from memo_system.memo import with_retry

    spreadsheet = spreadsheet or open_spreadsheet(region)
    for ws in with_retry(spreadsheet.worksheets):
        if ws.title == title:
            first = with_retry(ws.row_values, 1)
            if not any(str(v).strip() for v in first):  # 分頁在但沒有標題列 → 補寫
                with_retry(ws.update, values=[header], range_name=f"A1:{_col_letter(len(header))}1")
            return spreadsheet, ws
    ws = with_retry(spreadsheet.add_worksheet, title=title, rows=1000, cols=len(header))
    with_retry(ws.update, values=[header], range_name=f"A1:{_col_letter(len(header))}1")
    return spreadsheet, ws


def append_rows(ws, sheet_rows: list[list[str]], width: int = len(HEADER), key_col: int = 1) -> int:
    """貼到最下方；訂單編號（key_col 欄）已在分頁上的不重複貼。回傳實際貼入筆數。"""
    from memo_system.memo import with_retry

    keys = with_retry(ws.col_values, key_col)
    existing = {str(v).strip() for v in keys if str(v).strip()}
    idx = key_col - 1
    new_rows = [r for r in sheet_rows if r[idx] and r[idx] not in existing]
    if not new_rows:
        return 0
    col_a = keys if key_col == 1 else with_retry(ws.col_values, 1)
    start = max(last_data_row(col_a), last_data_row(keys), 1) + 1
    end = start + len(new_rows) - 1
    if end > ws.row_count:
        with_retry(ws.add_rows, end - ws.row_count + 100)
    with_retry(ws.update, values=new_rows, range_name=f"A{start}:{_col_letter(width)}{end}", value_input_option="USER_ENTERED")
    return len(new_rows)


# ------------------------------------------------------------
# 行事曆
# ------------------------------------------------------------
def build_calendar_event(result: dict, window: tuple[datetime, datetime], now: datetime) -> dict:
    counts = "、".join(f"{region} {item.get('saved', 0)} 筆" for region, item in result.items())
    notice_total = sum(int(item.get("notice_saved", 0) or 0) for item in result.values())
    flagged = sum(1 for item in result.values() for r in item.get("notice_rows") or [] if r.get("service_change"))
    if notice_total:
        counts += f"；客服備註 {notice_total} 筆" + (f"（異動 {flagged}）" if flagged else "")
    lines = [f"區間：{window[0]:%m/%d %H:%M} ～ {window[1]:%m/%d %H:%M}（訂購時間）", ""]
    for region, item in result.items():
        lines.append(f"■ {region}：貼入 {item.get('saved', 0)} 筆" + (f"（{item['error']}）" if item.get("error") else ""))
        if item.get("sheet_url"):
            lines.append(item["sheet_url"])
        for r in item.get("rows") or []:
            memo_text = str(r.get("客人備註", "")).replace("\n", " ")
            lines.append(f"{r.get('訂單號碼', '')} {r.get('客人姓名', '')} {r.get('服務日期', '')}：{memo_text[:60]}")
        if item.get("notice_rows"):
            from memo_system import memo
            lines.append(f"□ 客服備註①②③：貼入 {item.get('notice_saved', 0)} 筆")
            if item.get("notice_sheet_url"):
                lines.append(item["notice_sheet_url"])
            flagged_rows = [r for r in item["notice_rows"] if r.get("service_change")]
            others = len(item["notice_rows"]) - len(flagged_rows)
            if others:
                lines.append(f"（無異動 {others} 筆請看工作表）")
            for r in flagged_rows:
                kinds = memo.preview_change_kinds(r)
                lines.append(f"{memo.preview_section_label(r)[:1]} {r.get('order_id', '')} {r.get('customer_name', '')}"
                             f"：{memo.preview_status_text(r)}" + (f"　{kinds}" if kinds else ""))
        lines.append("")
    return dict(
        summary=f"{CALENDAR_PREFIX}{counts}（{now:%m/%d}）",
        description="\n".join(lines).strip(),
        start=now, reminder_minutes=[0], replace_prefix=CALENDAR_PREFIX,
    )


def write_calendar(result: dict, window, now: datetime, service_factory=None) -> list[str]:
    """寫行事曆；失敗只回報，不影響貼表結果。"""
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event, service_for

    service_factory = service_factory or _calendar_service
    preferred = os.getenv("CUSTOMER_MEMO_CALENDAR_ID", "").strip()
    calendar_ids = (preferred,) if preferred else CALENDAR_IDS
    event = build_calendar_event(result, window, now)
    last_error = None
    for calendar_id in calendar_ids:
        try:
            _insert_event(service_for(service_factory, calendar_id), calendar_id, **event)
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
    _preload_modules()
    from accounts import ACCOUNTS
    from function.customer_memo_query import customer_memo_rows, fetch_window_orders
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
        item = {"rows": [], "saved": 0, "sheet_url": "", "error": "",
                "notice_rows": [], "notice_saved": 0, "notice_sheet_url": ""}
        result[region] = item
        try:
            account = ACCOUNTS.get(region) or {}
            email, password = str(account.get("email") or ""), str(account.get("password") or "")
            if not email or not password:
                raise RuntimeError(f"{region}未設定後台帳密（{region} EMAIL／PASSWORD Secrets）")
            memo.set_runtime_credentials(email, password)
            with contextlib.redirect_stdout(io.StringIO()):  # 明細不印進 Actions 紀錄
                session = memo.login()
                candidates = fetch_window_orders(
                    window[0].strftime("%Y/%m/%d"), window[1].strftime("%Y/%m/%d"), lambda m: None,
                    session, created_from=window[0], created_to=window[1],
                )
                rows = customer_memo_rows(candidates)
                preview = memo.preview_by_conditions(
                    "購買日期", window[0].strftime("%Y/%m/%d"), window[1].strftime("%Y/%m/%d"), "全部",
                    session=session,
                )
                notice_rows = section_rows_in_window(preview, window)
            item["rows"], item["notice_rows"] = rows, notice_rows
            print(f"QUERY {region} 客人備註非空白 {len(rows)} 筆、客服備註①②③ {len(notice_rows)} 筆"
                  f"（有異動 {sum(1 for r in notice_rows if r.get('service_change'))} 筆）", flush=True)
            if dry_run:
                continue
            spreadsheet, ws = get_tab(region)
            item["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}"
            stamp = stamp_text(now)
            item["saved"] = append_rows(ws, build_sheet_rows(rows, memo.BASE_URL, stamp), key_col=KEY_COL)
            print(f"SAVE {region} 客人備註貼入 {item['saved']} 筆（重複略過 {len(rows) - item['saved']} 筆）", flush=True)
            if notice_rows:
                _, nws = get_tab(region, NOTICE_TAB_TITLE, NOTICE_HEADER, spreadsheet=spreadsheet)
                item["notice_sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={nws.id}"
                item["notice_saved"] = append_rows(nws, build_notice_sheet_rows(notice_rows, memo.BASE_URL, stamp),
                                                   width=len(NOTICE_HEADER), key_col=NOTICE_KEY_COL)
                print(f"SAVE {region} 客服備註貼入 {item['notice_saved']} 筆", flush=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)

    messages = [] if dry_run else write_calendar(result, window, now)
    for line in messages:
        print(line, flush=True)

    errors = [f"{r}：{i['error']}" for r, i in result.items() if i["error"]]
    summary = "；".join(f"{r} 客人備註 {len(i['rows'])} 筆貼入 {i['saved']} 筆、客服備註①②③ {len(i['notice_rows'])} 筆貼入 {i['notice_saved']} 筆"
                        for r, i in result.items())
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
    _preload_modules()
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
