# -*- coding: utf-8 -*-
"""官網評價自動登記（雲端排程，上班日）＋整理電話／姓名連結。

更新記錄：
2026-11-11（新增）
- complaint（上班日 07:00）：評價管理（/rating）中「服務滿意度」為不滿意或尚可的評價；
  滿意但評價項目有非正面（例：準時到達：無）或備註有負面字詞（NEGATIVE_KEYWORDS）也登記，客訴內容最前面註明交客服判斷；
  插入該區當年度「內勤工作表單」的「清潔客訴」分頁（最後一筆客訴之後插列，下方下拉選單清單會往下移）。
- booking（上班日 07:20）：有勾選「預約下次服務」的評價，插入「評價預約」分頁主名單之後
  （插列，主名單下方的空白列與手寫區塊整段往下移，不會被覆蓋）。
- relink（手動）：整理「清潔客訴」「評價預約」既有列的電話與姓名連結。
- 獨立功能「整理姓名／電話連結」（function/sheet_link_tool.py）：任一工作表指定姓名／電話欄套用同樣連結。
- 電話一律放後台訂單管理電話查詢連結；姓名一律加上 LINE 聊天連結（查不到 LINE 就維持文字）。
- 兩個排程的區間都是「前一上班日 07:00 ～ 今天 07:00」（依評價時間），已登記過的不重複貼。
- 貼完記 jenny@hers.com.tw 行事曆（寫不進去改 jenny@lemonclean.com.tw；可用 RATING_CALENDAR_ID 指定）。

由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」派送 .github/workflows/rating-schedule.yml：
  rating_complaint_daily → job=complaint、rating_booking_daily → job=booking。

Actions 紀錄只印筆數，不印客戶姓名、電話；逐筆明細寫進工作表與行事曆。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import traceback
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
CUTOFF = time(7, 0)
REGIONS = ("台北", "台中")
SHEET_CATEGORY = "內勤工作表單"
CALENDAR_IDS = ("jenny@hers.com.tw", "jenny@lemonclean.com.tw")
WEEKDAY_ZH = "一二三四五六日"

# ------------------------------------------------------------
# 清潔客訴分頁（台北／台中相同）：第 1 列分工、第 2 列標題、第 3 列起資料
# A客訴來源 B客訴類型 C服務日期 D月份 E客訴日期 F星期 G客戶 H電話 I客戶分類 J客訴內容 K連絡日期 L客戶溝通內容 M服務專員
# ------------------------------------------------------------
COMPLAINT_TAB = "清潔客訴"
COMPLAINT_FIRST_ROW = 3
COMPLAINT_WIDTH = 13  # A～M
COMPLAINT_NAME_COL, COMPLAINT_PHONE_COL = 7, 8  # G、H
COMPLAINT_SOURCE = "官網評價"
COMPLAINT_SATISFACTION = {"尚可", "不滿意"}
OK_ITEM_VALUES = {"有", "是", "良好", "滿意", "非常滿意", "準時", "好", "很好", "非常好"}
# 服務滿意度「滿意」但備註有這些字，也登記清潔客訴（客訴內容最前面註明，交客服判斷）
NEGATIVE_KEYWORDS = (
    "不乾淨", "沒乾淨", "沒擦", "沒有擦", "沒清", "沒有清", "沒洗", "漏掉", "遺漏", "漏了", "沒做", "沒有做", "未完成",
    "髒", "汙漬", "污漬", "水垢", "灰塵", "頭髮", "毛髮", "痕跡", "刮傷", "刮痕", "損壞", "弄壞", "打破", "破損", "不見",
    "遲到", "太慢", "超時", "提早離開", "態度不", "不禮貌", "不專業", "敷衍", "馬虎", "粗心", "隨便",
    "失望", "不滿", "可惜", "抱怨", "不舒服", "加強", "改進", "改善", "再注意", "希望下次", "不夠",
)
SKIP_ITEMS = {"服務滿意度", "從何得知我們的服務", "預約下一次服務時間"}

# ------------------------------------------------------------
# 評價預約分頁：台北依標題列 B～K；台中沿用原本 A 姓名／B 地址／C 預約／D 訂單（留空）的格式，其餘放 E 起
# ------------------------------------------------------------
BOOKING_TAB = "評價預約"
BOOKING_LAYOUTS = {
    "台北": dict(width=11, key_col=10, name_col=3, phone_col=4, line_col=11, first_row=2),
    "台中": dict(width=10, key_col=9, name_col=1, phone_col=5, line_col=10, first_row=1),
}
MAIN_LIST_GAP = 3  # 連續這麼多列 A～K 全空白＝主名單結束

CALENDAR_PREFIX = {"complaint": "【評價客訴】", "booking": "【評價預約】"}
TOOL_NAME = {"complaint": "官網評價尚可／不滿意／有負面意見→清潔客訴：自動排程", "booking": "官網評價預約下次→評價預約：自動排程",
             "relink": "清潔客訴／評價預約：整理電話與姓名連結"}


def _preload_modules() -> None:
    """先載入 orders，再用 shared.gsheet（shared.gsheet ↔ orders 互相 import，順序反了會失敗）。"""
    import orders  # noqa: F401
    import shared.gsheet  # noqa: F401


# ------------------------------------------------------------
# 時間區間
# ------------------------------------------------------------
def query_window(today: date, calendar: dict) -> tuple[datetime, datetime]:
    """前一上班日 07:00 ～ 今天 07:00（naive，台北時間）。"""
    from shared.customer_memo_schedule import previous_workday

    return datetime.combine(previous_workday(today, calendar), CUTOFF), datetime.combine(today, CUTOFF)


def parse_rating_time(text: str) -> datetime | None:
    try:
        return datetime.strptime(str(text or "").strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(text or "").strip()[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return None


def in_window(text: str, window) -> bool:
    when = parse_rating_time(text)
    return bool(when) and window[0] <= when < window[1]


# ------------------------------------------------------------
# 連結
# ------------------------------------------------------------
def _formula_text(value) -> str:
    return str(value or "").replace('"', '""')


def normalize_phone(phone) -> str:
    """只留數字；工作表把 0 去掉存成 9 碼數字（921109595）時補回 0。"""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) == 9 and digits.startswith("9"):
        digits = "0" + digits
    return digits


def phone_cell(base_url: str, phone) -> str:
    """電話：後台訂單管理電話查詢連結。"""
    from shared.customer_memo_schedule import phone_cell as _phone_cell

    return _phone_cell(base_url, normalize_phone(phone))


def name_cell(name, line_url: str = "") -> str:
    """姓名：有 LINE 網址就加 LINE 聊天連結，沒有維持文字。"""
    name = str(name or "")
    if not name or not line_url:
        return name
    return f'=HYPERLINK("{_formula_text(line_url)}","{_formula_text(name)}")'


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ------------------------------------------------------------
# 後台：評價管理
# ------------------------------------------------------------
def parse_rating_content(cell) -> dict:
    """評價內容儲存格 → {"items": {項目: 值}, "note": 備註, "text": 全文}。"""
    items = {}
    for li in cell.find_all("li"):
        text = li.get_text(" ", strip=True)
        m = re.match(r"^([^：:]+)[：:]\s*(.*)$", text)
        if m:
            items[m.group(1).strip()] = m.group(2).strip()
    full = cell.get_text("\n", strip=True)
    note = ""
    m = re.search(r"備註[：:]\s*(.*)", full, re.S)
    if m:
        note = m.group(1).strip()
    if not items:  # 沒有 <li> 時退回逐行解析
        for line in full.split("\n"):
            m = re.match(r"^([^：:]+)[：:]\s*(.*)$", line.strip())
            if m and m.group(1).strip() != "備註":
                items.setdefault(m.group(1).strip(), m.group(2).strip())
    return {"items": items, "note": note, "text": full}


def fetch_ratings(session, base_url: str, date_s: str, date_e: str, max_pages: int = 60) -> list[dict]:
    """/rating 評價日期區間內所有評價（date_e 多送一天：後台迄日只比到當天 00:00）。"""
    from bs4 import BeautifulSoup
    import quick_order as qo

    query_e = (date.fromisoformat(date_e) + timedelta(days=1)).isoformat()
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        resp = session.get(f"{base_url}/rating", params={"date_s": date_s, "date_e": query_e, "page": page},
                           headers=qo.HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f"評價管理查詢失敗：HTTP {resp.status_code}")
        table = BeautifulSoup(resp.text, "html.parser").find("table")
        trs = table.find("tbody").find_all("tr") if table and table.find("tbody") else []
        if not trs:
            break
        for tr in trs:
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            name_a = cells[0].find("a", href=re.compile(r"/member\?keyword="))
            order_a = cells[0].find("a", href=re.compile(r"/purchase\?keyword="))
            order_no = order_a.get_text(strip=True) if order_a else ""
            rated_at = cells[2].get_text(strip=True)
            if (order_no, rated_at) in seen:
                continue
            seen.add((order_no, rated_at))
            content = parse_rating_content(cells[1])
            out.append({
                "name": name_a.get_text(strip=True) if name_a else "",
                "order_no": order_no, "rated_at": rated_at,
                "staff": cells[3].get_text(" ", strip=True) if len(cells) > 3 else "",
                **content,
            })
        if len(trs) < 15:
            break
    out.sort(key=lambda r: r["rated_at"])
    return out


def is_unsatisfied(rating: dict) -> bool:
    """服務滿意度為「尚可」或「不滿意」才登記清潔客訴（後台選項只有 滿意／尚可／不滿意）。"""
    return str(rating.get("items", {}).get("服務滿意度", "")).strip() in COMPLAINT_SATISFACTION


def negative_items(rating: dict) -> list[str]:
    return [f"{k}：{v}" for k, v in rating.get("items", {}).items()
            if k not in SKIP_ITEMS and v and v not in OK_ITEM_VALUES]


def negative_keywords(text: str) -> list[str]:
    return [k for k in NEGATIVE_KEYWORDS if k in str(text or "")]


def complaint_reason(rating: dict) -> str:
    """要登記清潔客訴的原因；不用登記回傳空字串。
    尚可／不滿意 → 一律登記；滿意 → 評價項目有非正面，或備註有負面字詞才登記。"""
    if is_unsatisfied(rating):
        return f"服務滿意度{rating['items']['服務滿意度']}"
    if str(rating.get("items", {}).get("服務滿意度", "")).strip() != "滿意":
        return ""
    reasons = negative_items(rating)
    words = negative_keywords(rating.get("note", ""))
    if words:
        reasons.append("意見含「" + "、".join(words[:5]) + "」")
    return ("滿意但" + "；".join(reasons)) if reasons else ""


def complaint_text(rating: dict) -> str:
    """客訴內容：（滿意但有疑慮的註記）＋服務滿意度＋非正面的評價項目＋備註＋訂單編號（重複判斷用）。"""
    items = rating.get("items", {})
    lines = []
    if not is_unsatisfied(rating):
        lines += [f"【{complaint_reason(rating)}，請客服判斷】"]
    lines += [f"服務滿意度：{items.get('服務滿意度', '')}"]
    lines += negative_items(rating)
    if rating.get("note"):
        lines += ["", f"備註：{rating['note']}"]
    lines += ["", f"訂單：{rating.get('order_no', '')}"]
    return "\n".join(lines)


def order_detail(session, order_no: str) -> dict:
    """被評價訂單的電話、服務日期、LINE 網址。"""
    import quick_order as qo

    block = qo._fetch_purchase_block_for_order_no(session, order_no)
    lines = block.get("lines", [])
    service_date, _ = qo._parse_service_date_time_loose("\n".join(lines))
    return {"phone": qo._extract_phone_from_block_lines(lines), "service_date": service_date or "",
            "line_url": block.get("line_url", "")}


def build_complaint_row(rating: dict, detail: dict, base_url: str) -> list:
    rated = parse_rating_time(rating["rated_at"]) or datetime.now()
    return [
        COMPLAINT_SOURCE, "", str(detail.get("service_date", "") or "").replace("/", "-"),
        rated.month, rated.strftime("%Y-%m-%d"), WEEKDAY_ZH[rated.weekday()],
        name_cell(rating.get("name", ""), detail.get("line_url", "")),
        phone_cell(base_url, detail.get("phone", "")) if detail.get("phone") else "",
        "", complaint_text(rating), "", "", rating.get("staff", ""),
    ]


# ------------------------------------------------------------
# 評價預約
# ------------------------------------------------------------
def build_booking_row(region: str, r: dict, base_url: str) -> list:
    """r 是 quick_order.fetch_rating_next_appointments 的一筆。"""
    name = name_cell(r.get("姓名", ""), r.get("LINE", ""))
    phone = phone_cell(base_url, r.get("電話", "")) if r.get("電話") else ""
    if region == "台中":
        return [name, r.get("地址", ""), f"{r.get('預約下次日期', '')} {r.get('預約下次時間', '')}".strip(), "",
                phone, r.get("評價日期", ""), r.get("服務日期及時間", ""), r.get("服務人數", ""),
                r.get("訂單編號", ""), r.get("LINE", "")]
    return ["", r.get("評價日期", ""), name, phone, r.get("地址", ""), r.get("預約下次日期", ""),
            r.get("預約下次時間", ""), r.get("服務日期及時間", ""), r.get("服務人數", ""),
            r.get("訂單編號", ""), r.get("LINE", "")]


def main_list_end(values: list[list], first_row: int) -> int:
    """主名單最後一列的列號：從 first_row 往下，遇到連續 MAIN_LIST_GAP 列全空白就結束。"""
    last, blank = first_row - 1, 0
    for idx in range(first_row - 1, len(values)):
        if any(str(v).strip() for v in values[idx]):
            if blank >= MAIN_LIST_GAP and last >= first_row:
                break
            last, blank = idx + 1, 0
        else:
            blank += 1
            if blank >= MAIN_LIST_GAP and last >= first_row:
                break
    return last


def last_row_by_columns(values: list[list], cols: tuple[int, ...]) -> int:
    """指定欄位（1 起算）最後一個有值的列號。"""
    last = 0
    for idx, row in enumerate(values, start=1):
        if any(c - 1 < len(row) and str(row[c - 1]).strip() for c in cols):
            last = idx
    return last


# ------------------------------------------------------------
# 工作表
# ------------------------------------------------------------
def get_tab(region: str, title: str):
    from memo_system.memo import with_retry
    from shared.customer_memo_schedule import open_spreadsheet

    spreadsheet = open_spreadsheet(region)
    for ws in with_retry(spreadsheet.worksheets):
        if ws.title == title:
            return spreadsheet, ws
    raise RuntimeError(f"{region}內勤工作表單找不到「{title}」分頁")


def insert_after(ws, after_row: int, rows: list[list]) -> None:
    """在 after_row 之後插入（沿用上一列格式；下方內容整段往下移）。"""
    from memo_system.memo import with_retry

    with_retry(ws.insert_rows, rows, row=after_row + 1, value_input_option="USER_ENTERED",
               inherit_from_before=True)


def existing_complaint_keys(values: list[list]) -> tuple[set, set]:
    """（客訴內容裡的訂單編號、客訴日期＋客戶）兩種重複判斷鍵。"""
    orders_seen, name_dates = set(), set()
    for row in values[COMPLAINT_FIRST_ROW - 1:]:
        cell = lambda i: str(row[i]).strip() if i < len(row) else ""  # noqa: E731
        orders_seen.update(re.findall(r"[A-Z]{2}\d{8,}", cell(9)))
        if cell(4) and cell(6):
            name_dates.add((cell(4).replace("/", "-"), cell(6)))
    return orders_seen, name_dates


# ------------------------------------------------------------
# 行事曆
# ------------------------------------------------------------
def build_calendar_event(job: str, result: dict, window, now: datetime) -> dict:
    prefix = CALENDAR_PREFIX[job]
    counts = "、".join(f"{region} {item.get('saved', 0)} 筆" for region, item in result.items())
    lines = [f"區間：{window[0]:%m/%d %H:%M} ～ {window[1]:%m/%d %H:%M}（評價時間）", ""]
    for region, item in result.items():
        lines.append(f"■ {region}：新增 {item.get('saved', 0)} 筆" + (f"（{item['error']}）" if item.get("error") else ""))
        if item.get("sheet_url"):
            lines.append(item["sheet_url"])
        lines += item.get("summary_lines") or []
        lines.append("")
    return dict(summary=f"{prefix}{counts}（{now:%m/%d}）", description="\n".join(lines).strip(),
                start=now, reminder_minutes=[0], replace_prefix=prefix)


def write_calendar(job: str, result: dict, window, now: datetime, service_factory=None) -> list[str]:
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event, service_for

    service_factory = service_factory or _calendar_service
    preferred = os.getenv("RATING_CALENDAR_ID", "").strip()
    event = build_calendar_event(job, result, window, now)
    last_error = None
    for calendar_id in ((preferred,) if preferred else CALENDAR_IDS):
        try:
            _insert_event(service_for(service_factory, calendar_id), calendar_id, **event)
            return [f"已記入行事曆 {calendar_id}"]
        except Exception as exc:
            last_error = exc
    return [f"⚠️ 記入行事曆失敗：{last_error}"]


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def _log(job: str, status: str, message: str, traceback_text: str = "", run_type: str = "排程") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME[job], status=status, run_type=run_type, area="台北／台中",
                      message=message, traceback_text=traceback_text)
    except Exception as exc:
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _login(region: str, env: str):
    import requests
    import quick_order as qo
    from accounts import ACCOUNTS

    account = ACCOUNTS.get(region) or {}
    email, password = str(account.get("email") or ""), str(account.get("password") or "")
    if not email or not password:
        raise RuntimeError(f"{region}未設定後台帳密（{region} EMAIL／PASSWORD Secrets）")
    base_url = qo._configure_environment(env)
    session = requests.Session()
    if not qo.login(session, email, password):
        raise RuntimeError(f"{region}後台登入失敗")
    return session, base_url, email, password


def _complaint_region(region: str, env: str, window, dry_run: bool, item: dict) -> None:
    from memo_system.memo import with_retry

    session, base_url, _, _ = _login(region, env)
    with contextlib.redirect_stdout(io.StringIO()):
        ratings = fetch_ratings(session, base_url, window[0].date().isoformat(), window[1].date().isoformat())
    targets = [r for r in ratings if in_window(r["rated_at"], window) and complaint_reason(r)]
    print(f"QUERY {region} 評價 {len(ratings)} 筆，區間內要登記 {len(targets)} 筆"
          f"（尚可／不滿意 {sum(1 for r in targets if is_unsatisfied(r))}）", flush=True)
    item["found"] = len(targets)
    spreadsheet, ws = get_tab(region, COMPLAINT_TAB)
    item["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}"
    values = with_retry(ws.get_all_values)
    orders_seen, name_dates = existing_complaint_keys(values)
    rows, summary = [], []
    for r in targets:
        rated = (parse_rating_time(r["rated_at"]) or datetime.now()).strftime("%Y-%m-%d")
        if r["order_no"] in orders_seen or (rated, r["name"]) in name_dates:
            continue
        try:
            detail = order_detail(session, r["order_no"]) if r["order_no"] else {}
        except Exception as exc:
            detail = {}
            summary.append(f"⚠️ {r['order_no']} 查訂單失敗：{exc}")
        rows.append(build_complaint_row(r, detail, base_url))
        summary.append(f"{r['rated_at'][:16]} {r['name']} {r['order_no']}：{complaint_reason(r)}"
                       + (f"／{r['note'][:40]}" if r.get("note") else ""))
    item["summary_lines"] = summary
    if rows and not dry_run:
        last = max(last_row_by_columns(values, (3, 5, 7)), COMPLAINT_FIRST_ROW - 1)
        insert_after(ws, last, rows)
    item["saved"] = len(rows)
    print(f"SAVE {region} 清潔客訴新增 {len(rows)} 筆（已登記略過 {len(targets) - len(rows)} 筆）", flush=True)


def _booking_region(region: str, env: str, window, dry_run: bool, item: dict) -> None:
    import quick_order as qo
    from memo_system.memo import with_retry

    _, base_url, email, password = _login(region, env)
    with contextlib.redirect_stdout(io.StringIO()):
        found = qo.fetch_rating_next_appointments(env, email, password, window[0].date().isoformat(),
                                                  window[1].date().isoformat())
    targets = [r for r in found if in_window(r.get("評價時間", ""), window)]
    print(f"QUERY {region} 預約下次服務 {len(found)} 筆，區間內 {len(targets)} 筆", flush=True)
    item["found"] = len(targets)
    layout = BOOKING_LAYOUTS[region]
    spreadsheet, ws = get_tab(region, BOOKING_TAB)
    item["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}"
    values = with_retry(ws.get, f"A1:{_col_letter(max(layout['width'], 11))}{ws.row_count}")
    key_idx = layout["key_col"] - 1
    seen = {str(row[key_idx]).strip() for row in values if key_idx < len(row) and str(row[key_idx]).strip()}
    rows, summary = [], []
    for r in targets:
        if r.get("訂單編號") in seen:
            continue
        seen.add(r.get("訂單編號"))
        rows.append(build_booking_row(region, r, base_url))
        summary.append(f"{r.get('評價時間', '')[:16]} {r.get('姓名', '')} 預約 {r.get('預約下次日期', '')} "
                       f"{r.get('預約下次時間', '')}（上次 {r.get('訂單編號', '')}）")
    item["summary_lines"] = summary
    if rows and not dry_run:
        insert_after(ws, main_list_end(values, layout["first_row"]), rows)
    item["saved"] = len(rows)
    print(f"SAVE {region} 評價預約新增 {len(rows)} 筆（已在名單略過 {len(targets) - len(rows)} 筆）", flush=True)


def run(job: str, env: str = "prod", today: date | None = None, regions=REGIONS, dry_run: bool = False,
        calendar: dict | None = None, now: datetime | None = None) -> dict:
    _preload_modules()
    from shared.weekend_reminder_schedule import is_off_day, load_work_calendar

    calendar = load_work_calendar() if calendar is None else calendar
    now = now or datetime.now(TZ)
    today = today or now.date()
    if is_off_day(today, calendar):
        print(f"SKIP {today} 不是上班日", flush=True)
        return {"due": False, "today": str(today)}
    window = query_window(today, calendar)
    print(f"WINDOW {window[0]:%Y-%m-%d %H:%M} ～ {window[1]:%Y-%m-%d %H:%M}", flush=True)
    worker = _complaint_region if job == "complaint" else _booking_region

    result: dict = {}
    for region in regions:
        item = {"found": 0, "saved": 0, "sheet_url": "", "error": "", "summary_lines": []}
        result[region] = item
        try:
            worker(region, env, window, dry_run, item)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)

    for line in ([] if dry_run else write_calendar(job, result, window, now)):
        print(line, flush=True)
    errors = [f"{r}：{i['error']}" for r, i in result.items() if i["error"]]
    message = (f"{window[0]:%m/%d %H:%M}～{window[1]:%m/%d %H:%M}："
               + "；".join(f"{r} 符合 {i['found']} 筆新增 {i['saved']} 筆" for r, i in result.items())
               + ("（試跑，未寫入）" if dry_run else ""))
    if errors:
        message += "；錯誤 " + "；".join(errors)
    print(f"FINISH {message}", flush=True)
    if not dry_run:
        _log(job, "失敗" if errors else "成功", message)
    if errors and len(errors) == len(result):
        raise RuntimeError("；".join(errors))
    return {"due": True, "window": window, "result": result}


# ------------------------------------------------------------
# 整理電話／姓名連結（手動）
# ------------------------------------------------------------
def line_url_by_phone(session, phone: str, cache: dict) -> str:
    """後台訂單管理用電話搜尋，取第一個 LINE 聊天連結（同一支電話只查一次）。"""
    import orders
    import quick_order as qo
    from bs4 import BeautifulSoup
    from shared.backend_client import PURCHASE_FILTER_PARAMS_TEMPLATE

    phone = normalize_phone(phone)
    if not phone:
        return ""
    if phone not in cache:
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["phone"] = phone
        resp = session.get(orders.PURCHASE_URL, params=params, headers=qo.HEADERS, allow_redirects=True)
        link = BeautifulSoup(resp.text, "html.parser").find("a", href=re.compile(r"chat\.line\.biz")) \
            if resp.status_code == 200 else None
        cache[phone] = str(link.get("href", "")).strip() if link else ""
    return cache[phone]


def relink_updates(formulas: list[list], name_col: int, phone_col: int, first_row: int, base_url: str,
                   lookup, line_col: int = 0, last_row: int = 0) -> list[dict]:
    """回傳要更新的儲存格（已經是 HYPERLINK 的不動）。lookup(phone) → LINE 網址。"""
    updates = []
    end = last_row or len(formulas)
    for idx in range(first_row - 1, min(end, len(formulas))):
        row = formulas[idx]
        cell = lambda c: str(row[c - 1]).strip() if c - 1 < len(row) else ""  # noqa: E731
        name, phone_raw = cell(name_col), cell(phone_col)
        phone = "" if phone_raw.upper().startswith("=HYPERLINK") else normalize_phone(phone_raw)
        if phone_raw.upper().startswith("=HYPERLINK"):
            m = re.search(r'"([^"]*)"\s*\)\s*$', phone_raw)
            phone_for_line = normalize_phone(m.group(1)) if m else ""
        else:
            phone_for_line = phone
        if phone and len(phone) >= 9:
            updates.append({"range": f"{_col_letter(phone_col)}{idx + 1}", "values": [[phone_cell(base_url, phone)]]})
        if name and not name.startswith("="):
            line_url = cell(line_col) if line_col and "chat.line.biz" in cell(line_col) else ""
            line_url = line_url or (lookup(phone_for_line) if phone_for_line else "")
            if line_url:
                updates.append({"range": f"{_col_letter(name_col)}{idx + 1}", "values": [[name_cell(name, line_url)]]})
    return updates


def col_index(letter: str) -> int:
    """欄位字母 → 1 起算的欄號（支援 AB、AC 等多字母）。"""
    letter = str(letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", letter):
        raise ValueError(f"欄位格式錯誤：{letter or '（空白）'}")
    n = 0
    for ch in letter:
        n = n * 26 + ord(ch) - 64
    return n


def spreadsheet_key(text: str) -> str:
    """Google Sheet 網址或 ID → ID。"""
    text = str(text or "").strip()
    m = re.search(r"/spreadsheets/d/([\w-]+)", text)
    key = m.group(1) if m else text
    if not re.fullmatch(r"[\w-]{20,}", key):
        raise ValueError("請貼 Google Sheet 網址或 ID")
    return key


def login_session(email: str, password: str, env: str = "prod"):
    """用指定後台帳密登入（獨立功能用畫面上的帳密）。"""
    import requests
    import quick_order as qo

    base_url = qo._configure_environment(env)
    session = requests.Session()
    if not qo.login(session, email, password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")
    return session, base_url


def plan_sheet_links(ws, session, base_url: str, name_col: int, phone_col: int, first_row: int,
                     last_row: int = 0, line_col: int = 0) -> list[dict]:
    """任一工作表：回傳要更新的儲存格（姓名→LINE 連結、電話→訂單管理電話查詢連結）。"""
    from memo_system.memo import with_retry

    width = max(name_col, phone_col, line_col or 0)
    end = last_row or ws.row_count
    formulas = with_retry(ws.get, f"A1:{_col_letter(width)}{end}", value_render_option="FORMULA")
    if not last_row:
        cols = (name_col, phone_col)
        last_row = last_row_by_columns(formulas, cols)
    cache: dict = {}
    return relink_updates(formulas, name_col, phone_col, first_row, base_url,
                          lambda p: line_url_by_phone(session, p, cache), line_col=line_col, last_row=last_row)


def apply_updates(ws, updates: list[dict]) -> None:
    from memo_system.memo import with_retry

    for i in range(0, len(updates), 200):
        with_retry(ws.batch_update, updates[i:i + 200], value_input_option="USER_ENTERED")


def relink(env: str = "prod", regions=REGIONS, dry_run: bool = False) -> dict:
    _preload_modules()
    from memo_system.memo import with_retry

    result = {}
    for region in regions:
        item = {"updated": {}, "error": ""}
        result[region] = item
        try:
            session, base_url, _, _ = _login(region, env)
            cache: dict = {}
            lookup = lambda p: line_url_by_phone(session, p, cache)  # noqa: E731
            targets = [(COMPLAINT_TAB, COMPLAINT_NAME_COL, COMPLAINT_PHONE_COL, COMPLAINT_FIRST_ROW, 0, True)]
            lay = BOOKING_LAYOUTS[region]
            targets.append((BOOKING_TAB, lay["name_col"], lay["phone_col"], lay["first_row"], lay["line_col"], False))
            for title, name_col, phone_col, first_row, line_col, complaint in targets:
                _, ws = get_tab(region, title)
                formulas = with_retry(ws.get, f"A1:{_col_letter(max(ws.col_count, 11))}{ws.row_count}",
                                      value_render_option="FORMULA")
                last = last_row_by_columns(formulas, (3, 5, 7)) if complaint else 0
                with contextlib.redirect_stdout(io.StringIO()):
                    updates = relink_updates(formulas, name_col, phone_col, first_row, base_url, lookup,
                                             line_col=line_col, last_row=last)
                if updates and not dry_run:
                    for i in range(0, len(updates), 200):
                        with_retry(ws.batch_update, updates[i:i + 200], value_input_option="USER_ENTERED")
                item["updated"][title] = len(updates)
                print(f"RELINK {region} {title} 更新 {len(updates)} 格" + ("（試跑）" if dry_run else ""), flush=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)
    message = "；".join(f"{r} " + "、".join(f"{t} {n} 格" for t, n in i["updated"].items())
                       + (f"（{i['error']}）" if i["error"] else "") for r, i in result.items())
    print(f"FINISH {message}", flush=True)
    if not dry_run:
        _log("relink", "失敗" if any(i["error"] for i in result.values()) else "成功", message, run_type="手動")
    return result


def main():
    _preload_modules()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--job", required=True, choices=("complaint", "booking", "relink"))
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default="台北,台中")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫入工作表、不寫行事曆")
    args = parser.parse_args()
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        if args.job == "relink":
            relink(env=args.env, regions=regions, dry_run=args.dry_run)
        else:
            today = date.fromisoformat(args.date) if args.date.strip() else None
            run(args.job, env=args.env, today=today, regions=regions, dry_run=args.dry_run)
    except Exception as exc:
        _log(args.job, "失敗", str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
