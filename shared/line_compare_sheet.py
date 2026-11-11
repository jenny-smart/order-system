# -*- coding: utf-8 -*-
"""代客預訂 LINE 比對（第一步）：撈出待比對的代客預訂訂單，貼到內勤工作表單「line比對」分頁。

更新記錄：
2026-11-12（新增）
- 訂單編號認 LC／TT／KK（測試機是 TT），列表改由本檔自行解析。
- 依訂購日期（後台「購買日期」）逐日查詢，付款狀態只查「已付款」「待付款」，
  只留列表卡片上方有「代客預訂：○○」的訂單。
- 貼到該區「內勤工作表單」的「line比對」分頁最下方，欄位：
  訂購日期／訂單編號／訂購人／電話號碼／服務日期／服務時段／付款狀態／
  訂單金額（推算人數）／比對對話結果／代客預約人名
  訂購人是 HYPERLINK（客人 LINE 聊天連結，取自列表卡片的 LINE 連結；沒有連結維持文字）；
  電話號碼是 HYPERLINK（後台訂單管理用電話搜尋的結果頁）。
  訂單編號已在分頁上的不重複貼；沒有分頁時自動建立並寫標題列。
- 推算人數：卡片有「N人M小時」直接用；沒有則用（總金額－車馬費）÷（時數×每人時單價）推算，
  VIP／一般客單價都試，能整除才採用；再不行用卡片上已配班的專員人數。都推不出來只寫金額。
- 「比對對話結果」留白，下一步（LINE 對話比對）再填。只讀後台，不修改後台。

手動執行（預設今天、台北＋台中）：
    python -m shared.line_compare_sheet --start 2026-11-12 --end 2026-11-12 --regions 台北 --dry-run
"""
from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

TOOL_NAME = "代客預訂 LINE 比對：撈出待比對訂單"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北", "台中", "桃園", "新竹", "高雄")
DEFAULT_REGIONS = ("台北", "台中")
SHEET_CATEGORY = "內勤工作表單"
TAB_TITLE = "line比對"
HEADER = ["訂購日期", "訂單編號", "訂購人", "電話號碼", "服務日期", "服務時段", "付款狀態",
          "訂單金額（推算人數）", "比對對話結果", "代客預約人名"]
KEY_COL = 2  # 訂單編號在 B 欄
STATUSES = (("1", "已付款"), ("0", "待付款"))  # 後台 purchase_status 參數 → 工作表上的文字
MAX_DAYS = 31

_PROXY_RE = re.compile(r"代客預[訂約]\s*[：:]\s*([^\n]*)")
_ORDER_NO_RE = re.compile(r"(?:LC|TT|KK)\d+")  # 正式 LC、測試機 TT（同 orders.ORDER_NO_REGEX）


# ------------------------------------------------------------
# 卡片解析
# ------------------------------------------------------------
def proxy_booker(row_text: str) -> str:
    """列表卡片「代客預訂：瑋萱」的代客預約人名；不是代客預訂回傳空字串。"""
    m = _PROXY_RE.search(str(row_text or ""))
    if not m:
        return ""
    return m.group(1).strip() or "（未標示）"


def is_proxy(row_text: str) -> bool:
    return bool(_PROXY_RE.search(str(row_text or "")))


def customer_name(row_text: str, fallback: str = "") -> str:
    """訂購人＝「代客預訂：○○」的下一行（卡片順序：代客預訂／姓名／電話）。"""
    lines = [x.strip() for x in str(row_text or "").splitlines() if x.strip()]
    for i, line in enumerate(lines):
        if _PROXY_RE.match(line) and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not re.fullmatch(r"[\d\-－\s]+", nxt) and "@" not in nxt:
                return nxt
            break
    return str(fallback or "")


def _money(row_text: str, label: str):
    m = re.search(rf"{label}\s*[：:]\s*\$?\s*(-?[\d,]+)", str(row_text or ""))
    return int(m.group(1).replace(",", "")) if m else None


def estimate_persons(item: dict, config=None) -> str:
    """推算人數；推不出來回傳空字串。"""
    text = str(item.get("row_text", "") or "")
    m = re.search(r"(\d+)\s*人\s*\d+(?:\.\d+)?\s*(?:小時|時)", text)
    if m:
        return m.group(1)

    total, fare = _money(text, "總金額"), _money(text, "車馬費") or 0
    try:
        hours = float(item.get("hour") or 0)
    except (TypeError, ValueError):
        hours = 0
    service_date = str(item.get("service_date", "") or "")
    if total and hours > 0 and service_date and total - fare > 0:
        try:
            import service_pricing

            for tier in ("vip", "regular"):
                unit = float(service_pricing.unit_price(service_date, tier, config))
                if unit <= 0:
                    continue
                persons = (total - fare) / (unit * hours)
                if persons >= 1 and abs(persons - round(persons)) < 0.01:
                    return str(int(round(persons)))
        except Exception:
            pass

    staff = int(item.get("staff_count") or 0)
    return str(staff) if staff else ""


def amount_text(item: dict, config=None) -> str:
    """「訂單金額（推算人數）」欄：4,650（2人）；金額讀不到時只寫人數。"""
    total = _money(item.get("row_text", ""), "總金額")
    persons = estimate_persons(item, config)
    amount = f"{total:,}" if total is not None else ""
    return f"{amount}（{persons}人）" if persons else amount


def parse_list_html(html: str) -> list[dict]:
    """後台訂單列表一頁 → 訂單（卡片欄位＋服務日期＋LINE 連結＋已配班專員人數）。

    不用 memo.parse_purchase_list_page：它只認 LC 開頭，測試機（TT）整頁會被當成沒有訂單。
    """
    from memo_system import memo

    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, dict] = {}
    for tr in soup.select("table tbody tr") or soup.select("tr"):
        text = tr.get_text("\n", strip=True)
        m = _ORDER_NO_RE.search(text)
        if not m:
            continue
        item = memo.parse_purchase_row_text(text)
        item["order_no"] = m.group(0)
        tds = tr.find_all("td", recursive=False)
        if len(tds) > 2:
            m_sd = re.search(r"\d{4}-\d{2}-\d{2}", tds[2].get_text(" ", strip=True))
            if m_sd:
                item["service_date"] = m_sd.group(0).replace("-", "/")
        link = tr.find("a", href=re.compile(r"chat\.line\.biz"))
        item["line_url"] = str(link.get("href") or "").strip() if link else ""
        item["staff_count"] = len(tr.select('a[href*="schedule/edit"]'))
        items[item["order_no"]] = item
    return list(items.values())


# ------------------------------------------------------------
# 後台查詢
# ------------------------------------------------------------
def _fetch_list(session, params: dict) -> list[dict]:
    """同一組條件自動翻頁（沒有新訂單就停）。"""
    from memo_system import memo

    merged: dict[str, dict] = {}
    for page in range(1, memo.LIST_MAX_PAGES + 1):
        r = memo.session_get(session, memo.PURCHASE_URL, params={**params, "page": str(page)})
        r.raise_for_status()
        new_items = [x for x in parse_list_html(r.text) if x.get("order_no") and x["order_no"] not in merged]
        if not new_items:
            break
        for x in new_items:
            merged[x["order_no"]] = x
    return list(merged.values())


def each_day(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def fetch_proxy_orders(session, start: date, end: date, log=None, config=None) -> list[dict]:
    """訂購日期 start～end（含）內，已付款／待付款的代客預訂訂單（依訂購日期、訂單編號排序）。"""
    from memo_system import memo

    log = log or (lambda m: None)
    if start > end:
        raise ValueError("開始日期不可晚於結束日期")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"一次最多查 {MAX_DAYS} 天")

    rows: dict[str, dict] = {}
    for day in each_day(start, end):
        day_total = day_proxy = 0
        for status_code, status_name in STATUSES:
            params = memo.blank_list_params()
            params["date_s"] = params["date_e"] = day.strftime("%Y-%m-%d")
            params["purchase_status"] = status_code
            for item in _fetch_list(session, params):
                day_total += 1
                text = item.get("row_text", "")
                if not is_proxy(text) or item["order_no"] in rows:
                    continue
                day_proxy += 1
                rows[item["order_no"]] = {
                    "訂購日期": day.strftime("%Y/%m/%d"),
                    "訂單編號": item["order_no"],
                    "訂購人": customer_name(text, item.get("name", "")),
                    "LINE連結": item.get("line_url", ""),
                    "電話號碼": item.get("phone", ""),
                    "服務日期": item.get("service_date", ""),
                    "服務時段": item.get("period", ""),
                    "付款狀態": status_name,
                    "訂單金額（推算人數）": amount_text(item, config),
                    "代客預約人名": proxy_booker(text),
                }
        log(f"[{day:%m/%d}] 已付款＋待付款 {day_total} 筆，其中代客預訂 {day_proxy} 筆")
    return sorted(rows.values(), key=lambda r: (r["訂購日期"], r["訂單編號"]))


# ------------------------------------------------------------
# 工作表
# ------------------------------------------------------------
def build_sheet_rows(rows: list[dict], base_url: str) -> list[list[str]]:
    from shared.rating_schedule import name_cell, phone_cell

    return [[
        r["訂購日期"],
        r["訂單編號"],
        name_cell(r["訂購人"], r.get("LINE連結", "")),
        phone_cell(base_url, r["電話號碼"]),
        r["服務日期"],
        r["服務時段"],
        r["付款狀態"],
        r["訂單金額（推算人數）"],
        "",  # 比對對話結果：下一步填
        r["代客預約人名"],
    ] for r in rows]


def get_tab(region: str):
    """該區當年度內勤工作表單的「line比對」分頁（名稱不分大小寫、忽略空白）；沒有就建立。"""
    from memo_system.memo import with_retry
    from shared import customer_memo_schedule as cms

    spreadsheet = cms.open_spreadsheet(region)
    wanted = TAB_TITLE.replace(" ", "").lower()
    title = next((ws.title for ws in with_retry(spreadsheet.worksheets)
                  if ws.title.replace(" ", "").lower() == wanted), TAB_TITLE)
    return cms.get_tab(region, title, HEADER, spreadsheet=spreadsheet)


def plan(region: str, session, base_url: str, start: date, end: date, log=None) -> dict:
    """查後台＋比對分頁上已有的訂單編號；不寫入。"""
    from memo_system.memo import with_retry

    rows = fetch_proxy_orders(session, start, end, log=log)
    spreadsheet, ws = get_tab(region)
    existing = {str(v).strip() for v in with_retry(ws.col_values, KEY_COL) if str(v).strip()}
    new_rows = [r for r in rows if r["訂單編號"] not in existing]
    preview = [{"狀態": "已在工作表" if r["訂單編號"] in existing else "新增", **r} for r in rows]
    return {
        "region": region, "rows": rows, "new_rows": new_rows, "preview": preview, "ws": ws,
        "sheet_rows": build_sheet_rows(new_rows, base_url),
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}",
    }


def write(plan_result: dict) -> int:
    """把 plan 的新增列貼到分頁最下方；回傳實際貼入筆數。"""
    from shared import customer_memo_schedule as cms

    return cms.append_rows(plan_result["ws"], plan_result["sheet_rows"], width=len(HEADER), key_col=KEY_COL)


# ------------------------------------------------------------
# 指令列（之後接排程用）
# ------------------------------------------------------------
def run(env: str = "prod", start: date | None = None, end: date | None = None,
        regions=DEFAULT_REGIONS, dry_run: bool = False) -> dict:
    from shared.customer_memo_schedule import _preload_modules

    _preload_modules()
    from accounts import ACCOUNTS
    from memo_system import memo

    today = datetime.now(TZ).date()
    start = start or today
    end = end or start
    memo.set_env(env)
    result: dict = {}
    for region in regions:
        item = {"found": 0, "saved": 0, "sheet_url": "", "error": ""}
        result[region] = item
        try:
            account = ACCOUNTS.get(region) or {}
            email, password = str(account.get("email") or ""), str(account.get("password") or "")
            if not email or not password:
                raise RuntimeError(f"{region}未設定後台帳密")
            memo.set_runtime_credentials(email, password)
            session = memo.login()
            if dry_run:
                item["found"] = len(fetch_proxy_orders(session, start, end))
            else:
                p = plan(region, session, memo.BASE_URL, start, end)
                item["found"], item["sheet_url"] = len(p["rows"]), p["sheet_url"]
                item["saved"] = write(p)
            # 紀錄只印筆數，不印客戶姓名、電話
            print(f"{region} 代客預訂 {item['found']} 筆，貼入 {item['saved']} 筆", flush=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)
    errors = [f"{r}：{i['error']}" for r, i in result.items() if i["error"]]
    if errors and len(errors) == len(result):
        raise RuntimeError("；".join(errors))
    return result


def main():
    parser = argparse.ArgumentParser(description=TOOL_NAME)
    parser.add_argument("--env", default="prod")
    parser.add_argument("--start", default="", help="訂購日期起（YYYY-MM-DD，空白＝今天）")
    parser.add_argument("--end", default="", help="訂購日期迄（YYYY-MM-DD，空白＝同起日）")
    parser.add_argument("--regions", default=",".join(DEFAULT_REGIONS), help="逗號分隔")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫入工作表")
    args = parser.parse_args()
    start = date.fromisoformat(args.start) if args.start.strip() else None
    end = date.fromisoformat(args.end) if args.end.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or DEFAULT_REGIONS
    run(env=args.env, start=start, end=end, regions=regions, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
